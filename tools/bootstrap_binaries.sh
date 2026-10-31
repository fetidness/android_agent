#!/bin/bash
# bootstrap_binaries.sh - aduce in proiect binarele care NU stau in git.
#
# De ce: o clona noua are doar SURSELE. Jocurile de binare (toolchain 1 GB, jniLibs 430 MB,
# modelele vocale/STT) sunt ignorate de .gitignore pentru ca nu au ce cauta in git. Acest
# script le extrage din APK-ul existent, ca build-ul sa functioneze fara pasi manuali.
#
#   bash bootstrap_binaries.sh <cale-catre-APK>
#   bash bootstrap_binaries.sh --from-device      # ia APK-ul instalat de pe telefon (adb)
#
# Idempotent: sare peste fisierele care exista deja cu dimensiunea corecta.
# Verificare: la final ruleaza `gradle assembleDebug` daca --check e dat.
set -euo pipefail
# ruleaza din ORICE director: scriptul sta in tools/, proiectul in workspace/app/net.sys32.agent
REPO="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
PROJ="$REPO/workspace/app/net.sys32.agent"
[ -d "$PROJ" ] || { echo "[bootstrap] EROARE: nu gasesc proiectul in $PROJ" >&2; exit 1; }
cd "$PROJ"
APP=app/src/main

say() { echo "[bootstrap] $*"; }
die() { echo "[bootstrap] EROARE: $*" >&2; exit 1; }

APK=""
FROM_DEVICE=0
CHECK=0
for a in "$@"; do
  case "$a" in
    --from-device) FROM_DEVICE=1 ;;
    --check)       CHECK=1 ;;
    -*)            die "optiune necunoscuta: $a" ;;
    *)             APK="$a" ;;
  esac
done

# ---------------------------------------------------------------- sursa APK
TMPD=$(mktemp -d)
trap 'rm -rf "$TMPD"' EXIT

if [ "$FROM_DEVICE" = "1" ]; then
  command -v adb >/dev/null || die "adb lipseste din PATH"
  PKG=$(adb shell pm path net.sys32.agent 2>/dev/null | head -1 | tr -d '\r' | cut -d: -f2)
  [ -n "$PKG" ] || die "net.sys32.agent nu e instalat pe device (sau adb nu e autorizat)"
  say "extrag APK-ul de pe device: $PKG"
  adb pull "$PKG" "$TMPD/base.apk" >/dev/null || die "nu pot trage APK-ul"
  APK="$TMPD/base.apk"
fi

[ -n "$APK" ] || die "da calea catre APK: bash bootstrap_binaries.sh <apk> | --from-device"
[ -f "$APK" ] || die "APK inexistent: $APK"
say "APK: $APK ($(( $(stat -c%s "$APK") / 1024 / 1024 )) MB)"

command -v unzip >/dev/null || die "unzip lipseste"

# lista de intrari din APK, calculata O SINGURA DATA.
# ATENTIE: `unzip -Z1 "$APK" | grep -q ...` sub `set -o pipefail` da rezultat GRESIT
# (grep -q iese la primul match -> SIGPIPE pe unzip -> pipefail face conditia falsa).
LIST="$TMPD/list.txt"
unzip -Z1 "$APK" > "$LIST" || die "nu pot citi APK-ul"

# ---------------------------------------------------------------- 1. jniLibs
# binarele executabile si .so-urile: lib/arm64-v8a/<name> -> jniLibs/arm64-v8a/<name>
NB=0
mkdir -p "$APP/jniLibs/arm64-v8a"
for f in $(grep '^lib/arm64-v8a/' "$LIST"); do
  name=$(basename "$f")
  dst="$APP/jniLibs/arm64-v8a/$name"
  # .so-urile URMARITE de git (ex. libptts_ffi) nu se ating - vin din repo
  if git ls-files --error-unmatch "$dst" >/dev/null 2>&1; then continue; fi
  if [ -f "$dst" ] && [ "$(stat -c%s "$dst")" = "$(unzip -l "$APK" "$f" | awk 'NR==4{print $1}')" ]; then continue; fi
  unzip -o -q -j "$APK" "$f" -d "$APP/jniLibs/arm64-v8a"
  chmod 755 "$dst" 2>/dev/null || true
  NB=$((NB+1))
done
say "jniLibs: $NB fisiere extrase ($(ls "$APP/jniLibs/arm64-v8a" | wc -l) in total)"

# ---------------------------------------------------------------- 2. assets/toolchain
# 1 GB: clang, lld, sysroot, rust, cargo, cmake, perl, deps
if [ -d "$APP/assets/toolchain/bin" ]; then
  say "assets/toolchain: deja prezent - sar"
else
  say "assets/toolchain: extrag (~1056 MB, dureaza)"
  mkdir -p "$APP/assets"
  unzip -o -q "$APK" 'assets/toolchain/*' -d "$APP/assets/tmp_tc"
  mv "$APP/assets/tmp_tc/assets/toolchain" "$APP/assets/toolchain"
  rm -rf "$APP/assets/tmp_tc"
  say "assets/toolchain: $(find "$APP/assets/toolchain" -type f | wc -l) fisiere"
fi

# ---------------------------------------------------------------- 3. modelul vocal (Phonon)
if [ -f "$APP/assets/models/phonon-31m-en/model.q8.gguf" ]; then
  say "assets/models (voce): deja prezent - sar"
else
  say "assets/models (voce): extrag din APK..."
  mkdir -p "$APP/assets"
  unzip -o -q "$APK" 'assets/models/*' -d "$APP/assets/tmp_md"
  mkdir -p "$APP/assets/models"
  cp -r "$APP/assets/tmp_md/assets/models/." "$APP/assets/models/"
  rm -rf "$APP/assets/tmp_md"
  say "assets/models: ok ($(du -sh "$APP/assets/models" | cut -f1))"
fi

# ---------------------------------------------------------------- 4. modelul STT (Whisper)
if [ -f "$APP/assets/whisper/models/ggml-medium.bin" ]; then
  say "assets/whisper (STT): deja prezent - sar"
else
  say "assets/whisper (STT): il iau din APK daca exista, altfel il descarc"
  mkdir -p "$APP/assets/whisper/models"
  if grep -q '^assets/whisper/models/' "$LIST"; then
    say "assets/whisper (STT): extrag din APK (fara descarcare)"
    unzip -o -q "$APK" 'assets/whisper/models/*' -d "$APP/assets/tmp_wh"
    cp -f "$APP/assets/tmp_wh/assets/whisper/models/"*.bin "$APP/assets/whisper/models/"
    rm -rf "$APP/assets/tmp_wh"
  else
    say "assets/whisper (STT): nu e in APK - il descarc (1.5 GB)"
    bash "$PROJ/fetch_whisper.sh"
  fi
fi

# ---------------------------------------------------------------- 5. proot (rootfs Debian)
if [ -d "$APP/assets/proot" ] && [ "$(ls "$APP/assets/proot" | wc -l)" -gt 1 ]; then
  say "assets/proot: deja prezent - sar"
else
  say "assets/proot: extrag din APK..."
  mkdir -p "$APP/assets/proot"
  unzip -o -q "$APK" 'assets/proot/*' -d "$APP/assets/tmp_pr" || true
  if [ -d "$APP/assets/tmp_pr/assets/proot" ]; then
    cp -rf "$APP/assets/tmp_pr/assets/proot/." "$APP/assets/proot/"
  fi
  rm -rf "$APP/assets/tmp_pr"
  say "assets/proot: $(ls "$APP/assets/proot" | wc -l) fisiere"
fi

# ---------------------------------------------------------------- 5b. assets/android_build
# 399 MB: JDK + Gradle + build-tools + platform, folosite de build_apk (build PE TELEFON).
# Fara ele aplicatia porneste, dar tool-ul `build_apk` nu poate compila nimic.
if [ -d "$APP/assets/android_build" ] && [ "$(ls "$APP/assets/android_build" | wc -l)" -gt 1 ]; then
  say "assets/android_build: deja prezent - sar"
elif grep -q '^assets/android_build/' "$LIST"; then
  say "assets/android_build: extrag din APK (~399 MB)"
  unzip -o -q "$APK" 'assets/android_build/*' -d "$APP/assets/tmp_ab"
  mkdir -p "$APP/assets/android_build"
  cp -rf "$APP/assets/tmp_ab/assets/android_build/." "$APP/assets/android_build/"
  rm -rf "$APP/assets/tmp_ab"
  say "assets/android_build: $(ls "$APP/assets/android_build" | wc -l) fisiere"
else
  say "ATENTIE: assets/android_build lipseste din APK - build_apk (pe telefon) nu va functiona"
fi

# ---------------------------------------------------------------- 6. local.properties (sdk.dir)
# e in .gitignore, deci lipseste la o clona; fara el Gradle da "SDK location not found"
if [ ! -f "local.properties" ] || ! grep -q '^sdk.dir=' local.properties 2>/dev/null; then
  SDK="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-}}"
  if [ -z "$SDK" ]; then
    # cai uzuale pe acest host; daca niciuna nu exista, cerem explicit
    for c in /home/gab/Work/Android "$HOME/Android/Sdk" "$HOME/Android/sdk"; do
      [ -d "$c/platforms" ] && SDK="$c" && break
    done
  fi
  if [ -n "$SDK" ] && [ -d "$SDK" ]; then
    echo "sdk.dir=$SDK" > local.properties
    say "local.properties: sdk.dir=$SDK"
  else
    say "ATENTIE: nu am gasit SDK-ul Android. Scrie manual: sdk.dir=<cale> in local.properties"
  fi
fi

say "GATA. Acum: JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 gradle --offline assembleDebug"

if [ "$CHECK" = "1" ]; then
  say "verificare: build..."
  cd ..
  JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
    /home/gab/Work/Android/gradle-8.11.1/bin/gradle --offline assembleDebug 2>&1 | tail -5
fi
