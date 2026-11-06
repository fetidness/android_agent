# Recuperare completa: doar repo git + APK de debug

Scenariu: s-a pierdut tot ce era local (clona, binare, `dist/`, toolchain).
Au mai ramas DOUA lucruri: repository-ul git si un APK de debug construit.

**Verificat end-to-end pe telefon** (SM-A366B, Android 16, 6 nov 2026):
clona curata -> bootstrap -> build -> install -> `AGENT FULLY CONFIGURED AND OPERATIONAL`.

---

## De ce functioneaza

`.gitignore` exclude ~4 GB de binare (toolchain 1 GB, whisper 1.5 GB, jniLibs 416 MB,
android_build 399 MB, modele, rootfs) **plus stdlib-ul CPython** (`assets/python/Lib`,
3822 fisiere). O clona goala are doar sursele (~1.5 GB).
Toate acestea sunt insa in APK, deci `tools/bootstrap_binaries.sh` le scoate de acolo.

| Piesa | In git | Din APK |
|---|---|---|
| sursa Kotlin (192 clase), Python, res, manifest, gradle | da | - |
| assets/toolchain (1 GB) | nu | da |
| assets/whisper (1.5 GB) | nu | da |
| assets/models (63 MB) | nu | da |
| **assets/python/Lib (stdlib CPython, 110 MB)** | **nu** | **da** |
| assets/proot (rootfs Debian) | nu | da + **recomprimare** |
| assets/android_build (399 MB) | nu | da |
| jniLibs (151 .so) | nu | da |
| local.properties | nu | generat |

---

## Procedura (6 minute)

```bash
git clone git@github.com:fetidness/android_agent.git
cd android_agent

mkdir -p dist
cp /cale/catre/net.sys32.agent.apk dist/

bash tools/bootstrap_binaries.sh          # ~3 min (extrage 4 GB + recomprima rootfs)

cd workspace/app/net.sys32.agent
JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
  /home/gab/Work/Android/gradle-8.11.1/bin/gradle --offline clean assembleDebug
```

Rezultat: `app/build/outputs/apk/debug/app-debug.apk` (~3.8 GB).

Instalare pe telefon:
```bash
adb push app/build/outputs/apk/debug/app-debug.apk /data/local/tmp/a.apk
adb shell am force-stop net.sys32.agent
adb uninstall net.sys32.agent
adb shell pm install -r -d /data/local/tmp/a.apk
```

---

## Capcane dovedite (fiecare a costat un test esuat)

**1. `assets/python/Lib` lipseste din bootstrap -> aplicatia ingheata la "Libraries"**

`Lib/` e stdlib-ul CPython (3822 fisiere in APK). Fara el: setup-ul porneste, arata
"First-time setup", ajunge la `• Libraries` si **se blocheaza definitiv** - FARA nicio
eroare pe ecran, pentru ca `libpyexec` nu poate importa `threading` si nu se scrie
markerul `.stdlib_ok`.

Semn pe disc: `files/pyhome/lib/` are doar `pysitepkg.zip` + `stdlib_extra.zip`
(acesta din urma NU contine threading/os/encodings - verificat cu `unzip -l`),
`files/tmp/` e gol, `files/pyhome/lib/python3.14/threading.py` lipseste.

Bootstrap-ul extrage acum `assets/python/Lib/*` si are o **verificare finala care iese
cu exit code 1** daca lipseste oricare componenta critica.

**2. Guard-ul de toolchain verifica un director care nu exista**

Codul vechi: `if [ -d "$APP/assets/toolchain/bin" ]` - dar toolchain-ul livrat are
`cmake/ deps/ lib/ perl/ pyinc/ rust-libs.tar sysroot/`, **fara `bin/`**. Conditia era
mereu falsa -> re-extragea 1 GB la fiecare rulare, apoi `mv` cadea cu
`cannot overwrite '.../toolchain/toolchain': Directory not empty` (lipsea `rm -rf`).
Fix: guard pe `toolchain/deps` + `toolchain/sysroot`, si `rm -rf` inainte de `mv`.

**3. AGP dezarhiveaza asset-urile `.gz`**

In APK, `assets/proot/agentroot.tar.gz` apare ca **`agentroot.tar`** (539 MB, dezarhivat).
`fetch_rootfs.sh` si `build.gradle.kts` cer `.tar.gz`, deci fara recompresie build-ul cade:
```
[rootfs] LIPSESTE app/src/main/assets/proot/agentroot.tar.gz
```
Bootstrap-ul recomprima acum automat (`gzip -1`, +90 s). Continutul e identic - verificat
cu md5 pe primul MB.

**4. Java heap la compressDebugAssets**

4 GB de assets nu incap in 8 GB de heap (stdlib-ul a adaugat 110 MB peste limita).
Simptom: `Execution failed for task ':app:compressDebugAssets' > Java heap space`.
Foloseste `-Xmx11g` in `gradle.properties` + `--no-daemon` (un daemon vechi pastreaza
heap-ul vechi si conditia se repeta).

**5. `local.properties` lipseste din git**

Il scrie bootstrap-ul (`sdk.dir=/home/gab/Work/Android`). Fara el: "SDK location not found".

---

## Cum arata succesul

Pe ecran, dupa setup:
```
[setup] libs=True key=True cert=True
AGENT FULLY CONFIGURED AND OPERATIONAL
[adb] port detectat: 5555
[adb] AUTH -> trimit RSAPUBLICKEY 701 bytes
[adb] ✓ AUTORIZAT: device::ro.product.name=...;ro.product.model=SM-A366B
```

Pe disc (`adb shell run-as net.sys32.agent ls files/`):
```
pyhome/.stdlib_ok                        <- marker de completitudine
pyhome/lib/python3.14/threading.py       <- stdlib prezent
tmp/python3.sh                           <- scriptul de lansare
```

---

## Daca NU ai APK

Nu poti face bootstrap: toolchain-ul cross (1 GB) si whisper medium (1.5 GB) nu se
reconstruiesc din surse in timp rezonabil. Alternative: `bootstrap_binaries.sh
--from-device` (cere telefon cu aplicatia instalata) sau o copie a APK-ului.

**Concluzie practica: APK-ul de debug nu e optional - e a doua jumatate a backup-ului.**
Pastreaza `dist/net.sys32.agent.apk` sincronizat cu fiecare commit care schimba sursele.

---

## Daca ai DOAR APK, fara git

Codul Kotlin se recupereaza din `classes*.dex` cu `baksmali` (192 clase `net/sys32`,
cu `SMAP` care da harta instrucțiune -> linie din `.kt`), iar assets-urile
(`assets/python`, `skills`, `res`) sunt la SURSA EXACTA. Vezi skill-ul
`rebuild-android-agent-from-git-and-apk` pentru comenzile exacte.
