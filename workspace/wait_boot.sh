#!/bin/bash
cd /home/gab/Desktop/agent/workspace
source ./env.sh
adb wait-for-device
out=logs/boot_status.txt
: > $out
for i in $(seq 1 60); do
  bc=$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')
  echo "t=$((i*5))s boot_completed=[$bc]" >> $out
  if [ "$bc" = "1" ]; then echo "OK BOOT COMPLETE" >> $out; break; fi
  sleep 5
done
adb devices >> $out 2>&1
