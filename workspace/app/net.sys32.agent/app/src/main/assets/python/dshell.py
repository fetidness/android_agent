#!/usr/bin/env python3
"""dshell - client care vorbeste cu aplicatia agent prin TCP localhost.

Folosire:
  dshell sh "id -u"              ruleaza ca uid 2000 (adbd)
  dshell debian "uname -a"       ruleaza in Debian
  dshell ping
  dshell ui '{"action":"read","max":15}'    orice tool Android
  dshell battery '{"action":"full"}'
  dshell eval '{"op":"call","target":"ctx","method":"getPackageName"}'

Portul se citeste din dshell.port (scris de server), sau din $DSHELL_PORT.
"""
import json, os, socket, sys

PORTFILE_CANDIDATES = (
    "/sdcard/Download/Agent/workspace/dshell.port",
    "/data/local/tmp/dshell.port",
)
DEFAULT_PORT = 46500


def get_port():
    p = os.environ.get("DSHELL_PORT")
    if p:
        return int(p)
    for f in PORTFILE_CANDIDATES:
        try:
            return int(open(f).read().strip())
        except Exception:
            continue
    return DEFAULT_PORT


def call(cmd, arg="", port=None, timeout=None):
    port = port or get_port()
    req = {"cmd": cmd, "arg": arg}
    if timeout:
        req["timeout"] = timeout
    s = socket.socket()
    s.settimeout(300)
    s.connect(("127.0.0.1", port))
    s.sendall((json.dumps(req) + "\n").encode())
    buf = b""
    while b"\n" not in buf:
        d = s.recv(65536)
        if not d:
            break
        buf += d
    s.close()
    if not buf:
        return {"ok": False, "err": "fara raspuns de la bridge (aplicatia ruleaza?)"}
    try:
        return json.loads(buf.split(b"\n", 1)[0].decode("utf-8", "replace"))
    except Exception as e:
        return {"ok": False, "err": "raspuns invalid: %s" % e}


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    cmd = sys.argv[1]
    arg = " ".join(sys.argv[2:])
    r = call(cmd, arg)
    if r.get("ok"):
        print(r.get("out", ""), end="" if r.get("out", "").endswith("\n") else "\n")
        return 0
    print("[dshell] EROARE: %s" % r.get("err"), file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
