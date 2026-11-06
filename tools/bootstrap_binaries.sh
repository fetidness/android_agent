#!/bin/bash
# bootstrap_binaries.sh - aduce in proiect binarele care NU stau in git.
#
# De ce: o clona noua are doar SURSELE. Jocurile de binare (toolchain 1 GB, jniLibs 430 MB,
# modelele vocale/STT) sunt ignorate de .gitignore pentru ca nu au ce cauta in git. Acest
# script le extrage din APK-ul existent, ca build-ul sa functioneze fara pasi manuali.
#
#   bash tools/bootstrap_binaries.sh                 # ia automat cel mai nou APK din dist/
#   bash tools/bootstrap_binaries.sh <cale-catre-APK> # un APK anume
#   bash tools/bootstrap_binaries.sh --from-device    # AVARIE: de pe telefon, prin adb
#
# Locul fix al APK-ului este dist/ (ignorat de git). Fara telefon, fara adb.
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
  # optiune de AVARIE: ia APK-ul de pe telefon. Modul normal e din dist/ (fara telefon).
  command -v adb >/dev/null || die "adb lipseste din PATH"
  PKG=$(adb shell pm path net.sys32.agent 2>/dev/null | head -1 | tr -d '\r' | cut -d: -f2)
  [ -n "$PKG" ] || die "net.sys32.agent nu e instalat pe device (sau adb nu e autorizat).\n         Modul normal NU cere telefon: pune APK-ul in dist/ si ruleaza fara argument."
  say "extrag APK-ul de pe device: $PKG"
  adb pull "$PKG" "$TMPD/base.apk" >/dev/null || die "nu pot trage APK-ul"
  APK="$TMPD/base.apk"
fi

# fara argument: caut automat in dist/ (locul fix, independent de telefon)
if [ -z "$APK" ]; then
  say "caut APK-ul in $REPO/dist/ ..."
  NEWEST=$(ls -t "$REPO"/dist/*.apk 2>/dev/null | head -1 || true)
  if [ -n "$NEWEST" ]; then
    APK="$NEWEST"
    say "folosesc: ${APK#$REPO/} ($(( $(stat -c%s "$APK") / 1024 / 1024 )) MB)"
  else
    die "nu gasesc niciun APK in $REPO/dist/\n         Pune APK-ul complet acolo (ex: dist/net.sys32.agent.apk) si ruleaza din nou:\n           cp /cale/app-debug.apk $REPO/dist/\n           bash tools/bootstrap_binaries.sh"
  fi
fi

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
# ★ FIX (6 nov 2026): guard-ul vechi verifica `toolchain/bin`, care NU EXISTA in structura
# livrata (toolchain are cmake/ deps/ lib/ perl/ pyinc/ rust-libs.tar sysroot/). Conditia era
# mereu falsa -> re-extragea 1 GB la FIECARE rulare si apoi `mv` cadea cu
# "cannot overwrite '.../toolchain/toolchain': Directory not empty" (rm -rf nu se facea).
if [ -d "$APP/assets/toolchain/deps" ] && [ -d "$APP/assets/toolchain/sysroot" ]; then
  say "assets/toolchain: deja prezent - sar"
else
  say "assets/toolchain: extrag (~1056 MB, dureaza)"
  mkdir -p "$APP/assets"
  unzip -o -q "$APK" 'assets/toolchain/*' -d "$APP/assets/tmp_tc"
  rm -rf "$APP/assets/toolchain"
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
  # ★ FIX (6 nov 2026): AGP DEZARHIVEAZA asset-urile .gz la impachetare (AGP asset compression),
  # deci in APK arhiva apare ca `agentroot.tar` (539 MB), NU ca `agentroot.tar.gz`.
  # `fetch_rootfs.sh` si build.gradle.kts cer insa `agentroot.tar.gz`, deci fara recompresie
  # build-ul cade cu "[rootfs] LIPSESTE ... ruleaza sudo tools/build_rootfs.sh".
  # Recomprimem in loc (rapid: gzip -1), ca o clona noua sa construiasca out of the box.
  for _t in "$APP/assets/proot/"*.tar; do
    [ -f "$_t" ] || continue
    if [ ! -f "${_t}.gz" ]; then
      say "assets/proot: recompresez $(basename "$_t") -> $(basename "$_t").gz"
      gzip -1 -c "$_t" > "${_t}.gz" && rm -f "$_t"
    fi
  done
  say "assets/proot: $(ls "$APP/assets/proot" | wc -l) fisiere ($(du -sh "$APP/assets/proot" | cut -f1))"
fi

# ---------------------------------------------------------------- 5a. assets/python/Lib (STDLIB CPython)
# ★ CRITIC (descoperit 6 nov 2026): `assets/python/Lib/` = stdlib-ul CPython (190 entries,
# ~110 MB, 3822 fisiere in APK). E in .gitignore, deci NU vine cu clona. Fara el aplicatia
# porneste, arata "First-time setup", ajunge la "Libraries" si ACOLO SE BLOCHEAZA DEFINITIV:
# libpyexec nu poate porni (ModuleNotFoundError: threading) si nu exista nici markerul
# .stdlib_ok, deci setup-ul asteapta la infinit fara nicio eroare pe ecran.
# Verificat: APK-ul construit fara Lib/ avea 3264 fisiere in Lib/ (doar site-packages),
# cel corect are 3822 (stdlib complet + site-packages).
if [ -f "$APP/assets/python/Lib/threading.py" ]; then
  say "assets/python/Lib: deja prezent - sar"
elif grep -q '^assets/python/Lib/' "$LIST"; then
  say "assets/python/Lib: extrag stdlib CPython din APK (~110 MB)"
  rm -rf "$APP/assets/tmp_py"
  unzip -o -q "$APK" 'assets/python/Lib/*' -d "$APP/assets/tmp_py"
  mkdir -p "$APP/assets/python"
  cp -rf "$APP/assets/tmp_py/assets/python/Lib" "$APP/assets/python/"
  rm -rf "$APP/assets/tmp_py"
  say "assets/python/Lib: $(find "$APP/assets/python/Lib" -type f | wc -l) fisiere"
else
  say "EROARE: assets/python/Lib lipseste din APK - stdlib-ul CPython nu poate fi adus"
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

# ---------------------------------------------------------------- 7. VERIFICARE CRITICA
# Un bootstrap care raporteaza "GATA" dar lasa proiectul fara stdlib produce un APK care se
# instaleaza si apoi se blocheaza la "Libraries" pe telefon - fara nicio eroare vizibila.
# De aceea verificam EFECTIV fisierele de care depinde pornirea Python, nu doar exit code-ul.
MISSING=""
check_file() { [ -e "$1" ] || MISSING="$MISSING\n  - $1"; }
check_file "$APP/assets/python/agent.py"
check_file "$APP/assets/python/Lib/threading.py"
check_file "$APP/assets/python/Lib/os.py"
check_file "$APP/assets/python/Lib/encodings/__init__.py"
check_file "$APP/assets/python/Lib/site-packages/_brotli.cpython-314-aarch64-linux-android.so"
check_file "$APP/assets/python/Lib/site-packages/_quickjs.so"
check_file "$APP/assets/proot/agentroot.tar.gz"
check_file "$APP/assets/toolchain/deps"
[ -d "$APP/jniLibs/arm64-v8a" ] || MISSING="$MISSING\n  - $APP/jniLibs/arm64-v8a"
if [ -n "$MISSING" ]; then
  echo "[bootstrap] EROARE: lipsesc componente critice:$MISSING" >&2
  echo "[bootstrap] APK-ul construit ar parea OK, dar aplicatia s-ar bloca la 'Libraries'." >&2
  exit 1
fi
say "verificare: toate componentele critice prezente (stdlib, brotli, quickjs, rootfs, toolchain)"

say "GATA. Acum: JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 gradle --offline assembleDebug"

if [ "$CHECK" = "1" ]; then
  say "verificare: build..."
  cd ..
  JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
    /home/gab/Work/Android/gradle-8.11.1/bin/gradle --offline assembleDebug 2>&1 | tail -5
fi
