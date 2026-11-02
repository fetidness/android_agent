#!/bin/bash
# generate_adbkey.sh - scrie cheia adb PRE-AUTORIZATA pentru telefoanele operatorului.
#
# DE CE: aplicatia (untrusted_app) NU isi poate autoriza singura cheia la adbd - dialogul
# "Allow USB debugging" nu poate fi acceptat din cod, iar pe un telefon fara root lista
# user_keys nu poate fi modificata. Singura cale dovedita, care supravietuieste reboot-ului,
# e fisierul `adb_keys` al device-ului (`getprop persist.adb.allowed_keys_file`, pe Xiaomi
# /data/misc/adb/adb_keys): cheia publica a aplicatiei se scrie acolo O SINGURA DATA.
#
# Rulare:
#   tools/generate_adbkey.sh                 # (re)genereaza cheia in assets/adb/
#   tools/generate_adbkey.sh --authorize     # + o autorizeaza pe telefonul conectat USB
set -e
REPO=$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)
D=$REPO/app/src/main/assets/adb
ADB=${ADB:-/home/gab/Work/Android/platform-tools/adb}
mkdir -p "$D"
if [ ! -f "$D/adbkey" ] || [ "$1" = "--force" ]; then
    openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out "$D/adbkey" 2>/dev/null
    python3 "$REPO/tools/adbkey_pub.py" "$D/adbkey" "$D/adbkey.pub"
fi
chmod 644 "$D/adbkey" "$D/adbkey.pub"
echo "cheie: $D/adbkey (+.pub)"
if [ "$1" = "--authorize" ] || [ "$2" = "--authorize" ]; then
    F=$($ADB shell getprop persist.adb.allowed_keys_file | tr -d '\r')
    F=${F:-/data/misc/adb/adb_keys}
    $ADB root >/dev/null 2>&1 || true; sleep 2
    $ADB shell "mkdir -p $(dirname $F); grep -qF '$(cut -d' ' -f1 "$D/adbkey.pub")' $F 2>/dev/null || cat >> $F" < "$D/adbkey.pub"
    $ADB shell "wc -l $F"
    $ADB unroot >/dev/null 2>&1 || true
fi
