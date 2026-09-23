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

def _rsa_sign_token(token):
    """Semneaza token-ul adbd cu cheia privata (RSA PKCS#1 v1.5 SHA1) - EXACT ce
    asteapta protocolul ADB. Fara asta, un adbd care are DEJA cheia in user_keys
    nu raspunde la RSAPUBLICKEY (cerinta: dovada ca ai cheia privata).

    Se foloseste libcrypto (OpenSSL) prin ctypes. Returneaza semnatura bytes.
    """
    c = ctypes.CDLL(LIBCRYPT, mode=ctypes.RTLD_GLOBAL)
    def S(n, a, r):
        f = getattr(c, n); f.argtypes = a; f.restype = r
    S("BIO_new_file", [ctypes.c_char_p, ctypes.c_char_p], ctypes.c_void_p)
    S("BIO_free", [ctypes.c_void_p], ctypes.c_int)
    S("PEM_read_bio_PrivateKey", [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p], ctypes.c_void_p)
    S("EVP_PKEY_get0_RSA", [ctypes.c_void_p], ctypes.c_void_p)
    S("RSA_sign", [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint, ctypes.c_char_p,
                   ctypes.POINTER(ctypes.c_uint), ctypes.c_void_p], ctypes.c_int)
    S("EVP_sha1", [], ctypes.c_void_p)
    b = c.BIO_new_file(KEY.encode(), b"r")
    if not b:
        raise RuntimeError("nu pot deschide adbkey")
    try:
        pkey = c.PEM_read_bio_PrivateKey(b, None, None, None)
    finally:
        c.BIO_free(b)
    if not pkey:
        raise RuntimeError("cheia privata nu se poate citi")
    rsa = c.EVP_PKEY_get0_RSA(pkey)
    if not rsa:
        raise RuntimeError("nu e cheie RSA")
    # ★ EXACT CA IN AOSP (client/auth.cpp: adb_auth_sign):
    #     RSA_sign(NID_sha1, token, token_size, sig, &len, key)
    # Token-ul se trimite BRUT (RSA_sign face el SHA1+PKCS#1 v1.5 intern).
    # NID_sha1 = 64 in OpenSSL.
    S("RSA_sign", [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint, ctypes.c_char_p,
                   ctypes.POINTER(ctypes.c_uint), ctypes.c_void_p], ctypes.c_int)
    sig = ctypes.create_string_buffer(4096)
    slen = ctypes.c_uint(0)
    rc = c.RSA_sign(64, token, len(token), sig, ctypes.byref(slen), rsa)   # 64 = NID_sha1
    if rc != 1:
        raise RuntimeError("RSA_sign a esuat (rc=%d)" % rc)
    return sig.raw[:slen.value]


A_VERSION = 0x01000001
A_CNXN, A_AUTH, A_OPEN, A_OKAY, A_CLSE, A_WRTE = 0x4e584e43, 0x48545541, 0x4e45504f, 0x59414b4f, 0x45534c43, 0x45545257
AUTH_TOKEN, AUTH_SIGNATURE, AUTH_RSAPUBLICKEY = 1, 2, 3

# SIGALRM global: omoara procesul dupa N secunde (protectie anti-agatare).
# Configurabil prin ADB_GLOBAL_TIMEOUT (0 = dezactivat). Default 600s (10 min),
# nu 40s: bootstrap-ul toolchain-ului dureaza minute intregi.
_GT = int(os.environ.get("ADB_GLOBAL_TIMEOUT", "600") or "600")
def _alarm(s,f):
    print("[GLOBAL TIMEOUT %ss]" % _GT, flush=True); os._exit(2)
if _GT > 0:
    signal.signal(signal.SIGALRM, _alarm); signal.alarm(_GT)

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
    def close(self):
        """Inchide conexiunea curat."""
        try:
            if self.s:
                self.s.close()
        except Exception:
            pass
        self.s = None

    def connect(self):
        self.s = socket.create_connection((self.host,self.port), timeout=8)
        # ★ KEEPALIVE: tine socket-ul viu intre comenzi (fara el, adbd inchide
        # conexiunea idle si urmatorul apel face reconnect -> dialog nou "Allow")
        try:
            self.s.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            self.s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            if hasattr(socket, "TCP_KEEPIDLE"):
                self.s.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 30)
                self.s.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 10)
                self.s.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 6)
        except Exception:
            pass
        print("[adb] TCP conectat", flush=True)
        self._send(A_CNXN, A_VERSION, 256*1024, b"host::features=shell_v2,cmd,stat_v2\0")
        _auth_left = 3          # ★ anti-bucla: adbd retrimite AUTH_TOKEN daca semnatura e rea
        while True:
            cmd,a0,a1,d = self._recv(10)
            if cmd == A_CNXN:
                self.banner = d.decode(errors="replace").split("\0")[0]
                print("[adb] ✓ AUTORIZAT:", self.banner[:70], flush=True); return True
            elif cmd == A_AUTH and a0 == AUTH_TOKEN:
                # ★ ORDINEA CORECTA (protocol ADB):
                #   1. daca avem cheia privata si cheia e DEJA autorizata ->
                #      trimitem AUTH_SIGNATURE (dovada ca avem cheia privata).
                #      adbd raspunde IMEDIAT cu CNXN.
                #   2. daca nu avem cheie privata SAU semnarea esueaza ->
                #      trimitem AUTH_RSAPUBLICKEY (adbd afiseaza dialogul Allow).
                # Fara pasul 1, un adbd care are deja cheia in user_keys NU
                # raspunde la RSAPUBLICKEY -> timeout (bug real).
                # ★ ORDINEA CARE MERGE (verificat pe device):
                # 1. RSAPUBLICKEY cu cheia in formatul ANDROID_PUBKEY (524 bytes,
                #    ca a cheii adb standard) -> adbd o valideaza si autorizeaza.
                #    (Cheia in formatul vechi de 267 B -> "Invalid base64 key".)
                # 2. fallback: SIGNATURE (pentru adbd care au deja cheia salvata)
                pub = open(PUBC,"rb").read().strip()+b"\0"
                try:
                    print("[adb] AUTH -> trimit RSAPUBLICKEY", len(pub), "bytes", flush=True)
                    self._send(A_AUTH, AUTH_RSAPUBLICKEY, 0, pub)
                except Exception as e:
                    print("[adb] pubkey send err:", str(e)[:60], flush=True)
                    if os.path.exists(KEY):
                        sig = _rsa_sign_token(d)
                        print("[adb] AUTH -> trimit SIGNATURE", len(sig), "bytes", flush=True)
                        self._send(A_AUTH, AUTH_SIGNATURE, 0, sig)
                _auth_left -= 1
                if _auth_left <= 0:
                    raise RuntimeError("adbd a respins autorizarea (3 incercari) - "
                                       "accepta dialogul 'Allow USB debugging' pe telefon "
                                       "sau ruleaza: adb tcpip 1234 de pe PC")
            else:
                raise RuntimeError("neasteptat %#x a0=%d" % (cmd,a0))
    def shell(self, cmd, timeout=15):
        """Ruleaza o comanda shell. La iesire INCHIDE INTOTDEAUNA sesiunea
        (A_CLSE), altfel adbd pastreaza stream-ul deschis si urmatorul apel
        primeste raspunsuri amestecate / se blocheaza (bug real: conexiuni
        TIME_WAIT + timeout-uri de 30-60s la tot ce trecea prin adbsh)."""
        self.lid += 1; lid=self.lid
        self._send(A_OPEN, lid, 0, ("shell,v2,raw:"+cmd).encode()+b"\0")
        out=b""; end=time.time()+timeout; closed=False; timed_out=False
        try:
            while time.time()<end:
                try: c,a0,a1,d = self._recv(max(1,int(end-time.time())))
                except socket.timeout:
                    timed_out=True; break
                except Exception:
                    break
                if c == A_OKAY: pass
                elif c == A_WRTE:
                    if a0 != 0 and d:
                        if d[0] in (1,2) and len(d)>5: out += d[5:]
                        else: out += d
                    try: self._send(A_OKAY, lid, 0)
                    except Exception: break
                elif c == A_CLSE:
                    closed=True; break
        finally:
            # ★ inchidem sesiunea DOAR daca nu s-a inchis deja singura
            if not closed:
                try: self._send(A_CLSE, lid, 0)
                except Exception: pass
                # drenare: consumam pachetele rămase ale acestei sesiuni ca sa nu
                # se amestece cu raspunsul urmatoarei comenzi
                try:
                    self.s.settimeout(0.4)
                    for _ in range(64):
                        try: self._recv(0.3)
                        except Exception: break
                except Exception:
                    pass
        txt = out.decode(errors="replace")
        # ★ curat artefactele protocolului shell_v2 (ex. "\x03\x01\x00\x00\x00\x00"
        # ramase la finalul fiecarui raspuns) - altfel agentul vede "output amestecat"
        txt = txt.replace("\x03\x01\x00\x00\x00\x00", "").rstrip("\x00")
        if timed_out and not txt.strip():
            txt = "[adb] comanda a depasit %ss (procesul poate continua in fundal)" % int(timeout)
        return txt

    def ping(self):
        """Verifica daca sesiunea adb e inca sanatoasa (fara sa lase reziduuri)."""
        try:
            r = self.shell("echo __PING__", 5)
            return "__PING__" in r
        except Exception:
            return False

if __name__ == "__main__":
    a = Adb(); a.connect()
    for c in ["id", "getprop ro.product.model"]:
        print(f"\n$ {c}\n{a.shell(c)}", flush=True)
