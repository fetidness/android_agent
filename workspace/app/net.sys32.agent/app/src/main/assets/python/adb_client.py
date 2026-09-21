#!/usr/bin/env python3
"""ADB client pur Python -> adbd 127.0.0.1:5555. Trimite RSAPUBLICKEY direct."""
import socket, struct, os, sys, time, ctypes, signal

F = "/data/data/net.sys32.agent/files"
KEY = F + "/adbkey"; PUBC = F + "/adbkey.pub"
LIBCRYPT = F + "/libs/libcrypto.so"

def _ensure_libs():
    """Copiaza o singura data bibliotecile crypto din sistem in files/libs/ (linker-ul
    Android nu permite dlopen direct din /apex, dar permite din spatiul app-ului)."""
    import shutil
    d = F + "/libs"
    if os.path.exists(d + "/libcrypto.so"):
        return True
    try:
        os.makedirs(d, exist_ok=True)
        for fn in ("libcrypto.so", "libadb_pairing_auth.so", "libadb_pairing_connection.so"):
            for src in ("/apex/com.android.adbd/lib64/" + fn, "/system/lib64/" + fn):
                if os.path.exists(src):
                    shutil.copy2(src, d + "/" + fn); break
        return os.path.exists(d + "/libcrypto.so")
    except Exception as e:
        print("[adb] libs copy warning:", e, file=sys.stderr)
        return False

_ensure_libs()
if not os.path.exists(LIBCRYPT): LIBCRYPT = "/system/lib64/libcrypto.so"

A_VERSION = 0x01000001
A_CNXN, A_AUTH, A_OPEN, A_OKAY, A_CLSE, A_WRTE = 0x4e584e43, 0x48545541, 0x4e45504f, 0x59414b4f, 0x45534c43, 0x45545257
AUTH_TOKEN, AUTH_SIGNATURE, AUTH_RSAPUBLICKEY = 1, 2, 3

def _alarm(s,f): print("[TIMEOUT 40s]",flush=True); os._exit(2)
signal.signal(signal.SIGALRM, _alarm); signal.alarm(40)

class Adb:
    def __init__(self, host="127.0.0.1", port=None):
        # ★ AUTO-DETECTIE PORT: citesc service.adb.tcp.port (orice port foloseste adbd)
        if port is None:
            port = 5555
            try:
                import subprocess as _sp
                out = _sp.run(["getprop", "service.adb.tcp.port"], capture_output=True, text=True, timeout=5).stdout.strip()
                if out.isdigit() and int(out) > 0:
                    port = int(out)
                else:
                    # fallback: caut porturi adbd active
                    for p in (5555, 55555, 5556):
                        try:
                            import socket as _s
                            t = _s.socket(); t.settimeout(0.5); t.connect(("127.0.0.1", p)); t.close()
                            port = p; break
                        except Exception:
                            pass
            except Exception:
                pass
            print("[adb] port detectat: " + str(port), flush=True)
        self.host, self.port = host, port; self.s=None; self.banner=""; self.lid=0
    def _send(self, cmd, a0, a1, data=b""):
        h = struct.pack("<6I", cmd, a0, a1, len(data), sum(data)&0xffffffff, cmd ^ 0xffffffff)
        self.s.sendall(h+data)
    def _recv(self, t=10):
        self.s.settimeout(t); h=b""
        while len(h)<24:
            c=self.s.recv(24-len(h))
            if not c: raise RuntimeError("closed")
            h+=c
        cmd,a0,a1,ln,cs,mg = struct.unpack("<6I",h)
        d=b""
        while len(d)<ln:
            c=self.s.recv(min(65536,ln-len(d)))
            if not c: break
            d+=c
        return cmd,a0,a1,d
    def connect(self):
        self.s = socket.create_connection((self.host,self.port), timeout=8)
        print("[adb] TCP conectat", flush=True)
        self._send(A_CNXN, A_VERSION, 256*1024, b"host::features=shell_v2,cmd,stat_v2\0")
        while True:
            cmd,a0,a1,d = self._recv(10)
            if cmd == A_CNXN:
                self.banner = d.decode(errors="replace").split("\0")[0]
                print("[adb] ✓ AUTORIZAT:", self.banner[:70], flush=True); return True
            elif cmd == A_AUTH and a0 == AUTH_TOKEN:
                # ★ trimit DIRECT publickey (nu semnez)
                pub = open(PUBC,"rb").read().strip()+b"\0"
                print("[adb] AUTH -> trimit RSAPUBLICKEY", len(pub), "bytes", flush=True)
                self._send(A_AUTH, AUTH_RSAPUBLICKEY, 0, pub)
            else:
                raise RuntimeError("neasteptat %#x a0=%d" % (cmd,a0))
    def shell(self, cmd, timeout=15):
        self.lid += 1; lid=self.lid
        self._send(A_OPEN, lid, 0, ("shell,v2,raw:"+cmd).encode()+b"\0")
        out=b""; end=time.time()+timeout
        while time.time()<end:
            try: c,a0,a1,d = self._recv(max(1,int(end-time.time())))
            except socket.timeout: break
            if c == A_OKAY: pass
            elif c == A_WRTE:
                if a0 != 0 and d:
                    if d[0] in (1,2) and len(d)>5: out += d[5:]
                    else: out += d
                self._send(A_OKAY, lid, 0)
            elif c == A_CLSE: break
        return out.decode(errors="replace")

if __name__ == "__main__":
    a = Adb(); a.connect()
    for c in ["id", "getprop ro.product.model"]:
        print(f"\n$ {c}\n{a.shell(c)}", flush=True)
