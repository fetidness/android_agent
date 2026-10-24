#!/usr/bin/env python3
"""android_full - acces complet la Android din Debian (o singura cale: DShell).

DShell e puntea CANONICA: un server in procesul aplicatiei, expus pe TCP loopback,
cu client instalat in /usr/local/bin/dshell. Aici nu duplicam nimic - vorbim cu el.

De ce DShell si nu AndroidBridge direct:
  - DShell expune TOT ce expune AndroidBridge (orice cmd e pasat tool-urilor native)
    PLUS doua lucruri care nu exista in AndroidBridge: `sh` (uid 2000) si `debian`.
  - are self-heal la rebuild (clientul se rescrie in rootfs la fiecare pornire)
  - portul se muta automat daca e ocupat (46500..46519)

Protocol: o linie JSON per cerere -> {"cmd":..., "arg":...} -> {"ok":..., "out":...}

Uz:
  python3 android_full.py available
  python3 android_full.py sh "id -u"
  python3 android_full.py debian "uname -a"
  python3 android_full.py eval '{"op":"call","target":"ctx","method":"getSystemService","args":["wifi"]}'
  python3 android_full.py sensors '{"action":"list"}'
  python3 android_full.py battery '{"action":"full"}'
  python3 android_full.py ui '{"action":"read","max":10}'
  python3 android_full.py camera '{"on":true}'        # LANTERNA (nativ, nu reflexie)
  python3 android_full.py camera '{"on":false}'

Protocol: doua formate, in functie de cmd.
  {"cmd","arg"}                  -> comenzile vechi: sh, debian, ping
  {"tool","action","params":{}}  -> tot ce expune AndroidBridge.kt:
                                    sensors, camera, location, battery, clipboard, notify,
                                    vibrate, tts, volume, wifi, device, apps, intent, settings,
                                    system, storage, processes, network, display, audio,
                                    telephony, ui, notif, ime, capture, eval, services, info

Lanterna are acum actiune nativa: {"tool":"camera","action":"torch","params":{"on":true}}.
Inainte lipsea si trebuia improvizata cu reflexie peste CameraManager.setTorchMode,
care esua cu "field not found: cameraIdList" si "argument 1 has type CameraCharacteristics$Key".
"""
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

_PORT = {"v": None}


def _port_candidates():
    """Fisierele unde serverul Kotlin isi anunta portul, in ordinea de preferinta.

    AndroidBridge.kt scrie DOUA fisiere: files/bridge.port si files/home/bridge.port.
    Restul sunt mosteniri istorice (dshell.port) - pastrate ca fallback, dar ultimele,
    pentru ca pot fi VECHI si atunci clientul vorbeste pe un port mort.
    """
    c = []
    env = os.environ.get("DSHELL_PORT_FILE")
    if env:
        c.append(env)
    env = os.environ.get("AGENT_BRIDGE_PORT_FILE")
    if env:
        c.append(env)
    home = os.environ.get("HOME", "")
    if home:
        c.append(os.path.join(home, "bridge.port"))
        c.append(os.path.join(os.path.dirname(home), "bridge.port"))
    try:
        here = Path(__file__).resolve().parent          # files/python
        files = here.parent                             # files
        c.append(str(files / "bridge.port"))            # <- calea REALA scrisa de Kotlin
        c.append(str(files / "home" / "bridge.port"))
        c.append(str(here / "bridge.port"))
        c.append(str(here.parent / "tmp" / "dshell.port"))
    except Exception:
        pass
    c.append("/data/data/net.sys32.agent/files/bridge.port")
    c.append("/data/data/net.sys32.agent/files/home/bridge.port")
    c.append("/storage/emulated/0/Download/Agent/workspace/dshell.port")
    c.append("/data/local/tmp/dshell.port")
    return c


def port(force=False):
    if _PORT["v"] and not force:
        return _PORT["v"]
    for p in _port_candidates():
        try:
            if p and os.path.exists(p):
                t = open(p).read().strip()
                if t.isdigit():
                    _PORT["v"] = int(t)
                    return _PORT["v"]
        except Exception:
            pass
    raise RuntimeError("dshell.port negasit in: " + ", ".join(_port_candidates()))


def _request(payload, timeout=120):
    """Trimite UN dict JSON pe o linie si citeste UN dict JSON inapoi."""
    def _once():
        p = port()
        s = socket.create_connection(("127.0.0.1", p), timeout=timeout)
        try:
            s.sendall((json.dumps(payload) + "\n").encode())
            buf = b""
            while not buf.endswith(b"\n"):
                ch = s.recv(65536)
                if not ch:
                    break
                buf += ch
            if not buf:
                raise RuntimeError("raspuns gol de la bridge")
            return json.loads(buf.decode("utf-8", "replace"))
        finally:
            try:
                s.close()
            except Exception:
                pass
    try:
        return _once()
    except Exception:
        port(force=True)      # aplicatia poate fi pe alt port acum
        return _once()


def call(cmd, arg=""):
    """O cerere DShell in VECHIUL protocol {"cmd","arg"} (pastrat pentru `sh`/`debian`)."""
    return _request({"cmd": cmd, "arg": arg})


def tool(name, action="", **params):
    """Cerere in protocolul REAL al serverului: {"tool","action","params"}.

    AndroidBridge.kt (singurul care scrie bridge.port) accepta doar acest format;
    {"cmd","arg"} dadea "unknown tool: ".
    """
    r = _request({"tool": name, "action": action, "params": params})
    if not r.get("ok"):
        raise RuntimeError(str(r.get("error"))[:300])
    return r.get("data")


def ok(cmd, arg=""):
    """Ca call(), dar intoarce doar `out` si arunca daca ok=False."""
    r = call(cmd, arg)
    if not r.get("ok"):
        raise RuntimeError(str(r.get("error"))[:300])
    return r.get("out")


def json_call(cmd, action="", **params):
    """Pentru comenzile cu parametri: trimite {"action":..,...} ca JSON si parseaza `out`."""
    payload = dict(params)
    if action:
        payload["action"] = action
    out = ok(cmd, json.dumps(payload) if payload else "")
    if isinstance(out, str):
        try:
            return json.loads(out)
        except Exception:
            return out
    return out


def _probe():
    """Bridge viu? `ping` NU e tool in AndroidBridge.kt (dadea 'unknown tool:') - folosim camera list."""
    try:
        return bool(_request({"tool": "camera", "action": "list", "params": {}}).get("ok"))
    except Exception:
        return False


def available():
    return _probe()


# ---- scurtaturi pentru cazurile cele mai folosite ----
def sh(cmd):
    """Comanda ca uid 2000 (pm/dumpsys/settings/input)."""
    return ok("sh", cmd)


def debian(cmd):
    """Comanda in rootfs-ul Debian (proot)."""
    return ok("debian", cmd)


def eval_expr(expr):
    """Reflexie arbitrara: {"op":"services"} / {"op":"call",...} / {"op":"get",...}."""
    return ok("eval", json.dumps(expr) if isinstance(expr, dict) else str(expr))


def get_system_service(name):
    """Exact ca ctx.getSystemService din cod Android."""
    return eval_expr({"op": "call", "target": "ctx",
                      "method": "getSystemService", "args": [name]})


# ---- lanterna (actiune nativa `camera torch`, nu reflexie) ----
def torch(on):
    """Porneste/opreste lanterna. Intoarce {"on":bool,"cameraId":str}."""
    return tool("camera", "torch", on=bool(on))


def torch_status():
    """Starea lanternei asa cum o tine minte aplicatia (serverul nu are getter nativ)."""
    return tool("camera", "status")


def flash(times=1, delay=0.4):
    """Porneste lanterna de `times` ori, cu pauza intre cicluri. Intoarce lista de stari."""
    import time as _t
    out = []
    for i in range(int(times)):
        out.append({"cycle": i + 1, "on": torch(True)})
        _t.sleep(delay)
        out.append({"cycle": i + 1, "off": torch(False)})
        _t.sleep(delay)
    return out


def _dshell_bin():
    """Clientul oficial din rootfs, daca exista (calea cea mai directa)."""
    for p in ("/usr/local/bin/dshell", "/usr/bin/dshell"):
        if os.path.exists(p):
            return p
    return None


def via_binary(cmd, arg=""):
    """Varianta cu binarul `dshell` din rootfs (utile daca socketul e blocat)."""
    b = _dshell_bin()
    if not b:
        raise RuntimeError("dshell nu e instalat")
    r = subprocess.run([b, cmd] + ([arg] if arg else []),
                       capture_output=True, text=True, timeout=180)
    return r.stdout.strip()


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        sys.exit(0)
    cmd = a[0]
    arg = a[1] if len(a) > 1 else ""
    # Comenzile vechi vorbesc {"cmd","arg"}; orice altceva e un TOOL nativ {"tool","action","params"}.
    LEGACY = ("sh", "debian", "ping")
    try:
        if cmd == "available":
            out = {"available": _probe(), "port": port()}
        elif cmd == "torch":
            out = torch(arg.strip().lower() in ("1", "on", "true", "yes"))
        elif cmd == "flash":
            out = flash(int(arg or 1))
        else:
            if cmd in LEGACY:
                r = call(cmd, arg)
            else:
                params = {}
                action = ""
                if arg.strip():
                    try:
                        params = json.loads(arg)
                    except Exception:
                        params = {"action": arg.strip()}
                if isinstance(params, dict) and "action" in params:
                    action = str(params.pop("action"))
                r = _request({"tool": cmd, "action": action, "params": params})
            if not r.get("ok"):
                print("ERR: " + str(r.get("error") or r.get("err"))[:300])
                sys.exit(1)
            out = r.get("data", r.get("out"))
            if isinstance(out, str):
                s = out.strip()
                if s[:1] in "[{":
                    try:
                        out = json.loads(s)
                    except Exception:
                        pass
        if isinstance(out, str):
            print(out)
        else:
            print(json.dumps(out, indent=1, ensure_ascii=False)[:8000])
    except BrokenPipeError:
        # `| head` inchide pipe-ul: nu e o eroare reala, dar traceback-ul polueaza output-ul
        try:
            os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        except Exception:
            pass
        sys.exit(0)
    except Exception as e:
        try:
            print("ERR: " + type(e).__name__ + ": " + str(e)[:300])
        except BrokenPipeError:
            pass
        sys.exit(1)
