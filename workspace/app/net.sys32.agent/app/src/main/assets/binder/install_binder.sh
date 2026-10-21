#!/bin/sh
# install_binder.sh - instaleaza clientul Binder nativ in Debian (proot)
#
# Ruleaza IN Debian:  sh /sdcard/Download/Agent/workspace/install_binder.sh
# sau, dupa ce sursele sunt in /opt/android-binder:
#   sh /opt/android-binder/install_binder.sh
#
# Compileaza debian_binder.c cu gcc-ul din Debian si instaleaza binarul +
# modulul Python global.
set -e

SRC_DIR="${1:-/opt/android-binder}"
# ★ cai de pe device (instalare curata): sursa vine din assets -> files/binder,
# vizibila in Debian prin --bind=/data/local/tmp sau prin /sdcard dupa copiere.
for c in /data/local/tmp/binder /sdcard/Download/Agent/workspace/binder /root/binder; do
  [ -f "$SRC_DIR/debian_binder.c" ] && break
  [ -f "$c/debian_binder.c" ] && SRC_DIR="$c"
done
[ -f "$SRC_DIR/debian_binder.c" ] || { echo "nu gasesc debian_binder.c"; exit 1; }

echo "== sursa: $SRC_DIR"
command -v gcc >/dev/null || { echo "lipseste gcc: apt install gcc"; exit 1; }

mkdir -p /opt/android-binder
cd "$SRC_DIR"
gcc -O2 -o /opt/android-binder/android-binder debian_binder.c
chmod 755 /opt/android-binder/android-binder
cp debian_binder.c /opt/android-binder/ 2>/dev/null || true
[ -f "$SRC_DIR/binder.py" ] && [ "$SRC_DIR" != /opt/android-binder ] && cp "$SRC_DIR/binder.py" /opt/android-binder/ || true

ln -sf /opt/android-binder/android-binder /usr/local/bin/android-binder
echo "== binar: $(command -v android-binder)"

# modul Python importabil global
PY_DIR=$(python3 -c 'import site;print(site.getsitepackages()[0])' 2>/dev/null || echo /usr/local/lib/python3/dist-packages)
if [ -f /opt/android-binder/binder.py ]; then
    mkdir -p "$PY_DIR"
    cp /opt/android-binder/binder.py "$PY_DIR/binder.py"
    echo "== modul Python: $PY_DIR/binder.py"
fi

echo "== test:"
android-binder list | wc -l
android-binder check package
# ★ selftest: numara accesibile / lazy / null. NU conchide "binder stricat"
# dintr-un singur esec pe un serviciu lazy (activity, window, stats...).
android-binder selftest 2>/dev/null || true
