> ⚠️ **ISTORIC (5 oct 2026).** Acest manifest descrie un backup facut INAINTE de eliminarea
> celei de-a doua aplicatii. Arhiva `odc-build-inputs.tar` nu mai este necesara (era pentru
> build-ul `net.sys32.odc_agent`, scos pe 6 oct 2026). Pastrat ca referinta istorica.

# MANIFEST — Backup unelte + inputuri de build, Samsung SM-A366B (net.sys32.agent)

Data: 2026-10-05T05:30:56-04:00
Device: SM-A366B (RZGL102X5AT), Android 16, via adb USB
Sursa script: /home/gab/Desktop/android_agent/tools/backup_device_tools.sh

## Arhive

FISIER                            BYTES  SHA256
app-state.tar                 315195392  cee7744e51909f02f727bec186bc266c1baa5b807a7fe73f2f3833da21d92ec6
app-toolchain.tar            1945982976  af9593b857f3a9d4e046bb47a9e6dabbb4c70b4c04cf3c6d42498974b2ca11e8
hdbuild-gradle.tar           2752854016  ebe8456081017c13da9e1f51d860b0217f3e0df20eee2589cb20ab11453110ec
odc-build-inputs.tar         1530110976  bd11e10b3002b39fe759ef1f8a3b2ef3726aa459ac481b3e1e35e3bb39fdbdcf
sdcard-repo.tar                72322048  d68af2938126588f655c1dd7c1e6950f154768e903f81e842ca4a293c2a4feab
apkbuild-tools.tar            845754368  5febbeb611fd247feed3ba87c09d46f8dca75f39f524552cb5acddfbe61de082

## Ce e in fiecare (sursa pe device -> arhiva)

apkbuild-tools.tar      /data/local/tmp/apkbuild (doar uneltele, fara proiecte)
                        .android aapt2 android.jar apksigner aar_res build_apk.sh classpath d8
                        gradle javahost jdk jrun.sh kotlin release.keystore sdk tlib
                        NU: odc/ odc_full/ odc*.apk agent2/ work/ work_src/ hdvoice_proj/ a2/
                            hello/ gradlehome/ tmp/

odc-build-inputs.tar    /data/local/tmp/odcassets/assets + /data/local/tmp/odclibs
                        = exact inputurile pentru build-ul APK-ului odc_agent (toolchain in
                          forma de assets + lib/arm64-v8a/*.so extrase din APK)

app-toolchain.tar       files/toolchain  (toolchain-ul nativ de runtime: clang/cmake/ninja,
                        deps, rust, sysroot, perl, pyinc, rust-libs.tar 803MB)

app-state.tar           files/{python, pyhome, site_packages_keep, wheels, cargo, libs, logs,
                        home/, memory.md, context.json, ...}  — starea aplicatiei
                        FARA .ssh si FARA key.txt (secrete)

hdbuild-gradle.tar      files/hdbuild — stack-ul Gradle complet (jdk, gradle, sdk CU platforma
                        android-36 completa + platform-tools, gradlehome = cache offline,
                        tlib, aapt2bin, hdvoice_proj, logurile de build)
                        NU: odc2.apk, odc_java.apk, odc3.apk (iesiri), build.pid, gradle_v.pid,
                            gradle_run.log, testbin (symlink mort)

sdcard-repo.tar         /sdcard/Download/Agent/workspace/android_agent (clone-ul git de pe telefon)

## Verificari facute
- tar tf pe fiecare arhiva: rc=0, fara trunchiere
- set-diff fata de listarea device-ului (find):
    hdbuild:   device 66778 / arhiva 66770 -> diferenta = EXACT cele 8 excluderi intentionate
               (".", build.pid, gradle_v.pid, gradle_run.log, odc2.apk, odc3.apk, odc_java.apk, testbin)
    app-state: device 10361 / arhiva 10361 -> 0 diferente
    app-toolchain: 9679 = 9679 ; odc-build-inputs: 8214 = 8214 ; repo: 2655 = 2655
- md5 identic device vs arhiva pe: toolchain/rust-libs.tar, sysroot/.../stdio.h, odclibs/.../
  libpython3.14.so, hdbuild/jdk/bin/java, sdk/platforms/android-36/android.jar,
  gradlehome/.../fileHashes.bin, python/agent.py, memory.md, android_agent/readme.md,
  + apkbuild: android.jar, build_apk.sh, release.keystore, jdk/bin/java, aapt2
- 0 fisiere de secret in arhive (.ssh / key.txt absente)
- symlink-uri pastrate: app-toolchain 224, hdbuild 18, app-state 2

## ATENTIE la restaurare
- Symlink-urile absolute catre /data/app/~~<hash>==/net.sys32.javahost-<hash>==/lib/arm64/*.so
  (jdk/bin/java, javac, hdbuild/testbin) sunt MOARTE dupa reinstalarea APK-ului javahost.
  Dupa restore: re-creeaza-le la calea APK curenta (vezi BUILD_ANDROID_ON_DEVICE.md, §4).
- Restaurare: tar xf <arhiva>.tar -C <dest>
