# Agent Android (net.sys32.agent)

## Documentatie completa de dezvoltare

**Versiune:** 1.0
**Platforma:** Android 8+ (minSdk 26), target API 36 (Android 16)
**Autor:** dezvoltare asistata (sesiuni multiple)
**Ultima actualizare:** septembrie 2026

---

## CUPRINS

1. Prezentare generala
2. Arhitectura
3. Componentele aplicatiei (3.1-3.6: UI, Bridge, Reflection, Agent, AgentService, Accessibility)
4. Cum functioneaza Python pe Android
5. Pasii dezvoltarii de la 0 (etape 1-20)
6. Probleme intalnite si solutii
7. Structura de fisiere a aplicatiei
8. Structura pe dispozitiv (in rulare)
9. Comenzi disponibile
10. Tool-uri si accesul la sistem
11. Limitari cunoscute
12. Lecții invatate
13. Starea finala si pasii urmatori

---

## 1. PREZENTARE GENERALA

Applicatia **net.sys32.agent** este un agent autonom care ruleaza pe Android.
Vorbeste cu modelul DeepSeek, ia decizii, executa unelte si interactioneaza
cu intregul sistem Android. Interfata este un terminal cu culori ANSI.

Scop: acces cat mai complet la hardware si sistem, intr-un sandbox de aplicatie
normala (fara root), cu memorie persistenta si invatare din experienta.

---

## 2. ARHITECTURA

Trei componente care comunica intre ele:

    [ UI Kotlin ]  --deseneaza terminalul pe ecran
          |
          |  (stdout/stdin prin pipe-uri)
          v
    [ Agent Python ]  --creierul: DeepSeek API, tool-use, memorie
          |
          |  (socket TCP 127.0.0.1:port, o linie JSON/cerere)
          v
    [ Bridge Kotlin ]  --reflection pe Android SDK, acces hardware

Componenta 1 si 3 ruleaza in ACELASI proces Android (aplicatia).
Componenta 2 ruleaza ca PROCES SEPARAT (libpyexec.so agent.py).

---

## 3. COMPONENTELE APLICATIEI

### 3.1 UI (MainActivity.kt)
- TextView monospace cu scroll, culori ANSI (Ansi.kt converteste SGR)
- Paleta One Dark pe fundal #0D1117
- Font DejaVuSansMono livrat in assets (glyph-uri box-drawing continue)
- Input cu EditText: Enter de pe tastatura trimite taskul (TextWatcher,
  fiindca Gboard introduce caracterul \n in text, nu KEYCODE_ENTER)
- Butoane: trimitere (sageata), STOP (patrat rosu, linga trimitere), jos
- Auto-scroll inteligent: ramine sus cind citesti, urmareste cind esti jos
- Buton STOP trimite SIGINT procesului Python (PID luat prin reflexie din
  cimpul "pid", nu metoda - aceasta nu exista pe Android)

### 3.2 Bridge (AndroidBridge.kt)
- Server TCP pe 127.0.0.1, port aleator (ServerSocket(0, 8, 127.0.0.1))
- Portul scris in files/bridge.port si files/home/bridge.port
- Protocol: o linie JSON per cerere, o linie JSON per raspuns
- Shortcut-uri native: sensors, camera, location, battery, clipboard, notify,
  vibrate, tts, volume, wifi, device, apps, intent, settings
- Actiuni native suplimentare: system, storage, processes, network, display,
  audio, telephony, nfc, usb, appinfo

### 3.3 Reflection (Reflection.kt)
- Operatii: call, new, get, set, info, services, objs, free
- Target-uri: svc:NUME, class:FQCN, obj:ID, ctx, app, str:, int:
- Registry de obiecte cu id-uri (o0, o1, ...)
- Map de 298 servicii de sistem (cu fallback inteligent de nume)

### 3.4 Agent (agent.py)
- Bucla principala: citeste task, cheama DeepSeek, executa tool-uri
- Memorie pe termen lung (memory.md) + auto-learn
- Context persistent (context.json) cu compactare automata
- Comenzi slash (a se vedea sectiunea 9)

---

### 3.5 AgentService (foreground service)
Tine procesul Python viu in BACKGROUND, ca agentul sa poata lucra si cind aplicatia
e minimizata (ex. cind umbla prin alte aplicatii).
- notificare persistenta (canal "agent_bg", id 4711) -> procesul nu mai e candidat la kill
- PARTIAL_WAKE_LOCK -> CPU-ul nu adoarme in timpul unui task lung
- START_STICKY + onTaskRemoved -> serviciul revine daca sistemul il omoara (sau la swipe din recents)
- onDestroy-ul MainActivity NU mai omoara Python/bridge-ul cit timp serviciul ruleaza
- manifest: foregroundServiceType="specialUse", stopWithTask="false"
- merge si cu ECRANUL STINS/BLOCAT: task-urile HEADLESS (bridge, senzori, fisiere, retea)
  functioneaza 100% chiar in Doze, atita vreme cit aplicatia e in whitelist-ul de baterie
- pentru task-uri care ating UI-ul altor aplicatii (specific Android), agentul poate
  chema `ui wake` (wake lock ACQUIRE_CAUSES_WAKEUP + setShowWhenLocked/setTurnScreenOn pe
  activity): ecranul se aprinde si activitatea se arata peste lock screen
- `ui sleep` elibereaza wake lock-ul de ecran (procesul rămine viu, headless)
- `ui service` returneaza starea: foreground / accessibility / ignore_battery_opt

### 3.6 AgentAccessibilityService (vedere + control UI)
Da agentului VEDERE si CONTROL asupra oricarei alte aplicatii, FARA root.
Android interzice injectarea de input aplicatiilor normale (INJECT_EVENTS e o
permisiune de SEMNATURA - doar system apps o pot avea). AccessibilityService e
calea oficiala si singura viabila pentru un app normal.
Capabilitati expuse prin bridge (tool `ui`):
- read       - citeste arborele UI al oricarei aplicatii. COMPACT (default): lista text
               lizibila, ~10x mai mica decit JSON-ul brut. Format: [n] Cls id=x "text" @[x,y] <flags>
               (E=editabil C=clickabil K=checkable S=scrollabil). params: max, depth, textonly
- find       - CAUTA un nod dupa text/id FARA sa citeasca tot ecranul; intoarce potrivirile
               cu center=[x,y] gata de click. E calea eficienta cind cauti contact/buton/cimp
- settext    - scrie text (ACTION_SET_TEXT) in cimpul cautat / focalizat / primul editabil
- click      - apasa un nod (dupa text/id) sau un punct (x,y)
- tap/swipe  - gesturi reale prin dispatchGesture
- scroll     - scroll pe nod sau swipe pe ecran
- back/home/recents/notifications/quicksettings/screenshot/lockscreen - performGlobalAction
- openapp    - deschide orice aplicatie dupa pachet
- windows    - listeaza ferestrele vizibile

Config: res/xml/accessibility_service_config.xml (canRetrieveWindowContent=true,
canPerformGestures=true, flagReportViewIds, flagRetrieveInteractiveWindows).
Serviciul se activeaza de UTILIZATOR din Settings > Accessibility (vezi sec. 9).

## 4. CUM FUNCTIONEAZA PYTHON PE ANDROID

Aceasta este o parte importanta si usor de inteles gresit.

### 4.1 Android NU are bash si NU are "terminal"
- Shell-ul este **mksh** (MirBSD Korn Shell), la /system/bin/sh
- Utilitarele sunt **toybox** (~150 comenzi: ls, cat, grep, sed, find, tar)
- NU exista bash, grep -P, sau multe optiuni GNU
- NU exista un TTY/terminal de sistem pentru utilizator

### 4.2 Ce am facut de fapt
Am compilat **CPython 3.14.7 pentru Android** ca binar ELF nativ si l-am
rulat ca PROCES SEPARAT, NU "intr-un terminal Android".

- Python-ul este CPython 3.14.7 din sursa oficiala (are suport Android
  oficial in Android/android.py)
- Compilat pentru doua arhitecturi: arm64-v8a (telefon) si x86_64 (emulator)
- Rezultat: libpython3.14.so + libpyexec.so (interpreterul)

### 4.3 Cum porneste aplicatia Python-ul
NU face "sh -c python". Face direct:

    ProcessBuilder("/data/.../libpyexec.so", "agent.py")

Deci binarul este executat direct, fara shell intermediar. Pe API 29+
executabilele nu pot rula din filesDir, deci sint puse in nativeLibraryDir
ca libXXX.so.

### 4.4 Terminalul este construit de noi
Applicatia Kotlin citeste stdout-ul procesului Python linie cu linie, il
converteste cu Ansi.kt in text colorat (Spannable) si il deseneaza intr-un
TextView. NU folosim un terminal de sistem - nu exista unul.

### 4.5 Unde folosim totusi shell-ul
Tool-ul "bash" al agentului ruleaza de fapt "sh -c <comanda>" (mksh).
Merge pentru majoritatea comenzilor, dar fara specific bash.

    SHELL=[('sh','-c') if android else ('bash','-lc')]

### 4.6 De ce dumpsys este blocat
Tool-ul bash al agentului ruleaza sub UID-ul aplicatiei (sandbox SELinux),
nu sub "shell" (uid 2000). De aceea "dumpsys battery" returneaza
"Can't find service: battery". Accesul la sistem se face prin reflection
(svcs expuse public) si prin actiuni native Kotlin.

---

## 5. PASII DEZVOLTARII DE LA 0

### Etapa 1 - Mediul de dezvoltare
- Instalat JDK 21 (Debian trixie nu are openjdk-17)
- Instalat Android SDK in /home/gab/android: platform-tools, cmdline-tools,
  build-tools 35.0.1, Gradle 8.11.1
- Creat env.sh cu JAVA_HOME, ANDROID_HOME, ANDROID_SDK_ROOT, PATH

### Etapa 2 - Compilarea Python pentru Android
- Descoperit suportul Android oficial in CPython 3.14 (Android/android.py)
- Comanda: ./android.py build <target>
- Compilat pentru arm64-linux-android si x86_64-linux-android
- 114 module (36 built-in, 67 shared): _ssl, _hashlib, _sqlite3, zlib,
  _bz2, _lzma, _zstd, _ctypes incluse; lipsesc _tkinter, readline, _curses

### Etapa 3 - Proiectul Kotlin
- Structura Gradle: minSdk 26, targetSdk 36, namespace net.sys32.agent
- Python impachetat ca lib/libpython3.14.so + module in assets/python/libdynload/
- Extrase in files/ la prima rulare, cu sistem de stamp (.assets_vN)

### Etapa 4 - Interfata terminal
- TextView monospace + Ansi.kt (conversie SGR in Spannable)
- Paleta One Dark pe #0D1117
- Font DejaVuSansMono in assets
- Input, butoane, scroll cu auto-follow

### Etapa 5 - Podul Kotlin<->Python
- Server TCP pe 127.0.0.1, port aleator
- Protocol o linie JSON per cerere/raspuns
- Portul scris in doua fisiere (files/ si files/home/)

### Etapa 6 - Accesul la SDK prin reflection
- Reflection.kt: call, new, get, set, info, services, objs, free
- Registry de obiecte cu id-uri

### Etapa 7 - Agentul Python
- Bucla principala, DeepSeek API cu tool-use
- Memorie pe termen lung + auto-learn
- Context persistent cu compactare

### Etapa 8 - Deploy
- Emulator: android-36 google_apis x86_64, -gpu host cu offload NVIDIA
- Telefon real: Samsung SM-A366B prin USB

### Etapa 9 - Repararea accesului (faza majora)
- BUG reflection: flag "keep" implicit false -> obiectele nu primeau id ->
  fixat la true (fara asta, agentul "se invirtea" pierzind obiectele)
- Actiuni native noi: sensors stream, location fresh (fix GPS real),
  location current
- Stabilitate: agentul murea dupa primul task (linia goala oprea bucla) ->
  fixat (linia goala este ignorata, doar /exit si /quit opresc)
- Bridge: portul se pierdea la reconectare -> fixat (re-citire fisier)

### Etapa 10 - Acces complet la sistem
- Manifest: 34 -> 105 permisiuni
- Map servicii de sistem: 72 -> 298
- 11 tool-uri native noi: system, storage, processes, network, display,
  audio, telephony, nfc, usb, appinfo, sensors all
- battery full: toate datele bateriei accesibile unui app normal

### Etapa 11 - Bug-uri critice de permisiuni
- ACCESS_BACKGROUND_LOCATION in cererea principala -> TOATE dialogurile se
  inchideau instant (Android 11+ interzice combinarea) -> fixat: cerut separat
- Manifest cache-uit de Gradle -> APK avea doar 30 permisiuni din 105 ->
  rezolvat cu ./gradlew clean

### Etapa 12 - Rafinarea UI
- Scroll: ramine sus cind citesti in timpul generarii (diagnosticat cu logcat)
- Buton STOP functional (SIGINT, PID prin cimp)
- Enter de pe Gboard trimite taskul (TextWatcher pentru \n)
- Banner curat in engleza, AGENT rosu, mesaj pe linia "You >"
- Footer simplificat

### Etapa 13 - Workspace vizibil
- Mutat in /sdcard/Download/Agent/ (memorie + context)
- workspace/ (tot ce genereaza agentul)
- Comanda /where - arata unde e totul
- Marcaj media pentru indexare in My Files

### Etapa 14 - Identitate vizuala
- Iconita: prompt de terminal (sageata albastra + linie alba) pe fundal
  inchis, generata din SVG in toate densitatile

---

### Etapa 15 - Primitive generale de reflection (agent suprem)
Problema: reflection-ul pur nu putea implementa interfețe Java (ScanCallback, listeners),
nu putea pasa Context ca argument si nu putea astepta callbacks asincrone. Adaugat 4 primitive
generale in Reflection.kt + Primitives.kt:
- `op=proxy` - proxy de interfețe Java (java.lang.reflect.Proxy); fiecare apel devine un eveniment
- referințe de obiecte ca argumente: `["ref","ctx"]`, `["ref","obj:o5"]`, `["ref","svc:sensor"]`
- `op=await` / `op=events` / `op=sinks` - evenimente asincrone de la callback-uri
- `op=subclass` - SUBCLASARE LA RUNTIME prin DexMaker (genereaza o clasa reala care
  extinde orice clasa abstracta: ScanCallback, BroadcastReceiver etc.)
Rezultat: scanare BLE reala cu ScanCallback (11 dispozitive detectate), imposibil inainte.

### Etapa 16 - Biblioteci Python (Nivel 1)
Adaugate in assets/python/Lib/site-packages/ ~13 pachete PURE Python (fara cod nativ):
requests, urllib3, certifi, charset-normalizer, idna, beautifulsoup4, soupsieve,
python-dateutil, six, pyyaml, toml, packaging, typing-extensions (~3.1 MB).
Toate testate pe device (requests -> HTTP 200 real, bs4 -> parse HTML, yaml/toml -> round-trip).
NU exista pip; agentul stie exact ce are si ca nu poate instala altceva.

### Etapa 17 - Bug-uri de ambalare stdlib pe Android
- AAPT2 IGNORA folderele care incep cu `_` in assets (fisierele .py merg, folderele NU).
  zipfile/_path/ nu ajungea in APK -> livrat ca zipfile/_path.py (fisier simplu, glob inline).
- six.py (fisier la radacina wheel-ului) era sarit de scriptul de copiere (copia doar foldere).
- pyhome nu se actualiza (stdlib copiat o singura data) -> se sterge la re-extragere.

### Etapa 18 - Sistem de memorie si auto-learn
- memory.md pe termen lung, incarcat o singura data la start (snapshot in system prompt)
- auto-learn: la finalul unui task (>=5 pasi SAU eroare) extrage lectii reutilizabile
- filtru de VALOARE (_lesson_value): scor 0-10; taie banalitatile si observatiile fara consecinta
- filtru de mediu: respinge lectiile de developer/desktop (nu-s despre acest telefon)
- extractie multipla: pana la N lectii valide per task (nu doar una)
- linter (mem_lint): valideaza formatul, duplicatul, lungimea

### Etapa 19 - UI: streaming, scroll, comenzi
- comanda /run <script.py> [args]: ruleaza orice script Python din workspace, direct din chat,
  cu output STREAMING in timp real (linie cu linie) + salvare automata la output lung
- scroll: derulezi sus -> ramai sus (nu te mai arunca jos la generare); revii jos -> auto-follow
- buton STOP (SIGINT) in randul de input, langa send
- Enter de pe tastatura virtuala (Gboard) trimite taskul (TextWatcher pe newline)
- caseta de scris: creste corect pe mai multe randuri, nu mai taie ultima linie
- banner curat, aliniat la stanga; cuvantul AGENT rosu
- agentul raspunde in LIMBA operatorului (nu fortat romana)
- INTERZIS tabele pe ecran mic: prompt dur + conversie automata tabel->lista la afisare

### Etapa 20 - Workspace vizibil si git
- workspace mutat in /sdcard/Download/Agent/ (memorie + context) si workspace/ (tot ce genereaza)
- comanda /where arata unde e totul
- iconita profesionala (prompt de terminal, SVG -> toate densitatile)
- repo git + push pe GitHub (SSH)

### Etapa 21 - Background: agentul lucreaza la minimizare (foreground service)
Problema: cind aplicatia era minimizata, Android suspenda/omoara procesul Python, deci
agentul nu mai putea continua un task (critic cind trebuie sa umble prin alte aplicatii).
Solutie: AgentService (foreground) + PARTIAL_WAKE_LOCK + START_STICKY + onTaskRemoved.
Verificat pe Samsung SM-A366B: proces viu >25s in background, bridge 16/16 tool-uri,
supravietuieste la am send-trim-memory RUNNING_CRITICAL, repornire curata dupa force-stop.

### Etapa 22 - Fix senzori (registerListener fara Handler)
Problema: TOTI senzorii returnau "no data from accelerometer" desi existau.
Cauza: registerListener era apelat din thread-ul de socket, care NU are Looper;
fara un Handler explicit, onSensorChanged nu se declanseaza NICIODATA.
Fix: sensorHandler = Handler(Looper.getMainLooper()) ca al 4-lea argument la toate
cele 3 apeluri (read/stream/collect). Verificat: 8/8 senzori live (light 287 lx,
proximity 5cm, gravity 9.80 m/s^2, accelerometru, magnetic, giroscop, pedometru).

### Etapa 23 - Tastare si control in ALTE aplicatii (AccessibilityService)
Problema: agentul nu putea tasta/apasa butoane in alte aplicatii. Reflection
injectInputEvent -> SecurityException INJECT_EVENTS (permisiune de semnatura).
Shell `input` din app (untrusted_app) -> "Failed transaction". Ambele imposibile fara root.
Solutie: AgentAccessibilityService (vedere + control UI, fara root).
Verificat end-to-end pe telefon: am deschis Settings, am apasat "Search settings",
am TASTAT "bluetooth" in cimpul de cautare si am citit rezultatele ("Results (27)").


### Etapa 24 - Ecran stins / telefon blocat: headless mereu, UI la nevoie
Problema: cu ecranul stins si telefonul blocat, agentul parea ca "se opreste".
Diagnostic (reprodus pe Samsung A36): procesul NU murea si wake lock-ul era activ;
ce nu raspundea era tunelul `adb forward` (suspendat de Doze) - o limitare adb, nu a app-ului.
Testat direct pe telefon (adb shell nc): bridge-ul raspundea perfect cu ecranul blocat.
Solutii implementate:
- PARTIAL_WAKE_LOCK (CPU treaz) - deja existent, confirmat activ in Doze
- `ui wake` / `ui sleep`: wake lock suplimentar ACQUIRE_CAUSES_WAKEUP + setShowWhenLocked(true)
  + setTurnScreenOn(true) + FLAG_KEEP_SCREEN_ON pe perioada unui task cu UI
- cerere automata REQUEST_IGNORE_BATTERY_OPTIMIZATIONS la prima pornire (fara ea Samsung
  suspenda agresiv procesul); se poate pune si manual: Settings > Battery > Unrestricted
- `ui service`: expune starea (foreground / accessibility / ignore_battery_opt)
Verificat: cu ecranul STINS si BLOCAT (mWakefulness=Dozing, AOD aprins):
  - 6/6 + 8/8 + 10/10 task-uri HEADLESS reusite (baterie/device/senzori)
  - task UI reusit: `ui wake` -> `ui openapp com.android.settings` -> `ui read` (20 noduri)
  - procesul rămas viu dupa toate (PID stabil)


### Etapa 25 - read compact + find (ecranul devine lizibil pentru model)
Problema (reprodusa cu un task real: "deschide WhatsApp, cauta 'gab', trimite 'salut'"):
`ui read` returna JSON brut cu TOATE metadatele pe fiecare nod
(`"enabled":true,"bounds":[0,0,1080,2340],"pkg":"com.whatsapp"` etc) -> ~120 caractere
de zgomot pentru 3 caractere de text util. Un ecran WhatsApp = 8500+ caractere, iar
raspunsul era TRUNCHIAT la 8000 -> informatia cautata ("Gab") ajungea la poz. 6375,
la un pas de taiere. Agentul primea zgomot, nu informatie, si a ajuns sa caute
contactul in agenda Android (3 contacte de serviciu) in loc de rezultatele search-ului.
Solutii:
- read COMPACT (default): arborele devine lista text `[n] Cls id=x "text" @[x,y] <flags>`.
  Rezultat masurat: 8581 -> 1949 caractere (~4.5x mai putin); "Gab" vizibil pe linia [8].
- find <text>: cauta direct un nod (text/id/descriere) si intoarce potrivirile cu
  center=[x,y] -> agentul nu mai citeste tot ecranul cind cauta ceva anume.
- trunchiere inteligenta in agent.py: ui read/find primesc 12000 chars (textul e dens),
  iar mesajul de taiere spune explicit sa foloseasca max/depth mici sau `ui find`.
Verificat end-to-end pe Samsung A36 (taskul care esuase inainte):
  WhatsApp -> find "Gab" (13 potriviri) -> tap pe contact -> camp message (id=entry)
  -> settext "salut" -> tap send -> mesaj TRIMIS (confirmat vizual: bubble verde la Gab)


## 6. PROBLEME INTALNITE SI SOLUTII

1. SSL pe Android: URLError b'' la api.deepseek.com
   -> CA construit din /apex/com.android.conscrypt/cacerts + /system/etc/security/cacerts
   -> setat ssl._create_default_https_context si SSL_CERT_FILE

2. Nu exista bash pe Android: FileNotFoundError: 'bash'
   -> folosit sh -c

3. dumpsys blocat de SELinux pentru app
   -> acces prin reflection (servicii expuse public)

4. Proprietati Samsung SEM_BATTERY_* inaccesibile (intorc MIN_VALUE)
   -> datele bateriei luate din sticky broadcast ACTION_BATTERY_CHANGED

5. Capcana open(p,"w").write(open(p).read()) - TRUNCHIAZA fisierul la 0
   -> a golit MainActivity.kt de doua ori
   -> FIX: citeste intii intr-o variabila, apoi scrie

6. Assets nu se re-extrag daca stamp-ul (.assets_vN) are acelasi nume
   -> la orice modificare de assets: incrementeaza versiunea SI reporneste app-ul

7. Gradle foloseste manifest/dex din cache
   -> ./gradlew clean la modificari de manifest

8. Instalare peste APK cu alta semnatura: "signatures do not match"
   -> adb uninstall intii

9. Sensori: getSensorList(0) returneaza lista GOALA -> trebuie getSensorList(-1)

10. Reflection nu poate crea obiecte care implementeaza interfete Java
    (ex. SensorEventListener) -> pentru callback/stream folosim Kotlin

---

## 7. STRUCTURA DE FISIERE A APLICATIEI

    app/net.sys32.agent/
    |-- app/src/main/
    |   |-- AndroidManifest.xml          (105 permisiuni)
    |   |-- java/net/sys32/agent/
    |   |   |-- MainActivity.kt          (UI, pornire Python, input)
    |   |   |-- AndroidBridge.kt         (server TCP, tool-uri native)
    |   |   |-- Reflection.kt            (reflection SDK + primitive: proxy, ref, await, subclass)
    |   |   |-- Primitives.kt            (proxy de interfete, subclasare DexMaker, evenimente)
    |   |   |-- Ansi.kt                  (SGR -> Spannable)
    |   |   |-- Components.kt            (componente UI refolosibile)
    |   |   `-- CameraActivity.kt        (captura foto)
    |   |-- assets/python/
    |   |   |-- agent.py                 (creierul)
    |   |   |-- android_bridge.py        (client bridge)
    |   |   |-- memory.md                (schelet de memorie initiala)
    |   |   |-- libdynload/              (module .so pe arhitecturi)
    |   |   `-- Lib/                     (biblioteca standard Python)
    |   |       |-- zipfile/_path.py     (livrat ca fisier, folderul _path/ e ignorat de AAPT)
    |   |       `-- site-packages/       (13 pachete pure: requests, bs4, yaml, toml, ...)
    |   |-- res/mipmap-*/                (iconite toate densitatile)
    |   `-- lib/{arm64-v8a,x86_64}/      (libpython, libssl, libcrypto)
    `-- build.gradle.kts

---

## 8. STRUCTURA PE DISPOZITIV (IN RULARE)

    /sdcard/Download/Agent/              <-- VIZIBIL in file manager
    |-- memory.md                        (memoria agentului)
    |-- context.json                     (istoricul conversatiei)
    `-- workspace/                       (tot ce genereaza agentul)
        |-- .agent_folder.png            (marker pentru indexare)
        |-- logs/                        (output-uri complete de tool)
        `-- archive/                     (snapshot-uri context)

    /data/data/net.sys32.agent/files/    <-- sandbox privat
    |-- bridge.port                      (portul serverului)
    |-- home/bridge.port
    |-- pyhome/                          (PYTHONHOME)
    `-- python/                          (Python extras din assets)

Nota: tot ce face agentul ajunge in /sdcard/Download/Agent/ (vizibil in
My Files -> Internal storage -> Download -> Agent, sau prin USB/MTP).
La dezinstalare, aceste fisiere SUPRAVIETUIESC.

---

## 9. COMENZI DISPONIBILE

    /help, /?           lista de comenzi
    /learn              actualizeaza memoria acum (invatare manuala)
    /auto-learn on|off  invata SINGUR dupa fiecare task
    /mem                statistici memorie (marime, bullets, densitate)
    /ctx                context + arhive/log-uri pe disc
    /compact            comprima contextul acum
    /verbose            comuta afisarea completa a codului/output-ului
    /nospin             fara linia live (scrollback curat)
    /where              arata unde traieste totul
    /run <script.py> [args]   ruleaza un script Python din workspace, cu output STREAMING
    /reset              sterge istoricul conversatiei
    /exit, /quit        iese

---

### Activare AccessibilityService (o singura data, de catre utilizator)

Ca agentul sa poata citi ecranul / tasta / apasa in ALTE aplicatii, serviciul de
accessibility trebuie activat manual (Android cere asta din motive de securitate):

1. **Settings > Accessibility > Installed apps / Downloaded apps**
   (pe Samsung: Settings > Accessibility > Installed applications)
2. Gaseste **"Agent (control ecran)"** si porneste comutatorul
3. Apare un dialog de avertizare cu datele pe care le poate accesa -> **Allow / OK**
4. Butonul devine verde (ON) -> serviciul e activ

Verificare ca e activ (din chat, tool `android`):
    android(tool="ui", action="status")   ->  {"ok":true,"enabled":true}

Verificare rapida cu adb (util dupa reinstalare, se pierde la update):
    adb shell settings put secure enabled_accessibility_services \
        net.sys32.agent/net.sys32.agent.AgentAccessibilityService
    adb shell settings put secure accessibility_enabled 1

Nota: la fiecare REINSTALARE a APK, Android dezactiveaza serviciul -> re-activeaza-l
din Settings (sau cu cele 2 comenzi adb de mai sus).

### Baterie: exclude agentul de la optimizare (pentru rulare pe ecran stins)

Ca agentul sa ramina VIU cu ecranul stins/blocat (Doze), exclude-l de la optimizarea bateriei:

1. Aplicatia cere asta automat o data, la prima pornire (dialog "Allow Agent to run in background?")
2. Sau manual: **Settings > Battery > Background usage limits > Never sleeping apps / Unrestricted**
   (pe Samsung: Settings > Battery > Background usage limits -> adauga `Agent`)
3. Verificare din chat: `android(tool="ui", action="service")` -> `ignore_battery_opt:true`

Fara asta, Samsung poate suspenda procesul dupa citeva minute de ecran stins.
Nota: task-urile care nu au nevoie de UI (bridge, senzori, fisiere, retea) merg si asa,
dar cu whitelist-ul e garantat ca procesul nu e omorit.

### Ce functioneaza cu ecranul STINS si telefonul BLOCAT

| Tip task | Functioneaza? |
|---|---|
| Bridge, senzori, baterie, wifi, fisiere, retea (HEADLESS) | ✅ DA (mereu) |
| Agentul lucreaza singur pe un task dat din interfata | ✅ DA |
| UI in alte aplicatii (tastare/click) | ✅ DA, daca agentul cheama `ui wake` intii |
| Talk cu utilizatorul prin interfata aplicatiei | ⚠️ ecran stins (normal) |

## 10. TOOL-URI SI ACCESUL LA SISTEM

### Tool-uri principale
- python   - executa cod Python (stdlib complet + 13 pachete pre-instalate)
- bash     - executa comenzi shell (sh -c pe Android; NU e bash)
- smart    - router automat (alege python vs bash)
- look     - analizeaza o imagine cu vision
- android  - acces la SDK Android (reflection + shortcut-uri native + tool `ui` pentru
             citirea ecranului, tastare, click, gesturi in ORICE aplicatie - vezi 3.6)
- read     - citeste un FISIER de la un offset, cu limita (paginare) - pentru fisiere mari/log-uri

### Actiuni ale tool-ului android
ui (read/settext/click/tap/swipe/scroll/back/home/recents/notifications/openapp/windows),
sensors (list/read/stream/all), camera, location (last/current/fresh),
battery (get/full), clipboard, notify, vibrate, tts, volume, wifi, device,
apps, intent, settings, system (get/full), storage, processes, network,
display, audio, telephony, nfc, usb, appinfo, eval (reflection)

### Operatii reflection (Reflection.kt)
call, new, get, set, info, services, objs, free
+ PRIMITIVE GENERALE (agent suprem):
  - proxy    - creeaza o instanta a oricarei INTERFETE Java (fiecare apel = eveniment)
  - subclass - creeaza o SUBCLASA LA RUNTIME a oricarei clase abstracte (DexMaker)
  - await    - asteapta un eveniment (callback) de la un proxy/subclasa
  - events   - toate evenimentele capturate
  - sinks    - proxy-urile/subclasele active

### Referinte de obiecte ca argumente
Orice argument poate fi ["ref", <valoare>]:
  ["ref","ctx"]         - Context-ul aplicatiei
  ["ref","app"]         - Application context
  ["ref","obj:o5"]      - obiect pastrat dintr-un apel anterior
  ["ref","svc:sensor"]  - un serviciu de sistem
Merge la op=call SI la op=new (constructori).

### Biblioteci Python pre-instalate (pure)
requests, urllib3, certifi, charset-normalizer, idna, beautifulsoup4, soupsieve,
python-dateutil, six, pyyaml, toml, packaging, typing-extensions.
NU exista pip; NU se pot instala altele. numpy/pandas/cryptography NU sunt disponibile.

---

## 11. LIMITARI CUNOSCUTE

Un app normal (fara root) NU poate:
- accesa dumpsys pentru servicii de sistem (Permission Denial)
- citi /sys/class/power_supply/* (Permission denied)
- folosi proprietatile Samsung SEM_BATTERY_* (intorc MIN_VALUE)
- accesa /data/data/<alt pachet>/, /system, kernel

Ce POATE (cu permisiunile din manifest):
- toate serviciile de sistem expuse public (156 din 301)
- toate senzoarele, camera, locatia, microfonul
- reflection pe orice clasa publica a SDK-ului
- storage extern complet, contacte, SMS, telefon, calendar

Ce NU se poate rula din exterior:
- Python-ul agentului NU poate fi rulat direct din adb/Termux: files/python/
  are permisiuni restrinse (drwx------) si run-as nu poate intra in subdirectoare.
  De aceea exista comanda /run (ruleaza scriptul in sandbox-ul aplicatiei).

Ce NU se poate instala:
- NU exista pip/ensurepip -> zero pachete noi. Doar cele 13 pre-incluse in APK.
- numpy/pandas/cryptography/scipy necesita cod C compilat pentru arm64 -> excluse.
  Alternativa: array + statistics (pentru calcule), sqlite3 (baze de date).

Capcane AAPT2 la ambalare assets:
- folderele care incep cu "_" sunt IGNORATE (fisierele .py merg, folderele NU).
  Ex: zipfile/_path/ a trebuit livrat ca zipfile/_path.py.
- fisierele simple .py la radacina unui wheel (ex. six.py) trebuie copiate explicit.

Aceste limitari NU se rezolva din permisiuni - doar cu root.

---

## 12. LECTII INVATATE

1. Masoara, nu presupune. Logcat a rezolvat ce 3 incercari oarbe n-au reusit.
2. Operatorul are mereu dreptate. Cind a zis "tot sare jos" si "sunt 5
   fisiere", a avut dreptate de fiecare data.
3. Citeste propria memorie. Capcana open(w).write(open.read()) era notata
   si tot am calcat pe ea.
4. Portabilitate prin API, nu hardcodare. Caile din Environment, nu constante.
5. Fallback mereu. Daca storage-ul extern nu e scriibil, cade in sandbox.
6. Reflexia nu ajunge pentru callback-uri. Am pierdut 3 sesiuni pe BLE pina am
   adaugat primitivele generale (proxy + subclass/DexMaker). Lectia: nu "muri in
   gura" (retete), ci UNELTE GENERALE pe masa - agentul decide singur cum le foloseste.
7. Documenteaza API-ul, nu comportamentul. Agentul a ghicit 9 sintaxe greșite de
   referinta pentru ca nu erau in ghid. Un tool cu sintaxa nedocumentata e inutilizabil.
8. Verifica ce CITESTE modelul, nu doar ce ii scrii. auto-learn raspundea "NO" pentru
   ca primea doar promptul, fara istoricul taskului (ask(list(M)+[prompt]) lipsea).
9. Cache-urile de build mint. Gradle a servit un manifest vechi (30/105 permisiuni)
   si un APK cu _path/ lipsa; doar ./gradlew clean a rezolvat.
10. AAPT2 ignora folderele cu "_". Fisierele .py merg, folderele NU -> livrate ca .py.

---

## 13. STAREA FINALA SI PASII URMATORI

### Stare finala
- APK ~34 MB (debug, neprotejat, arm64 + x86_64)
- Kotlin + CPython 3.14 compilat
- 6 tool-uri: python, bash, smart, look, android, read
- 4 primitive reflection: proxy, referinte de obiecte, await/events, subclass (DexMaker)
- 25+ actiuni native (sensors, camera, location, battery, system, storage, network, display,
  audio, telephony, nfc, usb, appinfo, processes, ...)
- tool `ui` (AccessibilityService): citirea ecranului, TASTARE, CLICK, gesturi, scroll,
  navigare, deschidere app-uri - in ORICE alta aplicatie, fara root
- 13 biblioteci Python pre-instalate (pure): requests, bs4, dateutil, yaml, toml, packaging...
- Acces la hardware si sistem (maxim posibil fara root)
- Memorie persistenta cu auto-invatare (filtrata pe relevanta + mediu)
- Workspace vizibil: /sdcard/Download/Agent/ (memorie, context) + workspace/
- Comenzi: /help /learn /mem /ctx /where /run /reset /compact /verbose /nospin /exit
- Interfata terminal in engleza, raspuns in limba operatorului, auto-scroll corect,
  stop generare, fara tabele pe ecran mic
- Iconita profesionala
- Ruleaza in BACKGROUND (foreground service): taskul continua cind app-ul e minimizat
- Merge si cu ECRANUL STINS/BLOCAT: task-uri headless 100%, task-uri UI prin `ui wake`
- Excludere de la optimizarea bateriei (Doze) ceruta automat la prima pornire
- Senzori functionali (fix registerListener + Handler mainLooper)
- Vedere + control asupra altor aplicatii (AccessibilityService, fara root)
- Repo git cu push pe GitHub

### De facut la final (cind codul e stabil)
- R8/ProGuard pe build release (reduce + obfuscare Kotlin)
  Nota: agent.py ramine citibil (Python in assets) - pentru protectia lui
  e nevoie de criptare assets sau PyArmor
- Reducere dimensiune: split ABI (arm64-only ~18MB), scoatere _testcapi
- Eventual: descoperire SD card extern

---

## ANEXA A - PALETA DE CULORI

    Fundal:          #0D1117
    Text principal:  #ABB2BF
    Accent (albastru):#61AFEF
    AGENT (titlu):   rosu 38;5;203
    You >:           albastru 38;5;110
    TASK (chenar):   verde
    Comenzi:         ...(vezi agent.py, secțiunea de culori)

---

## ANEXA B - COMPILAREA

    # mediu
    source env.sh

    # build APK debug
    cd app/net.sys32.agent
    ./gradlew assembleDebug       # sau ./gradlew clean assembleDebug

    # instalare pe telefon
    adb install -r app/build/outputs/apk/debug/app-debug.apk

    # daca semnatura difera:
    adb uninstall net.sys32.agent

    # Python pentru Android (o singura data)
    cd build/Python-3.14.7
    ./android.py build aarch64-linux-android
    ./android.py build x86_64-linux-android

---

Sfirsitul documentului.
