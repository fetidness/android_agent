
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

P: zip -sf file.zip lists filenames without extracting -> use to inspect archive contents -> avoids unzip side effects; verify member names before extraction.

TRAP: recovery/flash tools (fastboot, ODIN, mtkclient) print empty/no-device output when run without root or udev rules present -> looks like "no hardware" -> verify with lsusb/dmesg and sudo, not tool output alone

TRAP: `adb shell pm list packages` without `-3`/`-s`/`-d` flag -> returns full system+user list, misleading if you only need user apps -> use `pm list packages -3` (third-party) or `-s` (system).

OK: tasks with explicit "verify before claiming done" phrasing (e.g. "confirm the file exists") require running the actual verification command and pasting real output, not asserting success -> skipped verification causes false completion claims -> always execute the check command and include its ra

TRAP: `grep -r pattern dir` without `-a` skips binary files silently -> misleading empty result -> add `-a` or use `rg -uuu` to search binaries too.

TRAP: nvidia-smi without root returns 'No devices were found' on locked GPUs -> misleading empty result -> verify with ls /dev/nvidia* or run under sudo

DEAD: web_search in this env returns empty for generic open-source queries -> tool result not a signal of absence -> verify important facts via direct fetch or repo URL before concluding

P: ffmpeg -y -i input -vf "drawtext=textfile=FILE:..." needs textfile path readable at runtime -> inline text with shell-quoted special chars breaks -> use a textfile with plain ASCII, verify with ffprobe

TRAP: `ip route get` without root can return an empty/misleading route -> agent infers wrong interface/gateway -> verify with `ip -br addr` and read /proc/net/route or run with sudo.

OK: /opt/homebrew/bin/ffmpeg exists on macOS ARM -> system ffmpeg absent or wrong -> call the absolute Homebrew path for reliable encodes

TRAP: piped `head`/`tail` on streaming commands hides exit code and truncates output -> use explicit flags not pipes -> verify with echo $?

TRAP: `git status` on a fresh repo shows clean even with untracked files if a global gitignore or core.excludesfile covers them -> misleading clean tree -> verify with `git status --ignored` and `git ls-files --others --exclude-standard`.

P: /home/ubuntu/Desktop/task/readable_ascii_art (or similar absolute artifact path) is the canonical readable output -> always reassemble and cat the final file after producing it -> verify bytes/path before reporting done.

TRAP: vcgencmd/raspi GPIO reads and most /sys/class/gpio ops return empty or misleading values without root or correct pinmux -> agent may conclude hardware absent/failing -> run as root and confirm pin function before trusting reads.

DEAD: `ls` on a directory/file without read permission returns permission denied, not empty - can't distinguish absence from lockdown -> check exit code / test -e before concluding a path doesn't exist.

DEAD: `claude` CLI non-interactive prompt flag `-p` still requires TTY in some hooks -> hangs/empty output when piped -> test with `echo hi | claude -p ...` before relying on it in automation.

P: macOS Intel hosts require arch -x86_64 prefix for brew under Rosetta; verify with brew config showing Rosetta 2 line before trusting Intel formula paths.

TRAP: `git branch -r` shows stale remote-tracking refs after fetch removal -> conclude remote branch gone -> run `git fetch --prune` before trusting remote ref list.

DEAD: native `stat -c %Y` on BusyBox/Alpine returns error -> use `stat -c %Y` only after confirming GNU coreutils; portable alt `date -r file +%s` -> verify with `stat --version` first.

TRAP: `du` / `find -size` in a sandbox without -r or via wrong mount shows empty/zero -> misread as "no data" -> verify with `ls -la`/`df -h` and check the real path/mount first.

P: GNU tar incremental archives with listed-incremental require a snapshot file regenerated each run; reusing an existing snapshot yields empty/unchanged results -> always regenerate or use a fresh snapshot path per backup.

OK: /usr/bin/time -v gives Max RSS and page faults, but /usr/bin/time without -v prints only elapsed time -> easy to conclude low memory wrongly -> always pass -v to check memory.

DEAD: vgmstream/ffmpeg trimming with -ss before -i on some VGM/ADPCM streams yields wrong/empty audio -> seeking happens on demuxer not decoder -> decode full then trim with -ss after -i or re-encode -t.

TRAP: nvidia-smi/lspci show GPU but no driver -> CUDA ops fail silently/absent -> verify with nvcc --version or python -c "import torch;print(torch.cuda.is_available())" before assuming GPU usable.

OK: `find / -name '*.conf'` as non-root floods stderr with permission-denied noise -> obscures real matches -> use `find /path -name '*.conf' 2>/dev/null` or restrict to readable dirs.

P: pipe/exec tool output may be truncated with no error -> verify by counting lines or grepping expected markers -> re-run with narrower scope if missing.

TRAP: `snap list` / `snap info` on classic distros without snapd installed returns empty or not-found, misleading you into thinking a package isn't available -> verify `which snap` or `dpkg -l snapd` first

TRAP: git log --oneline without a ref/path in a repo where HEAD is detached or on an empty branch -> prints nothing or "fatal", not the branch history -> always pass an explicit branch/path, e.g. git log --oneline <branch> -- <path>.

TRAP: bare `grep`/`find` style discovery commands can return empty without root or params on this system -> wrong "nothing exists" conclusion -> always re-run with explicit path/params or sudo before concluding absence.

OK: ipex-llm conda env setup -> `conda create -n ipex python=3.11` then `pip install ipex-llm[cpu]` works but pip resolves slow; use `pip install --extra-index-url https://pytorch-ipex.github.io/whl/cpu ipex-llm` for faster reliable install.

TRAP: nvidia-smi/docker info can appear fine while GPU is unusable in containers -> container lacks --gpus all or NVIDIA runtime -> verify with device query inside container, not host.

OK: macOS `grep` without file args reads stdin and hangs/empty → misleading "no match" → pass explicit paths or `-r`, or verify input source first.

OK: Long-running global-trade/GTM eval batches -> task text can be stale/mismatched (watcher picks arbitrary task per domain) -> trust the per-session launcher command over eval prompt wording; verify by reading the live task .txt before acting.

OK: pkg-config --modversion <lib> with no .pc file returns empty exit 1 -> stderr suppressed reads as "not installed" -> use `pkg-config --exists X && echo yes` or check dpkg -l instead

DEAD: /tmp/nonexistent scripts fail silently -> relative assumptions -> use absolute paths and verify file existence before exec

P: GNU/Linux `find -newermt` needs full timestamp or offset like `-newermt '-1 hour'`; bare `-newermt -1h` is parsed as a path -> use `-mmin -60` or quote `-newermt '-60 min'` -> verify by COUNTING matches first

TRAP: read-only shell probe `nvidia-smi`/`systemctl status` can return empty/blank without root or with no params -> agent misreads as "missing GPU/service" -> always pass explicit query args and verify exit code before concluding.

TRAP: bare `git diff` on a repo with only staged changes shows empty output -> changes are in index, not worktree -> verify with `git diff --cached` instead

TRAP: `git log -1 --format=%cd` in shallow clone shows only tip date, not repo age -> looks like recent project -> use `git log --reverse` or check tag count before assuming maturity

TRAP: `cat /proc/net/dev` without root works but reading `/proc/<pid>/net/dev` needs PTRACE/root -> misleading empty/permission result -> use root or `/proc/net/dev` for interface stats.

P: /home/gab/Desktop/agent/workspace/app/net.sys32.agent/app/src/main/assets/python/Lib/site-packages/ -> biblioteci pure-Python (requests, bs4, yaml, toml, packaging) descarcate de pe PyPI pentru agentul Android; puse aici ajung pe device in pyhome/lib/python3.14/site-packages

TRAP: folderele care incep cu `_` sunt IGNORATE la impachetare in assets Android (AAPT2) -> zipfile/_path/ nu ajungea in APK desi exista in sursa -> livrez pachetul ca fisier simplu _path.py, nu ca director

OK: script de copiere care itereaza doar os.listdir() pe directoare rateaza fisierele .py de la radacina unui wheel (ex six.py) -> copiaza explicit si fisierele, nu doar folderele

P: /home/gab/Desktop/agent/.gitignore -> are exceptii `!.../Lib/site-packages/` si `!.../Lib/zipfile/`; fara ele git ignora bibliotecile si fixul stdlib

TRAP: git push pe repo cu remote SSH nou -> cheia trebuie adaugata pe GitHub intai; core.sshCommand per-repo (`ssh -i <key> -o IdentitiesOnly=yes`) forteaza cheia corecta fara sa atinga ~/.ssh/config global

TRAP: `python3 -u -c "<script lung multi-linie>"` atarna fara output (nici primul print nu apare) -> comanda inline prea lunga e blocata de shell/hook -> scrie scriptul intr-un fisier (/tmp/x.py) si ruleaza `python3 -u /tmp/x.py

TRAP: `urllib.request.getproxies()` pe aceasta masina atarna intermitent (cheama gsettings/GNOME proxy) -> api.deepseek.com prin urllib atarna desi curl merge in 0.3s -> nu concluziona "reteaua e moarta" doar din urllib

OK: `curl -s -w "%{http_code} %{time_total}s" https://api.deepseek.com` returneaza 401 in ~0.3s (fara auth) -> test rapid de conectivitate fara sa astepte inferenta

TRAP: proces blocat in `hrtimer_nanosleep` (vezi /proc/<pid>/wchan fara sudo) = asteapta un timeout de socket, NU e deadlock -> nu-l omori; verifica ce timeout are codul

TRAP: modificarea lui agent.py (fisierul care ma ruleaza) live -> UnboundLocalError: cannot access local variable 'APITIMEOUT' la urmatorul task -> adauga `global X` sau testeaza cu py_compile + reporneste procesul

TRAP: atribuire `X = ...` intr-o functie care citeste X din global -> Python il face LOCAL in toata functia -> orice citire inainte de atribuire da UnboundLocalError -> declara `global X` in capul functiei

OK: tool-ul bash al framework-ului atarna intermitent, dar `subprocess.run(["bash","-lc",cmd])` din tool-ul python merge instant 0.01s -> cand bash atarna, ocoleste prin python

DEAD: `open(p,"w").write(open(p).read()...)` trunchiaza fisierul la 0 (w deschide inainte de read) -> scrie intai intr-o variabila, apoi open(w), sau os.replace atomic

OK: tool-ul `bash` se blocheaza intermitent (comanda nu ajunge la Popen, niciun proces copil) -> ocolesc cu tool-ul `python`: subprocess.run(['bash','-lc',cmd]) merge in 0.002-0.006s",

TRAP: atribuire `APITIMEOUT=...` intr-o functie fara `global` -> Python il face LOCAL in toata functia -> UnboundLocalError la citirea dinaintea atribuirii -> declara `global` in capul functiei",

P: /home/gab/Desktop/agent/agent.py -> agentul Linux care ruleaza ACUM (eu); backup-uri: agent.py.broken (versiunea rupta)",

OK: /proc/<pid>/syscall arata exact syscall-ul (230=nanosleep, 202=futex) -> util sa distingi 'doarme normal' de 'blocat in I/O' fara root",

TRAP: `run-as <pkg> /data/local/tmp/script.sh` da "Permission denied" (SELinux interzice exec din /data/local/tmp) -> copiaza wrapper-ul in filesDir/ al aplicatiei si ruleaza-l de acolo.

TRAP: reinstalarea unui APK (adb install -r) schimba hash-ul din calea /data/app/~~XXXX==/pkg-YYYY==/lib/<abi>/ -> calea libpyexec.so memorata devine invalida -> reciteste-o cu `dumpsys package <pkg> | grep codePath` inainte de a relansa Python.

TRAP: SensorManager.registerListener fara Handler, apelat din thread fara Looper (socket/worker) -> onSensorChanged nu se declanseaza NICIODATA desi getDefaultSensor gaseste senzorul -> livreaza `new Handler(Looper.getMainLooper())` ca 4-lea argument.

TRAP: bridge-ul Android cu tool-urile native asteapta `{"tool":..,"action":..,"params":{..}}` (cheia `name` la senzori, `field` la eval-get) -> cererea `{"op":..}` raspunde "unknown tool:" -> nu confunda eroarea de protocol cu bridge mort.

TRAP: `LLM import al agent.py` pe device agata (n-are `if __name__` guard, ruleaza bucla cu input() la nivel modul) -> nu-l importa; extrage functia cu regex intre `def X(` si urmatorul `\ndef ` si exec-o izolat.

TRAP: `adb shell uiautomator dump /sdcard/ui.xml` esueaza silentios (scoped storage, "No such file") -> scrie dump-ul in /data/local/tmp/ui.xml si citeste-l cu cat de acolo.

TRAP: dupa `adb install -r` hash-ul din calea /data/app/~~XXX==/pkg-YYY==/lib/<abi>/ se schimba -> calea libpyexec.so/LD_LIBRARY_PATH devine invalida -> reciteste-o cu `dumpsys package <pkg> | grep codePath`.

OK: `run-as <pkg> <script.sh>` nu poate executa din /data/local/tmp (SELinux Permission denied) -> copiaza scriptul in filesDir/ al aplicatiei si ruleaza-l de acolo cu `run-as <pkg> sh /data/data/<pkg>/files/x.sh`.

TRAP: importul agent.py pe device agata fara output (fara `if __name__` guard, ruleaza bucla cu input() la nivel modul) -> nu-l importa; extrage functia cu regex intre `def X(` si urmatorul `\ndef ` si exec-o izolat in python3.

TRAP: bridge Android cu `{"op":..}` raspunde "unknown tool:" desi bridge-ul e viu -> protocolul corect e `{"tool":..,"action":..,"params":{..}}` (senzori: cheia `name`; eval get: cheia `field`) -> nu confunda eroarea de protocol cu bridge mort.

TRAP: `input` (keyevent/text/tap) rulat din procesul app (untrusted_app uid 10000+) da "Failed transaction (2147483646)" / SecurityException INJECT_EVENTS, dar din `adb shell` (user shell) merge exit=0 -> pentru automatizare UI pe Android ne-rootat nu folosi input din app, ci AccessibilityService sa

TRAP: agentul Android a consumat ~40 mesaje incercand injectInputEvent/Instrumentation/cmd input, toate blocate de permisiunea INJECT_EVENTS (protectionLevel=signature) -> cand prima eroare e o permisiune de tip signature, abandoneaza dupa 1 incercare, nu testa 6 variante ale aceleiasi idei.

TRAP: la task cu obiectiv precis (tastare reala), agentul a substituit cu o varianta ocolita (URL cu ?msg= auto-trimis) si a raportat "FUNCTIONEAZA" -> defineste succesul strict pe obiectivul cerut; o cale diferita care ocoleste cerinta NU e succes, spune explicit "nu se poate + de ce".

OK: AccessibilityService e calea corecta pentru citit/tastat/apasat in alte app-uri fara root -> INJECT_EVENTS e permisiune signature (untrusted_app o primeste niciodata) -> expune-l prin bridge ca tool ui cu actiuni read depth=40/settext/click/openapp.

TRAP: `ui read` cu depth=4-8 întoarce doar scheletul (action_bar, RecyclerView) fara itemi -> nodurile reale sunt adanci -> foloseste depth=40 max=2000 ca sa vezi textele/butoanele.

P: /home/gab/Desktop/agent/workspace/app/net.sys32.agent/app/src/main/java/net/sys32/agent/AgentAccessibilityService.kt -> serviciul de accessibility (read/settext/click/gesture/global); AndroidBridge.kt tool "ui" il cheama prin instance; config in res/xml/accessibility_service_config.xml.

TRAP: `input keyevent/text` din shell-ul aplicatiei da `Failed transaction (2147483646)` sau SecurityException INJECT_EVENTS -> app ruleaza ca untrusted_app -> din adb shell (user shell) merge (exit=0); pe device ne-rootat foloseste AccessibilityService, nu `input`.

TRAP: `git commit -m` cu mesaj ce contine backtick-uri (ex. "tool `ui`") -> bash -lc executa textul dintre backtick-uri ("ui: command not found"), desi commit-ul reuseste -> scrie mesajul intr-un fisier si foloseste `git commit -F fisier

P: /home/gab/Desktop/agent/temp/ -> singurul loc de lucru temporar, dar se CURATA periodic -> fisierele puse aici (backup-uri, scripturi de test) dispar intre pasi -> nu te baza pe ele pentru recuperare; scrie in workspace/ sau fa backup in afara temp

TRAP: `settings put secure enabled_accessibility_services` se pierde la fiecare `adb install -r` -> Android dezactiveaza serviciul de accessibility la reinstalare -> re-activeaza-l din Settings > Accessibility > Installed apps (Samsung) sau cu cele 2 comenzi adb

P: Samsung Settings are accessibility sub numele "Installed apps", ascuns in "Advanced settings" dupa scroll -> "Installed applications" (denumirea Android standard) nu exista -> verifica cu `dumpsys accessibility | grep -A3 <pkg>` ca serviciul e listat

OK: `dumpsys accessibility | grep -A3 <pkg>` arata serviciile a11y declarate+enabled ale pachetului chiar daca UI-ul nu le gaseste -> foloseste ca verificare obiectiva a starii serviciului, nu screenshot-ul

TRAP: `adb forward tcp:N tcp:M` moare cand telefonul intra in Doze (ecran stins/blocat) -> curl de pe laptop primeste gol desi procesul traieste -> citirea `mWakefulness=Dozing` in `dumpsys power` confirma, iar interactiunea functioneaza totusi: scrie-le corect, fara ghilimele, complet.

OK: starea reala a serviciilor Android (foreground/accessibility/ecran) se citeste cu `adb shell dumpsys power | grep -E 'mWakefulness=|net.sys32'` si `dumpsys deviceidle whitelist | grep <pkg>` -> arata daca wake lock-ul e tinut si daca app-ul e exclus de Doze

TRAP: reconstruirea/instalarea APK-ului DEZACTIVEAZA serviciul de accessibility si scoate app-ul din whitelist-ul de baterie -> `accessibility:false` dupa `adb install -r` -> reactiveaza cu `adb shell settings put secure enabled_accessibility_services <pkg>/<pkg>.AgentAccessibilityService` + `settin

TRAP: `ui read` pe Android returna JSON brut cu toate metadatele pe fiecare nod (~120 chars zgomot pentru 3 chars text) -> ecran WhatsApp 8500+ chars trunchiat la 8000, informatia cautata la poz 6375 -> foloseste read compact (lista text `[n] Cls id=x "text" @[x,y]`) si action=find <text> pentru cau

TRAP: un agent care cauta un contact prin UI si nu-l gaseste in arborele de accesibilitate -> poate rata ca datele ERAU in raspuns dar ingropate in zgomot -> inainte de a declara "nu exista", verifica cu find <text> sau read compact, nu trage concluzia din JSON trunchiat

P: /home/gab/Desktop/agent/workspace/app/net.sys32.agent/app/src/main/assets/python/agent.py -> agentul Python din APK (assets vN se re-extragg pe device la .assets_vN din MainActivity) -> la orice schimbare de assets INCREMENTEAZA versiunea sau ramane copia veche

OK: testare Android fara laptop prin tunel adb -> bridge-ul raspunde via `adb shell 'echo -n <json> | nc 127.0.0.1 <port>'` (port din files/bridge.port) -> functioneaza chiar si cu ecranul blocat, spre deosebire de adb forward care moare in Doze

OK: `ui find "Send"` (bridge Android) gaseste butonul chiar cind arborele e trunchiat de `ui read` -> foloseste find inainte de read pe ecrane lungi cu RecyclerView.

TRAP: `adb shell input text 'fraza cu spatii'` se opreste la primul spatiu -> scrie `%s` in loc de spatiu -> `input text 'deschide%swhatsapp'`.

TRAP: `adb shell input tap X Y` rateaza butonul daca textul multi-linie din EditText rearanjeaza layout-ul (butonul s-a mutat de la y=2211 la y=1509) -> reia `uiautomator dump` si recalculeaza bounds inainte de fiecare tap.

TRAP: `/reset` in agentul Android (comanda in app) goleste context.json dar PASTREAZA memory.md -> calea corecta de a da un task curat fara sa pierzi lectiile invatate.
