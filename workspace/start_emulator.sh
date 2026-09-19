#!/bin/bash
# Porneste emulatorul Android16 in background, detasat de shell.
cd /home/gab/Desktop/agent/workspace
source ./env.sh
export PATH=$ANDROID_HOME/emulator:$PATH
# AVD-ul e in ~/.config/.android/avd din cauza XDG_CONFIG_HOME; emulatorul il cauta in ~/.android/avd
export ANDROID_AVD_HOME=$HOME/.config/.android/avd
mkdir -p logs
exec $ANDROID_HOME/emulator/emulator -avd Android16 -no-snapshot-save -no-audio -no-window -gpu swiftshader_indirect -no-boot-anim >> logs/emulator.log 2>&1
