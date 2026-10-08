#!/bin/sh
# Rebuild RAPID al APK-ului net.sys32.agent cand se schimba DOAR fisiere din
# assets/python (agent.py, toolchain.py, android_build.py...) - fara gradle.
#
# De ce: un build gradle complet re-ambaleaza ~1.9 GB (assets toolchain + jniLibs) si
# dureaza mult. Daca binarul (toolchain/jniLibs) NU s-a schimbat, e suficient sa
# inlocuim intrarile schimbate in APK-ul de baza si sa re-semnăm.
#
# IMPORTANT (capcana reala): APK-ul de baza trebuie sa fie SEMNAT cu acelasi debug
# keystore ca instalarea curenta, altfel `adb install -r` da INSTALL_FAILED_UPDATE_INCOMPATIBLE
# si uninstall-ul sterge key.txt/workspace/contextul. Keystore-ul corect:
#   ~/.config/.android/debug.keystore   (SHA-256 192d23a9...)
#
# Folosire:
#   tools/repack_assets.sh [apk_de_baza]
#   (fara argument: ia APK-ul instalat de pe device)
set -e

ADB=${ADB:-/home/gab/android/platform-tools/adb}
BT=${BT:-/home/gab/android/build-tools/35.0.0}
KS=${KS:-$HOME/.config/.android/debug.keystore}
REPO=$(cd "$(dirname "$0")/.." && pwd)
ASSETS="$REPO/workspace/app/net.sys32.agent/app/src/main/assets/python"
WORK=${WORK:-$HOME/.hermes/cache/scratch/apk}

# fisierele care se pot schimba fara build nativ (binarul din APK rămâne al aceluiasi build)
FILES="agent.py toolchain.py selfheal.py android_build.py adb_client.py adb_setup.py scraper.py
jsengine.py jsfetch.py newsfeed.py websearch.py devhelper.py build.py setexec.py
_streams.py sshkeygen.py android_bridge.py"

mkdir -p "$WORK"
cd "$WORK"

if [ -n "$1" ]; then
    BASE="$1"
else
    BASE="$WORK/base.apk"
    if [ ! -f "$BASE" ]; then
        P=$($ADB shell pm path net.sys32.agent | tr -d '\r' | sed 's/package://')
        echo "[repack] iau APK-ul de baza: $P"
        $ADB pull "$P" "$BASE"
    fi
fi

echo "[repack] pregatesc intrarile din $ASSETS"
rm -rf stage && mkdir -p stage/assets/python
for f in $FILES; do
    [ -f "$ASSETS/$f" ] || continue
    cp "$ASSETS/$f" stage/assets/python/
done

echo "[repack] copiez APK-ul de baza"
cp "$BASE" work.apk

echo "[repack] inlocuiesc intrarile (fara recompresie)"
(cd stage && zip -X -q "$WORK/work.apk" $(for f in $FILES; do [ -f "assets/python/$f" ] && echo "assets/python/$f"; done))

echo "[repack] zipalign"
# -p 4: aliniere pe pagini de 4 KB pentru .so necomprimate (exact ce face AGP cu
# packaging.jniLibs.useLegacyPackaging=true). ATENTIE: binarul zipalign din SDK-ul de aici
# NU stie `-P <pagesize_kb>` (desi il afiseaza in usage) -> iese cu rc=2 daca il folosesti.
"$BT/zipalign" -f -p 4 work.apk aligned.apk
"$BT/zipalign" -c -p 4 aligned.apk | tail -1

echo "[repack] semnez (debug keystore)"
"$BT/apksigner" sign --ks "$KS" --ks-pass pass:android --key-pass pass:android \
    --ks-key-alias androiddebugkey --out final.apk aligned.apk

"$BT/apksigner" verify --print-certs final.apk | head -3
ls -la final.apk
echo "[repack] gata: $WORK/final.apk"
echo "[repack] instalez: $ADB install -r final.apk"
