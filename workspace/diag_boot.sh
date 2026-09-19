#!/bin/bash
# Diagnostic boot: kernel log vizibil + verbose, GPU host (NVIDIA)
cd /home/gab/Desktop/agent/workspace
source ./env.sh
export PATH=$ANDROID_HOME/emulator:$PATH
export ANDROID_AVD_HOME=$HOME/.config/.android/avd
export DISPLAY=:0
export __NV_PRIME_RENDER_OFFLOAD=1
export __GLX_VENDOR_LIBRARY_NAME=nvidia
export VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/nvidia_icd.json

mkdir -p logs
exec $ANDROID_HOME/emulator/emulator -avd Android16 \
  -no-snapshot -no-audio -no-boot-anim -no-metrics \
  -gpu host -show-kernel -verbose \
  >> logs/emulator_kernel.log 2>&1
