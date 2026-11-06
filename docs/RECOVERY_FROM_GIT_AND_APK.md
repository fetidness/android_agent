# Recuperare completa: doar repo git + APK de debug

Scenariu: s-a pierdut tot ce era local (clone, binare, `dist/`, toolchain).
Au mai ramas DOUA lucruri: repository-ul git si un APK de debug construit.

**Verificat end-to-end pe 6 nov 2026** (SM-A366B, host x86_64, gradle 8.11.1, NDK 29).

---

## De ce functioneaza

`.gitignore` exclude ~4 GB de binare (toolchain 1 GB, whisper 1.5 GB, jniLibs 416 MB,
android_build 399 MB, modele, rootfs). O clona goala are doar **sursele** (~1.5 GB).
Toate binarele sunt insa in APK, deci `tools/bootstrap_binaries.sh` le scoate de acolo.

| Piesa | In git | Din APK |
|---|---|---|
| sursa Kotlin (192 clase), Python, res, manifest, gradle | da | - |
| assets/toolchain (1 GB) | nu | da |
| assets/whisper (1.5 GB) | nu | da |
| assets/models (63 MB) | nu | da |
| assets/proot (rootfs Debian) | nu | da + **recomprimare** |
| assets/android_build (399 MB) | nu | da |
| jniLibs (151 .so) | nu | da |
| local.properties | nu | generat |

---

## Procedura (5 minute)

```bash
git clone git@github.com:fetidness/android_agent.git
cd android_agent

mkdir -p dist
cp /cale/catre/net.sys32.agent.apk dist/

bash tools/bootstrap_binaries.sh          # ~32 s (recomprima rootfs: +90 s)

cd workspace/app/net.sys32.agent
JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
  /home/gab/Work/Android/gradle-8.11.1/bin/gradle --offline clean assembleDebug
```

Rezultat: `app/build/outputs/apk/debug/app-debug.apk`.

---

## Capcane dovedite

**1. AGP dezarhiveaza asset-urile `.gz`**

In APK, `assets/proot/agentroot.tar.gz` apare ca **`agentroot.tar`** (539 MB, dezarhivat).
`fetch_rootfs.sh` si `build.gradle.kts` cer `.tar.gz`, deci fara recompresie build-ul cade cu:

```
[rootfs] LIPSESTE app/src/main/assets/proot/agentroot.tar.gz: ruleaza 'sudo tools/build_rootfs.sh'
```

`bootstrap_binaries.sh` recomprima acum automat (`gzip -1`). Conținutul e identic - verificat
cu md5 pe primul MB intre varianta din APK si cea din proiect.

**2. Java heap la compresia assets**

3.6 GB de assets nu incap in 5 GB de heap. `gradle.properties` are acum `-Xmx8192m`.
Simptom fara el: `Execution failed for task ':app:compressDebugAssets' > Java heap space`.

**3. Un daemon Gradle vechi tine memoria**

Daca build-ul da heap space desi `-Xmx` e mare: `gradle --stop` si `pkill -f GradleDaemon`.

**4. `local.properties` lipseste din git**

Il scrie bootstrap-ul (`sdk.dir=/home/gab/Work/Android`). Fara el: "SDK location not found".

---

## Daca NU ai APK

Nu poti face bootstrap: toolchain-ul nativ si modelele nu se pot reconstrui din surse in
timp rezonabil (whisper medium = 1.5 GB de model, toolchain = compilator cross). In acest caz
ai nevoie de telefon (`bootstrap_binaries.sh --from-device`) sau de o copie a APK-ului.

---

## Ce NU se poate recupera din APK

- `build.gradle.kts`, `settings.gradle.kts`, `gradle.properties` - nu sunt in APK
  (dar SUNT in git, deci nu e o problema in acest scenariu)
- comentariile si istoricul de commit - sursa de adevar ramane repo git

## Daca ai DOAR APK, fara git

Vezi `docs/RECOVERY_FROM_APK_ONLY.md`: codul Kotlin se recupereaza din `classes*.dex` cu
`baksmali` (192 clase, cu `SMAP` care da harta spre liniile din `.kt`), iar assets-urile sunt
la sursa exacta.
