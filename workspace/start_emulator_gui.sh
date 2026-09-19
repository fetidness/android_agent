#!/bin/bash
# Porneste emulatorul Android16 CU interfata grafica, randare hardware.
cd /home/gab/Desktop/agent/workspace
source ./env.sh
export PATH=$ANDROID_HOME/emulator:$PATH
export ANDROID_AVD_HOME=$HOME/.config/.android/avd
export DISPLAY=:0
mkdir -p logs
exec $ANDROID_HOME/emulator/emulator -avd Android16 \
  -no-snapshot -no-audio -no-boot-anim \
  -gpu host \
  -no-metrics \
  >> logs/emulator_gui.log 2>&1
