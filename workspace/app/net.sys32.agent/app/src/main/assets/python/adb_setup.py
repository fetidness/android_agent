#!/usr/bin/env python3
"""SETUP ADB AUTOMAT cu CHEIE PERSISTENTA.
Cheia se salveaza in /sdcard/Download/Agent/ (supravietuieste reinstalarilor!).
La pornire: load din sdcard SAU genereaza + salveaza acolo."""
import ctypes, os, sys, struct, base64, shutil, socket, time

F = "/data/data/net.sys32.agent/files"
LIB = F + "/libs"
# ★ cheile PERSISTENTE (nu se sterg la uninstall)
PERSIST = "/sdcard/Download/Agent"
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
        log("cheie PERSISTENTA gasita in /sdcard")
        shutil.copy2(KEY, LKEY); shutil.copy2(PUBC, LPUBC)
        return True
    # 2. daca exista local (din sesiune) -> o promovez in /sdcard
    if os.path.exists(LKEY) and os.path.exists(LPUBC):
        log("promovez cheia locala in /sdcard")
        try:
            shutil.copy2(LKEY, KEY); shutil.copy2(LPUBC, PUBC)
        except Exception as e:
            log("nu pot salva in /sdcard: " + str(e)[:50])
        return True
    # 3. generez noua
    log("generez cheie RSA 2048...")
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
    blob = struct.pack(">I", nl) + nb.raw[:nl] + struct.pack(">I", el) + eb.raw[:el]
    open(LPUBC,"w").write(base64.b64encode(blob).decode())
    # ★ salvez in /sdcard (persistent!)
    try:
        shutil.copy2(LKEY, KEY); shutil.copy2(LPUBC, PUBC)
        log("cheie NOUA + salvata in /sdcard (persistenta)")
    except Exception as ex:
        log("atentie: nu pot salva in /sdcard: " + str(ex)[:50])
    return True

# ---------------- 3. CERT ----------------
def ensure_cert():
    if os.path.exists(CERT) and os.path.exists(TLSK):
        log("cert existent"); return True
    log("generez certificat...")
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
    if not pk: log("EROARE cheie"); return False
    x = c.X509_new(); c.X509_set_version(x,2)
    c.ASN1_INTEGER_set(c.X509_get_serialNumber(x),1)
    c.X509_gmtime_adj(c.X509_getm_notBefore(x),0); c.X509_gmtime_adj(c.X509_getm_notAfter(x),10*365*24*3600)
    c.X509_set_pubkey(x,pk)
    nm = c.X509_get_subject_name(x)
    c.X509_NAME_add_entry_by_txt(nm,b"CN",0x1000|1,b"adb",-1,-1,0)
    c.X509_set_issuer_name(x,nm)
    if c.X509_sign(x,pk,c.EVP_sha256()) <= 0: log("EROARE sign"); return False
    b2 = c.BIO_new_file(CERT.encode(),b"w"); c.PEM_write_bio_X509(b2,x); c.BIO_free(b2)
    shutil.copy2(LKEY, TLSK)
    return True

if __name__ == "__main__":
    log("=== SETUP ADB (cheie persistenta) ===")
    ensure_dirs()
    ok1 = ensure_libs()
    ok2 = ensure_key() if ok1 else False
    ok3 = ensure_cert() if ok2 else False
    log("libs=%s cheie=%s cert=%s" % (ok1, ok2, ok3))
    log("cheie persistenta: " + (PERSIST if os.path.exists(KEY) else "NU (in files/)"))
