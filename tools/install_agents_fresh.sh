#!/bin/bash
# Instalare de la ZERO a ambilor agenti (telefon gol dupa wipe).
set -u
ADB="${ADB:-/home/gab/android/platform-tools/adb}"
R=/home/gab/Desktop/android_agent
A_MAIN="$R/workspace/app/net.sys32.agent/app/build/outputs/apk/debug/app-debug.apk"
A_ODC="$R/odc_agent/app/build/outputs/apk/debug/app-debug.apk"
log(){ echo "[$(date +%H:%M:%S)] $*"; }

log "push net.sys32.agent ($(stat -c %s "$A_MAIN") bytes)"
"$ADB" push "$A_MAIN" /data/local/tmp/agent.apk 2>&1 | tail -1
log "install net.sys32.agent"
"$ADB" shell 'pm install -r --bypass-low-target-sdk-block /data/local/tmp/agent.apk' 2>&1 | tr -d '\r' | tail -1

log "push odc_agent ($(stat -c %s "$A_ODC") bytes)"
"$ADB" push "$A_ODC" /data/local/tmp/odc.apk 2>&1 | tail -1
log "install net.sys32.odc_agent"
"$ADB" shell 'pm install -r --bypass-low-target-sdk-block /data/local/tmp/odc.apk' 2>&1 | tr -d '\r' | tail -1

log "pornesc ambii agenti"
"$ADB" shell 'am start -n net.sys32.agent/.MainActivity' >/dev/null 2>&1
sleep 5
"$ADB" shell 'am start -n net.sys32.odc_agent/.MainActivity' >/dev/null 2>&1
sleep 5
"$ADB" shell 'settings put secure enabled_accessibility_services net.sys32.agent/net.sys32.agent.AgentAccessibilityService; settings put secure accessibility_enabled 1'

log "verificare"
"$ADB" shell 'pm list packages | grep sys32; echo ---; dumpsys package net.sys32.agent | grep -E "lastUpdateTime|versionName"; dumpsys package net.sys32.odc_agent | grep lastUpdateTime; echo ---; ps -A -o PID,PPID,NAME | grep -E "sys32|libpyexec"'
log "GATA (extractia assets-urilor la prima rulare dureaza cateva minute)"
