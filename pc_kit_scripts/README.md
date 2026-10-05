# pc_kit — construieste odc_agent.apk pe PC (offline)

Acest kit iti permite sa construiesti **odc_agent.apk** pe calculator. APK-ul rezultat
contine TOATE uneltele, deci la instalarea pe telefon poate **compila aplicatii Android
pe device, fara internet**.

## Ce contine kitul

```
pc_kit/
  odc_agent/              sursa completa a aplicatiei
    app/src/main/
      AndroidManifest.xml
      res/                resurse
      java/               sursa Kotlin (net/sys32/odc_agent)
      jniLibs/arm64-v8a/  146 libs native (java, aapt2, clang, python...) - pt TELEFON
      assets/python/      codul Python al agentului + android_build.py
      assets/toolchain/   clang/sysroot/ninja (aarch64) - pt TELEFON
      assets/android_build/  unelte descarcabile (JDK/Gradle/SDK) - optionale in kit
  deps/                   unelte de BUILD pt PC
    android.jar           API 36 (portabil)
    kotlinc/lib/*.jar     compilator Kotlin (portabil)
    d8/lib/d8.jar         dexer (portabil)
    apksigner/lib/*.jar   semnare (portabil)
    classpath/*.jar       androidx (portabil)
  build_odc_agent.sh      scriptul principal (ruleaza pe PC)
  prepare_pc_kit.sh       scriptul de pe device (deja rulat)
  README.md               acest fisier
```

## Cerinte pe PC

- **JDK 17+** (`java` in PATH sau `JAVA_HOME` setat)
- `curl` sau `wget`
- `unzip`

## Cum construiesti

```bash
cd pc_kit
chmod +x build_odc_agent.sh
./build_odc_agent.sh
```

Rezultat: **`odc_agent.apk`** (~617 MB) in folderul `pc_kit/`.

Scriptul:
1. Descarca `aapt2` x86_64 (din build-tools Google) si `android.jar` daca lipsesc (~130 MB, o data).
2. Compileaza resursele (aapt2), sursa Kotlin (kotlinc), dex-ul (d8).
3. Ambalazeaza assets + jniLibs (aarch64, pt telefon).
4. Semneaza cu o cheie noua (`odc_agent.keystore`).

## Instalare pe telefon

```bash
adb install -r --bypass-low-target-sdk-block odc_agent.apk
```

La prima rulare pe telefon, aplicatia extrage uneltele (JDK/Gradle/SDK) din assets in
filesDir (~5-10 min). Apoi poate compila APK-uri Android pe device, complet offline.

## Nota despre offline

- **Kit-ul e offline** (nu descarca nimic la build, in afara de aapt2/android.jar de pe PC).
- **APK-ul rezultat e offline** daca ai inclus `assets/android_build/` in kit
  (vezi `prepare_pc_kit.sh --with-downloads`). Atunci TOATE uneltele sunt in APK.
- Daca ai construit kit-ul fara `--with-downloads`, APK-ul va lua uneltele celor descarcabile
  (JDK/Gradle/SDK) la prima rulare pe telefon.

## Date tehnice

Pipeline-ul e cel documentat in `BUILD_ANDROID_ON_DEVICE.md`. Pe device, compilarea
efectiva a APK-urilor se face de `android_build.py` (tool `build_apk` al agentului).
