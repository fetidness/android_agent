#!/bin/bash
# make_agent_variant.sh — genereaza o VARIANTA a agentului din sursa CANONICA unica.
#
#   usage: tools/make_agent_variant.sh <PKG> <LABEL> <DEST> [--flat]
#
#   <PKG>    applicationId / namespace / pachet Kotlin, ex: net.sys32.odc_agent
#   <LABEL>  numele afisat (launcher + notificari),  ex: "ODC Agent"
#   <DEST>   directorul de iesire (se RECREEAZA)
#   --flat   layout "plat" pentru build_apk.sh pe device (AndroidManifest.xml + res/ +
#            src/ + assets/ in radacina, cu package= si <uses-sdk> injectate).
#            fara --flat  -> proiect Gradle normal (app/src/main/...).
#
# SURSA CANONICA: workspace/app/net.sys32.agent (pachet net.sys32.agent).
# Singura diferenta intre cei doi agenti este pachetul + eticheta: tot restul
# (Python, Kotlin, manifest, resurse, gradle) e generat de aici.
set -euo pipefail

PKG="${1:?usage: make_agent_variant.sh <PKG> <LABEL> <DEST> [--flat]}"
LABEL="${2:?lipseste LABEL}"
DEST="${3:?lipseste DEST}"
MODE="${4:-gradle}"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CANON="${CANON:-$ROOT/workspace/app/net.sys32.agent}"
FROM="net.sys32.agent"
LONG="${PKG//./\/}"           # net/sys32/odc_agent
LAST="${PKG##*.}"             # odc_agent

[ -d "$CANON/app/src/main" ] || { echo "EROARE: sursa canonica lipseste: $CANON"; exit 1; }
[ "$PKG" != "$FROM" ] || { echo "EROARE: PKG nu poate fi chiar sursa canonica ($FROM)"; exit 1; }

echo "[1/5] copiez sursa canonica -> $DEST"
rm -rf "$DEST"; mkdir -p "$DEST"
tar -C "$CANON" \
    --exclude=build --exclude=app/build --exclude=.gradle --exclude=.kotlin \
    --exclude='*.pyc' --exclude=__pycache__ --exclude=.git \
    -cf - . | tar -C "$DEST" -xf -

echo "[2/5] rescriu pachetul $FROM -> $PKG"
# fisiere text care pot contine numele pachetului
mapfile -t FILES < <(grep -rl --binary-files=without-match "$FROM" "$DEST" 2>/dev/null || true)
if [ "${#FILES[@]}" -gt 0 ]; then sed -i "s|${FROM}|${PKG}|g" "${FILES[@]}"; fi
echo "      fisiere modificate: ${#FILES[@]}"

echo "[3/5] redenumesc directorul Kotlin"
mv "$DEST/app/src/main/java/net/sys32/agent" "$DEST/app/src/main/java/$LONG"

echo "[4/5] eticheta: \"$LABEL\""
sed -i "s|android:label=\"Agent|android:label=\"$LABEL|g" "$DEST/app/src/main/AndroidManifest.xml"
sed -i "s|<string name=\"app_name\">Agent</string>|<string name=\"app_name\">$LABEL</string>|" \
       "$DEST/app/src/main/res/values/strings.xml"
grep -q "<string name=\"app_name\">$LABEL</string>" "$DEST/app/src/main/res/values/strings.xml" \
    || { echo "EROARE: app_name nu s-a schimbat"; exit 1; }

if [ "$MODE" = "--flat" ]; then
  echo "[5/5] layout PLAT pentru build_apk.sh (device)"
  M="$DEST/app/src/main"
  rm -rf "$DEST/_flat"; mkdir -p "$DEST/_flat"
  cp -a "$M/AndroidManifest.xml" "$DEST/_flat/"
  cp -a "$M/res"   "$DEST/_flat/"
  mkdir -p "$DEST/_flat/src"
  if [ -d "$M/src" ]; then cp -a "$M/src/." "$DEST/_flat/src/"; fi
  cp -a "$M/java/net" "$DEST/_flat/src/"     # src/net/sys32/<pkg>/*.kt  (build_apk.sh: find src -name '*.kt')
  if [ -d "$M/assets" ]; then cp -a "$M/assets" "$DEST/_flat/"; fi
  # manifestul pentru build MANUAL are nevoie de package= si de <uses-sdk>
  python3 - "$DEST/_flat/AndroidManifest.xml" "$PKG" <<'PY'
import sys, re
p, pkg = sys.argv[1], sys.argv[2]
s = open(p, encoding="utf-8").read()
if 'package="' not in s.split('>')[0]:
    s = s.replace('<manifest ', f'<manifest package="{pkg}" ', 1)
if '<uses-sdk' not in s:
    s = re.sub(r'(<manifest[^>]*>)',
               r'\1\n    <uses-sdk android:minSdkVersion="26" android:targetSdkVersion="34"/>', s, count=1)
open(p, "w", encoding="utf-8").write(s)
print("      manifest plat: package= si <uses-sdk> injectate")
PY
  mv "$DEST/_flat" "$DEST/flat"
  rm -rf "$DEST/app" "$DEST/build.gradle.kts" "$DEST/settings.gradle.kts" "$DEST/gradle" "$DEST/gradlew"* "$DEST/gradle.properties"
fi

echo "GATA: $DEST  (PKG=$PKG, LABEL=$LABEL, MODE=$MODE)"
