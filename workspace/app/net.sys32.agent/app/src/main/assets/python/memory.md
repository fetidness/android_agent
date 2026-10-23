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
