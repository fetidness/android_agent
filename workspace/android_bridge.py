"""Bridge catre tool-urile native Android (Kotlin).
Comunica prin TCP loopback cu AndroidBridge.kt (portul e scris in bridge.port).
"""
import json, os, socket, sys

_BRIDGE = None
_PORT = None

def _port_file_candidates():
    c = []
    v = os.environ.get("AGENT_BRIDGE_PORT_FILE")
    if v: c.append(v)
    v = os.environ.get("ANDROID_BRIDGE")
    if v: c.append(v + ".port")
    home = os.environ.get("HOME", "")
    if home:
        c.append(os.path.join(home, "bridge.port"))
        c.append(os.path.join(os.path.dirname(home), "bridge.port"))
    try:
        d = os.path.dirname(os.path.abspath(__file__))
        c.append(os.path.join(d, "bridge.port"))
        c.append(os.path.join(os.path.dirname(d), "bridge.port"))
    except Exception:
        pass
    # cai absolute tipice in sandbox-ul aplicatiei
    c.append("/data/data/net.sys32.agent/files/bridge.port")
    return c

def _find_port():
    global _PORT
    if _PORT: return _PORT
    for p in _port_file_candidates():
        try:
            if p and os.path.exists(p):
                t = open(p).read().strip()
                if t.isdigit():
                    _PORT = int(t)
                    return _PORT
        except Exception:
            pass
    raise RuntimeError("bridge port not found (looked in: %s)" % ", ".join(x for x in _port_file_candidates() if x))

def _connect():
    global _BRIDGE
    if _BRIDGE is not None:
        return _BRIDGE
    port = _find_port()
    s = socket.create_connection(("127.0.0.1", port), timeout=30)
    _BRIDGE = s
    return s

def call(tool, action="", **params):
    """Trimite o cerere catre bridge si intoarce dict-ul de raspuns."""
    global _BRIDGE
    try:
        s = _connect()
        req = {"tool": tool, "action": action, "params": params}
        s.sendall((json.dumps(req) + "\n").encode("utf-8"))
        buf = b""
        while not buf.endswith(b"\n"):
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
        if not buf:
            raise RuntimeError("empty response from bridge")
        return json.loads(buf.decode("utf-8", "replace"))
    except Exception:
        # reconectare o singura data (daca app-ul s-a repornit)
        try:
            _BRIDGE = None
            s = _connect()
            req = {"tool": tool, "action": action, "params": params}
            s.sendall((json.dumps(req) + "\n").encode("utf-8"))
            buf = b""
            while not buf.endswith(b"\n"):
                chunk = s.recv(65536)
                if not chunk: break
                buf += chunk
            return json.loads(buf.decode("utf-8", "replace"))
        except Exception as e:
            raise

def available():
    try:
        _connect(); return True
    except Exception:
        return False
