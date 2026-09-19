# APLICATIA net.sys32.agent - STARE (functionala)

## REZULTAT: APK FUNCTIONAL, AGENTUL RULEAZA IN APP

## Ce face
- La deschidere: extrage Python + agent din assets in filesDir,
  porneste Python ca PROCES COPIL, afiseaza terminalul agentului in UI
- Scrii in campul de jos -> ajunge la agent -> raspuns AI afisat live
- Permisiuni: cerute la prima pornire (camera, storage, locatie, senzori, ...)

## Structura
app/net.sys32.agent/
  app/src/main/
    java/net/sys32/agent/MainActivity.kt  -> terminal + proces python
    AndroidManifest.xml                   -> TOATE permisiunile
    assets/python/
      Lib/                                -> stdlib .py (comun)
      libdynload/{arm64,x86_64}/          -> module .so per ABI
      agent.py, key.txt, memory.md, workspace/
    jniLibs/{arm64-v8a,x86_64}/
      libpyexec.so        -> binarul python (renumit, ca sa fie executabil)
      libpython3.14.so, libpython3.so, libcrypto_python.so,
      libssl_python.so, libsqlite3_python.so

## Configuratie Python (in MainActivity)
- executabil: applicationInfo.nativeLibraryDir/libpyexec.so
- PYTHONHOME: filesDir/pyhome  (=> filesDir/pyhome/lib/python3.14 = stdlib)
- stdlib: copiat din filesDir/python/Lib
- lib-dynload: copiat din filesDir/python/libdynload/<abi>/
- rulare: ProcessBuilder(py, "agent.py") in filesDir/python (CA SCRIPT, nu -c!)
- LD_LIBRARY_PATH = nativeLibraryDir
- PATH = /system/bin:/vendor/bin
- HOME = filesDir/home

## BUILD
    cd /home/gab/Desktop/agent/workspace/app/net.sys32.agent
    ./gradlew assembleDebug
    adb install -r app/build/outputs/apk/debug/app-debug.apk
sau: ./build_app.sh   (face tot)

## APK
- ~30 MB (arm64-v8a + x86_64)
- AGP 8.7.3, Kotlin 2.0.21, Gradle 8.11.1, compileSdk 36, minSdk 26

## LECTII
- executabilele NU merg rulate din filesDir pe API29+ -> lib*.so in jniLibs
- python cu -c nu are __file__ -> agent.py trebuie rulat CA SCRIPT
- -E ignora PYTHONHOME -> NU folosi -E
- assets nu pot fi per-ABI -> modulele stdlib .so le tinem in libdynload/<abi>/ si le copiem la runtime
- emulatorul are popup de stylus care acopera butonul -> settings put secure stylus_handwriting_enabled 0

## DE IMBUNATATIT
- ANSI: momentan doar strip (fara culori in UI)
- tastatura acopera butonul trimite (de rezolvat cu adjustResize/implicit)
- iconita aplicatiei e un placeholder
- release build ar trebui semnat


## UI (v2 - finalizat)
### 1. Tastatura nu mai acopera input-ul
- `android:windowSoftInputMode="adjustResize|stateUnchanged"` in manifest
- `WindowCompat.setDecorFitsSystemWindows(window, false)` + setOnApplyWindowInsetsListener
- padding bottom = max(bars.bottom, ime.bottom) -> input+buton mereu DEASUPRA tastaturii

### 2. Culori ANSI (Ansi.kt)
- converteste secventele SGR in Spannable colorat
- suporta: 30-37, 90-97, 40-47, 100-107, 38;5;N/48;5;N (256 culori),
  38;2;R;G;B (truecolor), bold(1) italic(3) underline(4) strike(9), reset(0)
- paleta 16 culori adaptata (stil One Dark): #{'E06C75,98C379,E5C07B,61AFEF,C678DD,56B6C2,ABB2BF'}
- strip la \r (nu avem cursor in TextView)

### 3. Status bar (ora/wifi/baterie) nu se suprapune
- `setDecorFitsSystemWindows(false)` + inset top aplicat ca padding pe root
- statusBarColor = #0D1117 (acelasi cu fundalul)
- LAYOUT_IN_DISPLAY_CUTOUT_MODE_NEVER

### Culori UI
- fundal: #0D1117 (aproape negru)
- app banner: #61AFEF (albastru)
- hint input: #5C6370
- text: #ABB2BF

### Fisier nou
- app/src/main/java/net/sys32/agent/Ansi.kt
