---
name: binder-service-access-audit
description: "Binder pe acest device: ce comanda folosesti, cu ce context, ce e lazy vs blocat SELinux, si cum verifici corect. INCARCA-L inainte de orice test binder."
---
# Binder: cum se verifica CORECT (SM-A366B / Android 16)

## REGULA ZERO (cea care a costat 4 rapoarte false)
Inainte sa scrii UN SINGUR rand de client binder nou, verifica daca exista deja:
```bash
android-binder selftest          # in Debian (proot)
binder action=list               # in aplicatie (tool-ul binder)
```
Daca exista, FOLOSESTE-L. Codul care merge e deja in `assets/binder/debian_binder.c`
si in `assets/python/android_binder.py`. Un client scris de la zero in paralel a produs
"0 din 25 servicii" din cauza offseturilor gresite (code la 12 in loc de 16,
data_size la 20 in loc de 32, lipsa TF_ACCEPT_FDS, lipsa BC_ACQUIRE/BC_INCREFS,
getService cod 2 in loc de 1, uintptr tratat pe 4 bytes).

## Din APLICATIE (uid u0_aXXX, untrusted_app) - calea buna
```python
import android_binder                  # files/python/android_binder.py
b = android_binder.Binder()
len(b.list())                          # ~466 servicii
b.handle("package")                    # 1
b.interface_descriptor("display")      # android.hardware.display.IDisplayManager
st, data = b.call("display", 1)        # status=0, 1736 bytes, date reale
```
Dovedit functional: display(code 1)=1736 B, input(code 1)=8 B,
batteryproperties(code 1)=24 B, power(code 5)= eroare de permisiune reala
"Neither user N nor current process has android.permission.DEVICE_POWER".

## Din DEBIAN (proot, ctx u:r:shell:s0)
```bash
android-binder selftest     # 469 listate / ~213 getService OK / 3 lazy / ~253 null
android-binder iface package  -> android.content.pm.IPackageManager
android-binder iface power    -> android.os.IPowerManager
```

## Ce NU e eroare
- `null` la getService pentru ~350 servicii = **LAZY** (activity, window, notification,
  SurfaceFlinger, connectivity, stats, media.*). Nu sunt inregistrate in servicemanager
  pana nu le cere un client din framework. NU e SELinux, NU e binder stricat.
- `service check <nume>` din Android raspunde `found` pentru TOATE (469) - nu dovedeste acces.
- `0x80000001` in reply = NULL din parcel, nu un handle. Handle-ul real e u32 la offset 8
  in flat_binder_object si e 1 pentru majoritatea serviciilor de sistem.

## Capcane dovedite
TRAP: proot se lanseaza cu `-0` (root aparent) dar SELinux rămâne shell:s0; setuid(2000) nu schimba contextul
TRAP: `bctl-android` (binar Android) NU ruleaza din Debian (fara libc Android) - compileaza nativ cu gcc
TRAP: INTERFACE_TRANSACTION nu raspunde pe serviciile lazy -> foloseste un serviciu de baza (package/power/display)
TRAP: in aplicatie, un eval/reflexie costa ~60s; nu incerca sweep de 469 intr-un script (PTC 1800s)

## Verificare rapida "status dispozitiv + agent + Debian" (dovedita 2026-10-23)
- Aplicatie: `android tool=battery action=full` -> JSON cu level/current_now_uA/health_name;
  `binder action=list` -> 470 servicii pe acest device (ActivityManager, SurfaceFlinger, vendor.*).
- Shell/app: `date; uptime; free -m; id; getprop ro.product.model; getprop ro.build.version.release`;
  `df -h /data /storage/emulated` -> load 2.4 constant + RAM ~216 MB liberi e normal (system_server
  383 MB, SystemUI 287 MB, com.google.android.gms 246 MB), NU e defect de kernel.
- Debian: `terminal action=run` cu `cat /etc/debian_version; python3 -V; gcc --version | head -1`
  -> 13.7 / 3.13.5 / gcc 14.2.0; `android-binder selftest` -> 215 getService OK din shell:s0;
  retea: `python3 -c "import urllib.request;print(urllib.request.urlopen('https://pypi.org',timeout=6).status)"` -> 200.
- Assets agent: `ls /data/data/net.sys32.agent/files/binder` (bctl-android, binder.py, bindall.c) -
  cale ABSOLUTA; `ls files/binder` din cwd-ul workspace returneaza gol (cwd-ul e /storage/emulated/0/Download/Agent/workspace).
- TRAP: in `run_code`, tool-ul android NU se cheama `android(...)` positional -> returneaza
  "AttributeError: 'str' object has no attribute 'get'"; foloseste direct `android tool=...` ca tool.
- TRAP: in `run_code`, `bg(...)` nu e definit (NameError) - ruleaza-l ca tool separat.

## Cazul SENZORI din Debian: handle OK dar datele NU (dovedit 2026-10-23)
Intrebarea "Debian are acces la senzori?" are 3 niveluri - verifica-le pe rand, nu sari la concluzie:
1. Suprafata: `/dev/input/event0..6` EXISTA, `/dev/binder|hwbinder|vndbinder` se deschid cu `os.open(p, os.O_RDWR)` -> fd valid.
2. Serviciu: `android-binder check sensorservice` -> `found`; `android-binder handle <svc>` -> `1` pe toate trei:
   `sensorservice`, `android.hardware.sensors.ISensors/default`, `android.frameworks.sensorservice.ISensorManager/default`.
   Handle=1 NU e acces la date.
3. Datele: `android-binder call <svc> 1` (getSensorList) ->
   `status=0x80000001 len=4` = NULL din parcel, sau `status=0xffffffff` = eroare. NICIODATA date.
   `android-binder iface sensorservice` -> descriptor `android.gui.SensorServer` (NU ISensorManager).
TRAP: /dev/input este REFUZAT din Debian: `PermissionError 13` la os.open -> SELinux shell:s0, NU lipsa de uid.
TRAP: sysfs IIO e vizibil dar necitibil: `/sys/bus/iio/devices/iio:device0/name` -> `Permission denied`;
  `in_accel_x_raw` / `in_anglvel_x_raw` -> refuzat. device0/device1 sunt doar termici (pm6450/pmk8350 die_temp).
TRAP: `cat /sys/class/sensors/*/name` -> `No such file or directory` (calea nu exista pe acest device).
TRAP: in Debian NU exista `libandroid.so`, `libbinder.so`, nici modul Python `android` (ModuleNotFoundError) ->
  clientul generic android-binder NU poate parsa structurile AIDL de senzori; de aceea apelurile intorc NULL
  chiar daca binder-ul raspunde. Fix real = compilare client AIDL + rezolvare SELinux, nu "binder stricat".
COMPARATIE cu aplicatia: `android tool=sensors action=list` -> lista reala (LSM6DSV accel/gyro, MXGX300 mag,
  stk_stk31610 light, QTI gravity/rotation_vector, Samsung step_counter/hall/grip...) + date prin action=read/stream.
CONCLUZIE de formulat corect: "Debian atinge serviciile de senzori dar nu poate scoate date" - NU "Debian nu are acces deloc".

## De CE eșuează apelurile AIDL din Debian: parcel incomplet, NU libbinder lipsă
Nu există `libbinder.so`/`libutils.so`/`libcutils.so` în proot (`ldconfig -p | grep -i binder` = gol,
`find / -name 'libbinder*.so*'` = gol). Dar asta NU e cauza reală a eșecului.
Clientul `debian_binder.c` are DOAR: `parcel_iface` (string16 descriptor) + `transact_raw` + `get_service_handle`.
NU are `writeString16`/`readString16`/`writeStrongBinder`/`writeFileDescriptor`/array-uri/nested
(`grep -nE 'writeString16|readString16|writeStrongBinder|writeFileDescriptor' /opt/android-binder/debian_binder.c` = 0 rezultate).

Deci: apelurile FĂRĂ argumente merg, cele CU argumente nu:
```bash
android-binder iface package      # OK -> descriptor: android.content.pm.IPackageManager
android-binder call display 1     # status=0xffffffff len=744
#   hex 0000: ff ff ff ff 2b 00 00 00 42 00 69 00 6e 00
#   decodat UTF-16: "Binder invocation to an incorrect interface"
```
Același mesaj ca bug-ul de memset din `binder-app-binding`. Nu e SELinux, nu e handle greșit -
serverul primește tranzacția dar parcelul nu conține descriptorul/metoda așteptată.

FIX (dacă chiar ai nevoie de AIDL complet din Debian): adaugă accesoriile de parcel lipsă în
`debian_binder.c`, SAU nu scrie client - folosește uneltele Android deja compilate din uid 2000
(`dumpsys`, `cmd`, `service call`), care sunt clienți compleți și întorc date reale.

Consecință practică: lipsa libbinder NU blochează senzorii - vezi skill `android-sensor-data-by-context`
(uid 2000 citește accelerometru real prin `dumpsys sensorservice`).

## Compilarea unui helper C++ legat la libbinder.so REAL (dovedit 2026-10-23: se incarca, dar crash la apel)
Scop: inlocuieste clientul generic cu un binar care foloseste libbinder adevarat (parcel complet).
Pasi care MERG, cu erorile exacte intalnite:

1. Copiaza librariile Android din uid 2000 (proot NU vede /system):
```bash
# adbsh:
mkdir -p /data/local/tmp/abridge
cp /system/lib64/libbinder.so /system/lib64/libutils.so /system/lib64/libcutils.so \
   /system/lib64/libbase.so /system/lib64/liblog.so /system/lib64/libapexsupport.so \
   /system/lib64/libvndksupport.so /system/lib64/libprocessgroup.so /data/local/tmp/androidlibs/
# libc++_shared.so NU exista in /system/lib64 (doar libc++.so) ->
# copiaza-l din toolchain prin /sdcard: <TC>/sysroot/usr/lib/aarch64-linux-android/35/libc++_shared.so
```
proot VEDE /data/local/tmp/androidlibs (verificat cu `ls`).

2. NU descarca headere AOSP: `android.googlesource.com/...?format=TEXT` da
   `HTTP Error 429 Too Many Requests`, iar `frameworks/native/libs/utils` a fost mutat/dizolvat.
   Ocolire: prototipuri manuale cu nume mutilate + `dlopen`/`dlsym`.
   Simboluri reale (confirmate cu `readelf --dyn-syms -W libbinder.so`):
   `_ZN7android21defaultServiceManagerEv` (FUNC, 168 B),
   `_ZN7android12ProcessState4selfEv`,
   `_ZN7android2os16BpServiceManager12listServicesEiPNSt3__16vector...`

3. Compileaza cu clang din toolchain, legand libc++ STATIC (altfel ai DOUA libc++ in proces):
```bash
SYS=<TC>/sysroot/usr/lib/aarch64-linux-android/35
<TC>/bin/clang++ --target=aarch64-linux-android35 --sysroot=<TC>/sysroot \
  -resource-dir=<TC>/lib/clang/21 -O2 -fPIC -I<TC>/sysroot/usr/include/c++/v1 \
  h.cpp $SYS/libc++.a $SYS/libc++abi.a -o helper_bin \
  -L$SYS -L<TC>/lib/clang/21/lib/linux -Wl,-rpath,/system/lib64 -latomic -lm -ldl -lc
```

4. Ruleaza (proot NU vede /apex -> rulezi din adbsh):
```bash
export LD_LIBRARY_PATH=/data/local/tmp/androidlibs:/system/lib64:/apex/com.android.runtime/lib64/bionic
/apex/com.android.runtime/bin/linker64 /data/local/tmp/helper_bin
```
`linker64 --library-path X` NU merge ("error: expected absolute path"), foloseste LD_LIBRARY_PATH.

TRAP: linkand libc++.so din copy -> `ProcessState::self()` SEGFAULT (doua libc++ in proces).
  Fix: libc++.a + libc++abi.a STATIC.
TRAP: chiar si cu libc++ izolat, `ProcessState::self()` si `defaultServiceManager()` tot SEGFAULTEAZA
  la primul apel (fara AVC denial in logcat, `/dev/binder` se deschide OK cu `exec 9</dev/binder` -> BINDER_OPEN_OK;
  `logcat -d -b crash` gol, `/data/tombstones/` necitibil din shell). Cauza neconfirmata -
  ipoteza: libbinder 16 cere initializare de framework. NU declara "binder nu merge din Debian" pe baza asta.

## Puntea Debian -> uid 2000: /system NU e montat in proot
- `dumpsys`/`cmd`/`service` -> `command -v dumpsys` = gol; `/system` -> `No such file or directory`.
- `terminal action=run uid2000=true` NU schimba UID real: porneste tot proot ca root emulat ->
  `dumpsys: command not found` (verificat: fisierele scrise contineau exact aceasta eroare).
- adbsh (singura cale cu dumpsys real) a devenit INSTABIL dupa redirect-uri in fisiere:
  `dumpsys battery > /data/local/tmp/abridge/battery.txt` apoi `echo TEST_OK` -> output GOL.
  Workaround: tool-ul `android` (cale nativa, non-adbsh) merge independent.
- Consecinta: orice punte fiabila Debian<-Android trebuie facuta prin fisiere in /data/local/tmp
  scrise de adbsh si citite de proot, si depinde de stabilitatea adbsh.

## APELURI AIDL REALE din bindere propriu: de ce esueaza (dovedit 2026-10-23)
```
android-binder call display 1
  -> status=0xffffffff len=744
  -> decodat UTF-16: "Binder invocation to an incorrect interface"
android-binder iface package  -> status=0x22 len=76  -> android.content.pm.IPackageManager  (MERGE)
```
Cauza: clientul `debian_binder.c` are parcel DOAR pentru `getService`/`_INTF`.
Nu are `writeString16`/`readString16`/`writeStrongBinder`/`writeFileDescriptor`
(nu exista in sursa: `grep -nE 'writeString16|writeStrongBinder|writeFileDescriptor'` = 0 rezultate).
Deci ORICE metoda AIDL cu argumente esueaza; doar `iface` (fara argumente) merge.
Fix real: accesori de parcel in `debian_binder.c`, NU un client nou de la zero.

## libbinder.so REAL linkat din toolchain-ul APK (incercat, NU functioneaza)
```bash
# 1. librariile exista pe device (vizibile DOAR din adbsh, nu din proot)
ls /system/lib64/libbinder.so        # 772432 B
ls /system/lib64/libutils.so /system/lib64/libcutils.so /system/lib64/libbase.so /system/lib64/libc++.so
# 2. copiere pentru runtime
cp /system/lib64/libbinder.so /data/local/tmp/androidlibs/     # + libutils,libcutils,libbase,libc++.so,liblog
cp /system/lib64/libapexsupport.so /system/lib64/libvndksupport.so /system/lib64/libprocessgroup.so /data/local/tmp/androidlibs/
# 3. rulare
export LD_LIBRARY_PATH=/data/local/tmp/androidlibs:/system/lib64:/apex/com.android.runtime/lib64/bionic
/apex/com.android.runtime/bin/linker64 /data/local/tmp/helper_probe
```
Ce a mers: `dlopen("libbinder.so")` OK, `dlsym("_ZN7android21defaultServiceManagerEv")` gasit.
Ce NU merge: **`ProcessState::self()` si `defaultServiceManager()` SEGFAULTEAZA**
chiar si cu libc++ legat STATIC (`libc++.a` + `libc++abi.a` din
`sysroot/usr/lib/aarch64-linux-android/35/`), deci nu e dublu libc++.
Nu exista AVC denial, `/dev/binder` se deschide din shell (`exec 9</dev/binder` -> BINDER_OPEN_OK).
NU se rezolva: headerele AOSP lipsesc (android.googlesource.com da **HTTP 429**,
`libs/utils` a fost mutat) - dar prototipurile manuale compilesc, deci headerele NU erau blocajul.
CONCLUZIE: pentru date de sistem foloseste uneltele Android (`dumpsys`/`cmd`), nu libbinder.

TRAP: `libc++_shared.so` NU exista in /system/lib64 (doar libc++.so). Binarul legat din
toolchain cere `libc++_shared.so` -> "CANNOT LINK EXECUTABLE ... library libc++_shared.so not found"
-> copiaza `sysroot/usr/lib/aarch64-linux-android/35/libc++_shared.so` in acelasi dir cu LD_LIBRARY_PATH.
TRAP: linker64 NU accepta `--library-path` drept prim argument: da
`error: expected absolute path: "--library-path"` -> foloseste variabila `LD_LIBRARY_PATH`.
TRAP: `/system/lib64` NU e montat in proot (`ls /system/lib64` -> No such file or directory),
deci compilarea care linkeaza `libc++.so` din /system pica din procesul app
(`ld.lld: error: unable to find library -lc++.so`). Copiaza libraria prin /sdcard.
