#!/usr/bin/env python3
"""dshell_bridge.py - RPC bridge: expune puterile agentului catre Debian.

Ruleaza IN PROCESUL APLICATIEI (acces la SDK Android + adb_client).
Debian trimite linii JSON pe 127.0.0.1:PORT:
  {"cmd":"ping"}                      -> {"ok":true,"out":"pong"}
  {"cmd":"sh","arg":"id -u"}          -> shell uid 2000 (adbd)
  {"cmd":"debian","arg":"uname -a"}   -> ruleaza in Debian (proot)
  {"cmd":"eval","arg":"<java>"}       -> reflecție Android (coada evalq/)

Raspuns: o linie JSON {"ok":bool,"out":str} sau {"ok":false,"err":str}
"""
import json, os, socket, threading, time, traceback

PORT = int(os.environ.get("DSHELL_BRIDGE_PORT", "45800"))
BASE = "/storage/emulated/0/Download/Agent/workspace"
PORTFILE = os.path.join(BASE, "dshell.port")
EVAL_DIR = os.path.join(BASE, "evalq")


def _sh(cmd, timeout=120):
    import adb_client
    try:
        if not adb_client.is_socket_healthy():
            adb_client.close_shared()
    except Exception:
        pass
    return adb_client.shared().shell(cmd, timeout=timeout) or ""


def _debian(cmd, timeout=180):
    import sys
    p = "/data/data/net.sys32.agent/files/python"
    if p not in sys.path:
        sys.path.insert(0, p)
    import agent
    return agent.run_terminal_tool({"action": "run", "cmd": cmd, "timeout": timeout}) or ""


# ---------- coada eval: Debian scrie req, worker-ul aplicatiei scrie res ----------
def eval_worker():
    """Proceseaza continuu evalq/req.*.json -> evalq/res.*.json.

    Scrierea raspunsului e ATOMICA (tmp + rename), ca cititorul sa nu
    prinda niciodata un fisier pe jumatate scris.
    """
    os.makedirs(EVAL_DIR, exist_ok=True)
    while True:
        try:
            for name in os.listdir(EVAL_DIR):
                if not (name.startswith("req.") and name.endswith(".json")):
                    continue
                req = os.path.join(EVAL_DIR, name)
                base = name[4:-5]
                try:
                    expr = json.loads(open(req).read()).get("expr", "")
                except Exception:
                    try:
                        os.remove(req)
                    except Exception:
                        pass
                    continue
                out = _run_expr(expr)
                tmp = os.path.join(EVAL_DIR, ".tmp." + base)
                try:
                    with open(tmp, "w") as f:
                        json.dump({"ok": True, "out": out}, f)
                    os.rename(tmp, os.path.join(EVAL_DIR, "res.%s.json" % base))
                except Exception:
                    pass
                try:
                    os.remove(req)
                except Exception:
                    pass
        except Exception:
            pass
        time.sleep(0.05)


def _run_expr(expr):
    """Punct de extensie: aici se executa reflecția Android.

    Implicit returneaza expresia evaluata in Python (util pentru teste).
    Agentul poate inlocui aceasta functie cu apelul catre toolul `android`.
    """
    try:
        return str(eval(expr, {"__builtins__": {}}, {}))
    except Exception:
        return "[eval] %s" % expr


def _eval(expr, timeout=60):
    os.makedirs(EVAL_DIR, exist_ok=True)
    ts = "%d_%d" % (int(time.time() * 1000), os.getpid())
    req = os.path.join(EVAL_DIR, "req.%s.json" % ts)
    res = os.path.join(EVAL_DIR, "res.%s.json" % ts)
    with open(req, "w") as f:
        f.write(json.dumps({"expr": expr}))
    deadline = time.time() + timeout
    while time.time() < deadline:
        if os.path.exists(res):
            try:
                raw = open(res).read()
                d = json.loads(raw) if raw.strip() else {}
            except Exception:
                time.sleep(0.1)
                continue
            try:
                os.remove(res)
            except Exception:
                pass
            return d.get("out", "") if d.get("ok") else "[eval err] " + str(d.get("err"))
        time.sleep(0.05)
    return "[eval timeout] agentul nu a raspuns in %ds" % timeout


HANDLERS = {"sh": _sh, "debian": _debian, "eval": _eval}


def handle(req):
    cmd = req.get("cmd")
    if cmd == "ping":
        return {"ok": True, "out": "pong"}
    fn = HANDLERS.get(cmd)
    if not fn:
        return {"ok": False, "err": "comanda necunoscuta: %s" % cmd}
    try:
        return {"ok": True, "out": fn(req.get("arg", ""), req.get("timeout", 120))}
    except Exception as e:
        return {"ok": False, "err": "%s: %s" % (type(e).__name__, e)}


def _client(conn):
    try:
        conn.settimeout(300)
        buf = b""
        while True:
            while b"\n" not in buf:
                d = conn.recv(65536)
                if not d:
                    return
                buf += d
            line, buf = buf.split(b"\n", 1)
            if not line.strip():
                continue
            try:
                req = json.loads(line.decode("utf-8", "replace"))
            except Exception as e:
                conn.sendall((json.dumps({"ok": False, "err": "json: %s" % e}) + "\n").encode())
                continue
            conn.sendall((json.dumps(handle(req)) + "\n").encode())
    except Exception:
        pass
    finally:
        try:
            conn.close()
        except Exception:
            pass


def serve_forever(port=None):
    port = port or PORT
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", port))
    srv.listen(16)
    try:
        os.makedirs(BASE, exist_ok=True)
        with open(PORTFILE, "w") as f:
            f.write(str(port))
    except Exception:
        pass
    threading.Thread(target=eval_worker, daemon=True).start()
    print("[bridge] 127.0.0.1:%d  evalq=%s" % (port, EVAL_DIR))
    while True:
        try:
            conn, _ = srv.accept()
        except Exception:
            break
        threading.Thread(target=_client, args=(conn,), daemon=True).start()


if __name__ == "__main__":
    serve_forever()
