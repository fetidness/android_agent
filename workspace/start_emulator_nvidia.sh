#!/bin/bash
# Porneste emulatorul Android16 CU GUI, fortand randarea pe GPU-ul NVIDIA dedicat
# (sistem hibrid: iGPU AMD Raven + NVIDIA GTX 1660 Ti; folosim PRIME render offload).
cd /home/gab/Desktop/agent/workspace
source ./env.sh
export PATH=$ANDROID_HOME/emulator:$PATH
export ANDROID_AVD_HOME=$HOME/.config/.android/avd
export DISPLAY=:0

# --- fortare NVIDIA ---
export __NV_PRIME_RENDER_OFFLOAD=1
export __GLX_VENDOR_LIBRARY_NAME=nvidia
export __VK_LAYER_NV_optimus=NVIDIA_only
export VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/nvidia_icd.json
export __EGL_VENDOR_LIBRARY_FILENAMES=/usr/share/glvnd/egl_vendor.d/10_nvidia.json

mkdir -p logs
exec $ANDROID_HOME/emulator/emulator -avd Android16 \
  -no-snapshot -no-audio -no-boot-anim -no-metrics \
  -gpu host \
  >> logs/emulator_nvidia.log 2>&1
