#!/usr/bin/env python3
"""android_full - acces complet la Android din Debian, prin bridge-ul aplicatiei.

Bridge-ul (AndroidBridge.kt) ruleaza in procesul APLICATIEI, unde reflexia si
SDK-ul functioneaza complet. Aici e clientul: JSON pe linie peste TCP loopback.

Asta da lui Debian EXACT accesul pe care il are tool-ul `android` din agent:
senzori live, camera, orice getSystemService, reflexie arbitrara.

Uz:
  python3 android_full.py battery
  python3 android_full.py sensors list
  python3 android_full.py eval '{"op":"services"}'
  python3 android_full.py raw '{"tool":"wifi"}'
"""
import json
import os
import socket
import sys
from pathlib import Path

_PORT_CACHE = {"p": None}


def _port_candidates():
    """Locuri in care poate sta bridge.port, in ordinea sanselor."""
    c = []
    for env in ("AGENT_BRIDGE_PORT_FILE",):
        v = os.environ.get(env)
        if v:
            c.append(v)
    env = os.environ.get("ANDROID_BRIDGE")
    if env:
        c.append(env + ".port")
    # workspace-ul de pe /sdcard - calea prin care Debian vede device-ul
    c.append("/storage/emulated/0/Download/Agent/workspace/bridge.port")
    # filesDir (vizibil doar din app, dar incercam)
    c.append("/data/data/net.sys32.agent/files/bridge.port")
    c.append("/data/data/net.sys32.agent/files/home/bridge.port")
    here = Path(__file__).resolve().parent
    c.append(str(here / "bridge.port"))
    return c


def port(force=False):
    if _PORT_CACHE["p"] and not force:
        return _PORT_CACHE["p"]
    for p in _port_candidates():
        try:
            if p and os.path.exists(p):
                t = open(p).read().strip()
                if t.isdigit():
                    _PORT_CACHE["p"] = int(t)
                    return _PORT_CACHE["p"]
        except Exception:
            pass
    raise RuntimeError("bridge.port negasit in: " + ", ".join(_port_candidates()))


def call(tool, action="", **params):
    """O cerere catre bridge; intoarce dict-ul de raspuns (nu arunca la ok=False)."""
    def _once():
        p = port()
        s = socket.create_connection(("127.0.0.1", p), timeout=60)
        try:
            s.sendall((json.dumps({"tool": tool, "action": action, "params": params}) + "\n").encode())
            buf = b""
            while not buf.endswith(b"\n"):
                chunk = s.recv(65536)
                if not chunk:
                    break
                buf += chunk
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
        # aplicatia poate fi repornita pe alt port: recitim fisierul o data
        port(force=True)
        return _once()


def ok(tool, action="", **params):
    """Ca call(), dar intoarce doar `data` si arunca daca ok=False."""
    r = call(tool, action, **params)
    if not r.get("ok"):
        raise RuntimeError(str(r.get("error"))[:300])
    return r.get("data")


def available():
    try:
        return bool(call("battery").get("ok"))
    except Exception:
        return False


def eval_expr(expr):
    """Reflexie arbitrara: {"op":"services"} / {"op":"call",...} / {"op":"get",...}"""
    return ok("eval", expr=expr)


def service_info(target, filt=""):
    return ok("eval", expr={"op": "info", "target": target, "filter": filt})


def get_system_service(name):
    """Exact ca ctx.getSystemService din cod Android."""
    return ok("eval", expr={"op": "call", "target": "ctx",
                            "method": "getSystemService", "args": [name]})


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        sys.exit(0)
    cmd = a[0]
    try:
        if cmd == "eval":
            out = eval_expr(json.loads(a[1]))
        elif cmd == "info":
            out = service_info(a[1], a[2] if len(a) > 2 else "")
        elif cmd == "raw":
            out = call(**json.loads(a[1]))
        elif cmd == "available":
            out = {"available": available(), "port": port()}
        elif len(a) > 1:
            out = ok(cmd, a[1])
        else:
            out = ok(cmd)
        print(json.dumps(out, indent=1, ensure_ascii=False)[:8000])
    except Exception as e:
        print("ERR: " + type(e).__name__ + ": " + str(e)[:300])
        sys.exit(1)
