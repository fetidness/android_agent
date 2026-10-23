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
"""
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

_PORT = {"v": None}


def _port_candidates():
    c = []
    env = os.environ.get("DSHELL_PORT_FILE")
    if env:
        c.append(env)
    # calea pe care Debian o vede (workspace-ul de pe /sdcard)
    c.append("/storage/emulated/0/Download/Agent/workspace/dshell.port")
    c.append("/data/local/tmp/dshell.port")
    here = Path(__file__).resolve().parent
    c.append(str(here / "dshell.port"))
    c.append(str(here.parent / "tmp" / "dshell.port"))
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


def call(cmd, arg=""):
    """O cerere DShell. Intoarce dict-ul brut {"ok":..,"out"/"error":..}."""
    def _once():
        p = port()
        s = socket.create_connection(("127.0.0.1", p), timeout=120)
        try:
            s.sendall((json.dumps({"cmd": cmd, "arg": arg}) + "\n").encode())
            buf = b""
            while not buf.endswith(b"\n"):
                ch = s.recv(65536)
                if not ch:
                    break
                buf += ch
            if not buf:
                raise RuntimeError("raspuns gol de la dshell")
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


def available():
    try:
        return bool(call("ping").get("ok"))
    except Exception:
        return False


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
    try:
        if cmd == "available":
            out = {"available": available(), "port": port()}
        else:
            r = call(cmd, arg)
            if not r.get("ok"):
                print("ERR: " + str(r.get("error"))[:300])
                sys.exit(1)
            out = r.get("out")
            # multe comenzi intorc JSON ca STRING: il parsez o data, ca sa fie utilizabil
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
    except Exception as e:
        print("ERR: " + type(e).__name__ + ": " + str(e)[:300])
        sys.exit(1)
