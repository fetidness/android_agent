---
name: debian-android-access-limits
description: "Ce poate si ce NU poate Debian (uid 2000) sa faca pe Android, cu dovezile masurate: app_process blocat pe dalvik-cache chown, unde se opreste shell:s0, si ce cale deblocheaza restul"
---
# Debian uid 2000: granite reale de acces la Android

## When to Use
- Operatorul intreaba "Debian are acces deplin la Android?" / "poate face ce face aplicatia?"
- Vrei sa rulezi cod Java/Android propriu din shell (app_process, dalvikvm).
- Trebuie sa alegi intre: comenzi shell (pm/am/settings), binder direct, sau un helper in app.

## Method (masurat pe SM-A366B)

1. Identitate si capabilitati:
```bash
# din Debian:
id; grep -E 'CapEff|CapBnd' /proc/self/status
# -> uid=0(root) in proot, dar CapEff: 0000000000000000  CapBnd: 00000000008000c0
```
2. Accesul real se testeaza prin adb_client in app (vezi skill git-push / android_run.py):
   `import adb_client; adb_client.shared().shell("id")` -> uid=2000, u:r:shell:s0

3. CE MERGE (dovedit, rc=0):
   - `pm list packages | wc -l` -> 415
   - `pm grant net.sys32.agent android.permission.CAMERA` -> rc=0
   - `pm install <apk>` / `pm uninstall` / `pm clear` (executa; esueaza doar pe pachete de sistem)
   - `am force-stop <pkg>` -> rc=0, `am start`, `am broadcast`
   - `settings put global test_key 1` -> rc=0 (si `settings get` -> 1)
   - `input tap 500 500` -> rc=0, `input keyevent`
   - `screencap -p /data/local/tmp/t.png` -> PNG 328322 B
   - `dumpsys <orice>`, `logcat -d`, `service list` -> 470 servicii
   - `uiautomator dump /data/local/tmp/ui.xml` -> scrie fisierul

4. CE NU MERGE (dovedit):
   - `su` -> `/system/bin/sh: su: inaccessible or not found`
   - `ls /data/data/com.android.settings` -> Permission denied
   - `ls /data/app` -> Permission denied
   - `run-as com.android.settings` -> refuzat
   - `getenforce` -> Enforcing, `cat /proc/self/attr/current` -> u:r:shell:s0

5. Cod Java propriu din shell = BLOCAT:
```bash
ANDROID_DATA=/data/local/tmp/ad ANDROID_ROOT=/system app_process /system/bin --nice-name=t
# -> "Error changing dalvik-cache ownership : Operation not permitted"  -> Aborted
mkdir -p /data/local/tmp/ad/dalvik-cache/arm64   # rezolva "No such file or directory"
# dar reapare: "Error changing dalvik-cache ownership : Operation not permitted"
```
   Cauza: ART face chown pe dalvik-cache la pornire, iar chown cere CAP_CHOWN; CapEff=0.


## Calea care DEBLOCHEAZA tot restul: DShell bridge (verificat 2026-10-23)

Concluzia "Debian nu poate SDK-ul" e INCOMPLETA: bridge-ul aplicatiei da
reflexie arbitrara din proot. Verifica-l INAINTE de a declara o limita.

```bash
# in Debian:
dshell ping                                   # -> pong
dshell sh "id -u"                             # -> 2000
dshell battery '{"action":"full"}'            # -> {"level":59,...}
dshell eval '{"op":"call","target":"ctx","method":"getSystemService","args":["camera"]}'
# -> {"id":"o13","class":"android.hardware.camera2.CameraManager","str":"...@"}  obiect REAL
dshell sensors '{"action":"list"}'            # -> lista de 35 senzori
```

Alternative echivalente daca `dshell` lipseste:
```bash
# port citit din bridge.port (in Debian: /storage/emulated/0/Download/Agent/workspace/bridge.port)
python3 /tmp/bench/android_full.py available     # {"available": true, "port": 46431}
python3 /tmp/bench/android_full.py battery
```
Protocol brut (o linie JSON per cerere): `{"tool":"eval","action":"","params":{"expr":{...}}}`
trimis la `127.0.0.1:<port din bridge.port>`; raspuns = o linie JSON.

## Pitfalls
- `dumpsys battery | head -12` TRUNCHIAZA output-ul (pipe inchis inainte de `level:`) -> apare doar "Max charging voltage: 0" si pare ca bateria nu are nivel. Fara `head`: 12015 B, campul `level:` prezent. NU pune `head` mic pe `dumpsys`; filtreaza cu `grep` pe camp.
- Nu raspunde operatorului "Debian are doar dumpsys/senzori" fara sa fi rulat `dshell ping` intai: bridge-ul da camera, clipboard, UI, notificari si orice getSystemService.
- Din proot `dumpsys` NU e in PATH si `/system` nu exista -> orice unealta Android directa esueaza; singurele cai sunt `dshell` (TCP) sau adb_client rulat IN APP.

## Pitfalls (bariere dovedite)
- `app_process` esueaza cu "Error creating cache dir .../dalvik-cache/arm64 : No such file or directory" -> acela NU e blocajul real; dupa `mkdir -p` apare adevaratul "Error changing dalvik-cache ownership : Operation not permitted" (CapEff=0). Nu pierde timp pe calea asta.
- Nu confunda "are acces la senzori" cu "are acces deplin": uid 2000 are mai multa autoritate ADMINISTRATIVA decat aplicatia (pm grant/install/input/settings), dar mai putin acces la DATE (nu citeste filesDir, nu citeste /data/data/<alt pachet>).
- Barierele de mai sus NU sunt bug-uri de implementare: sunt granite de securitate Android. Orice plan care promite altceva trebuie sa treaca prin: helper in procesul aplicatiei (uid app are SDK+reflection) sau parcel binder complet.
- Pentru apeluri binder directe din Debian foloseste clientul existent, nu unul nou: vezi skill-urile binder-service-access-audit si binder-app-binding.

## Calea care DA acces deplin: bridge-ul aplicatiei (masurat 2026-10-23)

Aplicatia are deja `AndroidBridge.kt` (1142 linii) + `android_bridge.py`: JSON pe
linie peste TCP loopback, portul in `bridge.port`. NU scrie un bridge nou.

```bash
# 1. portul (din app se copiaza pe /sdcard ca Debian sa-l vada)
PORT=$(cat /storage/emulated/0/Download/Agent/workspace/bridge.port)   # ex. 46431

# 2. din DEBIAN, conexiune directa (merge din proot):
python3 -c "
import socket,json
port=int(open('/storage/emulated/0/Download/Agent/workspace/bridge.port').read().strip())
s=socket.create_connection(('127.0.0.1',port),timeout=30)
s.sendall((json.dumps({'tool':'battery','action':'','params':{}})+chr(10)).encode())
buf=b''
while not buf.endswith(b'\n'):
    c=s.recv(65536)
    if not c: break
    buf+=c
print(json.loads(buf.decode()))"
```

Rezultate dovedite din proot (nu din app):
- `{"tool":"battery"}` -> ok=True, level=60, voltage=4004, temperature_c=31.7
- `{"tool":"sensors","action":"list"}` -> ok=True, 35 senzori
- `{"tool":"sensors","action":"read","params":{"name":"accelerometer","seconds":2}}`
  -> valori LIVE: [-2.6829, 9.2650, -0.4707]
- `{"tool":"eval","expr":{"op":"services"}}` -> 301 servicii
- `{"tool":"eval","expr":{"op":"call","target":"ctx","method":"getSystemService","args":["wifi"]}}`
  -> `android.net.wifi.WifiManager` (reflexie arbitrara din Debian)

Client gata facut: `android_full.py` (in `files/python/`, livrat prin assets).
```bash
python3 /data/data/net.sys32.agent/files/python/android_full.py available
python3 /data/data/net.sys32.agent/files/python/android_full.py battery
python3 /data/data/net.sys32.agent/files/python/android_full.py eval '{"op":"services"}'
```
In cod: `import android_full as A; A.ok('sensors','read',name='accelerometer',seconds=2)`

Comenzi expuse de bridge (`AndroidBridge.kt` dispatcher): sensors, camera, location,
battery, clipboard, notify, vibrate, tts, volume, wifi, device, apps, intent, settings,
tourl, system, storage, processes, network, display, audio, telephony, nfc, usb,
appinfo, install, eval, services, info, ui, notif, ime, vpn, capture, guard.

### Pitfalls specifice bridge-ului
- `eval` cu `{"op":"call","target":"class:android.os.Build","method":"getModel"}` ->
  `error: "method not found: android.os.Build.getModel/0"` -> metodele statice cer alta
  sintaxa; ruleaza intai `{"op":"info","target":"android.os.Build"}` ca sa vezi lista reala.
- `{"op":"get","target":"ctx","field":"packageName"}` -> `error: "field not found: packageName"`
  -> expune metode, nu field-uri arbitrare; foloseste `op=call` cu metoda getter.
- Daca aplicatia a fost repornita, portul din `bridge.port` se schimba -> clientul
  trebuie sa reciteasca fisierul si sa reincerce O data (android_full.py face asta).
- `bridge.port` sta in filesDir (nevizibil din proot) -> copiaza-l in
  `/storage/emulated/0/Download/Agent/workspace/bridge.port` ca sa fie citibil din Debian.
- `dumpsys battery | head -12` TRUNCHIAZA output-ul: pipe-ul se inchide inainte sa apara
  `level:` si ramane doar "Max charging voltage: 0" (masurat: 402 B in loc de 12015 B).
  -> NU pune `head` mic pe dumpsys; ruleaza-l intreg sau filtreaza cu grep pe campul dorit.
- `dumpsys sensorservice | grep -E '^0x[0-9a-f]+\)'` merge; dar in adbsh grep-ul poate
  intoarce GOL pe alternanta cu backslash-pipe -> foloseste `grep -E` cu pipe simplu.
- Cine stie de bridge conteaza: `agent.py` trebuie sa aiba in TOOLGUIDE blocul
  "DEBIAN ARE ACCES COMPLET" si in descrierea tool-ului `terminal` nota "NU e orb la
  Android", altfel modelul raspunde ca Debian are doar dumpsys. Verificare:
  `python3 -c "import sys;sys.path.insert(0,'/data/data/net.sys32.agent/files/python');import agent;print('DEBIAN ARE ACCES COMPLET' in agent.TOOLGUIDE)"`

## UNIFICARE 2026-10-23: DShell e canalul CANONIC, nu AndroidBridge (masurat)

Exista DOUA servere in procesul aplicatiei si e usor sa construiesti peste cel gresit:

```bash
# ambele porturi, citite din fisiere diferite
cat /storage/emulated/0/Download/Agent/workspace/dshell.port    # -> 46500
cat /storage/emulated/0/Download/Agent/workspace/bridge.port    # -> 46431
```

- **DShell** (46500, `dshell.port`, client `/usr/local/bin/dshell`):
  protocol `{"cmd":"ping","arg":""}` -> `{"ok":true,"out":"pong"}`
- **AndroidBridge** (46431, `bridge.port`):
  protocol `{"tool":"battery","action":"","params":{}}` -> `{"ok":true,"data":{...}}`

DShell e **SUPERSET**: orice `cmd` ajunge la tool-urile native, PLUS doua comenzi
care nu exista in AndroidBridge:
```bash
dshell sh "id -u"            # -> 2000   (ruleaza ca uid 2000: pm/dumpsys/settings/input)
dshell debian "uname -r"     # -> 6.1.0-debian  (ruleaza in rootfs-ul proot)
```
plus self-heal: clientul din rootfs se rescrie la fiecare pornire a aplicatiei.

**Regula:** scrie peste DShell. Nu construi un client nou peste AndroidBridge -
ajungi cu doua punti paralele si confuzie.

### Pitfall de protocol (a costat 3 iteratii)
- `cmd`-urile `sh`, `debian`, `eval` vor `arg` ca **STRING BRUT**, nu JSON
  imbricat: `{"cmd":"sh","arg":"id -u"}`. Daca trimiti `{"cmd":"sh","arg":"{\"args\":\"id -u\"}"}`
  primesti `/system/bin/sh: {args:: inaccessible or not found`.
- Comenzile cu parametri (sensors/battery/ui) vor `arg` = JSON:
  `{"cmd":"sensors","arg":"{\"action\":\"list\"}"}`.
- `out` vine ca **string** si cand e JSON -> parseaza-l o data
  (`json.loads(out)`) inainte sa-l folosesti ca structura.
- `dshell.port` poate lipsi din `/data/local/tmp` (se scrie in workspace);
  verifica ambele: `/storage/emulated/0/Download/Agent/workspace/dshell.port`
  si `/data/local/tmp/dshell.port`.

Verificat dupa unificare (din proot):
`dshell ping`->pong, `sh`->2000, `debian`->6.1.0-debian, `sensors`->35,
`eval getSystemService("camera")`->`android.hardware.camera2.CameraManager`,
`ui read`->`[1] TextView "⚡ AGENT DeepSeek" @[260,187]`.
