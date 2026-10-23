# PLAN: Acces deplin la Android din Debian (egal cu aplicatia)

Document de lucru. Ultima actualizare: cercetare preliminara INCHIATA, plan scris.

## Intrebarea

Debian (uid 2000 / shell:s0) are azi puteri de ADMINISTRARE mai mari decat
aplicatia (pm install/grant, input, settings, screencap, dumpsys), dar NU poate:
  - citi datele private ale aplicatiilor
  - apela direct API-uri Android (SensorManager, CameraManager, orice getSystemService)
  - rula cod Java/Android propriu cu acces la framework

Aplicatia poate toate cele de mai sus (reflection + SDK), dar e sandboxed.

Tinta: Debian capabil de AMBELE categorii.

## Ce am masurat ACUM (nu presupuneri)

- `app_process64` exista: /system/bin/app_process64 (51760 B, root:shell, 755)
- `dalvikvm` exista si raspunde la -help
- `/system/framework/framework.jar` exista; 206 fisiere jar in /system/framework
- `/apex/com.android.art/bin/dex2oat64` exista
- uid 2000: CapEff = 0, CapBnd = 0x8000c0, SELinux Enforcing u:r:shell:s0
- `su` NU exista pe device
- `/data/data/com.android.settings` -> Permission denied
- `/data/app` -> Permission denied
- `run-as com.android.settings` -> refuzat
- `setsid true` -> rc=0 (procese noi OK)

### BLOCAJUL MASURAT (decisiv)
```
ANDROID_DATA=/data/local/tmp/ad ANDROID_ROOT=/system app_process /system/bin
  -> "Error changing dalvik-cache ownership : Operation not permitted"
  -> "Error creating cache dir .../dalvik-cache/arm64 : No such file or directory"
     (se rezolva cu mkdir -p, dar apoi revine ownership)
```
Cauza: ART face chown pe dalvik-cache la pornire; chown cere CAP_CHOWN, iar
CapEff al uid 2000 = 0. Deci app_process NU poate porni din shell.

## Cele 4 cai posibile (evaluate)

### Calea 1 - Binder AIDL complet din Debian (fara Java)
Extind `debian_binder.c` cu accesorii de parcel (string16, strongBinder, fd,
array, structuri nested) ca sa poata apela orice metoda AIDL.
- CE DA: apeluri directe la orice serviciu binder, din procesul Debian, fara
  Java, fara chown, fara app_process. Exact ce face reflection-ul aplicatiei.
- CE NU DA: acces la date private ale altor pachete (SELinux shell:s0 nu se
  schimba) si nici la serviciile care cer permisiuni de app.
- RISC: MEDIU. Cod propriu, dar parsare manuala per interfata.
- EFORT: mare (implementare + cate un marshaller per AIDL folosit).

### Calea 2 - Helper Java compilat, lansat de aplicatie (RECOMANDATA)
O aplicatie-serviciu (sau extinderea celei existente) care expune un API TCP/IPC
catre Debian. Debian trimite cereri, helper-ul ruleaza in procesul APLICATIEI
(uid 10426, unde totul functioneaza: reflection, SDK, filesDir, permisiuni).
- CE DA: TOT ce poate aplicatia azi - senzori live, camera, orice getSystemService,
  reflexie completa - fara sa lupte cu SELinux sau ART.
- CE NU DA: nu e "Debian ruleaza cod Android", dar functional e echivalent.
- RISC: MIC. Tehnologia exista deja (`android_bridge.py` + AndroidBridge.kt,
  port TCP in bridge.port) - trebuie doar extinsa.
- EFORT: mic-mediu. Extinderea unui bridge care deja merge.

### Calea 3 - app_process cu dalvik-cache pre-creat
Incercare de a ocoli chown: cache pre-generat, ANDROID_DATA pe o partitie
permisa, sau `dalvikvm` in loc de app_process.
- CE DA: ar permite cod Java propriu in uid 2000.
- CE NU DA: sanse mici; chown-ul e hardcodat in ART la pornire.
- RISC: MARE (efort necunoscut, probabil imposibil fara root).
- EFORT: necunoscut. DE VERIFICAT ULTIMA, dupa ce 1+2 sunt gata.

### Calea 4 - Root
Nu exista `su`, device-ul e `user` build (ro.build.type=user, ro.secure=1).
- DEAD pe acest device fara deblocare bootloader + Magisk.

## RECOMANDARE

**Calea 2 ca baza + Calea 1 ca armă secundară.**

Calea 2 da functionalitatea completa imediat, cu risc mic, refolosind bridge-ul
existent. Calea 1 da independenta (apeluri binder fara app) pentru serviciile
la care shell-ul are deja acces - util cand aplicatia nu ruleaza.

Calea 3 se incearca doar dupa, ca bonus.

## Faze

### Faza 0 - inventar bridge existent (30 min)
- [ ] citeste `android_bridge.py` + `AndroidBridge.kt`: ce comenzi suporta azi
- [ ] verifica portul si protocolul (JSON peste TCP loopback?)
- [ ] testeaza din Debian: o comanda prin bridge
- IESIRE: stiu exact ce extind, nu ghicesc.

### Faza 1 - extinde bridge-ul cu API generic (2-3 h)
- [ ] comanda `eval`: primeste o expresie de reflexie, o executa in app, intoarce JSON
      (exact ce face tool-ul `android` acum)
- [ ] comanda `sensors_stream`: inregistreaza listener, trimite esantioane N secunde
- [ ] comanda `system_service`: getSystemService + apel metoda
- [ ] whitelist de clase/metode (sa nu fie remote code execution orb)
- IESIRE: din Debian pot face orice apel SDK, ca tool-ul android.

### Faza 2 - client Python in Debian (1 h)
- [ ] `android_full.py` in assets/python: client pentru bridge
- [ ] API: `eval(expr)`, `sensors(type, sec)`, `service(name, method, args)`
- [ ] fallback pe calea de fisiere daca bridge-ul nu raspunde
- IESIRE: Debian are API curat, fara sa stie de TCP.

### Faza 3 - parcel complet in debian_binder.c (optional, 3-4 h)
- [ ] writeString16/readString16, writeStrongBinder, writeFileDescriptor
- [ ] reader recursiv pentru array/struct
- [ ] teste pe 5 servicii: sensorservice, package, activity, display, battery
- IESIRE: apeluri binder directe, fara app, pentru serviciile permise de SELinux.

### Faza 4 - verificare finala
- [ ] din Debian: citire senzori live (nu snapshot), apel getSystemService,
      lista pachetelor, captura ecran, tot ce face aplicatia azi
- [ ] comparatie punct cu punct cu tool-ul `android`
- [ ] documenteaza ce ramane imposibil (date private ale altor pachete)

## CE VA RAMANE IMPOSIBIL (oricare cale)

- citirea `/data/data/<alta.aplicatie>` - SELinux shell:s0 vs app_data_file
- accesul la datele private ale aplicatiilor fara root
- modificarea partitiilor de sistem
- capabilitati de kernel (CapEff ramane 0)

Astea nu sunt bug-uri de implementare: sunt granite de securitate Android.

## Jurnal

- Cercetare preliminara: app_process blocat pe chown dalvik-cache (CapEff=0).
  Bridge-ul existent (android_bridge.py + AndroidBridge.kt) pare calea cea mai
  ieftina si mai sigura. De confirmat in Faza 0.
