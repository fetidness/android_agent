# FIRST LAUNCH — de la clona la aplicația care rulează

---

## Ce este acest agent

`net.sys32.agent` **nu este un chatbot în browser și nu este un client subțire**. Este un
agent AI autonom care rulează **efectiv pe telefon** și care are acces la telefonul tău la
un nivel pe care aproape nicio aplicație normală nu îl are.

Când îi ceri ceva, nu trimite cererea undeva ca să îți dea un text înapoi — **execută**.
Citește senzori, ia un fix GPS real, deschide camera, compilează cod, instalează aplicații,
scrie pe ecran, citește notificările altor aplicații, intră în terminal Linux și rulează
comenzi acolo. Aplicația e terminalul; agentul e operatorul.

**Cerințe obligatorii, înainte de orice:**

1. **ADB pornit pe telefon** — aplicația comunică cu sistemul Android prin `adbd` pe
   `127.0.0.1:5555`. Fără ADB, jumătate din capabilități nu există: fără `pm install`,
   fără `dumpsys`, fără `settings put`, fără instalare de APK-uri, fără instrumentarea
   interfeței. Vezi [Pasul 5](#pasul-5--telefonul-developer-mode--usb-debugging) și
   [Pasul 6](#pasul-6--conexiunea-adb--tcpip-5555).
2. **Cheie API DeepSeek** — agentul este condus de un model de limbaj. Fără cheie,
   aplicația pornește, își extrage mediul, dar **nu poate gândi**: nu primești niciun
   răspuns. Cheia se obține de la <https://platform.deepseek.com> și se introduce la
   prima lansare. Vezi [Pasul 8](#pasul-8--prima-lansare-în-aplicație).

Fără aceste două lucruri, restul documentului nu te ajută la nimic.

---

## Ce poate face

### Android complet, prin ADB (uid 2000)

Agentul are un client ADB scris în Python, care intră în `adbd` pe loopback. Rezultatul
este **shell privilegiat** (`uid=2000(shell)`) în interiorul aplicației:

- `pm install` / `uninstall` / `grant` / `revoke` / `clear`
- `settings put global` — modifică setările sistemului și citește înapoi
- `dumpsys` complet — activity, battery, wifi, sensorservice, package
- `input tap` / `swipe` / `keyevent` — controlează orice aplicație, fără accessibility
- `screencap`, `uiautomator dump`, `logcat`, `am start` / `force-stop`
- `service call` — apeluri directe în serviciile de sistem

Pe deasupra, un al doilea canal: **reflection**. Evaluatorul din `Reflection.kt` dă
acces la **orice clasă și metodă din SDK-ul Android** — `getSystemService`, apeluri pe
obiecte, instanțiere de clase, listeners. Nu ești limitat la ce are un API pregătit.

### Binder nativ — fără adb, fără bridge

Aplicația deschide `/dev/binder` direct și vorbește cu serviciile Android la nivel de
protocol. **466 servicii** enumerate, descriptori AIDL rezolvați, apeluri reale verificate
(`display`, `input`, `batteryproperties`). Nu e o listă cosmetică: sunt apeluri IPC.

### Debian 13 complet funcțional, cu acces TOTAL la Android

În aplicație există un **terminal Linux real** — Debian 13 arm64, prin proot. Nu o
emulare, nu un sandbox gol: `apt`, `gcc`, `python3`, `git`, `nano`, `htop` funcționale.

Lucrul important, și cel care surprinde: **Debian-ul nu este orb la Android.** Are acces
la hardware și la SDK prin bridge-ul intern (AndroidBridge, TCP loopback):

- `eval call ctx.getSystemService(wifi)` → `android.net.wifi.WifiManager` real
- senzori cu valori **live**, baterie, cameră, clipboard, interfață
- reflexie arbitrară — aceleași capabilități ca agentul, din interiorul Linux-ului

Deci poți scrie un script Python în Debian care citește senzori și controlează telefonul.
Ce **nu** poate Debian: să citească `/data/data/<alt pachet>` (SELinux) și să obțină root
(nu există `su` pe device). În rest, accesul e complet.

### Mod audio — vorbești, nu tastezi

`/audio on` deschide ecranul vocal. Ții apăsat butonul, vorbești, eliberezi.

**Speech-to-text: Whisper, local.** Modelul `medium` (1,5 GB) rulează **pe telefon**,
prin `whisper.cpp` compilat nativ. Nimic nu pleacă în cloud. Ales `medium` și nu `small`
dintr-un motiv măsurat: `small` strică cuvintele românești.

**Text-to-speech: Phonon, local.** Model 31m (61 MB), voce offline. Răspunsul e rostit,
nu afișat.

Ambele sunt **offline și private**. Nu depind de rețea după setup.

### Toolchain de compilare nativ

Pe telefon există un toolchain complet, în interiorul aplicației:

- **clang 21**, lld, sysroot Android, NDK
- **Rust** (`rustc` 1.98.1, `cargo`), **maturin**
- **CMake 3.31.6**, **ninja**, **make**, **perl**
- **FLANG** (Fortran) — funcțional prin wrapper-ul din `files/tmp`

Consecința: aplicația **compilează cod pe telefon**, inclusiv extensii C/C++ pentru
Python (`pip_install` cu compilare nativă) și **APK-uri întregi** (`build_apk` — Gradle +
AGP + JDK + aapt2, toate pe device, fără PC).

### 22 de tool-uri, un agent

Agentul are la dispoziție: `python`, `bash`, `smart`, `read`, `multi`, `run_code`,
`todo`, `skill`, `scraper`, `android`, `androidapi`, `adbsh`, `binder`, `bridge`,
`terminal`, `build_apk`, `toolchain`, `bg`, `delegate`, `moa`, `look`, `help`.

Relevante pentru putere: **`delegate`** (subagenți izolați, în paralel), **`moa`**
(mai multe încercări independente pe o întrebare grea), **`bg`** (job-uri lungi în
fundal), **`run_code`** (un singur script care cheamă celelalte tool-uri).

### Web, memorie, auto-învățare

- **`scraper`** — lxml, parsel, trafilatura, quickjs, feedparser, toate native pe device
- **Skills** — proceduri salvate care se încarcă automat când sunt relevante
- **Memory** — lecții persistente, scrise la `/learn`
- **Auto-heal** — repară singur mediul la fiecare pornire (symlink-uri moarte, pachete
  trunchiate, CA bundle, identitate git)

### Ce NU poate face

Onest, ca să nu pierzi timp:

- **Nu are root.** Nu există `su` pe device; build `user`, `ro.secure=1`
- **Nu citește `/data/data/<alt pachet>`** — SELinux `untrusted_app` / `shell:s0`
- **Nu face ARP sau SYN scan** — CapEff=0, capabilitățile sunt zero în orice context
- **Nu rulează cod Java propriu din shell** — ART face `chown` la pornire, blocat structural

---

## Cuprins

1. [De ce ai nevoie](#2-de-ce-ai-nevoie)
2. [Pasul 0 — APK-ul original (OBLIGATORIU)](#pasul-0--apk-ul-original-obligatoriu)
3. [Pasul 1 — Clonare](#pasul-1--clonare)
4. [Pasul 2 — Bootstrap (scriptul .sh)](#pasul-2--bootstrap-scriptul-sh)
5. [Pasul 3 — Mediul de build pe laptop](#pasul-3--mediul-de-build-pe-laptop)
6. [Pasul 4 — Build APK](#pasul-4--build-apk)
7. [Pasul 5 — Telefonul: developer mode + USB debugging](#pasul-5--telefonul-developer-mode--usb-debugging)
8. [Pasul 6 — Conexiunea: adb + tcpip 5555](#pasul-6--conexiunea-adb--tcpip-5555)
9. [Pasul 7 — Instalare](#pasul-7--instalare)
10. [Pasul 8 — Prima lansare în aplicație](#pasul-8--prima-lansare-în-aplicație)
11. [Verificare finală](#verificare-finală)
12. [Depanare rapidă](#depanare-rapidă)

---

## 1. De ce ai nevoie

### Două lucruri fără care nu funcționează nimic

| Cerință | De ce e obligatorie | Unde se rezolvă |
|---|---|---|
| **ADB pornit** | jumătate din capabilități trec prin `adbd` | Pasul 5 + 6 |
| **Cheie DeepSeek** | fără model, agentul nu poate gândi | Pasul 8 |

Restul sunt condiții tehnice normale, enumerate mai jos.

### Pe telefon

- **Android 8.0+** (`minSdk 26`); teste făcute pe Android 16 (`targetSdk 36`)
- **arm64-v8a** (orice telefon modern). Există și x86_64 pentru emulator
- **~8 GB spațiu liber** — APK-ul are 2,4 GB, iar la prima lansare se mai extrage
  încă ~1,5 GB în stocarea internă a aplicației
- **~4 GB RAM** recomandat

### Pe laptop

- **Windows / macOS / Linux** — build-ul e identic, doar căile diferă
- **~15 GB spațiu liber** (repo + APK + Gradle cache)
- **Internet** pentru prima build (dependențele Gradle, ~500 MB o singură dată)

---

## Pasul 0 — APK-ul original (OBLIGATORIU)

**Asta e partea care nu se poate sări.** Din repo **lipsesc intenționat** fișierele
binare mari — nu încap în git:

| Ce lipsește | Mărime | De unde vine |
|---|---|---|
| `assets/toolchain/` | ~1056 MB | extras din APK-ul original |
| `assets/android_build/` | ~399 MB | extras din APK-ul original |
| `assets/models/` (voce) | ~63 MB | extras din APK-ul original |
| `assets/whisper/models/` | 1,5 GB | extras din APK **sau** descărcat |
| `assets/proot/` | ~var | extras din APK-ul original |
| `jniLibs/*.so` | ~24 MB | extras din APK-ul original |

Toate se află **într-un APK deja construit**. De aceea ai nevoie de unul.

### De unde iei APK-ul — link direct

**Descarcă de aici:**

```
https://sys32.net/dist/net.sys32.agent.apk
```

```bash
mkdir -p dist
curl -L -o dist/net.sys32.agent.apk https://sys32.net/dist/net.sys32.agent.apk
```

Sau cu reluare din locul unde s-a întrerupt (recomandat pentru 2,4 GB):

```bash
curl -L -C - -o dist/net.sys32.agent.apk https://sys32.net/dist/net.sys32.agent.apk
```

Sau cu `wget`:

```bash
wget -c -O dist/net.sys32.agent.apk https://sys32.net/dist/net.sys32.agent.apk
```

**Mărime:** 2 675 243 215 bytes (2,4 GB)

**Verifică integritatea** după descărcare — dacă hash-ul nu corespunde, descărcarea
s-a stricat și bootstrap-ul va eșua în moduri greu de diagnosticat:

```bash
sha256sum dist/net.sys32.agent.apk
# asteptat:
# d9e4bd32ff5e99faf42fc3f6980ce2c682ae890e84373f10e71932e654bfe44c
```

```bash
# macOS
shasum -a 256 dist/net.sys32.agent.apk
```

```powershell
# Windows
Get-FileHash dist\net.sys32.agent.apk -Algorithm SHA256
```

> **Nu ai APK-ul?** Nu poți face bootstrap de la zero, pentru că toolchain-ul nativ
> (clang, sysroot, Rust) ar trebui compilat de la sursă — proces de câteva ore pe
> un laptop puternic. APK-ul e calea normală, nu o scurtătură.

### Unde îl pui

**Exact în `dist/`**, la rădăcina repo-ului, clonat:

```
android_agent/
└── dist/
    └── net.sys32.agent.apk      <- AICI (numele nu contează, dar extensia da)
```

```bash
mkdir -p dist
ls -lh dist/net.sys32.agent.apk   # verifică: 2,4 GB
```

`dist/` e în `.gitignore` — APK-ul rămâne local, nu se urcă în git.

### Verifică APK-ul ÎNAINTE de bootstrap

Un APK trunchiat (descărcare întreruptă) produce erori criptice mai târziu. Testează-l:

```bash
unzip -t dist/net.sys32.agent.apk | tail -3
# așteptat: "No errors detected in compressed data of dist/net.sys32.agent.apk."
```

Dacă `unzip -t` raportează erori → **reia descărcarea**. Nu continua.

---

## Pasul 1 — Clonare

```bash
git clone https://github.com/fetidness/android_agent.git
cd android_agent
```

Repo-ul are ~100 MB (istoricul) și ~1400 fișiere.

Dacă folosești SSH:

```bash
git clone git@github.com:fetidness/android_agent.git
```

---

## Pasul 2 — Bootstrap (scriptul .sh)

Acesta e **singurul pas greu** și face tot: extrage binarele din APK în locurile
corecte în arborele de surse.

### Rulează

```bash
cd android_agent
bash tools/bootstrap_binaries.sh
```

Scriptul caută automat cel mai recent `.apk` din `dist/` — **nu are nevoie de telefon,
nu are nevoie de adb**. Poți rula totul pe laptop, offline după ce ai APK-ul.

### Ce face, în ordine

| # | Extrage | Destinație | Mărime |
|---|---|---|---|
| 1 | `lib/arm64-v8a/*` | `app/src/main/jniLibs/arm64-v8a/` | ~24 MB |
| 2 | `assets/toolchain/*` | `app/src/main/assets/toolchain/` | ~1056 MB |
| 3 | `assets/models/*` | `app/src/main/assets/models/` | ~63 MB |
| 4 | `assets/whisper/models/*` | `app/src/main/assets/whisper/models/` | 1,5 GB |
| 5 | `assets/proot/*` | `app/src/main/assets/proot/` | — |
| 6 | `assets/android_build/*` | `app/src/main/assets/android_build/` | ~399 MB |

După ce extrage, scrie `local.properties` cu `sdk.dir=` (dacă detectează un Android SDK).

### Trei reguli de care depinde totul

1. **Se rulează din orice director.** Scriptul își calculează singur rădăcina
   (`$(dirname $0)/..`). Nu-l muta din `tools/`.
2. **E idempotent.** La a doua rulare sare peste ce există deja cu dimensiunea corectă.
   Dacă s-a întrerupt, **rulează-l din nou** — nu șterge nimic manual.
3. **`.so`-urile urmărite de git nu se ating.** `libptts_ffi.so` și `libptts_exec.so`
   vin din repo, nu din APK (altfel s-ar suprascrie cu o versiune veche).

### Dacă eșuează

**`nu gasesc niciun APK in .../dist/`**
→ APK-ul nu e în `dist/`. Verifică `ls dist/*.apk`. Numele nu contează, extensia da.

**`unzip lipseste`**
```bash
sudo apt install unzip        # Debian/Ubuntu
brew install unzip            # macOS
```
Pe Windows: folosește **Git Bash** (vine cu unzip) sau WSL.

**`ATENTIE: assets/android_build lipseste din APK`**
→ APK-ul e dintr-un build fără build-tools. Aplicația va porni, dar `build_apk`
(compilare de APK pe telefon) nu va funcționa.

**Se oprește la jumătate, fără mesaj**
→ Spațiu pe disc. `df -h .` — ai nevoie de ~4 GB liberi în timpul extragerii.

---

## Pasul 3 — Mediul de build pe laptop

Aici construiești un APK **nou**, din sursele tale. Ai nevoie de patru componente.

### 3.1 JDK 21

**Obligatoriu JDK 17 sau 21.** Gradle 8.11.1 nu merge cu JDK 8/11.

```bash
# Debian / Ubuntu
sudo apt install openjdk-21-jdk

# macOS
brew install openjdk@21

# Windows: descarcă de la https://adoptium.net (Temurin 21)
```

Verificare:
```bash
java -version      # -> openjdk version "21.x"
```

> Pe Debian trixie **nu există openjdk-17** — folosește 21. AGP 8.7.3 merge cu el.

### 3.2 Android SDK (cu build-tools și platform 36)

Cea mai simplă cale — **Android Studio** (instalează SDK-ul automat):
<https://developer.android.com/studio>

Sau doar command-line tools:
<https://developer.android.com/studio#command-tools>

Ai nevoie de:
- **platforms;android-36** (`compileSdk = 36`)
- **build-tools;35.0.1** (sau 36.0.0)
- **platform-tools** (conține `adb`)

```bash
sdkmanager "platforms;android-36" "build-tools;35.0.1" "platform-tools"
```

> Pe Windows SDK-ul ajunge implicit în `%LOCALAPPDATA%\Android\Sdk`.

### 3.3 NDK 29.0.14206865

Proiectul fixează `ndkVersion = "29.0.14206865"`.

```bash
sdkmanager "ndk;29.0.14206865"
```

> **Capcană reală, măsurată:** **NDK 27 dă SIGSEGV** la link pe acest proiect.
> Nu improviza cu altă versiune — pune exact 29.0.14206865.

### 3.4 Gradle — vine cu proiectul

**Nu instala Gradle.** Proiectul are wrapper: `./gradlew` (Gradle 8.11.1).
Prima rulare îl descarcă singur (~130 MB).

### 3.5 Spune-i lui Gradle unde e SDK-ul

Fișierul `local.properties` (în `workspace/app/net.sys32.agent/`) — nu se comite,
fiecare are calea lui:

```properties
sdk.dir=/home/USER/Android/Sdk
```

```properties
# Windows (notează backslash-urile dublate)
sdk.dir=C\:\\Users\\USER\\AppData\\Local\\Android\\Sdk
```

> `bootstrap_binaries.sh` îl scrie automat dacă găsește SDK-ul. Dacă nu l-a găsit,
> scrie-l manual — altfel Gradle dă **`SDK location not found`**.

### Verificare completă a mediului

```bash
cd android_agent/workspace/app/net.sys32.agent

export JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64    # ajustează la tine
export ANDROID_HOME=$HOME/Android/Sdk
export ANDROID_SDK_ROOT=$ANDROID_HOME

java -version                 # openjdk 21
./gradlew --version           # Gradle 8.11.1 + JVM 21
echo $ANDROID_HOME            # calea SDK-ului
ls $ANDROID_HOME/platforms    # trebuie să conțină android-36
ls $ANDROID_HOME/ndk          # trebuie să conțină 29.0.14206865
```

Dacă toate patru răspund corect, ești gata de build.

---

## Pasul 4 — Build APK

```bash
cd android_agent/workspace/app/net.sys32.agent

export JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64
export ANDROID_HOME=$HOME/Android/Sdk
export ANDROID_SDK_ROOT=$ANDROID_HOME

./gradlew assembleDebug
```

**Rezultat:** `app/build/outputs/apk/debug/app-debug.apk` (~2,4 GB)

### Timpi reali, măsurați pe acest proiect

- **prima build** (descarcă deps, compilează tot): **10-20 min**
- **incremental**, după un `.py` sau `.kt`: **20-40 s**
- **nimic schimbat** (`--offline`): **~14 s**
- **`clean assembleDebug`**: minute bune (re-ambalează 1,9 GB de assets)

### Comenzi utile

```bash
./gradlew --offline assembleDebug      # fără rețea (deps în cache)
./gradlew clean assembleDebug          # rebuild de la zero
./gradlew assembleDebug --stacktrace   # când ceva crapă și vrei detalii
```

### Configurare relevantă (`app/build.gradle.kts`)

- `compileSdk 36`, `minSdk 26`, `targetSdk 36`
- `abiFilters arm64-v8a` (+ `x86_64` pentru emulator)
- `packaging.jniLibs.useLegacyPackaging = true`
  → **obligatoriu**: altfel `.so`-urile nu se pot executa pe API 29+

### Verifică APK-ul înainte de instalare

```bash
APK=app/build/outputs/apk/debug/app-debug.apk

ls -lh $APK                                             # 2675243215 bytes
unzip -l $APK | grep -c 'assets/python/'                # ~1400 fișiere
unzip -l $APK | grep 'assets/python/agent.py'           # agentul e prezent
unzip -l $APK | grep 'assets/toolchain/bin/clang'       # toolchain-ul e prezent
```

Dacă `assets/toolchain/` lipsește din APK → bootstrap-ul n-a rulat sau a eșuat parțial.
**Rulează `bash tools/bootstrap_binaries.sh` din nou** și rebuild.

### Dacă eșuează

**`SDK location not found`**
→ lipsește `local.properties` sau `sdk.dir` e greșit. Vezi 3.5.

**`NDK not configured` / `SIGSEGV` la link**
→ NDK greșit. Trebuie exact `29.0.14206865` (3.3).

**`Unsupported class file major version`**
→ JDK prea vechi. Trebuie 17 sau 21.

**`OutOfMemoryError: Java heap space`**
→ în `gradle.properties`: `org.gradle.jvmargs=-Xmx3072m` (sau mai mult).

**Build-ul ia peste 40 min**
→ normal prima dată dacă rețeaua e lentă; următoarele sunt de ordinul secundelor.

---

## Pasul 5 — Telefonul: developer mode + USB debugging

Fără asta, laptopul nu poate vorbi cu telefonul.

### 5.1 Activează Developer options

1. **Settings → About phone**
2. Găsește **Build number**
   - Samsung: *Settings → About phone → Software information → Build number*
   - Xiaomi/Redmi: *Settings → About phone → MIUI version* (apasă de 7 ori)
   - Pixel/stock: *Settings → About phone → Build number*
3. **Apasă pe Build number de 7 ori**
4. Apare: *"You are now a developer!"*
5. Dacă cere PIN/parolă, introdu-l

### 5.2 Activează USB debugging

1. **Settings → System → Developer options**
   (Samsung: *Settings → Developer options*, direct în Settings)
2. Găsește **USB debugging** și pornește-l
3. Confirmă dialogul

### 5.3 Setări care ajută (recomandate)

- **Stay awake** → ON. Ecranul nu se stinge în timpul transferului de 2,4 GB.
- **Verify apps over USB** → OFF (opțional; poate încetini instalarea)
- **Default USB configuration** → *File Transfer (MTP)*

> **Samsung:** *USB debugging* e destul. **Nu** e nevoie de „OEM unlocking"
> (ăla e pentru bootloader, nu pentru adb).

---

## Pasul 6 — Conexiunea: adb + tcpip 5555

### 6.1 Verifică adb pe laptop

`adb` vine cu platform-tools (instalat la 3.2).

```bash
adb version
```

Dacă nu e în `PATH`, folosește calea absolută:
`$ANDROID_HOME/platform-tools/adb`

### 6.2 Conectează prin USB și autorizează

1. Cablu USB **de date** (nu doar de încărcare — capcană frecventă)
2. Pe telefon apare: **"Allow USB debugging?"**
3. Bifează **"Always allow from this computer"**
4. **Allow**

```bash
adb devices -l
# așteptat:
# RZGL102X5AT   device usb:1-1 product:a36xxx model:SM_A366B device:a36xxx
```

**`device`** = OK. **`unauthorized`** = nu ai apăsat Allow. **`offline`** = replug.

### 6.3 Deschide portul TCP 5555

Acesta e pasul care îți permite să lucrezi **fără cablu** după aceea:

```bash
adb tcpip 5555
# -> restarting in TCP mode port: 5555
```

Telefonul se restartează în modul TCP. Găsește-i IP-ul în rețea:

```bash
adb shell ip -f inet addr show wlan0 | grep inet
# -> inet 192.168.1.100/24 brd ... scope global wlan0
```

Sau: *Settings → Connections → Wi-Fi → rețeaua curentă → IP address*

Conectează-te prin rețea și **scoate cablul**:

```bash
adb connect 192.168.1.100:5555
# -> connected to 192.168.1.100:5555

adb devices          # acum apare și intrarea IP
```

Acum transferul merge prin Wi-Fi. Pentru 2,4 GB, Wi-Fi 5 GHz e vizibil mai rapid
decât USB 2.0.

### 6.4 (Opțional) Înapoi la USB

TCP mode se pierde la reboot. Pentru a reveni la USB:

```bash
adb usb
```

### Verificare rapidă

```bash
adb shell getprop ro.product.model     # SM-A366B
adb shell getprop ro.build.version.sdk # 36
adb shell whoami                       # shell
```

> **Notă:** în TCP mode, dacă rețeaua se schimbă (alt router, VPN, hotspot),
> reconectează. Telefonul revine la USB după fiecare reboot — rulează din nou
> `adb tcpip 5555`.

---

## Pasul 7 — Instalare

### ⚠ Nu instala APK-ul din Downloads

**Aceasta e cea mai costisitoare capcană**, dovedită pe Android 16:

Copiezi APK-ul în `Downloads`, apeși pe el, dai *Install* → **„App not installed."**
fără niciun motiv vizibil. Nu e APK-ul stricat și nu e spațiul pe disc.

Motivul real (mesajul ascuns de interfață):

```
System server has no access to read file context u:object_r:fuse:s0
Error: Can't open file: /sdcard/Download/app-debug.apk
Consider using a file under /data/local/tmp/
```

Android 16 **nu permite instalarea unui APK din `/sdcard`** (context SELinux
`u:object_r:fuse:s0`). `/data/local/tmp` e citibil de `system_server`, deci merge.

### Instalarea corectă

```bash
adb push app/build/outputs/apk/debug/app-debug.apk /data/local/tmp/agent.apk

adb shell pm install -r -g /data/local/tmp/agent.apk
# -> Success
```

Flag-uri:
- `-r` — reinstalează păstrând datele
- `-g` — acordă toate permisiunile runtime dintr-un foc

**Durează 2-5 minute** pentru 2,4 GB. Nu întrerupe.

### Verificare

```bash
adb shell dumpsys package net.sys32.agent | grep -E 'firstInstallTime|lastUpdateTime|versionName'
```

Instalare curată → `firstInstallTime == lastUpdateTime`.
Dacă diferă, e un upgrade peste o versiune veche.

### Dacă eșuează

**`INSTALL_FAILED_INSUFFICIENT_STORAGE`**
→ chiar nu e spațiu. Ai nevoie de ~8 GB liberi (APK + extracție).

**`INSTALL_FAILED_UPDATE_INCOMPATIBLE`**
→ semnătură diferită față de versiunea instalată (alt keystore).
```bash
adb uninstall net.sys32.agent     # ATENȚIE: șterge datele aplicației
```
Apoi reinstalează. Dacă vrei să păstrezi datele, folosește același `debug.keystore`
cu care a fost semnat APK-ul instalat anterior.

**`device unauthorized`** după dezinstalare
→ telefonul revocă cheia. Reapasă **Allow** pe dialogul de pe ecran.

**`adb: failed to read copy response`** la push
→ cablu/port USB slab. Încearcă alt cablu sau prin TCP (Pasul 6.3).

---

## Pasul 8 — Prima lansare în aplicație

```bash
adb shell am start -n net.sys32.agent/.MainActivity
```

Sau atinge iconița **AGENT** pe ecran.

### Ce se întâmplă, în ordine

**1. Panoul de setup** apare peste terminal:
- titlul `⚡ AGENT`, subtitlul `First-time setup`
- mesaj: `Please wait, take a coffee and relax...`
- o bară de progres legată de permisiunile acordate
- lista `PERMISSIONS` cu bifă live

**2. Fereastra de permisiuni (30 s).**
Aplicația cere: Camera, Microphone, Location, Contacts, Photos & media,
Notifications, All files access.
**Acordă toate.** Se închide imediat ce sunt toate date.

Dacă refuzi vreuna:
```
⚠ WARNING: 2 permission(s) not granted.
Setup CANNOT start until ALL are granted: Camera, Notifications
[ GRANT ALL PERMISSIONS ]
```
Setup-ul e **blocat obligatoriu**. Dacă ai dat „Don't ask again", butonul deschide
direct Setările aplicației.

**3. Etapele de setup** apar o singură dată, cu bifă la final:
```
✓ Environment     extrage scripturile Python + stdlib complet (~1,5 GB)
✓ Libraries       verifică stdlib
✓ Bridge          pornește AndroidBridge
✓ Agent           lansează procesul Python
```

**Extragerea durează 3-10 minute** la prima lansare. E normal ca ecranul să pară
blocat. **Nu închide aplicația.**

**4. Cheia API DeepSeek — OBLIGATORIE.**

Fără cheie, aplicația pornește și își extrage mediul, dar **agentul nu poate gândi**:
nu primești niciun răspuns la nicio comandă.

Dacă lipsește, apare input-ul:
```
paste DeepSeek key (sk-...) and send
```

Lipește cheia și trimite. Se salvează local, în `files/python/key.txt` și
`files/home/key.txt`. Nu pleacă nicăieri altundeva decât la API-ul DeepSeek.

De unde iei cheia: <https://platform.deepseek.com> → *API keys* → *Create*.
Arată ca `sk-...` (35 caractere).

> **Atenție la siguranță:** nu pune cheia în git, în APK sau în `assets/`. Se scrie
> doar la runtime, în stocarea privată a aplicației. Fișierul `key.txt` e deja în
> `.gitignore` tocmai din acest motiv.

**5. Terminalul apare** după ce toate etapele sunt bifate.

### ADB — obligatoriu, verifică acum

Dacă ADB nu e pornit, aplicația merge, dar tool-urile privilegiate (`android`, `adbsh`,
`build_apk`, `binder`) nu au cu ce lucra. Verifică imediat după setup:

```bash
adb shell pm list packages | grep sys32     # de pe laptop -> trebuie sa raspunda
```

Din terminalul aplicației, primul semn că ADB funcționează:

```python
import adb_client
adb_client.shared().shell('id -u')     # -> 2000
```

Dacă primești `not authorised` sau timeout, vezi [Pasul 6](#pasul-6--conexiunea-adb--tcpip-5555):
`adb tcpip 5555` trebuie rulat pe telefon, iar dialogul *Allow USB debugging?* acceptat.

### Verificare

```bash
adb shell ps -A -o PID,PPID,NAME | grep -E 'sys32|libpyexec'
# trebuie să vezi procesul Python (libpyexec) printre rezultate
```

---

## Verificare finală

Totul funcționează dacă **toate** răspund corect:

```bash
# 1. aplicația e instalată
adb shell pm list packages | grep sys32
# -> package:net.sys32.agent

# 2. procesul Python rulează
adb shell ps -A | grep libpyexec

# 3. assets-urile s-au extras
adb shell run-as net.sys32.agent ls files/python/agent.py
adb shell run-as net.sys32.agent ls files/pyhome/.stdlib_ok

# 4. serverele răspund (din terminalul aplicației)
cat /data/data/net.sys32.agent/files/bridge.port    # portul AndroidBridge (mereu, dupa setup)
cat /data/data/net.sys32.agent/files/dshell.port    # portul DShell (apare cand porneste agentul)

# 5. toolchain-ul e funcțional (din terminalul aplicației)
toolchain selftest        # -> ok pentru C, C++, Python ext
```

---

## Depanare rapidă

**Aplicația pornește și se închide imediat**
→ Logcat: `adb logcat -d | grep -iE 'sys32|AndroidRuntime|FATAL' | tail -40`
Cauza cea mai frecventă la instalare curată: stdlib-ul Python nu s-a extras complet.

**Setup-ul se blochează la „Environment"**
→ `adb shell run-as net.sys32.agent du -sh files/pyhome`
Dacă e sub ~400 MB, extracția e în curs sau a eșuat (spațiu). Verifică `df /data`.

**Terminalul nu se deschide / Debian nu pornește**
→ Normal la prima apăsare: rootfs-ul se extrage pas cu pas, cu progres.
Durează câteva minute. Mesajul final e `READY !`.

**`adb` nu vede telefonul deloc**
→ `adb devices` gol: încarcă doar (fără date)? Alt cablu. Alt port USB (preferă
porturile din spate pe desktop). Pe Windows: instalează driverul USB al producătorului.
Pe Linux: `sudo usermod -aG plugdev $USER` apoi re-login.

**`adb connect` dă `Connection refused`**
→ TCP mode se pierde la reboot. Reconectează USB și rulează din nou `adb tcpip 5555`.
Verifică și că laptopul și telefonul sunt în **aceeași** rețea (nu VPN, nu hotspot separat).

**Build-ul reușește, dar aplicația nu are toolchain (build_apk eșuează)**
→ `assets/toolchain/` lipsește din APK. `bash tools/bootstrap_binaries.sh` din nou,
apoi rebuild. Verifică: `unzip -l app-debug.apk | grep -c 'assets/toolchain/'`.

---

## Recapitulare într-o singură fereastră

```bash
# --- pe laptop ---
git clone https://github.com/fetidness/android_agent.git && cd android_agent
mkdir -p dist
curl -L -C - -o dist/net.sys32.agent.apk https://sys32.net/dist/net.sys32.agent.apk
sha256sum dist/net.sys32.agent.apk                    # d9e4bd32...bfe44c
bash tools/bootstrap_binaries.sh                      # extrage binarele din APK

cd workspace/app/net.sys32.agent
export JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64
export ANDROID_HOME=$HOME/Android/Sdk
./gradlew assembleDebug                               # ~10-20 min prima dată

# --- pe telefon ---
# Settings > About phone > Build number x7 > Developer options > USB debugging ON
# conectează USB, apasă Allow pe telefon

adb tcpip 5555                                        # deschide portul
adb connect 192.168.1.100:5555                        # opțional: fără cablu

# --- instalare ---
adb push app/build/outputs/apk/debug/app-debug.apk /data/local/tmp/agent.apk
adb shell pm install -r -g /data/local/tmp/agent.apk  # -> Success
adb shell am start -n net.sys32.agent/.MainActivity

# --- în aplicație ---
# acordă TOATE permisiunile -> așteaptă extracția (3-10 min) -> lipește cheia API
```

---

*Document întocmit pe baza comenzilor și a valorilor reale din repo: `tools/bootstrap_binaries.sh`,
`app/build.gradle.kts` (AGP 8.7.3, Gradle 8.11.1, compileSdk 36, NDK 29.0.14206865),
`AndroidManifest.xml` și comportamentul măsurat pe Samsung SM-A366B / Android 16.*
