#!/bin/bash
# fetch_rootfs.sh - asigura imaginea rootfs Debian din APK (out of the box pe o clona noua).
# Binarele NU stau in git: le aduce tools/bootstrap_binaries.sh din APK-ul existent (dist/)
# sau le construieste tools/build_rootfs.sh (debootstrap). Aici doar verificam.
A=app/src/main/assets/proot/agentroot.tar.gz
if [ -f "$A" ]; then
    echo "[rootfs] ok: $A ($(du -h "$A" | cut -f1))"
    exit 0
fi
if [ -f tools/bootstrap_binaries.sh ]; then
    echo "[rootfs] lipseste $A -> bootstrap_binaries.sh"
    bash tools/bootstrap_binaries.sh || true
fi
[ -f "$A" ] || { echo "[rootfs] LIPSESTE $A: ruleaza 'sudo tools/build_rootfs.sh' o singura data"; exit 1; }
