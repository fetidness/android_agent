#!/bin/bash
# fetch_whisper.sh - descarca modelul Whisper (STT offline) in assets, ca build-ul sa
# functioneze out of the box dupa o clona noua. Modelul NU sta in git (1.5 GB).
# Idempotent: daca fisierul exista si are dimensiunea corecta, nu face nimic.
#
#   bash fetch_whisper.sh          # descarca doar daca lipseste
#   bash fetch_whisper.sh --force  # rescrie
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

MODEL="medium"
DEST="app/src/main/assets/whisper/models"
FILE="$DEST/ggml-$MODEL.bin"
# dimensiunea exacta a modelului medium (verificata pe device)
SIZE=1533763059
URL="https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-$MODEL.bin"

if [ -f "$FILE" ] && [ "${1:-}" != "--force" ]; then
    SZ=$(stat -c%s "$FILE")
    if [ "$SZ" -eq "$SIZE" ]; then
        echo "[whisper] deja prezent: $FILE ($((SZ/1024/1024)) MB) - nimic de facut"
        exit 0
    fi
    echo "[whisper] $FILE are $SZ octeti (asteptat $SIZE) - il descarc din nou"
fi

mkdir -p "$DEST"
echo "[whisper] descarc ggml-$MODEL.bin ($((SIZE/1024/1024)) MB, o singura data)"
# --fail: o eroare de retea opreste build-ul, in loc sa lase un fisier "Entry not found"
curl -L --fail --retry 3 -o "$FILE.part" "$URL"

SZ=$(stat -c%s "$FILE.part")
if [ "$SZ" -ne "$SIZE" ]; then
    echo "EROARE: modelul are $SZ octeti, asteptat $SIZE - descarcarea a esuat"
    rm -f "$FILE.part"
    exit 1
fi
mv "$FILE.part" "$FILE"
echo "[whisper] OK: $FILE ($((SZ/1024/1024)) MB)"
