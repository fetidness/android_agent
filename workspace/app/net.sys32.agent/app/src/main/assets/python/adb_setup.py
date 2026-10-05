#!/usr/bin/env python3
"""SETUP ADB AUTOMAT cu CHEIE PERSISTENTA.
Cheia se salveaza in /sdcard/Download/<folder aplicatiei>/ (supravietuieste reinstalarilor!).
Folderul vine din AGENT_HOME (setat de aplicatie); fiecare agent are folderul lui, ca sa nu
imparta adbkey-ul cu celalalt.
La pornire: load din sdcard SAU genereaza + salveaza acolo."""
import ctypes, os, sys, struct, base64, shutil, socket, time

F = "/data/data/net.sys32.agent/files"
LIB = F + "/libs"
# ★ cheile PERSISTENTE (nu se sterg la uninstall); folder PER APLICATIE
PERSIST = (os.environ.get("AGENT_HOME") or "").strip() or "/sdcard/Download/Agent"
KEY = PERSIST + "/adbkey"          # privata
PUBC = PERSIST + "/adbkey.pub"     # publica (format ADB)
# copii de lucru (locale, rapide)
LKEY = F + "/adbkey"; LPUBC = F + "/adbkey.pub"
CERT = F + "/tls.crt"; TLSK = F + "/tls.key"

def log(m): print("[setup] " + m, flush=True)

def ensure_dirs():
    for d in (LIB, PERSIST):
        try: os.makedirs(d, exist_ok=True)
        except: pass

# ---------------- 1. LIBS ----------------
def ensure_libs():
    os.makedirs(LIB, exist_ok=True)
    needed = ["libcrypto.so","libssl.so","libadb_pairing_auth.so","libadb_pairing_connection.so"]
    srcs = ["/apex/com.android.adbd/lib64/", "/apex/com.android.conscrypt/lib64/", "/system/lib64/"]
    for fn in needed:
        dst = os.path.join(LIB, fn)
        if os.path.exists(dst): continue
        for s in srcs:
            sp = s + fn
            if os.path.exists(sp):
                try: shutil.copy2(sp, dst); log("libs: " + fn); break
                except Exception: pass
    return os.path.exists(LIB + "/libcrypto.so")

# ---------------- 2. CHEIE (persistenta!) ----------------
def ensure_key():
    # ★ 1. daca exista in /sdcard -> o folosesc (persistenta!)
    if os.path.exists(KEY) and os.path.exists(PUBC):
        log("PERSISTENT key found in /sdcard")
        shutil.copy2(KEY, LKEY); shutil.copy2(PUBC, LPUBC)
        return True
    # 2. daca exista local (din sesiune) -> o promovez in /sdcard
    if os.path.exists(LKEY) and os.path.exists(LPUBC):
        log("promoting local key to /sdcard")
        try:
            shutil.copy2(LKEY, KEY); shutil.copy2(LPUBC, PUBC)
        except Exception as e:
            log("cannot save to /sdcard: " + str(e)[:50])
        return True
    # 3. generez noua
    log("generating RSA 2048 key...")
    c = ctypes.CDLL(LIB + "/libcrypto.so", mode=ctypes.RTLD_GLOBAL)
    def S(n,a,r):
        f = getattr(c,n); f.argtypes = a; f.restype = r
    S("BN_new",[],ctypes.c_void_p); S("BN_set_word",[ctypes.c_void_p,ctypes.c_ulong],ctypes.c_int)
    S("RSA_new",[],ctypes.c_void_p)
    S("RSA_generate_key_ex",[ctypes.c_void_p,ctypes.c_int,ctypes.c_void_p,ctypes.c_void_p],ctypes.c_int)
    S("EVP_PKEY_new",[],ctypes.c_void_p); S("EVP_PKEY_set1_RSA",[ctypes.c_void_p,ctypes.c_void_p],ctypes.c_int)
    S("BIO_new_file",[ctypes.c_char_p,ctypes.c_char_p],ctypes.c_void_p); S("BIO_free",[ctypes.c_void_p],ctypes.c_int)
    S("PEM_write_bio_PrivateKey",[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,
       ctypes.c_int,ctypes.c_void_p,ctypes.c_void_p],ctypes.c_int)
    S("RSA_get0_key",[ctypes.c_void_p,ctypes.POINTER(ctypes.c_void_p),
       ctypes.POINTER(ctypes.c_void_p),ctypes.POINTER(ctypes.c_void_p)],None)
    S("BN_bn2bin",[ctypes.c_void_p,ctypes.c_char_p],ctypes.c_int)
    S("BN_num_bits",[ctypes.c_void_p],ctypes.c_int)
    bn = c.BN_new(); c.BN_set_word(bn, 65537)
    rsa = c.RSA_new()
    if c.RSA_generate_key_ex(rsa, 2048, bn, None) != 1:
        log("EROARE RSA"); return False
    pkey = c.EVP_PKEY_new(); c.EVP_PKEY_set1_RSA(pkey, rsa)
    b = c.BIO_new_file(LKEY.encode(), b"w")
    c.PEM_write_bio_PrivateKey(b, pkey, None, None, 0, None, None); c.BIO_free(b)
    n = ctypes.c_void_p(); e = ctypes.c_void_p(); d = ctypes.c_void_p()
    c.RSA_get0_key(rsa, ctypes.byref(n), ctypes.byref(e), ctypes.byref(d))
    nl = (c.BN_num_bits(n)+7)//8; el = (c.BN_num_bits(e)+7)//8
    nb = ctypes.create_string_buffer(nl); c.BN_bn2bin(n, nb)
    eb = ctypes.create_string_buffer(el); c.BN_bn2bin(e, eb)
    # ★ FORMATUL ANDROID_PUBKEY (AOSP, system/core/libcrypto_utils/android_pubkey.h):
    #   [0:4]     u32 BIG-endian = 256 (len_n)       <- lungimea modulus-ului
    #   [4:260]   u8  modulus[256]  (BIG-endian)     <- modulus-ul, ordinea naturala
    #   [260:264] u32 BIG-endian   n0inv = -n^-1 mod 2^32 (0 inseamna "recomanda")
    #   [264:520] u8  rr[256]       (BIG-endian)     <- (2^2048)^2 mod n, pt Montgomery
    #   [520:524] u32 BIG-endian   exponent = 65537
    # Total EXACT 524 bytes; adbd verifica b64_pton(...) == 524.
    #
    # ★ BUG REPARAT (2026-09-25): versiunea veche scria [n0inv LE][modulus LE][rr LE][exp][exp]
    # - adica n0inv PRIMUL si TOTUL little-endian. Adbd respingea cheia (RSAPUBLICKEY ->
    # timeout, fara dialog). Cauza: modulus-ul era byte-reversed fata de ce asteapta adbd
    # (big-endian). Acum scriem EXACT formatul AOSP: len_n BE, modulus BE, n0inv BE, rr BE, exp BE.
    import ctypes as _ct
    S("BN_bn2binpad", [_ct.c_void_p, _ct.c_char_p, _ct.c_int], _ct.c_int)
    N = 2048 // 8      # 256 bytes
    def _bebn(bn, size=N):
        buf = _ct.create_string_buffer(size)
        c.BN_bn2binpad(bn, buf, size)
        return buf.raw[:size]
    mod_be = _bebn(n)                    # 256 bytes BIG-endian (ordinea naturala)
    m_int = int.from_bytes(mod_be, "big")
    m0 = m_int & 0xFFFFFFFF
    if m0 & 1 == 0: m0 |= 1
    n0inv = (2**32 - pow(m0, -1, 2**32)) % 2**32
    rr_int = pow(2, 2048 * 2, m_int)
    rr_be = rr_int.to_bytes(N, "big")
    blob = (struct.pack(">I", N) + mod_be + struct.pack(">I", n0inv)
            + rr_be + struct.pack(">I", 65537))
    assert len(blob) == 524, "android_pubkey blob trebuie 524 bytes, e %d" % len(blob)
    open(LPUBC,"w").write(base64.b64encode(blob).decode())
    # ★ salvez in /sdcard (persistent!)
    try:
        shutil.copy2(LKEY, KEY); shutil.copy2(LPUBC, PUBC)
        log("NEW key + saved to /sdcard (persistent)")
    except Exception as ex:
        log("warning: cannot save to /sdcard: " + str(ex)[:50])
    return True

# ---------------- 3. CERT ----------------
def ensure_cert():
    if os.path.exists(CERT) and os.path.exists(TLSK):
        log("certificate exists"); return True
    log("generating certificate...")
    c = ctypes.CDLL(LIB + "/libcrypto.so", mode=ctypes.RTLD_GLOBAL)
    def S(n,a,r):
        f = getattr(c,n); f.argtypes = a; f.restype = r
    S("BIO_new_file",[ctypes.c_char_p,ctypes.c_char_p],ctypes.c_void_p); S("BIO_free",[ctypes.c_void_p],ctypes.c_int)
    S("PEM_read_bio_PrivateKey",[ctypes.c_void_p]*4,ctypes.c_void_p)
    S("X509_new",[],ctypes.c_void_p); S("X509_set_version",[ctypes.c_void_p,ctypes.c_long],ctypes.c_int)
    S("X509_get_serialNumber",[ctypes.c_void_p],ctypes.c_void_p); S("ASN1_INTEGER_set",[ctypes.c_void_p,ctypes.c_long],ctypes.c_int)
    S("X509_gmtime_adj",[ctypes.c_void_p,ctypes.c_long],ctypes.c_void_p)
    S("X509_getm_notBefore",[ctypes.c_void_p],ctypes.c_void_p); S("X509_getm_notAfter",[ctypes.c_void_p],ctypes.c_void_p)
    S("X509_set_pubkey",[ctypes.c_void_p,ctypes.c_void_p],ctypes.c_int)
    S("X509_sign",[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p],ctypes.c_int); S("EVP_sha256",[],ctypes.c_void_p)
    S("X509_get_subject_name",[ctypes.c_void_p],ctypes.c_void_p); S("X509_set_issuer_name",[ctypes.c_void_p,ctypes.c_void_p],ctypes.c_int)
    S("X509_NAME_add_entry_by_txt",[ctypes.c_void_p,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,
       ctypes.c_int,ctypes.c_int,ctypes.c_int],ctypes.c_int)
    S("PEM_write_bio_X509",[ctypes.c_void_p,ctypes.c_void_p],ctypes.c_int)
    b = c.BIO_new_file(LKEY.encode(), b"r")
    pk = c.PEM_read_bio_PrivateKey(b, None, None, None); c.BIO_free(b)
    if not pk: log("ERROR key"); return False
    x = c.X509_new(); c.X509_set_version(x,2)
    c.ASN1_INTEGER_set(c.X509_get_serialNumber(x),1)
    c.X509_gmtime_adj(c.X509_getm_notBefore(x),0); c.X509_gmtime_adj(c.X509_getm_notAfter(x),10*365*24*3600)
    c.X509_set_pubkey(x,pk)
    nm = c.X509_get_subject_name(x)
    c.X509_NAME_add_entry_by_txt(nm,b"CN",0x1000|1,b"adb",-1,-1,0)
    c.X509_set_issuer_name(x,nm)
    if c.X509_sign(x,pk,c.EVP_sha256()) <= 0: log("ERROR sign"); return False
    b2 = c.BIO_new_file(CERT.encode(),b"w"); c.PEM_write_bio_X509(b2,x); c.BIO_free(b2)
    shutil.copy2(LKEY, TLSK)
    return True

if __name__ == "__main__":
    log("=== ADB SETUP (persistent key) ===")
    ensure_dirs()
    ok1 = ensure_libs()
    ok2 = ensure_key() if ok1 else False
    ok3 = ensure_cert() if ok2 else False
    log("libs=%s key=%s cert=%s" % (ok1, ok2, ok3))
    log("persistent key: " + (PERSIST if os.path.exists(KEY) else "NO (in files/)"))
