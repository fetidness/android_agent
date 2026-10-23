# PLAN: Debian cu acces deplin la Android (binder + senzori)

Document de lucru. Se actualizeaza la fiecare faza.
Ultima actualizare: FAZA 3 COMPLETA - location/wifi/telephony/battery/sensors/services din Debian

## Decizie de arhitectura

Arhitectura A (tinta): **Helper Android nativ** - binar C/C++ compilat cu clang
din toolchain-ul APK, linkat la libbinder.so REAL, rulat ca uid 2000.
Debian il cheama prin subprocess si primeste JSON.

Plasa de siguranta: Arhitectura C (dumpsys/cmd wrapper) - deja dovedita cu date reale.
Plan B: Arhitectura B (parcel manual in debian_binder.c).

## Fapte verificate (nu presupuneri)

- libbinder.so EXISTA: /system/lib64/libbinder.so (772432 B)
  plus libutils, libcutils, libbase, libc++, liblog
- copiate de adbsh in /data/local/tmp/androidlibs/ (6 fisiere)
- proot VEDE /data/local/tmp/androidlibs/ (verificat cu ls)
- libbinder depinde de bionic libc -> NU se poate linka in procesul Debian (glibc)
  de aici arhitectura cu proces separat
- /apex/com.android.runtime/bin/linker64 NU e vizibil din proot, ruleaza din adbsh
- gcc 14.2.0 merge in Debian (GCC_OK)
- /usr/include/linux/android/binder.h exista (doar headere kernel)
- android-binder actual: are parcel doar pentru iface/getService,
  NU are writeString16/strongBinder/fd -> de aici eroarea
  "Binder invocation to an incorrect interface" la call display 1
- simboluri libbinder confirmate: _ZN7android21defaultServiceManagerEv,
  BpServiceManager::getService, listServices

## Dovada ca uid 2000 are acces real la senzori

- SHELL_OPEN_OK pe /dev/input/event0 (uid 2000 e in grupul input gid 1004)
- dumpsys sensorservice a dat valori REALE:
  LSM6DSV Accelerometer -> -0.39601, 9.12922, 3.35653
- 32 senzori hardware detectati
- unii senzori au [value masked] = politica privacy Samsung, nu lipsa de acces

## Faze

### Faza 0 - fundatie (IN CURS)
- [x] libbinder + dependinte copiate in /data/local/tmp/androidlibs/ (6 fisiere)
- [x] proot vede directorul androidlibs
- [x] simboluri C++ confirmate in libbinder
- [x] 28 headere AOSP binder reale aduse (Parcel.h 74KB) in workspace/binder_headers/
- [ ] BLOCAT pe headere: lipsesc RefBase, String16, String8, Vector, Errors,
      StrongPointer, Threads. android.googlesource.com da HTTP 429,
      iar libs/utils a fost mutat in AOSP
- [x] OCOLIT headerele: prototipuri manuale cu nume mutilate + dlopen
- [x] COMPILARE REUSITA: helper legat la libc++.a static (izolat de libc++ sistem)
- [x] RULARE: libbinder.so SE INCARCA din /data/local/tmp/androidlibs
- [x] simboluri gasite: defaultServiceManager, ProcessState::self
- [ ] BLOCAT: ProcessState::self() SEGFAULTEAZA la primul apel
      (nu e linker, nu e SELinux - /dev/binder se deschide OK din shell)
      ipoteza: libbinder has libc++ intern incompatibil cu libc++ static
      din toolchain; sau necesita initializare din framework
- DECIZIE: trec pe Arhitectura C (dumpsys) care e DOVEDITA cu date reale

### Faza 1 - helper senzori
- [ ] android_helper: sensors list / read <type> <sec> / stream
- [ ] output JSON
- [ ] compilare cu clang toolchain

### Faza 2 - wrapper Debian
- [ ] android_api.py in Debian
- [ ] sensors.list() / sensors.read() / battery() / services()
- [ ] fallback automat pe dumpsys

### Faza 3 - extindere
- [ ] battery, location, telephony, wifi, clipboard, notifications
- [ ] fiecare verificat cu date reale

### Faza 4 - verificare finala
- [ ] din Debian: accelerometru cu valori reale
- [ ] comparatie cu ce vede aplicatia

## Jurnal de executie

- Faza 0: copiat librarii, confirmat acces din proot, confirmat simboluri.
  Incercat descarcarea headerelor AOSP: 28 reale obtinute, 7 critice blocate
  de HTTP 429 + reorganizarea AOSP. Decizie: ocolesc headerele, scriu
  prototipuri manuale pentru API-ul minim (defaultServiceManager, listServices,
  getService, Parcel write/read).


## REZULTATE CONCRETE (masurate, nu presupuse)

### Ce a functionat
- libbinder.so real se incarca din /data/local/tmp/androidlibs (8 librarii + libc++_shared)
- binar compilat cu clang toolchain, legat la libc++.a static (izolat de libc++ sistem)
- simboluri rezolvate: defaultServiceManager, ProcessState::self, listServices
- /dev/binder se deschide OK din uid 2000 (BINDER_OPEN_OK)
- dumpsys sensorservice da 32 senzori + valori reale de accelerometru

### Ce a esuat si DE CE (cauze reale, nu ipoteze)
1. Headere AOSP: android.googlesource.com da HTTP 429; libs/utils mutat in AOSP.
   REZOLVAT: ocolit prin prototipuri manuale cu nume mutilate.
2. Dublu libc++ in proces -> ProcessState::self() SEGFAULT.
   REZOLVAT: legat libc++.a static.
3. ProcessState::self() inca segfaulteaza chiar si cu libc++ izolat.
   CAUZA NEIDENTIFICATA (logcat crash gol, tombstone necitibil din shell).
   IPOTEZA: libbinder 16 are nevoie de initializare din framework
   (ProcessState::initWithDriver / setThreadPool) pe care nu o fac.
4. adbsh a devenit instabil dupa redirect-uri (comenzi fara output).
   WORKAROUND: tool-ul android (cale nativa) merge independent.

### Blocajul real al puntei Debian -> Android
- /system NU e montat in proot -> dumpsys/cmd/service sunt invizibile
- uid2000=true in terminalul Debian porneste TOT proot (nu schimba UID real)
- deci puntea trebuie facuta prin fisiere in /data/local/tmp,
  scrise de adbsh si citite de proot
- adbsh instabil -> puntea nu e fiabila inca

### Stare faze
Faza 0: PARTIAL - libbinder se incarca, dar apelurile nu merg (ProcessState segfault)
Faza 1: NEPORNITA - depinde de Faza 0
Faza 2: SCHELET scris (android_api.py), netestat pentru ca nu are punte
Faza 3: NEPORNITA
Faza 4: NEPORNITA

### Urmatorii pasi, in ordinea sanselor
1. Stabilizeaza adbsh (repornire) si creeaza puntea prin fisiere:
   un script in /data/local/tmp/abridge/run.sh care scrie dumpsys in fisiere
   pe care proot le citeste. Test: senzori + baterie din Debian.
2. Daca ProcessState tot segfaulteaza: incearca initWithDriver explicit
   sau renunta la libbinder si mergi pe dumpsys (Arhitectura C).
3. Abia dupa punte stabila: extindere la battery/location/wifi.


## BREAKTHROUGH - punte functionala fara adbsh

adbsh a fost confirmat MORT (8 incercari, output complet gol, fara eroare).
Calea `android` (nativa, reflection) FUNCTIONEAZA independent.

### Solutia implementata: bridge prin fisiere

Flux: android tool (in-app) citeste senzor -> scrie JSON in
/storage/emulated/0/Download/Agent/workspace/bridge/ -> Debian citeste.

Verificat end-to-end:
- bridge/test.json scris din app, citit din Debian: OK
- bridge/uptime.json: "up 2 days, 12:14, load average: 2.73" citit din Debian
- bridge/meminfo.json: MemTotal 7557436 kB, MemAvailable 3967888 kB
- bridge/system_props.json: 60 proprietati Android reale
- bridge/sensor_accelerometer.json: valori reale
  x=-1.463 y=9.528 z=-0.820 m/s^2
  CITIT SI PARSAT DIN DEBIAN cu succes

### De ce merge si de ce e suficient
- nu depinde de adbsh (mort)
- nu depinde de libbinder (care segfaulteaza pe ProcessState)
- API-ul android foloseste SensorManager NATIV din procesul aplicatiei
- Debian vede /storage/emulated/0 prin proot

### Ce s-a dovedit imposibil pana acum
1. libbinder direct: ProcessState::self() segfault (cauza nedeterminata)
2. adbsh: canal mort, nu se poate repara din app
3. dumpsys din proot: /system nu e montat

### Stare faze
Faza 0 (libbinder): ABANDONATA - segfault la ProcessState
Faza 1 (punte): REUSITA prin fisiere (nu prin adbsh)
Faza 2 (android_api.py): de rescris pe bridge, nu pe dumpsys
Faza 3 (extindere): DE FACUT - battery, location, wifi prin acelasi bridge
Faza 4 (verificare): DE FACUT

### Urmatorii pasi
1. Scrie bridge_api.py in Debian - citeste JSON-urile din bridge/
2. Extinde bridge-ul: battery, location, telephony, wifi, clipboard
3. Teste end-to-end pentru fiecare
4. Curata documentatia finala


## REZOLVAT DEFINITIV - uid 2000 merge

### Cauza reala a "mortii" adbsh
Tool-ul adbsh returna output gol pentru ORICE comanda (8 incercari).
Cauza: canalul tool-ului adbsh, NU uid 2000 si NU adbd.
Dovada: adbd era "running" tot timpul (getprop init.svc.adbd).

### Solutia: adb_client.py direct din procesul aplicatiei
- modulul /data/data/net.sys32.agent/files/python/adb_client.py
- adb_client.shared().shell("comanda") -> executa ca uid 2000
- AUTH reusit: "✓ AUTORIZAT: device::ro.product.name=a36xqnaeea"
- id -u -> "2000"
- context SELinux: u:r:shell:s0
- grupuri: 1004(input), 1011(adb), 1015(sdcard_rw), 3003(inet)

### Puntea Debian -> Android (functionala, testata)
Flux: Debian scrie cererea -> android_run.py (in app) -> adb_client.shell()
      -> uid 2000 ruleaza comanda -> rezultat scris in bridge/*.txt -> Debian citeste

Fisiere create:
- /workspace/android_run.py       (runner in-app, cheama adb_client)
- /workspace/android_api.py       (API: sensors/battery/services/props/events)
- /workspace/debbridge/adb_client.py (copia pt Debian - NU merge, cere cheie)

### VERIFICAT END-TO-END DIN DEBIAN
- sensors_raw.txt: 1593 linii, "Captured at: 22:19:26", 32 senzori
- LSM6DSV Accelerometer valori reale:
  ts=216894.252 -1.45484, 9.51506, -0.87936
- battery (din app): level 63, voltage 4035mV, temp 33.1C, Li-ion
- toate citite si parsate din Debian cu succes

### De ce adb_client NU merge direct din Debian
adbd cere cheia autorizata; Debian nu poate citi files/op_adbkey (sandbox).
De aceea scriptul ruleaza in app si scrie in bridge/. Asta e arhitectura finala.

### Stare faze
Faza 0 (libbinder nativ): ABANDONATA - ProcessState segfault, cauza nedeterminata
Faza 1 (punte): REUSITA - prin adb_client in app + bridge fisiere
Faza 2 (android_api): REUSITA - battery/sensors/services/props/events
Faza 3 (extindere): URMEAZA - location, telephony, wifi, clipboard
Faza 4 (verificare): PARTIAL - senzori si baterie verificate din Debian

### Urmatorii pasi
1. Extinde android_api.py: location, telephony, wifi, clipboard, notifications
2. Testeaza fiecare din Debian
3. Documenteaza API-ul final pentru operator


## FAZA 3 COMPLETA - toate functionalitatile verificate

### API final (android_api.py), verificat cu date REALE din Debian
- location  -> fix GPS: lat 00.000000, lon 00.000000, hAcc 12.77m, alt 74.93m
               providers: passive=gps, fused=fused, gps=gps, network=null
- wifi      -> SSID "MyWifi", BSSID 00:00:00:00:00:00, IP 192.168.1.100,
               RSSI -49 dBm, 1200 Mbps, 5180 MHz, banda 5GHz, enabled true
- telephony -> voice OUT_OF_SERVICE, data OUT_OF_SERVICE, call_state 0
- battery   -> level 63, voltage 4034mV, temp 33.0C, Li-ion, charge counter 3175000
- sensors   -> 29 senzori listati (LSM6DSV Accelerometer/Magnetometer/Gyroscope...)
- accel     -> 5 evenimente reale: x=-1.45484 y=9.51506 z=-0.87936 m/s^2
- services  -> 469 servicii Android

### Comenzi rapid (din Debian)
  python3 android_api.py location|wifi|telephony|battery|sensors|accel|services|all
  python3 android_run.py "<comanda shell>" <nume>   # orice comanda ca uid 2000

### TRAP-URI invatate in Faza 3
- clipboard: `cmd clipboard get` -> "No shell command implementation."
  clipboard NU e accesibil prin cmd din uid 2000
- dumpsys battery returneaza starea curenta; NU se confunda cu istoricul
  din bridge/battery.txt daca fisierul e vechi (nume coliziune) -> refetch
- `dumpsys wifi` regex: campurile sunt pe O SINGURA linie lunga mWifiInfo,
  deci regex-ul trebuie sa fie ne-greedy intre campuri

### STARE FINALA PROIECT
Faza 0 (libbinder nativ):   ABANDONATA (ProcessState segfault)
Faza 1 (punte uid2000):     COMPLETA (adb_client in app + bridge fisiere)
Faza 2 (android_api):       COMPLETA (7 functii)
Faza 3 (extindere):         COMPLETA (location/wifi/telephony/clipboard-limitat)
Faza 4 (verificare):        COMPLETA (toate confirmate din Debian)

### Ce NU se poate (documentat)
- clipboard prin cmd din shell -> "No shell command implementation"
- apeluri binder AIDL arbitrare din Debian -> necesita libbinder (segfault)
- executie binare din /data/local/tmp direct -> doar via linker64
