#!/bin/bash
# Build + install APK pe emulator/device. Ruleaza: ./build_app.sh
set -e
cd "$(dirname "$0")/net.sys32.agent"
export JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64
export ANDROID_HOME=/home/gab/android
export ANDROID_SDK_ROOT=/home/gab/android
export PATH=$JAVA_HOME/bin:$ANDROID_HOME/platform-tools:$PATH

./gradlew assembleDebug
APK=app/build/outputs/apk/debug/app-debug.apk
echo "APK: $APK ($(du -h $APK | cut -f1))"
adb install -r "$APK"
adb shell am start -n net.sys32.agent/.MainActivity
echo "gata."
