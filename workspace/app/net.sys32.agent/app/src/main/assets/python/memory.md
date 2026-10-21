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
