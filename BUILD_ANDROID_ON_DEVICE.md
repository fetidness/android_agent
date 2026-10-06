# BUILD ANDROID PE DEVICE — Ghid complet end-to-end

> **Ce este acesta:** rețeta completă, dovedită E2E, pentru a compila aplicații Android
> (inclusiv cele cu cod nativ C/C++/NDK, Hilt, Room, kapt, Compose, Firebase) **direct pe
> telefon, fără PC, fără Gradle pe PC, fără Android Studio.**
>
> Dovedit pe: **Samsung SM-A366B** (Android 16, arm64-v8a), compilând **VocisHD**
> (`net.sys32.vocis`, 93 fișiere Kotlin + codec Opus C cu 149 fișiere) → `assembleDebug`
> COMPLET, APK 38 MB, instalat + rulat. 58 task-uri Android.
>
> Autor: agentul autonom (sesiunea 5 oct 2026). Toate cifrele sunt MĂSURATE pe device.

---

## 0. DE CE E GREU (esența problemei)

Pe Android, o aplicație (uid `untrusted_app`, SELinux `untrusted_app`) **NU poate executa
binarare ELF arbitrare**. Concret:

- Binararele din `filesDir` (`/data/data/<pkg>/files/...`) → **Permission denied** la exec.
- Binararele din `/data/local/tmp` → executabile doar de shell (uid 2000), nu de app.
- **Singurul loc de unde app-ul poate executa** = `<APK>/lib/arm64/` (`lib*_exec.so`),
  directorul `nativeLibraryDir`.

În plus, Android blochează **execuția în lanț** (un `lib*_exec.so` care `execv` altul →
segfault) și **dlopen-ul libs nespecificate** în namespace (chiar cu `rpath=$ORIGIN`,
un executabil din `lib/arm64` nu-și încarcă frații din același dir — namespace policy).

De aceea unelte ca `java`, `aapt2`, `cmake` (care nativ ar trebui doar executate) trebuie
**împachetate ca `lib*_exec.so` într-un APK-gazdă**, iar dependențele lor puse în locații
care SUNT în `LD_LIBRARY_PATH`-ul procesului care le lansează.

---

## 1. ARHITECTURA SOLUȚIEI

### 1.1 APK-gazdă (`net.sys32.javahost`)

Un APK mic (~11 MB) care conține binararele JDK + aapt2 ambalate ca lib-uri, plus ~120 libs
de suport. E gazda de executabile. NU are legătură cu aplicația compilată.

```
net.sys32.javahost/
  lib/arm64-v8a/
    libjava_exec.so        # jdk/bin/java (launcher JLI, ~6 KB)
    libjlink_exec.so       # jdk/bin/jlink
    libjmod_exec.so        # jdk/bin/jmod
    libjimage_exec.so      # jdk/bin/jimage
    libjavac_exec.so       # jdk/bin/javac
    libjar_exec.so         # jdk/bin/jar
    libkeytool_exec.so     # jdk/bin/keytool
    libjarsigner_exec.so   # jdk/bin/jarsigner
    libaapt2_exec.so       # aapt2 (Termux 2.20, aarch64)
    lib*.so                # ~120 libs: libfmt, libprotobuf, libabsl_*, libc++_shared
```

`android:extractNativeLibs="true"` în manifest este OBLIGATORIU.

### 1.2 Stack-ul de build (în `filesDir`)

Totul rulează ca APP (uid ~10322), deci căile trebuie să fie în `filesDir` (accesibil).
`filesDir` = `/data/data/<gazda>/files/`.

```
<filesDir>/build/
  jdk/          # JAVA_HOME: bin/java..jarsigner = SYMLINK la javahost lib*_exec.so
                #           lib/, lib/server/ = modulele JDK (INCARCATE, nu executate)
  gradle/       # Gradle 9.8 (Termux) + libnative-platform.so extras din jar
  gradlehome/   # GRADLE_USER_HOME (cache deps, transforms, daemon)
  sdk/          # SDK Android minimal
    platforms/android-36/     # COMPLET (11311 fisiere + package.xml)
    build-tools/36.0.0/       # aapt2 = symlink la javahost; aidl/zipalign/etc.
    cmake/3.22.1/bin/         # cmake = symlink la toolchain-ul nostru aarch64
    licenses/                 # android-sdk-license (hash-uri)
    platform-tools/           # instalat de AGP singur
  toolchain/    # toolchain-ul nostru (clang 21, sysroot, cmake, ninja, deps/lib)
    ndk/                            # FAKE NDK (symlink-uri)
    deps/lib/                       # libs absl/protobuf/fmt + glibc-shim (libm.so.6 etc.)
  project/      # proiectul copiat (sau symlink)
  tmp/          # TMPDIR + java.io.tmpdir
  .android/debug.keystore           # keystore debug (generat cu keytool)
```

---

## 2. UNELTELE (de unde se iau)

Pachete **Termux aarch64** (`https://packages.termux.dev/apt/termux-main/pool/main/...`),
fiecare `.deb` = arhivă `ar` → `data.tar.xz` (se extrage cu python: parsezi `ar` manual,
`tarfile`+`lzma`). Prefix intern: `data/data/com.termux/files/usr`.

| Unealtă | Pachet | Mărime |
|---|---|---|
| JDK 21 | `openjdk-21_21.0.12_aarch64.deb` | 106 MB |
| Gradle 9.8 | `gradle_1:9.8.0_all.deb` | 149 MB |
| aapt2 | `aapt2_16.0.0.4-2_aarch64.deb` | 1 MB |
| d8 (dexer) | `d8_37.0.0_all.deb` | 14.7 MB |
| apksigner | `apksigner_37.0.0_all.deb` | 1.1 MB |
| kotlinc 2.4.20 | `kotlin_2.4.20_all.deb` | 88 MB |
| libs C++ | `libc++`, `fmt`, `libprotobuf`, `abseil-cpp`, `libexpat`, `libpng`, `libzopfli`, `zlib` | ~3.6 MB |
| libs JDK | `libandroid-shmem`, `libandroid-spawn`, `libiconv`, `libjpeg-turbo`, `littlecms`, `alsa-plugins` | ~1.2 MB |

De asemenea:
- **android.jar API 36**: `https://dl.google.com/android/repository/platform-36_r01.zip`
  (63 MB → `android-36/android.jar` 27.7 MB + platforma completă). Google îl dă DIRECT.
- **build-tools**: `https://dl.google.com/android/repository/build-tools_r36_linux.zip` (63 MB).
- **androidx + AGP + Kotlin plugins**: se descarcă automat de Gradle din `google()`/`mavenCentral()`.

**NDK-ul oficial Google e x86_64 → INUTIL pe ARM.** Se folosește toolchain-ul propriu + fake-NDK.

---

## 3. PAȘII COMPLEȚI (end-to-end)

### Pasul 0 — Kernel de executabile: Java în APK

1. Ia `jdk/bin/java` (+ jlink/jmod/jimage/javac/jar/keytool/jarsigner), copiază-le ca
   `lib<name>_exec.so` în `javahost/lib/arm64-v8a/`.
2. Adaugă libs de suport (din pachetele Termux: libfmt, libprotobuf, libabsl_*, libc++_shared).
3. Build javahost (vezi §4 — cu `aapt2` + `kotlinc` + `d8` + `apksigner`, sau cu Gradle dacă merge).
4. Instalează: `pm install -r --bypass-low-target-sdk-block javahost.apk`.
5. Creează `JAVA_HOME` în `filesDir`: `bin/java` = symlink la
   `<apk>/lib/arm64/libjava_exec.so`, la fel jlink/jmod/... . Modulele JDK (`lib/`, `lib/server/`)
   rămân în `filesDir` (sunt `dlopen`-uite, nu executate).

### Pasul 1 — Gradle

1. Extrage pachetul Termux `gradle`.
2. `libnative-platform.so` lipsește din pachet → extrage-l din
   `native-platform-linux-aarch64-0.22-milestone-29.jar` → pune-l în `gradle/lib/`.
3. Rulează cu:
   `java -Djava.library.path=<gradle>/lib -cp <gradle>/lib/gradle-launcher-9.8.0.jar org.gradle.launcher.GradleMain ...`

### Pasul 2 — SDK Android minimal

1. Extrage `platform-36_r01.zip` → `sdk/platforms/android-36/` (COMPLET, 11311 fișiere).
2. Adaugă `package.xml` valid în platformă (fără el: „Failed to find target android-36").
3. Extrage `build-tools_r36_linux.zip` → `sdk/build-tools/36.0.0/`.
4. `sdk/licenses/android-sdk-license` (hash-uri) + `android-sdk-preview-license`.
5. `local.properties`: `sdk.dir=<filesDir>/sdk`.
6. AGP își instalează singur `platform-tools` dacă lipsesc (SDK-ul trebuie să fie SCRIIBIL).

### Pasul 3 — Fake NDK

`toolchain/ndk/` cu structură standard:
```
ndk/
  source.properties            # Pkg.Revision = 27.1.12297006
  build/cmake/android.toolchain.cmake   # toolchain CMake (vezi toolchain-ul nostru)
  toolchains/llvm/prebuilt/linux-x86_64/
    bin/{clang,clang++,ld.lld,ld,ar,ranlib,strip,nm,
         llvm-strip,llvm-ar,llvm-ranlib,llvm-nm}  # symlink la toolchain-ul nostru
    sysroot -> <toolchain>/sysroot
```
În `build.gradle.kts`: `android { ndkPath = "<filesDir>/toolchain/ndk" }`.

### Pasul 4 — cmake/aapt2 aarch64 (AGP își descarcă x86_64)

- `sdk/cmake/3.22.1/bin/{cmake,ninja}` → symlink la `toolchain/bin/{cmake,ninja}` (aarch64).
- `sdk/build-tools/36.0.0/aapt2` → symlink la `javahost/libaapt2_exec.so`.
- **aapt2 din Maven** (transform-uri AAR): AGP îl descarcă la
  `gradlehome/caches/9.8.0/transforms/<hash>/transformed/aapt2-9.0.1-<rev>-linux/aapt2`.
  **Înlocuiește-l cu symlink** la `javahost/libaapt2_exec.so`.
- `gradle.properties`: `android.aapt2FromMavenOverride=<filesDir>/aapt2bin/aapt2`
  (symlink FĂRĂ `.so` — AGP respinge `*.so` ca „not an AAPT2 executable").

### Pasul 5 — Libs pentru aapt2 în LD_LIBRARY_PATH-ul daemonului

Daemonul Gradle are un `LD_LIBRARY_PATH` **propriu** (nu moștenește env-ul clientului!),
care include `<toolchain>/deps/lib`. Pune acolo libs aapt2 (libfmt, libprotobuf,
toate libabsl_*, libc++_shared). Verifică: `cat /proc/<daemon_pid>/environ`.

Pentru sqlite/glibc shim (vezi §6): `libm.so.6`, `libpthread.so.0`, `libdl.so.2`,
`libc.so.6` → symlink la `/system/lib64/lib*.so` (tot în `deps/lib`).

### Pasul 6 — kapt + SQLite (Room)

`sqlite-jdbc 3.41.2.2` (cerut de Room) **NU are natives Android** (varianta
`Linux-Android/aarch64` e 0 bytes) → SQLite detectează OS='Linux' și ia varianta glibc
(cere `libm.so.6`/`libpthread.so.0`) → `ExceptionInInitializerError`.

**Fix:** descarcă **`sqlite-jdbc 3.46.0.0`** (are `Linux-Android/aarch64/libsqlitejdbc.so`
real, 1.18 MB, depinde doar de libs de system: libm/libc/libandroid/libdl/liblog). Pune-l
într-un DIRECTOR și în `gradle.properties`:
```
org.gradle.jvmargs=... -Dorg.sqlite.lib.path=<dir cu libsqlitejdbc.so> -Dorg.sqlite.tmpdir=<tmp>
```
`org.sqlite.lib.path` trebuie să fie **DIRECTOR** (nu fișierul .so).

### Pasul 7 — Java/Gradle flags (obligatorii)

```
-Duser.home=<filesDir>                       # build.gradle caută ~/.android/debug.keystore
-Djdk.lang.Process.launchMechanism=VFORK     # jspawnhelper nu rulează → VFORK
-Djava.io.tmpdir=<filesDir>/tmp              # altfel java.io.tmpdir = cale Termux inexistentă
-Djava.library.path=<tmp>:<gradle>/lib
```
Plus în mediu: `JAVA_HOME`, `LD_LIBRARY_PATH` (tlib:tmp:gradle/lib:javahost_lib:jdk/lib),
`JAVA_TOOL_OPTIONS` cu VFORK+tmpdir+user.home (propagă la JVM-urile copil), `ANDROID_HOME`,
`GRADLE_USER_HOME`, `TMPDIR`.

### Pasul 8 — Keystore debug

`build.gradle` caută `$user.home/.android/debug.keystore`. Generează-l:
`keytool -genkeypair -keystore <filesDir>/.android/debug.keystore -alias androiddebugkey
-storepass android -keypass android -keyalg RSA -keysize 2048 -validity 10000`.

### Pasul 9 — google-services.json (proiecte Firebase)

Repo-urile îl exclud (gitignore). Creează un DUMMY valid în `app/google-services.json`
(structura corectă, valori fake) — pluginul doar îl validează.

### Pasul 10 — Build

```
cd <project>
java -Duser.home=<filesDir> -Djdk.lang.Process.launchMechanism=VFORK \
     -Djava.io.tmpdir=<filesDir>/tmp -Djava.library.path=<tmp>:<gradle>/lib \
     -cp <gradle>/lib/gradle-launcher-9.8.0.jar \
     org.gradle.launcher.GradleMain assembleDebug
```
Rulează ca APP (python subprocess / bg), NU prin adbsh.

---

## 4. CAPCANE (fiecare = un eșec real, cu fix)

| Simptom | Cauză | Fix |
|---|---|---|
| `Permission denied` la exec binar | SELinux: filesDir/tmp nu sunt executabile | ambalează în APK ca `lib*_exec.so` |
| `CANNOT LINK EXECUTABLE ... libX not found` | Android namespace nu dlopen frații | LD_LIBRARY_PATH cu dir-ul libs |
| Gradle: `Could not initialize native services` | lipsește `libnative-platform.so` | extrage din `native-platform-linux-aarch64-*.jar` |
| Gradle: `Failed to exec spawn helper` | `jspawnhelper` (JDK) nu rulează | `-Djdk.lang.Process.launchMechanism=VFORK` |
| Gradle: `Could not start JAVA_HOME/bin/java` | symlink rupt după reinstalare APK | re-creează symlink-urile la calea APK CURENTĂ |
| `java.io.tmpdir is set to .../com.termux/...` | cale Termux compilată în JDK | `-Djava.io.tmpdir=<filesDir>/tmp` |
| `[CXX1101] not a valid NDK` | AGP validează NDK strict | adaugă `build/cmake/android.toolchain.cmake` + source.properties |
| `Failed to find target android-36` | lipsește `package.xml` în platformă | creează package.xml valid |
| `SDK directory is not writable` | SDK în /data/local/tmp (uid 2000) | mută SDK în filesDir |
| `AAPT2 Daemon startup failed` | aapt2 Maven x86_64 / fără libs | symlink la javahost libaapt2 + libs în deps/lib |
| `does not point to an AAPT2 executable` | override cu `*.so` | folosește symlink FĂRĂ `.so` |
| `kaptDebugKotlin ExceptionInInitializerError` | sqlite-jdbc fără natives Android | sqlite-jdbc 3.46 + `org.sqlite.lib.path` (dir) |
| `NoSuchFieldError view_tree_lifecycle_owner` | R.java incomplet (aapt2 non-daemon) | pune toate resursele AAR la link |
| `ClassNotFoundException kotlin.jvm.internal.Intrinsics` | kotlin-stdlib nu e în dex | include stdlib la d8 |
| `Cannot run program libpyexec.so` | libs native lipsă din APK | ambalează `jniLibs` |
| `ModuleNotFoundError: encodings` | lipsește stdlib Python | ambalează `assets/python/Lib` |
| `No native library found for os.name=Linux` | `org.sqlite.lib.path` = fișier, nu dir | dă DIRECTORUL |
| `chmod` pierdut la copiere sdcard | /sdcard nu păstrează exec bit | `chmod -R 755` după copy |

---

## 5. TIMPI REALI (SM-A366B, măsurați)

- Descărcarea uneltelor: ~700 MB (o singură dată).
- **VocisHD complet** (93 .kt + Opus 149 .c x 7 ABI + kapt + Hilt + dex + packaging):
  **BUILD SUCCESSFUL în ~2m 30s** (după ce cache-ul e populat).
- Configurarea inițială (prima dată, când AGP descarcă tot): 5-15 min.
- APK rezultat: 38 MB (89 MB despachetat, 545 fișiere).

---

## 6. VERIFICARE FINALĂ (stop criterion)

Build-ul NU e „gata" când un tool zice OK. E gata când:
1. `BUILD SUCCESSFUL` + `app/build/outputs/apk/debug/app-debug.apk` există (>0).
2. `aapt2 dump badging app-debug.apk` → package/corect, versiune, permisiuni.
3. `unzip -l` → conține `classes.dex`, `resources.arsc`, `AndroidManifest.xml`, `lib/*/*.so`.
4. `pm install -r --bypass-low-target-sdk-block app-debug.apk` → Success.
5. `am start -n <pkg>/.MainActivity` → fără crash în `logcat -b crash`.

Dovedit pe VocisHD: toate 5 trecute. ✅

---

## 7. REZUMAT ÎN O PROPOZIȚIE

Un app poate compila alt app pe Android dacă: binararele (java, aapt2, cmake) sunt ambalate
ca `lib*_exec.so` într-un APK-gazdă; libs lor sunt în `LD_LIBRARY_PATH`-ul procesului care
le lansează (inclusiv `toolchain/deps/lib` al daemonului Gradle); SDK-ul e în filesDir;
NDK-ul e fake prin symlink-uri; și Gradle rulează cu `VFORK` + `tmpdir` + `user.home` setate.

---
*Document generat pe device, 5 oct 2026. Reproducibil cu acest ghid + memoria agentului.*


---

## 8. AUTOMATIZARE COMPLETĂ (modulul `android_build.py`)

Tot pipeline-ul e împachetat într-un modul Python care vine CU aplicația. La instalare de la
zero, agentul poate compila APK-uri fără nicio pregătire manuală.

### Ce conține APK-ul (stare 5 oct 2026 — ambii agenți au ACELAȘI payload)

> Actualizat: între timp sursa s-a unificat (vezi §9). Numerele de mai jos sunt MĂSURATE
> din APK-urile buildate (`unzip -l`), nu estimări.

```
assets/android_build/          # uneltele (se extrag la setup in filesDir)
  openjdk-21.deb     (106 MB)  # JDK module
  gradle.deb         (149 MB)  # Gradle 9.8
  platform36.zip     ( 66 MB)  # SDK platform android-36
  buildtools36.zip   ( 64 MB)  # SDK build-tools 36.0.0
  aapt2.deb, sqlite-jdbc-3.46.0.0.jar, android.toolchain.cmake
                               # total: 7 fisiere, 381 MB
assets/toolchain/              # 1007 MB despachetat / 6077 fisiere: clang/sysroot/deps/perl
                               #   + rust-libs.tar 801,6 MB (librustc_driver+libLLVM+std)
assets/python/                 # 54 MB (agent.py, android_build.py, toolchain.py, Lib/...)
jniLibs/arm64-v8a/*.so         # 146 libs native (405 MB): java/javac/jlink/jmod/jimage/
                               #   jar/keytool/jarsigner/aapt2/aapt2wrap (lib*_exec.so)
                               #   + clang/cmake/ninja/rust/perl/python + absl/protobuf/fmt
```

Rezultat: APK-ul `net.sys32.agent` = **~983 MB** (payload complet, offline-capable). `.deb`-urile și
`.zip`-urile sunt STORE (deja comprimate), `rust-libs.tar` e deflat (840 MB -> 292 MB).

`net.sys32.javahost` NU mai e necesar: `lib*_exec.so` (java, aapt2) stau acum in `jniLibs`-ul
fiecărei aplicații, deci fiecare e gazdă pentru propriile executabile.

### API (3 funcții)

```python
import android_build
android_build.setup()                     # extrage toate uneltele in filesDir (~5-10 min, o data)
apk = android_build.build("/path/project") # compileaza -> calea APK
android_build.verify(apk)                 # {ok, size_mb, has_dex, has_arsc, has_manifest}
```

### Ca tool al agentului

`android tool=... action=...` — de fapt tool-ul se cheamă `build_apk`:
- `build_apk action=setup`
- `build_apk action=build dir=/path/to/project`
- `build_apk action=verify apk=/path/to.apk`

### Ce face `build()` automat (ca să nu fie nevoie de setup manual al proiectului)

1. Scrie `gradle.properties` în proiect cu VFORK + tmpdir + aapt2 override (dacă lipsesc).
2. Înlocuiește aapt2-ul x86_64 din Maven transforms cache cu symlink la al nostru.
3. Rulează Gradle cu `JAVA_TOOL_OPTIONS` (VFORK propagat la daemon + procese copil).

### Dovedit E2E

Un proiect HelloWorld Android compilat cu `android_build.build()` → APK 0.8 MB
(classes.dex + resources.arsc + manifest), INSTALAT pe device. Toate task-urile Gradle
(processDebugResources, dexBuilder, packageDebug, assembleDebug) au rulat.

---

## 9. STAREA ACTUALĂ (5 oct 2026): ambii agenți identici, o singură sursă

Ce s-a schimbat după ce s-a scris restul ghidului:

### 9.1 O singură sursă de cod

Exista **o singura sursa de cod**: `workspace/app/net.sys32.agent/`.

> **6 oct 2026:** a doua aplicatie (`net.sys32.odc_agent`, generata cu
> `tools/make_agent_variant.sh`) a fost **eliminata** — duplica ~49% din fisiere si crea confuzie.
> Detalii in `readme.md` -> **OP.9**.

### 9.2 APK-ul are payload-ul complet (inclusiv Rust)

Compoziție măsurată (§8): toolchain 1007 MB / 6077 fișiere (cu `rust-libs.tar` 801,6 MB),
146 libs native (405 MB), `assets/android_build` 381 MB, `assets/python` 54 MB.

### 9.3 Cum se construiește

```bash
# pe laptop (Gradle):
cd workspace/app && ./build_app.sh

# pe DEVICE, fara PC (unealta build_apk; vezi §1-§7):
#   build_apk setup          (o data)
#   build_apk build dir=<proiect>
```

### 9.4 Capcane noi (fiecare = un eșec real, cu fix)

| Simptom | Cauză | Fix |
|---|---|---|
| Gradle: `:app:compressDebugAssets > Java heap space` | task-ul decomprimă `rust-libs.tar.gz` (840 MB) și îl re-comprimă; la build de la zero are nevoie de heap | `org.gradle.jvmargs=-Xmx5120m` în `gradle.properties` |
| După instalare curată: aplicația NU extrage nimic (`files/` are doar `profileInstalled`), fără Python | `startCore()` (care face `extractAssets`) rulează doar dacă TOATE permisiunile esențiale sunt acordate — la instalare curată lipsea `READ_MEDIA_IMAGES` | `pm grant` pentru CAMERA, RECORD_AUDIO, ACCESS_FINE_LOCATION, READ_CONTACTS, READ_MEDIA_IMAGES, POST_NOTIFICATIONS + `appops set <pkg> MANAGE_EXTERNAL_STORAGE allow` |
| După wipe: agentul cere cheia API | cheia stă in `files/` (privat), dispare cu `pm uninstall` | scrie-o inapoi prin `run-as` (ambele aplicații sunt debuggable: build Gradle debug) sau lipește-o in UI |
| Cei doi agenți văd aceeași conversație / același `adbkey` | `AGENT_HOME` era hardcodat `Download/Agent` pentru amândoi, iar `adb_setup.py` era lansat fără el | `agent_home_dir` per variantă (generat) + `AGENT_HOME` setat pe AMBELE `ProcessBuilder`-uri din `MainActivity.kt` |

### 9.5 Instalare de la zero (reproductibil)

```bash
bash tools/wipe_device.sh            # dezinstalează net.sys32.*, golește /data/local/tmp și /sdcard
bash tools/install_agents_fresh.sh   # push + pm install ambii, start, accessibility
```

Verificat pe SM-A366B: după wipe total (205 GB liberi) ambii agenți s-au instalat și și-au
extras singuri payload-ul din propriul APK (`files/toolchain`, `files/python`, marker
`.assets_v257`), fără `/data/local/tmp` și fără descărcări; au pornit Python (un subproces
`libpyexec.so` sub fiecare aplicație) și au creat foldere separate pe `/sdcard`
(`Download/Agent`, cu `adbkey` și `workspace/`).

---

### 9.6 Sursa unica de cod

Exista o singura aplicatie si o singura sursa: `workspace/app/net.sys32.agent/`.
Tool-urile (12, inclusiv `build_apk`), payload-ul de build si comportamentul sunt intr-un
singur loc. A doua aplicatie (`net.sys32.odc_agent`) a fost eliminata pe 6 oct 2026.
