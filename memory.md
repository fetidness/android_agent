
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

TRAP: after editing assets/*.py on disk, the installed APK still serves the old copy -> app only re-extracts when the `.assets_vN` marker in app filesDir is bumped -> increment the marker in MainActivity AND rebuild/install, otherwise `adb push` to files/python/ is lost on next extract

DEAD: `adb shell run-as <pkg> cat <file>` drops the final trailing newline -> byte count is off by 1 vs the real file -> compare with `run-as md5sum <file>`, not with cat output

TRAP: `adb shell run-as <pkg> <script>` fails "Permission denied" for scripts in /data/local/tmp (SELinux) -> copy the wrapper into the app filesDir first and exec it from there

TRAP: `joblib` `libpyexec.so` gives "library libpython3.14.so not found" or "Failed to import encodings" without the full env -> must set LD_LIBRARY_PATH=<nativeLibraryDir> PYTHONHOME=files/pyhome HOME=files/home, not PYTHONHOME=files/python

TRAP: `run-as <pkg> sh -c 'cp x y'` prin adb pierde argumentele din cauza quote-urilor -> fisierul nu se copiaza si zici ca lipseste -> ruleaza cp ca argumente separate (`run-as pkg cp /data/local/tmp/x /data/data/.../y`), fara sh -c.

TRAP: calea libdir din `dumpsys package | grep codePath` nu contine ABI -> `lib/libpyexec.so` da "inaccessible or not found" -> append `/arm64` la libdir, iar calea se schimba la fiecare reinstalare (`~~hash` nou), deci re-citeste-o inainte de fiecare rulare.

TRAP: `run-as <pkg> cat fisier` pierde newline-ul final -> md5 diferit fata de original (113545 vs 113546) desi continutul e identic -> verifica identitatea cu `run-as pkg md5sum fisier` pe device, nu prin cat.

TRAP: lansarea Python din app cere PYTHONHOME=files/pyhome (nu files/python) si LD_LIBRARY_PATH=nativeLibraryDir -> altfel "Fatal Python error: Failed to import encodings module" -> copiaza exact env-ul din ProcessBuilder (PYTHONHOME, HOME, PATH, AGENT_HOME) in wrapper.

TRAP: cheia API era urcata in git in 3 locatii (key.txt root, assets/python/key.txt, ~/.deepseek_agent_key) desi doar ultima e citita de agentul desktop -> `git ls-files | grep -i key` arata ce e urmarit -> dupa expunere scoate din tracking cu `git rm --cached` SI adauga in .gitignore, altfel cheia ramane in istoric (git log --all -S'<cheie>' gaseste commit-ul) si doar revocarea ei la provider te mai salveaza.

OK: adb -s RZGL102X5AT exec-out run-as net.sys32.agent cat <path> -> extracts app-private files on this device; /data/data/net.sys32.agent/files/context.json is empty (2 bytes) but the real context lives at /sdcard/Download/Agent/context.json readable via plain exec-out cat, no run-as needed.

DEAD: connecting app->adbd from inside Android via SPAKE2/TLS pairing -> stops at internal AOSP PEER_INFO framing and adb_keys in /data/misc/adb is unreadable without root; ADB must come from outside (laptop) as uid shell 2000, never self-promote.

P: ADB wireless debugging state on this Android (RZGL102X5AT) is live: adbd listens on TCP port 6100 (0x17D4) uid=1000, laptop 10.0.0.2 already ESTABLISHED -> connect adb to 10.188.228.103:6100 instead of assuming USB-only.

OK: /data/local/tmp/adbkey.pub on this device is world-readable (mode 666) and readable by an app via adb shell run-as -> the public key can be read from an app, but the PRIVATE key ~/.android/adbkey stays on the laptop, so an app cannot self-authenticate to adbd; ADB must come from outside.

OK: adb reverse tcp:9500 tcp:9500 works over UsbFfs on this device -> any privileged command can be tunneled to an app on 127.0.0.1:9500, giving uid=shell (2000) rights (pm grant, dumpsys, input, settings put, run-as all confirmed working) without root.

TRAP: `adb shell run-as <pkg> env ... <path-in-filesDir>.py` -> SELinux denies exec of scripts in app filesDir ("Permission denied") -> run the script via `run-as <pkg> sh -c 'export ...; exec $LIBDIR/libpyexec.so $F/script.py'` instead.

TRAP: `adb -s <serial> reverse --list` can print `UsbFfs tcp:N tcp:N` (device<->host reverse) while a same-port entry also shows in device `/proc/net/tcp` LISTEN, so port collisions with planned adb-reverse ports (e.g. 9500) must be checked via `adb reverse --list` AND `adb shell cat /proc/net/tcp | grep <hex>` before hardcoding one.

OK: AOSP adb sources are at android.googlesource.com/platform/packages/modules/adb (NOT platform/system/core which lacks adb/) -> cloned dir at /tmp/adbsrc has client/ + adb_wifi.cpp for wireless support.

P: use_version_lib and Android.bp Soong build mean adb cannot be built with plain make -> need repo+Soong (long) or hand-written CMakeLists with NDK arm64 toolchain.

DEAD: git ls-remote against android.googlesource.com timed out/empty -> use curl to check AOSP availability, but full git clone works fine.

DEAD: adb protocol on Android 11+/16 adbd (this device SDK 36) requires STLS + full TLS handshake + SPAKE2 pairing before CNXN; raw CNXN/STLS packets over TCP give silent timeout, not error -> do not attempt pure-Python ADB client (option A) without implementing TLS+SPAKE2; use real adb binary or adb reverse instead.

P: on this device adbd wireless listen is 127.0.0.1:6100 (hex 17D4, uid 1000) and reachable via TCP from app uid, but /dev/socket/adbd is permission-denied -> connect via TCP loopback, not the unix socket.

OK: AOSP adb protocol source cloned at /tmp/adbsrc (types.h struct amessage, adb.h command consts, adb.cpp handshake logic) -> use /tmp/adbsrc as reference for ADB packet layout (cmd,arg0,arg1,datalen,checksum,magic=cmd^0xffffffff).

TRAP: bash heredoc `cat > file << EOF` inside the python tool failed silently leaving no file (adb push then errored "cannot stat") -> write scripts with python open().write() instead of heredocs, and verify file exists before push.

OK: pypi spake2 0.9 e pur Python (py3-none-any, zero .so) iar cryptography e folosit DOAR pentru HKDF-SHA256 in groups.py -> se porteză pe ARM inlocuind HKDF cu hmac+hashlib stdlib (~10 linii) -> a rulat pe device Android cu chei identice, deci SPAKE2 nu necesita compilare C

TRAP: parsarea "dumpsys package <pkg> | grep codePath" cu split("=")[-1] da cale goala daca nu tai prefixul "codePath=" -> folosesc raw.split("codePath=")[-1].strip() altfel libpyexec.so "inaccessible or not found

TRAP: adb -s <serial> shell 'run-as <pkg> cd files/...' esueaza cu "No such file or directory" pentru ca cd nu e in PATH-ul run-as -> folosesc cai absolute /data/data/<pkg>/files/... si run-as <pkg> mkdir -p / cp / tar direct

TRAP: running adb from subprocess with short timeouts leaves hung python processes on device that block adbd's shell service -> adb devices stays "device" but adb shell hangs forever -> before killing adb, pkill -9 -f libpyexec on device (or reboot phone / toggle wireless debugging) to free adbd shell channel

P: adb shell blocks and cannot be recovered from the host once the shell service is stuck; getprop/devices/get-state still work but shell commands all TIMEOUT -> budget generous timeouts (60s+) for tests that spawn device-side processes, and always build self-terminating timeouts into the device script itself so no orphan process is left

DEAD: adb shell pe device prin adbd la 127.0.0.1:5555 -> dupa multe conexiuni shell Python libpyexec lăsate deschise, canalul shell al adbd se blocheaza si adb devices ramane 'device' dar adb shell da TIMEOUT -> dupa orice shell Python prin adb inchide canalul (CLSE) si omoara procesul; daca totusi se blocheaza, repornește Wireless debugging sau telefonul.

P: ADB auth pe 127.0.0.1:5555 din app Android -> adbd autorizeaza automat conexiunile localhost fara dialog -> nu e nevoie de adbkey pre-autorizat pe device pentru shell uid=2000 din app.

TRAP: adb shell '<cmd>' cu comenzi multiple secventiale (peste ~6-8) -> depaseste timeout-ul si lasa procese libpyexec agatate care blocheaza adbd -> ruleaza comenzi adb shell scurte, una-doua per apel, cu timeout explicit.

TRAP: `adb shell <cmd>` pe dispozitiv cu shell-ul adbd blocat (procese client agățate) -> toate comenzile adb shell returnează TIMEOUT, inclusiv `echo`/`dumpsys`, nu doar cele grele -> verifică mai întâi cu `adb devices` și un `echo PING`, nu lansa secvențe de diagnostice care se agață.

OK: `python3 subprocess.run(..., timeout=N)` NU omoară procesul adb copil la TimeoutExpired -> procesele adb rămân agățate și blochează serviciul shell al adbd pentru sesiuni viitoare -> folosește `signal.alarm` sau `subprocess` cu kill explicit (`start_new_session` + os.killpg) ca să nu lași adb orfan.

P: uid Android `u0_aNNN` = uid (NNN+10000); `u0_a327`=uid 10327 e ALTĂ aplicație, nu cea instalată de tine -> cheile „user keys" autorizate nu se șterg din „Paired devices" (acolo sunt doar pairing-uri wireless) ci doar prin Developer options -> Revoke USB debugging authorizations sau rm /data/misc/adb/adb_keys (root).

DEAD: Android adbd pe acest device rulează ca uid=shell (nu root) și după restart repornește în mod wireless/TLS -> socket TCP către 127.0.0.1:5555 și :6100 se conectează dar recv dă TimeoutError (adbd așteaptă TLS/SPAKE2 pairing, nu protocol ADB clasic) -> nu relua implementarea client ADB clasic; adb tcpip 5555 nu readuce adbd în mod clasic aici, verifică mai întâi modul adbd sau implementează TLS+SPAKE2.

OK: dumpsys adb pe device arată în debugging_manager cheile autorizate (user_keys) și last_key_received ca SHA256 fingerprint -> folosește-l pentru a confirma dacă cheia proprie a ajuns la adbd în loc să ghicești.

TRAP: `bash -lc "grep -n ... file"` returned empty intermittently in this session while the file existed and had content -> output flushed empty for no error -> re-verify with python open()+read() or rerun before concluding a pattern/path is absent.

PREVENT: agent.py Python test scripts on the phone leave the adb shell permanently hung (adb shell/get-state return empty, output-less) -> always wrap on-device python runs with a hard timeout (signal.alarm) and kill leftover processes; if hung, toggle Wireless debugging / force-stop Agent / reboot to recover.

OK: Android device pairing libraries live at /apex/com.android.adbd/lib64/ (libadb_pairing_auth.so, libadb_pairing_connection.so with pairing_connection_client_new/start, libcrypto.so) -> load via ctypes instead of reimplementing SPAKE2/TLS/PEER_INFO framing; exported symbols listed in the matching .map.txt files under /tmp/adbsrc/pairing_connection/.

TRAP: running a .py directly from /data/data/<pkg>/files on Android gives "Permission denied" (SELinux blocks exec from filesDir) -> pass the script as an ARGUMENT to libpyexec.so: run-as <pkg> env PYTHONHOME=... LD_LIBRARY_PATH=... <libdir>/libpyexec.so /path/script.py.

OK: adb shell prin subprocess.run([ADB,"-s","SERIAL","shell",...]) e fiabil, dar apele adb din tool-ul bash returneaza des gol fara eroare -> foloseste python subprocess cu capture_output pentru adb -s SERIAL shell.

TRAP: adbd pairing_connection callback is void (*)(const PeerInfo*, int, void*) where the int is the SOCKET FD, not an error code; success = peer pointer != NULL (NotifyResult(&their_info_)), failure = NotifyResult(nullptr) -> don't interpret n==4 as an error.

DEAD: adb "adb -s RZGL102X5AT shell logcat -d" and "dmesg" return empty on this device -> no world-readable pair/adbd logs -> don't rely on logcat to debug pairing; instead instrument inside the app process (run-as net.sys32.agent) and print to stdout.

P: Android toybox awk has no strtonum() -> /proc/net/tcp6 parsing fails -> parse ports with grep/hex via printf "%d 0x..." or use netstat instead.

OK: on this device the app-private dir /data/data/net.sys32.agent/files holds libs/, python/, home/, pyhome/ and pair.crt/pair.key/adbkey.pub, runnable via run-as net.sys32.agent sh -c 'cd files/python && HOME=files/home PYTHONHOME=files/pyhome LD_LIBRARY_PATH=<lib_arm64> libpyexec.so script.py' -> this exact invocation is the working way to run arbitrary Python+ctypes against the app's bundled libcrypto/libadb_pairing_*.

P: adb pairing code expires in ~30-60s and each pairing attempt consumes it (dialog self-closes) -> a second/2nd-minute attempt returns peer=NULL indistinguishable from a wrong-code failure -> always request a fresh code immediately before running the pairing script.

DEAD: ctypes calling pairing_auth_get_spake2_msg(ctx) as returning pointer segfaults the process -> real signature is void pairing_auth_get_spake2_msg(PairingAuthCtx*, uint8_t* out_buf), buffer size from pairing_auth_msg_size(ctx) -> always grep the AOSP header in /tmp/adbsrc/<module>/include/... for the exact prototype before ctypes-restype/argtypes.

OK: verifying a C shared lib symbol with ctypes is fastest by calling a self-contained client+server pair in one process (pairing_auth_client_new + pairing_auth_server_new with same password, exchange msgs via pairing_auth_init_cipher) -> both rc=1 proves the whole crypto path works and isolates external failures.

TRAP: ctypes callback pentru pairing_connection_start poate aborta procesul cu fdsan ("attempted to close file descriptor ... actually owned by unique_fd") chiar DUPĂ un pairing reușit -> apel libc.android_fdsan_set_error_level(0) înainte, sau os._exit(0) la final ca să sari peste cleanup

DEAD: adb connect pe portul de pairing (ex. 37167) NU realizează pairing -> pair-ul trebuie făcut prin protocol TLS+SPAKE2; pairing-ul e valabil doar ~1-2 min, după care peer=NULL fără eroare explicită

DEAD: ADB wireless pairing from an app (untrusted_app) to adbd's pairing port -> adbd never answers TLS at all (raw ClientHello times out, pairing_connection_start gives peer=NULL even with a fully valid X.509 cert incl. basicConstraints/keyUsage/SKI) -> don't retry app-side pairing; use `adb tcpip 5555` instead, which already yielded uid=2000(shell).

OK: reading adbd logs on this device -> `adb -s RZGL102X5AT logcat -d -t 300 -s adbd:*` works from the laptop shell (via adb logcat, NOT `adb shell logcat`); `adb shell logcat` returned empty because uid shell lacks read access.

P: this machine's ~/android/platform-tools/adb is the only working ADB to the phone at 192.168.0.215:5555; after phone reboot the TCP listener dies -> re-run `adb -s RZGL102X5AT tcpip 5555` from USB to restore.

TRAP: adb devices can list a device as "device" while adb tcpip/other adb subcommands still fail with "device not found" during/after phone reboot -> adbd briefly drops -> retry the adb command after the device line stabilizes, don't assume the first failure is fatal.

TRAP: phone adbd over localhost does NOT auto-approve when you reply to AUTH_TOKEN with AUTH_SIGNATURE (RSA signature) -> infinite AUTH loop, adbd never registers the key -> send AUTH_RSAPUBLICKEY (the .pub file) directly on the first AUTH_TOKEN; it authorizes instantly with no on-screen dialog and no key persistence.

P: phone TCP-ADB reachable from the phone itself at 127.0.0.1:5555 when netstat shows adbd LISTEN on [::]:5555 -> proves port 5555 is the working entry point; verify reachability with netstat under adb shell, not just host-side adb devices.

PREVENT: adb tcpip does NOT persist across phone reboot (after restart the 5555 listener is gone, only 6100 remains) -> re-run adb tcpip 5555 over USB after every phone restart before any TCP-ADB work.

P: adb_client.py (client ADB in Python pur, files/python) permite shell uid=2000 pe telefonul local prin 127.0.0.1:5555 -> deblocheaza pm grant/dumpsys/input/screencap/settings put fara PC sau root; require adb tcpip 5555 o data dupa fiecare reinstall/restart al adbd.

P: linker-ul Android refuza dlopen pe /apex/com.android.adbd/lib64/*.so -> copiaza libcrypto.so+libadb_pairing_*.so in files/libs/ la runtime si incarca de acolo; pe PC Linux libcrypto se incarca direct din /usr/lib.

TRAP: pe PC-ul asta adb run-as <pkg> cp/cat din /data/data esueaza silentios pe unele cai -> extrage fisiere cu: adb exec-out run-as <pkg> cat <path> > local (nu pull, nu run-as cp).

TRAP: libdir real al APK-ului se schimba la fiecare reinstalare (hash in /data/app/~~X==/pkg-Y==/lib/arm64) -> reciteste-l mereu cu: adb shell dumpsys package <pkg> | grep codePath, apoi append /lib/arm64; calea veche da "inaccessible or not found".

P: pentru a testa o functie izolata din agent.py fara a rula bucla, exec pe fragmentul de cod cu namespace care include "__file__": <path>, _show_step, _spin, HCLR, TASK, TN -> altfel NameError: __file__ is not defined.

OK: adbd on Android auto-accepts loopback (uid=2000) adb connections WITHOUT saving key to adb_keys/user_keys, so dumpsys adb user_keys will never contain the local agent key -> do not treat absence as auth failure; verify by running adbsh and checking "AUTORIZAT"/uid instead.

TRAP: reading adbkey.pub via shell 'cat' appended filename text (" adbkey") making the key 363 chars/corrupt and silently invalid -> always check length ~356-524 and final base64 ...AQAB; regenerate from adbkey PEM via libcrypto RSA_get0_key.

P: adb shell pe Android via /home/gab/android/platform-tools/adb -s RZGL102X5AT: conexiunile adb repetate de pe laptop re-declanșează dialogul "Allow USB debugging?" (UsbDebuggingActivity) și pot agăța temporar adbd-ul (settings get / echo dau timeout) -> la shell-uri blocate intermitent, verifică mai întâi mCurrentFocus pentru UsbDebuggingActivity și închide dialogul (input tap pe Allow/Cancel sau keyevent 4) înainte de a reîncerca comanda.

P: Android adb install -r dezactivează AccessibilityService (enabled_accessibility_services se golește) -> după fiecare rebuild/reinstall de APK, reactivează cu: settings put secure enabled_accessibility_services <pkg>/<pkg>.AgentAccessibilityService ; settings put secure accessibility_enabled 1 ; verifică cu ui service -> accessibility:true.

TRAP: `dumpsys adb | grep 'user_keys='` prints the raw keystore blob with base64 padding and embedded spaces which breaks naive regex but IS the authoritative list of authorized keys -> count `QAAAAB` (keystore/laptop keys) vs `AAEAAL` (adb pubkey/agent keys) separately; a key only in `lastConnection` is NOT authorized, only keys in `user_keys` count -> to verify authorization, compare both lists, not lastConnection.

P: on this machine every `adb -s RZGL102X5AT shell ...` call restarts the USB adb connection and re-triggers the Android "Allow USB debugging" dialog, so testing via adb from the laptop keeps the dialog in an infinite loop -> when a device-side dialog must be approved, approve it ONCE with the checkbox verified checked=true then stop issuing adb commands, or disconnect USB before approving.

TRAP: `uiautomator dump` returns empty text (no <node> entries) when the focused window is still loading (e.g. Settings SubSettings) -> never conclude the screen is blank from an empty dump; re-dump after delay or check `dumpsys window | grep mCurrentFocus` first.

TRAP: verificarea amprentei ADB pt aprobare telefon trebuie facuta in ambele parti - `dumpsys adb | grep last_key_received` pe device vs amprenta cheii laptop; daca nu corespund, adbd cere mereu aprobare -> fix: `Revoke USB debugging authorizations` pe telefon, apoi reaproba.

TRAP: daca ~/.android/adbkey.pub lipseste, NU sterge adbkey privat ca sa-l regenerezi - adb NU regenereaza .pub singur si cheia se schimba -> fix: fa backup si regenereaza .pub manual.

TRAP: openssl rsa -in ~/.android/adbkey -pubout -outform DER returneaza 0 bytes pe acest sistem -> foloseste `openssl rsa -noout -text` si parseaza modulus/publicExponent in schimb.

DEAD: python cryptography nu e instalat pe acest Linux (ImportError) -> nu te baza pe el pt operatii chei RSA; foloseste openssl.

OK: adb server (this machine) autorizează per public-key fingerprint, nu per device -> cheia generată de o altă aplicație/agent (alt fingerprint) declanșează din nou dialogul Allow USB debugging chiar dacă laptopul e deja autorizat; verifică cu `dumpsys adb | grep last_key_received` și compară amprenta SHA256 a cheii trimise.

TRAP: `adb shell run-as <pkg> ls -la <dir>/prefix*` nu expandează glob (nu e shell interactiv) -> întoarce "No such file"; verifică existența fișierelor cu `run-as <pkg> ls <full-path>` per fișier sau `ls <dir>/` fără wildcard.

DEAD: adb USB-authorization for an unauthorized device cannot be bypassed from an app on the phone itself (dumpsys adb shows user_keys holds only the laptop key; app-process adbd is sandboxed SELinux and adbd refuses its key) -> don't retry adb shell am start / libadb_pairing_connection tricks to become authorized; the only path is the Wireless debugging pairing-code flow, which needs a live 6-digit code from the on-screen dialog.

OK: /home/gab/android/platform-tools/adb is the working adb binary on this box; device serial RZGL102X5AT is reachable via adb -s -> use it directly instead of hunting for adb elsewhere.

OK: on-device Python/ctypes runs via HOME=/data/data/net.sys32.agent/files/home PYTHONHOME=.../pyhome LD_LIBRARY_PATH=<pkg>/lib/arm64 <pkg>/lib/arm64/libpyexec.so script.py under run-as -> exact invocation to execute a pushed script inside the agent app context.

P: adb wireless adbd listens as uid 2000 (shell) on a random port shown in dumpsys adb / netstat, NOT 5555; /proc/net/tcp6 local_address is hex little-endian port -> decode hex to find the real pairing/connect port instead of assuming 5555.

TRAP: adb pairing always uses a fresh 6-digit code from the "Pair device with pairing code" dialog, valid ~30-60s -> never cache or reuse an old code; request a new one and run pairing immediately.

P: Android linker on this device resolves NEEDED .so by soname from default_library_paths (/system/lib64, /apex/.../bionic) BEFORE any LD_LIBRARY_PATH dir -> a bundled libcrypto.so in a private dir is silently ignored in favor of the older /system/lib64/libcrypto.so -> prefix LD_LIBRARY_PATH with the private libs dir first (LD_LIBRARY_PATH=/data/data/<pkg>/files/libs:<nativeLibDir>) so the correct version wins; verify with ctypes.CDLL of the .so that previously failed on a missing bssl symbol.

OK: /apex/com.android.adbd/lib64/libadb_pairing_connection.so has BoringSSL statically linked and does NOT need libssl.so; loading a libssl.so from /apex/com.android.conscrypt/lib64 segfaults (exit 139) against adbd's libcrypto -> do not bundle libssl for ADB pairing, only libcrypto + libadb_pairing_auth + libadb_pairing_connection.

DEAD: running the ADB pairing connection client and server in the SAME python process deadlocks the TLS handshake (both ends block on recv, pairing_connection_start returns 1 then no callback) -> local loopback testing of adbd pairing is unrepresentative; test only against the real adbd process.

TRAP: `run-as <pkg> cp /apex/com.android.adbd/lib64/<lib>.so` can fail silently (verified: liblog.so not copied, ls showed no file, rc not checked) -> /apex adbd libs are not always readable by run-as; always verify with ls after cp and fall back to /system/lib64 copies only if version-compatible.

P: Android agent on net.sys32.agent runs its python tool in-process (subprocess.Popen([sys.executable]+argv) where sys.executable=libpyexec.so), so a task sent to the agent can execute arbitrary Python with the agent's already-configured LD_LIBRARY_PATH/PYTHONHOME without needing a shell wrapper.

P: adb pairing libs live at /data/data/net.sys32.agent/files/libs (libcrypto.so, libadb_pairing_auth.so, libadb_pairing_connection.so) and must be loaded via ctypes.CDLL with RTLD_GLOBAL in order crypto -> auth -> connection before use.

P: adb shell command that returns empty intermittently for the same query -> retry or switch to `adb exec-out run-as <pkg> cat <file>` piped to host; grep-through-shell is the flaky path, exec-out cat is the reliable one.

P: Android pairing_crypto pairing_connection_start preia ownership fd (unique_fd) -> Python socket.fileno() cauzeaza dubla proprietate -> fdsan abort() ucide procesul inainte ca callback-ul sa returneze peer_info, aparent peer=NULL; fix libc.android_fdsan_set_error_level(0) inainte de pairing (nu doar LD_LIBRARY_PATH)

OK: build adb pairing pe Android ne-rootat -> libs native trebuie puse in files/libs si LD_LIBRARY_PATH sa inceapa cu files/libs (nu libdir din lib/arm64) altfel libpymodules/libpython se incarca gresit

PREVENT: la pairing wireless adb codul expira in ~30-60s -> re-deschide dialogul si extrage port+cod proaspat dupa fiecare rulare esuata

TRAP: adb pairing TLS needs CLIENT cert (mTLS) -> plain ssl wrap closes connection instantly with SSLZeroReturnError -> always load_cert_chain(pair.crt, pair.key) BEFORE wrap_socket on the pairing port.

DEAD: Samsung adbd on-device wireless pairing (pairing_auth SPAKE2 via libpyexec) completes full PEER_INFO exchange (8208B both ways, type=1) but never persists the key to dumpsys user_keys -> pairing alone can't grant adb shell on this A36; only laptop `adb tcpip 5555` produces a usable uid=2000 shell.

P: dumpsys adb user_keys shows ONLY the keystore-encoded QAAAAB laptop key (524B: 4B len=64 + 64B hash + rest), format differs from raw AAABA adb pubkey -> comparing q[5:]==our_pubkey fails; the on-device adbkey is NOT a byte copy of the laptop's authorized key.

TRAP: `run-as net.sys32.agent` python needs LD_LIBRARY_PATH=$F/libs:$libdir AND LD_LIBRARY_PATH set inside `sh -c` for adbd .so ctypes loads -> libdir is read from $F/libdir.txt (run-as ... cat); without it ctypes.CDLL of libadb_pairing_auth.so / libcrypto.so fails.

OK: `adb` regenerates a valid `~/.android/adbkey.pub` (537 bytes, prefix `40000000`) on `kill-server; start-server` -> a hand-built/wrong pub (356 bytes) gives unauthorized forever -> delete both adbkey+adbkey.pub then restart adb so it recreates them correctly

OK: `dumpsys adb` field `last_key_received=<fp>` shows the device SAW the agent's key; `user_keys=` lists only saved keys -> if last_key_received updates but user_keys stays 1 key and adbsh times out, the key is NOT persisted (localhost TCP auth doesn't save to keystore on this Samsung) -> use a key already in user_keys

DEAD: Android adbd on Samsung refuses repeated TCP auth attempts (timeout, no response) even with correct key -> triggers rate-limit/brute-force protection after several tries -> wait 2-3min before retrying, do a single clean auth attempt, close the "Allow USB debugging?" dialog first.

P: adb shell over the local adb server (/home/gab/android/platform-tools/adb -s RZGL102X5AT) hangs with <<TIMEOUT>> whenever any command runs while the on-screen UsbDebugging "Allow" dialog is open -> adbd blocks on the pending auth -> before any bulk adb-shell scripting, check dumpsys window | grep mCurrentFocus for UsbDebugging and dismiss/approve via input keyevent, then retry.

P: adb "always allow" key persists in `dumpsys adb | grep user_keys=` on the phone (format QAAAA...); a fresh RSA pubkey must match byte-for-byte or adbd silently never answers the AUTH signature packet -> regenerate key with no trailing username field, exactly 700-char base64 body, use recv_exact() loop for 24-byte adb packets or short TCP reads desync the whole handshake.

TRAP: after many failed adb auth attempts adbd on port 5555 stops replying entirely (silent timeout, no dialog) -> rate-limited/blocked, not a key problem -> restart adbd via `settings put global adb_wifi_enabled 0` then `1` then `adb tcpip 5555`, wait ~3s, retry; verify with `netstat -tln | grep 5555`.

DEAD: `adb connect 127.0.0.1:5555` from this Linux host to a phone-side loopback listener is always "Connection refused" because tcpip 5555 binds phone loopback only -> test the adb client from ON the phone via run-as, not from the laptop.

DEAD: `adb -s <serial> connect <wifi-ip>:5555` to a phone on the same LAN fails with "Connection refused" when adbd was started via `adb tcpip 5555` -> that port only binds on the device loopback/[::] for the USB-tunnelled adb, not the phone's wifi IP -> to reach it use `adb forward`/`adb reverse` through the USB serial instead of connecting to the phone's wlan IP.

OK: `adb shell dumpsys adb` shows `user_keys=` (authorized pubkeys) and `last_key_received=<sha256-fingerprint>` in the debugging_manager block -> use these two fields to tell whether a client key is truly authorized and whether adbd actually processed a new key -> if last_key_received does not change after an auth attempt, adbd rejected before registering the key.

TRAP: /data/local/tmp/*.pub and /sdcard/Download/Agent/adbkey.pub are NOT the keys adb actually uses -> adb daemon reads /data/misc/adb/adb_keys (root) or the app's own dir (run-as net.sys32.agent) -> when hunting "which key is authorized" on this device, cat /data/misc/adb/adb_keys via run-as/root, not sdcard or /data/local/tmp copies.

OK: net.sys32.agent private files are readable with `adb shell run-as net.sys32.agent ls -la /data/data/net.sys32.agent/files` -> app runs debuggable so run-as works without root -> use run-as for any per-app file inspection on this device instead of requesting root.

TRAP: local ADB wireless on 6100 was already occupied by the laptop's own adb connection -> an app/agent connecting to 127.0.0.1:6100 silently fails while the PC holds the port -> before pointing a new client at the wireless pair port, disconnect this host first (`adb disconnect`) or use 5555.

TRAP: `adb shell netstat -tln | grep <port>` pe device arată porturi LISTEN/ESTABLISHED dar NU dezvăluie cine e peer-ul când IP-ul remote nu e în subnetul local -> verifică `dumpsys adb` pentru last_key_received/user_keys și `adb -s <serial> disconnect` apoi re-check netstat ca să vezi dacă revine (persistent=alt client, dispare=clientul tău)

OK: adb -s <serial> kill-server kills the whole adb server on this desktop, not just that device -> after it the daemon restarts at tcp:5037 and any existing wireless-debug ESTABLISHED sockets on the phone side persist untouched -> to actually drop phone-side 6100/6101 connections you must toggle Wireless debugging OFF and/or reboot the device, not rely on kill-server.

P: /home/gab/android/platform-tools/adb is the adb binary path on this desktop; adb is not on PATH -> invoke it by absolute path or define ADB=/home/gab/android/platform-tools/adb in every script.

TRAP: Android `netstat -tn` shows remote 10.x.x.x:7777/7778 pairs as ESTABLISHED on ports 6100/6101 even when settings global adb_wifi_enabled=0 -> this is normal adbd wireless-debug listener behaviour, NOT proof of an intrusion -> verify by checking whether the remote IP matches this laptop's own IP before flagging a security incident.

TRAP: resolving a device's own mobile IP with `ip route get <remote>` returns "via 192.168.3.1 dev wlan0 table 1045" -> table 1045 is the Android per-network routing table for the rmnet/mobile data interface, not a sign the traffic is spoofed -> interpret table 104x as mobile-data route, not anomaly.

TRAP: `adb -s <serial> exec-out run-as <pkg> cat <file>` intoarce 0 bytes desi fisierul exista -> exec-out+run-as+cat e fragil pe Samsung -> foloseste `adb shell run-as <pkg> cat <file>` sau `head -25`/`grep -n` in loc de cat.

DEAD: `adb shell run-as <pkg> grep -n '...' <file>` cu pattern-uri multi-alternativa intoarce gol desi `head` pe acelasi fisier arata continut -> grep+run-as pe Android e nesigur -> verifica cu `head`/`sed` direct.

P: /home/gab/android/platform-tools/adb este binarul adb folosit pe acest desktop (nu `adb` din PATH) -> foloseste calea absoluta in scripturi.

TRAP: cand USB-ul e instabil, `adb -s <serial>` da "device not found" si apoi "unauthorized" -> repornirea adbd/Telefon re-apare cu "device" dupa ~25s -> pune retry cu poll pe `adb devices` inainte sa conchizi ca tool-ul nu merge.

DEAD: adb wireless debugging port 6100 stays ESTABLISHED to remote 10.0.0.2 and survives even `adb kill-server` + `settings put global adb_wifi_enabled 0` -> not the local host's own adb; to free the port requires phone reboot or revoking debug authorizations, agent can't kill it via shell.

TRAP: pe acest telefon porturile wireless ADB sunt fix 6100 (TLS/listen) și 6101 (pairing), iar conexiunea ESTABLISHED cu IP-ul PC-ului rămâne agățată după ce UI-ul arată OFF → `adb kill-server` pe PC nu eliberează; doar restart telefon sau reconnect din UI eliberează.

DEAD: adb shell cat on /sdcard/Download/Agent/context.json works without root, but run-as net.sys32.agent fails ("files/context.json: No such file or directory") because the app's private dir is not at files/context.json remotely -> read agent state from /sdcard/Download/Agent/context.json via plain adb shell cat, not run-as.

OK: adb -s RZGL102X5AT shell for SM-A366B (Android 16) works headless from this Linux box with /home/gab/android/platform-tools/adb binary -> use that absolute path and -s RZGL102X5AT for all device commands.

TRAP: adb `android.settings.WIRELESS_DEBUGGING_SETTINGS` intent returns "unable to resolve" on this Samsung Android device -> use `am start -a android.settings.SETTINGS` then tap "Wireless debugging" via accessibility bridge instead.

OK: adb pairing connection flow proven working via libadb_pairing_auth.so: TLS1.3 mTLS with tls.crt/tls.key -> SPAKE2 (pairing_auth_client_new/get_spake2_msg/init_cipher returns 1) -> PEER_INFO encrypted, but final decrypt returns 0 -> pairing code pair is valid only ~60s, old codes give init_cipher=1 but decrypt=0.

DEAD: adb wireless (TLS A_STLS) on Samsung SM-A366B - ports from Settings "IP address & Port" (6100, 33827, 32813) accept TCP but never reply to TLS or A_AUTH (EOF/timeout) -> only service.adb.tcp.port 5555 speaks A_AUTH and works; do not bother retrying wireless TLS, use 5555.

TRAP: `ip -4 -br addr` on this laptop shows only enp2s0 192.168.1.136 (no 192.168.3.x) -> laptop and phone are on DIFFERENT subnets, so any 10.0.0.2 / 192.168.3.75 seen in phone netstat is NOT this laptop; verify with `ip route get <ip>` before assuming a device is you.

OK: check which uid owns an ADB listen port on the phone via getprop/adb shell `/proc/net/tcp6` + `netstat -tln` -> uid=2000 (shell) means adbd legacy A_AUTH, not a wireless TLS service; distinguishes usable ports without guessing.

DEAD: Wireshark on this Linux desktop cannot capture the Android USB/adb tcp:5555 loopback traffic -> loopback iface and Android-internal sockets are not visible to host capture -> use `adb -s RZGL102X5AT shell` / dumpsys directly instead of host packet capture.

OK: real adbd process state on Android is readable via `adb shell ps -A | grep adbd` and `adb shell getprop service.adb.*` -> adb forward/connect output is stale -> always confirm with ps/getprop before believing port state.

P: /home/gab/android/platform-tools/adb is the working adb binary and device serial RZGL102X5AT is the connected Android device here -> adb from PATH may differ -> always call the absolute path with `-s RZGL102X5AT`.

DEAD: Python ssl module on this Linux desktop (and Android python build) does not expose SSL_export_keying_material, so ADB wireless TLS pairing cannot be completed from Python alone -> SPAKE2 key derivation needs TLS ExportKeyingMaterial(64) appended to the code -> use libadb_pairing_connection.so or a real PC adb pair client instead of hand-rolling pairing in Python.

DEAD: android adb wireless pairing from Python fails: ssl module lacks TLS ExportKeyingMaterial -> cannot do pairing code path -> fall back to USB `adb tcpip 5555` once, then connect 127.0.0.1:5555.

OK: pull Linux->device via adb push to /data/local/tmp then run-as <pkg> cp to app-private dir; run-as can read/write but push cannot target private paths directly.

P: On this machine `run-as <pkg> sh -c '...'` needs the whole command single-quoted; nested " and $ inside get mangled -> prefer writing a script file and executing it instead of long inline sh -c.

OK: adb exec-out run-as net.sys32.agent cat <file> -> read app-private files without root; run-as fails silently on non-debuggable apps -> prefer this over su for net.sys32.agent paths.

P: agent tool descriptions bundle DECISION RULES inline ("use adbsh ONLY for pm/appops/settings put, NOT for screen reads") -> the LLM picks native android/python/bash first and adbsh last -> put per-tool when-to-use rules in the description field, not just the system prompt.

TRAP: adb shell rm -f /sdcard/Download/Agent/context.json then am start -> app replays old context unless force-stop precedes rm -> always am force-stop net.sys32.agent, then rm context.json, then am start.

OK: Android app's own dirs live under /data/data/<pkg>/files and are fully readable/writable from shell via `adb shell run-as <pkg> sh -c '...'` (also cat/ls/rm) -> use run-as to inspect/generate/delete app-private files without root, e.g. run-as net.sys32.agent rm -f files/adbkey

P: native libdir path embeds the install hash (/data/app/~~<hash>==/<pkg>-<hash>==/lib/arm64) and CHANGES on every reinstall -> never hardcode it; re-read with `adb shell dumpsys package <pkg> | grep codePath` and append /lib/arm64, or exec fails with "No such file or directory

DEAD: launching an exec:ed .so with the wrong LD_LIBRARY_PATH fails as `libpyexec.so: No such file or directory` even though the file exists -> the error is from the dynamic loader, not from a missing file

OK: adb tcpip 5555 on Android + self-generated adbkey.pub in app files dir -> adb connect 127.0.0.1:5555 gets authorized -> run-as app sh with LD_LIBRARY_PATH=<codePath>/lib/arm64 libpyexec.so script.py works for testing

DEAD: Android accessibility_enabled resets to 0 after am force-stop of the accessibility service app -> re-enable with settings put secure enabled_accessibility_services <pkg>/<Service> then accessibility_enabled 1, verify via ui service json accessibility field

TRAP: uiautomator dump reads app terminal as a single multiline text node with &#10; entities -> parse text and unescape &#10;/&amp; to see full output, and empty=agent died before printing (check ps -A)

P: Android MainActivity permisiuni runtime sunt asincrone -> requestPermissions nu blocheaza, codul de dupa ruleaza imediat cu permisiuni needate -> muta tot startup-ul (extractAssets/startPython/service) in onRequestPermissionsResult, cu flag coreStarted, si porneste direct daca allEssentialPermsGranted() e deja true la onCreate.

OK: Android app data/assets dir exact paths on device RZGL102X5AT: /data/data/net.sys32.agent/files/ (run-as net.sys32.agent ls) and /data/data/<pkg>/files/assets/ -> use these to verify first-run state before app has run

OK: /sdcard/Download/Agent/memory.md on phone persists across app uninstall (pm uninstall keeps /sdcard) -> back up via adb shell cat before uninstalling app to avoid losing agent memory

TRAP: uiautomator dump XML wraps long terminal text with &#10; entities and blank text nodes appear for EditText/scrollable views -> replace &#10; with \n and filter nodes by (y2-y1)>300 to find real content, else you get empty-looking dumps

TRAP: ADB uninstall/install nu readuce app-ul in foreground -> dumpsys window mCurrentFocus poate arata com.android.settings (dialog permisiuni), nu app-ul -> verifica cu uiautomator dump, nu presupune ca app-ul ruleaza.

OK: adb install -r pe net.sys32.agent nu aplică APK-ul nou dacă procesul vechi rulează -> ecranul arată codul VECHI chiar dacă sursa și APK-ul sunt noi -> verifică `dumpsys package <pkg> | grep lastUpdateTime` vs mtime APK și fă uninstall+install curat, apoi am force-stop + am start.

OK: uiautomator dump pe Android scrie implicit /sdcard/window_dump.xml, nu /data/local/tmp -> `cat /data/local/tmp/xxx.xml` returnează gol -> scrie explicit `uiautomator dump /data/local/tmp/x.xml` înainte de cat.

TRAP: assets_vNN din MainActivity.kt controlează re-extracția assets la pornire -> dacă nu incrementezi, modificările din assets nu ajung pe device -> incrementează .assets_vNN la fiecare schimbare de assets.

DEAD: runOnUiThread in a Thread loop renders all iterations at once because UI thread batches late -> countdown appears instant -> use android.os.Handler(Looper.getMainLooper()).postDelayed for real 1s ticks

P: adb package install/uninstall for net.sys32.agent at /home/gab/android/platform-tools/adb -s RZGL102X5AT; APK output at workspace/app/net.sys32.agent/app/build/outputs/apk/debug/app-debug.apk -> adb install -r can hit version-conflict; do uninstall+install for fresh state

P: MainActivity.kt calls startPython() async (Thread) so any UI message printed from runSetup appears BEFORE Python setup output -> to order output after [setup] lines, print from inside startPython after sp.waitFor(), not from runSetup

OK: ADB device serial for the net.sys32.agent test phone is RZGL102X5AT; adb at /home/gab/android/platform-tools/adb -> use -s RZGL102X5AT for all adb shell/dumpsys/uiautomator commands.

OK: read Android app UI screen text headlessly via `adb -s SERIAL shell "uiautomator dump /data/local/tmp/x.xml >/dev/null 2>&1; cat /data/local/tmp/x.xml"` then regex text="..." on nodes with bounds height>300 -> reliable way to assert on-screen state without a GUI.

OK: inspect app-private files on non-rooted Android via `adb shell run-as net.sys32.agent ls -la /data/data/net.sys32.agent/files/` -> works without root for debuggable apps and is how to verify a persistence marker file was written.

OK: adb shell uid 2000 (shell) is reachable on this desktop via /home/gab/android/platform-tools/adb -s RZGL102X5AT without root; grants dumpsys, /proc/net/tcp, logcat -d, pm list packages, appops get, settings put/delete, input keyevent, screencap, uiautomator dump -> use it for privileged Android inspection/automation instead of assuming root-only.

DEAD: adb shell uid 2000 cannot read /data/data or run su -> for app-private data next time use `run-as <pkg>` only on debuggable apps, never expect plain shell access.

P: agent context for a run is persisted at /sdcard/Download/Agent/context.json on device RZGL102X5AT, pullable via `adb -s RZGL102X5AT shell cat` -> read it to recover the full tool/assistant transcript of prior steps.

DEAD: adb tcpip port must be exactly 5555; a typo like 5555->55555 reads back in getprop service.adb.tcp.port and adbd listens on 55555, so client connecting 127.0.0.1:5555 gets ECONNREFUSED -> after adb tcpip, verify with `getprop service.adb.tcp.port` equals 5555 before expecting adbsh to work.

P: `adb tcpip <port>` setter must match the hardcoded port in the app's adb client (`adb_client.py` `port=5555`); setting `adb tcpip 55555` leaves port 5555 refused and adbsh times out -> always `adb tcpip 5555` and verify with `adb shell getprop service.adb.tcp.port` returning 5555.

P: On this headless Linux box `adb` lives at `/home/gab/android/platform-tools/adb` (platform-tools only, ~11MB `adb` binary); no Android Studio/SDK needed -> invoke that absolute path, no PATH setup required.

P: Running Python inside the app's sandbox from this desktop shell works via `run-as net.sys32.agent sh -c 'cd .../files/python && HOME=.../home PYTHONHOME=.../pyhome LD_LIBRARY_PATH=.../libs:<codePath>/lib/arm64 timeout N <libdir>/libpyexec.so script.py'` -> `run-as net.sys32.agent` alone cannot exec the bundled interpreter; libdir from `dumpsys package net.sys32.agent | grep codePath`.

TRAP: Two different adbd listens can coexist conceptually but only one port actually answers; testing both ports (`socket.connect` to 5555 vs 55555) shows 5555 REFUSED / 55555 CONNECTED depending on the last `adb tcpip` -> never assume from a previous successful test; re-check the live port each session.

OK: `adb -s <serial> shell getprop service.adb.tcp.port` returns the actual TCP port adbd listens on (5555, 55555, or any `adb tcpip <n>` value) -> do not hardcode 5555 in adb clients, read this prop first then fall back to probing 5555/55555/5556 -> verified live: `adb tcpip 55555` starts adbd LISTEN on tcp6 [::]:55555 and rejects 5555.

TRAP: adbd listens on exactly ONE TCP port at a time; `adb tcpip 5555` then `adb tcpip 55555` -> old port stops listening, connections to the stale port fail ConnectionRefusedError -> when a local adb client gets EACCES/refused, re-read getprop service.adb.tcp.port before blaming auth or libs.

P: Android agent adb port auto-detect -> agentul citeste getprop service.adb.tcp.port la runtime -> orice port setat cu `adb tcpip N` (1-65535) e preluat automat, nu hardcoda 5555

TRAP: adb tcpip schimba portul adbd dar si getprop service.adb.tcp.port -> dupa adb tcpip N re-ruleaza `adb shell getprop service.adb.tcp.port` inainte de a te reconecta, altfel crezi ca adbd a picat

OK: testare port adb neobisnuit pe RZGL102X5AT -> `adb -s RZGL102X5AT tcpip 9999` apoi `adb shell getprop service.adb.tcp.port` confirma detectia -> revino la 5555 cu `adb -s RZGL102X5AT tcpip 5555` dupa test

OK: adb device serial RZGL102X5AT is the connected Android phone -> all adb calls need `adb -s RZGL102X5AT` -> use /home/gab/android/platform-tools/adb with that serial

OK: Android APK audit on this machine -> unzip -l on app-debug.apk lists assets/python/ and lib/arm64-v8a/ contents -> use to verify packaging without installing

P: /home/gab/Desktop/agent/workspace/app/net.sys32.agent/ holds the Android agent project -> main sources under app/src/main/{java/net/sys32/agent,assets/python,jniLibs} -> use these absolute paths next time

OK: `git add -A` + `git commit` in /home/gab/Desktop/agent works from bash tool and pushes to github.com:fetidness/android_agent.git master -> use it for committing repo changes there.

TRAP: /sdcard/Download/Agent/context.json scris de app nu e JSON valid (are "Extra data" dupa array, ~76 bytes in plus) -> json.loads() esueaza cu "Extra data" -> foloseste json.JSONDecoder().raw_decode(raw) care intoarce (obj, idx) si parseaza pana la primul obiect valid.

OK: analiza conversatiei agentului Android din context.json: raw_decode iti da 301 mesaje; mesajele lungi sunt trunchiate in afisare cu "[... N chars in the middle, NOT LOST: ... logs/tool_<ts>.log ...]" -> textul complet e in /home/gab/Desktop/agent/temp/logs/tool_*.log, citeste acel log dupa timestamp.

OK: adbd pe acest telefon asculta pe portul 1234 (nu 5555) - getprop service.adb.tcp.port; adb_client.py auto-detecteaza portul, dar cheia noua necesita aprobare o singura data altfel connect() da "AUTH -> trimit RSAPUBLICKEY" apoi TimeoutError in _recv.

DEAD: ninja from Termux repo on Android arm64 is broken (libandroid-spawn.so) - every build command fails code=127; use samu (samurai 1.3) as ninja replacement with same CLI.

P: adb (`/home/gab/android/platform-tools/adb`, device RZGL102X5AT) comanda `run-as net.sys32.agent` executa cu context SELinux al aplicatiei -> fisierele in /data/local/tmp au context shell si `.so` incarcate cu dlopen dau "couldn't map ... Permission denied" -> copiaza librariile/pachetele Python in /data/data/net.sys32.agent/files/... inainte de import.

P: pe acest telefon Python-ul ruleaza ca `run-as net.sys32.agent sh -c 'HOME=.. PYTHONHOME=.. LD_LIBRARY_PATH=<files/libs>:$CODE/lib/arm64 <libdir>/libpyexec.so script.py'` unde libdir=`$(dumpsys package net.sys32.agent | grep codePath | cut -d= -f2)/lib/arm64` -> libpyexec.so e executabilul Python (nu exista python binar).

TRAP: pentru Python pe telefon, `sys.path.insert(0,"/data/local/tmp/...")` face importul sa incerce .so din /data/local/tmp si esueaza cu Permission denied, mascand faptul ca o copie valida exista in site-packages -> sterge/evita path-ul din /data/local/tmp in scriptul de test.

P: Termux packages on this Samsung are managed without root/Termux via /data/local/tmp/tpm + tpm.py (repo packages.termux.dev apt termux-main aarch64); toolchain.py/tpm.py in assets/python reach them; check state with `toolchain.py check` -> clang/python/ld/ar/git show false until a full `install` bootstrap (~500MB) runs.

TRAP: run-as net.sys32.agent python on this device works only with the full env prefix (HOME=.../files/home PYTHONHOME=.../files/pyhome LD_LIBRARY_PATH=.../files/libs:<codePath>/lib/arm64 and invoke <libdir>/libpyexec.so script.py) -> bare run-as ... python3 script.py fails -> get codePath via `dumpsys package net.sys32.agent | grep codePath` and build that exact prefix.

OK: toolchain.py/tpm.py descarca .deb-uri Termux (bionic) in /data/local/tmp/tpm/usr si ruleaza pe Android fara Termux -> pentru compilare nativa pe telefon foloseste samu nu ninja (ninja Termux e rupt: libandroid-spawn.so, exit 127) si tine binarele in /data/local/tmp (nu /sdcard, montat noexec)

TRAP: /sdcard pe aceasta masina Android e montat noexec -> orice binar extras/copiat acolo da "Permission denied" la exec -> pune executabilele in /data/local/tmp sau /data/data/<pkg>/files

OK: pentru a rula python+libs din APK in shell foloseste run-as net.sys32.agent cu PYTHONHOME=/data/data/net.sys32.agent/files/pyhome si LD_LIBRARY_PATH=<codePath>/lib/arm64 -> altfel import-urile esueaza

DEAD: `pm install -r /data/local/tmp/app-debug.apk` before pushing the file -> prints a Binder stacktrace and NO "Success", focus stays on LauncherActivity so the app never starts -> always `adb push <host-apk> /data/local/tmp/app-debug.apk` first, verify push says "1 file pushed", then pm install and require "Success" in output before launching.

OK: Android app running under run-as (uid~10377) CANNOT read /data/local/tmp (SELinux Permission denied) while ADB shell uid=2000 can -> any file a Python script needs to read from shell context (tpm.py etc) must be adb-pushed to /data/local/tmp, not left in app files dir.

OK: adb_client.py inside Termux-built python3 toolchain (/data/local/tmp/tpm/usr/bin/python3) fails with ConnectionRefusedError because device adbd TCP port is 1234 not 5555 -> when running scripts as uid=2000 use subprocess /system/bin/sh directly (os.geteuid()==2000 guard) instead of routing through adb_client.

OK: Termux repo package python-pip does NOT exist; pip ships via package python-ensurepip-wheels (3.14.6) -> install that, then python3 -m ensurepip --upgrade to activate pip.

P: toolchain at /data/local/tmp/tpm/usr requires BOTH PATH=/data/local/tmp/tpm/usr/bin and LD_LIBRARY_PATH=/data/local/tmp/tpm/usr/lib set together, otherwise every binary (python3, clang) fails with 'library libandroid-support.so not found' even though the .so is present.

P: cand verifici textul scris intr-un EditText Android prin uiautomator dump, NU folosi regex cu text="([^"]*)" dupa class EditText -> caracterele speciale (paranteze, diacritice) pot face regexul sa rateze desi textul e acolo -> verifica intai dumpsys window mCurrentFocus sa confirmi app-ul in focus, apoi cauta textul brut in XML cu re.finditer pe toate nodurile.

TRAP: adb shell input text cu spatiu -> trebuie inlocuit spatiul cu %s (input text 'a%sb') altfel textul nu se scrie -> scrie intotdeauna task.replace(' ','%s') inainte de input text.

OK: /data/local/tmp full wipe -> `rm -rf /data/local/tmp/*` and per-file rm fail silently on some entries, but `find /data/local/tmp -mindepth 1 -maxdepth 1 -exec rm -rf {} +` empties it completely with no error output.

TRAP: pm install cu cale de pe host (ex /home/gab/...) esueaza cu Binder exception -> APK-ul trebuie mai intai adb push /data/local/tmp/ si apoi pm install -r de acolo

TRAP: `input text 'fraza cu spatii'` pe shell Android scrie zerouri (text gol, verificat cu uiautomator dump) -> inlocuieste spatiile cu %s: `input text 'fraza%scu%sspatii

DEAD: Termux .deb packages contain ONLY data.tar.xz (no gz variant) -> Python here has NO lzma module (_lzma missing from build, "No module named 'compression._common'" on import lzma/gzip/tarfile) and Android toybox tar has no xz support, so extracting .deb in pure Python is impossible -> do not attempt offline .deb extraction without a real xz/lzma binary; either bootstrap via the shell path (tpm.py through adbsh as uid 2000) or add _lzma to the Python build.

P: shells on this Android device: /system/bin/tar is toybox 0.8.12 (no xz), no standalone xz/busybox, /system/lib64/liblzma.so is stripped (no lzma_stream_* symbols usable via ctypes) -> gzip/CA/HTTP work but xz decompression has no local tool.

TRAP: run_adbsh_tool in agent.py capped SIGALRM at min(int(timeout),60) -> any long adb-shell operation (toolchain bootstrap, big copies) died at 60s with "[TIMEOUT 40s]" even when caller passed timeout=3600 -> fix was _sig.alarm(max(min(int(timeout),3600),1)); verify by grepping for min(int(timeout),60) before trusting long bootstrap runs.

P: Android app uid (run-as) cannot create files under /data/local/tmp (PermissionError Errno 13); only the shell uid can -> stage extracted files inside /data/data/<pkg>/files/ then copy to /data/local/tmp via adbsh.

P: Python urllib on this device fails TLS with CERTIFICATE_VERIFY_FAILED unless an explicit CA bundle is passed (ssl.create_default_context(cafile=...)) -> always pass a cafile (certifi or /system/etc/security/cacerts) for HTTPS downloads in on-device Python.

OK: adb push toolchain.py to device then run via `run-as net.sys32.agent sh -c 'HOME=... PYTHONHOME=... LD_LIBRARY_PATH=<pkg>/lib/arm64:/data/data/net.sys32.agent/files/libs libpyexec.so script.py'` -> works for testing python code on the phone; recreate /data/data/net.sys32.agent/files/pyhome/lib/python3.14/compression/_common/{__init__.py,_streams.py} after every app rebuild because it gets wiped.

TRAP: Termux .deb extraction via pure-python untar loses symlinks (libX.so.N.M.P -> libX.so.N, clang->clang-21, ld->lld, ld.lld->lld, libbz2.so.1.0) -> clang reports "unable to execute command: No such file or directory" on link step -> fix by re-creating all symlinks after extraction; lld needs both `ld` and `ld.lld` names.

TRAP: Android shell has no `strings`/`readelf`/`objdump`/`file` by default -> analysing binaries from adb needs those dumped manually or via python on-device.

TRAP: adb shell commands run from app process (uid=untrusted_app) cannot execute binaries in /data/local/tmp due to SELinux -> compile/run tools must shell out via `adb shell` (uid=2000) instead of subprocess in the app -> route native tool invocations through run_adbsh_tool.

TRAP: on this Android device /sdcard and /storage are mounted noexec -> any compiled binary or script placed there fails with "Permission denied" or "can't execute" -> always put executables in /data/local/tmp and chmod +x there.

P: Android app process (net.sys32.agent, uid 10378) cannot write or read /data/local/tmp directly but shell uid=2000 can -> to stage files into /data/local/tmp from the app, write to /sdcard staging then copy via adb shell (run-as only reaches app-private dirs).

TRAP: AAPT2 silently drops asset directories whose name begins with underscore (e.g. compression/_common/) -> imports like `from compression._common import ...` fail with ModuleNotFoundError at runtime -> deliver the file with a non-underscore name (_streams_data.py) and recreate the underscore package dir at first runtime launch.

TRAP: python tarfile on this Android/Python3.14 build fails when its compression backend (_common) is missing -> implement a minimal pure-Python tar reader (512-byte headers) instead of relying on tarfile for .deb extraction.

TRAP: adb_client.py had a global signal.alarm(40) that aborts long-running adb shell ops with "[TIMEOUT 40s]" -> make the timeout configurable (ADB_GLOBAL_TIMEOUT, default 600s, 0 disables) before running bootstrap/compile that exceed 40s.

DEAD: symlink(.deb typeflag 2) members are skipped by the tar reader -> recreate libX.so.N -> libX.so.N.M and tool aliases (clang/ld/ar) manually via a _fix_symlinks() pass after extraction.

TRAP: `pm uninstall` returning "Failure [DELETE_FAILED_INTERNAL_ERROR]" does NOT mean the app is still installed -> verify with `pm list packages | grep <pkg>` -> package may be already gone; don't retry uninstall endlessly.

TRAP: adb shell run-as <pkg> python import fails with ImportError "cannot import name X from Y" even when the target .py file exists and has correct size -> stale __pycache__/*.pyc left over from an earlier broken state shadows the source -> always "run-as <pkg> rm -rf <dir>/__pycache__ <dir>/_common/__pycache__" before retesting imports; verify with ls -la that the .py is real and then purge caches.

PREVENT: when an agent/script patches a Python package split (e.g. compression._common should be a PACKAGE dir with __init__.py + _streams.py, not a _common.py file) -> a lone _common.py file makes `from compression._common import _streams` fail though os.path.exists is true -> fix must os.remove the _common.py file AND os.makedirs the _common/ dir, guarded by `if os.path.isdir(common) and os.path.exists(common/_streams.py)` not just isdir.

TRAP: Android app process (uid 10381) cannot see or write /data/local/tmp (SELinux) -> os.listdir/open there from app-side Python returns empty or PermissionError silently, producing zero symlinks/artifacts -> do all /data/local/tmp inspection, symlink creation and file writes via adb shell (uid 2000), never from in-app Python os calls.

TRAP: Python imports a stale __pycache__/_common.pyc built from an earlier file layout -> new module files on disk are ignored and import keeps failing with ModuleNotFoundError -> delete __pycache__ dirs after any module-file restructuring before retesting.

OK: Android SDK sidecar build on this machine: bash -lc 'cd /home/gab/Desktop/agent/workspace/app && ./build_app.sh' rebuilds and reinstalls the APK, bumping assets_vN in MainActivity.kt forces asset refresh -> run this exact script after editing assets/python/*.py.

OK: /data/local/tmp on Android is reachable only via shell uid=2000 (adbsh/ADB), not from the app process (uid~10300 untrusted_app, SELinux blocks) -> any os.listdir/stat/mkdir/cp/chmod/exec there from the app is silently empty or denied -> do all such ops through shell, verify by listing via shell

OK: Termux toolchain symlinks (libz.so.1->libz.so.1.3.2, clang->clang-21, ld->lld->ld.lld, llvm-*) must be recreated -> a clang run fails with 'library libz.so.1 not found' or 'clang: not found' -> regenerate symlinks generically (libX.so.N.M.P -> libX.so.N and libX.so) plus specials before compiling

OK: /sdcard on Android is mounted noexec -> a binary copied there gives "Permission denied" on run -> keep source .c/.cpp on /sdcard but put executables in /data/local/tmp and run them via shell

DEAD: Python import fails with stale __pycache__ even after restoring the real module file -> old bytecode from a deleted package shadows new source -> shutil.rmtree the __pycache__ dir after replacing a module/package

OK: For 'from pkg._sub import x' to work, pkg must be a directory with __init__.py, not a single .py file -> mis-shaped package breaks transitive imports (e.g. lzma -> compression._common._streams) -> create _common/__init__.py + _common/_streams.py, not _common.py

OK: adb on this headless desktop is /home/gab/android/platform-tools/adb, device SM-A366B serial RZGL102X5AT -> phone /sdcard/Download/Agent/context.json holds the Android-agent conversation as a JSON array -> read it via `adb -s RZGL102X5AT shell cat /sdcard/Download/Agent/context.json` (public path, no run-as) and parse with json.JSONDecoder().raw_decode (may have trailing data).

P: context.json transcript is truncated per-message with marker `[... N chars in the middle, NOT LOST: the complete text in logs/<file>.log ...]` -> those logs/ files are self-referential noise (each log is itself truncated pointing to another), NOT a recoverable full transcript -> analyze the context.json messages directly; do not chase the log chain.

OK: Android agent builds natively on-device into /data/local/tmp/tpm/usr (clang-21, python3.14, lib/ site-packages) -> missing ld.lld/clang symlinks break linking ("unable to execute command: No such file or directory") -> fix with `ln -sf lld $PREFIX/bin/ld.lld` and `ln -sf clang-21 clang` then compile with `-fuse-ld=lld`.

TRAP: bash tool on this machine intermittently returns EMPTY output for heredocs/`cat`/redirected commands (rc reported but no text) -> do not conclude "no output"/"command failed"; re-run the same command through the python tool with subprocess.run(capture_output=True) and decode with errors="replace".

OK: to run a command on the connected Android device and get binary-safe text back, use `adb -s <serial> exec-out cat <path>` via python subprocess -> plain `adb shell cat` mangles non-UTF8 bytes (UnicodeDecodeError on 0xb7 etc), so capture bytes and .decode("utf-8","replace").

TRAP: python f-strings cannot contain C/SQL braces or `{`-heavy heredocs -> SyntaxError "expecting '=' after ':'" -> write the shell/C script to a real file (open().write) and push/run it, never inline braces inside an f-string.

PREVENT: a single python loop doing patchelf/readelf over 200+ files can end in "Segmentation fault" after the work is already done -> always re-verify the RESULT (readelf/grep counts) instead of trusting the tool's exit code or "Segmentation fault" line.

TRAP: adb shell dumpsys/uiautomator dump and screencap can return stale launcher/menu content even when mCurrentFocus names the target app -> you misread screen state -> verify app visibility by running screencap to a file and inspecting the image, not by parsing the ui.xml or dumpsys focus.

OK: adb -s <serial> shell monkey -p <pkg> -c android.intent.category.LAUNCHER 1 reliably relaunches an app that am start reports as already foregrounded.

TRAP: bash tool `adb exec-out screencap -p > file.png` occasionally returns empty/no output while the redirect still creates a 0-byte or missing file -> use `python subprocess.run([ADB,"-s",S,"exec-out","screencap","-p"],capture_output=True).stdout` and write bytes, then verify len>0.

P: check UI dialogs/permissions on Android without tapping blindly -> `adb -s <S> shell uiautomator dump /data/local/tmp/d.xml 2>&1 >/dev/null; cat /data/local/tmp/d.xml` then regex `text="..."` bounds to compute tap center; if a transient dialog is gone, dump returns app text instead and the search yields nothing.

OK: bulk-grant Android runtime permissions non-interactively to skip all dialogs -> `for p in CAMERA RECORD_AUDIO ACCESS_FINE_LOCATION ...; do adb -s <S> shell pm grant <pkg> android.permission.$p; done`; empty stderr = granted.

OK: logcat survives app reinstall but /data/local/tmp is wiped by `rm -rf /data/local/tmp/*` -> re-downloads of large toolchains should stage cache outside /data/local/tmp (e.g. /sdcard/Download/Agent/tc_stage) so cleanup does not destroy 295MB of already-fetched packages.

OK: adb shell uiautomator dump then grep for text/bounds -> bounds of input box collide with STOP/SEND buttons when layout shifts, tapping a stale coordinate hit STOP and killed the task (SIGINT) -> re-dump before every tap and pick the node whose text is '→' (send), never hardcode x,y.

OK: python multi-line scripts with many printf/long lines sent via adb shell get truncated (agent reported 'output decalat', 'comanda multi-linie e trunchiata de adbsh') -> adb shell mangles/has length limits on complex quoting -> write the script to a file and push it, then run, instead of one giant inline command.

TRAP: grep -c 'pattern' on files under /data/data/<pkg> via `adb shell run-as` returned 0 even though the strings were present -> adb shell grep over run-as has quirks/truncation -> pull with `adb exec-out run-as <pkg> cat <file>` and grep locally.

DEAD: `adb shell input text` requires the target EditText to already hold focus -> text lands nowhere if field not tapped first -> tap the input box (found via uiautomator bounds) before `input text`, and replace spaces with %s.

OK: pip/meson builds that need Python.h failed with "Compiler cython cannot compile programs" -> pkg-config .pc files shipped with a Termux prefix (/data/data/com.termux/files/usr) while python3.pc alone was patched -> sed-replace the prefix in ALL $PREFIX/lib/pkgconfig/*.pc and $PREFIX/share/pkgconfig/*.pc, not just python3.pc.

OK: importing C++ extensions (numpy) failed with "cannot locate symbol _ZTVNSt6__ndk1..." -> extension .so lacked NEEDED libc++_shared.so -> run patchelf --add-needed libc++_shared.so on every .so in site-packages (19 fixed) and add -lc++_shared to LDFLAGS.

TRAP: android platform-tools `adb exec-out screencap -p` on Samsung SM-A366B (Android 16) returns a valid PNG that is ONLY the Agent app window when captured via exec-out; `adb shell screencap` variants differ -> always pass `-s <serial>` (RZGL102X5AT) and verify byte size >100KB before trusting the image, otherwise you may read a stale/blank frame.

OK: reading the agent's live terminal on this phone works via `adb -s RZGL102X5AT exec-out screencap -p` saved to /home/gab/Desktop/agent/temp/*.png then the look tool -> avoids needing GUI; polling this every 60s is the reliable progress check, not `ps | grep` (python3.14 compiled builds spawn processes grep misses).

P: numpy compiled natively on this phone lives in /data/local/tmp/tpm/usr with wrapper script /sdcard/Download/Agent/workspace/numpy_build/numpy-env.sh -> use `sh numpy-env.sh -c "..."` to run numpy on-device without re-deriving PATH/LD_LIBRARY_PATH.

OK: verifying a phone-side build from this desktop works with `adb -s RZGL102X5AT shell 'export PATH=/data/local/tmp/tpm/usr/bin:/system/bin LD_LIBRARY_PATH=/data/local/tmp/tpm/usr/lib HOME=/data/local/tmp; /data/local/tmp/tpm/usr/bin/python3.14 -c "import numpy;print(numpy.__version__)"'` -> import test proves binaries actually run, not just that files exist.

TRAP: `ps -A | grep python3.14` on this phone returns 0 even while a compiled python build is actively running (process name/shown args don't match) -> never use ps-grep as liveness proof for the on-device build; poll the agent's terminal screenshot or a logfile instead.

TRAP: os.path.exists in the agent sandbox.py does NOT see /data/local/tmp files -> file checks return false negatives -> verify toolchain/device files only via _sh (adb shell test -f), never os.path.exists.

TRAP: patchelf cannot patch a binary that is currently executing (Text file busy) -> the RUNPATH fix silently skips python3/python3.14 -> patch via a copy or re-run after the process exits, then confirm with readelf -d.

P: adb shell commands containing C compound literals or braces in f-strings break python syntax -> write the shell script to a file and adb push it instead of inlining.

DEAD: patching 200+ binaries in one adb-shell loop can end in a segfault (nonzero exit) but the work is still done -> judge by the result (readelf | grep com.termux count), not by exit code.
