---
name: agent-bridge-port-and-protocol
description: "Two independent servers expose Android to Python on this device: DShell (inside agent.py, port 46500-46519, file dshell.port, protocol {cmd,arg}, supports sh/debian/eval + any native tool) and AndroidBridge.kt (Kotlin, file bridge.port, protocol {tool,action,params}). Use when a client gets 'unknown tool', picks the wrong port, or you are about to 'fix' dshell.py."
---
# DShell vs AndroidBridge: doua servere diferite, nu unul

## Regula de aur (masurata 2026-10-24, dupa ce am stricat-o)
**`dshell.py` si `android_full.py` sunt COREcte in git. Nu le "repara".**
Ordinea din `PORTFILE_CANDIDATES` (dshell.port PRIMUL) este intentionata.

## Cele doua servere

| | DShell | AndroidBridge.kt |
|---|---|---|
| unde | IN `agent.py` (`_dshell_serve`) | procesul aplicatiei, Kotlin |
| fisier port | `dshell.port` (46500..46519) | `bridge.port` |
| protocol | `{"cmd","arg"}` | `{"tool","action","params"}` |
| `ping` | `pong` | unknown tool |
| `sh` | uid 2000 | **nu exista** |
| `debian` | proot rootfs | **nu exista** |
| `eval` | reflexie | doar ca tool `eval` |
| native tools | le ruteaza la android_bridge | nativ |

DShell e SUPERSETUL: `_dshell_handle` ruteaza orice nume necunoscut catre
`android_bridge`, deci `{"cmd":"battery","arg":'{"action":"full"}'}` merge.


## Procedura de diagnostic (in ordinea asta - altfel tragi concluzii false)
1. **Intreaba SERVERUL, nu clientul.** Un client stricat te face sa crezi ca serverul nu exista.
   ```
   adb shell run-as net.sys32.agent cat files/bridge.port       # AndroidBridge
   adb shell run-as net.sys32.agent cat files/tmp/dshell.port   # DShell
   adb shell ss -ltn | grep -E '46500|34793'                    # cine asculta
   ```
2. Sondeaza fiecare port cu payload-ul POTRIVIT (script pe disc, NU `-c` cu ghilimele
   imbricate - escapare in `adb shell` da output GOL si crezi ca portul e mort):
   ```python
   import socket, json
   def probe(port, payload):
       s=socket.socket(); s.settimeout(6); s.connect(("127.0.0.1",port))
       s.sendall((json.dumps(payload)+"\n").encode())
       buf=b""
       while not buf.endswith(b"\n"):
           c=s.recv(65536)
           if not c: break
           buf+=c
       s.close(); return buf.decode("utf-8","replace").strip()
   probe(46500, {"cmd":"ping"})                              # DShell  -> pong
   probe(46500, {"cmd":"debian","arg":"cat /etc/debian_version"})  # -> 13.7
   probe(46500, {"cmd":"sh","arg":"id -u"})                  # -> 2000
   probe(34793, {"cmd":"ping"})                              # AndroidBridge -> unknown tool
   probe(34793, {"tool":"camera","action":"list","params":{}})     # -> camerele
   ```
3. Abia apoi citeste codul: `_dshell_handle` in `agent.py` arata exact ce comenzi
   accepta DShell (`ping|sh|debian|eval`, restul -> `android_bridge`).

## Pitfalls
- **Un client stricat NU dovedeste ca serverul lipseste.** Am concluzionat "DShell nu
  exista" pentru ca `dshell.py` intorcea `unknown tool:` - el lua `bridge.port` pentru ca
  fusesem eu insumi pus `bridge.port` inaintea `dshell.port` in `PORTFILE_CANDIDATES`.
  Verificarea corecta e pasul 1-2 de mai sus, nu rularea clientului.
- A pune `bridge.port` primul in `dshell.py` / `android_full.py` STRICA ambele:
  ele vorbesc DShell. Restaurare: `git checkout <commit> -- <fisier>`.
- `adb shell 'run-as ... '` rulat prin `bash -lc` pe HOST da `run-as: command not found`
  (comanda ajunge local). Foloseste `subprocess.run([ADB,"shell"], input=cmd)`.

## Dovada ca DShell e viu (ruleaza asta INAINTE sa concluzionezi ceva)
```
python3 -c: socket -> 127.0.0.1:46500, trimite {"cmd":"ping"}
  -> {"ok": true, "out": "pong"}
  {"cmd":"debian","arg":"cat /etc/debian_version"} -> "13.7"
  {"cmd":"sh","arg":"id -u"}                       -> "2000"
  {"cmd":"battery","arg":"{\"action\":\"full\"}"}   -> level/charging/temp
  {"cmd":"sensors","arg":"{\"action\":\"list\"}"}   -> 35 senzori
  {"cmd":"eval","arg":"{\"op\":\"call\",\"target\":\"ctx\",\"method\":\"getPackageName\"}"}
```

## Capcane
- `dshell.port` NU e "vechi": e portul DShell. `bridge.port` e alt server. Ambele sunt vii.
- Istoric: `dshell_bridge.py` (proces separat, port 45800) a fost ABSORBIT in `agent.py`
  in commit-ul `d130556` ("stabil la rebuild"). Fisierul nu mai exista pe disc, dar
  serverul DA - e in agent.py.
- `python3.sh` din `files/tmp` contine `nativeLibraryDir`, care se schimba la FIECARE
  reinstalare (`/data/app/~~XXXX==/net.sys32.agent-YYYY==`). Simptom:
  `libpyexec.so: inaccessible or not found`. Repara cu
  `pm path net.sys32.agent | sed 's|package:||;s|/base.apk||'` (NU `cut -d= -f2`: calea contine `==`).
- `dumpsys media.camera` fara pipe in `adb shell` da "inaccessible or not found":
  ruleaza-l din python sau fara pipe.
