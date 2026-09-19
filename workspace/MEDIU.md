# Mediu dezvoltare Android - STARE (setup initial)

## Componente instalate / verificate
- JDK: OpenJDK 21.0.12.1 (Debian trixie)  -> /usr/lib/jvm/java-21-openjdk-amd64
- Gradle: 8.11.1                           -> /home/gab/android/gradle-8.11.1/bin/gradle
- Android SDK: /home/gab/android
  - platform-tools (adb 37.0.0)
  - cmdline-tools/latest (sdkmanager 12.0, avdmanager)
  - build-tools: 34.0.0, 35.0.0, 35.0.1, 36.0.0
  - platforms: android-31, 34, 35, 36
  - ndk: 27.1.12297006, 29.0.14206865
  - cmake: 3.22.1
  - emulator 36.5.11.0
  - system-images: android-33, 36.1, 36-ext19 (x86_64 google_apis)

## Cum activezi mediul
    source /home/gab/Desktop/agent/workspace/env.sh
(aceleasi variabile sunt si in ~/.bashrc pentru shell-uri noi)

## Variabile
JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64
ANDROID_HOME=/home/gab/android
ANDROID_SDK_ROOT=/home/gab/android

## Note
- OpenJDK 17 NU exista in Debian trixie; disponibil 21 (default-jdk) si 25.
- Am ales 21 (LTS, compatibil Gradle 8.11.1 + AGP).
- KVM disponibil (/dev/kvm) -> emulatorul ruleaza hardware-accelerat.
- Niciun AVD creat inca (avdmanager list avd -> gol).


## AVD: Android16 (CREAT SI FUNCTIONAL)
- Nume: Android16
- Imagine: system-images;android-36;google_apis;x86_64  (rev 7, Android 16 / API 36, STABILA)
- PlayStore: NU (tag google_apis, nu playstore)
- Device: pixel_7 | 1080x2400 | 4 GB RAM | 6 cores | 8 GB storage
- Boot: ~35 secunde (cold boot)
- Config AVD: ~/.config/.android/avd/Android16.avd/config.ini
  (atentie: XDG_CONFIG_HOME=.config muta AVD-ul aici, nu in ~/.android/avd
   -> emulatorul are nevoie de ANDROID_AVD_HOME=$HOME/.config/.android/avd)

## GPU (sistem hibrid)
- card0=amdgpu (Radeon Vega 10, iGPU), card1=nvidia (GTX 1660 Ti, driver 550.163.01)
- Pentru randare pe NVIDIA (PRIME render offload):
    __NV_PRIME_RENDER_OFFLOAD=1
    __GLX_VENDOR_LIBRARY_NAME=nvidia
    VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/nvidia_icd.json

## Scripturi utile in workspace
- env.sh                   -> seteaza JAVA_HOME/ANDROID_HOME/PATH
- start_emulator_nvidia.sh -> porneste AVD Android16 cu GUI, randare pe NVIDIA
- wait_boot.sh             -> asteapta boot_completed
- MEDIU.md                 -> acest fisier

## LECTII INVATATE
- Imaginea android-36.1 (dev build) boota EXTREM de lent / parea blocata -> foloseste android-36 (stabil).
- AVD needefinit cu ramSize 1536M e prea mic pentru Android 16 -> 4096M merge repede.
- xwd+ffmpeg functioneaza pentru screenshot; ffmpeg are nevoie de -update 1 sau pattern pentru PNG unic.
