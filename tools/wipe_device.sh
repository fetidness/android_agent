#!/bin/bash
# WIPE total (varianta aleasa de operator):
#  1) dezinstaleaza TOATE aplicatiile net.sys32.* (cu tot cu datele lor private)
#  2) goleste /data/local/tmp (9,7 GB de unelte si proiecte)
#  3) goleste /sdcard (toate directoarele de utilizator + fisierele de la radacina)
set -u
ADB="${ADB:-/home/gab/android/platform-tools/adb}"
log(){ echo "[$(date +%H:%M:%S)] $*"; }

log "1/3 dezinstalez aplicatiile net.sys32.*"
for p in net.sys32.agent net.sys32.javahost net.sys32.vocis net.sys32.test; do
  "$ADB" shell "am force-stop $p" >/dev/null 2>&1
  r=$("$ADB" shell "pm uninstall --user 0 $p" 2>&1 | tr -d '\r' | tail -1)
  log "   $p -> $r"
done
log "   ramase: $("$ADB" shell 'pm list packages | grep -c sys32' | tr -d '\r')"

log "2/3 gol /data/local/tmp"
"$ADB" shell 'rm -rf /data/local/tmp/* /data/local/tmp/.[!.]* 2>/dev/null'
log "   intrari ramase: $("$ADB" shell 'ls -A /data/local/tmp 2>/dev/null | wc -l' | tr -d '\r')"

log "3/3 gol /sdcard"
"$ADB" shell 'cd /sdcard && rm -rf Alarms Android Audiobooks DCIM Documents Download Movies Music Notifications Pictures Podcasts Ringtones Recordings _ui.xml log nlibs numpy_tmp agent_tmp 2>/dev/null'
"$ADB" shell 'cd /sdcard && for f in * .[!.]*; do [ -e "$f" ] && rm -rf "$f" 2>/dev/null; done'
log "   ramas pe /sdcard: $("$ADB" shell 'ls -A /sdcard | tr "\n" " "' | tr -d '\r')"

log "STARE FINALA"
"$ADB" shell 'echo "   pachete sys32: $(pm list packages | grep -c sys32)"; echo "   /data/local/tmp: $(ls -A /data/local/tmp 2>/dev/null | wc -l) intrari"; echo "   spatiu liber /data: $(df -h /data | tail -1 | awk "{print \$4}")"; echo "   spatiu liber /sdcard: $(df -h /storage/emulated | tail -1 | awk "{print \$4}")"'
log "GATA"
