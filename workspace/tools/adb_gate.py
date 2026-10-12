#!/usr/bin/env python3
"""
gate.py - portita simpla telefon <-> laptop prin USB (mod ADB REVERSE).
UN SINGUR FISIER. Zero dependinte (doar Python 3 stdlib).

FOLOSIRE:
    python3 gate.py            # porneste (tunel adb reverse pe 9999)
    python3 gate.py --port N   # alt port
    Ctrl+C                     # opreste

Nu are nevoie de tethering. Doar: cablu USB + telefon conectat + adb instalat
si autorizat. Tunelul se re-face automat daca se pierde.
Clientul (telefonul) se conecteaza la 127.0.0.1:PORT.

PROTOCOL (framing: 4 bytes big-endian lungime + JSON):
    {"op":"TOKEN","token":"gab2026"}   -> {"auth":true}
    {"op":"PING"}                      -> {"pong":true}
    {"op":"CMD","cmd":"ls -la"}        -> {"rc":0,"out":"...","err":"..."}
    {"op":"GET","path":"/etc/hosts"}   -> {"size":N,"b64":"..."}
    {"op":"PUT","path":"/tmp/x","b64"} -> {"ok":true}
    {"op":"INFO"}                      -> {host,user,cwd,os,py}
"""
import socket, subprocess, os, sys, base64, threading, struct, json, argparse, platform, getpass, time, shutil

PORT_DEFAULT = 9999
TOKEN_DEFAULT = "gab2026"

def recv_exact(conn, n):
    buf = b""
    while len(buf) < n:
        d = conn.recv(n - len(buf))
        if not d: return None
        buf += d
    return buf

def recv_frame(conn):
    hdr = recv_exact(conn, 4)
    if hdr is None: return None
    ln = struct.unpack(">I", hdr)[0]
    return b"" if ln == 0 else recv_exact(conn, ln)

def send_frame(conn, data):
    conn.sendall(struct.pack(">I", len(data)) + data)

def jb(d): return json.dumps(d).encode()

def run_cmd(cmd, timeout):
    # copilul NU mosteneste socketul: setsid + inchide fd 3..255 + stdin gol
    def pre():
        os.setsid()
        for fd in range(3, 256):
            try: os.close(fd)
            except OSError: pass
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, timeout=timeout,
                           stdin=subprocess.DEVNULL, preexec_fn=pre)
        return {"rc": r.returncode,
                "out": r.stdout.decode("utf-8", "replace"),
                "err": r.stderr.decode("utf-8", "replace")}
    except subprocess.TimeoutExpired:
        return {"rc": -9, "out": "", "err": "TIMEOUT %ds" % timeout}
    except Exception as e:
        return {"rc": -1, "out": "", "err": str(e)}

def handle(conn, addr, token, timeout):
    authed = (token == "")
    conn.settimeout(None)
    try:
        while True:
            raw = recv_frame(conn)
            if raw is None: break
            try:
                req = json.loads(raw.decode("utf-8", "replace"))
            except Exception as e:
                send_frame(conn, jb({"error": "bad json: " + str(e)})); continue
            op = req.get("op", "").upper()
            if op == "PING":
                send_frame(conn, jb({"pong": True})); continue
            if op == "TOKEN":
                authed = (req.get("token", "") == token)
                send_frame(conn, jb({"auth": authed})); continue
            if not authed:
                send_frame(conn, jb({"error": "not authenticated"})); continue
            if op == "CMD":
                cmd = req.get("cmd", "")
                print("[>] %s" % (cmd[:120],), flush=True)
                send_frame(conn, jb(run_cmd(cmd, timeout)))
            elif op == "GET":
                try:
                    data = open(req.get("path", ""), "rb").read()
                    send_frame(conn, jb({"size": len(data), "b64": base64.b64encode(data).decode()}))
                except Exception as e:
                    send_frame(conn, jb({"error": str(e)}))
            elif op == "PUT":
                try:
                    data = base64.b64decode(req.get("b64", ""))
                    path = req.get("path", "")
                    d = os.path.dirname(os.path.abspath(path))
                    if d: os.makedirs(d, exist_ok=True)
                    open(path, "wb").write(data)
                    send_frame(conn, jb({"ok": True, "size": len(data), "path": path}))
                except Exception as e:
                    send_frame(conn, jb({"error": str(e)}))
            elif op == "INFO":
                send_frame(conn, jb({"host": socket.gethostname(), "user": getpass.getuser(),
                                     "cwd": os.getcwd(), "os": platform.platform(),
                                     "py": sys.version.split()[0], "pid": os.getpid()}))
            else:
                send_frame(conn, jb({"error": "unknown op: " + op}))
    except Exception as e:
        print("[!] eroare: %s" % e, flush=True)
    finally:
        conn.close()

def reverse_keeper(port):
    """Tine tunelul adb reverse activ permanent."""
    if not shutil.which("adb"):
        print("[!] 'adb' nu e in PATH. Instaleaza adb (apt install adb) si reincearca.", flush=True)
        print("[!] Fara adb, portita nu poate primi conexiuni de pe telefon.", flush=True)
        return
    print("[*] tin tunelul adb reverse activ (port %d)..." % port, flush=True)
    while True:
        try:
            out = subprocess.run(["adb", "reverse", "--list"], capture_output=True, timeout=5).stdout.decode()
            if ("tcp:%d tcp:%d" % (port, port)) not in out:
                r = subprocess.run(["adb", "reverse", "tcp:%d" % port, "tcp:%d" % port],
                                   capture_output=True, timeout=5)
                if r.returncode == 0:
                    print("[+] tunel activ: telefon 127.0.0.1:%d -> laptop" % port, flush=True)
                else:
                    print("[!] adb reverse esuat: %s" % r.stderr.decode().strip(), flush=True)
        except Exception as e:
            print("[!] reverse: %s" % e, flush=True)
        time.sleep(3)

def main():
    ap = argparse.ArgumentParser(description="Portita telefon<->laptop prin adb reverse")
    ap.add_argument("--port", type=int, default=PORT_DEFAULT)
    ap.add_argument("--token", default=TOKEN_DEFAULT, help="token de acces (gol = fara)")
    ap.add_argument("--timeout", type=int, default=600, help="timeout maxim per comanda (s)")
    args = ap.parse_args()

    threading.Thread(target=reverse_keeper, args=(args.port,), daemon=True).start()
    time.sleep(1)

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("127.0.0.1", args.port))
    s.listen(16)
    print("[*] Portita pe 127.0.0.1:%d  (token: %s)" % (args.port, args.token or "NICIUNUL"), flush=True)
    print("[*] Clientul se conecteaza de pe telefon la 127.0.0.1:%d" % args.port, flush=True)
    print("[*] Ctrl+C pentru oprire.", flush=True)
    try:
        while True:
            conn, addr = s.accept()
            print("[+] conectat (prin tunel)", flush=True)
            threading.Thread(target=handle, args=(conn, addr, args.token, args.timeout), daemon=True).start()
    except KeyboardInterrupt:
        print("\n[*] Oprire.", flush=True)
    finally:
        s.close()

if __name__ == "__main__":
    main()
