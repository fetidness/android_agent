#!/usr/bin/env python3
"""Build git 2.47.1 de la ZERO pe device (dupa reteta corectata).

Ruleaza ca proces al aplicatiei (filesDir accesibil), scrie progres in
files/tmp/gb_status.txt. NU foloseste ./configure (git se compileaza direct cu make).
"""
import os, sys, subprocess, tarfile, time, shutil, glob, urllib.request

F = "/data/data/net.sys32.agent/files"
TC = F + "/toolchain"
DEPS = TC + "/deps"
B = F + "/tmp/gb"
INS = F + "/toolchain/git"          # ★ prefixul COMPILAT = locul DURABIL:
# altfel binarul retine tree-ul de build (files/tmp/gb/prefix) si fiecare comanda da
# warning-uri "unable to access .../etc/gitattributes", iar la curatare git se strica.
# (agentul a ajuns sa PATCH-UIE binarul ca sa scape de ele - nu e necesar)
SRC = B + "/src"
ST = F + "/tmp/gb_status.txt"
NAT = None

def log(msg):
    with open(ST, "a") as f:
        f.write("[%s] %s\n" % (time.strftime("%H:%M:%S"), msg))
    print(msg, flush=True)

sys.path.insert(0, F + "/python")
import toolchain as tc
tc._ensure_launchers()
e = dict(tc.env_vars())
e["PATH"] = F + "/tmp:" + e.get("PATH", "")
e["TMPDIR"] = F + "/tmp"
NAT = tc._native_dir()

def run(args, cwd=None, timeout=1800, label=""):
    log("RUN %s: %s" % (label, " ".join(args)[:140]))
    r = subprocess.run(args, cwd=cwd, env=e, capture_output=True, text=True, timeout=timeout,
                       stdin=subprocess.DEVNULL)
    out = ((r.stdout or "") + (r.stderr or "")).strip()
    log("  %s rc=%s | %s" % (label, r.returncode, out[-200:].replace("\n", " | ")))
    return r.returncode, out

open(ST, "w").write("start\n")
for d in (B, INS, SRC):
    os.makedirs(d, exist_ok=True)

# 1) surse
srcs = [("git-2.47.1.tar.xz", "https://mirrors.edge.kernel.org/pub/software/scm/git/git-2.47.1.tar.xz"),
        ("libssh2-1.11.1.tar.gz", "https://www.libssh2.org/download/libssh2-1.11.1.tar.gz"),
        ("nghttp2-1.64.0.tar.gz", "https://github.com/nghttp2/nghttp2/releases/download/v1.64.0/nghttp2-1.64.0.tar.gz")]
for name, url in srcs:
    p = SRC + "/" + name
    if not os.path.exists(p):
        try:
            urllib.request.urlretrieve(url, p)
            log("descarcat %s (%d bytes)" % (name, os.path.getsize(p)))
        except Exception as ex:
            log("EROARE descarcare %s: %r" % (name, ex)); sys.exit(1)
    # extract cu python (toybox tar nu are xz)
    base = name.split(".tar")[0]
    if not os.path.isdir(SRC + "/" + base):
        with tarfile.open(p) as tf:
            tf.extractall(SRC)
        log("extras %s" % base)

# 2) nghttp2 (shared) si libssh2 (static) in prefix
cm = F + "/tmp/cmake"; ninja = F + "/tmp/ninja"
if not os.path.exists(INS + "/lib/libnghttp2.so.14"):
    rc, _ = run([cm, "-S", SRC + "/nghttp2-1.64.0", "-B", B + "/b_ng", "-G", "Ninja",
                 "-DCMAKE_INSTALL_PREFIX=" + INS, "-DBUILD_STATIC_LIBS=OFF",
                 "-DENABLE_LIB_ONLY=ON", "-DENABLE_APP=OFF"], label="cmake-nghttp2")
    if rc == 0:
        run([ninja, "-C", B + "/b_ng", "install"], label="install-nghttp2")
if not os.path.exists(INS + "/lib/libssh2.a"):
    rc, _ = run([cm, "-S", SRC + "/libssh2-1.11.1", "-B", B + "/b_ss", "-G", "Ninja",
                 "-DCMAKE_INSTALL_PREFIX=" + INS, "-DCRYPTO_BACKEND=OpenSSL",
                 "-DBUILD_SHARED_LIBS=OFF", "-DBUILD_STATIC_LIBS=ON",
                 "-DCMAKE_PREFIX_PATH=" + DEPS, "-DBUILD_TESTING=OFF",
                 "-DBUILD_EXAMPLES=OFF"], label="cmake-libssh2")
    if rc == 0:
        run([ninja, "-C", B + "/b_ss", "install"], label="install-libssh2")

# 3) curl-config fals (git il cheama ca sa afle flag-urile libcurl)
cc = F + "/tmp/curl-config"
open(cc, "w").write(
    "#!/system/bin/sh\n"
    "case \"$1\" in\n"
    "  --cflags) echo \"-I%s/include\" ;;\n"
    "  --libs)   echo \"-L%s/lib -lcurl -lnghttp2 -lssh2 -lssl -lcrypto -lz -lzstd\" ;;\n"
    "  --version) echo \"8.0.0\" ;;\n"
    "  *) echo \"\" ;;\n"
    "esac\n" % (DEPS, INS))
os.chmod(cc, 0o755)

# 4) git: DIRECT cu make (fara ./configure) - flag-urile dovedite + NO_PTHREADS (Bionic)
gitsrc = SRC + "/git-2.47.1"
mk = F + "/tmp/make"
# ★ Flag-urile COMPLETE (inclusiv --target/--sysroot): altfel lansatorul clang isi adauga singur
# setul lui de -I (inclusiv pyinc) si git isi ia headerele Python in loc de ale lui
# ("object.h: unknown type name 'Py_ssize_t'").
api = tc._device_api()
cflags = ("-O2 -fPIC --target=aarch64-linux-android%s --sysroot=%s/sysroot "
          "-resource-dir=%s/lib/clang/21 -I%s/include -I%s/include" % (api, TC, TC, DEPS, INS))
ldflags = ("--target=aarch64-linux-android%s --sysroot=%s/sysroot -L%s/lib -L%s/lib "
           "-L%s/lib/clang/21/lib/linux -Wl,-rpath,%s/lib" % (api, TC, INS, DEPS, TC, INS))
# 3b) shim MD5: libcurl.a cere MD5_Init/Update/Final, dar libcrypto.a din deps e construit fara
# MD5 (no-md5). Le implementam peste EVP (care exista) si il linkam in git.
shim = F + "/tmp/md5shim.c"
open(shim, "w").write("""#include <openssl/evp.h>
#include <string.h>
typedef struct { EVP_MD_CTX *c; } MD5_CTX_SHIM;
int MD5_Init(void *ctx) { MD5_CTX_SHIM *m = (MD5_CTX_SHIM *)ctx;
  m->c = EVP_MD_CTX_new(); return EVP_DigestInit_ex(m->c, EVP_md5(), NULL); }
int MD5_Update(void *ctx, const void *data, unsigned long len) {
  MD5_CTX_SHIM *m = (MD5_CTX_SHIM *)ctx; return EVP_DigestUpdate(m->c, data, len); }
int MD5_Final(unsigned char *md, void *ctx) {
  MD5_CTX_SHIM *m = (MD5_CTX_SHIM *)ctx; unsigned int n = 0;
  int r = EVP_DigestFinal_ex(m->c, md, &n); EVP_MD_CTX_free(m->c); return r; }
""")
shim_o = F + "/tmp/md5shim.o"
rc0, _ = run([F + "/tmp/clang", "-c", shim, "-o", shim_o,
              "--target=aarch64-linux-android" + str(tc._device_api()),
              "--sysroot=" + TC + "/sysroot", "-resource-dir=" + TC + "/lib/clang/21",
              "-I" + DEPS + "/include"], label="compile-md5shim")
SHIM = []
if rc0 == 0:
    # ★ NU prin "LIBS=" (suprascrie lista interna a git-ului -> "undefined symbol: xstrdup",
    # "the_repository"...). Facem o biblioteca statica si o adaugam la CURL_LDFLAGS.
    # un SINGUR mecanism: obiectul, referit direct in CURL_LIBCURL (fara arhiva - altfel
    # "duplicate symbol: MD5_Init")
    SHIM = [shim_o]
    try:
        if os.path.exists(B + "/libmd5shim.a"):
            os.remove(B + "/libmd5shim.a")
    except Exception:
        pass

MKVARS = [  # refolosite si la install (altfel install reporneste make cu "cc" -> cc-rust)
    "CC=" + F + "/tmp/clang", "AR=" + F + "/tmp/ar", "RANLIB=" + F + "/tmp/ranlib",
    "NO_GETTEXT=1", "NO_TCLTK=1", "NO_PYTHON=1", "NO_PERL=1", "NO_RUST=1", "NO_EXPAT=1",
    "NO_ICONV=1", "NO_INSTALL_HARDLINKS=1", "NO_MMAP=1", "NO_PTHREADS=YesPlease",
    "CURL_CONFIG=sh " + cc, "CURL_CFLAGS=-I%s/include" % DEPS,
    # ★ static linking: toate caile + --start-group (libcurl<->libssl/libcrypto se refera
    # reciproc; fara grouping apar "undefined symbol: X509_STORE_up_ref"/"DES_set_odd_parity")
    "CURL_LDFLAGS=-L%s/lib -L%s/lib -lcurl -lnghttp2 -lssh2 -lssl -lcrypto -lz -lzstd" % (INS, DEPS),
    # ★ Helper-ele (git-remote-http, git-http-fetch) linkeaza prin CURL_LIBCURL; daca il setam pe
    # linia de comanda, suprascrie "+=" din Makefile, deci trebuie sa contina TOT (shim + grup).
    "CURL_LIBCURL=" + " ".join(["-Wl,--allow-multiple-definition"] +
                               ([(shim_o)] if SHIM else []) +
                               ["-Wl,--start-group", "-L" + INS + "/lib", "-L" + DEPS + "/lib",
                                "-lcurl", "-lnghttp2", "-lssh2", "-lssl", "-lcrypto", "-lz",
                                "-lzstd", "-Wl,--end-group"]),
    "LIBSSH2_LIBRARY=-lssh2",
    "CFLAGS=" + cflags, "LDFLAGS=" + ldflags,
    "prefix=" + INS, "gitexecdir=" + INS + "/libexec/git-core"]  # NU pune NO_CURL: in make,
    # "NO_CURL=0" inseamna "NO_CURL este definit" -> git se construieste FARA helper-ele curl
    # ("git: 'remote-https' is not a git command").
rc, out = run([mk, "-j4", "-C", gitsrc,
               # ★ git isi ia implicit "cc" -> ajunge la shim-ul vechi cc-rust (care nu gaseste
               # clang: "cc-rust: exec clang: No such file or directory"). Dam compilatorul nostru.
               ] + MKVARS + ["all"], timeout=2400, label="make-git")
try:
    open(F + "/tmp/gb_make.log", "w").write(out)
except Exception:
    pass
if rc != 0:
    log("BUILD FAILED la make (log complet: files/tmp/gb_make.log)")
    # primele erori reale, ca sa nu pierdem timp cu tail-ul
    errs = [l for l in out.split("\n") if "error:" in l][:6]
    for l in errs:
        log("  EROARE: " + l.strip()[:180])
    sys.exit(1)
run([mk, "-C", gitsrc] + MKVARS + ["install"], timeout=1800, label="install-git")

# 5) esentialul in locul durabil
G = TC + "/git"
for d in (G + "/bin", G + "/lib"):
    os.makedirs(d, exist_ok=True)
shutil.copy2(INS + "/bin/git", G + "/bin/git")
os.chmod(G + "/bin/git", 0o755)
for so in glob.glob(INS + "/lib/*.so*"):
    shutil.copy2(so, G + "/lib/" + os.path.basename(so))
for b in ("dbclient", "dropbearconvert"):
    if os.path.exists(INS + "/bin/" + b):
        shutil.copy2(INS + "/bin/" + b, G + "/bin/" + b)
        os.chmod(G + "/bin/" + b, 0o755)
le = INS + "/libexec/git-core"
if os.path.isdir(le):
    dst = G + "/libexec/git-core"
    os.makedirs(dst, exist_ok=True)
    for x in os.listdir(le):
        sp, dp = le + "/" + x, dst + "/" + x
        try:
            if os.path.islink(sp):
                t = os.readlink(sp)
                if os.path.lexists(dp):
                    os.remove(dp)
                os.symlink(t, dp)
            elif not os.path.exists(dp):
                shutil.copy2(sp, dp)
                os.chmod(dp, 0o755)
        except Exception:
            pass
    log("libexec copiat: %d intrari" % len(os.listdir(dst)))
# 4b) dropbear: clientul SSH + convertorul de chei
dbsrc = SRC + "/dropbear-2024.86"
if not os.path.exists(dbsrc):
    p = SRC + "/dropbear-2024.86.tar.bz2"
    if not os.path.exists(p):
        for _u in ("https://github.com/mkj/dropbear/releases/download/DROPBEAR_2024.86/dropbear-2024.86.tar.bz2",
                   "https://matt.ucc.asn.au/dropbear/releases/dropbear-2024.86.tar.bz2"):
            try:
                _rq = urllib.request.Request(_u, headers={"User-Agent": "curl/8.0"})
                with urllib.request.urlopen(_rq, timeout=120) as _rs, open(p, "wb") as _fo:
                    _fo.write(_rs.read())
                log("descarcat dropbear de la %s" % _u.split("/")[2])
                break
            except Exception as _ex:
                log("  descarcare esuata (%s): %r" % (_u.split("/")[2], _ex))
    with tarfile.open(p) as tf:
        tf.extractall(SRC)
    log("extras dropbear-2024.86")
if not os.path.exists(INS + "/bin/dbclient"):
    env2 = dict(e)
    env2["LIBS"] = "-lz"
    # ★ --host: fara el configure incearca sa RULEZE programele C compilate (cross) si cade cu
    #   "cannot run C compiled programs. If you meant to cross compile, use --host".
    r = subprocess.run(["/system/bin/sh", "./configure", "--host=aarch64-linux-android",
                        "--prefix=" + INS, "--disable-zlib", "--disable-syslog"],
                       cwd=dbsrc, env=env2, capture_output=True, text=True,
                       timeout=900, stdin=subprocess.DEVNULL)
    # ★ Android nu are crypt(): dropbear cade cu
    #   "DROPBEAR_SVR_PASSWORD_AUTH requires `crypt()'" la compilarea libtomcrypt.
    # Vrem doar CLIENTUL (dbclient), deci stingem auth-ul cu parola de pe server.
    try:
        lo = dbsrc + "/localoptions.h"
        txt = open(lo).read() if os.path.exists(lo) else ""
        if "DROPBEAR_SVR_PASSWORD_AUTH" not in txt:
            with open(lo, "a") as f:
                f.write("\n#define DROPBEAR_SVR_PASSWORD_AUTH 0\n")
            log("localoptions.h: DROPBEAR_SVR_PASSWORD_AUTH 0")
    except Exception as _e:
        log("localoptions warn: %r" % (_e,))
    log("configure-dropbear rc=%s | %s" % (r.returncode, ((r.stdout or "")+(r.stderr or ""))[-160:].replace("\n", " | ")))
    # ★ Bionic nu are getpass() -> cli-auth.c cade cu "call to undeclared function 'getpass'".
    # Ii dam o implementare mica (citeste de la /dev/tty).
    try:
        ca = dbsrc + "/src/cli-auth.c"
        txt = open(ca).read()
        if "static char *getpass_shim" not in txt:
            shim = ('#include <stdio.h>\n#include <string.h>\n'
                    'static char *getpass_shim(const char *p){ static char b[256]; FILE *f;\n'
                    '  size_t n; fprintf(stderr, "%s", p); f = fopen("/dev/tty", "r");\n'
                    '  if (!f) return NULL; if (!fgets(b, sizeof b, f)) { fclose(f); return NULL; }\n'
                    '  fclose(f); n = strlen(b); if (n && b[n-1] == 10) b[n-1] = 0; return b; }\n'
                    '#define getpass getpass_shim\n')
            open(ca, "w").write(shim + txt)
            log("cli-auth.c: shim getpass adaugat")
    except Exception as _e:
        log("getpass shim warn: %r" % (_e,))
    # ★ Makefile-ul lui dropbear cheama ./src/ifndef_wrapper.sh direct -> "Permission denied"
    #   (scripturile din filesDir nu se executa). Il facem sa cheme `sh`.
    try:
        mf = dbsrc + "/Makefile"
        t2 = open(mf).read()
        if "$(srcdir)/ifndef_wrapper.sh" in t2:
            open(mf, "w").write(t2.replace("$(srcdir)/ifndef_wrapper.sh",
                                           "sh $(srcdir)/ifndef_wrapper.sh"))
            log("Makefile dropbear: ifndef_wrapper prin sh")
    except Exception as _e:
        log("patch Makefile warn: %r" % (_e,))
    # ★ CFLAGS pe linia de comanda SUPRASCRIE `CFLAGS +=` din Makefile (make nu aduna la command-line
    #   vars) -> sub-make-ul libtommath pierdea -I spre dropbear/src ("dbmalloc.h not found").
    #   De aceea TOATE -I-urile si -DLOCALOPTIONS_H_EXISTS trebuie sa fie in CFLAGS-ul dat de noi.
    db_cflags = [e.get("CFLAGS", "")] + ["-I" + dbsrc + "/src", "-I" + dbsrc,
                                         "-DLOCALOPTIONS_H_EXISTS"]
    run([mk, "-C", dbsrc, "CFLAGS=" + " ".join(x for x in db_cflags if x.strip()),
         "PROGRAMS=dropbear dbclient dropbearkey dropbearconvert", "-j4",
         "dropbear", "dbclient", "dropbearconvert", "dropbearkey"],
        timeout=1800, label="make-dropbear")
    for b in ("dbclient", "dropbearconvert"):
        sp = dbsrc + "/" + b
        if os.path.exists(sp):
            shutil.copy2(sp, INS + "/bin/" + b)
            os.chmod(INS + "/bin/" + b, 0o755)

# ★ dropbear se construieste DUPA prima copiere -> recopiem binarele lui acum
for _b in ("dbclient", "dropbearconvert", "dropbearkey"):
    _s2 = INS + "/bin/" + _b
    if os.path.exists(_s2):
        shutil.copy2(_s2, G + "/bin/" + _b)
        os.chmod(G + "/bin/" + _b, 0o755)
log("DONE: git in %s (size %d)" % (G + "/bin/git", os.path.getsize(G + "/bin/git")))
log("VERIF: " + str(run([G + "/bin/git", "--version"], label="git-version")[1][:60]))
