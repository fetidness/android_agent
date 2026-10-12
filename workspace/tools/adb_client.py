#!/usr/bin/env python3
"""phone_client.py - client pentru gate.py (framing binar 4B + JSON)."""
import socket, struct, json, base64, sys

PORT = 9999
TOKEN = "gab2026"
HOST = "127.0.0.1"   # prin adb reverse, portita laptopului apare local

def _recv_exact(s, n):
    b = b""
    while len(b) < n:
        d = s.recv(n - len(b))
        if not d: return None
        b += d
    return b

def _frame(s, obj):
    d = json.dumps(obj).encode()
    s.sendall(struct.pack(">I", len(d)) + d)

def _unframe(s):
    h = _recv_exact(s, 4)
    if h is None: return None
    ln = struct.unpack(">I", h)[0]
    return json.loads(_recv_exact(s, ln).decode("utf-8", "replace"))

def call(op, token=TOKEN, host=HOST, port=PORT, timeout=600, **kw):
    s = socket.socket(); s.settimeout(timeout)
    s.connect((host, port))
    try:
        if token:
            _frame(s, {"op": "TOKEN", "token": token})
            if not _unframe(s).get("auth"):
                raise RuntimeError("auth esuat (token gresit)")
        _frame(s, dict(op=op, **kw))
        return _unframe(s)
    finally:
        s.close()

def ping(**k):  return call("PING", **k)
def info(**k):  return call("INFO", **k)
def cmd(c, **k): return call("CMD", cmd=c, **k)
def get(p, **k): return base64.b64decode(call("GET", path=p, **k)["b64"])
def put(p, data, **k): return call("PUT", path=p, b64=base64.b64encode(data).decode(), **k)

if __name__ == "__main__":
    h = sys.argv[1] if len(sys.argv) > 1 else HOST
    print("PING:", ping(host=h))
    print("INFO:", info(host=h))
    r = cmd("uname -a && whoami && pwd", host=h)
    print("CMD rc=%s" % r.get("rc"))
    print(r.get("out", "").strip())
    if r.get("err"): print("ERR:", r["err"].strip())
