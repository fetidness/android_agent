#!/usr/bin/env python3
"""ADB client pur Python -> adbd 127.0.0.1:5555. Trimite RSAPUBLICKEY direct."""
import socket, struct, os, sys, time, ctypes, signal
import threading

# ★ FIX (output gol intermitent - cauza RADACINA): ACELASI socket ADB e folosit de
# mai multe thread-uri (agentul in thread-ul principal + bootstrap-ul toolchain pe un
# thread secundar, ambele prin shared()). Fara serializare, doua shell()-uri se pot
# suprapune pe acelasi socket: unul citeste pachetele celuilalt -> protocol desync ->
# COMENZI CARE IES GOALE fara nicio eroare (simptomul raportat de operator).
# Solutie: un Lock global care serialzeaza ORICE operatie pe socket (shell/ping/_drain).
_SOCK_LOCK = threading.RLock()

F = "/data/data/net.sys32.agent/files"
# ★ FAZA 4q: preferam cheia OPERATORULUI (op_adbkey), deja autorizata pe device: adb_setup.py
# poate regenera files/adbkey, iar o cheie noua nu e autorizata -> adbd cere dialog si adbsh
# da timeout. Cu op_adbkey, autentificarea prin AUTH_SIGNATURE merge din prima.
_OPK = F + "/op_adbkey"; _OPP = F + "/op_adbkey.pub"
KEY = _OPK if os.path.exists(_OPK) else F + "/adbkey"
PUBC = _OPP if os.path.exists(_OPP) else F + "/adbkey.pub"
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

def _rsa_key_parts(priv=True):
    """(n, e) - intregi - din adbkey (PEM) prin libcrypto; daca priv=True si (n, d).
       Nu depinde de RSA_sign/EVP (BoringSSL poate refuza SHA-1)."""
    c = ctypes.CDLL(LIBCRYPT, mode=ctypes.RTLD_GLOBAL)
    def S(n, a, r):
        f = getattr(c, n); f.argtypes = a; f.restype = r
    S("BIO_new_file", [ctypes.c_char_p, ctypes.c_char_p], ctypes.c_void_p)
    S("BIO_free", [ctypes.c_void_p], ctypes.c_int)
    S("PEM_read_bio_PrivateKey", [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p],
      ctypes.c_void_p)
    # ★ OBLIGATORIU: PEM_read_bio_PrivateKey intoarce un EVP_PKEY*, iar RSA_get0_key cere un RSA*.
    #   Fara EVP_PKEY_get0_RSA, BoringSSL trateaza structura EVP_PKEY ca RSA si citeste pointeri
    #   din ea -> SIGSEGV (dovedit pe device: "Fatal signal 11 ... fault addr 0x8648...").
    S("EVP_PKEY_get0_RSA", [ctypes.c_void_p], ctypes.c_void_p)
    S("RSA_get0_key", [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p),
                       ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_void_p)], None)
    S("BN_num_bits", [ctypes.c_void_p], ctypes.c_int)
    S("BN_bn2bin", [ctypes.c_void_p, ctypes.c_char_p], ctypes.c_int)
    b = c.BIO_new_file(KEY.encode(), b"r")
    if not b:
        raise RuntimeError("cannot open adbkey")
    try:
        pkey = c.PEM_read_bio_PrivateKey(b, None, None, None)
    finally:
        c.BIO_free(b)
    if not pkey:
        raise RuntimeError("the private key cannot be read")
    rsa = c.EVP_PKEY_get0_RSA(pkey)
    if not rsa:
        raise RuntimeError("not an RSA key")
    nb_ = ctypes.c_void_p(); eb_ = ctypes.c_void_p(); db_ = ctypes.c_void_p()
    c.RSA_get0_key(rsa, ctypes.byref(nb_), ctypes.byref(eb_), ctypes.byref(db_))
    if not nb_:
        raise RuntimeError("not an RSA key")
    def _int(bn):
        size = (c.BN_num_bits(bn) + 7) // 8
        buf = ctypes.create_string_buffer(size)
        c.BN_bn2bin(bn, buf)
        return int.from_bytes(buf.raw[:size], "big")
    n = _int(nb_); e = _int(eb_)
    if priv:
        return n, e, _int(db_)
    return n, e

# Prefixul DER al DigestInfo pentru SHA-1 (RFC 8017, PKCS#1 v1.5).
_SHA1_DIGESTINFO = bytes.fromhex("3021300906052b0e03021a05000414")

def _rsa_sign_token_manual(token):
    """Semnatura RSA PKCS#1 v1.5 SHA-1 calculata MANUAL (EM^d mod n cu BN_mod_exp).
       ★ DE CE: `RSA_sign(NID_sha1, ...)` prin libcrypto de SISTEM (BoringSSL) poate fi
       refuzat/limitat pentru SHA-1 -> adbd primea o semnatura invalida, raspundea iar cu
       AUTH_TOKEN si afisa dialogul 'Allow USB debugging' la INFINIT (fiecare conexiune)."""
    import hashlib
    n, e, d = _rsa_key_parts(priv=True)
    k = (n.bit_length() + 7) // 8
    h = hashlib.sha1(token).digest()
    di = _SHA1_DIGESTINFO + h
    if k < len(di) + 11:
        raise RuntimeError("key too small for PKCS#1 v1.5")
    em = b"\x00\x01" + b"\xff" * (k - 3 - len(di)) + b"\x00" + di
    return pow(int.from_bytes(em, "big"), d, n).to_bytes(k, "big")

def _rsa_verify_token(token, sig):
    """Verifica semnatura cu cheia publica (sig^e mod n == EM). Fara asta nu trimitem nimic."""
    import hashlib
    n, e = _rsa_key_parts(priv=False)
    k = (n.bit_length() + 7) // 8
    if not sig or len(sig) != k:
        return False
    em = pow(int.from_bytes(sig, "big"), e, n).to_bytes(k, "big")
    di = _SHA1_DIGESTINFO + hashlib.sha1(token).digest()
    return em.endswith(di) and em[:2] == b"\x00\x01" and em[k - len(di) - 1] == 0

def _rsa_sign_token(token):
    """Semneaza token-ul adbd (RSA PKCS#1 v1.5 SHA1) - EXACT ce asteapta protocolul ADB.

    ★ NU folosim `RSA_sign` din libcrypto de SISTEM (BoringSSL): pe acest device
    (SM-A366B / Android 16) apelul cu SHA-1 fie esueaza (rc!=1), fie TERMINA PROCESUL
    (abort in BoringSSL - "proces terminat" + restart de watchdog, dovedit pe device).
    Efectul vechi: aplicatia nu putea NICIODATA sa semneze -> trimitea doar cheia publica ->
    adbd afisa dialogul 'Allow USB debugging' la fiecare conexiune, la infinit, iar adbsh/
    install nu functionau niciodata.

    Implementarea manuala (PKCS#1 v1.5 + exponent modulo n, pur Python + BN pentru n/d) a fost
    verificata cu `openssl dgst -sha1 -verify` -> "Verified OK", si se auto-verifica inainte de
    a fi trimisa.
    """
    sig = _rsa_sign_token_manual(token)
    if not _rsa_verify_token(token, sig):
        raise RuntimeError("our own signature does not verify - not sending it")
    return sig


def _rsa_sign_token_libcrypto(token):
    """Calea clasica (RSA_sign/NID_sha1). PASTRATA DOAR CA REFERINTA - nu se apeleaza:
    pe BoringSSL poate aborta procesul (vezi docstring-ul de mai sus)."""
    c = ctypes.CDLL(LIBCRYPT, mode=ctypes.RTLD_GLOBAL)
    def S(n, a, r):
        f = getattr(c, n); f.argtypes = a; f.restype = r
    S("BIO_new_file", [ctypes.c_char_p, ctypes.c_char_p], ctypes.c_void_p)
    S("BIO_free", [ctypes.c_void_p], ctypes.c_int)
    S("PEM_read_bio_PrivateKey", [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p], ctypes.c_void_p)
    S("EVP_PKEY_get0_RSA", [ctypes.c_void_p], ctypes.c_void_p)
    S("RSA_sign", [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint, ctypes.c_char_p,
                   ctypes.POINTER(ctypes.c_uint), ctypes.c_void_p], ctypes.c_int)
    b = c.BIO_new_file(KEY.encode(), b"r")
    if not b:
        raise RuntimeError("cannot open adbkey")
    try:
        pkey = c.PEM_read_bio_PrivateKey(b, None, None, None)
    finally:
        c.BIO_free(b)
    if not pkey:
        raise RuntimeError("the private key cannot be read")
    rsa = c.EVP_PKEY_get0_RSA(pkey)
    if not rsa:
        raise RuntimeError("not an RSA key")
    sig = ctypes.create_string_buffer(4096)
    slen = ctypes.c_uint(0)
    rc = c.RSA_sign(64, token, len(token), sig, ctypes.byref(slen), rsa)   # 64 = NID_sha1
    if rc != 1:
        raise RuntimeError("RSA_sign failed (rc=%d)" % rc)
    return sig.raw[:slen.value]


A_VERSION = 0x01000001
A_CNXN, A_AUTH, A_OPEN, A_OKAY, A_CLSE, A_WRTE = 0x4e584e43, 0x48545541, 0x4e45504f, 0x59414b4f, 0x45534c43, 0x45545257
AUTH_TOKEN, AUTH_SIGNATURE, AUTH_RSAPUBLICKEY = 1, 2, 3

# SIGALRM global (protectie anti-agatare) - DOAR LA CERERE, nu la import.
#
# ISTORIC: versiunea veche arma un signal.alarm(600) LA IMPORT. Efectul: ORICE proces
# care importa adb_client murea dupa 10 min, chiar daca nu era blocat (ex. o sesiune
# lunga de lucru normala). Operatorul primea "[GLOBAL TIMEOUT 600s]" si procesul se
# oprea, desi nimic nu era agatat. Alarm-ul global e o plasa de siguranta pentru
# operatii LUNGI si RISCANTE (build, bootstrap, pip install), nu o limita de viata
# a procesului.
#
# DESIGN NOU (inteligent):
#   - la import NU se armeaza nimic (un proces normal traieste cat are nevoie);
#   - daca ADB_GLOBAL_TIMEOUT e setat EXPLICIT in mediu, se respecta (backward compat);
#   - operatiile lungi isi armeaza singure limita via arm_global_timeout(sec), si o
#     pot reimprospata cu touch_global_timeout() (fiecare progres = inca `sec` secunde)
#     sau o pot scoate cu disarm_global_timeout().
#
# ★ SIGALRM merge DOAR in thread-ul principal: armarea dintr-un thread secundar
# (ex. bootstrap-ul toolchain-ului ruleaza pe un thread) ar arunca
# "signal only works in main thread" -> de aceea functiile de mai jos sunt no-op
# sigure pe thread-uri secundare (socket-ul are oricum propriul timeout per comanda).
import threading as _thr

def _alarm(s, f):
    print("[GLOBAL TIMEOUT %ss]" % _GT[0], flush=True)
    os._exit(2)

_GT = [0]          # valoarea curenta (0 = dezarmat); lista = mutabila in closure

def _arm(sec):
    """Armeaza (sau rearma) alarm-ul global la `sec` secunde. No-op pe thread secundar."""
    if sec <= 0:
        return False
    if _thr.current_thread() is not _thr.main_thread():
        return False          # SIGALRM nu functioneaza in afara thread-ului principal
    try:
        _GT[0] = int(sec)
        signal.signal(signal.SIGALRM, _alarm)
        signal.alarm(int(sec))
        return True
    except Exception:
        return False

def arm_global_timeout(sec):
    """Armeaza un SIGALRM global de `sec` secunde (protectie anti-agatare pentru
    operatii LUNGI: build, bootstrap, pip install). Returneaza True daca s-a armat."""
    return _arm(sec)

def touch_global_timeout(sec=None):
    """Reimprospateaza alarm-ul global (fiecare progres = inca `sec` secunde, implicit
    valoarea curenta). De apelat in buclele lungi, ca sa NU expire cat progreseaza."""
    s = sec if sec is not None else _GT[0]
    if s and s > 0:
        return _arm(s)
    return False

def disarm_global_timeout():
    """Scoate alarm-ul global (procesul poate trai nelimitat de aici inainte)."""
    try:
        if _thr.current_thread() is _thr.main_thread():
            signal.alarm(0)
    except Exception:
        pass
    _GT[0] = 0

# Backward compat: DOAR daca e setat explicit in mediu (nu mai exista default 600).
_env_gt = os.environ.get("ADB_GLOBAL_TIMEOUT")
if _env_gt is not None and _env_gt.strip() != "":
    try:
        _v = int(_env_gt)
    except Exception:
        _v = 0
    if _v > 0:
        _arm(_v)

# ============================================================================
# CONEXIUNE PARTEJATA (module-level singleton)
#
# PROBLEMA REALA: fiecare apel `Adb().connect()` deschide o conexiune NOUA.
# adbd cere aprobarea "Allow USB debugging" pentru fiecare cheie/sesiune noua
# in anumite conditii -> dialogul reapare la fiecare comanda!
# (toolchain._sh() facea connect()+close() la FIECARE apel -> dialog non-stop.)
#
# SOLUTIA: o singura conexiune, refolosita de toti consumatorii din proces.
# ============================================================================
_SHARED = None          # instanta Adb partajata
_SHARED_PID = None      # pid-ul procesului care a creat-o (nu refolosim intre procese)


def shared(host="127.0.0.1", port=None, auto=True):
    """Returneaza conexiunea ADB partajata, creand-o la prima folosire.

    Reutilizeaza socket-ul daca e viu; reconecteaza DOAR daca e mort.
    Astfel adbd vede O SINGURA sesiune -> un singur dialog 'Allow'.
    """
    global _SHARED, _SHARED_PID
    # ★ FAZA 4z-B (SERIALIZARE HANDSHAKE - dovedit pe device): shared() NU era sub _SOCK_LOCK,
    # deci doua thread-uri care o chemau simultan la pornire (a11y_selfheal + primul tool)
    # vedeau amandoua `_SHARED is None` si deschideau CATE O CONEXIUNE -> DOUA dialoguri
    # "Allow USB debugging" (simptomul raportat: "ma intreaba, ii dau allow, ma intreaba iar").
    # Acum totul (inclusiv connect()) e sub lock: un singur handshake, un singur Allow.
    with _SOCK_LOCK:
        return _shared_locked(host, port, auto)


def _shared_locked(host="127.0.0.1", port=None, auto=True):
    global _SHARED, _SHARED_PID
    pid = os.getpid()
    if _SHARED_PID != pid:
        _SHARED = None
        _SHARED_PID = pid
    # ★ FIX adbfix-3 (cauza principala a starii 'alterate'): inainte conditia era doar
    # `_SHARED.s is not None`, deci o instanta cu socket mort dar atribuit ramanea in cache
    # si TOATE apelurile urmatoare refoloseau acelasi obiect rupt - fara nicio reincercare,
    # pana la revoke manual. Acum verificam si un flag explicit `closed`.
    if _SHARED is not None and _SHARED.s is not None and not getattr(_SHARED, "closed", False):
        # ★ FAZA 4z-A (conexiuni FANTOMA, dovedite pe device): o conexiune poate ramane
        # ESTABLISHED cu date NECITITE in queue (44 B = raspunsul de autorizare al adbd) dupa
        # ce handshake-ul a fost abandonat (ex. dialogul "Allow" a venit prea tarziu pentru
        # timeout-ul vechi). Un astfel de socket NU e "viu" desi select() zice ca are date:
        # il refolosim => comanda urmatoare citeste restul handshake-ului si iese GUNOI.
        # De aceea: daca are date in queue, fac un ping REAL; daca nu raspunde, il inchid
        # CURAT (nu il las in ESTAB ca fantoma) si deschid unul nou.
        try:
            import select as _sel
            r, _, _ = _sel.select([_SHARED.s], [], [], 0)
            if r:
                peek = _SHARED.s.recv(1, 0x02)     # MSG_PEEK
                if peek == b"":
                    _SHARED = None                  # EOF real
                else:
                    # date in queue: fie un raspuns real de citit, fie un handshake abandonat.
                    # Test ieftin: incerc un ping; daca iese prost, conexiunea e fantoma.
                    try:
                        if not _SHARED.ping():
                            _SHARED.close()
                            _SHARED = None
                    except Exception:
                        try: _SHARED.close()
                        except Exception: pass
                        _SHARED = None
        except BlockingIOError:
            pass                                    # EAGAIN: e viu
        except Exception:
            _SHARED = None
    if _SHARED is None:
        _obj = Adb(host=host, port=port)
        if auto:
            try:
                _obj.connect()
            except Exception:
                # ★ nu pastra in cache o conexiune rupta: altfel TOATE apelurile urmatoare
                # refoloseau acelasi obiect si dadeau acelasi timeout (raportat: "adbsh nu merge")
                try:
                    _obj.close()
                except Exception:
                    pass
                raise
        _SHARED = _obj
    return _SHARED


def _demux_shellv2(buf):
    """Demultiplexeaza fluxul `shell,v2,raw`.

    Formatul: o secventa de [1 byte stream][4 bytes little-endian length][payload], unde
    stream 1 = stdout, 2 = stderr, 3 = exit code (0 = stdin, ignorat).
    Intr-un singur pachet A_WRTE pot veni MAI multe astfel de cadre, iar un cadru poate fi spart
    pe doua pachete - de aceea parsarea se face pe fluxul complet, nu pe pachet (vechea varianta
    presupunea un singur header per pachet si lasa header-ele interioare in output: agentul vedea
    "\x01\x0b\x00\x00\x00", "\x02...", "\x03\x01\x00\x00\x00\x01" ca 'gunoi binar').
    Daca datele nu incep cu un header valid, se intoarce brut (compatibilitate).
    """
    i = 0
    n = len(buf)
    parts = []
    while i + 5 <= n:
        sid = buf[i]
        ln = int.from_bytes(buf[i + 1:i + 5], "little")
        if sid not in (0, 1, 2, 3) or ln > (64 << 20):
            return buf if not parts else b"".join(parts)
        if i + 5 + ln > n:
            if sid in (1, 2):
                parts.append(buf[i + 5:])
            break
        if sid in (1, 2):
            parts.append(buf[i + 5:i + 5 + ln])
        i += 5 + ln
    return b"".join(parts)


def close_shared():
    """Inchide conexiunea partajata (la iesirea din proces, nu intre comenzi)."""
    global _SHARED
    if _SHARED is not None:
        try:
            _SHARED.close()
        except Exception:
            pass
        _SHARED = None


def force_reconnect():
    """★ AUTO-HEAL (fix pentru blocajele care nu se reparau singure):
    inchide socket-ul partajat si deschide unul NOU. Folosit cand protocolul s-a
    desincronizat iremediabil (pachete malformate, reziduuri) si nicio drenare
    nu mai ajuta. O conexiune noua NU cere dialogul 'Allow' atat timp cat cheia
    e deja in user_keys ale adbd (cazul normal dupa prima autorizare)."""
    global _SHARED
    try:
        if _SHARED is not None: _SHARED.close()
    except Exception:
        pass
    _SHARED = None
    try:
        return shared()      # creeaza conexiunea noua
    except Exception:
        return None


def is_socket_healthy(timeout=3):
    """Test rapid: trimite 'echo' si verifica daca raspunsul e curat.
    Returneaza True/False fara sa arunce."""
    try:
        a = shared()
        if a is None or a.s is None: return False
        r = a.shell("echo __HEALTH__", timeout)
        return "__HEALTH__" in r
    except Exception:
        return False


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
                    for p in (5555, 55555, 5556, 1234):
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
        self._poisoned = False   # ★ setat cand protocolul s-a desincronizat (vezi _drain_locked)
    def _send(self, cmd, a0, a1, data=b""):
        h = struct.pack("<6I", cmd, a0, a1, len(data), sum(data)&0xffffffff, cmd ^ 0xffffffff)
        # ★ FIX adbfix-1 (dovedit pe device): dupa close() sau dupa ce adbd a cazut,
        # self.s ramane None si FECARE apel urmator murea cu
        # AttributeError: 'NoneType' object has no attribute 'sendall' - la infinit,
        # fara nicio reincercare (simptomul 'ADB ramane alterat pana la revoke').
        # Acum: reconectez transparent o singura data.
        if self.s is None:
            self.connect()
            return self._send(cmd, a0, a1, data)
        try:
            self.s.sendall(h+data)
        except (BrokenPipeError, ConnectionResetError, OSError):
            self.close()
            raise
    def _recv(self, t=10):
        # ★ FIX adbfix-2: self.s poate fi None (dupa close/force_reconnect) sau poate muri
        # in timpul citirii. Inainte: AttributeError / blocare fara reconectare.
        if self.s is None:
            raise ConnectionError("adb socket closed")
        self.s.settimeout(t); h=b""
        while len(h)<24:
            try:
                c=self.s.recv(24-len(h))
            except socket.timeout:
                # ★ FIX adbfix-7 (DOVEDIT prin urmarirea pachetelor): socket.timeout NU este o
                # eroare de retea - comanda pur si simplu nu a terminat in bugetul dat si
                # sesiunea adbd e INCA VALIDA. Inainte orice exceptie inchidea socket-ul,
                # ceea ce forta un reconnect complet (3 handshake-uri) pentru FIECARE timeout.
                # Acum timeout-ul se propaga NESCHIMBAT, iar socket-ul ramane deschis.
                raise
            except OSError as e:
                self.close()
                raise ConnectionError(f"adb recv failed: {e}")
            if not c:
                self.close()
                raise RuntimeError("closed")
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
        # ★ FIX adbfix-3b: marcaj explicit, ca shared() sa NU mai refoloseasca un socket inchis.
        self.closed = True
        try:
            if self.s:
                self.s.close()
        except Exception:
            pass
        self.s = None

    def connect(self):
        # ★ FIX adbfix-4: o conexiune NOUA nu mai e "closed" - altfel shared() ar
        # arunca imediat obiectul proaspat creat si ar reconecta la infinit.
        self.closed = False
        # ★ FIX adbfix-5 (DOVEDIT pe device): _auth_tries se acumula pe OBIECT si nu era
        # resetat la reconectare. Dupa primul close()/reconnect, contorul era deja 1, deci
        # handshake-ul sarea PESTE AUTH_RSAPUBLICKEY (singura cale care merge pe acest adbd)
        # si trimitea doar AUTH_SIGNATURE -> "adbd did not accept the authorisation" la
        # infinit, desi cheia era perfect valida. Reset obligatoriu pe fiecare connect().
        self._auth_tries = 0
        self.s = socket.create_connection((self.host,self.port), timeout=8)
        # ★ FIX adbfix-9 (BLOCAJ IMPOSIBIL DE OCOLIT, dovedit pe device): un `recv()`
        # blocant NU poate fi intrerupt din Python (settimeout se poate reseta, iar
        # ThreadPoolExecutor.shutdown(wait=False) lasa thread-ul agatat in do_poll).
        # Cand o comanda ca `htop` lasa sesiunea adbd deschisa, TOATE comenzile
        # urmatoare se blocau in futex_wait. SO_RCVTIMEO e aplicat de KERNEL, deci
        # recv() ridica socket.timeout garantat, indiferent de settimeout() ulterior.
        try:
            import struct as _st
            _tv = _st.pack("ll", 120, 0)   # 120s limita absoluta de citire
            self.s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVTIMEO, _tv)
            self.s.setsockopt(socket.SOL_SOCKET, socket.SO_SNDTIMEO, _tv)
        except Exception:
            pass
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
        _auth_left = 1          # ★ FAZA 4y: UNA singura. Cu 3, fiecare retry pe acelasi socket
                                # agrava dialogul (adbd retrimite token; noi raspundeam din nou).
        while True:
            # ★ FIX (testul din UI: "adbsh nu merge, uid 2000"): cand cheia aplicatiei nu e
            # autorizata, adbd AFISEAZA DIALOGUL si nu raspunde -> _recv iesea in timeout si
            # agentul primea doar "TimeoutError" sec. Acum = aprobare in asteptare, cu instructiuni.
            try:
                # ★ FAZA 4y: TIMEOUT LUNG pentru aprobare. Vechiul _recv(10) expira in 10 s,
                # iar shared() reconecta la fiecare esec -> FIECARE reconnect deschidea un dialog
                # "Allow USB debugging" NOU (simptomul raportat: 5 apasari la rand). Aprobarea
                # umana poate lua 30-60 s, deci asteptam 120 s inainte sa renuntam - o singura
                # fereastra de aprobare, nu 5.
                cmd,a0,a1,d = self._recv(120)
            except socket.timeout:
                raise RuntimeError(
                    "adbd is WAITING FOR the app key to be APPROVED: accept the 'Allow USB "
                    "debugging' dialog on the phone (if it does not appear: Developer options -> disable and "
                    "re-enable USB debugging or Wireless debugging, then Allow with 'Always allow'; "
                    "from a PC you can also run 'adb tcpip 5555')")
            if cmd == A_CNXN:
                self.banner = d.decode(errors="replace").split("\0")[0]
                print("[adb] ✓ AUTORIZAT:", self.banner[:70], flush=True); return True
            elif cmd == A_AUTH and a0 == AUTH_TOKEN:
                # ★ FAZA 4n - ORDINEA CARE MERGE (verificat pe device, 2026-10-01):
                # adbd trimite AUTH_TOKEN si ASTEAPTA o dovada. Sunt doua cai:
                #   (1) AUTH_SIGNATURE   - semnam token-ul cu cheia privata (RSA PKCS#1v1.5/SHA1,
                #       exact ca adb_auth_sign din AOSP). Merge INSTANT cand cheia publica e deja
                #       in lista adbd (user_keys) - fara dialog, fara timeout.
                #   (2) AUTH_RSAPUBLICKEY - trimitem cheia publica ca adbd sa afiseze dialogul
                #       "Allow USB debugging". Pe acest device adbd NU raspunde la (2) cand cheia
                #       e deja autorizata: ramane mut -> timeout (simptomul "adbsh nu merge, uid
                #       2000" din testele din UI).
                # De aceea: (1) PRIMUL, (2) doar ca a doua incercare.
                _n_auth = getattr(self, "_auth_tries", 0)
                self._auth_tries = _n_auth + 1
                if _n_auth == 0:
                    # ★ FAZA 4x (DOVEDIT pe device, SM-A366B/Android 16, 2026-10-16):
                    # ORDINEA REALA e INVERSA fata de ce credea codul. Test brut (socket,
                    # urmarind fiecare pachet): AUTH_SIGNATURE -> adbd retrimite TOKEN NOU
                    # (respinse) de fiecare data, desi openssl confirma "Verified OK" si cheia
                    # privata e IDENTICA cu a adb-ului de pe PC care merge; AUTH_RSAPUBLICKEY
                    # -> A_CNXN IMEDIAT, fara dialog "Allow". De aceea: RSAPUBLICKEY PRIMA.
                    try:
                        pub = open(PUBC, "rb").read().strip() + b"\0"
                    except Exception:
                        pub = b""
                    if pub:
                        print("[adb] AUTH -> trimit RSAPUBLICKEY", len(pub), "bytes", flush=True)
                        self._send(A_AUTH, AUTH_RSAPUBLICKEY, 0, pub)
                        continue
                try:
                    _sig = _rsa_sign_token(d)
                    self._send(A_AUTH, AUTH_SIGNATURE, 0, _sig)
                    print("[adb] AUTH -> AUTH_SIGNATURE (%d bytes)" % len(_sig), flush=True)
                except Exception as _e:
                    print("[adb] semnare indisponibila (%s)" % str(_e)[:60], flush=True)
                _auth_left -= 1
                if _auth_left <= 0:
                    raise RuntimeError(
                        "adbd did not accept the authorisation (signature + public key). On the phone: "
                        "Developer options -> disable and re-enable Wireless debugging / USB "
                        "debugging and press Allow (with 'Always allow'); from a PC: adb tcpip 5555. "
                        "OR (no dialog): copy the key the operator already authorised into "
                        "files/op_adbkey + files/op_adbkey.pub - the signature is then accepted instantly.")
            else:
                raise RuntimeError("unexpected %#x a0=%d" % (cmd,a0))
    def _drain(self):
        """Empties leftovers... (serializat: vezi _SOCK_LOCK)."""
        with _SOCK_LOCK:
            return self._drain_locked()

    def _drain_locked(self):
        """Empties leftovers from ALREADY-CLOSED sessions before opening a new one.
        Safe by construction: it reads a packet ONLY when select() says data is ready, and it
        handles SHORT reads (a TCP segment may carry only part of the 24-byte header) instead of
        treating them as errors - the first version called _recv(0.2), whose small timeout turned
        a partial header into an exception, retried, and burned the whole command timeout."""
        try:
            import select as _sel
            idle = 0
            # ★ FIX (blocaj): si aceasta bucla are acum un buget TOTAL de timp, nu doar
            # numarul de citiri idle - altfel datele continue de la adbd o fac sa nu se
            # termine niciodata (acelasi bug ca la drenarea din shell()).
            _dl = time.time()+0.5
            _foreign_seen = 0
            while idle < 2 and time.time() < _dl:
                r,_,_ = _sel.select([self.s], [], [], 0.05)
                if not r:
                    idle += 1
                    continue
                _foreign_seen += 1
                # ★ AUTO-HEAL: prea multe pachete straine drenate = socket desincronizat
                # iremediabil. Il marcam ca bolnav ca shell() sa forteze reconectarea,
                # altfel comanda urmatoare mosteneste gunoiul si iese goala/blocata.
                if _foreign_seen > 8:
                    self._poisoned = True
                # read a whole packet, tolerating short reads
                try:
                    self.s.settimeout(0.3)
                    h = b""
                    while len(h) < 24:
                        c = self.s.recv(24-len(h))
                        if not c: return
                        h += c
                    cmd,a0,a1,ln,ck,mg = struct.unpack("<6I", h)
                    d = b""
                    while len(d) < ln:
                        c = self.s.recv(min(65536, ln-len(d)))
                        if not c: break
                        d += c
                except Exception:
                    return          # socket busy/unusable: leave it alone
                # FIX (output gol intermitent): confirmarea unui pachet strain trebuie sa
                # foloseasca id-urile INVERSATE (a1, a0) - exact ca in shell(). Vechiul
                # (a0, 0) lasa scriitorul strain desincronizat, adbd inchide sesiunea, iar
                # urmatoarea comanda primeste output GOL fara nicio eroare. Cand a1==0
                # (pachet care nu apartine niciunei sesiuni) raspundem totusi cu (a1,a0)
                # ca sa nu inventam un id de sesiune care nu exista.
                if cmd == A_WRTE:
                    try: self._send(A_OKAY, a1, a0)
                    except Exception: return
                elif cmd == A_CLSE:
                    try: self._send(A_CLSE, a1, a0)
                    except Exception: return
                idle = 0
        except Exception:
            pass

    def shell(self, cmd, timeout=15):
        """Wrapper SERIALIZAT: ia Lock-ul global inainte de a atinge socket-ul.
        Fara el, doua thread-uri (agentul + bootstrap toolchain) se puteau
        suprapune pe acelasi socket => protocol desync => OUTPUT GOL intermitent."""
        with _SOCK_LOCK:
            # ★ AUTO-HEAL: daca protocolul s-a desincronizat (prea multe pachete straine
            # drenate), reconectam INAINTE de a trimite comanda. Fara asta, comanda
            # mostenea gunoiul si iesea goala sau bloca drenarea.
            if getattr(self, "_poisoned", False):
                self._poisoned = False
                try:
                    self.close()
                    self.connect()
                except Exception:
                    pass
            r = self._shell_locked(cmd, timeout)
            # ★ FIX (masurat pe SM-A366B): o comanda care se termina CU SUCCES si nu
            # produce output (true, cd, mkdir, git commit -q, touch...) NU inseamna
            # socket stricat. Vechiul cod reconecta + re-executa => 485-1226 ms in loc
            # de ~45 ms (12-27x) pentru FIECARE comanda tacuta din Debian.
            # Reconectam doar daca avem motiv REAL: socket mort sau flag _poisoned.
            if r == "" and cmd.strip() and not cmd.strip().startswith("echo __MK") \
                    and not getattr(self, "_last_rc_ok", False):
                try:
                    self.close(); self.connect()
                    r2 = self._shell_locked(cmd, timeout)
                    if r2.strip(): r = r2
                except Exception:
                    pass
            return r

    def shell_unlocked(self, cmd, timeout=15):
        """Ruleaza o comanda FARA lock-ul global `_SOCK_LOCK`.

        ★ DE CE EXISTA (dovedit pe device, reprodus in izolare):
        `shell()` ia `_SOCK_LOCK` - un lock GLOBAL, nu per-conexiune. Shell-ul Debian
        (`run_in_debian` -> `_adb().shell()`) il TINE pe toata durata comenzii, deci un
        al doilea thread (bridge-ul dshell) care cheama `shell()` astepta acelasi lock
        pana la timeout -> `dshell sh` din Debian atarna cu rc=124, desi `dshell camera`
        (care nu atinge adb) mergea perfect. O conexiune ADB separata NU e suficienta:
        lock-ul era global. De aceea aici sarim peste el.

        SIGURANTA: se foloseste EXCLUSIV pe o conexiune PRIVATA (vezi `_dshell_adb`),
        cu care nu imparte socket-ul niciun alt thread. Serializarea intre thread-uri
        nu mai e necesara pentru ca nu exista concurenta pe acel socket.
        """
        if getattr(self, "_poisoned", False):
            self._poisoned = False
            try:
                self.close(); self.connect()
            except Exception:
                pass
        return self._shell_locked(cmd, timeout)

    def _shell_locked(self, cmd, timeout=15):
        """Runs ONE shell command over a shell-v2 stream and returns its output.

        SESSION ID DISCIPLINE (this is what fixes the 'output lags by one call' bug):
        adbd answers an A_OPEN with A_OKAY/A_WRTE/A_CLSE carrying the id WE chose (`lid`).
        Older data left in the socket from a PREVIOUS session arrives with a DIFFERENT id.
        The previous version accepted `a0 != 0` - i.e. any session - so leftovers were
        appended to the CURRENT answer: the command returned the PREVIOUS command's output,
        consistently one call behind (13 reproductions in the field report).
        Now every packet is matched against `lid`; foreign packets are DROPPED and drained,
        never mixed into this answer."""
        self.lid += 1; lid=self.lid
        # ★ PRE-FLUSH: golim orice reziduu de protocol ramas in socket INAINTE de a deschide
        # sesiunea noua. Fara asta, un rest de la comanda anterioara (adbd lent, timeout de
        # drenare prea scurt) intra in raspunsul curent -> "output cu un apel in urma".
        # ★ PRE-FLUSH CONDITIONAT (optimizare viteza, masurat: 588ms -> 49ms/cmd):
        # drenam DOAR daca socket-ul CHIAR are date reziduale (select timeout=0). Altfel
        # _drain() pierdea ~0.45s la FIECARE comanda, chiar cand nu era nimic de golit.
        try:
            import select as _sel0
            _r0,_w0,_x0 = _sel0.select([self.s], [], [], 0)
        except Exception:
            _r0 = [self.s]
        if _r0:
            self._drain()
        self._send(A_OPEN, lid, 0, ("shell,v2,raw:"+cmd).encode()+b"\0")
        # ★ FAZA 4l: acumulam BYTES BRUTI si demultiplexam la final.
        # Vechea varianta presupunea ca fiecare pachet A_WRTE are EXACT un header de substream
        # (`d[0] in (1,2) and len(d)>5 -> d[5:]`). adbd poate pune insa mai multe substream-uri
        # intr-un singur pachet (stdout+stderr+exit code) sau poate sparge unul pe doua pachete:
        # atunci header-ele interioare ajungeau in output si agentul vedea "gunoi binar"
        # (\x01\x0b\x00\x00\x00, \x02..., \x03\x01\x00\x00\x00\x01) - exact simptomul raportat
        # in doua sesiuni de test din UI.
        raw=b""; end=time.time()+timeout; closed=False; timed_out=False; foreign=0
        try:
            while time.time()<end:
                try: c,a0,a1,d = self._recv(max(1,int(end-time.time())))
                except socket.timeout:
                    timed_out=True; break
                except Exception:
                    break
                # ★ STRICT SESSION MATCH. Protocol fact, verified on the device: we OPEN with
                # (a0=OUR id, a1=0) and adbd answers with (a0=ITS id, a1=OUR id). So the field that
                # identifies OUR session is a1 - checking a0 (the old `a0 != 0`, i.e. "any session")
                # let leftovers from the previous command into this answer: the 'lag by one call'
                # bug of the field report. Checking a0==lid is equally wrong (it would reject
                # everything and time out).
                if c in (A_OKAY, A_WRTE, A_CLSE) and a1 != lid:
                    foreign += 1
                    if c == A_WRTE:
                        try: self._send(A_OKAY, a1, a0)   # FIX: id-uri INVERSATE (ca la 336); (a0,a1) desincroniza adbd -> output gol intermitent
                        except Exception: break
                    continue                             # never append it to `out`
                if c == A_OKAY: pass
                elif c == A_WRTE:
                    if d:
                        raw += d
                    try: self._send(A_OKAY, a1, a0)       # reply with the ids SWAPPED (adbd's id first)
                    except Exception: break
                elif c == A_CLSE:
                    closed=True; break
        finally:
            # ★ FIX adbfix-8 (PROCESE ORFANE): la timeout, comanda ruleaza MAI DEPARTE pe
            # device (adbd nu o omoara), deci un `sleep 300` sau un build uitat ramane viu
            # si poate tine sesiunea ocupata minute bune. Inchiderea sesiunii (A_CLSE) NU
            # opreste procesul. Cand si numai cand am dat timeout, trimitem si un SIGTERM
            # catre sesiune, pe un socket CURAT (ca sa nu atingem sesiunea curenta).
            if timed_out and not closed:
                # ★ SIGURANTA: NU folosim `pkill -f sleep` - ar ucide si procese legitime
                # (build-uri, scripturi ale operatorului) care contin cuvantul. Vizam STRICT
                # procese ORFANE (PPID 1) care inca ruleaza - exact rezultatul unui timeout.
                try:
                    import subprocess as _sp
                    _sp.run(["sh","-c",
                             "for p in $(ps -A -o pid=,ppid= 2>/dev/null | awk '$2==1{print $1}'); do "
                             "kill -9 $p 2>/dev/null; done; true"],
                            capture_output=True, timeout=5)
                except Exception:
                    pass
            # ★ inchidem sesiunea DOAR daca nu s-a inchis deja singura
            if not closed:
                # ★ FIX adbfix-6 (DOVEDIT pe device, cauza RECONECTARILOR IN LANT):
                # La timeout, `a1` (id-ul nostru de sesiune) venea din ULTIMUL pachet primit,
                # iar daca acela era un A_OKAY atunci a1==0. Trimiteam deci A_CLSE cu id 0,
                # adbd nu recunostea sesiunea si INCHIDEA CONEXIUNEA -> _send reconecta ->
                # 4 handshake-uri pentru o singura comanda de 2s (masurat: 4.05s).
                # Id-ul NOSTRU de sesiune este INTOTDEAUNA `lid` (cel cu care am dat A_OPEN),
                # iar adbd se asteapta la (local=al nostru, remote=al lui).
                try: self._send(A_CLSE, lid, a1 if 'a1' in dir() else 0)
                except Exception:
                    try: self._send(A_CLSE, lid, 0)
                    except Exception: pass
            # ★ DRENARE DETERMINISTA: golim socket-ul (pana la 3 citiri idle consecutive).
            # ★ FIX (BLOCAJ INFINIT - raportat de operator, pasi de ~1.2s): bucla veche
            # `while idle < 3` NU avea limita de timp total. Daca adbd trimitea date
            # continuu (ex. o sesiune care nu se inchide), `idle` se reseta la fiecare
            # pachet => bucla nu se termina NICIODATA => comanda agata la infinit.
            # Acum exista un buget TOTAL de timp (0.6s): oricate pachete ar veni,
            # drenarea se opreste la timp si comanda NU poate bloca.
            # ★ DRENARE RAPIDA (optimizare, masurat 588ms->49ms/comanda): session-matching-ul
            # strict (a1 != lid) de mai sus garanteaza deja corectitudinea; resturile minore se
            # curata la URMATORUL apel prin pre-flush-ul conditionat. Daca socket-ul e GOL
            # (select=0) NU mai asteptam 3 x 0.15s. Buget total 0.3s, iesire imediata cand e gol.
            try:
                _deadline = time.time() + 0.3
                while time.time() < _deadline:
                    import select as _sel
                    _r,_w,_x = _sel.select([self.s], [], [], 0.02)
                    if not _r:
                        break
                    self.s.settimeout(0.15)
                    try:
                        self._recv(0.15)
                    except Exception:
                        break
            except Exception:
                pass
            try: self.s.settimeout(8)
            except Exception: pass
        out = _demux_shellv2(raw)
        txt = out.decode(errors="replace")
        if timed_out and not txt.strip():
            txt = "[adb] command exceeded %ss (the process may still run in the background)" % int(timeout)
        # ★ FLAG pentru shell(): comanda s-a terminat NORMAL (fara timeout) => un output
        # gol e REZULTAT VALID, nu semn de socket stricat. Fara asta, shell() reconecta
        # la fiecare comanda tacuta (true/cd/mkdir/touch) = 485-1226 ms in loc de ~45 ms.
        try:
            self._last_rc_ok = (not timed_out)
        except Exception:
            pass
        return txt

    # ---------------------------------------------------------------- STREAMING
    def open_stream(self, cmd):
        """Deschide o sesiune shell PERSISTENTA (pentru terminal interactiv).

        Returneaza (lid, reader) unde reader are .read(timeout) / .write(bytes) / .close().
        Protocoale ADB: A_OPEN o data, apoi A_WRTE in ambele sensuri (stdin/stdout).
        Folosit de terminal_server pentru pty-ul din aplicatie.
        """
        self.lid += 1
        lid = self.lid
        with _SOCK_LOCK:
            try:
                import select as _sel
                r, _, _ = _sel.select([self.s], [], [], 0)
                if r:
                    self._drain()
            except Exception:
                pass
            self._send(A_OPEN, lid, 0, ("shell,v2,raw:" + cmd).encode() + b"\0")
        return lid, _AdbStream(self, lid)

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


class _AdbStream:
    """Sesiune ADB persistenta: citire/scriere continua (terminal interactiv)."""

    def __init__(self, adb, lid):
        self.adb = adb
        self.lid = lid
        self.closed = False
        self.buf = b""

    def write(self, data):
        if self.closed:
            return
        try:
            with _SOCK_LOCK:
                self.adb._send(A_WRTE, self.lid, self.lid, data)
        except Exception:
            self.closed = True

    def read(self, timeout=0.5):
        """intoarce bytes noi (stdout+stderr demultiplexat) sau b"" la timeout."""
        if self.closed:
            return b""
        out = b""
        import time as _t
        end = _t.time() + timeout
        try:
            while _t.time() < end:
                with _SOCK_LOCK:
                    try:
                        c, a0, a1, d = self.adb._recv(max(0.05, end - _t.time()))
                    except Exception:
                        break
                if a1 != self.lid:
                    continue
                if c == A_WRTE:
                    out += _demux_v2(d)
                    with _SOCK_LOCK:
                        try:
                            self.adb._send(A_OKAY, self.lid, self.lid)
                        except Exception:
                            pass
                elif c == A_CLSE:
                    self.closed = True
                    break
                elif c == A_OKAY:
                    continue
        except Exception:
            pass
        return out

    def close(self):
        self.closed = True
        try:
            with _SOCK_LOCK:
                self.adb._send(A_CLSE, self.lid, self.lid)
        except Exception:
            pass


def _demux_v2(data):
    """extrage payload-ul din substream-urile shell-v2 (1=stdout, 2=stderr, 3=exit)."""
    out = b""
    i = 0
    while i + 5 <= len(data):
        st = data[i]
        ln = int.from_bytes(data[i + 1:i + 5], "little")
        payload = data[i + 5:i + 5 + ln]
        if st in (1, 2):
            out += payload
        i += 5 + ln
    return out
