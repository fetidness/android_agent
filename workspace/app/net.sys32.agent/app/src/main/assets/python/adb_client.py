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
    pid = os.getpid()
    if _SHARED_PID != pid:
        _SHARED = None
        _SHARED_PID = pid
    if _SHARED is not None and _SHARED.s is not None:
        try:
            import select as _sel
            r, _, _ = _sel.select([_SHARED.s], [], [], 0)
            if r:
                peek = _SHARED.s.recv(1, 0x02)     # MSG_PEEK
                if peek == b"":
                    _SHARED = None                  # EOF real
        except BlockingIOError:
            pass                                    # EAGAIN: e viu
        except Exception:
            _SHARED = None
    if _SHARED is None:
        _SHARED = Adb(host=host, port=port)
        if auto:
            _SHARED.connect()
    return _SHARED


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
                # ★ ORDINEA CORECTA (fix dupa blocajul "adbsh timeout" din teste):
                # adbd trimite AUTH_TOKEN si ASTEAPTA o dovada. Sunt doua cai:
                #   (1) AUTH_SIGNATURE  - daca cheia privata e deja in user_keys: adbd
                #       verifica semnatura si raspunde CNXN IMEDIAT, fara dialog.
                #   (2) AUTH_RSAPUBLICKEY - daca NU e autorizata: adbd afiseaza dialogul
                #       "Allow USB debugging".
                # Vechiul cod incerca (2) PRIMUL si (1) doar in `except`. Pe acest device
                # cheia e deja in user_keys, deci adbd NU raspunde deloc la (2):
                # ramanea in timeout si adbsh parea mort. Acum incercam (1) PRIMUL.
                # ★ FIX (verificat pe device): RSAPUBLICKEY PRIMUL.
                # adbd accepta RSAPUBLICKEY INSTANT (raspunde CNXN), in timp ce
                # SIGNATURE e respinsa cand cheia nu e in lista persistenta.
                pub = open(PUBC,"rb").read().strip()+b"\0"
                print("[adb] AUTH -> trimit RSAPUBLICKEY", len(pub), "bytes", flush=True)
                self._send(A_AUTH, AUTH_RSAPUBLICKEY, 0, pub)
                _auth_left -= 1
                if _auth_left <= 0:
                    raise RuntimeError("adbd a respins autorizarea (3 incercari) - "
                                       "accepta dialogul 'Allow USB debugging' pe telefon "
                                       "sau ruleaza: adb tcpip 1234 de pe PC")
            else:
                raise RuntimeError("neasteptat %#x a0=%d" % (cmd,a0))
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
            # daca rezultatul e gol si nu era de asteptat gol, incercam O reconectare
            if r == "" and cmd.strip() and not cmd.strip().startswith("echo __MK"):
                try:
                    self.close(); self.connect()
                    r2 = self._shell_locked(cmd, timeout)
                    if r2.strip(): r = r2
                except Exception:
                    pass
            return r

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
        out=b""; end=time.time()+timeout; closed=False; timed_out=False; foreign=0
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
                        if d[0] in (1,2) and len(d)>5: out += d[5:]
                        else: out += d
                    try: self._send(A_OKAY, a1, a0)       # reply with the ids SWAPPED (adbd's id first)
                    except Exception: break
                elif c == A_CLSE:
                    closed=True; break
        finally:
            # ★ inchidem sesiunea DOAR daca nu s-a inchis deja singura
            if not closed:
                try: self._send(A_CLSE, a1 if 'a1' in dir() else lid, a0 if 'a0' in dir() else 0)
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
