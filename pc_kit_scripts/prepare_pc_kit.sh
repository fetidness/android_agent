#!/usr/bin/env bash
# ============================================================================
# prepare_pc_kit.sh — ruleaza pe DEVICE. Produce kitul PC (pc_kit/).
# ============================================================================
# Kitul contine:
#   odc_agent/           sursa completa (manifest, res, java, jniLibs aarch64,
#                        assets/python, assets/toolchain aarch64) - ~630 MB
#   deps/                unelte de BUILD portabile (kotlinc, d8, apksigner = JAR-uri),
#                        android.jar, classpath/ - ~90 MB
#   build_odc_agent.sh   scriptul de build (ruleaza pe PC)
#   prepare_pc_kit.sh    acest script
#
# Ce NU e in kit (PC-ul le ia singur sau le are):
#   JDK (PC), aapt2 x86_64 (PC descarca), uneltele Termux descarcabile
#
# Rulare pe device:  sh prepare_pc_kit.sh [dest]
# Apoi copiaza pc_kit/ pe PC si ruleaza ./build_odc_agent.sh
# ============================================================================
set -e
OUT="${1:-/sdcard/Download/Agent/workspace/pc_kit}"
SRC=/storage/emulated/0/Download/Agent/workspace/agent2/app/src/main
DEPS=/data/local/tmp/apkbuild

echo "=== pregatesc kit PC in $OUT ==="
mkdir -p "$OUT/odc_agent/app/src/main" "$OUT/deps/classpath" "$OUT/deps/kotlinc/lib" "$OUT/deps/d8/lib" "$OUT/deps/apksigner/lib"

echo "[1] sursa odc_agent..."
cp "$SRC/AndroidManifest.xml" "$OUT/odc_agent/app/src/main/"
cp -r "$SRC/res"     "$OUT/odc_agent/app/src/main/"
cp -r "$SRC/java"    "$OUT/odc_agent/app/src/main/"
cp -r "$SRC/jniLibs" "$OUT/odc_agent/app/src/main/"
mkdir -p "$OUT/odc_agent/app/src/main/assets"
cp -r "$SRC/assets/python"   "$OUT/odc_agent/app/src/main/assets/" 2>/dev/null || true
cp -r "$SRC/assets/fonts"    "$OUT/odc_agent/app/src/main/assets/" 2>/dev/null || true
cp -r "$SRC/assets/toolchain" "$OUT/odc_agent/app/src/main/assets/" 2>/dev/null || true
# android_build/ (descarcabilele) - PC le descarca; dar daca vrei 100% offline le copiez:
if [ "$2" = "--with-downloads" ]; then
  cp -r "$SRC/assets/android_build" "$OUT/odc_agent/app/src/main/assets/" 2>/dev/null || true
fi

echo "[2] unelte de BUILD portabile (JAR-uri)..."
cp "$DEPS/android.jar" "$OUT/deps/"
cp "$DEPS/kotlin/opt/kotlin/lib/"*.jar    "$OUT/deps/kotlinc/lib/" 2>/dev/null || true
cp "$DEPS/d8/share/java/d8.jar"           "$OUT/deps/d8/lib/" 2>/dev/null || true
cp "$DEPS/apksigner/share/java/apksigner.jar" "$OUT/deps/apksigner/lib/" 2>/dev/null || true
cp "$DEPS/classpath/"*.jar                "$OUT/deps/classpath/" 2>/dev/null || true

echo "[3] scriptul de build..."
cp "$OUT/prepare_pc_kit.sh" "$OUT/" 2>/dev/null || true

echo "=== kit gata: $OUT ==="
du -sh "$OUT"/* 2>/dev/null
echo ""
echo "PASI PE PC:"
echo "  1. copiaza tot folderul pc_kit/ pe PC"
echo "  2. cd pc_kit && chmod +x build_odc_agent.sh && ./build_odc_agent.sh"
echo "  3. rezulta odc_agent.apk -> adb install -r --bypass-low-target-sdk-block odc_agent.apk"
