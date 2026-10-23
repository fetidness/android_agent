---
name: android-sensor-data-by-context
description: "Cine poate citi DATE reale de senzori pe acest device, per context (proot root vs uid2000 shell vs app) si cum verifici, cu comenzile exacte."
---
# Date de senzori per context de acces (SM-A366B / Android 16)

## When to Use
- Intrebarea "Debian are acces la senzori?" / "pot citi senzori din shell?".
- Trebuie sa decizi daca un context poate scoate VALORI de senzor, nu doar handle-uri binder.
- Nu confunda "serviciu vizibil in binder" cu "date de senzor accesibile" - sunt lucruri diferite.

## REGULA: intai contextul, apoi concluzia
Trei contexte, trei raspunsuri DIFERITE. Verifica contextul INAINTE de a declara ceva blocat:
```bash
id; cat /proc/self/attr/current; grep -E 'CapEff|CapBnd' /proc/self/status
```
- proot Debian "root"   -> uid 0 emulat, ctx u:r:shell:s0, CapEff 0000000000000000
- adbsh (uid 2000)      -> uid=2000(shell), ctx u:r:shell:s0, in grupul input (gid 1004)
- aplicatia             -> uid 10426 (u0_a426), untrusted_app

## Method

### 1. proot root (uid 0 emulat): NU scoate date
Serviciile exista si se deschid, dar apelurile intorc NULL:
```bash
android-binder check sensorservice               # found
android-binder handle sensorservice              # 1
android-binder iface sensorservice               # descriptor: android.gui.SensorServer
android-binder call sensorservice 1              # status=0xffffffff  (eroare)
android-binder call android.frameworks.sensorservice.ISensorManager/default 1   # 0x80000001
android-binder call android.hardware.sensors.ISensors/default 1                # 0x80000001
```
`0x80000001` = NULL in parcel, NU handle. Cauza: lipsesc libbinder/structurile AIDL Android,
deci clientul generic nu poate parsa raspunsul. Nu e o problema de SELinux (handle-ul se obtine).

### 2. uid 2000 (adbsh / terminal uid2000): DA, date reale prin dumpsys
```bash
dumpsys sensorservice | head -15                 # 32 senzori h/w, cu handle + sampling period
dumpsys sensorservice | grep -A3 'LSM6DSV Accelerometer: last'
#  -> -0.39601, 9.12922, 3.35653   (valori brute reale + ts + wall)
dumpsys sensorservice | grep -A2 'Auto Brightness Light'
```
`dumpsys` ESTE clientul care lipseste din proot: ruleaza ca shell si vorbeste cu sensorservice.
Nu ai nevoie de libbinder si nu trebuie sa scrii niciun client AIDL.

### 3. Aplicatia: stream nativ complet
```
android tool=sensors action=list
android tool=sensors action=read name="LSM6DSV Accelerometer" seconds=2
android tool=sensors action=stream names=["LSM6DSV Accelerometer"] seconds=5
```
Aceasta e singura cale cu STREAM si callbacks; dumpsys da doar snapshot periodic.

## Pitfalls
- TRAP: "serviciu are handle 1" NU inseamna acces la date -> apelul poate intoarce 0x80000001 (NULL). Verifica un `call` real, nu doar `handle`/`check`.
- TRAP: `android-binder` se pierde din PATH in unele shell-uri -> `timeout: exec android-binder: No such file or directory`; foloseste calea absoluta `/usr/local/bin/android-binder`.
- TRAP: in adbsh NU exista python3 (`/system/bin/sh: python3: inaccessible or not found`) -> testeaza deschiderea fisierelor cu shell: `( exec 3</dev/input/event0 && echo OPEN_OK && exec 3<&- )`.
- TRAP: `dd if=/dev/input/event0 count=1` pare FAIL dar de fapt BLOCHEAZA (rc=124 timeout) = deschidere REUSITA, nu exista eveniment (ecran stins) -> nu raporta "refuzat" pe baza unui timeout.
- TRAP: `/sys/class/input/event0/device/name` si `/proc/bus/input/devices` dau `Permission denied` din uid 2000, desi `/dev/input/event0` se deschide -> sysfs e mai strict decat devnode-ul.
- TRAP: `[value masked]` in dumpsys NU e lipsa de acces -> e privacy Samsung pentru senzori biometrici/gestuali (Grip, Touch Pocket, Wake Up Motion); accelerometrul/giroscopul/magneticul dau valori reale.
- TRAP: din proot nu exista `/system/bin/dumpsys` (ls: cannot access '/system/bin/am') -> dumpsys e disponibil DOAR din adbsh/uid2000.

## De ce `call <svc> 1` esueaza din proot: eroarea exacta
```bash
android-binder call display 1
# status=0xffffffff len=744
# 0000: ff ff ff ff 2b 00 00 00 42 00 69 00 6e 00 64 00
```
Decodat din UTF-16LE: "Binder invocation to an incorrect interface".
Nu e SELinux si nu e "libraria lipseste" - e PARCEL INCOMPLET: descriptorul AIDL nu e
scris in parcel. `android-binder iface package` merge (status=0x22, descriptor
android.content.pm.IPackageManager) pentru ca `_INTF` nu are argumente.

## Ce lipseste REAL din Debian (verificat)
```bash
ldconfig -p | grep -i binder          # NIMIC
find / -name 'libbinder*.so*' 2>/dev/null   # NIMIC (doar /usr/include/linux/android/binder.h)
```
`/opt/android-binder/debian_binder.c` (22KB) are doar `parcel_iface` + `transact_raw`;
NU are writeString16/readString16, writeStrongBinder, writeFileDescriptor, array/recursive reader.
=> orice metoda AIDL cu argumente esueaza; doar getService/iface/linkToDeath merg.

## Librariile Android EXISTA, dar nu in proot
```bash
# din adbsh (uid 2000), NU din proot:
ls -la /system/lib64/libbinder.so /system/lib64/libutils.so /system/lib64/libcutils.so \
       /system/lib64/libbase.so /system/lib64/libc++.so /system/lib64/liblog.so
# toate prezente; libbinder.so = 772432 B
/system/bin/linker64 --list /system/lib64/libbinder.so   # cere libc.so din
#   /apex/com.android.runtime/lib64/bionic/libc.so  => bionic, NU glibc
```
Consecinte dovedite:
- in proot `/system/lib64` nu exista (`ls: cannot access '/system/lib64'`) si nici
  `/apex/com.android.runtime/bin/linker64` -> libbinder NU poate fi linkat in procesul Debian.
- copiind librariile in `/data/local/tmp/androidlibs/` din adbsh, proot LE VEDE
  (verificat: `ls -la /data/local/tmp/androidlibs/` din terminal arata libbinder.so, libc++.so...).
- arhitectura corecta: proces SEPARAT compilat cu toolchain-ul Android (clang + bionic),
  care linkeaza libbinder real si e chemat din Debian prin subprocess; Debian ramane glibc.

## Fallback ieftin si deja dovedit: dumpsys/cmd din uid 2000
```bash
dumpsys sensorservice    # snapshot cu valori reale la senzorii ne-mascati
cmd sensor_privacy       # help: enable USER_ID SENSOR ...
settings get global sensor_privacy   # null pe acest device
```
De preferat fata de scrierea unui client parcel nou daca e nevoie doar de CITIRE.

## Punte Debian -> Android prin FISIERE cand adbsh e mort (dovedit)

TRAP MAJOR, masurat: adbsh poate muri complet si NU se repara din app.
Simptom exact: 8 comenzi diferite (`echo ALIVE_TEST`, `id`, `true`, `getprop`,
`id -u`, `echo revive`) -> TOATE intorc output COMPLET GOL, fara eroare,
fara timeout. Nu e o comanda care esueaza: canalul returneaza gol indiferent de comanda.
In acelasi timp tool-ul `android` (reflection nativa) merge normal
(`android tool=device action=get` -> date reale) => nu e device-ul mort, e canalul adbsh.

WORKAROUND care NU depinde de adbsh si nici de libbinder:

PAS 1 - in APP (python/bash), creeaza directorul punte si fa-l public:
```python
from pathlib import Path; import os
BR = Path("/storage/emulated/0/Download/Agent/workspace/bridge")
BR.mkdir(parents=True, exist_ok=True); os.chmod(BR, 0o777)
p = BR/"x.json"; p.write_text(json.dumps(obj, indent=1)); os.chmod(p, 0o644)
```

PAS 2 - datele Android le obtii cu tool-ul `android` (NU adbsh):
```
android tool=sensors action=read  params={"name":"accelerometer","seconds":3}
   -> {"ok":true,"data":{"sensor":"accelerometer","values":[-1.4626129,9.52822,-0.8195418],"unit":"m/s^2"}}
android tool=sensors action=list
android tool=device  action=get
```
ATENTIE la nume: `action=read name="LSM6DSV Accelerometer"` DA
`unknown sensor: LSM6DSV Accelerometer (try: accelerometer, gyroscope, magnetic, ...)`
=> foloseste numele GENERIC (accelerometer/gyroscope/light...), nu numele hardware.

PAS 3 - Debian citeste fisierul (proot vede /storage/emulated/0):
```bash
cd /storage/emulated/0/Download/Agent/workspace/bridge && python3 -c "
import json; d=json.load(open('sensor_accelerometer.json'))
print(d['sensor'], d['values'], d['unit'])"
```
Verificat end-to-end: x=-1.463 y=9.528 z=-0.820 m/s^2 citit si parsat din Debian.
Merge si pentru uptime/meminfo/system_props (`getprop | head -60` scris din app).

## Ce NU merita incercat (dovedit esuat, nu mai pierde pasi)
- libbinder real legat in binar propriu: dupa ce rezolvi tot lantul
  (`libc++.a` static pentru a evita DUBLU libc++ in proces, care da segfault),
  `ProcessState::self()` si `defaultServiceManager()` SEGFAULTEAZA in continuare
  (`ps=0x...` apoi `Segmentation fault`), cu `/dev/binder` care SE DESCHIDE OK
  din shell (`exec 3</dev/binder` -> BINDER_OPEN_OK) si CapEff=0.
  Deci nu e permisiune; e initializare de framework lipsa. Cost real: ~20 pasi.
- headere AOSP de la android.googlesource.com: dupa ~6 descarcari da
  `HTTP Error 429: Too Many Requests`, iar `libs/utils/include/utils` a fost mutat
  (`404`), deci lantul RefBase/String16/String8/Vector nu se poate asambla usor.
- `terminal action=run uid2000=true` NU da uid 2000: porneste TOT proot
  (`dumpsys: command not found`), identic cu run normal.
- redirect-urile in adbsh (`cmd > /data/local/tmp/x.txt`) pot lasa canalul mut;
  dupa ele adbsh a inceput sa returneze gol. Nu rula redirect-uri in adbsh.

## SOLUTIA FINALA dovedita: adb_client.py in APP (adbsh poate fi mort, asta merge)

Cand tool-ul `adbsh` returneaza gol, uid 2000 TOT functioneaza daca il chemi direct
prin modulul adb_client din procesul aplicatiei (uid app). Comenzi reale rulate:

```python
import sys
sys.path.insert(0, "/data/data/net.sys32.agent/files/python")
import adb_client
s = adb_client.shared()          # -> "[adb] ✓ AUTORIZAT: device::ro.product.model=SM-A366B"
s.shell("id -u")                 # -> '2000'
s.shell("id")
# -> uid=2000(shell) gid=2000(shell) groups=...,1004(input),1011(adb),1015(sdcard_rw),3003(inet)
#    context=u:r:shell:s0
s.shell("dumpsys sensorservice | grep -A4 'Accelerometer: last'")
# -> -1.45484, 9.51506, -0.87936   (valori reale)
s.shell("dumpsys battery | head -5")
```

Puntea completa Debian -> Android (ruleaza scriptul in APP, nu in proot):

```python
# /storage/emulated/0/Download/Agent/workspace/android_run.py  (executat cu python3 din APP)
import sys, os, subprocess
from pathlib import Path
BR = Path("/storage/emulated/0/Download/Agent/workspace/bridge")
BR.mkdir(parents=True, exist_ok=True); os.chmod(BR, 0o777)
def shell(cmd, timeout=30):
    code = ("import sys; sys.path.insert(0,'/data/data/net.sys32.agent/files/python');"
            "import adb_client; print(adb_client.shared().shell(%r))" % cmd)
    p = subprocess.run([sys.executable,"-c",code],capture_output=True,text=True,timeout=timeout)
    return "\n".join(l for l in p.stdout.splitlines() if not l.startswith("[adb]")).strip()
# shell("dumpsys sensorservice") -> scrie in bridge/sensors_raw.txt (0o644) -> Debian citeste
```
Verificat: `sensors_raw.txt` = 1593 linii, "Captured at: ...", 32 senzori,
plus baterie level 63 / voltage 4035 / temp 331 / Li-ion - toate citite din Debian.

## Pitfalls pentru adb_client
- TRAP: copierea `adb_client.py` in Debian si rularea cu python3 din proot NU merge:
  `RuntimeError: adbd did not accept the authorisation (signature + public key)`
  -> adbd cere cheia autorizata, iar proot nu poate citi `files/op_adbkey`
  (filesDir e mode 700, alt owner). Scriptul TREBUIE sa ruleze in app, nu in Debian.
- TRAP: `files/python/bin/python3` si `files/pyhome/bin/python3` NU exista
  (`False`); interpreterul aplicatiei este `.so` in APK lib dir
  (`sys.executable` = /data/app/~~.../lib/arm64/libpyexec.so) si calea APK
  NU e vizibila din proot (`ls: cannot access '/data/app/~~...'`).
- OK: `import adb_client` are nevoie doar de stdlib
  (socket/hashlib/struct/threading/subprocess/time/select/shutil) - nicio dependenta externa.
- OK: autentificarea foloseste TCP 5555: log-ul real este
  `[adb] port detectat: 5555` / `[adb] TCP conectat` / `[adb] AUTH -> trimit RSAPUBLICKEY`.
- TRAP: output-ul lui adb_client e poluat de linii `[adb] ...` -> filtreaza-le
  (`if not l.startswith("[adb]")`) inainte de a parsa.

## REGULA finala (ordinea cailor) pentru date Android din Debian
1. `adb_client.shared().shell(...)` dintr-un script care ruleaza IN APP -> scrie in bridge/ -> Debian citeste. (dovedit, 32 senzori + baterie)
2. tool-ul `android` (reflection nativa, in-app) -> scrie JSON in bridge/ -> Debian citeste. (dovedit, accelerometru)
3. tool-ul `adbsh` direct - doar daca raspunde; poate fi mort fara sa se repare.
4. NU libbinder legat in binar propriu (ProcessState segfault) si NU client parcel scris de la zero.
