
P: `open` CLI on Linux reports ENXIO "No such device" for `/dev/video*` even when device exists -> wrapper lacks V4L2 support -> verify with `v4l2-ctl --list-devices` or `ls -l` instead

DEAD: curl to external IP without a resolved proxy env var returns empty body silently -> no CONNECT/proxy set -> verify with curl -v showing "Connection refused", set HTTPS_PROXY=http://127.0.0.1:PORT or use a reachable host

TRAP: tmux send-keys without -l misinterprets literal strings containing semicolons/quotes -> silent truncation -> use `tmux send-keys -l "$cmd"` then separate `Enter`.

## 2026-09-19 - android env/emulator (session: /home/gab/Desktop/agent/workspace)
- P: /home/gab/Desktop/agent/workspace/env.sh -> source it: JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64, ANDROID_HOME=/home/gab/android, ANDROID_SDK_ROOT=/home/gab/android, PATH+=platform-tools:cmdline-tools/latest/bin:build-tools/35.0.1:gradle-8.11.1/bin
- TRAP: gradle/sdkmanager fail `JAVA_HOME is not set and no 'java' command could be found` -> no JDK anywhere on disk -> Debian trixie has NO openjdk-17 (only 21=default-jdk, 25) -> `sudo apt-get install -y openjdk-21-jdk` (Gradle 8.11.1 + AGP OK)
- TRAP: `avdmanager list avd` empty after successful `create avd` -> XDG_CONFIG_HOME=/home/gab/.config moves AVD to ~/.config/.android/avd but emulator searches ~/.android/avd -> set `ANDROID_AVD_HOME=$HOME/.config/.android/avd` before running emulator
- TRAP: emulator black screen / adb `offline` forever, boot killing time -> system image `android-36.1` is a dev build (setprop took 11683ms) -> use stable `system-images;android-36;google_apis;x86_64` (rev7) -> boot ~35s
- TRAP: AVD from `avdmanager create` gets hw.ramSize=1536M -> too little for Android 16 -> edit ~/.config/.android/avd/<name>.avd/config.ini: hw.ramSize=4096, vm.heapSize=512, disk.dataPartition.size=8G, hw.cpu.ncore=6
- OK: emulator hybrid-GPU NVIDIA offload -> `-gpu host` + __NV_PRIME_RENDER_OFFLOAD=1 __GLX_VENDOR_LIBRARY_NAME=nvidia VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/nvidia_icd.json; log confirms `Found physical GPU 'NVIDIA GeForce GTX 1660 Ti'` (default was AMD radeonsi iGPU)
- OK: screenshot from X session -> `DISPLAY=:0 xwd -root -silent -out s.xwd` then `ffmpeg -y -i s.xwd out.png` (plain `ffmpeg -i - out.png` from pipe fails); verify with look()
- TRAP: `nohup cmd &` / `setsid ... &` in a bash -lc one-shot does NOT persist (process gone, no log written) -> run long jobs FOREGROUND capturing to log, or use a dedicated wrapper script executed with setsid nohup env DISPLAY=:0 ./script.sh
- OK: avdmanager/sdkmanager prompts -> feed via stdin file (`< /tmp/ans.txt`) or python subprocess input=..., NOT a pipe `yes |` or `printf |` which hangs the non-interactive bash tool
- PREVENT: before downloading a system image or JDK, check what is already on disk (`find /home/gab/android/system-images -maxdepth 4 -type d`) - downloads take minutes and android-36.1/36-ext19 were already present

TRAP: Windows cmd `where`/`find`/`dir` under Git-Bash or piping may return empty without error -> path/shell mismatch -> verify with absolute path or `ls`/`command -v` and check exit code.

P: GitHub Actions `gh run view` needs `--log` flag for logs -> bare `gh run view` only shows status/jobs, risking wrong "no logs" conclusion -> use `gh run view <id> --log` to get real output.

P: /usr/bin/time -v gives max RSS and exit status but writes stats to stderr, so redirect 2>file then read file; plain time (shell builtin) may be missing in sh -> use /usr/bin/time explicitly.

TRAP: bare GPU/OS probes (nvidia-smi, systemctl, ip, docker info) can return empty/partial data when run without needed privileges or env -> agent may wrongly conclude hardware/service absent -> re-run with sudo/full path or check exit code and stderr.

## 2026-09-19 - android/cpython build + agent port (session: /home/gab/Desktop/agent/workspace)
- P: /home/gab/Desktop/agent/workspace/build/Python-3.14.7/cross-build/{aarch64,x86_64}-linux-android/prefix -> CPython 3.14.7 compilat de noi pentru Android (aarch64=telefon, x86_64=emulator)
- OK: CPython 3.14 are suport Android OFICIAL in sursa (Python-3.14.7/Android/android.py) -> `./android.py configure-build; make-build; configure-host HOST; make-host HOST` sau `./android.py build aarch64-linux-android` (rc=0, ~50-85s/faza); HOST valid: aarch64-linux-android, x86_64-linux-android
- OK: binarul produs de android.py e Android nativ: ELF ARM aarch64, interpreter /system/bin/linker64, for Android 24 -> NU trebuie cross-toolchain manual
- TRAP: `./android.py configure-build` eșuează fără host tools -> lipsesc autoconf/pkg-config/cmake -> `sudo apt-get install -y build-essential pkg-config autoconf libssl-dev zlib1g-dev libffi-dev libsqlite3-dev libreadline-dev libbz2-dev liblzma-dev libgdbm-dev libncurses-dev`
- OK: android.py compilează 114 module (36 built-in, 67 shared); UTILE _ssl _hashlib _sqlite3 zlib _bz2 _lzma _zstd _ctypes; LIPSA _tkinter readline _curses _gdbm _uuid
- P: POC Python-pe-Android din pachete Termux (respins pentru licenta): workspace/poc/ -> debs/ (aarch64), debs_x86/, rootfs/, rootfs_x86/, RAPORT_POC.md; NU se foloseste, s-a ales sursa PSF
- TRAP: agent.py pe Android -> `URLError: b''` la api.deepseek.com -> Python cauta CA in calea termux (/data/data/com.termux/files/usr/etc/tls/cert.pem) care nu exista -> FIX in agent.py dupa importuri: construieste /tmp/ca-bundle.pem din /apex/com.android.conscrypt/cacerts + /system/etc/security/cacerts, seteaza ssl._create_default_https_context si SSL_CERT_FILE
- TRAP: agent.py tool bash pe Android -> `FileNotFoundError: [Errno 2] No such file or directory: 'bash'` -> Android are doar sh/mksh, NU bash -> FIX: `SHELL=[('sh','-c') if (sys.platform=='android' or os.path.exists('/system/bin/linker64')) else ('bash','-lc')]` si `subprocess.Popen(SHELL[0]+(cmd,), ...)`
- OK: agent.py ruleaza complet pe Android dupa cele 2 patch-uri (SSL + SHELL): răspunde de la DeepSeek, tool bash (uname/toybox) si tool python OK
- OK: subprocess din Python-ul Android compilat vede `sh`, `ls /sdcard`, toybox 0.8.12-android (~150 utilitare: cat grep sed find tar) -> bash-in-app NU e blocat de SELinux; doar /system/alte-app necesita root
- PREVENT: pentru app Android NU folosi Chaquopy (dependinta grea externa) -> livram Python compilat; ruleaza ca PROCES SEPARAT (nu in-process) ca subprocess sa mearga nativ; pe API29+ executabilele nu pot rula din filesDir -> le punem in nativeLibraryDir ca libXXX.so
- OK: verificat in emulator: `subprocess.run(['ls','/sdcard'])` si `open('/proc/version')` merg dintr-un app-shell uid 2000 SELinux Enforcing; permisiunile runtime (camera/storage/senzori) se expun prin Kotlin, nu prin shell
- TRAP: `adb root` NU functioneaza pe imaginea `google_apis` -> ramane uid=2000(shell) -> pe emulator nu avem root, doar userdebug ar merge
- OK: push fisiere mari in emulator fiabil: tar local + `adb push` + `adb shell sh -c 'mkdir -p D && cd D && tar xf ../f.tar'` (pipe `tar | adb shell` NU merge si output-ul adb multiplu-pipe se blocheaza in bash -lc)
