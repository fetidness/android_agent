---
name: agent-bridge-port-and-protocol
description: "Diagnose why the Android agent's Python clients (android_full.py, dshell.py, android_bridge.py) cannot reach the Kotlin AndroidBridge: wrong bridge.port file, wrong JSON protocol, or a missing native action forcing reflection. Use when the agent improvises with `eval`/reflection and fails with 'field not found', 'unknown tool' or 'cannot resolve target'."
---
# Bridge Python <-> AndroidBridge.kt: portul, protocolul, actiunile lipsa

## Cand se foloseste
- Agentul incearca sa aprinda lanterna / sa citeasca un senzor si ocoleste prin `eval` cu reflexie.
- Erori tipice: `unknown tool:`, `field not found: cameraIdList`,
  `method ...get argument 1 has type CameraCharacteristics$Key, got java.lang.String`,
  `cannot resolve target: svc:media.camera`.

## Cauza radacina (masurat 2026-10-24)
Exista TREI clienti Python cu TREI conventii diferite, dar UN SINGUR server:
`AndroidBridge.kt` este singurul care scrie `files/bridge.port` si accepta doar
`{"tool":..,"action":..,"params":{..}}`.

| fisier | cauta portul in | protocol |
|---|---|---|
| android_bridge.py | bridge.port (corect) | {tool,action,params} |
| android_full.py | dshell.port INAINTE de bridge.port (greșit) | {cmd,arg} (greșit) |
| dshell.py | doar /sdcard + /data/local/tmp, default 46500 | {cmd,arg} |

`dshell.port` ramane pe disc cu valoarea dintr-o rulare VECHE (ex. 46500) in timp ce
`bridge.port` are portul real (ex. 34793). Cine citeste intai dshell.port vorbeste pe un port mort.

## Reparatii aplicate in sursa
1. `AndroidBridge.kt` — acțiune noua `camera`/`action=torch` cu `params.on`, plus `torch_list`.
   CameraManager NU are getter de torch, deci starea se tine intr-un `object TorchState`.
2. `android_full.py` — `_port_candidates()` pune `files/bridge.port` PRIMUL; `_request()` trimite
   protocolul corect; `tool()`, `torch()`, `flash(n)`; `_probe()` foloseste `camera list`
   (`ping` nu exista ca tool); `BrokenPipeError` prins in `__main__`.
3. `dshell.py` — aceleasi cai, `DEFAULT_PORT = None` (fara ghicit), retry explicit.

## Verificare (pe device, nu pe loguri)
```
adb shell run-as net.sys32.agent cat files/bridge.port      # portul REAL
adb shell run-as net.sys32.agent cat files/tmp/dshell.port  # poate fi VECHI - nu te baza pe el
T='run-as net.sys32.agent sh files/tmp/python3.sh files/python/android_full.py'
adb shell "$T available"                 # {"available":true,"port":...}
adb shell "$T camera '{\"action\":\"torch_list\"}'"
adb shell "$T flash 3"
adb shell dumpsys media.camera | grep -i 'Torch for camera' | head -6   # DOVADA fizica
```

## Capcane
- `python3.sh` din `files/tmp` e scris de `toolchain.py` si contine calea
  `nativeLibraryDir`. Dupa FIECARE reinstalare calea `codePath` se schimba
  (`/data/app/~~XXXX==/net.sys32.agent-YYYY==`), deci wrapper-ul vechi da
  `libpyexec.so: inaccessible or not found`. Se repara ruland toolchain-ul sau rescriind
  wrapper-ul cu `pm path net.sys32.agent`.
- NU taia calea cu `cut -d= -f2`: `~~XXXX==` contine `=`. Foloseste
  `pm path net.sys32.agent | sed 's|package:||;s|/base.apk||'`.
- `dumpsys media.camera` fara pipe in `adb shell` da "inaccessible or not found";
  ruleaza-l cu stdin din python sau fara pipe.
