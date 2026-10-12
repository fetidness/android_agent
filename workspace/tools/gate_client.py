#!/usr/bin/env python3
"""
gate_client.py - CLIENTUL portitei gate.py (perechea lui gate.py).
Se conecteaza la portita care ruleaza pe laptop (prin tunel adb reverse).

Pe TELEFON (sau orice masina care ajunge la 127.0.0.1:9999) rulezi:
    python3 gate_client.py --shell "uname -a"
    python3 gate_client.py --info
    python3 gate_client.py --put /tmp/x fisierul_local.txt
    python3 gate_client.py --get /etc/hosts salvare_locala.txt
    python3 gate_client.py --interactiv        # shell interactiv

Ca biblioteca:
    from gate_client import Gate
    g = Gate()                    # 127.0.0.1:9999, token gab2026
    print(g.shell("ls -la")["out"])
"""
import socket, struct, json, base64, argparse, sys, os

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9999
DEFAULT_TOKEN = "gab2026"

class Gate:
    """Client pentru portita gate.py."""
    def __init__(self, host=DEFAULT_HOST, port=DEFAULT_PORT, token=DEFAULT_TOKEN, timeout=60):
        self.host, self.port, self.token = host, port, token
        self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.s.settimeout(timeout)
        self.s.connect((host, port))
        r = self.cmd({"op": "TOKEN", "token": token})
        if not r or not r.get("auth"):
            raise RuntimeError("autentificare esuata (token gresit?)")

    def _recv_exact(self, n):
        buf = b""
        while len(buf) < n:
            d = self.s.recv(n - len(buf))
            if not d:
                raise ConnectionError("conexiune inchisa")
            buf += d
        return buf

    def cmd(self, obj, timeout=None):
        if timeout:
            self.s.settimeout(timeout)
        data = json.dumps(obj).encode()
        self.s.sendall(struct.pack(">I", len(data)) + data)
        hdr = self._recv_exact(4)
        ln = struct.unpack(">I", hdr)[0]
        payload = self._recv_exact(ln) if ln else b"{}"
        return json.loads(payload.decode("utf-8", "replace"))

    def ping(self):
        return self.cmd({"op": "PING"})

    def shell(self, cmd, timeout=None):
        return self.cmd({"op": "CMD", "cmd": cmd}, timeout)

    def info(self):
        return self.cmd({"op": "INFO"})

    def get(self, remote_path):
        r = self.cmd({"op": "GET", "path": remote_path})
        if "error" in r:
            raise RuntimeError(r["error"])
        return base64.b64decode(r["b64"])

    def put(self, remote_path, data):
        if isinstance(data, str):
            data = data.encode()
        return self.cmd({"op": "PUT", "path": remote_path, "b64": base64.b64encode(data).decode()})

    def close(self):
        self.s.close()

def main():
    ap = argparse.ArgumentParser(description="Client pentru gate.py")
    ap.add_argument("--host", default=DEFAULT_HOST)
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--token", default=DEFAULT_TOKEN)
    grp = ap.add_mutually_exclusive_group()
    grp.add_argument("--shell", metavar="CMD", help="executa o comanda")
    grp.add_argument("--info", action="store_true", help="detalii sistem")
    grp.add_argument("--put", nargs=2, metavar=("REMOTE", "LOCAL"), help="urca un fisier")
    grp.add_argument("--get", nargs=2, metavar=("REMOTE", "LOCAL"), help="descarca un fisier")
    grp.add_argument("--interactiv", action="store_true", help="shell interactiv")
    args = ap.parse_args()

    g = Gate(args.host, args.port, args.token)

    if args.shell:
        r = g.shell(args.shell)
        sys.stdout.write(r.get("out", ""))
        if r.get("err"):
            sys.stderr.write(r["err"])
        g.close()
        sys.exit(r.get("rc", 0))
    elif args.info:
        r = g.info()
        for k, v in r.items():
            print("%s: %s" % (k, v))
    elif args.put:
        local = open(args.put[1], "rb").read()
        print(g.put(args.put[0], local))
    elif args.get:
        open(args.get[1], "wb").write(g.get(args.get[0]))
        print("[+] salvat in %s" % args.get[1])
    elif args.interactiv:
        print("[*] shell interactiv. 'exit' pentru iesire.")
        while True:
            try:
                c = input("laptop$ ")
            except (EOFError, KeyboardInterrupt):
                break
            if c.strip() in ("exit", "quit"):
                break
            r = g.shell(c)
            sys.stdout.write(r.get("out", ""))
            if r.get("err"):
                sys.stderr.write(r["err"])
    else:
        print("[*] gate_client. Foloseste --shell/--info/--put/--get/--interactiv sau --help")
    g.close()

if __name__ == "__main__":
    main()
