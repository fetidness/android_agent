# Agent Android (net.sys32.agent)

## ⚡ START RAPID — CITESTE ASTA PRIMUL

**Daca esti un agent proaspat resetat (memorie goala) si citesti asta, iata esenta:**

### Ce esti
Esti un **agent autonom Android** (`net.sys32.agent`) care ruleaza PE telefon
(Samsung SM-A366B, Android 16), compilat de la zero cu:
- **Python 3.14.7** compilat pentru ARM64 (in APK, ca `libpyexec.so`)
- **Kotlin** pentru UI + bridge + accessibility
- **DeepSeek API** pentru creier

### Ce poti face (12 tool-uri)

| Tool | Ce face | Uid |
|------|---------|-----|
| `android` | bridge Kotlin: senzori, camera, reflection SDK, sub-toolui `ui` | 10362 (app) |
| `ui` | VEDE + CONTROLEAZA alte app-uri (read/find/click/settext/tap) | 10362 |
| **`adbsh`** | **SUPER-PUTERI: shell ca uid=2000 (pm grant, dumpsys, settings, input, screencap)** | **2000 (shell!)** |
| `python` | stdlib + pachete pure-Python | 10362 |
| `bash` | shell in sandbox-ul app | 10362 |
| `smart` | auto-router python/bash | 10362 |
| `read` | **citire cu BUGET GARANTAT** (path/offset/limit/budget/grep) — nu se taie niciodata | 10362 |
| **`multi`** | **BATCH: 2-6 operatiuni independente intr-UN apel** (economie ~60-97% tokeni) | 10362 |
| `look` | analiza imagini (vision) | — |
| `bg` | **gestionar de procese in fundal** (start/status/log/kill/list/clean) — OBLIGATORIU pentru orice comanda >30s | 10362 |
| `toolchain` | compilare C/C++ nativa pe telefon (clang-21, samu, pkg Termux) | 10362 |

### REGULA DE AURENTRU ALEGEREA TOOL-URILOR
1. **Ecran** (citire/tap/text) → `android ui` (nativ, instant, 0 auth)
2. **Senzori/camera/baterie** → `android` (nativ, instant)
3. **Reflection SDK** → `android eval`
4. **Fisiere/imagini** → `python`, `bash`, `read`, `look`
5. **Super-puteri** (uid=2000) → `adbsh` **DOAR** cand app-ul NU poate:
   permisiuni (`pm grant`), `settings put`, `dumpsys`, `input` fara accessibility,
   `run-as` alte app-uri, `screencap`, `logcat`

> **NU folosi `adbsh` pentru ce face `android`/`python`** — e 10x mai lent si poate rate-limita.
6. **Mai multe verificari independente** → `multi` **O SINGURA DATA** (fiecare
   cerere retrimite TOT contextul: 2-6 ops intr-un apel = economie ~60-97% tokeni)


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

---

## 🛠 OPERATIUNI (BUILD · INSTALL · DEBUG · VERIFICARE)

> **Sectiunea asta e PROCEDURA OPERATIONALA.** Daca esti un agent proaspat resetat
> si trebuie sa construiesti, instalezi sau sa debughezi aplicatia, citeste DOAR
> partea asta si urmeaz-o pas cu pas. Restul documentului explica DE CE.

---

### OP.1 — MEDIUL DE BUILD (pe laptop)

| Componenta | Valoare | Nota |
|------------|---------|------|
| JDK | `/usr/lib/jvm/java-21-openjdk-amd64` | **JDK 21** — Debian trixie NU are openjdk-17; Gradle 8.11.1 + AGP merg cu 21 |
| Android SDK | `/home/gab/android` | `ANDROID_HOME` = `ANDROID_SDK_ROOT` |
| build-tools | `34.0.0`, `35.0.0`, `35.0.1`, `36.0.0` | se foloseste automat de AGP |
| Gradle | wrapper **8.11.1** | cache in `~/.gradle/wrapper/dists/gradle-8.11.1-bin` |
| adb | `/home/gab/android/platform-tools/adb` | **NU e in PATH!** foloseste calea absoluta |
| NDK / cmake / emulator | in `/home/gab/android/` | doar pentru build nativ, nu pentru APK |
| Device | `RZGL102X5AT` (Samsung SM-A366B, Android 16) | `adb devices -l` |

**De ce conteaza:** `env.sh` din vechea structura **a fost sters** (commit `f72a5eb`).
Toate variabilele sunt setate acum de `build_app.sh`. Daca rulezi `gradlew` manual,
exporta-le tu:

```bash
export JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64
export ANDROID_HOME=/home/gab/android
export ANDROID_SDK_ROOT=/home/gab/android
export PATH=$JAVA_HOME/bin:$ANDROID_HOME/platform-tools:$PATH
```

**Verificare mediu (5 secunde):**
```bash
java -version                                  # -> openjdk 21.0.12.1
cd /home/gab/Desktop/agent/workspace/app/net.sys32.agent && ./gradlew --version
/home/gab/android/platform-tools/adb devices -l
```

---

### OP.2 — BUILD APK

#### Calea normala (build + install + start) — 99% din cazuri

```bash
cd /home/gab/Desktop/agent/workspace/app
./build_app.sh
```

Ce face scriptul (citit, verificat):
```bash
export JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64
export ANDROID_HOME=/home/gab/android
export ANDROID_SDK_ROOT=/home/gab/android
export PATH=$JAVA_HOME/bin:$ANDROID_HOME/platform-tools:$PATH
cd "$(dirname "$0")/net.sys32.agent"
./gradlew assembleDebug                        # BUILD
adb install -r app/build/outputs/apk/debug/app-debug.apk   # INSTALL
adb shell am start -n net.sys32.agent/.MainActivity        # START
```

#### Doar build (fara install)

```bash
cd /home/gab/Desktop/agent/workspace/app/net.sys32.agent
./gradlew assembleDebug                 # APK: app/build/outputs/apk/debug/app-debug.apk
./gradlew --offline assembleDebug       # fara retea (deps in cache) — ~14s incremental
./gradlew clean assembleDebug           # rebuild de la ZERO (lent: 59M assets + 24M libs)
./gradlew assembleRelease               # release (isMinifyEnabled=false, nesemnat)
```

| Comanda | Timp tipic | Cand |
|---------|-----------|------|
| `assembleDebug --offline` (nimic schimbat) | ~14 s | verifici ca mediul e OK |
| `assembleDebug` dupa 1 fisier `.py`/`.kt` | ~20-40 s | iteratie normala |
| `clean assembleDebug` | minute | schimbari de config/deps |

**Configurare relevanta** (`app/build.gradle.kts`): `compileSdk 36`, `minSdk 26`,
`abiFilters arm64-v8a + x86_64`, `packaging.jniLibs.useLegacyPackaging = true`
(★ obligatoriu: altfel `.so`-urile nu se pot executa pe API 29+).
`gradle.properties`: `-Xmx3072m`, `parallel`, `caching`, `android.useAndroidX`.

**Verificare APK inainte de install** (comenzi TESTATE, cu rezultatul real de pe acest proiect):
```bash
APK=app/build/outputs/apk/debug/app-debug.apk
ls -lh $APK            # -> -rw-rw-r-- 33M  app-debug.apk
/home/gab/android/build-tools/35.0.1/aapt2 dump badging $APK 2>&1 | head -4
#   -> package: name='net.sys32.agent' versionCode='1' versionName='1.0'
#      platformBuildVersionName='16' platformBuildVersionCode='36' compileSdkVersion='36'
#      minSdkVersion:'26' / targetSdkVersion:'36'
#      uses-permission: name='android.permission.INTERNET' ...
unzip -l $APK | grep -c 'assets/python/'              # -> 928 fisiere Python ambalate
unzip -l $APK | grep 'assets/python/agent.py'         # -> 151871  assets/python/agent.py
unzip -l $APK | grep 'lib/arm64-v8a/'
#   -> 4537664  lib/arm64-v8a/libcrypto_python.so
#        4400  lib/arm64-v8a/libpyexec.so          (mic = interpreterul)
#     5828792  lib/arm64-v8a/libpython3.14.so
#        4048  lib/arm64-v8a/libpython3.so
#      886800  lib/arm64-v8a/libsqlite3_python.so
#      956256  lib/arm64-v8a/libssl_python.so
/home/gab/android/build-tools/35.0.1/dexdump -f $APK >/dev/null 2>&1 && echo dex-ok   # -> dex-ok
```
> ⚠️ `aapt2` scrie `version` pe **stderr** (pe stdout da gol) — nu te speria de output gol acolo.
> ⚠️ AAPT2 **IGNORA** directoarele din assets care incep cu `_` → de asta
> `_path.py` / `_streams.py` sunt livrate ca FISIERE, nu ca foldere. Daca un import
> da `ModuleNotFoundError` pentru un subpachet cu `_`, asta e cauza.

---

### OP.3 — INSTALL + CELE 3 CAPCANE OBLIGATORII

```bash
ADB=/home/gab/android/platform-tools/adb
$ADB install -r app/build/outputs/apk/debug/app-debug.apk    # "Success"
$ADB shell am start -n net.sys32.agent/.MainActivity
```

**Verificare ca s-a instalat CHIAR versiunea noua:**
```bash
$ADB shell dumpsys package net.sys32.agent | grep -E 'lastUpdateTime|codePath|versionName'
stat -c '%y' app/build/outputs/apk/debug/app-debug.apk        # compara mtime APK cu lastUpdateTime
$ADB shell pm list packages | grep sys32                       # package present?
```
> ⚠️ Daca procesul VECHI inca ruleaza, ecranul poate arata codul vechi desi
> `lastUpdateTime` e nou → `am force-stop` + `am start`, sau `uninstall` + `install`.

#### ★ CAPCANA 1 — `.assets_vNN` (cea mai frecventa)

`MainActivity.kt` in `extractAssets()`:
```kotlin
val stamp = File(filesDir, ".assets_v81")
if (stamp.exists() && dest.exists()) return   // ← iese IMEDIAT daca markerul exista
```
Deci: **modificarile din `assets/` NU ajung pe device** daca nu incrementezi markerul.

**Procedura:**
```bash
# 1. gaseste markerul curent
grep -n 'assets_v' app/src/main/java/net/sys32/agent/MainActivity.kt
#    -> 554:  val stamp = File(filesDir, ".assets_v81")

# 2. incrementeaza-l (v81 -> v82)
sed -i 's/\.assets_v81/.assets_v82/' app/src/main/java/net/sys32/agent/MainActivity.kt

# 3. rebuild + install, apoi verifica PE DEVICE
$ADB shell run-as net.sys32.agent ls -la /data/data/net.sys32.agent/files/ | grep assets_v
#    -> .assets_v82  (trebuie sa fie NOU)
```

Ce face re-extragerea (util cand ceva „nu se actualizeaza"):
- salveaza `python/memory.md`, sterge `python/` si `pyhome/`, copiaza assets, **pune memoria la loc**
- sterge `pyhome/` intentionat → stdlib-ul (`Lib/`) si `site-packages/` se actualizeaza la fiecare extract

#### ★ CAPCANA 2 — `adb install -r` DEZACTIVEAZA accessibility

```bash
$ADB shell settings put secure enabled_accessibility_services net.sys32.agent/net.sys32.agent.AgentAccessibilityService
$ADB shell settings put secure accessibility_enabled 1
# verificare:
$ADB shell dumpsys accessibility | grep -A3 net.sys32.agent   # serviciul e enabled=true?
# sau din chat:  android(tool="ui", action="status")  -> {"ok":true,"enabled":true}
```
> ⚠️ Si `am force-stop` reseteaza `accessibility_enabled` la 0 → re-ruleaza cele 2 comenzi.

#### ★ CAPCANA 3 — `libdir` se schimba la fiecare reinstalare

Calea contine hash-ul instalarii: `/data/app/~~<hash>==/net.sys32.agent-<hash>==/lib/arm64`.
La fiecare install hash-ul e **altul** → `libdir.txt` de pe device devine invalid.

```bash
$ADB shell dumpsys package net.sys32.agent | grep codePath
#    -> codePath=/data/app/~~ABC==/net.sys32.agent-DEF==     (append /lib/arm64)
```

---

### OP.4 — DEBUG (7 niveluri, de la cel mai des la cel mai rar)

#### D1. LOGCAT — prima oprire mereu

```bash
ADB=/home/gab/android/platform-tools/adb
$ADB logcat -c                                                # curata INAINTE de repro
$ADB logcat --pid=$($ADB shell pidof -s net.sys32.agent)       # live, doar app-ul
$ADB logcat -d -t 300 | grep -iE 'net.sys32|AndroidRuntime'    # ultimele 300 linii
$ADB logcat -s AndroidRuntime:E                                # doar crash-uri Java/Kotlin
$ADB logcat -d | grep -iE 'DEBUG|tombstone|SIGSEGV' | tail -40 # crash NATIV (libpyexec.so)
```

> **Lectie din proiect:** *„Masoara, nu presupune. Logcat a rezolvat ce 3 incercari
> oarbe n-au reusit."* (sect. 12, lectia 1)

#### D2. TERMINALUL APP-ULUI = stdout-ul Python

Nu exista TTY de sistem. `MainActivity` citeste stdout-ul `libpyexec.so` linie cu
linie si il deseneaza in TextView. Deci **orice `print()` din `agent.py` apare pe ecran**.

Citire headless:
```bash
$ADB exec-out screencap -p > /home/gab/Desktop/agent/temp/shot.png   # apoi tool `look`
ls -l /home/gab/Desktop/agent/temp/shot.png     # ★ verifica >100KB, altfel frame gol/stale
```
Alternativa mai buna (fara OCR): scrie in `/sdcard/Download/Agent/` si citeste fisierul.
```bash
$ADB shell cat /sdcard/Download/Agent/context.json | head -c 2000
```

`uiautomator dump` pe ecranul agentului da **un singur nod multi-linie** cu `&#10;`:
```bash
$ADB shell uiautomator dump /data/local/tmp/x.xml    # ★ scrie explicit calea!
$ADB shell cat /data/local/tmp/x.xml                 # altfel citesti window_dump.xml gresit
# entitatile &#10; trebuie inlocuite cu \n
```

#### D3. PROCESUL PYTHON TRAIESTE?

```bash
$ADB shell ps -A | grep -E 'sys32|libpyexec'
$ADB shell dumpsys window | grep mCurrentFocus       # ce e in FATA (app? dialog? Settings?)
$ADB shell dumpsys power | grep -E 'mWakefulness=|net.sys32'   # Doze?
$ADB shell dumpsys deviceidle whitelist | grep sys32           # exclus de Doze?
```
> ⚠️ `ps -A | grep python3.14` **NU e fiabil** pe acest device (build-urile compilate
> nu apar cu numele asteptat) → nu-l folosi ca dovada de liveness. Foloseste screenshot-ul.

#### D4. FISIERE APP-PRIVATE (fara root, prin `run-as`)

```bash
$ADB shell run-as net.sys32.agent ls -la /data/data/net.sys32.agent/files/
$ADB shell run-as net.sys32.agent ls -la /data/data/net.sys32.agent/files/python/
$ADB exec-out run-as net.sys32.agent cat /data/data/net.sys32.agent/files/python/agent.py > /tmp/agent_on_device.py
cat /data/data/net.sys32.agent/files/python/key.txt     # NU trebuie sa apara in git!
```
> ⚠️ `exec-out run-as cat` poate da **0 bytes** pe Samsung (desi fisierul exista) →
> incearca alternativ `shell run-as ... head -50` sau `sed -n`.
> ⚠️ `run-as <pkg> cat` **pierde ultimul newline** → compara cu `md5sum` pe device, nu cu `cat`.

#### D5. STARE PERSISTENTA (memoria + contextul)

```bash
$ADB shell cat /sdcard/Download/Agent/context.json     # istoricul conversatiei
$ADB shell cat /sdcard/Download/Agent/memory.md        # lectiile invatate
```
> ⚠️ `context.json` **nu e mereu JSON valid** (poate avea „Extra data" dupa array) →
> parseaza cu `json.JSONDecoder().raw_decode(raw)` care intoarce `(obj, idx)`.

#### D6. INSPECTIA APK-ULUI

```bash
APK=/home/gab/Desktop/agent/workspace/app/net.sys32.agent/app/build/outputs/apk/debug/app-debug.apk
/home/gab/android/build-tools/35.0.1/aapt2 dump badging $APK 2>&1 | head -20   # ★ 2>&1: scrie pe stderr!
unzip -l $APK | grep 'assets/python/' | wc -l        # 928 fisiere Python (masurat)
unzip -l $APK | grep 'assets/python/agent.py'        # 151871 bytes (masurat)
unzip -l $APK | grep 'lib/arm64-v8a/'                # 6 .so-uri (libpyexec 4400, libpython3.14 5828792)
/home/gab/android/build-tools/35.0.1/dexdump -f $APK >/dev/null 2>&1 && echo dex-ok
```

#### D7. DEBUGGER KOTLIN (JDWP) — rar

```bash
./gradlew installDebug
$ADB shell am set-debug-app -w net.sys32.agent                  # asteapta debugger
$ADB forward tcp:8700 jdwp:$($ADB shell pidof net.sys32.agent)
# attach din IDE la localhost:8700
$ADB shell am clear-debug-app
```

---

### OP.5 — TABEL DIAGNOSTIC (simptom → comanda exacta)

| Simptom | Cauza probabila | Comanda / Fix |
|---------|-----------------|---------------|
| Modificarea din `assets/` „nu se vede" | marker `.assets_vNN` nebumpat | `grep -n assets_v MainActivity.kt` → `sed -i` bump → rebuild |
| Cifre/meniu vechi pe ecran dupa install | proces vechi inca ruleaza | `am force-stop net.sys32.agent` apoi `am start -n .../.MainActivity` |
| `INSTALL_FAILED_UPDATE_INCOMPATIBLE` | semnatura/versiune diferita | `$ADB uninstall net.sys32.agent` + install curat |
| `INSTALL_FAILED_NO_MATCHING_ABIS` | ABI lipsa | `unzip -l $APK \| grep lib/` (trebuie arm64-v8a) |
| `pm install` da Binder stacktrace, fara „Success" | APK nu a fost push-uit | `adb push` intai in `/data/local/tmp/`, apoi `pm install -r` de acolo |
| `libpyexec.so: No such file` | `libdir.txt` vechi (hash schimbat) | `dumpsys package ... \| grep codePath` → append `/lib/arm64` |
| `cannot locate symbol ...` | `LD_LIBRARY_PATH` gresit | pune `files/libs` **PRIMUL** in `LD_LIBRARY_PATH` |
| `ModuleNotFoundError` pe subpachet `_xxx` | AAPT2 ignora foldere cu `_` | livreaza ca `.py` simplu, nu ca director |
| Accessibility se dezactiveaza singur | `install -r` sau `force-stop` | cele 2 `settings put secure ...` |
| `ui` da `accessibility:false` | serviciul nu e activat | `dumpsys accessibility \| grep -A3 net.sys32` |
| `adbsh` timeout | adbd nu asculta pe port | `adb tcpip 5555` (o data, de pe laptop) |
| Dialog „Allow USB debugging" reapare | cheie noua / adbd resetat | apasa Allow (o data) |
| `adbsh` timed out dupa multe apeluri | rate-limit adbd | asteapta 10s / reporneste wireless debugging |
| Python nu porneste, `Fatal error: Failed to import encodings` | `PYTHONHOME` gresit | trebuie `files/pyhome`, NU `files/python` |
| Build esueaza cu `JAVA_HOME is not set` | shell nou fara export | exporta cele 4 variabile din OP.1 |
| `gradlew` da eroare de retea | deps nu-s in cache | `--offline` sau reconectare |
| Crash instant la pornire | `.so` lipsa/corupt | `unzip -l $APK \| grep lib/arm64-v8a/` |
| Agentul „uita" contextul | `context.json` invalid/corupt | `exec-out cat` + verificare `raw_decode` |
| Apel API `HTTPError` (tool_calls orfane) | mesaj `assistant` cu tool_calls nedublat de `tool` | vezi Etapa 36: repara perechile in `context.json` |

---

### OP.6 — BUILD PYTHON PENTRU ANDROID (o singura data / rar)

> ⚠️ **ATENTIE: sursele NU sunt pe disc acum.** Directorul
> `workspace/build/Python-3.14.7/` este in `.gitignore` (linia 2: `workspace/build/`)
> si **a fost sters de pe laptop** — `workspace/` contine doar `app/` si
> `android_bridge.py`. Rezultatul compilarii E in schimb in repo, in
> `app/src/main/jniLibs/` + `assets/python/Lib/`.
> Daca trebuie sa recompilezi CPython pentru Android, re-descarca sursele (vezi mai jos).

CPython 3.14 are **suport Android oficial** (`Android/android.py`) — NU trebuie
cross-toolchain manual; scriptul oficial face tot.

```bash
# 1. re-descarca sursele (odata, ~25 MB)
mkdir -p /home/gab/Desktop/agent/workspace/build && cd /home/gab/Desktop/agent/workspace/build
curl -LO https://www.python.org/ftp/python/3.14.7/Python-3.14.7.tgz
tar xf Python-3.14.7.tgz
cd Python-3.14.7

# 2. dependinte de HOST (o singura data; Debian trixie)
sudo apt-get install -y build-essential pkg-config autoconf libssl-dev zlib1g-dev \
     libffi-dev libsqlite3-dev libreadline-dev libbz2-dev liblzma-dev libgdbm-dev libncurses-dev

# 3. build
sudo apt-get install -y build-essential pkg-config autoconf libssl-dev zlib1g-dev \
     libffi-dev libsqlite3-dev libreadline-dev libbz2-dev liblzma-dev libgdbm-dev libncurses-dev
./android.py build aarch64-linux-android     # pentru TELEFON
./android.py build x86_64-linux-android      # pentru EMULATOR
```

Rezultat in `cross-build/<abi>-linux-android/prefix/`:
- `lib/python3.14/` → devine `assets/python/Lib/`
- `lib-dynload/*.so` → devine `assets/python/libdynload/<abi>/`
- `libpython3.14.so` → `jniLibs/<abi>/libpython3.14.so` (5.8 MB)
- `libpyexec.so` (4 KB, interpreterul executabil) → `jniLibs/<abi>/`
- modulele C: `_ssl`, `_hashlib`, `_sqlite3`, `zlib`, `_bz2`, `_lzma`, `_zstd`, `_ctypes`
  → devin `libssl_python.so`, `libcrypto_python.so`, `libsqlite3_python.so`
  ✔ absolut necesar: Android linker-ul rezolva `.so` dupa **soname** din caile de sistem
  → prefixarea cu `_python` evita conflictul cu vechile libs de sistem

**Lipsesc intentionat:** `_tkinter`, `readline`, `_curses`, `_gdbm`, `_uuid`.
**Verificare:** `$ADB shell run-as net.sys32.agent ... libpyexec.so -c "import ssl, sqlite3, zlib; print('ok')"`

---

### OP.7 — CHECKLIST PRE-COMMIT (ruleaza inainte sa zici „gata")

- [ ] `cd workspace/app && ./build_app.sh` → BUILD SUCCESSFUL + `Success`
- [ ] daca am atins `assets/` → `.assets_vNN` incrementat **si** verificat pe device
- [ ] accessibility reactivat **si** confirmat (`ui status` → `enabled:true`)
- [ ] `$ADB devices -l` arata device-ul
- [ ] `$ADB shell dumpsys package net.sys32.agent | grep lastUpdateTime` = timpul de acum
- [ ] am citit logcat-ul dupa pornire (fara excepții)
- [ ] `grep -rn 'key.txt\|AIza\|sk-' --include='*.py' --include='*.kt' .` → **nicio cheie** in repo
- [ ] `git status --short` → doar fisierele intentionate
- [ ] `py_compile` pe fisierele Python modificate (`python3 -m py_compile agent.py`)

---

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
  (workspace/build/Python-3.14.7/                sursele Python - STERSE, in .gitignore; vezi OP.6)
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

> **OPERATIUNI (build/install/debug/verificare): vezi sectiunea „🛠 OPERATIUNI"
> chiar inainte de „REZOLVAREA PROBLEMELOR FRECVENTE" — OP.1 pina la OP.7.**

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
- 10 tool-uri: android, ui, adbsh, python, bash, smart, read, look, bg, toolchain
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

> **Vezi si sectiunea OPERATIUNI (OP.1-OP.7) de mai sus — acolo e procedura completa.**
> `env.sh` NU mai exista (sters); variabilele sunt setate de `build_app.sh`.

    # build + install + start (recomandat, face tot)
    cd /home/gab/Desktop/agent/workspace/app
    ./build_app.sh

    # sau manual:
    export JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64
    export ANDROID_HOME=/home/gab/android
    export ANDROID_SDK_ROOT=/home/gab/android
    export PATH=$JAVA_HOME/bin:$ANDROID_HOME/platform-tools:$PATH
    cd net.sys32.agent
    ./gradlew assembleDebug --offline

    # instalare
    /home/gab/android/platform-tools/adb install -r app/build/outputs/apk/debug/app-debug.apk
    # daca semnatura difera:
    /home/gab/android/platform-tools/adb uninstall net.sys32.agent

    # Python pentru Android (o singura data / rar) - vezi OP.6
    # ATENTIE: sursele NU sunt pe disc (build/ e in .gitignore) - re-descarca-le intai
    cd /home/gab/Desktop/agent/workspace/build/Python-3.14.7
    ./android.py build aarch64-linux-android     # telefon
    ./android.py build x86_64-linux-android      # emulator

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


---

## Etapa 36 - FIX context invalid: `tool_calls` orfane (HTTPError de la API)

**Simptom:** dupa ce operatorul scrie in chat in timpul unui task, orice mesaj
nou da:
```
[API] HTTPError: An assistant message with 'tool_calls' must be followed by
tool messages responding to each 'tool_call_id'.
(insufficient tool messages following tool_calls message)
```
Agentul devine INUTILIZABIL pana la `/reset`.

**Cauza (reala, reprodusa):** bucla principala face
`M.append({"role":"user","content":q})` **fara sa verifice** starea istoricului.
Daca task-ul anterior s-a oprit cu un mesaj `assistant` care declara
`tool_calls` (ex. bootstrap pornit, apoi API error / intrerupere), acel mesaj
ramane **orfan**. Mesajul `user` nou se adauga IMEDIAT dupa el -> API-ul
respinge intreaga cerere (cerinta protocolului: fiecare `tool_call_id` trebuie
sa aiba un mesaj `tool` inainte de orice alt rol).

**Fix (2 locuri):**
1. **`sanitize_msgs(msgs)`** - funcție noua care parcurge istoricul si, pentru
   fiecare `assistant` cu `tool_calls`, verifica ca TOATE id-urile au raspuns
   `tool` imediat dupa; cele lipsa primesc un mesaj `tool` de completare
   („not executed - the run was interrupted"). Idempotenta.
2. Apelata **inainte de fiecare cerere API** (`ask()`) SI **inainte de a adauga
   un mesaj user nou** in bucla principala. Deci contextul nu mai poate rămâne
   invalid, indiferent ce face operatorul in timpul unui task.

**Verificat:** pe contextul real care producea eroarea, `sanitize_msgs` a
reparat 1 tool_call orfan; validarea arata toate perechile `tool_calls`/`tool`
in ordine corecta; taskul nou ruleaza fara HTTPError.

**Bonus:** contextul de pe dispozitiv a fost reparat in-place (nu a fost nevoie
de `/reset`), deci operatorul nu pierde istoricul.


---

## Etapa 37 - tool `bg`: gestionar de procese in fundal (rezolva "output amestecat")

**Simptom raportat de operator:** agentul lansa procese in fundal si apoi
"uita" de ele, isi amintea pe parcurs, avea output amestecat si comenzi
amestecate pe fundal de care nu era constient.

**Dovezi din conversatia reala (llama.cpp):**
- `[73]` "pornit pid=16405" (build lansat cu nohup)
- `[79]` "Log-ul e incomplet (output-ul e in buffer). Build-ul poate inca ruleaza"
- `[85]` "se pare ca VECHIUL build inca rula in fundal si scria in build.log (confuzie de output)"
- `[121]` "Output-ul e din log-ul VECHI de configurare"
- `[131]` "Output amestecat din nou, dar 8 procese clang active"

**Cauza rădăcină:** NU exista un registru al proceselor. Agentul lansa cu
`nohup ... &` prin adbsh, apoi citea fisiere de log FARA sa stie carui job
apartin si daca sunt actuale. Doua build-uri scriau in acelasi log.

**Solutia: tool nou `bg`** (gestionar persistent de joburi):
| Actiune | Ce face |
|---------|---------|
| `start cmd=... name=...` | lanseaza in fundal cu **log unic timestampat** + PID inregistrat |
| `status` | ce ruleaza ACUM (verifica `/proc/<pid>`, nu ghiceste) + durata + marimea log-ului |
| `log job=<id> lines=N` | ultimele N linii din log-ul ACELUI job (cu antet: cand a pornit, PID) |
| `kill job=<id>` | opreste job-ul + copiii |
| `list` | toate joburile (inclusiv terminate) |
| `clean` | sterge joburile terminate si log-urile lor |

Registru persistent: `/sdcard/Download/Agent/bg.json`; loguri: `/data/local/tmp/bg/<job>.log`.

**Regula in system prompt:** "orice comanda care poate lua >30s trece prin `bg`;
NICIODATA `nohup`/`&` brut; inainte de a porni o rulare noua a aceluiasi lucru,
verifica `bg status` si omoara resturile; citeste log-ul DOAR prin `bg log`,
care iti spune carui job apartine si cand a inceput."

**Verificat:** toate cele 6 actiuni testate (start/status/log/kill/list/clean);
statusul foloseste `/proc/<pid>/stat` (prinde si procesele zombie).

---

## Etapa 38 - OPTIMIZARI DE COST (citirea fisierelor mari + tool `read`)

**Problema (masurata):** output-ul unui tool call se taie la ~8000 chars (capetele raman, mijlocul dispare).
Marcajul promitea „NOT LOST: textul complet e in logs/...log", dar **logul de pe disc era plafonat la fel** →
mijlocul nu exista nicaieri. Citirea unui fisier de 92 KB a costat ~20 de pasi de re-citire.

**Cauza rădăcină:** `TOOLMAX=1800` (fereastra) era prea mic pentru o citire deliberata, iar `_store()` scria
logul fara sa verifice ca e complet.

**Fixuri:**
| # | Ce | Detaliu |
|---|----|---------|
| 1 | `CHUNK` configurabil | `AGENT_CHUNK` (default 7000) ridica plafonul ferestrei; `0` = comportamentul vechi |
| 2 | `_budget()` | alege plafonul corect per apel |
| 3 | `_cut()` spune adevarul | scrie `NOT LOST` **doar** daca logul e verificat complet; altfel `LOST - RE-RUN` |
| 4 | `_store()` verifica | `os.path.getsize(p) == len(o.encode())`, nu presupune |
| 5 | **tool `read`** | citire paginata cu **buget GARANTAT** (`path/offset/limit/budget/grep`) + footer `NEXT: offset=N` |
| 6 | avertisment preventiv | la 90% din buget, **o singura data per task** |

**Metoda de lucru pentru fisiere mari (in system prompt):**
```
(1) read cu grep = regex   -> harta fisierului cu numere de linie, in UN apel
(2) read cu offset/limit   -> doar sectiunea de interes
```

**MASURAT:** citirea `readme.md` (92.621 chars): **18 pasi -> 2 pasi**, input **4.82M -> 0.418M chars (-91%)**.

---

## Etapa 39 - OPTIMIZARI DE COST (batching + densitate)

**Principiul descoperit (masurat):** API-ul DeepSeek e **stateless** → la fiecare cerere se retrimite TOT
contextul. O sesiune de 348 mesaje = **64M chars input** (~16M tokeni), adica **187x** contextul final.
Deci costul real nu sunt pasii, ci **numarul de cereri x masa contextului**.

**Componenta contextului (masurata):** 53.2% output-uri de tool, **36.3% codul trimis de agent**,
10.2% text assistant. Deci 89.5% din context e produs de agent, nu de operator.

| # | Optimizare | Efect |
|---|-----------|-------|
| 1 | **tool `multi`** | 2-6 operatiuni independente intr-UN apel; cap 6 ops, plafon 2000/entry, plafon 7000 total; **eroarea unei operatiuni NU opreste restul** |
| 2 | regula **BATCH** in prompt | „daca pasul B nu citeste ce a scris pasul A, sunt in ACELASI `multi`"; NU batchuieste dependent/greu/poate-atarna |
| 3 | regula **CODE DENSITY** | codul din tool_call arguments se retrimite la fiecare cerere → cod minim, fara comentarii decorative |
| 4 | regula **DENSITY RULE** | etichete de ~60-90 chars, verb + obiect |
| 5 | **cache HIT** afisat | per task in footer + in `/ctx` (din `usage.prompt_cache_hit_tokens`) |

> **TRAP:** `print()` in bucle NU economiseste tokeni — scrie pe stdout, nu intra in context.
> Doar `m['content']` si `tool_calls[].arguments` se retrimit.

**MASURAT pe task-uri reale:** 13 operatiuni in 5 apeluri (-62% apeluri); pe 10 op. `-82%` input,
pe 50 op. `-97%`.

---

## Etapa 40 - FEREASTRA REALA + COMPACTARE DEZACTIVATA

**Avertisment FALS (reparat):** `CTXWINDOW` era hardcodat la `128000`, dar modelul `deepseek-flash`
(DeepSeek-V4.1-Flash) are **`context_window=1048576` (1M)**. Un context de 160.4k tokeni raporta
**125%** si declansa alerta rosie desi era la **15%**.

**Sursa de adevar = API-ul:**
```bash
curl -s https://api.deepseek.com/models -H "Authorization: Bearer $KEY"
#   -> deepseek-flash: context_window=1048576, max_output_tokens=393216
```

**Fixuri:**
- `CTXWINDOW=1048576` (verificat in API, nu ghicit)
- `ctx_check_window()` la startup: intreaba API-ul si **corecteaza singur** constanta daca diferă;
  daca reteaua cade, pastreaza constanta locala si NU blocheaza startup-ul
- `ctx_warn()`: avertisment **ROSU** la **90%** din fereastra, o singura data per trecere,
  re-armat sub 80%; **NU comprima si NU sterge nimic**

**COMPACTARE DEZACTIVATA (decizie operator):** `CTXBUDGET=0` + `compact_history()` devine **no-op**
(chiar si cu `force=True` de la `/compact`). Motivul: comprimarea inlocuia output-urile grele cu
pointeri catre `archive/`, deci informatia ramanea pe disc dar **dispareа din context**.
Operatorul vrea memoria inserata la startup sa rămâna **INTREAGA pana la `/reset`**.

**Verificat:** dupa 50 de mesaje x 8000 chars, **0 pointeri noi**, memoria intacta.

---

## Etapa 41 - TESTUL DECISIV (audit de securitate cu uid 2000)

**Task (fara indicii tehnice):** „audit de securitate complet, folosind **intensiv adbsh cu uid 2000**:
permisiuni periculoase, servicii in fundal, conexiuni de retea, fisiere accesibile doar ca shell,
starea SELinux/verity/root. Verdict cu riscuri concrete."

**REZULTAT:** audit de **6500 chars**, **23 operatiuni in 12 apeluri API**
(7 `adbsh` uid=2000 + 5 `multi` + 1 python); `multi` a grupat 15 operatiuni.

**Comenzi privilegiate rulate cu uid 2000:** `dumpsys cpuinfo`, `appops`, `/proc/net/tcp`
(cu conversie hex `$((16#hex))`), `getenforce`, `getprop` verity/boot, `ls /dev/socket`, `id`.

**Economie masurata:** **-45% apeluri**, **-59% input** (~428k tokeni).

**VERIFICARE INDEPENDENTA a dovezilor** (toate confirmate):
| Afirmatie agent | Verificare | Rezultat |
|-----------------|-----------|----------|
| SELinux Enforcing | `getenforce` | ✅ Enforcing |
| `su` absent | `ls /system/bin/su` | ✅ ABSENT |
| Bootloader locked | `getprop ro.boot.flash.locked` | ✅ 1 |
| Verity enforcing | `getprop ro.boot.veritymode` | ✅ enforcing |
| Agentul are 3 permisiuni | `dumpsys package` | ✅ granted=true, USER_SET |

**Riscuri reale identificate de agent:**
1. **(ridicat)** `net.sys32.agent` are camera+microfon+locatie SI e debuggable
2. **(mediu)** `/data/local/tmp` e `0777` world-writable
3. **(scazut)** 469 pachete instalate, suprafata mare de atac

**Artifact:** `temp/audit-securitate-SM-A366B.md`

---

## Etapa 42 - SINCRONIZARE `agent.py` (Android) cu optimizarile

Toate optimizarile din etapele 38-41 sunt in **`assets/python/agent.py`** (creierul agentului Android),
adaptate pentru particularitatile telefonului (NU copiate 1:1):

| Desktop | Android |
|---------|---------|
| `bash(cmd, cwd)` — 2 argumente | `run_bash_tool(cmd)` — 1 argument |
| `py(code, cwd)` | `run_tool(code)` |
| tool-uri standard | + `run_android_tool`, `run_adbsh_tool`, `run_toolchain_tool`, `bg_tool` |

**Build:** `./build_app.sh` → BUILD SUCCESSFUL, instally, `.assets_v83` extras pe device.
Optimizarile confirmate **in APK** (citite din zip).

> **⚠️ CAPCANA:** markerul `.assets_vNN` din `MainActivity.kt` trebuie INCREMENTAT la fiecare
> modificare de assets, altfel app-ul foloseste copia VECHE de pe device.
---

## Etapa 43 - FIX BUG DE BUFFER `adbsh` (output cu un apel in urma)

**Simptom (raportat de agent dupa compilarea numpy):** tool-ul `adbsh` returna output-ul comenzii
**PRECEDENTE**, nu al celei curente. Lag fix de exact o iteratie, reprodus de **13 ori consecutiv**.
Comportament inselator: output-ul era intotdeauna **complet si plauzibil** — doar din alt apel.
Tools neafectate: `multi`, `bash`, `python`, `bg`. Doar `adbsh`.

**Raport complet:** `temp/raport_buffer_adbsh.md` (agentul l-a scris singur, cu transcript de reproduceri).

### Cauza reala (NU ce presupunea raportul)

Protocolul ADB are **doua** campuri de id in fiecare pachet. Verificat cu pachete brute pe device:
```
Noi:  A_OPEN (a0=id_NOSTRU=1,  a1=0)              <- cerem o sesiune
adbd: A_OKAY (a0=id_LOR=1850,  a1=id_NOSTRU=1)    <- id-ul NOSTRU e in a1!
adbd: A_WRTE (a0=id_LOR=1850,  a1=id_NOSTRU=1)
adbd: A_CLSE (a0=id_LOR=1850,  a1=id_NOSTRU=1)
```

Codul vechi filtra `if a0 != 0:` — adica **accepta pachete din ORICE sesiune**. Resturile ramase
in socket de la comanda anterioara (drenare incompleta) se lipeau la raspunsul curent → **lag de
exact un apel**. Raportul a dat 3 ipoteze (asincronie sesiune / ring buffer / reutilizare FD);
niciuna nu era corecta — era **campul de id gresit**.

> **⚠️ TRAP — capcana proprie:** prima incercare de fix a fost `if a0 != lid:` (logica inversa).
> Rezultat: TOATE comenzile dadeau timeout (14.58s pentru un simplu `echo`), pentru ca filtrarea
> respingea tot. Diagnosticul care a salvat: dump-ul pachetelor brute, care arata `a0=1850 a1=1`.

### Fixurile aplicate (3)

| # | Fix | Detaliu |
|---|-----|---------|
| 1 | **filtrare pe `a1`** (id-ul nostru) | `if c in (A_OKAY,A_WRTE,A_CLSE) and a1 != lid: continue` — pachetele straine sunt DROPATE, niciodata adaugate la raspuns |
| 2 | **`_drain()` sigur** | `select()` + citiri partiale tolerate (24-byte header poate veni fragmentat); prima versiune folosea `_recv(0.2)` si ardea tot timeout-ul |
| 3 | **`A_OKAY` cu id-uri inversate** | `self._send(A_OKAY, a1, a0)` — protocol ADB corect |

Plus in `agent.py`: **integrity guard** — fiecare comanda `adbsh` primeste un marker unic
(`echo __MK<ts>__; <cmd>`); daca markerul lipseste din raspuns, sesiunea e desincronizata ->
drain + re-rulare O DATA, apoi raportare onesta. Markerul e eliminat din output.

### VERIFICAT

| Test | Rezultat |
|------|----------|
| `echo` simplu (durata) | **0.58s** (era 14.58s cu fix-ul gresit) |
| 6 comenzi consecutive cu markere unice (manual, pe device) | **6/6 CORECTE** |
| Acelasi test END-TO-END prin agent | **6/6 CORECTE**, zero lag |

```
apel 1: stiut=MK1_71021 primit='MK1_71021\npayload_1' -> OK
apel 2: stiut=MK2_71591 primit='MK2_71591\npayload_2' -> OK
...
REZULTAT: 6/6 corecte
```

**Lectia:** cand un tool comunica prin protocol binar, **nu presupune semantica campurilor** —
dumpuieste pachetele brute si citeste-le. Raportul agentului a diagnosticat perfect COMPORTAMENTUL
(13 reproduceri, tools neafectate, output plauzibil), dar cauza tehnica cerea un nivel mai jos.
---

## Etapa 44 - TOOLCHAIN: PERSPECTIVA dubla + disciplina de terminare (din raportul numpy)

**Context:** agentul a compilat numpy 2.3.5 de la 0 (SUCCES) dar a lovit o serie de probleme pe care
si le-a documentat singur in `workspace/npy/RAPORT_numpy_android.md`. Raportul e exemplar pentru ca
pune PE PRIMUL LOC eroarea proprie, nu pe cea tehnica.

### Cea mai grava eroare (auto-diagnosticata de agent)

> *"Am confundat «un pas intermediar a reusit» cu «task-ul e gata». Criteriul de terminare era
> `import numpy` functioneaza; eu l-am inlocuit mintal cu «bootstrap a zis OK»."*

Costul: **un tur pierdut complet** - agentul a livrat un mesaj de "progres" in loc de rezultatul cerut,
iar operatorul a trebuit sa-l intrebe de ce s-a oprit.

### Eroarea tehnica: status VERDE cu prefix GOL

`toolchain status` raporta `clang=true, make=true, compile_test=true` in timp ce
`/data/local/tmp/tpm/usr/bin` avea **0 fisiere** din perspectiva app-ului.

**Cauza:** toolchain-ul e instalat de **uid 2000 (shell)** si e consumat de **app (~10300)**.
`check()` verifica doar prin shell - deci "totul OK" insemna "OK pentru ALT user decat cel care cere".

### Optimizarile aplicate

| # | Ce | Unde |
|---|----|------|
| **A1** | `check()` verifica **AMBELE perspective**: `app_can_read_prefix`, `app_can_exec_python` + hint explicit ca "app nu poate executa" e NORMAL, nu defect | toolchain.py |
| **A2** | `chmod -R a+rX` automat la finalul bootstrap-ului (prefixul era `drwxrws---`, app-ul nu putea nici citi) | toolchain.py |
| **A3** | marker de versiune `$ROOT/.tc_version` (fara el nu stim CE e instalat) | toolchain.py |
| **A3b** | `python-ensurepip-wheels` in PKGS (in repo Termux `python-pip` NU exista) | toolchain.py |
| **A4** | `pip_install` instaleaza intai **build deps** (meson, meson-python, Cython, ninja) si foloseste `--no-build-isolation` DOAR daca deps sunt deja in prefix (verificat, nu presupus) | agent.py |
| **A5** | timp pe faze: `[phases] total Xs` la fiecare pip_install | agent.py |
| **A6** | **`action=doctor`** - health check per-uid: poate SHELL-ul sa compileze? poate APP-ul sa citeasca/execute? + verdict | toolchain.py + agent.py |

### Reguli noi in system prompt (recomandarea C din raport)

```
STOPPING CRITERION: before you call a task done, state WHAT the finish line is
(e.g. `python -c "import numpy"` exits 0). The task is NOT done because a tool
printed OK - it is done when the FINAL verification returns the result asked for.
After EVERY step that reports success, check the EFFECT on disk, not the status.
NEVER end a turn with "I did X, next comes Y" when the operator asked for Y.

SHELL-OWNED RESOURCES: the toolchain belongs to uid 2000. As an app you can READ
its files but CANNOT execute them - run through `adbsh`/`/run_su`.
A `status` that looks green from the shell perspective does not mean YOU can use it.
```

### COMPLETARE: recomandarile B (flux de build) - toate acoperite

Primele doua erau deja implementate; restul au fost adaugate acum.

| # | Propunere | Implementare |
|---|-----------|--------------|
| **B1** | build in /data/local/tmp, nu pe FUSE | deja: `TMPDIR=/data/local/tmp/tmp` in `env_vars()` + `_prepare_dirs()` |
| **B2** | cache de wheel persistent | deja: `PIP_CACHE_DIR=$HOME/.cache/pip` |
| **B3** | OpenBLAS | `NPY_BLAS_ORDER` / `NPY_LAPACK_ORDER` in env (opt-in `AGENT_BLAS=openblas`); fara el rămâne BLAS-ul intern |
| **B4** | `-O3 -mcpu=native` / SIMD | `_simd_flags()` adauga `-march=armv8.2-a+dotprod+fp16` + `-O3` in CFLAGS/CXXFLAGS, controlabil cu `AGENT_SIMD=0` |
| **B5** | CCACHE | `ccache` in PKGS + wrapperele clang din `/data/local/tmp/wrap` il folosesc cand exista (fallback transparent) |
| **B6** | LTO off | corect lasat off (nimic de facut) |

### TREI bug-uri gasite la integrare (pe care raportul nu le putea sti)

| Bug | Simptom | Fix |
|-----|---------|-----|
| `doctor` lipsea din **enum-ul schemei** | agentul: *"actiune necunoscuta: doctor"* desi handler-ul exista | adaugat in enum + descriere |
| `doctor` lipsea din **lista inline a `_run`** | `_run` are actiunile hardcodate pentru exec inline; `doctor` cadea pe branch-ul "necunoscut" | adaugat `elif _act == "doctor"` |
| `shell_ls_count` folosea `len()` pe string | raporta **3** binare in loc de **239** | `int()` + curatare artefacte protocol |

> **LECTIE DE INTEGRARE:** cand adaugi o actiune intr-un tool care are (a) schema cu `enum`,
> (b) dispatcher in agent.py, (c) lista inline in `_run`, (d) CLI in modul - trebuie atinse TOATE
> patru locuri. Lipsa unuia produce "actiune necunoscuta" desi codul pare complet.

### VERIFICAT

```
toolchain action=doctor ->
  shell_ls_count: 239        shell_clang: true    shell_python: true   shell_pip: true
  app_can_read: true         app_can_exec: false
  prefix_mode: 2775 shell:shell                   world_readable: true
  verdict: OK - shell builds, app can read (execute via adbsh, as designed)
```

> **Nota despre iteratie:** instalarea unui APK nou NU reincarca `agent.py` in procesul Python deja
> pornit (agentul ruleaza bucla cu fisierul incarcat la startup). Dupa orice schimbare de assets:
> `am force-stop` + `am start` + **reactivare accessibility**.
---

## Etapa 45 - FIX CRITIC `__main__` + MONITOR DE STATUS (0 tokeni)

### BUG-ul care bloca TOTUL (ore de "timeout" aparent)

`agent.py` rula `refresh()` si bucla `input()` **la nivel de modul**, fara `if __name__ == "__main__"`.
`py()` lansa `[sys.executable, "-c", cod]`, iar pe Android `sys.executable` = `libpyexec.so` →
interpretorul **RE-INCARCA agent.py** → reintra in bucla `input()` → **atarna infinit**.

**Efect:** ORICE tool `python`/`run_tool` parea blocat; agentul "statea intepenit dupa task".

**Fix:** un singur `if __name__ == "__main__":` inainte de blocul de startup.
Acelasi fix aplicat si in `agent-original.py` (agentul Linux):
`import` = **0.08s** (era blocat infinit).

### OPTIMIZARI DE TIMP (referatul: "fazele de fix au fost mai lungi decat build-ul")

| Operatie | Inainte | Acum | Cauza |
|----------|---------|------|-------|
| `_patch_runpath` | **13+ min** | **0.3s** | `readelf -d` per fisier (~1000 spawn-uri) → o singura trecere Python |
| `_fix_libcxx_needed` | minute | **0.1s** | la fel |
| `check()` runpath | ~30s | **<1s** | la fel |
| `setexec.py` | **nu rula deloc** | ruleaza | `python3` NU exista pe Android → `python3.14` |
| `_fix_ninja` | copie (distrugea originalul) | wrapper script | referatul: "nu mai e recuperabil" |
| `_fix_meson_exe` | lipsea | wrapper `python3.14 -m mesonbuild.mesonmain` | meson vine ca MODUL |
| preflight | `cmake_build=false` | **true** | `PREFIX` exportat + filtrare linii `[adb]` |

`adb_client`: incearca **AUTH_SIGNATURE primul** (cheia e in `user_keys` → CNXN imediat),
`RSAPUBLICKEY` doar fallback. Ordinea inversa producea timeout la fiecare comanda.

### MONITOR DE STATUS: `/watch [sec]` — 0 TOKENI

**Intrebarea operatorului:** "poti adauga un check la fiecare minut? devine costisitor?"

**Masurat:** prin API, 30 de check-uri (build de 30 min) = **~255.000 tokeni input**, fiindca
fiecare check retrimite TOT contextul. Prin monitor local: **0 tokeni, 0 cereri API**.

**Cum functioneaza:** un thread LOCAL care citeste registrul joburilor de fundal si verifica
`/proc/<pid>/stat` (nu ghiceste), apoi scrie o linie pe ECRAN (stdout). Nu atinge contextul.

```
/watch        -> porneste (60s)
/watch 30     -> la 30 de secunde
/watch        -> opreste
AGENT_WATCH=1 -> pornit automat la startup
```

Exista in AMBELE agenti (Android si Linux). `_watch_loop` scrie DOAR cat ruleaza un job
(silentios cand nu e nimic de raportat) si doar cand linia se schimba (fara zgomot).

### REGULI NOI IN SYSTEM PROMPT

```
STOPPING CRITERION: task-ul NU e gata pentru ca un tool a afisat OK - e gata cand
VERIFICAREA FINALA returneaza rezultatul cerut. Dupa fiecare pas, verifica EFECTUL
pe disc, nu mesajul de status. Niciodata sa nu inchei un tur cu "am facut X, urmeaza Y".

TIMING: tool-urile care apeleaza shell intorc in milisecunde aici, deci un pas care
ia secunde inseamna ca ASTEPTA (timeout, lock, retea) - investigheaza cauza in loc
sa astepti. Nu dormi intre pasi: fiecare pas asteapta exact cat are nevoie tool-ul.
```

### REZULTAT

numpy 2.5.3 compilat nativ pe telefon (import OK, matmul/svd/fft/random functionale);
wheel `numpy-2.5.3-cp314-cp314-android_24_arm64_v8a.whl` (7.3 MB).
