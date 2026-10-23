# memory.md - lectii ale agentului de pe TELEFON (Android)

Acest fisier este memoria pe termen lung a agentului care ruleaza PE TELEFON.
Se incarca in system prompt la pornire si creste cu /learn sau auto-learn.
IMPORTANT: aici se scriu DOAR lectii relevante pentru dispozitivul Android pe
care ruleaza agentul (Samsung SM-A366B, Android 16). NU se scriu lectii despre
mediul de dezvoltare (desktop, Windows, emulator, build tools) - acelea nu au
legatura cu telefonul si induc in eroare.
Format: o lectie pe linie - `TRAP: ce a esuat -> eroare -> cauza -> fix`,
`OK: ce merge verificat`, `DEAD: ce nu merge -> dovada`, `P: cale -> la ce foloseste`.
Sectiuni: `## AAAA-LL-ZZ - subiect`.

## REGULA FUNDAMENTALA: OUT OF THE BOX (cerinta operatorului, 2026-10-23)
RULE: ORICE modificare pe care o facem si o urcam pe git TREBUIE sa functioneze automat dupa REBUILD APK + REINSTALARE, fara niciun pas manual. Nu e suficient sa mearga pe device-ul de acum: trebuie sa porneasca la fel de la o instalare curata.
CHECKLIST obligatoriu inainte de fiecare push:
  1. codul care ruleaza trebuie sa fie in `assets/` (python/, binder/, skills/, proot/, memory.md la radacina assets/) - NU doar in filesDir, pentru ca filesDir se re-extrage din assets la fiecare update de APK
  2. filesDir NU e sursa de adevar: ce pui doar acolo dispare la reinstalare
  3. fisierele noi sunt urmarite de git: `git check-ignore -v <fisier>` trebuie sa dea gol; regulile globale din .gitignore (memory.md, *.so, *.a, workspace/*.txt) prind usor fisiere care TREBUIE livrate -> negatie `!cale/exacta` la SFARSITUL .gitignore
  4. scripturile din assets NU au voie sa aiba cai hardcodate: isi detecteaza singure filesDir (AGENT_FILES_DIR / parinte cu pyhome sau python) si directorul de schimb (AGENT_BRIDGE_DIR), ca sa mearga si dupa reinstalare
  5. `assets/toolchain/` lipseste din repo - NORMAL (257MB, gitignore, se genereaza cu `workspace/app/build_toolchain.sh` la build); nu-l adauga in git
  6. dupa push: `git status --porcelain` gol + `git rev-parse HEAD` == `git rev-parse origin/master`
TEST final: simuleaza instalarea curata - ruleaza scriptul din `filesDir` dupa ce l-ai copiat din `assets/`, nu din workspace-ul de lucru.
## 2026-10-17 - desktop Linux: Assetto Corsa + Content Manager sub Proton
OK: masina are GE-Proton11-9 si prefixul jocului la ~/.local/share/Steam/steamapps/compatdata/244210/pfx; jocul in ~/.steam/steam/steamapps/common/assettocorsa
P: ~/Desktop/CM_latest/Content Manager.exe -> instalarea CM de pe desktop (v0.8.2594.39678)
P: ~/android_agent/temp/bin/ -> scripturi utilitare ale operatorului (start-cm.sh etc.)
TRAP: prefixul Wine/Proton are doar c: si z: -> operatorul nu vede folderele ascunse (.steam) in dialogul Windows de browse -> Wine ascunde implicit fisierele cu punct (HKCU\Software\Wine ShowDotFiles, absent = ascuns) -> se scrie calea direct in campul de sus al dialogului, sau se adauga un drive in pfx/dosdevices/<litera>: catre folder
TRAP: un drive nou in dosdevices nu apare in aplicatia deja pornita -> Wine citeste dosdevices doar la pornire -> repornire aplicatie
TRAP: AssettoCorsa.exe este Content Manager (11.3MB), launcher-ul Kunos e pastrat ca AssettoCorsa_original.exe (5.3MB) -> orice lansare a AssettoCorsa.exe deschide CM -> pentru meniul original se lanseaza AssettoCorsa_original.exe
TRAP: CM da "Couldn't run Steam" la Go -> log CM arata AppIdStarter.Run -> SteamRunningHelper.EnsureSteamIsRunning -> se schimba starter-ul din AppId in Direct (setarea e dropdown in Settings -> Content Manager -> Drive, nu o bifa)
TRAP: shell-ul acestui mediu nu executa heredoc `cat <<EOF` in mod fiabil (comanda iese fara output, fisierul nu se scrie) -> se scrie fisierul din python (open().write())
TRAP: comenzi xdotool/wmctrl pot bloca fara output -> fereastra se ridica din python cu ctypes pe libX11.so.6 (XMapRaised + XSetInputFocus)
OK: verificarea starii reale a unei ferestre = xwd -root -out x.xwd + ffmpeg -i x.xwd x.png + look pe png (nu se ghiceste ce e pe ecran)
OK: sesiunea grafica a operatorului e X11 (LXQt, DISPLAY=:0, pcmanfm-qt ca desktop) si e accesibila din tool-uri
## 2026-10-21 - BINDER: PROCEDURA OBLIGATORIE (instalare curata)
RULE (ordinea cailor) pentru orice cerinta despre binder:
  1. din APLICATIE: `import android_binder; Binder().list()/handle()/call()` (assets/python/android_binder.py)
  2. din DEBIAN: `android-binder selftest` (binarul din /opt/android-binder, sursa in files/binder/debian_binder.c)
  3. DOAR daca cele doua lipsesc: instaleaza cu `sh files/binder/install_binder.sh`
  4. NICIODATA sa scrii un client binder nou de la zero - asa au aparut 4 rapoarte false
TRAP: pe device, la prima pornire dupa instalare, assets/binder si assets/skills se extrag in files/ - daca lipsesc, aplicatia nu a pornit inca o data: deschide aplicatia
OK: acest device (SM-A366B, Android 16): aplicatia vede 466 servicii; ~113 au handle direct, restul de ~353 sunt LAZY (activity, window, notification, SurfaceFlinger, connectivity, stats, media.*) = nu sunt inregistrate in servicemanager pana nu le cere un client din framework. NU e SELinux, NU e binder stricat
OK: din Debian (u:r:shell:s0): `android-binder selftest` -> 469 listate, ~213 getService OK, 3 lazy, ~253 null. `iface package` -> android.content.pm.IPackageManager
OK: apeluri reale dovedite: display(code 1)=1736 B, input(code 1)=8 B, batteryproperties(code 1)=24 B, power(code 5)= eroare reala "Neither user N nor current process has android.permission.DEVICE_POWER"
TRAP: `0x80000001` in reply = NULL din parcel, NU handle. Handle-ul e u32 la offset 8 in flat_binder_object (=1 pentru majoritatea)
TRAP: `service check <nume>` din Android zice "found" pentru toate 469 - nu dovedeste acces
TRAP: client binder scris de la zero a esuat din 8 cauze: binder_size_t/uintptr 8B pe arm64 (nu 4), code la off 16 (nu 12), data_size la off 32 (nu 20), flags TF_ACCEPT_FDS=0x10 obligatoriu, EAGAIN nu e fatal, mmap MAP_SHARED, BC_ACQUIRE+BC_INCREFS inainte de primul apel, getService cod 1 (nu 2/4)
TRAP: proot se lanseaza cu -0 (root aparent) dar SELinux ramane shell:s0; setuid(2000) nu schimba contextul. bctl-android NU ruleaza din Debian (fara libc Android)
## 2026-10-23 - RAM pe Android: ce cifra conteaza (session: /storage/emulated/0/Download/Agent/workspace)
TRAP: am raportat `free -m` (MemFree=216MB) drept 'RAM aproape plina' -> concluzie falsa -> MemFree ~= cache reclaimable -> se citeste `MemAvailable` din /proc/meminfo (real: 3956 MB disponibili din 7380 MB, Cached 3561 MB) + /proc/swaps (zram0) + load average
OK: baterie completa = `android tool=battery action=full` (level/temp/voltage/health/current_now/charge_counter/battery_full_estimate); SEM_*/BATTERY_STATS cer root, nu sunt accesibile din app normal
OK: binder din app `binder list` -> 470 servicii (SM-A366B Android 16); din Debian `android-binder selftest` -> 215 getService OK, 3 lazy, 252 refuzate SELinux (shell vs untrusted_app)
OK: agent uid 10426 u0_a426, python 3.14.7 aarch64, files/toolchain 1.8G, files/python 59M, files/binder extras la pornire; Debian 13.7 root, python3 3.13.5, gcc 14.2.0, HTTPS din Debian OK
PREVENT: orice intrebare despre memorie/performanta -> citeste MemAvailable (+ swap + load) INAINTE de a declara presiune de memorie; NU recomanda inchiderea aplicatiilor pe baza MemFree
OK: capabilitatile pe acest device NULL pe toate contextele de care dispun (app u:r:untrusted_app uid10426 CapEff/CapBnd=0; shell u:r:shell:s0 uid2000 si proot root-emulat CapEff=0, CapBnd=0x8000c0) -> AF_PACKET, RAW ICMP/IP, ARP, SYN scan sunt refuzate identic peste tot
OK: Debian proot (uid 0 emulat, u:r:shell:s0) si shell adb (uid 2000) au acelasi CapEff=0 -> proot NU da capabilitati; capabilitatile se pierd la fork, nu se castiga cu uid 0
OK: matrice acces fisiere masurata: filesDir doar din app; /data/local/tmp doar din shell/adbsh si Debian; /storage/emulated/0 din toate; /system/bin listabil doar din adbsh; /proc/1/ns refuzat peste tot (fara nsenter in netns system_server)
OK: comenzile privilegiate difera per context: app are pm list + am start + input + logcat + getprop; dumpsys/settings/screencap cer shell (adbsh); app primeste 'Can't find service: battery' si SecurityException la settings
OK: tool-ul terminal action=run cu uid2000=true NU schimba UID-ul real -> porneste tot proot ca root emulat (uid 0, u:r:shell:s0), identic cu run normal
P: /data/data/net.sys32.agent/files/nmap/nmap -> nmap 7.95 compilat nativ (libpcre2/libpcap/libdnet, fara openssl/lua/ssh2); rulare doar via /apex/com.android.runtime/bin/linker64 + --datadir <dir> + --dns-servers <router>
TRAP: nmap cu -PR pe Android nu face ARP, cade automat pe CONNECT (log -d2: 'Changing ping technique ... to connect to port 80') -> nu confunda 'a gasit hosturile' cu 'a facut ARP'; -sS da explicit 'requires root privileges'
P: /storage/emulated/0/Download/Agent/workspace/probe.py -> baterie de 21 teste de capabilitati (uid/selinux/CapEff/sockete/drepturi fisiere) rulabila in orice context

## 2026-10-23 - adb_client: uid 2000 REAL din app (session: /storage/emulated/0/Download/Agent/workspace)
TRAP: tool-ul `adbsh` returneaza output GOL pentru ORICE comanda (id/echo/true/getprop), fara eroare si fara timeout -> NU e adbd mort (`getprop init.svc.adbd` = running) si NU e uid 2000 stricat -> e canalul tool-ului -> fix: `import sys; sys.path.insert(0,'/data/data/net.sys32.agent/files/python'); import adb_client; adb_client.shared().shell('id -u')` -> "2000"
OK: adb_client.shared().shell(cmd) din procesul app = uid 2000(u:r:shell:s0), grupuri 1004(input)/1011(adb)/1015(sdcard_rw)/3003(inet), AUTH automat cu files/adbkey -> `dumpsys`, `service list`, `getprop` toate merg
DEAD: adb_client din Python-ul Debian (3.13.5) -> RuntimeError "adbd did not accept the authorisation" -> Debian nu poate citi files/op_adbkey (sandbox) -> deci scriptul ruleaza in APP, nu in Debian
P: /storage/emulated/0/Download/Agent/workspace/android_run.py -> runner care ruleaza in app: `python3 android_run.py "<shell cmd>" <name>` scrie rezultatul in bridge/<name>.txt
P: /storage/emulated/0/Download/Agent/workspace/android_api.py -> sensors_list/sensor_events/battery/services/props, CLI sensors|battery|services|props|events
RULE (punte Debian->Android): 1. `adb_client` in APP (uid 2000) -> 2. scrie in /storage/emulated/0/.../bridge/*.txt (chmod 644, dir 777) -> 3. Debian citeste prin proot; NU incerca adb_client direct din Debian
OK: dumpsys sensorservice da 32 senzori + valori REALE (LSM6DSV Accelerometer -1.45484, 9.51506, -0.87936); unii senzori au [value masked] = privacy Samsung, nu lipsa acces
TRAP: procesul Debian (proot) NU vede /system si /data/app/.../lib/arm64/libpyexec.so -> 'No such file or directory' -> orice unealta Android (dumpsys/cmd/service) e invizibila direct din Debian, doar prin puntea de fisiere
## 2026-10-23 - libbinder nativ sub Android: ce NU merge (session: /storage/emulated/0/Download/Agent/workspace)
DEAD: libbinder.so real (/system/lib64) incarcat prin dlopen din uid 2000 -> `ProcessState::self()` SEGFAULT la primul apel -> nu e linker (toate deps se rezolva), nu e SELinux (fara avc denial, /dev/binder se deschide OK), nu e dublu libc++ (legat libc++.a static) -> ipoteza: libbinder 16 cere init din framework
TRAP: headere AOSP binder (IServiceManager.h/IBinder.h/Parcel.h) -> android.googlesource.com da HTTP 429 dupa ~20 fisiere, iar libs/utils a fost mutat -> 28 headere luate, lipsesc RefBase/String16/String8/Vector/Errors/StrongPointer/Threads -> ocolire: prototipuri manuale cu nume mutilate (dlsym) in loc de headere
OK: compile binar Android care leaga libc++ STATIC: `clang++ --target=aarch64-linux-android35 --sysroot=<tc>/sysroot <src> <tc>/sysroot/usr/lib/aarch64-linux-android/35/libc++.a .../libc++abi.a -L.../35 -latomic -lm -ldl -lc` -> altfel cere libc++_shared.so (inexistent in /system/lib64)
TRAP: libbinder.so are NEEDED libapexsupport.so + libvndksupport.so + libprocessgroup.so -> fara ele dlopen reuseste dar init crapa -> copiaza-le toate in acelasi dir cu libbinder
DEAD: /data/local/tmp/<binar> executat direct -> Permission denied (SELinux data_file_type) -> ruleaza via `/apex/com.android.runtime/bin/linker64 /data/local/tmp/x` cu LD_LIBRARY_PATH setat
DEAD: `linker64 --library-path ... <bin>` -> "error: expected absolute path: --library-path" -> se foloseste doar LD_LIBRARY_PATH env
## 2026-10-23 - DEBIAN are acces COMPLET la Android (nu doar shell)
OK: bridge-ul exista deja si merge din proot: `AndroidBridge.kt` (1142 linii, in procesul aplicatiei) + `android_bridge.py`, JSON pe linie peste TCP loopback, portul in `bridge.port` (vizibil din Debian ca /storage/emulated/0/Download/Agent/workspace/bridge.port).
OK: DIN DEBIAN (proot), masurat: battery level 60/voltage 4004/temp 31.7C; `sensors list` = 35 senzori; `sensors read accelerometer` = valori LIVE; `eval services` = 301; `eval call ctx.getSystemService(wifi)` -> `android.net.wifi.WifiManager` REAL.
P: /data/data/net.sys32.agent/files/python/android_full.py -> client Python pt bridge (port auto-detectat, reconnectare); in assets/python/ deci se extrage automat la rebuild.
TRAP: `dumpsys battery | head -12` TRUNCHIAZA output-ul (pipe inchis inainte de `level:`) -> apare doar "Max charging voltage: 0" -> NU pune `head` mic pe dumpsys; filtreaza cu grep pe camp sau ruleaza-l intreg (12015 B).
PREVENT: cand operatorul intreaba ce poate Debian, NU raspunde "doar dumpsys/senzori" - bridge-ul da reflexie arbitrara, camera, clipboard, UI, orice getSystemService. Verifica cu `python3 android_full.py available`.
DEAD: `app_process` din uid 2000 -> "Error changing dalvik-cache ownership: Operation not permitted" -> ART face chown, CapEff=0 -> cod Java propriu in shell e blocat structural (nu se rezolva cu ANDROID_DATA/mkdir).
## 2026-10-23 - agent.py: integrarea unui tool nou (session: /storage/emulated/0/Download/Agent/workspace)
TRAP: am adaugat tool `androidapi` in lista T + sandbox run_code + functie -> apelul modelului intoarcea GOL -> exista DOUA dispatchere: `_call_tool_inner(c)` (apelurile REALE, ~linia 2741, lant `if fn=="nume":`) si `sandbox={...}` din run_code_ptc (~3545); adauga in AMBELE -> verificare `grep -n 'if fn=="NUME"' agent.py`
TRAP: TOOLGUIDE e TUPLU de stringuri care se inchide cu `")` pe ULTIMA linie -> daca adaug o linie si las `,)` => `TypeError: can only concatenate tuple (not "str") to tuple` -> nu edita pe linii: `t.replace(ULTIMA_LINIE_EXACTA, ultima_fara_paranteza + "\\n" + linie_noua + ")")`
TRAP: editarea `lines[i]=...` pe agent.py (6300+ linii) a produs de 3 ori `SyntaxError: '(' was never closed` -> foloseste `str.replace(OLD_EXACT, NEW)` cu text copiat verbatim, nu indexi de linie
PREVENT: dupa orice modificare de agent.py -> `py_compile.compile(p,doraise=True)` DUPA FIECARE pas, apoi test real prin `m._call_tool_inner({"function":{"name":"X","arguments":json.dumps({...})}})`; NU `call_tool()` (lanseaza insight_tool/subprocese si poate atarna)
PREVENT: procesul agentului tine codul VECHI in memorie -> tool-ul da GOL dupa modificare desi `py_compile` trece; nu depana codul, cere RESTART si retesteaza
P: /data/data/net.sys32.agent/files/python/agent.py -> agentul care ruleaza; `workspace/app/net.sys32.agent/app/src/main/assets/python/agent.py` -> sursa din APK la rebuild (trebuie IDENTICE, verifica md5)
## 2026-10-23 - assets APK: ce se extrage automat la instalare (session: /storage/emulated/0/Download/Agent/workspace)
OK: MainActivity.extractAssets() face `copyDir("python"|"binder"|"proot"|"skills"|"toolchain")` + `assets.open("memory.md")`; stampila = versionCode+lastUpdateTime -> orice update de APK re-extrage automat; un script pus in `assets/python/` ajunge in `files/python/` fara interventie
TRAP: `assets.open("memory.md")` esua silentios (try/catch gol) pentru ca fisierul exista DOAR in `assets/python/memory.md` -> la instalare curata agentul pornea fara lectiile din APK -> se pune si `assets/memory.md` la radacina
TRAP: `.gitignore` are regula globala `memory.md` -> `assets/memory.md` NU se commitea -> fix: linie `!workspace/app/net.sys32.agent/app/src/main/assets/memory.md` LA SFARSITUL .gitignore (negarea nu merge inainte de regula care exclude)
TRAP: `assets/toolchain/` lipseste din repo (gitignore, 257MB) -> NORMAL, se genereaza cu `workspace/app/build_toolchain.sh`; nu-l cauta si nu-l adauga in git
## 2026-10-23 - git push din Debian (session: /storage/emulated/0/Download/Agent/workspace)
OK: `apt-get install -y git` in Debian merge (git 2.47.3), desi dpkg da erori la daemoni (dbus/pam-cap) - binarul se instaleaza; repo: `git@github.com:fetidness/android_agent.git`, remote-LOCAL in Debian `~/android_agent`
TRAP: `ssh -T git@github.com` -> `Host key verification failed` -> `ssh-keyscan -t ed25519,rsa github.com >> ~/.ssh/known_hosts` apoi merge: "Hi fetidness!"
TRAP: git commit esua cu identity lipsa -> `git config user.name/user.email` in repo inainte de primul commit
P: /storage/emulated/0/Download/ssh_github/id_ed25519 -> cheia SSH GitHub; se copiaza in Debian `~/.ssh/id_ed25519` chmod 600 + `.pub` chmod 644
RULE (verificare sincronizare repo<->device): 1. md5 pe fiecare fisier din `files/python/` vs `assets/python/` 2. `git status --porcelain` gol 3. `git rev-parse HEAD` == `git rev-parse origin/master`; `key.txt` trebuie sa LIPSEASCA din repo (e cheie API)

## 2026-10-23 - operator: asteptari de livrare (sesiune: /storage/emulated/0/Download/Agent/workspace)
OK: operatorul cere plan scris intr-un fisier inainte de executie si actualizarea lui pe parcurs ("sa nu ne pierdem pe drum"); raspunde in romana, accepta si cere verdict explicit dupa teste comparative ("care este mai capabil?")
OK: operatorul verifica afirmatiile si corecteaza (ex: "eu stiam ca si debian are acces complet la senzori", "ai zis ca ar lipsi o librarie binder?") -> o concluzie despre environment se da DOAR dupa un test care a esuat, cu comanda si eroarea exacta
OK: standard de livrare "out of the box": orice modificare urcata pe git trebuie sa functioneze dupa rebuild APK + reinstalare curata, fara pasi manuali (regula scrisa in capul memory.md)
## 2026-10-23 - Android: ce poate si ce nu poate uid 2000 (shell), masurat (sesiune: /workspace)
OK: uid 2000 are puteri de ADMINISTRARE mai mari decat aplicatia: `pm install/grant/uninstall/clear` (grant rc=0), `am force-stop`/`am broadcast` rc=0, `settings put global` rc=0 si citibil inapoi, `input tap/keyevent` rc=0, `screencap` scrie PNG 328KB in /data/local/tmp, `logcat`, `dumpsys activity`, `uiautomator dump`, `service call`, `appops get/set`, `cmd wifi status`; `pm list packages` = 415 aplicatii, `service list` = 470
DEAD: uid 2000 NU are acces de app: `/data/data/com.android.settings` si `/data/app` -> Permission denied; `run-as com.android.settings` refuzat; `su` inexistent pe device; CapEff=0 CapBnd=0x8000c0, SELinux Enforcing u:r:shell:s0
DEAD: cod Java/ART propriu din uid 2000 -> `app_process /system/bin` da "Error changing dalvik-cache ownership : Operation not permitted" (chiar si cu ANDROID_DATA=/data/local/tmp/ad si mkdir dalvik-cache/arm64) -> ART face chown la pornire, CapEff=0 -> cod Java in shell e blocat structural, NU e configuratie lipsa
OK: ierarhia reala pe acest device: aplicatia (reflection+SDK, sandbox untrusted_app) > uid 2000 (comenzi de sistem, fara API nativ) > root (inexistent, build user ro.secure=1)
TRAP: `dumpsys battery | head -12` trunchiaza output-ul -> pipe se inchide inainte de campurile utile -> apare doar "Max charging voltage: 0" fara level/voltage/temp -> ruleaza dumpsys FARA head (12015 B) sau filtreaza cu grep pe campul dorit
P: /storage/emulated/0/Download/Agent/workspace/PLAN_DEBIAN_ACCES_DEPLIN.md -> plan acces deplin Android din Debian (4 cai evaluate, blocajul app_process masurat)
