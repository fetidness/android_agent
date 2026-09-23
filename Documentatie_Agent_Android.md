# Agent Android (net.sys32.agent)

## ⚡ START RAPID — CITESTE ASTA PRIMUL

**Daca esti un agent proaspat resetat (memorie goala) si citesti asta, iata esenta:**

### Ce esti
Esti un **agent autonom Android** (`net.sys32.agent`) care ruleaza PE telefon
(Samsung SM-A366B, Android 16), compilat de la zero cu:
- **Python 3.14.7** compilat pentru ARM64 (in APK, ca `libpyexec.so`)
- **Kotlin** pentru UI + bridge + accessibility
- **DeepSeek API** pentru creier

### Ce poti face (8 tool-uri)

| Tool | Ce face | Uid |
|------|---------|-----|
| `android` | bridge Kotlin: senzori, camera, reflection SDK, sub-toolui `ui` | 10362 (app) |
| `ui` | VEDE + CONTROLEAZA alte app-uri (read/find/click/settext/tap) | 10362 |
| **`adbsh`** | **SUPER-PUTERI: shell ca uid=2000 (pm grant, dumpsys, settings, input, screencap)** | **2000 (shell!)** |
| `python` | stdlib + pachete pure-Python | 10362 |
| `bash` | shell in sandbox-ul app | 10362 |
| `smart` | auto-router python/bash | 10362 |
| `read` | citeste fisiere mari (paginat) | 10362 |
| `look` | analiza imagini (vision) | — |

### REGULA DE AURENTRU ALEGEREA TOOL-URILOR
1. **Ecran** (citire/tap/text) → `android ui` (nativ, instant, 0 auth)
2. **Senzori/camera/baterie** → `android` (nativ, instant)
3. **Reflection SDK** → `android eval`
4. **Fisiere/imagini** → `python`, `bash`, `read`, `look`
5. **Super-puteri** (uid=2000) → `adbsh` **DOAR** cand app-ul NU poate:
   permisiuni (`pm grant`), `settings put`, `dumpsys`, `input` fara accessibility,
   `run-as` alte app-uri, `screencap`, `logcat`

> **NU folosi `adbsh` pentru ce face `android`/`python`** — e 10x mai lent si poate rate-limita.

### Unde sunt fisierele (pe device)
```
/data/data/net.sys32.agent/files/
  python/          agent.py, adb_client.py, adb_setup.py, android_bridge.py, Lib/, libdynload/
  adbkey           cheia RSA privata (auto-generata)
  adbkey.pub       cheia publica (format ADB)
  tls.crt/key      certificat X.509
  libs/            libcrypto, libssl, pairing_auth, pairing_connection (din /apex)
  home/, pyhome/   HOME + PYTHONHOME
  libdir.txt       calea catre libpyexec.so (SE SCHIMBA la reinstalare!)
  bridge.port      portul bridge-ului Kotlin
/sdcard/Download/Agent/
  adbkey, adbkey.pub   ★ CHEIA PERSISTENTA (supravietuieste reinstalarilor)
  context.json     istoricul conversatiei
  memory.md        memoria pe termen lung (lectiile)
  workspace/       fisierele de lucru
```

### Cum pornesti Python-ul manual (pe device, prin adb)
```bash
LIBDIR=$(dumpsys package net.sys32.agent | grep codePath | sed 's/.*codePath=//')/lib/arm64
run-as net.sys32.agent sh -c "cd /data/data/net.sys32.agent/files/python && \
  HOME=/data/data/net.sys32.agent/files/home \
  PYTHONHOME=/data/data/net.sys32.agent/files/pyhome \
  LD_LIBRARY_PATH=/data/data/net.sys32.agent/files/libs:$LIBDIR \
  $LIBDIR/libpyexec.so SCRIPT.py"
```

### Ce NU se poate (limite reale Android — NU incerca degeaba)
1. **`adb tcpip 5555`** — app-ul NU poate rula asta (necesita sistem/root).
   Se face O DATA de pe laptop dupa restart telefon.
2. **Pairing WIRELESS (SPAKE2+TLS)** — NU functioneaza din app:
   Python `ssl` nu expune `export_keying_material` → mismatch de chei SPAKE2.
   → wireless ADB real merge DOAR cu client extern (PC).
3. **Citirea `/data/misc/adb/`** — permission denied (doar root).

### Starea actuala (functionala)
- ✅ `adbsh` → uid=2000 (cheia auto-generata + persistenta in /sdcard)
- ✅ Auto-setup la prima pornire (cheie + cert + libs)
- ✅ Alegere inteligenta a tool-urilor (testat live)
- ✅ Auto-detectie port ADB (5555, 55555 sau orice port setat)
- ✅ Setup o singura data (`.setup_done`; lansarile ulterioare = pornire directa)

### AUTONOMIE: CE E IN APK vs. CE E MANUAL

**IN APK (auto, dupa instalare):**
- Python 3.14 ARM64 + libpyexec + stdlib + libdynload
- agent.py, adb_client.py, adb_setup.py, android_bridge.py
- 9 module Kotlin (UI, bridge, accessibility, reflection, service)
- memory.md (default), key.txt (API)
- LA PRIMA PORNIRE se AUTO-GENEREAZA: cheia RSA, certificatul X.509,
  libs-urile crypto/ssl (copiate din /apex)

**MANUAL (nu se poate automatiza — limitari Android):**
| Ce | De ce | Cum | Cand |
|----|-------|-----|------|
| `adb tcpip <port>` | Android interzice app-ului sa deschida portul adbd TCP | de pe calculator: `adb tcpip 5555` | dupa fiecare RESTART telefon |
| "Allow USB debugging" | dialog de sistem Android | pe telefon, o data | la prima conectare / cheie noua |
| Accessibility ON | Android cere activare explicita din Settings | Settings > Accessibility > Agent | dupa fiecare reinstalare APK |

**FARA calculator:** agentul merge cu `android`, `ui`, `python`, `bash`,
`smart`, `read`, `look` (senzori, camera, GPS, ecran, fisiere, HTTP).

**CU calculator** (+ 30s o data): se deblocheaza `adbsh` (uid=2000):
`pm grant`, `settings put`, `dumpsys`, `logcat`, `input`, `screencap`,
`run-as`, `getprop/setprop` — puteri de dezvoltator, fara root.

---

oid (net.sys32.agent)

---



---

### FLOW ZILNIC DE OPERARE (cand telefonul a fost repornit)

    ┌─────────────────────────────────────────────────────────┐
    │ 1. VERIFICA daca adbsh merge                            │
    │    adbsh(cmd="id -u")  → trebuie "2000"                 │
    ├─────────────────────────────────────────────────────────┤
    │ 2. DACA NU merge (timeout/dialog "Allow"):              │
    │    a) pe laptop (USB): adb tcpip 5555                   │
    │    b) pe telefon: apasa "Allow" in dialog (o data)      │
    │    c) reincearca adbsh(cmd="id -u")                     │
    ├─────────────────────────────────────────────────────────┤
    │ 3. DACA merge → continua taskul normal                  │
    │    foloseste tool-urile dupa REGULA DE AUR             │
    └─────────────────────────────────────────────────────────┘

**NU e nevoie de altceva.** Cheia e persistenta, libs se copiaza singure.

### REZOLVAREA PROBLEMELOR FRECVENTE

| Simptom | Cauza | Fix |
|---------|-------|-----|
| `adbsh` timeout | adbd nu asculta pe 5555 | `adb tcpip 5555` (laptop) |
| Dialog "Allow USB debugging" reapare | cheia noua / adbd resetat | apasa Allow (o data) |
| `libpyexec.so: No such file` | libdir.txt vechi | re-citeste cu `dumpsys package ... codePath` |
| `cannot locate symbol...` (libs) | LD_LIBRARY_PATH gresit | pune `files/libs` PRIMUL in LD_LIBRARY_PATH |
| `adbsh error: timed out` dupa multe apeluri | adbd rate-limit | asteapta 10s, sau repornire wireless |
| Libs lipsa dupa update APK | assets re-extrase | app le copiaza automat la pornire (adb_setup.py) |
| `code=127` / `library libX.so not found` | RUNPATH Termux hardcodat | `toolchain.py` face patch automat (patchelf) |
| `ninja: subcommand failed` | ninja Termux e rupt | se inlocuieste automat cu samu |
| `rm: inaccessible or not found` | PATH minimal la meson/ninja | wrapper-ele pun /system/bin in PATH |
| `undefined symbol ctanl/ccoshl` | clang target android24 ascunde C99 | `--target=aarch64-linux-android<API>` |
| `cannot locate symbol _ZTVNSt6__ndk1...` | lipseste libc++ la runtime | `LD_PRELOAD=libc++_shared.so` |
| `undefined symbol` la linkare cu -lm | nu exista libm.so in Termux | `-L/apex/com.android.runtime/lib64/bionic` |
| nume trunchiate in lib-dynload | tar GNU LongName (`typeflag=L`) ignorat | `_untar()` cu suport L/K/PAX (automat) |
| `Compiler cython cannot compile programs` | **toate** `.pc` au prefix Termux | `_fix_sysconfig` le rescrie (automat) |
| `cannot locate symbol _ZTVNSt6__ndk1...` | lipseste `NEEDED libc++_shared` | `_fix_libcxx_needed` + `-lc++_shared` (automat) |
| 63 scripturi "No such file or directory" | shebang Termux mort | `_fix_wrappers_shebang` (automat) |
| `python3`/`pip3` negasite | Termux nu face symlink | `_fix_symlinks` (automat) |
| RUNPATH reapare dupa reinstalare pachet | agentul reinstaleaza .deb-uri | ruleaza `_patch_runpath` din nou (bootstrap) |

### CUM REBUILDUIESTI APLICATIA (daca modifici cod)
```bash
cd /home/gab/Desktop/agent/workspace/app
./build_app.sh          # build + install + start (face tot)
```
**ATENTIE:**
- dupa FIECARE modificare de assets → INCREMENTEAZA `.assets_vNN` in MainActivity.kt
- `adb install -r` DEZACTIVEAZA accessibility → reactiveaza:
  ```bash
  adb shell settings put secure enabled_accessibility_services net.sys32.agent/net.sys32.agent.AgentAccessibilityService
  adb shell settings put secure accessibility_enabled 1
  ```
- libdir.txt se schimba la fiecare reinstalare → reciteste-l

### UNDE E CODUL SURSA (pe laptop, pentru dezvoltare)
```
/home/gab/Desktop/agent/
  agent-original.py                              agentul pentru LINUX (desktop)
  Documentatie_Agent_Android.md                  ACEST document
  memory.md                                      memoria agentului desktop
  workspace/app/net.sys32.agent/
    app/src/main/assets/python/agent.py          agentul ANDROID (Python)
    app/src/main/assets/python/adb_client.py     client ADB (super-puteri)
    app/src/main/assets/python/adb_setup.py      auto-setup
    app/src/main/assets/python/android_bridge.py bridge Python-side
    app/src/main/java/net/sys32/agent/*.kt       Kotlin (MainActivity, Bridge, Accessibility, Reflection)
  build/Python-3.14.7/                           sursele Python + cross-build
```

---

ent Android (net.sys32.agent)

---

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

TEST COMPLET CURAT (memoria + contextul STERSE, WhatsApp pe ecranul principal):
  Task: "deschide whatsapp, cauta userul gab si da i un mesaj de salut" - pornit de la zero.
  Fluxul agentului (37 mesaje, ~1 minut, 100% autonom):
    1. ui wake + apps.launch com.whatsapp
    2. ui read (textonly) -> 49 noduri, lista de chat-uri
    3. ui find "Gab"       -> gasit conversatia in lista (fara sa citeasca tot ecranul)
    4. ui tap pe contact
    5. ui find id=entry    -> gasit campul de mesaj
    6. ui settext "Salut Gab! Ce faci?"
    7. ui find (verificare ca textul e scris)
    8. ui read             -> gasit butonul Send
    9. ui tap send
   10. ui read             -> VERIFICAT ca mesajul a plecat
   11. ui sleep            -> eliberat ecranul
  Rezultat: mesaj "Salut Gab! Ce faci?" trimis la 14:12 (ora reala a telefonului),
  confirmat vizual (bubble verde + bife duble in lista de chat-uri).
  CONCLUZIE: cu read compact + find, taskul care esua inainte (17 citiri de ecran
  pierdute in JSON) acum reuseste din prima, complet autonom, de la memorie zero.


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

### Etapa 26 - Fix memorie: limita 300 -> 500 si taiere la granita de propozitie
Problema (observata in memoria de pe telefon): lectiile erau TRUNCHIATE la mijloc.
Dovada: din 55 de lectii, 5 se opreau fix la 299-300 chars, la mijloc de propozitie
(ex. "...pentru a verifica daca un app e semnat de" - fix-ul era taiat!).
Cauza: in auto_learn_check() linia `if len(_ln) > 300: _ln = _ln[:300].rstrip()`
MUTILA lectia in loc sa o respinga. Necorelare in 3 locuri: promptul cerea "max 300
chars", mem_lint avertiza la 300, dar auto_learn_check TAIA la 300. O lectie
`TRAP: situatie -> cauza -> fix` nu incape in 300 de caractere.
Fix (aplicat in TOATE cele 3 fisiere: desktop agent-original.py, device
files/python/agent.py, assets/python/agent.py):
- limita ridicata la 500 (prompt + mem_lint MAXLINE + trunchiere)
- taiere doar la GRANITA DE PROPOZITIE (` -> `, `. `, `; `, `, `), niciodata la
  mijloc de cuvant; daca nu gaseste separator, pastreaza tot
- scoate separatorul `->` ramas suspendat la coada
Cod nou:
    if len(_ln) > 500:
        _cut = _ln[:500]
        for _sep in (" -> ", ". ", "; ", ", "):
            _p = _cut.rfind(_sep)
            if _p > 200: _cut = _cut[:_p+len(_sep)]; break
        _ln = _cut.rstrip(" ,;-")
        while _ln.endswith("->"): _ln = _ln[:-2].rstrip(" ,;-")
Verificat pe device (Samsung A36), 4 cazuri:
  lectie 296 chars -> INTREAGA (inainte s-ar fi taiat)
  lectie 396 chars -> INTREAGA
  lectie 496 chars -> INTREAGA
  lectie 705 chars -> taiata la 286, la granita de propozitie, fara cuvant rupt
Nota: lectiile VECHI din memorie ramin trunchiate (fix-ul previne doar de acum inainte).
Deploy: assets v51 -> v52, rebuild (BUILD SUCCESSFUL), reinstall, reactivare accessibility.

### Etapa 27 - Fix auto-learning: doar ULTIMUL task (nu toata sesiunea)

**Problema (raportata de operator):** dupa fiecare task, auto-learning-ul
analiza TOATA sesiunea in loc de ultimul task. Rezultatul: agentul isi nota
mereu aceleasi lectii (reformulate), iar sistemul de dedup nu le prindea
(acelasi fapt, cuvinte diferite). Memoria se umplea artificial.

**Cauza:** in `auto_learn_check()`, apelul de decizie trimitea la model
`list(M)` = TOATA lista de mesaje acumulata in sesiune:
```python
_probe = ask(list(M)+[{"role":"user","content":AUTO_LEARN_PROMPT}], tools=[])
```
Desi promptul zicea "Look at the task that just finished above", contextul
trimis continea de fapt zeci de task-uri anterioare -> modelul re-analiza tot.

**Fix (2 schimbari):**

1. `auto_learn_check` primeste acum `task_msgs` (mesajele ULTIMULUI task):
```python
def auto_learn_check(task_steps, had_error, task_msgs=None):
    ...
    _msgs = list(task_msgs) if task_msgs is not None else list(M)
    _probe = ask(_msgs+[{"role":"user","content":AUTO_LEARN_PROMPT}], tools=[])
```
   Iar la apel, din bucla principala, se trimite `M[mark:]` (`mark=len(M)`
   este setat chiar la inceputul taskului, deci `M[mark:]` = doar taskul curent):
```python
auto_learn_check(TASK["steps"], TASK["err"], M[mark:])
```

2. **Limita de lectii per fisier dublata: 8 -> 16** (`mem_lint`):
```python
if len(lessons) > 16:   # era > 8
    out.append((0, "too many lesson lines ... - possible padding"))
```

**Test functional (izolat, cu spy pe ask):** cu o sesiune veche de 40 de
mesaje `STS-VECHI-*` si un task curent de 3 mesaje:
```
mesaje trimise la model: 4
   - TASK-CURENT: deschide whatsapp
   - ok
   - {"ok":true}
   - PROMPT-TEST
CONTINE SESIUNEA VECHE? False   <- FIX CONFIRMAT
CONTINE TASKUL CURENT? True
```

**Efect:** lectiile se scriu acum DOAR din ultimul task -> fara re-analiza
sesiunii, fara duplicare prin reformulare. Aplicat pe Android (device +
assets) si pe desktop (`agent-original.py`).

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


### Etapa 29 - TOOLCHAIN DE COMPILARE NATIV (toolchain.py + tpm.py)

**Ce face:** agentul isi instaleaza SINGUR un toolchain complet de compilare
(clang 21, make, cmake, ninja/samu, git, python+pip, rust, libc++, openssl)
si devine o masina de build autonoma - fara PC, fara root, fara Termux.

**Arhitectura:**
```
agent.py -> tool "toolchain"
   |
   +-- toolchain.py : bootstrap/status/env/pip_install/compile
   +-- tpm.py       : descarca .deb din repo Termux, extrage in
   |                  /data/local/tmp/tpm/usr (executabil!)
   +-- build.py     : compilare module C pentru pip
```

**Instalare:** /data/local/tmp/tpm/usr/ (uneltele) + marker .toolchain_ok

**DESCOPERIREA CHEIE (din jurnalul agentului):**
- ninja din Termux e RUPT (libandroid-spawn.so) -> cod 127 la toate comenzile
- SOLUTIE: samu (samurai 1.3) in loc de ninja
- numpy 2.5.3 compilat complet: 1625 C + 488 C++ + 165 Fortran + 29 Cython,
  217/217 tinte, functional (BLAS, LAPACK, FFT, ufuncs)

**CAPCANE REZOLVATE:**
1. /sdcard e montat noexec -> binarele trebuie in /data/local/tmp
2. .deb e arhiva "ar": ultimul membru e data.tar (nu primul xz)
3. "import gzip" loveste bug compression._common -> _streams.py oficial
4. file locking pe /sdcard -> build in /data/
5. meson PyPI fara modulul features -> meson vendored in PYTHONPATH
6. 24 functii C99 lipsa din bionic -> dezactivate 54 macro HAVE_C* in config.h
7. RUNPATH libc++_shared.so -> LD_LIBRARY_PATH

**LEGAL / LICENTE:**
Aplicatia NU include binare. Bootstrap-ul descarca din repo-ul PUBLIC Termux
(packages.termux.dev), ca apt. Licente: clang=Apache-2.0, python=PSF-2.0,
make/cmake=GPL-3.0, ninja/samu=Apache-2.0, openssl=Apache-2.0. Descarcarea si
folosirea locala nu creeaza obligatii de redistribuire. Daca cineva
impacheteaza binarele in alt produs, trebuie sa respecte licentele (inclusiv
GPL). Folosirea repo-ului de alt client e tehnica permisa dar neoficiala.

**TOOL NOU in agent:** "toolchain" (action=status/bootstrap/pip_install/
compile/env/tpm)

**Fisiere in APK:** assets/python/{toolchain.py, tpm.py, build.py, _streams.py}



### Etapa 30 - TOOLCHAIN COMPILARE NATIVA FUNCTIONAL (testat end-to-end)

**REZULTAT TESTAT (2026-09-22):**
Agentul a scris un program C, l-a compilat si l-a rulat SINGUR pe telefon:
```
calc.c -> toolchain action=compile -> COMPILE_OK
-> output: "6 * 7 = 42"
```
Agentul a detectat singur ca /sdcard e noexec, a copiat binarul in
/data/local/tmp, l-a facut executabil si l-a rulat.

**ARHITECTURA (bootstrap_direct - pur Python, fara adb in bucla):**
```
toolchain action=bootstrap
  -> _load_index()   : descarca Packages.gz din repo Termux (3001 pachete)
  -> _http_get()     : SSL cu CA bundle (certifi sau /apex conscrypt)
  -> _extract_deb()  : parseaza arhiva .ar, gaseste data.tar.xz
  -> _untar()        : parseaza tar PUR PYTHON (fara tarfile - bug Android)
  -> _fix_symlinks() : recreeaza libX.so.N + clang/ld/ar -> binarele reale
  -> _sh()           : copiaza staging (/sdcard) in prefix (/data/local/tmp)
```

**BUG-URI REZOLVATE (fiecare blocant):**
1. `compression._common` lipseste (AAPT2 ignora foldere cu "_")
   -> fix: _streams_data.py livrat ca fisier + recreare _common la runtime
2. `lzma` nu se putea importa (acelasi bug) -> _common recreat in pyhome
3. SSL CERTIFICATE_VERIFY_FAILED -> CA bundle
4. `tarfile` importa compression._common -> _untar pur Python (512B headers)
5. Numele membrilor .ar au "/" la final -> rstrip("/") (altfel endswith(".xz") esua)
6. app nu poate scrie/executa in /data/local/tmp (SELinux untrusted_app)
   -> staging in /sdcard, copiere prin shell uid=2000
7. `[TIMEOUT 40s]` din adb_client.py (signal.alarm(40) la import!)
   -> ADB_GLOBAL_TIMEOUT configurabil, default 600s
8. symlink-uri .deb (typeflag 2) nu se extrageau -> _fix_symlinks()
9. `ld` -> `lld`, apoi `ld.lld` -> `lld` (lld e driver generic)
10. compile rula in procesul app (uid 10378, nu exec /data/local/tmp)
    -> rulat prin adbsh (uid=2000)
11. output in /sdcard (noexec) -> mutat automat in /data/local/tmp

**TOOLCHAIN INSTALAT:** clang 21.1.8, make 4.4.1, cmake 4.4.3, ninja 1.13.2,
git 2.55.0, LLVM tools (ar/ld/nm/strip), pkg-config, python3 3.14.6, pip, zstd.

**TOOL in agent:** "toolchain" cu actiuni: status, bootstrap, compile, run,
pip_install, tpm, env.

**LICENTE:** bootstrap descarca din repo public Termux (ca apt). Aplicatia nu
include binare. Licente: clang=Apache-2.0, python=PSF-2.0, make/cmake=GPL-3.



### Etapa 31 - REMEDieri dupa testul AUTONOM real (2026-09-22)

Testul suprem: reset complet (fara memorie, fara toolchain), reinstalare,
task natural "compila un program C care afiseaza 6 ori 7" - FARA indicii
tehnice. Agentul a REUSIT (6 x 7 = 42) dar a intampinat erori pe care le-a
ocolit manual. Le-am eliminat din radacina:

**1. compression._common - fisier in loc de pachet**
Agentul crease `compression/_common.py` (fisier). Dar `lzma.py` face
`from compression._common import _streams` -> are nevoie de PACHET.
Fix: sterge `_common.py`, creeaza `_common/__init__.py` + `_common/_streams.py`.

**2. __pycache__ vechi bloca importul**
Chiar cu `_streams.py` prezent, Python folosea `__pycache__` din versiunea
goala. Fix: `shutil.rmtree(__pycache__)` dupa fiecare creare de `_common/`.

**3. _fix_symlinks rula in procesul app (nu vede /data/local/tmp)**
`os.listdir(ROOT+"/usr/lib")` returna gol (SELinux). Deci 0 symlink-uri ->
`clang` murea: `library "libz.so.1" not found`.
Fix: rescris complet ca SCRIPT SHELL (ruleaza prin adbsh, uid=2000):
- generic: libX.so.N.M.P -> libX.so.N si libX.so
- speciale: libz.so.1, libbz2.so.1.0, libexpat.so.1, libandroid-support.so
- binare: clang->clang-21, clang++->clang-21, ld->lld, ld.lld->lld,
  ar->llvm-ar, ranlib->llvm-ranlib, nm/objdump/strip/readelf->llvm-*,
  python->python3, pip->pip3

**4. app nu poate scrie/executa in /data/local/tmp**
- scriere: sursa C se scrie in /sdcard (sau files/), compilarea se face
  prin adbsh in /data/local/tmp
- executie: binarul se ruleaza prin adbsh (uid=2000), nu din procesul app

**REZULTAT DUPA FIX (testat pe device):**
```
bootstrap -> 65 pachete -> symlink-uri automate -> compile -> run
REZULTAT: 6*7=42   (FARA pasi manuali, FARA erori)
```

**REGULA DE AUR (de respectat in tot codul care atinge /data/local/tmp):**
Orice operatie pe fisiere din /data/local/tmp (listdir, stat, mkdir, cp,
chmod, exec) trebuie facuta PRIN SHELL (adb_client/adbsh uid=2000), NU cu
`os.*` din procesul aplicatiei (uid ~10300, SELinux untrusted_app).

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

### Etapa 28 - SUPER-PUTERI: ADB shell uid=2000 (fara root, fara PC)

**Obiectiv:** agentul sa aiba acces la comenzi de sistem (uid=2000 shell), nu doar la ce poate app-ul (uid 10362).

**Descoperirea cheie:**
- app-ul se poate autentifica la adbd-ul LOCAL (127.0.0.1:5555) prin protocolul ADB clasic
- cheia trebuie sa fie in formatul corect (`QAAAA...`, ~700 chars, FARA username)
- adbd accepta cheia de pe localhost dupa o singura aprobare "Allow"

**Ce poate face agentul acum (dovedit, 7/7):**
    adbsh id                                  -> uid=2000(shell), groups include input/adb/inet
    adbsh 'pm list packages -3 | wc -l'       -> numarul de app-uri third-party
    adbsh 'dumpsys battery | grep level'      -> bateria
    adbsh 'settings get global airplane_mode_on' -> setari (citire + scriere)
    adbsh 'screencap -p /sdcard/x.png'        -> screenshot
    adbsh 'input keyevent 3'                  -> UI automation FARA accessibility
    adbsh 'getprop ro.product.model'          -> proprietati sistem

**Ce deblocheaza (ce app code NU poate):**
    pm grant/revoke (permisiuni runtime)   appops set
    settings put secure/global             dumpsys complet
    input tap/text/keyevent                run-as pe alte app-uri
    screencap, uiautomator dump            logcat, svc, wm size/density

---

#### 28.1 - AUTO-SETUP la prima pornire (`adb_setup.py`)

Integrat in MainActivity: ruleaza inainte de `agent.py`, o singura data.

    1. LIBS: copiaza libcrypto.so, libssl.so, libadb_pairing_auth.so,
             libadb_pairing_connection.so din /apex/com.android.adbd/lib64
             (si /apex/com.android.conscrypt) in files/libs/
    2. CHEIE: genereaza RSA 2048 -> adbkey (privata) + adbkey.pub (format ADB)
              ★ SALVATA in /sdcard/Download/Agent/ (PERSISTENTA, supravietuieste
                reinstalarilor si "Clear data"!)
    3. CERT: genereaza X.509 self-signed din cheie (tls.crt + tls.key)

**Idempotent:** daca cheia exista in /sdcard, o refoloseste (nu regenereaza!).

---

#### 28.2 - Tool nou: `adbsh`

    adbsh(cmd="pm grant net.sys32.agent CAMERA")   comanda shell ca uid=2000
    adbsh(cmd="dumpsys battery")                    output complet
    adbsh(cmd="input tap 540 1200")                 UI automation

Client: `adb_client.py` (protocol ADB pur Python: CNXN/AUTH/OPEN/WRTE).
Auth: RSAPUBLICKEY direct (adbd auto-aproba pe localhost).

**AUTO-DETECTIE PORT (important!):**
    `Adb()` fara parametru citeste `getprop service.adb.tcp.port` si se
    conecteaza pe acel port (5555, 55555 SAU ORICE valoare setata de
    `adb tcpip <port>`). Daca getprop nu raspunde -> fallback: testeaza
    5555, 55555, 5556. Astfel agentul merge indiferent de portul ales.

**Formatul cheii (critic!):**
    - `adbkey.pub` = [4B len_modulus][modulus][4B len_exponent][exponent], base64
    - ~700 chars pentru RSA 2048
    - NICIODATA cu username lipit (a cauzat bucla de "Allow USB debugging")

---

#### 28.3 - CHOICE: agentul decide INTELIGENT ce tool foloseste

Adaugat in system prompt (ANDROID_GUIDE) reguli explicite:

    (1) ECRAN (read/tap/text)      -> android ui (nativ, instant, 0 auth)
    (2) SENZORI/CAMERA/BATTERIE    -> android (nativ, instant)
    (3) REFLECTION SDK             -> android eval
    (4) FISIERE/VISION             -> python, bash, read, look
    (5) SUPER-PUTERI (uid=2000)    -> adbsh DOAR cand app code NU poate:
                                      permisiuni, settings put, dumpsys, input fara a11y

**Test live (dovedit):** la 5 intrebari, agentul a ales:
    1. app pe ecran       -> android ui read   (motiv: nativ, 10x mai rapid)
    2. nr app-uri         -> adbsh (pm list -3 | wc -l)  (motiv: nevoie de pipeline shell)
    3. bateria            -> android battery get (motiv: nativ instant)
    4. senzor lumina      -> android sensor (motiv: instant)
    5. mod avion          -> android settings get (motiv: citirea e permisa nativ)

**Rezultat:** 4/5 native (rapide), 1/5 super-puteri (unde era nevoie). Ales corect + constient.

---

#### 28.4 - CE NU SE POATE (limite reale Android)

1. `adb tcpip 5555` - NU poate fi rulat de app (necesita permisiune de sistem/root)
   => o data dupa restart telefon, de pe laptop (5 secunde)
2. Aprobarea "Allow USB debugging" - dialog de sistem, o singura data
   => DAR cu cheia persistenta in /sdcard, tine pentru TOTDEAUNA (nu la reinstalare)
3. PAIRING WIRELESS (SPAKE2+TLS) - NU functioneaza din app:
   - protocolul e implementat corect (TLS+SPAKE2+PEER_INFO toate OK)
   - dar decrypt-ul final esueaza: parola SPAKE2 = cod + TLS ExportKeyingMaterial(64)
   - Python ssl NU expune export_keying_material => mismatch de chei
   - libadb_pairing_connection.so ar face export-ul, dar da fdsan/peer=NULL pe Samsung
   => singura cale wireless: client ADB extern (PC) cu `adb pair`

---

#### 28.5 - REZUMAT: ce are agentul suprem

    android      bridge Kotlin: senzori, camera, reflection SDK, ui (accessibility)
    ui           vede + controleaza alte app-uri (read/find/click/settext)
    adbsh        SUPER-PUTERI uid=2000: pm, dumpsys, settings, input, screencap...
    python       stdlib + pachete pure-Python
    bash         shell in sandbox-ul app-ului
    smart        auto-router python/bash
    read/look    fisiere mari + analiza imagini

**Autonomie:** instalezi APK-ul -> isi genereaza cheia + certul + libs SINGUR.
Singura intervenție: `adb tcpip 5555` + "Allow" o data (dupa restart).

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

---


---

## Etapa 32 - REMEDIERI TOOLCHAIN (compilarea C/C++ reparata complet)

**Context:** la sfirsitul sesiunii precedente numpy esua la pasul 1/345 cu
`ninja: subcommand failed` / `FAILED: [code=127]` si nu se stia de ce
(operatorul a intrerupt diagnosticul). Reparat acum, end-to-end.

### Cauzele REALE (4, toate inlantuite)

| # | Simptom | Cauza | Fix |
|---|---------|-------|-----|
| 1 | `code=127`, `library libX.so not found` | .deb-urile Termux au **RUNPATH hardcodat** la `/data/data/com.termux/files/usr/lib`, director care NU exista aici | `patchelf --set-rpath` pe toate binarele + .so + modulele din `lib-dynload` |
| 2 | `ninja: subcommand failed` | **ninja din Termux e RUPT**: nu poate executa NICIUN proces (nici `/system/bin/sh`) | inlocuit cu **samu** (samurai 1.9.0), care face exact acelasi lucru |
| 3 | `rm: inaccessible or not found` | subprocesele meson/ninja primesc **env minimal** (PATH doar cu prefix) -> `rm`/`sh` din `/system/bin` lipsesc | wrapper-ele adauga `/system/bin:/system/xbin` in PATH |
| 4 | `call to undeclared function ctanl/ccoshl` (numpy) | clang are target **implicit android24**; functiile C99 cu `__INTRODUCED_IN(26)` sunt ASCUNSE | wrapper `cc/clang` injecteaza `--target=aarch64-linux-android<API real>` |

**Piesa lipsa la linkare:** pachetul **`ndk-sysroot`** (nu era instalat, desi
era in lista) - aduce crt-urile (`crtbegin_dynamic.o`) si stub-urile de link.
`libm.so` NU exista in Termux: pe Android 11+ e fuzionat in libc, iar simbolurile
C99 complete (ctanl, ccoshl...) sunt in
`/apex/com.android.runtime/lib64/bionic/libm.so` -> se linkeaza cu `-L` acolo.

**Piesa lipsa la rulare:** extensiile C++ (numpy) **nu au `NEEDED libc++_shared.so`**
dar folosesc simboluri din el -> `ImportError: cannot locate symbol
_ZTVNSt6__ndk117bad_function_callE` -> fix: `LD_PRELOAD=<prefix>/lib/libc++_shared.so`.

### Functii noi in toolchain.py
- `_patch_runpath()` - corecteaza RUNPATH (binare + libs + lib-dynload)
- `_fix_ninja()`    - inlocuieste ninja rupt cu samu
- `_fix_cc_wrappers()` - wrappere cc/clang cu `--target` + PATH complet
- `_device_api()`   - detecteaza API-ul real (36 pe Android 16), cu fallback
- `check()`         - acum verifica FUNCTIONAL (compile_test), nu doar prezenta

Se apeleaza automat la finalul `bootstrap_direct()`. `env_vars()` returneaza
acum CFLAGS/LDFLAGS cu target + libm bionic, si `LD_PRELOAD`.

### REZULTAT (dovedit azi, pe telefon)
```
pip install numpy   ->  RC=0, "Successfully built numpy", "Successfully installed numpy-2.5.3"
import numpy        ->  NUMPY 2.5.3   sum=15   det=-2.0
```
Compilare nativa reala pe ARM64, fara root, fara Termux.

### CAPCANE
- `patchelf` nu se poate patch-ui PE SINE ("Text file busy") -> copie care
  patchuieste originalul.
- patch-ul pe 200+ fisiere intr-o singura bucla Python poate segfaulta la final
  (memorie) - dar lucrarea se face; verifica INTOTDEAUNA rezultatul, nu doar exit code.
- `chmod u+r` inainte de patchelf: unele binare au mod `--x` si nu pot fi citite.


---

## Etapa 33 - OPTIMIZARE COMPLETA (test end-to-end: numpy compilat de la 0)

**Testul:** app resetata complet (zero memorie, zero toolchain), task = "compileaza
numpy de la 0". **Runda 1** (fara optimizari): ~2h, blocat cu code=127, 6+ erori
nerezolvate. **Runda 2** (cu fixurile din toolchain.py): **17:54, 103 pasi, SUCCES**
(numpy 2.5.3 functional: array, matmul, det/inv/eig, FFT, random, SIMD).

### Cauzele REALE gasite (toate inlantuite, fiecare reparata la sursa)

| # | Simptom | Cauza | Fix in cod |
|---|---------|-------|-----------|
| 1 | `code=127`, `library libX.so not found` | .deb-urile Termux au RUNPATH hardcodat `/data/data/com.termux/files/usr/lib` (inexistent aici) | `_patch_runpath()` (patchelf pe binare+libs+lib-dynload) |
| 2 | `ninja: subcommand failed` | ninja din Termux e RUPT (nu executa niciun proces) | `_fix_ninja()` → samu |
| 3 | `rm: inaccessible or not found` | meson/ninja dau subprocese cu PATH minimal | wrapperele pun `/system/bin` in PATH |
| 4 | `undeclared function ctanl/ccoshl` | clang target implicit android24 ascunde C99 | `_fix_cc_wrappers()` → `--target=<API real>` |
| 5 | numele **TRUNCHIATE** in lib-dynload (`.so` dispare) | tar GNU pune numele lungi in `typeflag='L'`, `_untar` il ignora | `_untar()` cu suport `L`/`K` + PAX |
| 6 | **63 scripturi** moarte | shebang `#!/data/data/com.termux/files/usr/bin/bash` | `_fix_wrappers_shebang()` |
| 7 | `LIBDIR` = calea Termux (71 variabile!) | `_sysconfigdata` are prefixul de compilare | `_fix_sysconfig()` rescrie prefixul |
| 8 | `Compiler cython cannot compile programs` | **TOATE** `.pc` au prefix Termux (`pkg-config --cflags python3` → cale moarta) | `_fix_sysconfig()` repara **toate** `.pc` |
| 9 | `cannot locate symbol _ZTVNSt6__ndk1...` | extensiile C++ n-au `NEEDED libc++_shared.so` | `_fix_libcxx_needed()` + `-lc++_shared` in LDFLAGS |
| 10 | `CERTIFICATE_VERIFY_FAILED` (pip HTTPS) | Python Termux nu gaseste CA store | `_fix_ca_bundle()` + `SSL_CERT_FILE` |
| 11 | `python3`/`pip3` lipsesc | Termux nu face symlink-urile | `_fix_symlinks()` |
| 12 | `pip` = script cu shebang Termux | wrapper, nu binar | `_fix_symlinks()` il rescrie |
| 13 | `_prepare_dirs()` nedefinita | functie pierduta la un patch | restaurata |
| 14 | false negative la `check()` | `os.path.exists` **nu vede** `/data/local/tmp` din sandbox | toate verificarile prin `_sh` |
| 15 | `Module "features" does not exist` | numpy are nevoie de meson-ul propriu (vendored) | documentat (meson-python il foloseste automat) |
| 16 | linking fara `-lc++_shared` | meson-python nu adauga libc++ | `LDFLAGS` explicit |

### Functii noi in toolchain.py (9 fixuri automate in bootstrap)
`_prepare_dirs` · `_patch_runpath` · `_fix_ninja` · `_fix_cc_wrappers` ·
`_fix_symlinks` · `_fix_wrappers_shebang` · `_fix_sysconfig` · `_fix_ca_bundle` ·
`_fix_libcxx_needed` · `_device_api` · `check()` (functional)

### Mod de operare nou (agent.py)
- `pip_install` foloseste `_toolchain_exports()` (env complet din `env_vars()`)
  si apeleaza automat `_fix_libcxx_needed()` dupa instalare
- `compile` foloseste acelasi env complet
- `env_vars()`: PATH cu `/system/bin`, `--target`, `-L bionic`, `LD_PRELOAD`,
  `SSL_CERT_FILE`, `HOME`, `TMPDIR`, `PIP_CACHE_DIR`

### REZULTAT (masurat)
```
Runda 1: ~2h, esec (code=127)
Runda 2: 17:54, 103 pasi, SUCCES
  numpy 2.5.3 | array, matmul, det, inv, eig, FFT, random, SIMD — toate OK
```
Agentul a auto-invatat 4 lectii (identice cu diagnosticul de dezvoltare),
scrise singur in memory.md.

### CAPCANE DE RETINUT
- RUNPATH-ul se **pierde** cand agentul reinstaleaza pachete Termux → `_patch_runpath`
  trebuie re-rulat (bootstrap-ul o face).
- `patchelf` nu se poate patch-ui pe sine (Text file busy) → copie.
- patch pe 200+ fisiere intr-o bucla poate da segfault la final, dar munca se face:
  verifica REZULTATUL (readelf), nu exit code-ul.


---

## Etapa 34 - OPTIMIZARE dupa raportul llama.cpp (pre-flight + profiluri de build)

**Context:** agentul a compilat llama.cpp de la 0 (REUSIT, ~50 min, inferenta
functionala) dar a lovit **9 obstacole**; a scris singur raportul
`RAPORT_COMPILARE_llama.cpp.md` (in workspace si in repo) cu clasificarea
fiecarei probleme: necesara / evitabila, cu cost in apeluri si fix propus.

### Obstacolele raportate si fixurile aplicate

| # | Obstacol | Cauza | Fix implementat |
|---|----------|-------|-----------------|
| 1 | `git` fara `remote-https` | pachetul Termux e incomplet | documentat; `git` local merge |
| 2 | `curl` din /system/bin e rupt | legat de libcrypto incompatibil | regula: foloseste `python3 urllib` |
| 3 | `CERTIFICATE_VERIFY_FAILED` | python nu gaseste CA | `SSL_CERT_FILE` in `env_vars()` + `env.sh` (**deja**) |
| 4 | `make: /data/.../termux/sh: No such file` (cmake) | make are **SHELL hardcodat** la calea Termux | `_fix_termux_paths()` patch binarul make |
| 5 | `cmake` nu gaseste `api-level.h` | `PREFIX` nesetat | `PREFIX` in `env.sh` + profil cmake |
| 6 | `undefined symbol: std::__ndk1::cout` | `-stdlib=libc++` NU e suficient | `_fix_cxx_linker()` wrapper clang++ cu `-L -lc++_shared` |
| 7 | `undefined symbol: log2f/expf/sinf...` | `/system/lib64/libm.so` e STUB | `-L /apex/.../bionic` in profil + LDFLAGS (**deja**) |
| 8 | comenzi `adbsh` lungi blocheaza sesiunea | output bufferizat/trunchiat | documentat: scripturi in fisier + logfile |
| 9 | `git clone --depth` fara remote-helper | pachet incomplet | documentat |

### Functii noi (recomandarile R1-R9 din raportul agentului)

- **R1 `_write_env_file()`** - scrie `/data/local/tmp/tpm/env.sh` cu TOT mediul
  (PREFIX, PATH, LD_LIBRARY_PATH, SSL_CERT_FILE, CC/CXX, CFLAGS, LDFLAGS, TMPDIR,
  HOME, MAKEFLAGS). `adbsh` il **surseaza automat** la fiecare comanda, deci
  agentul nu mai scrie export-uri manual.
- **R2/R4 `preflight()`** - test de 10 secunde care compileaza si **linkeaza**
  C, C++ (STL), math (libm bionic), verifica PREFIX, make SHELL, SSL, git si
  face un **cmake+build real** de proiect C++ minim. Prinde toate problemele
  de mediu INAINTE de un build de 10 minute.
- **R3/R4b `profile("cmake"|"cflags"|"cxxflags"|"ldflags")`** - flaguri
  PREFABRICATE cu tot ce trebuie (target API, libc++, libm bionic, rpath,
  `CMAKE_SYSTEM_VERSION`). `profile("cmake")` intoarce un **script shell** gata
  de rulat (`sh prof.sh <src> <build>`) - evita problems de word-splitting.
- **R5/R6** - `adbsh` surseaza `env.sh` automat; actiunea `toolchain fix`
  re-aplica toate fixurile dupa reinstalarea de pachete Termux.
- **`_fix_cxx_linker()`** - wrappere `clang/clang++/cc/c++/gcc/g++` in
  `/data/local/tmp/wrap` care injecteaza `--target`, `-L prefix`, `-L bionic`,
  `-lc++_shared`. Orice build C++ linkeaza corect fara flaguri speciale.
- **`_fix_termux_paths()`** - patch pe binarele cmake/make (inlocuire de siruri
  cu padding NUL, caile lungi intai). NU patch-uieste libpython/libLLVM (se corup).

### Actiuni noi in tool-ul `toolchain`
`preflight` · `profile` · `fix` · `env-file` (+ enum extins, descriere actualizata
cu regula: **preflight INAINTE de orice build mare**).

### REZULTAT
```
preflight(): c_compile cxx_compile math_link prefix_hdr make_shell ssl cmake git cmake_build  -> TOATE TRUE
cmake + C++ (STL, math, vector) -> CONFIGURE OK | BUILD OK | CMAKE_CXX_MATH_OK 7
```


---

## Etapa 35 - comanda `/run_su` (rulare cu DREPTURI DE SHELL, uid=2000)

**Problema:** `/run` ruleaza scriptul in sandbox-ul aplicatiei (uid=app ~10300).
SELinux ii interzice accesul la `/data/local/tmp` si executia binarilor
compilate acolo. Deci un script care foloseste llama.cpp, toolchain-ul nativ,
modele GGUF etc. **NU putea fi rulat** din aplicatie.

**Solutia:** comanda noua `/run_su <script> [args...]` in agent.py:
- ruleaza scriptul **prin `adbsh`** (clientul ADB intern, uid=2000 shell)
- surseaza automat `/data/local/tmp/tpm/env.sh` (mediul complet)
- detecteaza tipul: `.py` -> `python3` din toolchain; `.sh` -> `sh`; altfel executabil
- streaming live al output-ului (ca `/run`), salvare automata la output lung

**Verificat pe device:**
```
/run_su test_su.sh          -> uid=2000, vede /data/local/tmp, llama-cli --version OK
/run_su run_chat.sh -p "..." -> LLM local (Qwen2.5-0.5b) a RASPUNS: 10.6 tok/s
```

**Utilizare:**
```
/run              -> uid app (sandbox, fara /data/local/tmp)
/run_su           -> uid 2000 (shell): /data/local/tmp, toolchain nativ, llama.cpp
```
Atentie la quoting: ca in orice shell, spatiile se pun intre ghilimele:
`/run_su run_chat.sh -p "Buna, cine esti?"`

**In system prompt:** agentul e instruit sa recomande `/run_su` cand operatorul
trebuie sa ruleze ceva compilat (binar, llama.cpp, model GGUF, script de chat)
si sa scrie lansatorul ca `.sh` in workspace.
