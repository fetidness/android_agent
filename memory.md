
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

P: auto-incrementing version badge shows stale build number when image cache not busted -> deploy uses cached layer -> verify badge matches build log after cache-bust env var change

P: iOS UIView/UIViewController hit-testing ignores subviews that are outside the parent's bounds unless clipsToBounds is false and parent overrides point(inside:) -> taps silently do nothing -> verify with hitTest debug or override point(inside:with:) on the container.

TRAP: `pip show <pkg>` prints nothing and exits 0 when pkg absent in some pip versions -> false "installed" read -> verify with `python -c "import pkg"` or `pip list | grep`.

P: ls /usr/lib/modules/$(uname -r)/build -> needed for DKMS/kernel-header builds -> if missing, install matching linux-headers before any out-of-tree module compile

P: `ansible-runner` needs sshpass installed on the CONTROL node, not the target -> playbook using `ansible_password` fails "to use the ssh connection type with passwords, you must install the sshpass program" -> install sshpass on the box running ansible (not the managed host)

OK: In bash, `set -e` + command substitution in conditionals can mask failures -> `if out=$(cmd)` treats nonzero as false instead of exiting -> run cmd separately or check $? explicitly.

## 2026-09-19 - android app UI + reflection bridge (session: /home/gab/Desktop/agent/workspace)
- TRAP: `LAYOUT_IN_DISPLAY_CUTOUT_MODE_NEVER` pe app cu notch -> ora/status bar trunchiata (iesea in afara ecranului) -> SCOATE modul; lasa default; padding top = max(bars.top, cutout.top)+16dp
- TRAP: bara de status acoperita pe emulator -> `dumpsys window displays | grep cutout` arata `mDisplayCutout=DisplayCutout{insets=Rect(0,136-0,0)}` (cutout=136px > statusBars=74px) -> padding top trebuie maxOf(statusBars.top, displayCutout.top)
- TRAP: chenar/box-drawing `─│╭╯` fragmentat (goluri intre segmente) in TextView -> fontul monospace Android nu are box-drawing continuu -> livraza `assets/fonts/DejaVuSansMono.ttf` + `Typeface.createFromAsset` (are toate glyph-urile U+2500+ verificat)
- OK: tastatura nu acopera input-ul -> manifest `android:windowSoftInputMode=adjustResize|stateUnchanged` + `WindowCompat.setDecorFitsSystemWindows(window,false)` + padding bottom=maxOf(bars.bottom, ime.bottom)
- OK: culori ANSI in TextView -> clasa Ansi.kt convertește SGR in Spannable (30-37/90-97/38;5;N/38;2;R;G;B, bold/italic/underline/strike); paleta 16 culori stil One Dark pe fundal #0D1117
- OK: scroll terminal cu auto-follow -> flag autoScroll=(child.bottom-scroll.height-scrollY<=24), buton flotant ⇩ cand user deruleaza sus; `programmaticScroll` previne bucla listener-ului
- P: /home/gab/Desktop/agent/workspace/app/net.sys32.agent -> proiect Gradle app agent (net.sys32.agent); build: ./gradlew assembleDebug sau ./app/build_app.sh
- OK: acces generic Android fara root -> AndroidBridge.kt TCP 127.0.0.1:<port> + Reflection.kt (`Class.forName`+invoke); op: call/new/get/set/info/services/free/objs; targets svc:NUME|class:FQCN|obj:ID|ctx|app|str:|int:
- OK: portul bridge-ului -> scris in files/bridge.port SI files/home/bridge.port (python il cauta in HOME); protocol = o linie JSON pe cerere -> o linie JSON raspuns
- TRAP: unele `Context.X_SERVICE` NU exista in SDK public (WEARABLE_SERVICE, CAST_SERVICE, AUTOFILL_SERVICE, COUNTRY_DETECTOR, NETWORK_POLICY_SERVICE, STATUSBAR_SERVICE, SENSOR_PRIVACY_SERVICE, TRANSLATION_SERVICE) -> compilare esueaza `Unresolved reference` -> foloseste string-uri literale ("sensor","wifi","statusbar")
- OK: reflection teste verificate -> `Build.MODEL` (get static field) = sdk_gphone64_x86_64; `Runtime.getRuntime()`; `svc:sensor getSensorList(-1)` = 139 senzori; `svc:window getDefaultDisplay`; svc:activity getRunningAppProcesses
- TRAP: `SensorManager.getSensorList(0)` -> lista GOALA; TREBUIE `-1` (TYPE_ALL=-1, nu 0)
- DEAD: reflection NU poate crea obiecte care implementeaza interfete Java la runtime (ex SensorEventListener propriu) -> pentru callback/stream de senzori foloseste listeneri scrisi in Kotlin
- TRAP: `open(p,'w').write(open(p).read().replace(...))` TRUNCHIAZA fisierul la 0 (w deschide inainte de read) -> a distrus MainActivity.kt -> citeste intai in variabila, apoi scrie
- TRAP: regex `re.findall(r'"name":"(\w+)"', str(T))` pe lista de dict-uri da GOL si prinde chei imbricate (str(dict) foloseste ' nu ") -> foloseste direct `", ".join(t["function"]["name"] for t in T)`
- OK: agent.py tools array `T` = 5 tool-uri: python, bash, smart, look, android; header-ul afiseaza dinamic `", ".join(t["function"]["name"] for t in T)`
- TRAP: editare agent.py prin replace pe anchor poate MUTA/sterge o linie `def X():` -> `NameError: name 'call_tool' is not defined` -> dupa orice patch verifica `py_compile` SI ca toate `def ` sunt la nivel modul
- OK: assets-uri in app se re-extragg odata cu stamp cache (`.assets_vN` in MainActivity extractAssets) -> la orice schimbare de assets INCREMENTEAZA versiunea, altfel ramane copia veche
- OK: emulator popup stylus/handwriting acopera butonul trimite -> `adb shell settings put secure stylus_handwriting_enabled 0` (si stylus_first_detection_done 1)
- PREVENT: in app Android inlocuieste tool bash cu `sh -c` (Android n-are bash) si citeste CA din /apex/com.android.conscrypt/cacerts — ambele deja patched in agent.py

TRAP: A bare `du -sh` under a directory the user doesn't own can return empty/permission-denied without sudo -> agent may wrongly conclude zero size -> prefix with sudo or verify via stat/ls on specific paths.

TRAP: checking only /mnt/c/Program Files/... without Drive letter variants -> wrong path yields empty result -> verify Windows paths under all mount roots (c, d) before concluding absent

## 2026-09-19 - android phone real + git (session: /home/gab/Desktop/agent/workspace)
- OK: instalez app pe telefon real via USB -> `adb -s <SERIAL> install -r app-debug.apk` (APK debug are deja arm64+x86_64, ~4.7s install) -> `adb devices -l` da serialul, `getprop ro.product.cpu.abilist` confirma arm64-v8a
- TRAP: `appops set <pkg> MANAGE_EXTERNAL_STORAGE allow` NU deschide ecranul de permisiuni -> pe Samsung Settings$AppManageExternalStorageActivity ramane in front si `am start` doar aduce task-ul lui in fata -> acorda permisiunile de baza cu `pm grant` si accepta dialogurile UI
- OK: acceptare automata a dialogurilor de permisiuni Android -> bucla: `uiautomator dump /sdcard/ui.xml` + `cat /sdcard/ui.xml` -> regex pe text+bounds -> centru buton -> `input tap X Y`; butoane Samsung: 'While using the app', 'Allow'
- TRAP: variabile shell `A='adb -s X'; $A shell ...` intr-un bash -lc non-interactiv nu produc output -> scrie comanda adb completa de fiecare data sau ruleaz-o din python subprocess
- TRAP: `adb shell <cmd>` cu pipe/grep complex intoarce INTERMITENT output gol (nu eroare, exit 0) -> foloseste python subprocess cu capture_output pentru orice adb cu pipe
- OK: verificare ca app-ul ruleaza pe device: `dumpsys window | grep mCurrentFocus` -> `Window{... net.sys32.agent/net.sys32.agent.MainActivity}`; proces via `ps -A | grep sys32`
- OK: task Settings din recents NU se sterge cu `am task remove` (unknown command) -> `input keyevent KEYCODE_HOME` sau `am force-stop com.android.settings` apoi `monkey -p <pkg> -c android.intent.category.LAUNCHER 1`
- OK: git repo in /home/gab/Desktop/agent cu .gitignore care taie build/poc/pydist, assets/python/Lib, libdynload, *.apk/*.so/*.tar/*.deb, *.png/*.xwd, logs/, context.json, archive/ -> 776 fisiere -> 52, repo 31MB
- TRAP: `git add -A` adauga fisiere INAINTE ca regula din .gitignore sa existe in index -> raman staged si ignore-ul nu le scoate -> fix: dupa orice schimbare de .gitignore ruleaza `git rm -r --cached . && git add .`
- TRAP: linii de negare `!path` la finalul .gitignore re-includ ce tocmai ai exclus -> scoate-le daca vrei sa excludi ferm un director

OK: Shell commands that fail silently without stderr (e.g. unzip -l on missing file into pipe) -> can yield empty output mistaken for success -> verify exit code or test file existence explicitly

OK: bare `timeout` cmd with no DURATION prints usage/errors -> can look like failure -> always pass duration first, e.g. `timeout 30 <cmd>

TRAP: bare `ffmpeg`/`ffprobe` on streams returns generic errors without `-v error` context -> agent may misdiagnose codec vs network cause -> always add `-v verbose`/`-v error` and check stderr separately.

OK: no root/params can return empty/misleading command output -> verify commands with required args/root before concluding failure

TRAP: kill -0 <pid> returns success for zombie/defunct processes -> liveness check can't detect dead-but-unreaped children -> inspect /proc/<pid>/stat state field (Z) or use waitpid instead.

TRAP: tail/grep-less short follow-ups can look empty against large logs -> paged output hides owner line -> always grep exact symbol/path+'\b' and print with line numbers.

TRAP: `pip install` in a venv without `--user` can silently no-op if the package is already satisfied system-wide; verify with `python -c "import X; print(X.__file__)"` to confirm it lives in the venv, not the system path.

P: /home/oai/share is world-readable/writable scratch for user-visible artifacts, not root-only -> prefer it for saving outputs so user can inspect -> verify with ls -l.

OK: pip install on macOS system python fails with "externally-managed-environment" -> PEP 668 blocks -> use a venv (python3 -m venv .venv && source .venv/bin/activate) or pipx, never sudo pip.

DEAD: assuming a post-install hook ran apt/system libs cleanly -> tasks succeeding despite missing runtime deps unless you grep exit logs for warnings -> verify each setup step's output, not just overall exit code

OK: git stash push -m msg creates stash but stash pop after branch switch can conflict -> verify with git stash list before pop and prefer git stash apply to keep recovery option.

P: /usr/bin/python3 -c 'import gi; gi.require_version("Gtk","3.0")' silently no-ops under headless SSH -> GTK apps fail without DISPLAY -> verify with xvfb-run or check $DISPLAY before GUI commands

TRAP: `ps` alone in a container shows only that process -> hides sibling/parent procs -> use `ps -ef` or read /proc to see all container processes.

DEAD: Python `date -d`-free shell arithmetic on YYYYMMDD via `expr` fails on leading-zero octals (e.g. 08) -> expr treats 08 as invalid octal -> use `date -d "$d" +%s` or strip leading zeros with `10#$var` in bash arithmetic.

TRAP: docker ps with no -a shows only running containers -> a stopped service container looks absent -> use `docker ps -a` before concluding a container doesn't exist

DEAD: `find / -name '*.cfg'` style broad filesystem scans timeout/return empty under sandboxed roots -> miss real configs -> scope search to known dirs (/etc, ~/.config, ./) or use fd with depth limit.

OK: `find / -name "*.conf" 2>/dev/null | head` returns empty even when files exist if pipes close early via SIGPIPE; use `-print -quit` or drop `head` -> misleading empty result -> verify with `find ... | wc -l`.

TRAP: macOS `/usr/bin/time -l` output goes to stderr and its first line is column-formatted; piping `time` alone (`time cmd`) is a bash keyword so flags differ -> capture with `{ /usr/bin/time -l cmd ; } 2>file` rather than `time -l`.

DEAD: `lsblk` without sudo on some systems shows empty/wrong mount info -> non-root restricted device enumeration -> use `lsblk -f` with sudo or check /proc/mounts as root for accurate results.
