#!/usr/bin/env bash
# ============================================================================
# build_odc_agent.sh — construieste odc_agent.apk COMPLET OFFLINE, pe PC.
# ============================================================================
# Rezultat: odc_agent.apk (toate uneltele incluse) -> la instalare pe telefon
# poate compila APK-uri Android pe device, fara net.
#
# PRINCIPIU:
#   - jniLibs/*.so si assets/toolchain/ sunt aarch64 (pentru TELEFON) — se copiaza ca atare.
#   - uneltele de BUILD (aapt2, javac, kotlinc, d8, apksigner) ruleaza pe PC (x86_64).
#   - JAR-urile (kotlinc, d8, apksigner) sunt portabile si vin in ./deps/.
#   - aapt2 + JDK = se iau x86_64 (scriptul le descarca daca lipsesc).
#
# Necesita: JDK 17+ (bin/java), curl/wget, unzip.
# Rulat: ./build_odc_agent.sh
# ============================================================================
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="$HERE/odc_agent/app/src/main"
DEPS="$HERE/deps"
OUT="$HERE/odc_agent.apk"

echo "=== build odc_agent APK pentru telefon (offline-capable) ==="
[ -d "$SRC/jniLibs" ] || { echo "EROARE: lipseste $SRC/jniLibs"; exit 1; }

# --- JDK (sistem sau JAVA_HOME) ---
JAVA="${JAVA_HOME:+$JAVA_HOME/bin/java}"; JAVA="${JAVA:-$(command -v java || true)}"
[ -n "$JAVA" ] || { echo "EROARE: JDK lipsa. Instaleaza JDK 17+ sau seteaza JAVA_HOME."; exit 1; }
JAVA_DIR="$(dirname "$(readlink -f "$JAVA")")"
echo "JDK: $JAVA_DIR"

# --- aapt2 x86_64 ---
AAPT2="$DEPS/aapt2"
if [ ! -x "$AAPT2" ]; then
  echo "[aapt2] descarc build-tools x86_64..."
  mkdir -p "$DEPS/_bt"
  if command -v curl >/dev/null; then curl -fL -o "$DEPS/_bt.zip" https://dl.google.com/android/repository/build-tools_r36_linux.zip
  else wget -O "$DEPS/_bt.zip" https://dl.google.com/android/repository/build-tools_r36_linux.zip; fi
  ( cd "$DEPS/_bt" && unzip -qo ../_bt.zip && cp */aapt2 "$AAPT2" )
fi
chmod +x "$AAPT2" 2>/dev/null || true
[ -x "$AAPT2" ] || { echo "EROARE: aapt2 x86_64 lipsa. Pune un aapt2 linux-x86_64 in $DEPS/aapt2"; exit 1; }

# --- android.jar ---
AJAR="$DEPS/android.jar"
if [ ! -f "$AJAR" ]; then
  echo "[android.jar] descarc platform-36..."
  mkdir -p "$DEPS/_plat"
  ( command -v curl >/dev/null && curl -fL -o "$DEPS/_plat.zip" https://dl.google.com/android/repository/platform-36_r01.zip ) || wget -O "$DEPS/_plat.zip" https://dl.google.com/android/repository/platform-36_r01.zip
  ( cd "$DEPS/_plat" && unzip -qo ../_plat.zip && cp android-36/android.jar "$AJAR" )
fi

# --- JAR-uri portabile (vin in kit) ---
KL="$DEPS/kotlinc/lib"
D8JAR="$DEPS/d8/lib/d8.jar"
SIGNJAR="$DEPS/apksigner/lib/apksigner.jar"
[ -f "$D8JAR" ]     || { echo "EROARE: lipseste $D8JAR"; exit 1; }
[ -f "$SIGNJAR" ]   || { echo "EROARE: lipseste $SIGNJAR"; exit 1; }
KOTLINC_CP="$KL/kotlin-compiler.jar:$KL/kotlin-stdlib.jar:$KL/kotlin-reflect.jar:$KL/kotlin-script-runtime.jar:$KL/trove4j.jar:$KL/annotations-13.0.jar"
KCP="$(ls "$DEPS"/classpath/*.jar 2>/dev/null | tr '\n' ':')"

# --- ambalare structura ---
WORK="$HERE/_build"; rm -rf "$WORK"; mkdir -p "$WORK"
cp "$SRC/AndroidManifest.xml" "$WORK/"
cp -r "$SRC/res" "$WORK/"
cp -r "$SRC/java" "$WORK/src"
cp -r "$SRC/assets" "$WORK/assets"
mkdir -p "$WORK/lib"; cp -r "$SRC/jniLibs/arm64-v8a" "$WORK/lib/arm64-v8a"
cd "$WORK"

echo "[1/5] aapt2 compile+link"
"$AAPT2" compile --dir res -o res.zip
"$AAPT2" link -o base.apk -I "$AJAR" --manifest AndroidManifest.xml --java gen --auto-add-overlay res.zip 2>&1 | grep -v "No package ID" || true

echo "[2/5] kotlinc"
mkdir -p classes
find src gen -name "*.kt" -o -name "*.java" > sources.txt
"$JAVA" -cp "$KOTLINC_CP" org.jetbrains.kotlin.cli.jvm.K2JVMCompiler -cp "$AJAR:$KCP" -d classes @sources.txt 2>&1 | grep -iE "error:" || true
find gen -name "*.java" > rjava.txt
[ -s rjava.txt ] && "$JAVA_DIR/javac" -cp "$AJAR:$KCP" -d classes @rjava.txt 2>/dev/null || true

echo "[3/5] jar + d8"
"$JAVA_DIR/jar" cf classes.jar -C classes .
mkdir -p dex
"$JAVA" -cp "$D8JAR" com.android.tools.r8.D8 --min-api 26 --lib "$AJAR" --output dex classes.jar 2>&1 | grep -iE "error:" || true

echo "[4/5] ambalare"
STG="$WORK/stage"; mkdir -p "$STG"; cp base.apk "$STG/app.apk"; cp dex/classes.dex "$STG/"
cd "$STG"
"$JAVA_DIR/jar" uf app.apk classes.dex >/dev/null
"$JAVA_DIR/jar" uf app.apk -C "$WORK" assets >/dev/null 2>&1 || true
"$JAVA_DIR/jar" uf app.apk -C "$WORK" lib >/dev/null 2>&1 || true

echo "[5/5] semnare"
KS="$HERE/odc_agent.keystore"
[ -f "$KS" ] || "$JAVA_DIR/keytool" -genkeypair -keystore "$KS" -alias rel -keyalg RSA -keysize 2048 \
  -validity 10000 -storepass odc12345 -keypass odc12345 -dname "CN=ODC Agent,O=Agent,C=RO"
"$JAVA" -jar "$SIGNJAR" sign --ks "$KS" --ks-pass pass:odc12345 --key-pass pass:odc12345 --out "$OUT" "$STG/app.apk"

echo "=== GATA: $OUT ($(du -h "$OUT" | cut -f1)) ==="
echo "Instaleaza: adb install -r --bypass-low-target-sdk-block odc_agent.apk"
