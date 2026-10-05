#!/system/bin/sh
# build_apk.sh <project_dir> <package> <app_label> <out_apk>
# Pipeline build APK nativ pe device (fara Gradle). Proiectul trebuie sa aiba:
#   AndroidManifest.xml, res/, src/ (fisiere .kt)
# Rulat prin: /system/bin/sh build_apk.sh ...   (NU direct, se pierd permisiunile)
set -e
PROJ="$1"; PKG="$2"; LABEL="$3"; OUT="$4"
TC=/data/local/tmp/apkbuild
JH=$TC/jdk
export JAVA_HOME=$JH
export LD_LIBRARY_PATH=$TC/tlib:$JH/lib:$JH/lib/server
KL=$TC/kotlin/opt/kotlin/lib
KCP=$(ls $TC/classpath/*.jar 2>/dev/null | tr '\n' ':')
KOTLINC_CP="$KL/kotlin-compiler.jar:$KL/kotlin-stdlib.jar:$KL/kotlin-reflect.jar:$KL/kotlin-script-runtime.jar:$KL/trove4j.jar:$KL/annotations-13.0.jar"

echo "[1/6] aapt2 compile + link manifest+res"
cd "$PROJ"
$TC/aapt2/bin/aapt2 compile --dir res -o res.zip 2>&1 | grep -viE "No package ID" || true
test -f res.zip || { echo "EROARE: res.zip nu s-a generat"; exit 1; }
# resursele din AAR-urile androidx (appcompat/core) - necesare pt Theme.AppCompat
AARR=$TC/aar_res
for d in $AARR/*/; do
  nm=$(basename "$d")
  if [ -d "$d/res" ]; then $TC/aapt2/bin/aapt2 compile --dir "$d/res" -o "aarr_$nm.zip" 2>/dev/null || true; fi
done
EXTRA=$(ls aarr_*.zip 2>/dev/null | tr '\n' ' ')
# --extra-packages: genereaza R.java si pentru appcompat/core (altfel ClassNotFoundException androidx.appcompat.R$drawable)
$TC/aapt2/bin/aapt2 link -o base.apk -I $TC/android.jar \
  --manifest AndroidManifest.xml --java gen --auto-add-overlay \
  --extra-packages androidx.appcompat:androidx.core:androidx.fragment:androidx.lifecycle.runtime:androidx.lifecycle.viewmodel:androidx.lifecycle:androidx.savedstate:androidx.activity:androidx.loader:androidx.drawerlayout:androidx.customview:androidx.coordinatorlayout:androidx.emoji2 \
  $EXTRA res.zip 2>&1 | grep -viE "No package ID" || true
test -f base.apk || { echo "EROARE: base.apk nu s-a generat"; exit 1; }

echo "[2/6] kotlinc surse"
rm -rf classes && mkdir classes
find src gen -name "*.kt" -o -name "*.java" > sources.txt
$JH/bin/java -cp "$KOTLINC_CP" org.jetbrains.kotlin.cli.jvm.K2JVMCompiler \
  -cp "$TC/android.jar:$KCP" -d classes @sources.txt 2>&1 | grep -iE "error" | head -20 || true
# R.java-urile generate (agent2 + appcompat/core/fragment) le compilam cu javac
# (kotlinc nu garanteaza compilarea .java fara javac)
find gen -name "*.java" > rjava.txt
if [ -s rjava.txt ]; then
  $JH/bin/javac -cp "$TC/android.jar:$KCP" -d classes @rjava.txt 2>&1 | grep -i error | head -5 || true
fi
NCLS=$(find classes -name "*.class" | wc -l)
echo "      clase compilate: $NCLS"
test "$NCLS" -gt 0 || { echo "EROARE: 0 clase (verifica erorile de mai sus)"; exit 1; }

echo "[3/6] jar + d8 (dex)"
$JH/bin/jar cf classes.jar -C classes .
rm -rf dex && mkdir dex
# includem si kotlin-stdlib + dependintele runtime in dex (altfel ClassNotFoundException: kotlin.jvm.internal.Intrinsics)
RUNTIME="$KL/kotlin-stdlib.jar"
for j in $TC/classpath/*.jar; do RUNTIME="$RUNTIME $j"; done
$JH/bin/java -cp $TC/d8/share/java/d8.jar com.android.tools.r8.D8 \
  --min-api 26 --lib $TC/android.jar --output dex classes.jar $RUNTIME 2>&1 | grep -i error | head -5 || true
test -f dex/classes.dex || { echo "EROARE: classes.dex nu s-a generat"; exit 1; }

echo "[4/6] ambalare dex + assets"
rm -rf stage && mkdir stage
cp base.apk stage/app.apk
cp dex/classes.dex stage/
cd stage
$JH/bin/jar uf app.apk classes.dex >/dev/null 2>&1
if [ -d "$PROJ/assets" ]; then $JH/bin/jar uf app.apk -C "$PROJ" assets >/dev/null 2>&1; fi
# libs native (jniLibs): trebuie sa fie in APK ca lib/arm64-v8a/*.so
if [ -d "$PROJ/lib" ]; then
  echo "      ambalez libs native..."
  $JH/bin/jar uf app.apk -C "$PROJ" lib >/dev/null 2>&1
fi
cd "$PROJ"

echo "[5/6] semnare"
if [ ! -f "$PROJ/../release.keystore" ]; then
  $JH/bin/keytool -genkeypair -keystore "$PROJ/../release.keystore" -alias rel \
    -keyalg RSA -keysize 2048 -validity 10000 -storepass agent123 -keypass agent123 \
    -dname "CN=$LABEL, O=Agent, C=RO" >/dev/null 2>&1
fi
$JH/bin/java -jar $TC/apksigner/share/java/apksigner.jar sign \
  --ks "$PROJ/../release.keystore" --ks-pass pass:agent123 --key-pass pass:agent123 \
  --out "$OUT" stage/app.apk

echo "[6/6] verificare"
$JH/bin/java -jar $TC/apksigner/share/java/apksigner.jar verify --print-certs "$OUT" 2>&1 | head -2
ls -la "$OUT"
echo "BUILD OK: $OUT"
