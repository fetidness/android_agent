#!/bin/bash
# fetch_model.sh - descarca modelul Phonon 31m in assets, ca build-ul sa functioneze
# out of the box dupa o clona noua. Idempotent: daca model.q8.gguf exista deja, nu face nimic.
#
#   bash fetch_model.sh          # descarca doar daca lipseste
#   bash fetch_model.sh --force  # rescrie
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

DEST="app/src/main/assets/models/phonon-31m-en"
REPO="https://huggingface.co/gradium/phonon-31m-en/resolve/8c64b55ec301728e2d1695bfea87a08a267d0c2d"
VOICES="https://huggingface.co/gradium/phonon-voices/resolve/da6c9ec0d47be8df5c87c730a3aa97187f3229c3/voices"

if [ -f "$DEST/model.q8.gguf" ] && [ "${1:-}" != "--force" ]; then
    echo "[model] deja prezent: $DEST ($(du -sh "$DEST" | cut -f1)) - nimic de facut"
    exit 0
fi

echo "[model] descarc Phonon 31m in $DEST (63 MB, o singura data)"
mkdir -p "$DEST/voices"

# OBLIGATORII: fara ele motorul nu incarca modelul (--fail: orice eroare opreste build-ul)
for f in config.json tokenizer.json tokenizer.model model.q8.gguf; do
    [ -f "$DEST/$f" ] && [ "${1:-}" != "--force" ] && { echo "  skip $f"; continue; }
    echo "  descarc $f"
    curl -sSL --fail -o "$DEST/$f.tmp" "$REPO/$f" || { echo "EROARE la $f"; rm -f "$DEST/$f.tmp"; exit 1; }
    mv "$DEST/$f.tmp" "$DEST/$f"
done
# OPTIONALE: nu exista in toate checkpoint-urile (HF da 404); motorul le tolereaza lipsa
for f in generation_config.json processor_config.json tokenizer_config.json; do
    curl -sSL -o "$DEST/$f" "$REPO/$f" 2>/dev/null || true
done

# vocile: en(Zoey), fr(Noemie), de(Nele), es(Noa)
for v in NbpkqMVS3CJeq2j8 FXxJ9mANRq6BCTX5 2A2fFf8SkDEJ8nzx b6FvJAiokjdqIti4; do
    [ -f "$DEST/voices/$v.safetensors" ] && [ "${1:-}" != "--force" ] && continue
    echo "  descarc voce $v"
    curl -sSL --fail -o "$DEST/voices/$v.safetensors" "$VOICES/$v.safetensors" || { echo "EROARE voce $v"; exit 1; }
done
curl -sSL --fail -o "$DEST/voices.jsonl" "$VOICES/../voices.jsonl" 2>/dev/null || true

# verificare: modelul trebuie sa aiba exact 64512352 octeti
SZ=$(stat -c%s "$DEST/model.q8.gguf" 2>/dev/null || echo 0)
if [ "$SZ" -lt 60000000 ]; then
    echo "EROARE: model.q8.gguf are $SZ octeti (asteptat ~64512352) - descarcarea a esuat"
    exit 1
fi
echo "[model] OK: $(du -sh "$DEST" | cut -f1)"
