#!/bin/bash
# Backup unelte + inputuri de build de pe Samsung SM-A366B (net.sys32.agent)
# Ruleaza: bash backup_device_tools.sh    (adb trebuie sa fie in PATH)
set -u
ADB="${ADB:-/home/gab/android/platform-tools/adb}"
OUT=/home/gab/Desktop/android_agent/build/device-backup
mkdir -p "$OUT"
cd "$OUT" || exit 1
log() { echo "[$(date +%H:%M:%S)] $*"; }

pull() {  # pull <nume.tar> <comanda-device>
  local t="$1"; shift
  log "INCEPE $t"
  "$ADB" exec-out "$*" > "$t" || { log "EROARE la $t"; return 1; }
  log "GATA $t : $(stat -c %s "$t") bytes"
}

# 1. Inputurile exacte pentru build-ul APK-ului odc_agent (assets + libs native extrase din APK)
pull odc-build-inputs.tar 'cd /data/local/tmp && tar cf - odcassets odclibs'

# 2. Toolchain-ul nativ de runtime al agentului (clang/cmake/ninja/deps/rust/sysroot)
pull app-toolchain.tar "run-as net.sys32.agent sh -c 'cd files && tar cf - toolchain'"

# 3. Starea aplicatiei: cod Python viu, PYTHONHOME, site-packages, home (FARA .ssh / key.txt), config
#    SECRETE EXCLUSE: files/home/.ssh/ (cheia GitHub) + orice key.txt (cheia API DeepSeek)
pull app-state.tar "run-as net.sys32.agent sh -c 'cd files && tar cf - \$(cd python && ls -A | grep -v \"^key\\.txt\$\" | sed \"s|^|python/|\") pyhome site_packages_keep wheels cargo libs logs pip.conf profileInstalled toolchain_env.sh memory.md context.json .assets_v252 .assets_v253 .setup_done adbkey adbkey.pub tls.crt tls.key \$(cd home && ls -A | grep -v \"^\\.ssh\$\" | grep -v \"^key\\.txt\$\" | sed \"s|^|home/|\")'"

# 4. Stack-ul Gradle (jdk/gradle/sdk/tlib/cache offline gradlehome) + proiectul de test,
#    FARA APK-urile de iesire (odc2.apk 728MB, odc_java.apk 336MB, odc3.apk 29MB)
pull hdbuild-gradle.tar "run-as net.sys32.agent sh -c 'cd files/hdbuild && tar cf - .android .kotlin aapt2bin aapt2wrap.c gradle gradlehome hdvoice_proj home jdk sdk sqlitedir tlib tmp minitest.c test.sh testbin.sh libsqlitejdbc-android.so java_path.txt javahost_lib.txt gradle_v.log gradle_v2.log gradle_v3.log gradle_v4.log vocis_8core.log vocis_FINAL.log vocis_agp8.log vocis_build.log vocis_build2.log vocis_build3.log vocis_build4.log vocis_build5.log vocis_build6.log vocis_jh.log vocis_jh2.log vocis_jh3.log vocis_jh4.log vocis_jh5.log vocis_jh6.log vocis_jh7.log vocis_jh8.log vocis_jh9.log vocis_jh10.log vocis_jh11.log vocis_jh12.log vocis_jh13.log vocis_jh14.log vocis_jh15.log vocis_jh16.log vocis_jh17.log vocis_jh18.log vocis_jh19.log kapt_dbg.log kapt_dbg2.log'"

# 5. Clone-ul git al repo-ului de pe telefon (are .git cu istoricul local)
pull sdcard-repo.tar 'cd /sdcard/Download/Agent/workspace && tar cf - android_agent'

log "TOATE ARHIVELE SUNT GATA"
ls -l "$OUT"
