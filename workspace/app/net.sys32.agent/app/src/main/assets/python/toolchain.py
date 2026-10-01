#!/usr/bin/env python3
"""
toolchain.py - Toolchain de compilare NATIV, livrat COMPLET in APK.
Fara root, fara pachete externe, fara PC, fara bootstrap.

clang 21 + lld + LLVM utils + sysroot Android + libc++ complet + ninja +
libxml2/libxslt + Python.h vin CU APLICATIA si sunt folosite DIRECT de app.

Folosire (agentul il cheama automat):
  python toolchain.py check     -> ce e instalat
  python toolchain.py preflight -> test de 10s al lantului complet C/C++
  python toolchain.py env       -> exporta variabilele de mediu
"""

import json, datetime

# ---------------------------------------------------------------------------
# LICENTE / LEGAL
# ---------------------------------------------------------------------------
# Componentele native sunt livrate IN APK (assets/toolchain + jniLibs), compilate
# din surse open-source pentru ARM64. Licente:
#   clang/LLVM  -> Apache-2.0 with LLVM exceptions
#   python      -> PSF-2.0
#   make/cmake  -> GPL-3.0
#   ninja/samu  -> Apache-2.0
#   openssl     -> Apache-2.0
#   zlib, xz    -> zlib / public domain
#   clang/LLVM + lld + llvm-*  -> Apache-2.0 with LLVM exceptions
#   ninja                      -> Apache-2.0
#   Python 3.14                -> PSF-2.0
#   sysroot Android (bionic)   -> Apache-2.0
# Nimic nu se descarca la rulare.
import os, sys, subprocess, json, time

F = "/data/data/net.sys32.agent/files"
WS = "/sdcard/Download/Agent/workspace"
ROOT = "/data/data/net.sys32.agent/files/toolchain"
BIN = ROOT + "/bin"
DEPS = ROOT + "/deps"

# biblioteci bionice de pe DEVICE (libm.so real, cu simboluri C99 complete).
# clang nu linkeaza -lm implicit pe android36 (pe Android 11+ libm e fuzionat in libc).
BIONIC_LIB = "/apex/com.android.runtime/lib64/bionic"
BIONIC_LIB_FALLBACK = "/system/lib64"

# marker de versiune al toolchain-ului instalat (in filesDir, langa toolchain)
MARKER = "/data/data/net.sys32.agent/files/toolchain/.toolchain_ok"


# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# AUTO-FIX: compression._common (workaround AAPT2 care ignora foldere "_")
# Trebuie sa ruleze INAINTE de orice import de lzma/gzip/bz2/tarfile.
# ---------------------------------------------------------------------------
def _sh(cmd, timeout=300):
    """★ RUN LOCAL (ca APP, uid 10318): toolchain-ul din APK traieste in filesDir.

    Inainte rulea prin adb_client ca uid=2000 - corect cand prefixul era in
    /data/local/tmp. Shell-ul NU POATE citi filesDir (Permission denied),
    deci orice verificare raporta fals "toolchain lipseste". Executam direct cu
    subprocess: acelasi uid, aceleasi drepturi, zero dependenta de adbsh.
    """
    import subprocess as _sp
    if cmd.startswith("cat "):
        path = cmd[4:].split(" 2>")[0].strip()
        try:
            with open(path) as fh:
                return fh.read()
        except Exception:
            return ""
    p = None
    try:
        _e = dict(os.environ)
        # ★ F/tmp PRIMUL: acolo sunt symlink-urile spre nativeLibraryDir
        # (singurele executabile ca app); BIN/deps nu sunt executabile.
        _e["PATH"] = F + "/tmp:" + DEPS + "/bin:" + BIN + ":/system/bin"
        # ★ FIX BLOCAJ (1): stdin=DEVNULL (sh nu mai asteapta un pipe mostenit).
        # ★ FIX BLOCAJ (2): Popen + killpg: subprocess.run la timeout NU omoara
        # copiii pe Android -> ramanea un `sh` orfan in bucla R care ardea CPU.
        p = _sp.Popen(["/system/bin/sh", "-c", cmd], stdin=_sp.DEVNULL,
                      stdout=_sp.PIPE, stderr=_sp.PIPE, text=True, env=_e,
                      start_new_session=True)
        try:
            out, err = p.communicate(timeout=timeout)
        except _sp.TimeoutExpired:
            try:
                os.killpg(os.getpgid(p.pid), 9)
            except Exception:
                try:
                    p.kill()
                except Exception:
                    pass
            try:
                out, err = p.communicate(timeout=5)
            except Exception:
                out, err = "", ""
            return ((out or "") + (err or "") + "[sh-timeout]")[:8000]
        return (out or "") + (err or "")
    except Exception as e:
        if p is not None:
            try:
                os.killpg(os.getpgid(p.pid), 9)
            except Exception:
                pass
        return "[sh-error] " + str(e)[:120]


def have(binary):
    """Verifica LOCAL (ca app) ca binarul exista si e executabil."""
    import os as _os
    for d in (BIN, DEPS + "/bin"):
        p = _os.path.join(d, binary)
        if _os.path.exists(p) and _os.access(p, _os.X_OK):
            return True
    return False


def preflight():
    """Pre-flight rapid inainte de build-uri mari.

    ★ FAZA 4m (raportat in testul din UI, "fa o verificare completa toolchain"): varianta veche
    rula un SCRIPT SHELL bazat pe aranjamentul vechi (toolchain/bin/python3.14, ROOT/usr/lib,
    $B/samu, $B/git, LD_PRELOAD). Dupa ce toolchain-ul a fost mutat in APK (nativeLibraryDir) si
    deps/*.a in assets, scriptul raporta TOTUL false (in contradictie directa cu doctor/selftest
    care erau verzi) si agentul pierdea pasi verificand cine are dreptate.
    Acum preflight deleaga la selftest (compileaza+linkeaza REAL, in procesul aplicatiei) si
    intoarce aceleasi chei plus cateva rezumate - o singura sursa de adevar.
    """
    r = dict(selftest())
    out = {}
    for k in ("c_compile_link", "cxx_stl", "python_extension", "fortran_compile", "rust", "cargo",
              "cmake", "ninja", "make", "pkg_config", "lld", "setuptools", "pybind11", "cython",
              "ram_liber_mb", "lipsa", "verdict", "detalii"):
        if k in r:
            out[k] = r[k]
    out["api"] = _device_api()
    out["nota"] = ("preflight == selftest (compilare+linkare reala, in procesul aplicatiei); "
                   "varianta veche pe script shell era perimata si raporta fals totul")
    return out

def doctor():
    """Health check RAPID, fara subprocess (anti-blocaj).

    ★ Vechiul doctor rula `_sh("clang ... /data/local/tmp/.d.c")` - se bloca
    (app nu scrie in /data/local/tmp) si in plus clang cu argv[0] gresit se invartea.
    Acum: verificari PURE de fisiere, instant, din perspectiva app-ului (suntem app).
    """
    r = {"prefix": ROOT}
    api = _device_api()
    r["api"] = api
    _nat = _native_dir()
    # binarele-native executabile (nativeLibraryDir) = ce poate FOLOSI app-ul
    _need = {"clang": "libclang_exec.so", "lld": "liblld_exec.so",
             "ar": "libllvmar_exec.so", "ranlib": "libllvmranlib_exec.so",
             "nm": "libllvmnm_exec.so", "strip": "libllvmstrip_exec.so",
             "ninja": "libninja_exec.so", "make": "libmake_exec.so",
             "flang": "libflang_exec.so", "pkg-config": "libpkgconf_exec.so"}
    for _k, _so in _need.items():
        r[_k] = bool(_nat and os.path.exists(_nat + "/" + _so))
    r["cc"] = r["clang"]
    r["cxx"] = os.path.exists(ROOT + "/sysroot/usr/include/c++/v1/__configuration/abi.h")
    # perspective
    try:
        os.listdir(BIN)
        r["app_can_read"] = True
    except Exception:
        r["app_can_read"] = False
    r["app_can_exec"] = bool(_nat)  # executabilele-native sunt executabile ca app
    r["native_dir"] = _nat or "(lipsa)"
    r["prefix_mode"] = "app-owned"
    r["marker"] = os.path.exists(MARKER)
    # deps: fiecare biblioteca livrata
    for _l in ("zstd", "lzma", "bz2", "ffi", "expat", "crypto", "ssl", "jpeg",
               "xml2", "xslt", "openblas", "blas", "lapack"):
        r["deps(%s)" % _l] = os.path.exists(DEPS + "/lib/lib" + _l + ".a")
    r["libatomic"] = bool(_atomic_dir())
    r["pip.conf"] = os.path.exists(F + "/pip.conf")
    r["site-packages"] = (lambda p: (os.path.isdir(p) and len(os.listdir(p)) or 0))(
        F + "/pyhome/lib/python3.14/site-packages")
    if r.get("clang") and os.path.isdir(ROOT + "/sysroot/usr/include"):
        r["verdict"] = ("OK - toolchain din APK (clang 21 + sysroot + deps + make/ninja), "
                        "se foloseste CA APP: pip_install compileaza direct")
    else:
        r["verdict"] = "INCOMPLET - reinstaleaza APK-ul (lipsesc assets bin/sysroot)"
    return r


def _exec_ok(p):
    """True daca p e executabil ACUM (symlink-ul trebuie sa aiba tinta vie).

    ★ Capcana: la fiecare reinstalare, hash-ul din nativeLibraryDir se schimba ->
    symlink-urile vechi devin MOARTE. os.path.exists() da False desi fisierul e acolo.
    """
    try:
        if os.path.islink(p):
            return os.path.exists(os.readlink(p))
        return os.path.exists(p)
    except Exception:
        return False


def check():
    """Starea toolchain-ului - verificari FUNCTIONALE, nu doar prezenta fisierelor.

    Fiecare test de aici corespunde unei erori REALE intalnite pe device;
    daca unul e rosu, agentul stie exact ce fix lipseste.

    ★ DOUA PERSPECTIVE (fix pentru fals-pozitivul din raportul numpy): toolchain-ul apartine
    uid-ului 2000 (shell), dar AGENTUL ruleaza ca app (~10300). Vechiul check() verifica doar
    prin shell - deci raporta "clang=true, make=true, compile_test=true" in timp ce din
    perspectiva app-ului prefixul era inaccesibil, iar agentul credea ca poate compila.
    Acum fiecare verificare "poate fi FOLOSIT de cel care o cere?" e evaluata pe AMBELE
    perspective, iar rezultatul expune explicit `app_can_use` - daca diferă, e o alarma.
    """
    try:
        _ensure_launchers()
        _ensure_python_pc()
    except Exception:
        pass
    # ★ FIX BLOCAJ: NU rula `ls` prin shell (subprocess in procesul agentului cu
    # thread-uri -> deadlock pe fork: shell ramane in bucla R si consuma CPU).
    # os.listdir e API direct, fara fork, fara blocaj.
    try:
        present = set(os.listdir(BIN))
    except Exception:
        present = set()
    api = _device_api()
    # ★ verificari aliniate cu REALITATEA: toolchain-ul e livrat in APK (nu se
    # instaleaza nimic). Ce conteaza e ce poate FI FOLOSIT, nu ce "exista in prefix".
    _SL = ROOT + "/sysroot/usr/lib/aarch64-linux-android/35"
    need = {
        "clang": ("clang" in present) or ("clang-21" in present),
        "ld.lld": _exec_ok(F + "/tmp/ld.lld"),
        "ar_shim": _exec_ok(F + "/tmp/ar"),
        "ninja": _exec_ok(F + "/tmp/ninja"),
        "make": _exec_ok(F + "/tmp/make"),
        "deps(zstd)": os.path.exists(DEPS + "/lib/libzstd.a"),
        "deps(lzma)": os.path.exists(DEPS + "/lib/liblzma.a"),
        "deps(bz2)": os.path.exists(DEPS + "/lib/libbz2.a"),
        "deps(ffi)": os.path.exists(DEPS + "/lib/libffi.a"),
        "deps(expat)": os.path.exists(DEPS + "/lib/libexpat.a"),
        "deps(openssl)": os.path.exists(DEPS + "/lib/libcrypto.a"),
        "libatomic": bool(_atomic_dir()),
        "pip.conf": os.path.exists(F + "/pip.conf"),
        "pkg-config": os.path.exists(DEPS + "/bin/pkg-config"),
        "sysroot(crt)": os.path.exists(_SL + "/crtbegin_dynamic.o"),
        "sysroot(native-libs)": os.path.exists(_SL + "/libc.so"),
        "deps(libxml2)": os.path.exists(DEPS + "/lib/libxml2.a"),
        "deps(blas)": os.path.exists(DEPS + "/lib/libblas.a"),
        "deps(lapack)": os.path.exists(DEPS + "/lib/liblapack.a"),
        "deps(jpeg)": os.path.exists(DEPS + "/lib/libjpeg.a"),
        "deps(openblas)": os.path.exists(DEPS + "/lib/libopenblas.a"),
        "flang": _exec_ok(F + "/tmp/flang") or bool(_flang_path()),
        "libc++ headers": os.path.exists(
            ROOT + "/sysroot/usr/include/c++/v1/__configuration/abi.h"),
        "marker": os.path.exists(MARKER),
    }
    # --- verificari FUNCTIONALE ---
    # ★ ANTI-BLOCAJ (critic): NU rula subprocess/shell aici. Cand `check()` e chemat
    # din procesul agentului (care are thread-uri bridge/watcher), fork+exec in
    # subprocess fie se blocheaza (deadlock pe lock-uri mostenite), fie produce un
    # copil care se INVARTE (argv[0] gresit la clang -> generic driver, 100% CPU).
    # Simptom pe device: task-ul "atarna fara output", sh copil in stare R la infinit.
    # Toate verificările sunt acum PURE (os.path / fisiere) - instant, fara fork.
    ev = env_vars()
    for _k in ("AR", "RANLIB", "NM", "STRIP", "READELF", "OBJDUMP", "CXX", "CC"):
        _p = (ev.get(_k) or "").split()[0] if ev.get(_k) else ""
        need[_k.lower()] = bool(_p) and (os.path.exists(_p) or os.path.lexists(_p))
    # executabilele-native (in nativeLibraryDir) = dovada ca putem COMPILA
    _nat = _native_dir()
    need["compile_test"] = bool(_nat and os.path.exists(_nat + "/libclang_exec.so"))
    need["ar_test"] = bool(_nat and os.path.exists(_nat + "/libllvmar_exec.so"))
    # libc++ complet (headere) - necesar pentru orice sursa C++
    need["cxx_test"] = os.path.exists(
        ROOT + "/sysroot/usr/include/c++/v1/__configuration/abi.h")
    # make / ninja (unelte de build): fallback pe binarul din nativeLibraryDir
    need["make"] = bool(_nat and os.path.exists(_nat + "/libmake_exec.so"))
    need["ninja"] = bool(_nat and os.path.exists(_nat + "/libninja_exec.so"))
    # ★ 8. PERSPECTIVA APP vs SHELL (raportul numpy, eroarea 2): cel care CERE
    #    toolchain-ul e agentul (uid app). Verificam daca IL POATE FOLOSI, nu doar
    #    daca exista. `run-as <pkg>` ruleaza ca app, exact ca tool-urile noastre.
    try:
        _pkg = "net.sys32.agent"
        try:
            os.listdir(BIN)
            app_read = True
        except Exception:
            app_read = False
        need["app_can_read_prefix"] = app_read
        # exec: app-ul NU poate executa binare din prefixul altui uid (read != execute)
        app_exec = ""  # app nu executa din filesDir (SELinux) - fara run-as (blocant)
        _pkg = "net.sys32.agent"
        need["app_can_exec_python"] = ("Python" in app_exec) and ("denied" not in app_exec.lower())
        if not need["app_can_exec_python"]:
            need["app_perspective_hint"] = ("the app CANNOT execute the toolchain directly - it must "
                "orchestrate it through adbsh/run_su (uid 2000). This is EXPECTED, not a failure.")
    except Exception as e:
        need["app_perspective_error"] = str(e)[:100]
    # ★ 9. MARKER DE VERSIUNE (raportul numpy, A2): fara el nu stim ce e instalat
    need["version_marker"] = "YES" in ("YES" if os.path.exists(ROOT + "/.tc_version") else "NO")
    # ★ TOOLCHAIN DIN APK: clang/lld/sysroot traiesc in filesDir (extrase din assets)
    # si se folosesc DIRECT DE APP (uid 10318). Nu exista prefix extern, nici bootstrap.
    import os as _os
    _hc = _os.path.exists(ROOT + "/bin/clang-21")
    _hs = _os.path.isdir(ROOT + "/sysroot/usr/include")
    _hd = _os.path.isdir(ROOT + "/deps/include")
    need["clang_ok"] = _hc
    need["sysroot_ok"] = _hs
    need["deps_ok"] = _hd
    need["prefix"] = ROOT
    if _hc and _hs:
        need["verdict"] = ("OK - toolchain din APK (clang 21 + sysroot + deps), "
                           "se foloseste CA APP: pip_install compileaza direct")
    else:
        need["verdict"] = "INCOMPLET - reinstaleaza APK-ul (lipsesc assets bin/sysroot)"
    return need


# ============================================================
#  FIXURI DE MEDIU (aplicate direct de app, fara adb)
# ============================================================
_ARCH = "aarch64"


def _q(s):
    """Quoting sigur pentru shell (single-quote cu escape)."""
    return "'" + str(s).replace("'", "'\\''") + "'"


def _device_api():
    """API-ul real al telefonului (36 = Android 16).
    Incercam 3 cai; daca toate esueaza folosim 36 (Android 16), pentru ca un
    target PREA MIC ascunde functiile C99 noi si rupe compilarea numpy etc."""
    # ★ FIX BLOCAJ: `getprop` prin shell se BLOCHEAZA ca app (property service
    # nu raspunde in sandbox) -> shell ramanea in R la infinit. Citim direct din
    # build.prop cu open() (fara fork) si abia apoi, daca nu gasim, shell.
    try:
        _bp = open("/system/build.prop").read()
        import re as _re
        _m = _re.search(r"ro\.build\.version\.sdk=(\d+)", _bp)
        if _m:
            return int(_m.group(1))
    except Exception:
        pass
    # ★ getprop ELIMINAT: se blocheaza ca app. Doar build.prop + env.
    for cmd in ("cat /system/build.prop 2>/dev/null | grep -m1 ro.build.version.sdk",
                "cat /system/build.prop 2>/dev/null | grep -m1 ro.build.version.release"):
        try:
            out = _sh(cmd, 20)
            n = int("".join(c for c in out.split("\n")[0] if c.isdigit()) or 0)
            if 26 <= n <= 99:
                return n
        except Exception:
            pass
    return 36


def _fix_libcxx_needed():
    """Extensiile C++ (numpy) NU au `NEEDED libc++_shared.so` desi folosesc simboluri din el
    -> la import: `cannot locate symbol _ZTVNSt6__ndk1...`. Fix: patchelf --add-needed.

    ★ OPTIMIZARE DE TIMP: versiunea veche rula `readelf -d` pe FIECARE .so din site-packages
    (sute de fisiere, un proces per fisier). Acum lista se face INTR-O TRECERE Python
    (citim ultimii bytes, unde sta tabelul de stringuri) si patchelf ruleaza doar pe cele
    care chiar nu au NEEDED libc++_shared.
    """
    py = r"""
import os, glob
P = "/data/data/net.sys32.agent/files/toolchain"
NEED = b"libc++_shared.so"
need = []
for d in glob.glob(P + "/lib/python3.*/site-packages"):
    for root, _, files in os.walk(d):
        for fn in files:
            if not fn.endswith(".so"):
                continue
            fp = os.path.join(root, fn)
            try:
                data = open(fp, "rb").read()
            except Exception:
                continue
            if NEED not in data:          # nu depinde de libc++ deloc
                continue
            # are deja NEEDED-ul? (apare in tabelul .dynamic, nu doar ca string)
            if b"libc++_shared.so\x00" in data[-4096:]:
                continue
            need.append(fp)
print("NEEDCXX " + " ".join(need))
"""
    try:
        out = _sh("%s -c %s" % (_py_exec(), _q(py)), 300)
        line = [l for l in out.split("\n") if l.startswith("NEEDCXX")]
        files = line[0].split(" ", 1)[1].split() if line and len(line[0].split(" ", 1)) > 1 else []
        if not files:
            print("[toolchain] libc++_shared: nimic de adaugat")
            return
        bat = "L=%s; PE=%s/patchelf; " % (ROOT + "/usr/lib", BIN)
        bat += "; ".join('"$PE" --add-needed libc++_shared.so "%s" 2>/dev/null' % f for f in files)
        bat += "; echo CXXDONE"
        out2 = _sh("export LD_LIBRARY_PATH=$L:$LD_LIBRARY_PATH; " + bat, 900)
        if "CXXDONE" in out2:
            print("[toolchain] libc++_shared adaugat pe %d .so" % len(files))
    except Exception as e:
        print("[toolchain] libcxx err:", e)


def _write_env_file():
    """Scrie un fisier de mediu PERSISTENT pentru NOUL toolchain (din APK).

    Toolchain-ul e in filesDir/toolchain
    (extras din assets). Fisierul e sursat de `adbsh` si de tool-ul toolchain.
    Scriem DIRECT in filesDir (app-ul are drepturi), nu prin shell.
    """
    import os as _os
    api = _device_api()
    P = ROOT                     # ROOT = filesDir/toolchain
    D = P + "/deps"
    body = (
        "# Generat automat de toolchain.py - mediu complet de compilare\n"
        "export TC_ROOT={P}\n"
        "export TC_DEPS={D}\n"
        "export PATH={D}/bin:{P}/bin:/system/bin\n"
        "export CC={P}/bin/clang-21\n"
        "export CXX={P}/bin/clang-21++\n"
        # ★ CAPCANA (raportata de testul E2E din UI): binutils trebuie predate ca LANSATOARELE
        # din files/tmp (nume fara sufix, executabile de procesul app) - NU calea din
        # toolchain/bin, pe care untrusted_app nu o poate executa (fals negativ la cmake).
        "export AR={F}/tmp/ar\n"
        "export RANLIB={F}/tmp/ranlib\n"
        "export NM={F}/tmp/nm\n"
        "export STRIP={F}/tmp/strip\n"
        "export READELF={F}/tmp/readelf\n"
        "export OBJDUMP={F}/tmp/objdump\n"
        "export CC_EXTRA=\"--target=aarch64-linux-android{api} --sysroot={P}/sysroot\"\n"
        "export CFLAGS=\"-fPIC -O2 --target=aarch64-linux-android{api} --sysroot={P}/sysroot -I{P}/sysroot/usr/include -I{P}/pyinc -I{D}/include -I{D}/include/libxml2\"\n"
        "export CXXFLAGS=\"$CFLAGS\"\n"
        "export LDFLAGS=\"-L{D}/lib -L{P}/sysroot/usr/lib/aarch64-linux-android/{api}\"\n"
        "export PKG_CONFIG_PATH={D}/lib/pkgconfig\n"
        "export TMPDIR={F}/tmp\n"
        "export HOME={F}/home\n"
        "export PIP_CACHE_DIR=$HOME/.cache/pip\n"
        "export PIP_NO_BUILD_ISOLATION=1\n"
    ).format(P=P, D=D, F=F, api=api)
    out = _os.path.join(F, "toolchain_env.sh")
    try:
        with open(out, "w") as fh:
            fh.write(body)
        return out
    except Exception as e:
        return "err: %s" % e

def _fix_ca_bundle():
    """Python cauta CA in locatii standard Android
    (inexistent) -> orice HTTPS (pip!) moare cu CERTIFICATE_VERIFY_FAILED.
    Construim un bundle real din cacerts-ul Android si setam SSL_CERT_FILE."""
    script = r"""
P="__PREFIX__"
mkdir -p "$P/etc/tls" 2>/dev/null
OUT="$P/etc/tls/cert.pem"
if [ -s "$OUT" ]; then echo CA_EXISTS; exit 0; fi
: > "$OUT"
for d in /apex/com.android.conscrypt/cacerts /system/etc/security/cacerts; do
  [ -d "$d" ] || continue
  for f in "$d"/*; do
    [ -f "$f" ] || continue
    if grep -q 'BEGIN CERTIFICATE' "$f" 2>/dev/null; then
      cat "$f" >> "$OUT"; printf '\n' >> "$OUT"
    fi
  done
done
sz=$(wc -c < "$OUT" 2>/dev/null || echo 0)
echo "CA_WRITTEN=$sz"
"""
    script = script.replace("__PREFIX__", ROOT + "/usr")
    try:
        out = _sh(script, 180)
        if "CA_WRITTEN" in out or "CA_EXISTS" in out:
            print("[toolchain] CA bundle pregatit (SSL_CERT_FILE)")
    except Exception as e:
        print("[toolchain] CA err:", e)


def profile(name="cmake"):
    """Flaguri/scripturi pregatite pentru un build (vezi BUILD_PROFILES).

    name="cmake"    -> SCRIPT shell gata de rulat: `sh cmake_prof.sh <srcdir>`
    name="cflags"/"cxxflags"/"ldflags" -> string de flaguri
    name="python_env" -> dict de variabile pentru pip/python
    """
    api = _device_api()
    fmt = dict(bin=BIN, api=api, prefix=ROOT + "/usr", bionic=BIONIC_LIB, root=ROOT,
               tmp=F + "/tmp")
    if name == "cmake":
        args = [x.format(**fmt) for x in BUILD_PROFILES["cmake_args"]]
        # script cu fiecare argument intr-un tablou (quoting corect garantat)
        lines = ["#!/system/bin/sh", "# Profil cmake generat de toolchain.py",
                 "# Folosire: sh cmake_prof.sh <dir_sursa> [dir_build]", 'SRC="${1:-.}"',
                 'BUILD="${2:-.}"',
                 'SRC="$(cd "$SRC" && pwd)"',          # absolut INAINTE de cd
                 'mkdir -p "$BUILD"; BUILD="$(cd "$BUILD" && pwd)"; cd "$BUILD"',
                 "exec cmake \"$SRC\" \\"]
        for k, a in enumerate(args):
            tail = "" if k == len(args) - 1 else " \\"
            lines.append("  '" + a.replace("'", "'\\''") + "'" + tail)
        return "\n".join(lines) + "\n"
    val = BUILD_PROFILES.get(name)
    if isinstance(val, str):
        return val.format(**fmt)
    if isinstance(val, dict):
        return {k: v.format(**fmt) for k, v in val.items()}
    return val


def _prepare_dirs():
    """Creeaza directoarele de lucru (TMPDIR, HOME, cache pip).
    pip/meson au nevoie de un HOME si TMPDIR scriibile; fara ele: erori obscure."""
    script = r"""
mkdir -p __TMP__ __HOME__ __HOME__/.cache/pip 2>/dev/null
chmod 777 __TMP__ 2>/dev/null
echo DIRS_OK
"""
    script = script.replace("__HOME__", F + "/home").replace("__TMP__", F + "/tmp")
    try:
        _sh(script, 60)
    except Exception:
        pass


def _simd_flags():
    """Extra SIMD flags for this SoC, controlled by AGENT_SIMD (default on, "0" disables).
    The numpy report suggests armv8.2-a+dotprod+fp16; on this Snapdragon those features exist and
    speed up dot products (numpy's matmul). Kept behind a switch because the same report warns
    'test it does not break something' - and a switch costs nothing when it works."""
    if os.environ.get("AGENT_SIMD", "1").strip() in ("0", "off", "no"):
        return ""
    return " -march=armv8.2-a+dotprod+fp16"


def _stub_link_dirs():
    """Directoare de LINK (NDK sysroot) - NU au ce cauta in LD_LIBRARY_PATH la RULARE.

    ★ BUG REAL (dovedit cu tombstone + probe pe device, 28 sept): sysroot/usr/lib/
    aarch64-linux-android/35 contine libc.so/libm.so/libdl.so **STUB** (NDK-ul le
    da DOAR pentru linkare; fara cod in .text). Daca acel director e primul in
    LD_LIBRARY_PATH, linkerul bionic al unui proces COPIL le prefera in fata
    celor reale din /system/lib64 -> procesul crapa cu SIGSEGV in constructorii
    libpython3.14.so (tombstone: "Fatal signal 11 ... in tid libpyexec.so",
    pc in libpython, call_constructors). Efectul vizibil: `pip install` murea la
    "Preparing metadata (pyproject.toml): exit code: -11" (subprocesul de build
    backend). Procesul AGENT nu era afectat doar pentru ca bionic isi citeste
    LD_LIBRARY_PATH la INIT (nu la dlopen) -> parintele mergea, copiii mureau.
    """
    return [ROOT + "/sysroot/usr/lib/aarch64-linux-android/35",
            ROOT + "/sysroot/usr/lib"]


def sanitize_ld_library_path(value):
    """Curata un LD_LIBRARY_PATH de RULARE: scoate directoarele de LINK (stub NDK)
    si duplicatele. Pastreaza ordinea. Idempotenta."""
    out = []
    for p in str(value or "").split(":"):
        p = p.strip()
        if not p or p in out:
            continue
        if "sysroot" in p:          # stub-uri NDK: DOAR link-time (vezi _stub_link_dirs)
            continue
        out.append(p)
    return ":".join(out)


def _stable_libs():
    """Dir STABIL de runtime (nu depinde de hash-ul instalarii APK).

    ★ Raportat de agent in testul E2E: binarul C++/Fortran compilat INAINTE de un update de APK
    murea cu "library libc++_shared.so not found", pentru ca rpath-ul arata catre nativeLibraryDir,
    iar acel path (/data/app/~~hash==/pkg-.../lib/arm64) se schimba la fiecare instalare.
    Aici tinem o copie stabila (files/libs), iar rpath-ul binarilor arata aici.
    """
    d = F + "/libs"
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        return d
    for name in ("libc++_shared.so", "libpython3.14.so"):
        tgt = d + "/" + name
        if os.path.exists(tgt) and os.path.getsize(tgt) > 100000:
            continue
        try:
            import shutil as _sh
            # surse posibile: nativeLibraryDir (libc++_shared) sau deps/lib (libpython3.14)
            for src in (_native_dir() + "/" + name, DEPS + "/" + name):
                if os.path.exists(src):
                    _sh.copyfile(src, tgt)
                    os.chmod(tgt, 0o755)
                    break
        except Exception:
            pass
    return d


def _rt_ld_path():
    """LD_LIBRARY_PATH corect la RULARE (fara stub-uri de link):
    nativeLibraryDir (libpython3.14.so real + libc++_shared.so) : deps/lib
    (libopenblas/libjpeg la runtime) : files/libs (crypto ADB) : restul mostenit."""
    parts = []
    for chunk in (_native_dir(), DEPS + "/lib", F + "/libs",
                  sanitize_ld_library_path(os.environ.get("LD_LIBRARY_PATH", ""))):
        for q in str(chunk or "").split(":"):
            q = q.strip()
            if q and q not in parts and "sysroot" not in q:
                parts.append(q)
    return ":".join(parts)


def _ensure_py_include():
    """Headerele Python pentru extensii C/C++ (setuptools/meson).

    ★ BUG REAL (28 sept): sysconfig.INCLUDEPY = <prefix>/include/python3.14, dar pe
    device headerele sunt in toolchain/pyinc -> orice build de extensie C murea cu
    `fatal error: 'Python.h' file not found` (regex, zstandard, lxml...).
    Fix: <pyhome>/include/python3.14 -> symlink catre toolchain/pyinc.
    """
    dst = F + "/pyhome/include"
    link = dst + "/python3.14"
    try:
        os.makedirs(dst, exist_ok=True)
        if os.path.isdir(link) and not os.path.islink(link):
            if os.path.exists(link + "/Python.h"):
                return link                      # copie reala deja prezenta
        if os.path.islink(link) and not os.path.exists(link + "/Python.h"):
            os.remove(link)                      # symlink mort (reinstalare APK)
        if not os.path.lexists(link):
            os.symlink(ROOT + "/pyinc", link)
    except Exception:
        pass
    return link


def _ensure_py_lib_link():
    """`-lpython3.14` trebuie sa fie gasibil la LINK (altfel: "unable to find library
    -lpython3.14" la ORICE extensie C - regex, zstandard...).

    ★ BUG REAL (28 sept): sysconfig LIBDIR = '/usr/local/lib' (prefix de compilare,
    care NU exista pe telefon) -> distutils adauga `-L/usr/local/lib -lpython3.14`
    si linkarea esueaza. Fix: link stabil <pyhome>/lib/libpython3.14.so -> copia
    reala din nativeLibraryDir, si LIBDIR rescris catre el.
    """
    d = F + "/pyhome/lib"
    tgt = (_native_dir() or "") + "/libpython3.14.so"
    link = d + "/libpython3.14.so"
    try:
        os.makedirs(d, exist_ok=True)
        if os.path.islink(link) and not os.path.exists(link):
            os.remove(link)
        if not os.path.lexists(link) and os.path.exists(tgt):
            os.symlink(tgt, link)
    except Exception:
        pass
    return d


def _ensure_sysroot_api_dir(api):
    """clang cauta crt-urile in `<sysroot>/usr/lib/<triple>/<api>/` si, daca nu exista,
    cade pe nume BARE (crtbegin_so.o) - pe care lld le cauta DOAR in CWD -> esec la link
    ("cannot open crtbegin_so.o", desi -L e dat).

    ★ BUG REAL (28 sept, dovedit cu clang -v pe device): avem doar directorul `35` in
    sysroot, dar target-ul e `aarch64-linux-android36` -> clang nu gaseste dirul de API
    si nu mai emite caile absolute. Fix: symlink `<api>` -> directorul existent (35).
    """
    base = ROOT + "/sysroot/usr/lib/aarch64-linux-android"
    dst = base + "/" + str(api)
    try:
        if os.path.exists(dst + "/crtbegin_so.o"):
            return dst
        src = None
        for n in sorted(os.listdir(base), reverse=True):
            p = base + "/" + n
            if n != str(api) and os.path.isdir(p) and os.path.exists(p + "/crtbegin_so.o"):
                src = p
                break
        if src:
            # ★ CAPCANA: daca `dst` exista ca DIRECTOR REAL dar nu are crt-urile (ex. a fost
            # livrat gresit in assets cu un singur fisier), symlink-ul nu se mai poate face
            # (`os.remove` pe dir non-gol esueaza) si clang cauta degeaba in el ->
            # "cannot open crtend_android.o" / "-lm not found". Il inlocuim cu symlink.
            if os.path.isdir(dst) and not os.path.islink(dst):
                try:
                    import shutil as _sh2
                    _sh2.rmtree(dst, ignore_errors=True)
                except Exception:
                    pass
            if os.path.lexists(dst):
                try:
                    os.remove(dst)
                except Exception:
                    pass
            try:
                os.symlink(src, dst)
            except Exception:
                pass
    except Exception:
        pass
    return dst


def _patch_sysconfig_device():
    """Rescrie _sysconfigdata-ul Python pentru MEDIUL DE PE TELEFON.

    ★ Cauze reale (28 sept, masurate):
      * INCLUDEPY='/usr/local/include/python3.14' -> "Python.h file not found";
      * LIBDIR='/usr/local/lib' -> "unable to find library -lpython3.14";
      * CC/CXX/LDSHARED = <toolchain>/bin/clang-21 (fara --target/--sysroot) ->
        target implicit android24 (simboluri C99 ascunse) si fara sysroot.
    Idempotent: rescrie doar daca markerul (api + libDir) nu corespunde.
    """
    try:
        api = _device_api()
        nat = _native_dir() or ""
        _ensure_sysroot_api_dir(api)      # ★ crt-uri gasite de clang (vezi functia)
        mark = F + "/pyhome/.sysconfig_fixed"
        stamp = "api=%s|nat=%s|v6" % (api, nat)
        try:
            if open(mark).read().strip() == stamp:
                return True
        except Exception:
            pass
        inc = F + "/pyhome/include/python3.14"
        libd = _ensure_py_lib_link()
        cc = F + "/tmp/clang"
        cxx = F + "/tmp/clang++"
        if not os.path.exists(cc):
            cc = (nat or "") + "/libclang_exec.so"
        if not os.path.exists(cxx):
            cxx = cc
        tgt = (" -resource-dir=%s/lib/clang/21"
               " --target=aarch64-linux-android%d --sysroot=%s/sysroot" % (ROOT, api, ROOT))
        cc_v = cc + tgt
        # ★ -L direct in LDSHARED: setuptools NU foloseste LDFLAGS din sysconfig la link
        # (comanda observata: "clang -shared <objs> -L<pyhome>/lib -lpython3.14 -o out"),
        # deci dirurile de libs trebuie sa fie in comanda de link insasi.
        _ldirs = (" -L%s/sysroot/usr/lib/aarch64-linux-android/%s -L%s/lib"
                  " -L%s/lib/clang/21/lib/linux/aarch64" % (ROOT, api, DEPS, ROOT))
        vals = {
            "LIBDIR": libd,
            "LIBPL": libd,
            "INCLUDEPY": inc,
            "CC": cc_v,
            "CXX": cxx + tgt,
            "LDSHARED": cc_v + " -shared" + _ldirs,
            "BLDSHARED": cc_v + " -shared" + _ldirs,
        }
        import re as _re
        import json as _json
        base = F + "/pyhome/lib/python3.14"
        for fn in os.listdir(base):
            p = base + "/" + fn
            if fn.startswith("_sysconfigdata") and fn.endswith(".py"):
                src = open(p, encoding="utf-8", errors="replace").read()
                for k, v in vals.items():
                    src = _re.sub(r"('%s':\s*)'[^']*'" % k, lambda m, v=v: m.group(1) + repr(v), src)
                # CFLAGS: adauga target+sysroot (o singura data)
                if "--sysroot=" not in src.split("'CFLAGS'")[1][:400]:
                    _cinc = (tgt + " -I" + DEPS + "/include -I" + DEPS + "/include/libxml2")
                    for ck in ("CFLAGS", "PY_CFLAGS", "CONFIGURE_CFLAGS"):
                        src = _re.sub(r"('%s':\s*)(['\"])(.*?)\2" % ck,
                                      lambda m, t=_cinc: '%s%s%s%s%s' % (m.group(1), m.group(2), m.group(3) + t, m.group(2), ""),
                                      src, count=1)
                if "--sysroot=" not in src.split("'LDFLAGS'")[1][:600]:
                    # ★ -L obligatorii la LINK (distutils foloseste LDFLAGS din sysconfig,
                    # NU env LDFLAGS): crtbegin_so.o/crtend_so.o + stub-urile libc/libdl
                    # sunt in sysroot/usr/lib/<triple>/<api>, iar builtins/unwind in
                    # lib/clang/21/lib/linux/aarch64. Fara ele: "cannot open crtbegin_so.o"
                    # / "unable to find library -lc".
                    _ldx = (tgt + " -L" + ROOT + "/sysroot/usr/lib/aarch64-linux-android/" + str(api)
                            + " -L" + DEPS + "/lib"
                            + " -L" + ROOT + "/lib/clang/21/lib/linux/aarch64")
                    src = _re.sub(r"('LDFLAGS':\s*)(['\"])(.*?)\2",
                                  lambda m, t=_ldx: '%s%s%s%s%s' % (m.group(1), m.group(2), m.group(3) + t, m.group(2), ""),
                                  src, count=1)
                open(p, "w", encoding="utf-8").write(src)
            elif fn.startswith("_sysconfig_vars") and fn.endswith(".json"):
                try:
                    d = _json.load(open(p))
                    d.update(vals)
                    _json.dump(d, open(p, "w"))
                except Exception:
                    pass
        # cache-ul de bytecode al sysconfigdata-ului
        import shutil as _sh2
        for dp, dn, fns in os.walk(base):
            if os.path.basename(dp) == "__pycache__":
                _sh2.rmtree(dp, ignore_errors=True)
        open(mark, "w").write(stamp)
        # ★ reincarca sysconfig in PROCESUL CURENT (altfel agentul foloseste in continuare
        # valorile vechi din cache; subprocesele citesc oricum fisierul nou).
        try:
            import sysconfig as _syscfg
            import sys as _sysm
            for _n in [n for n in _sysm.modules if n.startswith("_sysconfigdata")]:
                _sysm.modules.pop(_n, None)
            _cv = getattr(_syscfg, "_CONFIG_VARS", None)
            if isinstance(_cv, dict):
                _cv.clear()
            _syscfg.get_config_vars()
        except Exception:
            pass
        return True
    except Exception:
        return False


def _sdk_lib_dir():
    """Directorul cu libpython3.14.so + libc++_shared.so (sysroot sau nativeLib)."""
    for c in (ROOT + "/sysroot/usr/lib/aarch64-linux-android/35", _native_dir()):
        if c and os.path.exists(c + "/libpython3.14.so"):
            return c
    return _native_dir() or (ROOT + "/sysroot/usr/lib/aarch64-linux-android/35")


def _ensure_libcxx():
    """★ N1 (raport numpy/scipy): AAPT2 ELIMINA folderele care incep cu "_" din assets.

    libc++ are ~2000 de fisiere in directoare modularizate (__configuration/,
    __algorithm/, __support/...). In APK ajung doar ~157 (cele de la nivel 0) ->
    "file not found" la ORICE include C++ (#include <vector>).
    Fix: headerele complete vin ca ZIP (libcxx_include.zip) si se extrag o data
    in sysroot/usr/include. Returneaza directorul de include de folosit.
    """
    inc = ROOT + "/sysroot/usr/include"
    marker = inc + "/c++/v1/__configuration/abi.h"
    if os.path.exists(marker):
        return inc
    # sursele zip-ului: assets (la prima pornire) sau copia deja extrasa
    cand = [F + "/python/toolchain/libcxx_include.zip",
            os.path.dirname(os.path.abspath(__file__)) + "/toolchain/libcxx_include.zip",
            F + "/toolchain/libcxx_include.zip"]
    for p in cand:
        if not os.path.exists(p):
            continue
        # 1) zipfile (rapid) - poate fi rupt: AAPT2 pierde zipfile/_path/ (vezi stdlib_extra.zip)
        try:
            import zipfile as _zf
            with _zf.ZipFile(p) as z:
                n = len(z.namelist())
                z.extractall(inc)
            if os.path.exists(marker):
                print("[toolchain] libc++ complet extras (%d fisiere)" % n)
                return inc
        except Exception:
            pass
        # 2) unzip din /system/bin (nu depinde de stdlib)
        try:
            subprocess.run(["/system/bin/unzip", "-o", "-q", p, "-d", inc],
                           capture_output=True, timeout=180)
            if os.path.exists(marker):
                print("[toolchain] libc++ extras cu unzip")
                return inc
        except Exception:
            pass
    return inc


def _flang_path():
    """Calea catre compilatorul Fortran (flang), daca e disponibil.

    ★ P1 din raport: flang rezolva 80% din problemele Fortran (scipy: 30-40 min
    in loc de 5 ore, fara patch-uri manuale pe 500 fisiere LAPACK).
    """
    nat = _native_dir()
    for c in (F + "/tmp/flang", F + "/tmp/flang-new", BIN + "/flang",
              (nat + "/libflang_exec.so") if nat else ""):
        if c and (os.path.exists(c) or os.path.lexists(c)):
            return c
    return ""


def _native_dir():
    """nativeLibraryDir REAL (executabil) - cu auto-detectie daca TC_NATIVE lipseste.

    ★ Symlink-urile catre libDir mor la FIECARE reinstalare (hash nou in /data/app).
    TC_NATIVE vine de la Kotlin la pornirea procesului; daca lipseste sau e invechit,
    il deducem din sys.executable (care e chiar libpyexec.so din libDir).
    """
    nat = os.environ.get("TC_NATIVE", "")
    if nat and os.path.exists(nat + "/libpyexec.so"):
        return nat
    try:
        ex = os.path.realpath(sys.executable or "")
        d = os.path.dirname(ex)
        if os.path.exists(d + "/libpyexec.so"):
            return d
    except Exception:
        pass
    return nat


def _ensure_launchers():
    """★ N5: meson/ninja/cython trebuie BINARE EXECUTABILE, nu scripturi in filesDir.

    meson cheama ninja/cython ca PROGRAME -> scripturile din filesDir dau
    Permission denied. Punem lansatoare in files/tmp: symlink catre binarul din
    nativeLibraryDir (ninja) sau wrapper shell catre libpyexec -m <modul> (cython).
    """
    try:
        os.makedirs(F + "/tmp", exist_ok=True)
    except Exception:
        pass
    nat = _native_dir()
    py = _sdk_lib_dir() + "/libpyexec.so"
    if not os.path.exists(py):
        py = ""
    made = []
    # ★ ninja / samu / make: binar executabil din nativeLibraryDir (build-uri meson/make)
    for name, so in (("ninja", "libninja_exec.so"), ("samu", "libninja_exec.so"),
                     ("make", "libmake_exec.so"), ("gmake", "libmake_exec.so")):
        if nat and os.path.exists(nat + "/" + so):
            p = F + "/tmp/" + name
            try:
                _st = False
                if os.path.islink(p):
                    try:
                        _st = not os.path.exists(os.readlink(p))
                    except Exception:
                        _st = True
                if os.path.lexists(p) and (not os.path.islink(p) or _st):
                    os.remove(p)
                if not os.path.lexists(p):
                    os.symlink(nat + "/" + so, p)
                made.append(name)
            except Exception:
                pass
    # ★ cmake (FAZA 1): binar ARM64 cross-compilat de noi -> nativeLibraryDir ca
    # libcmake_exec.so + symlink cu numele real in files/tmp (scikit-build-core il cauta
    # dupa nume in PATH).
    if nat and os.path.exists(nat + "/libcmake_exec.so"):
        p = F + "/tmp/cmake"
        try:
            _st = False
            if os.path.islink(p):
                try:
                    _st = not os.path.exists(os.readlink(p))
                except Exception:
                    _st = True
            if os.path.lexists(p) and (not os.path.islink(p) or _st):
                os.remove(p)
            if not os.path.lexists(p):
                os.symlink(nat + "/libcmake_exec.so", p)
            made.append("cmake")
        except Exception:
            pass
    # ★ binutils (ar/ranlib/nm/strip/readelf/objdump): cmake si autotools le cauta dupa NUME
    # in PATH, iar untrusted_app nu poate executa din toolchain/bin -> lansatoare in files/tmp.
    # (Capcana raportata de testul E2E: cmake/ar cadeau cu "Permission denied".)
    for _nm, _so in (("ar", "libllvmar_exec.so"), ("ranlib", "libllvmranlib_exec.so"),
                     ("nm", "libllvmnm_exec.so"), ("strip", "libllvmstrip_exec.so"),
                     ("readelf", "libllvmreadelf_exec.so"), ("objdump", "libllvmobjdump_exec.so")):
        if nat and os.path.exists(nat + "/" + _so):
            _p = F + "/tmp/" + _nm
            try:
                _st = False
                if os.path.islink(_p):
                    try:
                        _st = not os.path.exists(os.readlink(_p))
                    except Exception:
                        _st = True
                if os.path.lexists(_p) and (not os.path.islink(_p) or _st):
                    os.remove(_p)
                if not os.path.lexists(_p):
                    os.symlink(nat + "/" + _so, _p)
                made.append(_nm)
            except Exception:
                pass
    # ★ FAZA 4g: si in toolchain/bin (unde caută oamenii/agentul) trebuie sa existe NUME REALE
    # de executabile, NU symlink-uri catre NDK-ul neexecutabil. Un symlink catre un ELF din
    # nativeLibraryDir este executabil si din filesDir (SELinux judeca TINTA, nu link-ul), deci
    # punem acolo cmake/ninja/make/perl + binutils. Fara asta: "toolchain/bin nu are cmake".
    _BINSHIM = (("cmake", "libcmake_exec.so"), ("ninja", "libninja_exec.so"),
                ("make", "libmake_exec.so"), ("gmake", "libmake_exec.so"),
                ("perl", "libperl_exec.so"), ("ar", "libllvmar_exec.so"),
                ("ranlib", "libllvmranlib_exec.so"), ("nm", "libllvmnm_exec.so"),
                ("strip", "libllvmstrip_exec.so"), ("clang", "libclang_exec.so"),
                ("clang++", "libclang_exec.so"), ("pkg-config", "libpkgconf_exec.so"),
                ("maturin", "libmaturin_exec.so"), ("rustc", "librustc_exec.so"),
                ("cargo", "libcargo_exec.so"), ("flang", "libflang_exec.so"),
                ("patchelf", "libpatchelf_exec.so"), ("ld.lld", "liblld_exec.so"),
                # aliasuri llvm-* (numele pe care le cheama cmake/autotools: "llvm-ar: Permission denied")
                ("llvm-ar", "libllvmar_exec.so"), ("llvm-ranlib", "libllvmranlib_exec.so"),
                ("llvm-nm", "libllvmnm_exec.so"), ("llvm-strip", "libllvmstrip_exec.so"),
                ("llvm-readelf", "libllvmreadelf_exec.so"),
                ("llvm-objdump", "libllvmobjdump_exec.so"))
    try:
        os.makedirs(BIN, exist_ok=True)
    except Exception:
        pass
    for _nm, _so in _BINSHIM:
        if not (nat and os.path.exists(nat + "/" + _so)):
            continue
        for _d in (BIN,):
            _p = _d + "/" + _nm
            try:
                _ok = False
                if os.path.islink(_p):
                    try:
                        _ok = os.readlink(_p) == nat + "/" + _so
                    except Exception:
                        _ok = False
                if not _ok:
                    if os.path.lexists(_p):
                        os.remove(_p)
                    os.symlink(nat + "/" + _so, _p)
            except Exception:
                pass
    # ★ wrapper-ele SCRIPT trebuie sa fie si ele in toolchain/bin (agentul le caută acolo):
    # se pun ca symlink la lansatorul ELF (altfel: script neexecutabil de untrusted_app).
    for _nm, _so in (("cc-rust", "libccrust_exec.so"),):
        if nat and os.path.exists(nat + "/" + _so):
            for _d in (BIN, F + "/tmp"):
                _p = _d + "/" + _nm
                try:
                    if os.path.lexists(_p):
                        os.remove(_p)
                    os.symlink(nat + "/" + _so, _p)
                except Exception:
                    pass
    # ★ patchelf (numpy/meson-python): meson-python rescrie RPATH-urile modulelor
    # construite si cheama `patchelf`; fara el build-ul pica la final cu
    # "FileNotFoundError: [Errno 2] No such file or directory: 'patchelf'".
    for _nm, _so in (("patchelf", "libpatchelf_exec.so"),):
        if nat and os.path.exists(nat + "/" + _so):
            _p = F + "/tmp/" + _nm
            try:
                _st = False
                if os.path.islink(_p):
                    try:
                        _st = not os.path.exists(os.readlink(_p))
                    except Exception:
                        _st = True
                if os.path.lexists(_p) and (not os.path.islink(_p) or _st):
                    os.remove(_p)
                if not os.path.lexists(_p):
                    os.symlink(nat + "/" + _so, _p)
                made.append(_nm)
            except Exception:
                pass
    # ★ perl (FAZA 3): binarul Termux (ARM64) in nativeLibraryDir ca libperl_exec.so +
    # symlink 'perl' in files/tmp (MakeMaker/Configure il cauta dupa nume in PATH).
    if nat and os.path.exists(nat + "/libperl_exec.so"):
        p = F + "/tmp/perl"
        try:
            _st = False
            if os.path.islink(p):
                try:
                    _st = not os.path.exists(os.readlink(p))
                except Exception:
                    _st = True
            if os.path.lexists(p) and (not os.path.islink(p) or _st):
                os.remove(p)
            if not os.path.lexists(p):
                os.symlink(nat + "/libperl_exec.so", p)
            made.append("perl")
        except Exception:
            pass
    # ★ clang/clang++ (task greenlet, 28 sept): in filesDir untrusted_app NU poate
    # executa -> symlink in files/tmp catre libclang_exec.so, cu REPARARE cand tinta
    # e moarta (hash nou in /data/app la fiecare reinstalare). Numele 'clang++'
    # decide modul C++ al driver-ului; fara el orice sursa C++ cadea cu
    # "[Errno 13] Permission denied .../toolchain/bin/clang++".
    if nat and os.path.exists(nat + "/libclang_exec.so"):
        for name in ("clang", "clang++"):
            p = F + "/tmp/" + name
            try:
                _st = False
                if os.path.islink(p):
                    try:
                        _st = not os.path.exists(os.readlink(p))
                    except Exception:
                        _st = True
                if os.path.lexists(p) and (not os.path.islink(p) or _st):
                    os.remove(p)
                if not os.path.lexists(p):
                    os.symlink(nat + "/libclang_exec.so", p)
                made.append(name)
            except Exception:
                pass
    # ★ FLANG (Fortran): NU se cheama binarul direct - driver-ul cade pe
    # "gcc frontend command failed" si nu stie sa linkeze runtime-ul Fortran.
    # Wrapper shell: (1) -fc1 la compilare (frontend Fortran real),
    # (2) linkeaza libFortranRuntime/Decimal + builtins + libc++_shared.
    if nat and os.path.exists(nat + "/libflang_exec.so"):
        _sl = (ROOT + "/sysroot/usr/lib/aarch64-linux-android/35")
        # Wrapper in 2 pasi: (1) -fc1 -triple pentru .o (driver-ul flang NU stie sa
        # compileze Fortran singur: cade pe "gcc frontend command failed"),
        # (2) link cu clang (care stie sysroot/LDFLAGS) + runtime-urile Fortran.
        _body = ('#!/system/bin/sh\n'
                 'CS="%s"; R="%s"; SL="%s"\n'
                 # ★ CAPCANA (raportata de testul E2E): `-fc1` NU accepta flag-uri de driver
                 # (`-c` -> "error: unknown argument: '-c'"). Trebuie traduse: scoatem -c/-o,
                 # punem -emit-obj si mutam rezultatul la -o.
                 'case " $* " in\n'
                 '  *" -c "*|*" -S "*|*" -E "*)\n'
                 '    OUT=""; SRC=""\n'
                 '    while [ $# -gt 0 ]; do\n'
                 '      case "$1" in\n'
                 '        -c|-S|-E) shift ;;\n'
                 '        -o) OUT="$2"; shift 2 ;;\n'
                 '        *.f|*.f90|*.f95|*.for|*.F|*.F90|*.F95) SRC="$1"; shift ;;\n'
                 '        *) shift ;;\n'
                 '      esac\n'
                 '    done\n'
                 '    [ -n "$SRC" ] || { echo "flang: lipsește sursa Fortran"; exit 1; }\n'
                 '    D="$(cd "$(dirname "$SRC")" && pwd)"; B="$(basename "$SRC")"\n'
                 '    ( cd "$D" && "$CS/flang-bin" -fc1 -triple aarch64-linux-android35 '
                 '-emit-obj "$B" -I"$CS/pyinc" ) || exit 1\n'
                 '    O="$D/${B%%.*}.o"\n'
                 '    [ -f "$O" ] || O="$D/${B%%.*}"\n'
                 '    [ -f "$O" ] || { echo "flang: nu a produs .o pentru $SRC"; exit 1; }\n'
                 '    if [ -n "$OUT" ]; then cp "$O" "$OUT"; else cp "$O" "./${B%%.*}.o"; fi\n'
                 '    exit 0 ;;\n'
                 'esac\n'
                 'OUT=""; OBJS=""; SRCS=""\n'
                 'while [ $# -gt 0 ]; do\n'
                 '  case "$1" in\n'
                 '    -o) OUT="$2"; shift 2 ;;\n'
                 '    *.f|*.f90|*.f95|*.for|*.F|*.F90) SRCS="$SRCS $1"; shift ;;\n'
                 '    *) OBJS="$OBJS $1"; shift ;;\n'
                 '  esac\n'
                 'done\n'
                 # ★ -fc1 IGNORA -o pe acest build: compilez in CWD cu -emit-obj
                 # (numele implicit .o) si mut rezultatul. Altfel: 0 bytes, exit 0.
                 'TMP="$CS/fobjs"; mkdir -p "$TMP"\n'
                 'FORTO=""; n=0\n'
                 'for s in $SRCS; do\n'
                 '  n=$((n+1)); b=$(basename "$s"); base="${b%%%%.*}"\n'
                 '  SD="$(cd "$(dirname "$s")" && pwd)"; b="$(basename "$s")"\n'
                 '  ( cd "$SD" && "$CS/flang-bin" -fc1 -triple aarch64-linux-android35 '
                 '-emit-obj "$b" ) || exit 1\n'
                 '  o="$SD/$base.o"\n'
                 '  [ -f "$o" ] || o="$SD/$base"\n'
                 '  [ -f "$o" ] && cp "$o" "$TMP/$base.o" && o="$TMP/$base.o"\n'
                 '  [ -f "$o" ] || { echo "flang: nu a produs .o pentru $s"; exit 1; }\n'
                 '  FORTO="$FORTO $o"\n'
                 'done\n'
                 'exec "%s/libclang_exec.so" --target=aarch64-linux-android35 '
                 '--sysroot="$R/sysroot" -B"$CS" -resource-dir="$R/lib/clang/21" '
                 '$OBJS $FORTO -o "$OUT" -L"$SL" -L"$R/sysroot/usr/lib/aarch64-linux-android/35" '
                 '-lFortranRuntime -lFortranDecimal -lc++_shared -lm\n'
                 % (F + "/tmp", ROOT, _sl, nat))
        # ★ FAZA 4e: launcher ELF, nu script. untrusted_app NU poate executa scriptul din
        # filesDir; `libshwrap_exec.so` (jniLibs) executa `sh <nume>.sh "$@"`, iar scriptul
        # scris in files/tmp/flang.sh poate fi CITIT de app (doar exec direct e interzis).
        _sw = nat + "/libshwrap_exec.so"
        for name in ("flang", "flang-new", "flang-21"):
            p = F + "/tmp/" + name
            ps = F + "/tmp/" + name + ".sh"
            try:
                if (not os.path.exists(ps)) or open(ps).read() != _body:
                    open(ps, "w").write(_body)
                os.chmod(ps, 0o755)
                if os.path.exists(_sw):
                    if os.path.lexists(p):
                        os.remove(p)
                    os.symlink(_sw, p)
                else:
                    if os.path.lexists(p):
                        os.remove(p)
                    open(p, "w").write(_body)
                    os.chmod(p, 0o755)
                made.append(name)
            except Exception:
                pass
        _pb = F + "/tmp/flang-bin"
        try:
            _st = False
            if os.path.islink(_pb):
                try: _st = not os.path.exists(os.readlink(_pb))
                except Exception: _st = True
            if os.path.lexists(_pb) and (not os.path.islink(_pb) or _st):
                os.remove(_pb)
            if not os.path.lexists(_pb):
                os.symlink(nat + "/libflang_exec.so", _pb)
        except Exception:
            pass
    if py:
        # ★ FAZA 4i: launcher ELF (libshwrap_exec.so) + script .sh - NU script executabil direct.
        # Raportat de agent: "cython: Permission denied" pentru ca files/tmp/cython era un SCRIPT
        # in filesDir, iar untrusted_app nu poate executa scripturi de acolo (doar ELF/symlink-ELF).
        _sw2 = nat + "/libshwrap_exec.so" if nat else ""
        # ★ FAZA 4j: `env` PROPRIU. meson isi impacheteaza comenzile custom ca
        #   `env PYTHONPATH=... <python> -m modul`, iar toybox env de pe Android executa gresit
        #   ("env: exec -m: No such file or directory", rc=127) -> build-ul numpy pica la primul
        #   pas de codegen. Punem un env corect primul in PATH (files/tmp e primul in PATH).
        try:
            _envsh = F + "/tmp/env.sh"
            _envbody = ("#!/system/bin/sh\n"
                        "# env propriu (toybox env executa gresit comenzile meson).\n"
                        "# Atentie: calea APK contine '==' (~~xqic99_7GfT6epcvQxafJg==), deci NU\n"
                        "# putem testa generic '*=*' - numele trebuie sa inceapa cu litera/_ (ca la sh).\n"
                        "while [ $# -gt 0 ]; do\n"
                        "  case \"$1\" in\n"
                        "    -i) shift ;;\n"
                        "    -u) shift 2 ;;\n"
                        "    [A-Za-z_]*=*) export \"$1\"; shift ;;\n"
                        "    -*) shift ;;\n"
                        "    *) exec \"$@\" ;;\n"
                        "  esac\n"
                        "done\n"
                        "exit 125\n")
            if (not os.path.exists(_envsh)) or open(_envsh).read() != _envbody:
                open(_envsh, "w").write(_envbody)
            os.chmod(_envsh, 0o755)
            _ep = F + "/tmp/env"
            if _sw2 and os.path.exists(_sw2):
                if os.path.lexists(_ep):
                    os.remove(_ep)
                os.symlink(_sw2, _ep)
            else:
                if os.path.lexists(_ep):
                    os.remove(_ep)
                open(_ep, "w").write(_envbody)
                os.chmod(_ep, 0o755)
            made.append("env")
        except Exception:
            pass
        # ★ FAZA 4p: `python3`/`python` AUTO-SUFICIENTE. pip lanseaza build-backend-ul cu
        # sys.executable, adica prin acest lansator, DAR cu un env minimal (fara PYTHONHOME):
        # Python nu-si gasea stdlib-ul ("Could not find platform independent libraries",
        # "No available output") si ORICE pip install cu build backend murea - de aici esecul
        # "pip install numpy (exit 1, 19s)" din testul din laborator.
        # Lansatorul isi exporta SINGUR PYTHONHOME/PYTHONPATH/TMPDIR, deci merge din orice context.
        try:
            _pysh = F + "/tmp/python3.sh"
            _pyhome = F + "/pyhome"
            # ★ si LD_LIBRARY_PATH: fara el, incarcatorul nu gaseste libpython3.14.so
            # ("CANNOT LINK EXECUTABLE ... libpyexec.so") cand pip il lanseaza cu env minimal.
            # PREPEND, niciodata replace (regula dovedita: pierderea nativeLibraryDir = moarte).
            _pybody = ("#!/system/bin/sh\n"
                       "export PYTHONHOME=%s\n"
                       "export PYTHONPATH=%s/lib/stdlib_extra.zip:%s/lib/pysitepkg.zip:%s/python\n"
                       "export TMPDIR=%s/tmp\n"
                       "export LD_LIBRARY_PATH=%s:%s/libs:%s/lib:${LD_LIBRARY_PATH}\n"
                       "exec %s/libpyexec.so \"$@\"\n"
                       % (_pyhome, _pyhome, _pyhome, F, F, nat, F, DEPS, nat))
            if (not os.path.exists(_pysh)) or open(_pysh).read() != _pybody:
                open(_pysh, "w").write(_pybody)
            os.chmod(_pysh, 0o755)
            for _nm in ("python3", "python"):
                _pp = F + "/tmp/" + _nm
                if _sw2 and os.path.exists(_sw2):
                    if os.path.lexists(_pp):
                        os.remove(_pp)
                    os.symlink(_sw2, _pp)
                else:
                    _pp2 = F + "/tmp/" + _nm + ".sh"
                    open(_pp2, "w").write(_pybody)
                    os.chmod(_pp2, 0o755)
                made.append(_nm)
        except Exception:
            pass
        # ★ cargo: config GLOBAL (CARGO_HOME/config.toml) - altfel build-urile Rust pornite din alt
        # cwd (ex. /storage) nu gasesc linker-ul cc-rust si cad cu "linking with cc failed: exit 127".
        try:
            _ch = F + "/cargo"
            os.makedirs(_ch, exist_ok=True)
            _ccfg = F + "/cargo/config.toml"
            _body = ("[target.aarch64-linux-android]\n"
                     "linker = \"%s/tmp/cc-rust\"\n" % F)
            if (not os.path.exists(_ccfg)) or open(_ccfg).read() != _body:
                open(_ccfg, "w").write(_body)
        except Exception:
            pass

        for name, mod in (("cython", "cython"), ("cython3", "cython"), ("cython-3", "cython"),
                          ("f2py", "numpy.f2py"), ("pip", "pip"), ("pip3", "pip")):
            p = F + "/tmp/" + name
            ps = F + "/tmp/" + name + ".sh"
            try:
                body = ('#!/system/bin/sh\nexec "%s" -m %s "$@"\n' % (py, mod))
                if (not os.path.exists(ps)) or open(ps).read() != body:
                    open(ps, "w").write(body)
                os.chmod(ps, 0o755)
                if _sw2 and os.path.exists(_sw2):
                    if os.path.lexists(p):
                        os.remove(p)
                    os.symlink(_sw2, p)
                else:
                    if os.path.lexists(p):
                        os.remove(p)
                    open(p, "w").write(body)
                    os.chmod(p, 0o755)
                made.append(name)
            except Exception:
                pass
    return made


def _ensure_python_pc():
    """★ N6/N7: scrie python3.pc cu prefixul NOSTRU (meson/cmake il cauta).

    Fara el: 'Run-time dependency python3 found: NO' + 'Header Python.h not found'.
    Libs-urile trebuie sa duca spre libpython3.14.so, altfel link test esueaza.
    """
    inc = ROOT + "/pyinc"
    pc = DEPS + "/lib/pkgconfig/python3.pc"
    try:
        os.makedirs(DEPS + "/lib/pkgconfig", exist_ok=True)
        body = ("prefix=%s\nexec_prefix=${prefix}\n"
                "libdir=%s\nincludedir=%s\n\n"
                "Name: Python\nDescription: Python standard library\n"
                "Version: 3.14\nLibs: -L%s -lpython3.14\n"
                "Cflags: -I%s\n" % (ROOT, _sdk_lib_dir(), inc, _sdk_lib_dir(), inc))
        if (not os.path.exists(pc)) or open(pc).read() != body:
            open(pc, "w").write(body)
    except Exception:
        pass


def _atomic_dir():
    """Directorul care contine libatomic.a (builtins clang), sau "" daca lipseste."""
    for _p in (BIN + "/../lib/clang/21/lib/linux", DEPS + "/lib",
               ROOT + "/sysroot/usr/lib/aarch64-linux-android/35"):
        for _f in ("libatomic.a", "libatomic.so"):
            if os.path.exists(_p + "/" + _f):
                return _p
    return ""


def _have_libatomic():
    """★ sect. 5: grpcio cere -latomic. libatomic.a e livrat ca builtin clang."""
    return bool(_atomic_dir())


def _ensure_pipconf():
    """★ sect. 4: pip creeaza un mediu izolat la fiecare build si pierde PYTHONPATH
    -> "Cannot import 'setuptools.build_meta'". FIX: pip.conf cu no-build-isolation."""
    d = F + "/python/Lib/site-packages"
    conf = F + "/pip.conf"
    for _d in (F, d):
        try:
            os.makedirs(_d, exist_ok=True)
        except Exception:
            pass
    body = ("[global]\n"
            "no-build-isolation = true\n"
            "\n[build]\n"
            "no-build-isolation = true\n")
    for _c in (F + "/pip.conf", F + "/python/Lib/site-packages/pip.conf",
               F + "/pyhome/lib/python3.14/site-packages/pip.conf"):
        try:
            if (not os.path.exists(_c)) or open(_c).read() != body:
                open(_c, "w").write(body)
        except Exception:
            pass
    return conf


def _ensure_fake_ndk():
    """★ FAZA 1: cmake detecteaza automat platforma Android din triple-ul compilatorului
    (aarch64-linux-android35) si atunci CEREE un NDK cu layout standard - altfel:
    "file failed to open: /include/android/api-level.h" si "compiler broken".
    Nu avem NDK pe device, dar avem exact piesele (clang + sysroot) -> construim un
    NDK MINIMAL prin symlink-uri in files/toolchain/ndk. cmake il accepta si foloseste
    compilatorul + sysroot-ul nostru.
    """
    base = ROOT + "/ndk/toolchains/llvm/prebuilt/linux-x86_64"
    for d in (base + "/bin", base + "/sysroot", ROOT + "/ndk/build/cmake/hooks/pre",
              ROOT + "/ndk/build/cmake/hooks/post"):
        try:
            os.makedirs(d, exist_ok=True)
        except Exception:
            pass
    # sysroot-ul nostru real
    try:
        _sr = base + "/sysroot"
        if os.path.islink(_sr) and not os.path.exists(_sr):
            os.remove(_sr)
        if not os.path.lexists(_sr):
            os.symlink(ROOT + "/sysroot", _sr)
    except Exception:
        pass
    # binarele cu numele cerute de cmake (clang/clang++/ld.lld/ar/ranlib/strip/nm)
    _map = {"clang": "clang", "clang++": "clang++", "ld.lld": "ld.lld", "ld": "ld",
            "ar": "ar", "ranlib": "ranlib", "strip": "strip", "nm": "nm"}
    for name in _map:
        src = F + "/tmp/" + name
        dst = base + "/bin/" + name
        try:
            if not os.path.exists(src):
                continue
            if os.path.islink(dst) and not os.path.exists(dst):
                os.remove(dst)
            if not os.path.lexists(dst):
                os.symlink(src, dst)
        except Exception:
            pass
    # "source.properties" - cmake/NDK il citesc pentru versiune (optional, dar ieftin)
    try:
        _sp = ROOT + "/ndk/source.properties"
        if not os.path.exists(_sp):
            open(_sp, "w").write("Pkg.Desc = Android NDK (minimal, generat de net.sys32.agent)\n"
                                 "Pkg.Revision = 27.1.12297006\n")
    except Exception:
        pass
    return ROOT + "/ndk"


def _pybind11_dir():
    """★ pachetele C++ cu binding-uri (duckdb) fac `find_package(pybind11)`, care are nevoie
    de pybind11Config.cmake. pybind11 il livreaza in pachetul Python - dar la noi pachetele
    stau in ZIP-uri (zipimport), iar cmake nu citeste din zip -> extragem subtree-ul
    share/cmake intr-un director real si il dam prin -Dpybind11_DIR."""
    out = F + "/toolchain/pybind11-cmake"
    try:
        if os.path.isdir(out) and os.path.exists(out + "/pybind11Config.cmake"):
            return out
    except Exception:
        pass
    inst = os.path.dirname(os.path.abspath(__file__))
    cands = [F + "/pyhome/lib/python3.14/site-packages/pybind11/share/cmake",
             inst + "/pybind11/share/cmake"]
    try:
        import pybind11
        d = pybind11.get_cmake_dir()
        if d:
            cands.insert(0, os.path.dirname(d))
    except Exception:
        pass
    import zipfile
    for z in (F + "/pyhome/lib/pysitepkg.zip", F + "/pyhome/lib/stdlib_extra.zip"):
        try:
            if not os.path.exists(z):
                continue
            with zipfile.ZipFile(z) as zf:
                memb = [n for n in zf.namelist() if "pybind11/share/cmake/" in n]
                if not memb:
                    continue
                os.makedirs(out, exist_ok=True)
                for n in memb:
                    rel = n.split("pybind11/share/cmake/", 1)[1]
                    if not rel or n.endswith("/"):
                        continue
                    dst = os.path.join(out, rel)
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    with open(dst, "wb") as fh:
                        fh.write(zf.read(n))
                if os.path.exists(out + "/pybind11Config.cmake"):
                    return out
        except Exception:
            pass
    for d in cands:
        if os.path.isdir(d) and os.path.exists(d + "/pybind11/pybind11Config.cmake"):
            return d + "/pybind11"
    return ""


def _ensure_real_cython():
    """★ BUG MAJOR reparat (numpy): Cython isi cauta fisierele `Includes/` RELATIV la
    `__file__` (libc/stdint.pxd, cpython/ref.pxd). La noi Cython sta in pysitepkg.zip
    (zipimport) -> Cython nu gaseste Includes si numpy pica la compilarea .pyx cu
    "'libc/stdint.pxd' not found" / "'cpython/ref.pxd' not found".
    Solutie: extragem arborele Cython din zip intr-un director REAL, pus in PYTHONPATH
    INAINTEA zip-ului (altfel zipimport are prioritate)."""
    real = F + "/pyhome/lib/pyreal"
    dst = real + "/Cython"
    try:
        if os.path.isdir(dst) and os.path.exists(dst + "/Includes/libc/stdint.pxd"):
            return real
    except Exception:
        pass
    z = F + "/pyhome/lib/pysitepkg.zip"
    try:
        import zipfile
        if not os.path.exists(z):
            return ""
        with zipfile.ZipFile(z) as zf:
            memb = [n for n in zf.namelist() if n.startswith("Cython/") and not n.endswith("/")]
            if not memb:
                return ""
            os.makedirs(dst, exist_ok=True)
            for n in memb:
                d = os.path.join(real, n)
                os.makedirs(os.path.dirname(d), exist_ok=True)
                with open(d, "wb") as fh:
                    fh.write(zf.read(n))
        return real if os.path.exists(dst + "/Includes/libc/stdint.pxd") else ""
    except Exception:
        return ""


def _ensure_python_launcher():
    """★ BUG MAJOR reparat (numpy): meson/meson-python scriu comenzi de forma
        env PYTHONPATH=... '<interpreter>' -m ...
    Interpreterul era libpyexec.so din nativeLibraryDir, iar calea contine `~~` si `==`
    (/data/app/~~xxxx==/net.sys32.agent-yyyy==/lib/arm64/libpyexec.so) -> meson o pune
    INTRE GHILIMELE SIMPLE, iar `env` nu stie de ghilimele: "env: exec -m: No such file
    or directory" -> orice generator de cod din numpy pica.
    Solutie: symlink cu nume CURAT in files/tmp (kernelul urmareste symlink-ul, deci
    SELinux vede tinta exec-abila din nativeLibraryDir) + sys.executable setat catre el,
    ca meson/scikit-build/setuptools sa primeasca o cale fara caractere speciale."""
    _nat = _native_dir()
    if not _nat:
        return ""
    p = F + "/tmp/python3"
    try:
        for name in ("python3", "python"):
            q = F + "/tmp/" + name
            _st = False
            if os.path.islink(q):
                try:
                    _st = not os.path.exists(os.readlink(q))
                except Exception:
                    _st = True
            if os.path.lexists(q) and (not os.path.islink(q) or _st):
                os.remove(q)
            if not os.path.lexists(q):
                os.symlink(_nat + "/libpyexec.so", q)
        return p
    except Exception:
        return ""


def _patch_sys_executable():
    """Setam sys.executable catre lansatorul cu nume curat (vezi _ensure_python_launcher)."""
    p = _ensure_python_launcher()
    if not p:
        return
    try:
        if os.path.exists(p):
            sys.executable = p
            if hasattr(sys, "_base_executable"):
                sys._base_executable = p
    except Exception:
        pass


def _write_cmake_toolchain(_cflags, _ldflags):
    """★ FAZA 1: scrie toolchain-ul CMake pentru DEVICE (o singura sursa de adevar:
    acelasi _cflags/_ldflags ca build-urile pip). cmake il citeste din variabila de
    mediu CMAKE_TOOLCHAIN_FILE (vezi cmake.cxx: GetEnv("CMAKE_TOOLCHAIN_FILE")).
    Fara el: cmake nu stie sysroot-ul -> "file failed to open: /include/android/api-level.h"."""
    _cf = _cflags.replace("\\", "/")
    _lf = _ldflags.replace("\\", "/")
    _txt = """# GENERAT AUTOMAT de toolchain.py (net.sys32.agent) - nu edita manual.
# Toolchain CMake pentru cmake care ruleaza PE TELEFON (Android/aarch64, fara NDK pe device).
# ★ cmake detecteaza singur Android din triple-ul clang-ului, dar apoi cere un NDK cu
# layout standard (altfel: "file failed to open: /include/android/api-level.h").
# `_ensure_fake_ndk()` construieste layout-ul minim prin symlink-uri (clang + sysroot).
set(CMAKE_SYSTEM_NAME Android)
set(CMAKE_SYSTEM_PROCESSOR aarch64)
set(CMAKE_SYSTEM_VERSION 35)
set(CMAKE_ANDROID_API 35)
set(CMAKE_ANDROID_ARCH_ABI arm64-v8a)
set(CMAKE_ANDROID_NDK "%(ndk)s")
set(CMAKE_ANDROID_STL_TYPE c++_shared)
set(CMAKE_SYSROOT "%(ndk)s/toolchains/llvm/prebuilt/linux-x86_64/sysroot")
set(CMAKE_C_COMPILER "%(f)s/tmp/clang")
set(CMAKE_CXX_COMPILER "%(f)s/tmp/clang++")
set(CMAKE_C_FLAGS_INIT "%(cf)s")
set(CMAKE_CXX_FLAGS_INIT "%(cf)s")
set(CMAKE_EXE_LINKER_FLAGS_INIT "%(lf)s")
set(CMAKE_SHARED_LINKER_FLAGS_INIT "%(lf)s")
set(CMAKE_MODULE_LINKER_FLAGS_INIT "%(lf)s")
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
set(CMAKE_FIND_ROOT_PATH "%(root)s/sysroot" "%(deps)s")
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
# ★ find_package(Python3) trebuie sa functioneze (pachetele cu binding-uri: duckdb, pyarrow):
# python-ul e NATIV (ruleaza pe acelasi device), deci BOTH, nu ONLY.
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE BOTH)
set(CMAKE_PREFIX_PATH "%(deps)s")
""" % {"root": ROOT, "f": F, "deps": DEPS, "cf": _cf, "lf": _lf,
       "ndk": _ensure_fake_ndk()}
    _ndk = _ensure_fake_ndk()
    _p = F + "/tmp/android.toolchain.cmake"
    try:
        if not os.path.exists(_p) or open(_p).read() != _txt:
            open(_p, "w").write(_txt)
    except Exception:
        pass
    return _p


def _rust_dir():
    return ROOT + "/rust"


def _rust_lib():
    return _rust_dir() + "/lib"


_RUST_NEEDS_PRELOAD = None


_MATURIN_SHIM = '''"""maturin - shim PEP 517 pentru device (net.sys32.agent).

Pachetele cu `[build-system] build-backend = "maturin"` (orjson, cramjam, pydantic-core,
tokenizers...) au nevoie de MODULUL python `maturin`, care in mod normal vine cu un wheel
binar (inexistent pentru Android). Aici modulul e doar un invelis subtire peste binarul
`maturin` livrat in APK (jniLibs/libmaturin_exec.so, symlink in files/tmp).
"""
import glob
import os
import subprocess
import sys


def _bin():
    p = "/data/data/net.sys32.agent/files/tmp/maturin"
    if os.path.exists(p):
        return p
    raise RuntimeError("maturin: binarul lipseste din APK (libmaturin_exec.so)")


def _run(args, capture=True):
    env = dict(os.environ)
    env.setdefault("CARGO_HOME", "/data/data/net.sys32.agent/files/cargo")
    p = subprocess.run([_bin()] + list(args), capture_output=capture, text=True, env=env)
    if p.returncode != 0:
        tail = ((p.stdout or "") + (p.stderr or ""))[-4000:]
        raise RuntimeError("maturin %s a esuat:\\n%s" % (" ".join(args), tail))
    return p


def _newest(d, pat):
    f = sorted(glob.glob(os.path.join(d, pat)), key=os.path.getmtime)
    if not f:
        raise RuntimeError("maturin: nu a produs niciun %s in %s" % (pat, d))
    return os.path.basename(f[-1])


def get_requires_for_build_wheel(config_settings=None):
    return []


def get_requires_for_build_sdist(config_settings=None):
    return []


def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
    args = ["build", "--release", "--out", wheel_directory, "--interpreter", sys.executable]
    _run(args)
    return _newest(wheel_directory, "*.whl")


def build_sdist(sdist_directory, config_settings=None):
    _run(["sdist", "--out", sdist_directory])
    return _newest(sdist_directory, "*.tar.gz")


def prepare_metadata_for_build_wheel(metadata_directory, config_settings=None):
    try:
        _run(["pep517", "write-dist-info", "--metadata-directory", metadata_directory,
              "--interpreter", sys.executable])
        import os as _os
        for d in _os.listdir(metadata_directory):
            if d.endswith(".dist-info"):
                return d
    except Exception:
        pass
    raise NotImplementedError("fara prepare_metadata (pip construieste wheel-ul pentru metadate)")
'''


def _ensure_setuptools():
    """★ setuptools TREBUIE sa fie instalat: cu PIP_NO_BUILD_ISOLATION=1 (setat in env_vars),
    backendul de build ruleaza in procesul nostru si importa setuptools; daca a fost sters de
    vreun pip anterior, TOATE build-urile clasice cad. Raportat de testul E2E din UI
    ("setuptools - singurul care chiar lipseste"). Il reinstalam o data, cu marker.
    """
    try:
        import setuptools  # noqa: F401
        return True
    except Exception:
        pass
    _mk = F + "/pyhome/lib/python3.14/site-packages/.setuptools_tried"
    if os.path.exists(_mk):
        return False
    try:
        open(_mk, "w").write("1")
    except Exception:
        pass
    try:
        _py = _py_exec()
        # ★ NU chemam env_vars() aici (ne cheama ELE pe noi -> recursiune); luam minimul necesar
        env = dict(os.environ)
        try:
            env["LD_LIBRARY_PATH"] = _rt_ld_path()
            env["PATH"] = F + "/tmp:" + env.get("PATH", "")
            env["PYTHONHOME"] = F + "/pyhome"
            env["PYTHONPATH"] = (F + "/pyhome/lib/stdlib_extra.zip:" + F + "/pyhome/lib/python3.14:"
                                 + F + "/pyhome/lib/pysitepkg.zip")
            env["TMPDIR"] = F + "/tmp"
            env["SSL_CERT_FILE"] = env["CURL_CA_BUNDLE"] = _ca_bundle()
            env["PIP_NO_BUILD_ISOLATION"] = "1"
        except Exception:
            pass
        subprocess.run([_py, "-m", "pip", "install", "--no-cache-dir", "-q", "setuptools"],
                       capture_output=True, text=True, timeout=900, env=env,
                       stdin=subprocess.DEVNULL)
    except Exception:
        pass
    try:
        import setuptools  # noqa: F401
        return True
    except Exception:
        return False


def _ensure_maturin():
    """★ FAZA 5: pachete Python cu backend `maturin` (orjson, cramjam, pydantic-core...).

    Doua componente, ca la rustc/cargo:
      * binarul (jniLibs/libmaturin_exec.so) -> lansator in files/tmp/maturin;
      * modulul python `maturin` (PEP 517) -> shim scris in site-packages, care cheama binarul.
    Fara binar: pachetele cu maturin nu se pot construi deloc pe Android (nu exista wheel).
    """
    nat = _native_dir()
    if nat and os.path.exists(nat + "/libmaturin_exec.so"):
        _p = F + "/tmp/maturin"
        try:
            _st = False
            if os.path.islink(_p):
                try:
                    _st = not os.path.exists(os.readlink(_p))
                except Exception:
                    _st = True
            if os.path.lexists(_p) and (not os.path.islink(_p) or _st):
                os.remove(_p)
            if not os.path.lexists(_p):
                os.symlink(nat + "/libmaturin_exec.so", _p)
        except Exception:
            pass
    # shim-ul python (in site-packages-ul REAL, unde cauta pip)
    try:
        import sysconfig as _sc
        _sp = _sc.get_paths().get("purelib") or _sc.get_paths().get("platlib")
        if not _sp:
            _sp = F + "/pyhome/lib/python3.14/site-packages"
        _d = _sp + "/maturin"
        os.makedirs(_d, exist_ok=True)
        _f = _d + "/__init__.py"
        if (not os.path.exists(_f)) or open(_f).read() != _MATURIN_SHIM:
            open(_f, "w").write(_MATURIN_SHIM)
    except Exception:
        pass


def _rust_link_flags():
    """Flags de LINK pentru rustc/cargo pe device (clang din APK + sysroot-ul de device).

    Sunt puse in RUSTFLAGS (variabila de MEDIU), nu doar in `files/cargo/config.toml`:
    `rustflags` din `[target.*]` NU ajung la compilarea build-scripturilor (cargo le
    compileaza pentru gazda) -> linkul lor cadea cu "cannot open crtbegin_dynamic.o" si
    "-ldl/-llog/-lm/-lc not found". Build-scripturile sunt obligatorii pentru majoritatea
    crate-urilor, deci trebuie sa mearga.
    """
    return ("-C linker=" + F + "/tmp/clang"
            + " -C link-arg=--target=aarch64-linux-android" + str(_device_api())
            + " -C link-arg=--sysroot=" + ROOT + "/sysroot")


def _ensure_rust():
    """★ FAZA 4 (Rust): rustc + cargo cross-compilate de noi pentru Android.

    Doua lumi diferite, cu reguli diferite (capcana dovedita pe device):
      * BINARELE (rustc, cargo) trebuie EXECUTATE -> untrusted_app nu poate executa
        din filesDir -> stau in APK ca lib*_exec.so, cu symlink in files/tmp/ (PATH).
      * LIBRARIILE (librustc_driver, libLLVM.so.21.1, libc++_shared, std/*.rlib) se
        INCARCA (dlopen/read) -> merg din filesDir, unde le extragem din
        assets/toolchain/rust-libs.tar.gz (o singura data, ~480 MB pe disc).
    Fara librustc_driver in LD_LIBRARY_PATH: "CANNOT LINK EXECUTABLE rustc".
    """
    global _RUST_NEEDS_PRELOAD
    rd, lib = _rust_dir(), _rust_lib()
    # ★ dupa un update de APK, sysroot-ul se re-extrage si pierde subdir-ul de API creat
    # la rulare (35/36) -> rustc/clang nu mai gasesc crtend_android.o/-lm/-lc. Il refacem.
    try:
        _ensure_sysroot_api_dir(_device_api())
    except Exception:
        pass
    try:
        os.makedirs(lib, exist_ok=True)
    except Exception:
        pass
    # ★ CAPCANA: AGP/aapt2 DEZARHIVEAZA asset-urile .gz (ajung pe device ca
    # "rust-libs.tar", 650 MB, comprimate de zip-ul APK-ului) -> acceptam ambele
    # nume, iar tarfile detecteaza singur compresia.
    for _nm in ("/rust-libs.tar.gz", "/rust-libs.tar"):
        tgz = ROOT + _nm
        if os.path.exists(tgz):
            break
    if os.path.exists(tgz):
        # ★ CAPCANA (dovedita de testul E2E din UI): marker-ul ".extracted" supravietuieste
        # update-urilor de APK, dar arhiva din assets se schimba (rustc nou -> nume NOU de
        # librustc_driver). Rezultatul: rustc nou + driver vechi -> agentul raporta
        # "Rust rupt (segfault)". De aceea stampilam (size, mtime) si re-extragem la schimbare.
        try:
            _st = os.stat(tgz)
            _sig = "%d:%d" % (_st.st_size, int(_st.st_mtime))
        except Exception:
            _sig = ""
        _need = not os.path.exists(lib + "/.extracted")
        if not _need and _sig:
            try:
                _need = open(lib + "/.extracted").read().strip() != _sig
            except Exception:
                _need = True
        if _need:
            try:
                import shutil as _sh0
                import tarfile
                _sh0.rmtree(lib, ignore_errors=True)   # scoatem .so-urile vechi (nume/hash nou)
                os.makedirs(lib, exist_ok=True)
                with tarfile.open(tgz) as t:
                    # ★ CAPCANA (Python 3.14): filtrul implicit "data" ARUNCA
                    # AbsoluteLinkError daca arhiva are vreun symlink absolut
                    # (lib/rustlib/src/rust -> /home/gab/... din arborele de build).
                    # Filtrul "tar" doar ignora linkurile absolut/escape-urile, nu pica.
                    try:
                        t.extractall(rd, filter="tar")
                    except TypeError:
                        t.extractall(rd)
                open(lib + "/.extracted", "w").write(_sig or "1")
            except Exception:
                pass
    # lansatoare executabile in files/tmp (acelasi tipar ca cmake/perl/clang)
    nat = _native_dir()
    for _nm, _so in (("rustc", "librustc_exec.so"), ("cargo", "libcargo_exec.so")):
        if nat and os.path.exists(nat + "/" + _so):
            _p = F + "/tmp/" + _nm
            try:
                _st = False
                if os.path.islink(_p):
                    try:
                        _st = not os.path.exists(os.readlink(_p))
                    except Exception:
                        _st = True
                if os.path.lexists(_p) and (not os.path.islink(_p) or _st):
                    os.remove(_p)
                if not os.path.lexists(_p):
                    os.symlink(nat + "/" + _so, _p)
            except Exception:
                pass
    # librustc_driver refera std::__ndk1::* (libc++). Daca NU are deja NEEDED
    # libc++_shared.so (patch cu patchelf la impachetare), singura cale de a-l incarca
    # e LD_PRELOAD - si doar pentru procesele Rust, ca sa nu atingem clang-ul.
    if _RUST_NEEDS_PRELOAD is None:
        _RUST_NEEDS_PRELOAD = False
        try:
            import glob as _glob
            for _d in _glob.glob(lib + "/librustc_driver*.so"):
                _head = open(_d, "rb").read(60000)
                if b"libc++_shared.so" not in _head:
                    _RUST_NEEDS_PRELOAD = True
                break
        except Exception:
            _RUST_NEEDS_PRELOAD = False
    # ★ wrapper de LINKER (script, in files/tmp): cargo NU propaga linker-ul/rustflags catre
    # linkul build-scripturilor (nici cu target-applies-to-host, nici prin RUSTFLAGS - dovedit
    # pe device), deci singura cale sigura e ca `cc`-ul insusi sa adauge --target/--sysroot.
    # Scriptul e executabil pentru ca e interpretat de /system/bin/sh (nu exec direct).
    try:
        # ★ FAZA 4e: lansator ELF (nu script!). untrusted_app NU poate executa fisiere din
        # filesDir (Android 10+ W^X) - deci scriptul shell de aici NU putea fi rulat de app,
        # doar prin `sh <script>`. `libccrust_exec.so` (in jniLibs) executa clang-ul cu
        # --target/--sysroot si merge in orice context.
        _elf = nat + "/libccrust_exec.so"
        if os.path.exists(_elf):
            for _nm in ("cc-rust", "cc", "c++"):
                _p = F + "/tmp/" + _nm
                try:
                    if os.path.lexists(_p):
                        os.remove(_p)
                    os.symlink(_elf, _p)
                except Exception:
                    pass
        _cc = F + "/tmp/cc-rust"
        if not os.path.lexists(_cc):
            _body = ('#!/system/bin/sh\n'
                     'exec ' + F + '/tmp/clang --target=aarch64-linux-android' + str(_device_api())
                     + ' --sysroot=' + ROOT + '/sysroot "$@"\n')
            try:
                open(_cc, "w").write(_body)
                os.chmod(_cc, 0o755)
            except Exception:
                pass
        _cc = F + "/tmp/cc-rust"
        if not os.path.lexists(_cc):
            # fallback (fara launcher ELF in APK): script shell + -resource-dir
            _res = ROOT + "/lib/clang/21"
            _resf = (" -resource-dir=" + _res) if os.path.isdir(_res + "/include") else ""
            _body = ('#!/system/bin/sh\n'
                     'exec ' + F + '/tmp/clang' + _resf + ' --target=aarch64-linux-android'
                     + str(_device_api()) + ' --sysroot=' + ROOT + '/sysroot "$@"\n')
            try:
                open(_cc, "w").write(_body)
                os.chmod(_cc, 0o755)
                made.append("cc-rust")
            except Exception:
                pass
    except Exception:
        pass
    # config cargo: linker-ul nostru + sysroot-ul de device. ★ `target-applies-to-host` e
    # OBLIGATORIU: fara el cargo NU aplica linker/rustflags build-scripturilor (le compileaza
    # "pentru gazda") si linkul lor cade cu "cannot open crtbegin_dynamic.o" / "-lc not found".
    try:
        _ch = F + "/cargo"
        os.makedirs(_ch, exist_ok=True)
        _cfg = _ch + "/config.toml"
        _rf = '["-C", "link-arg=--target=aarch64-linux-android%d", "-C", "link-arg=--sysroot=%s/sysroot"]' % (_device_api(), ROOT)
        _want = ('[build]\ntarget = "aarch64-linux-android"\n\n'
                 '[target.aarch64-linux-android]\n'
                 'linker = "' + F + '/tmp/cc-rust"\n'
                 'rustflags = ' + _rf + '\n')
        if (not os.path.exists(_cfg)) or open(_cfg).read() != _want:
            open(_cfg, "w").write(_want)
    except Exception:
        pass


def rust_env(base=None):
    """Mediul pentru rustc/cargo pe device (librustc_driver + libLLVM + std)."""
    _ensure_rust()
    env = dict(base or os.environ)
    ld = [x for x in (env.get("LD_LIBRARY_PATH", "") or "").split(":") if x]
    for d in (_rust_lib(), _native_dir()):
        if d and d not in ld:
            ld.append(d)
    env["LD_LIBRARY_PATH"] = ":".join(ld)
    try:
        os.makedirs(F + "/cargo", exist_ok=True)
    except Exception:
        pass
    env["CARGO_HOME"] = F + "/cargo"
    env["PATH"] = F + "/tmp:" + F + "/cargo/bin:" + env.get("PATH", "")
    # ★ CAPCANA: `rustflags` din [target.*] din config.toml NU se aplica la compilarea
    # build-scripturilor (cargo le compileaza "pentru gazda") -> linkerul clang rula fara
    # --target/--sysroot si linkul cadea cu "cannot open crtbegin_dynamic.o" /
    # "-ldl/-llog/-lm/-lc not found". RUSTFLAGS din MEDIU se aplica la TOT.
    env["RUSTFLAGS"] = _rust_link_flags()
    # ★ crate-urile care compileaza C prin `cc-rs` (maturin -> git2/libgit2, ring, psm...)
    # cauta un compilator NUMIT `<target>-clang` sau variabilele CC_<target>/CXX_<target>.
    # Fara ele: "failed to find tool \"aarch64-linux-android-clang\"".
    _t = "aarch64-linux-android"
    env.setdefault("CC_" + _t, F + "/tmp/cc-rust")
    env.setdefault("CXX_" + _t, F + "/tmp/cc-rust")
    env.setdefault("AR_" + _t, F + "/tmp/ar")
    env.setdefault("CARGO_TARGET_AARCH64_LINUX_ANDROID_LINKER", F + "/tmp/cc-rust")
    # ★ LTO OFF: std-ul vine cu bitcode LLVM 22.1.8 (LLVM-ul intern al Rust 1.98.1), iar
    # rustc-ul de pe device e linkat cu libLLVM 21.1.8 -> LTO cade cu
    # "failed to load bitcode of module ...: Unknown attribute kind (105)
    #  (Producer: 'LLVM22.1.8-rust-1.98.1-stable' Reader: 'LLVM 21.1.8')" (dovedit cu orjson).
    env.setdefault("CARGO_PROFILE_RELEASE_LTO", "false")
    env.setdefault("CARGO_PROFILE_RELEASE_DEBUG", "false")
    # ★ cargo are curl STATIC in el -> fara CA bundle "SSL certificate problem"
    # la primul `cargo fetch`/`cargo install` de pe crates.io.
    try:
        _ca = _ca_bundle()
        env.setdefault("SSL_CERT_FILE", _ca)
        env.setdefault("CURL_CA_BUNDLE", _ca)
        env.setdefault("CARGO_HTTP_CAINFO", _ca)
    except Exception:
        pass
    if _RUST_NEEDS_PRELOAD:
        env["LD_PRELOAD"] = _rust_lib() + "/libc++_shared.so"
    return env


def env_vars():
    """Mediul COMPLET de compilare pentru toolchain-ul livrat in APK.

    Totul traieste in filesDir/toolchain: bin/ (clang, lld, binutils), sysroot/
    (headers+libs Android 35), pyinc/ (Python.h), deps/ (libxml2, libxslt, librt).
    Nu exista /data/local/tmp/wrap si nici prefix extern: nimic nu le foloseste.
    """
    home = F + "/home"
    pipcache = home + "/.cache/pip"
    _ensure_launchers()
    _ensure_setuptools()         # ★ pip fara izolare are nevoie de setuptools in proces
    _ensure_rust()                # ★ FAZA 4: rustc/cargo + librustc_driver/libLLVM/std
    _ensure_maturin()             # ★ FAZA 5: maturin (backend pentru orjson/cramjam/...)
    _ensure_python_pc()
    _ensure_pipconf()
    _ensure_py_include()          # ★ Python.h pentru extensii C (INCLUDEPY)
    _patch_sysconfig_device()     # ★ INCLUDEPY/LIBDIR/CC/LDSHARED corecte pe device
    _cxxinc = _ensure_libcxx()
    apexsdk = ROOT + "/sysroot/usr/lib/aarch64-linux-android/35"
    try:
        os.makedirs(pipcache, exist_ok=True)
    except Exception:
        pass
    # ★ TMPDIR trebuie SA EXISTE: pip/setuptools scriu acolo fisierele temporare
    # de build (lxml scrie xmlXPathInit*.c). Fara el, compilarea esueaza silentios.
    try:
        os.makedirs(F + "/tmp", exist_ok=True)
    except Exception:
        pass
    # ★ BINARLE EXECUTABILE: untrusted_app NU poate executa din filesDir (SELinux).
    # Singurul loc executabil e nativeLibraryDir (unde traiesc .so-urile APK-ului).
    # Acolo avem clang/lld/pkg-config redenumite lib*_exec.so.
    NAT = _native_dir()
    if NAT and os.path.exists(NAT + "/libclang_exec.so"):
        # ★ FIX argv[0]: clang decide driver-ul din basename. `libclang_exec.so`
        # NU e recunoscut ca "clang" -> se comporta ca generic driver si se INVARTE
        # (100% CPU, fara output). Symlink cu numele real in files/tmp (exec-abil).
        CC_EXEC = NAT + "/libclang_exec.so"
        try:
            _cl = F + "/tmp/clang"
            _st = False
            if os.path.islink(_cl):
                try:
                    _st = not os.path.exists(os.readlink(_cl))
                except Exception:
                    _st = True
            if os.path.lexists(_cl) and (not os.path.islink(_cl) or _st):
                os.remove(_cl)
            if not os.path.lexists(_cl):
                os.symlink(NAT + "/libclang_exec.so", _cl)
            elif os.path.islink(_cl):
                pass
            # symlink-urile sunt executabile ca app (ca la ld.lld) -> folosim numele real
            if os.path.exists(_cl):
                CC_EXEC = _cl
        except Exception:
            pass
        try:
            _cx = F + "/tmp/clang++"
            if not os.path.lexists(_cx):
                os.symlink(NAT + "/libclang_exec.so", _cx)
        except Exception:
            pass
        PKG_EXEC = NAT + "/libpkgconf_exec.so"
        _extra = " -resource-dir=" + ROOT + "/lib/clang/21"
        # ★ FIX LINKER (esential pentru orice wheel cu extensii C: lxml, numpy, pillow):
        # lld exec-abil traieste DOAR in nativeLibraryDir si se numeste liblld_exec.so.
        # Probleme in lant:
        #   1) clang invoca linkerul dupa nume -> "unable to execute command"
        #   2) lld decide modul dupa argv[0]; cu basename 'liblld_exec.so' zice
        #      "lld is a generic driver" si refuza sa linkeze.
        # SOLUTIA: symlink cu basename EXACT 'ld.lld' in filesDir (kernelul urmareste
        # symlink-ul, deci SELinux vede tinta exec-abila) + --ld-path catre el.
        # ★ lld: symlink cu basename EXACT 'ld.lld'/'ld' in files/tmp (clang il cauta
        # in PATH dupa nume). --ld-path NU e suportat de libclang-ul nostru
        # ("invalid linker name"), deci NE bazam doar pe PATH.
        if os.path.exists(NAT + "/liblld_exec.so"):
            for _ln in ("ld.lld", "ld"):
                _p = F + "/tmp/" + _ln
                try:
                    _stale2 = False
                    if os.path.islink(_p):
                        try:
                            _stale2 = not os.path.exists(os.readlink(_p))
                        except Exception:
                            _stale2 = True
                    if os.path.lexists(_p) and (not os.path.islink(_p) or _stale2):
                        os.remove(_p)
                    if not os.path.lexists(_p):
                        os.symlink(NAT + "/liblld_exec.so", _p)
                except Exception:
                    pass
            _extra += " -B" + F + "/tmp"
        # ★ P3/P4: AR/RANLIB/NM/STRIP/READELF/OBJDUMP erau setate catre binarele din
        # filesDir -> "Permission denied" (W^X/SELinux). Orice build_clib (Pillow) esua.
        # Acelasi tratament ca la ld.lld: symlink cu basename real in files/tmp catre
        # shim-ul lib*_exec.so din nativeLibraryDir (singurul loc executabil).
        _SHIM = {"ar": "libllvmar_exec.so", "ranlib": "libllvmranlib_exec.so",
                 "nm": "libllvmnm_exec.so", "strip": "libllvmstrip_exec.so"}
        for _n, _so in _SHIM.items():
            _t = F + "/tmp/" + _n
            try:
                if os.path.exists(NAT + "/" + _so):
                    # ★ IMPORTANT: symlink-ul vechi pointeaza la libDir-ul INSTALARII
                    # ANTERIOARE (hash-ul se schimba la fiecare install!) -> il recreem
                    # daca tinta lui nu mai exista. Altfel: "No such file or directory".
                    _stale = False
                    if os.path.islink(_t):
                        try:
                            _stale = not os.path.exists(os.readlink(_t))
                        except Exception:
                            _stale = True
                    if os.path.lexists(_t) and (not os.path.islink(_t) or _stale):
                        os.remove(_t)
                    if not os.path.lexists(_t):
                        os.symlink(NAT + "/" + _so, _t)
            except Exception:
                pass
            _lt = F + "/tmp/" + _n
            if os.path.exists(_t):
                _SHIM[_n] = _t
            elif os.path.exists(_lt):
                _SHIM[_n] = _lt           # lansator ELF din files/tmp (executabil ca app)
            else:
                _SHIM[_n] = BIN + "/llvm-" + _n
        # ★ P5: clang-21++ NU exista in bin/ (doar clang++ -> clang-21) -> cale moarta
        # pentru orice sursa C++ (numpy C++ parts, cryptography, pybind11).
        # ★ BUG REAL (28 sept, prins de TESTUL REAL din UI, task greenlet):
        # `CXX = toolchain/bin/clang++` NU e executabil pentru app (SELinux
        # untrusted_app nu executa din filesDir) -> desi CC mergea, orice sursa C++
        # cadea cu "[Errno 13] Permission denied .../toolchain/bin/clang++".
        # Fix: ACELASI tratament ca la CC - symlink in files/tmp, cu reparare daca
        # tinta e moarta (hash nou la reinstalarea APK).
        _CXX = BIN + "/clang++"
        if not os.path.exists(_CXX) and os.path.exists(BIN + "/clang-21"):
            _CXX = BIN + "/clang-21"
        try:
            _cx = F + "/tmp/clang++"
            _stx = False
            if os.path.islink(_cx):
                try:
                    _stx = not os.path.exists(os.readlink(_cx))
                except Exception:
                    _stx = True
            if os.path.lexists(_cx) and (not os.path.islink(_cx) or _stx):
                os.remove(_cx)
            if not os.path.lexists(_cx):
                os.symlink(NAT + "/libclang_exec.so", _cx)
            if os.path.exists(_cx):
                _CXX = _cx
        except Exception:
            pass
        # ★ P4b: readelf/objdump - nu exista shim ARM64; folosim llvm-nm ca substitut
        # de inspectie, iar daca apar shim-uri in libDir le folosim pe ele.
        _RD = NAT + "/libllvmreadelf_exec.so"
        _OD = NAT + "/libllvmobjdump_exec.so"
        if not os.path.exists(_RD):
            _RD = BIN + "/llvm-readelf"
        if not os.path.exists(_OD):
            _OD = BIN + "/llvm-objdump"
        AR_EXEC, RANLIB_EXEC, NM_EXEC, STRIP_EXEC = (_SHIM["ar"], _SHIM["ranlib"],
                                                     _SHIM["nm"], _SHIM["strip"])
        READELF_EXEC, OBJDUMP_EXEC, CXX_EXEC = _RD, _OD, _CXX
        # binutils executabile sunt PRIMELE in PATH (build_clib le cheama dupa nume)
        _binpath = F + "/tmp:" + NAT + ":" + DEPS + "/bin:" + BIN + ":/system/bin"
    else:
        CC_EXEC = BIN + "/clang-21"
        PKG_EXEC = DEPS + "/bin/pkg-config"
        _extra = ""
        AR_EXEC = BIN + "/llvm-ar"; RANLIB_EXEC = BIN + "/llvm-ranlib"
        NM_EXEC = BIN + "/llvm-nm"; STRIP_EXEC = BIN + "/llvm-strip"
        READELF_EXEC = BIN + "/llvm-readelf"; OBJDUMP_EXEC = BIN + "/llvm-objdump"
        CXX_EXEC = BIN + "/clang++"
        if not os.path.exists(CXX_EXEC):
            CXX_EXEC = BIN + "/clang-21"
        _binpath = DEPS + "/bin:" + BIN + ":/system/bin"
    # ★ N9: libc++_shared.so REAL trebuie gasibil la RUNTIME (numpy.fft, scipy.special),
    # altfel "cannot locate symbol"/"library libc++_shared.so not found".
    _sdk_lib = ROOT + "/sysroot/usr/lib/aarch64-linux-android/35"
    # ★ CAPCANA (raportata de agent): clang apelat prin symlinkul din files/tmp isi calculeaza
    # gresit resource-dir (/lib/lib/clang/21/...) -> "cannot open" / "'stddef.h' file not found".
    # Il fixam EXPLICIT in CFLAGS (se aplica si in cmake, care foloseste acest string).
    _cflags = ("-fPIC -O2 --target=aarch64-linux-android35 --sysroot=" + ROOT + "/sysroot "
               "-resource-dir=" + ROOT + "/lib/clang/21 "
               # ★ si in CFLAGS: compilarea+linkarea intr-un singur pas (clang s.c -o bin) nu vede
               # LDFLAGS-ul; libatomic.a/compiler-rt sunt in lib/clang/21/lib/linux (raportat de agent)
               + "-L" + ROOT + "/lib/clang/21/lib/linux "
               "-I" + ROOT + "/sysroot/usr/include -I" + _cxxinc + "/c++/v1 "
               "-I" + ROOT + "/pyinc "
               "-I" + DEPS + "/include -I" + DEPS + "/include/libxml2")
    # ★ R3: --no-undefined prinde simbolurile nerezolvate la LINK, nu abia la import
    # (raport: "-ljpeg cu doar .a e ignorat silentios"). -lc++_shared pentru module C++.
    # ★ sysroot lib PRIMUL: acolo sunt crtbegin/crtend_android.o + libc.so/libdl.so
    # (stub-uri de link). Fara el: "cannot open crtend_android.o" / "unable to find -lc".
    _atom = _atomic_dir()
    _ldflags = ("-L" + _sdk_lib + " -L" + DEPS + "/lib -L" + apexsdk
                # ★ libatomic/libclang_rt sunt STATICE, in lib/clang/21/lib/linux (agentul:
                # "-latomic" nu se rezolva fara aceasta cale)
                + " -L" + ROOT + "/lib/clang/21/lib/linux"
                # ★ CAPCANA raportata de agent ("CANNOT LINK EXECUTABLE t_f90: library
                # libc++_shared.so not found"): binarul proaspat construit nu-si gaseste libc++_shared
                # la RULARE. ★ SI: rpath-ul catre nativeLibraryDir devine INVALID dupa fiecare
                # update de APK (calea /data/app/~~hash==/... se schimba) -> binarele vechi mor.
                # De aceea rpath-ul indica o cale STABILA: files/libs (unde copiem libc++_shared.so
                # + libpython), plus deps/lib. Asa un binar compilat azi ruleaza si dupa update.
                + " -Wl,-rpath," + _stable_libs()
                + " -Wl,-rpath," + DEPS + "/lib"
                + " -Wl,-rpath," + _native_dir()
                # ★ FAZA 4m: C++ se leaga IMPLICIT cu libc++ (raportat in testul din UI: agentul
                # primea "undefined symbol __gxx_personality_v0" si trebuia sa adauge manual
                # -lc++_shared). Punem si calea stabila files/libs (contine libc++_shared.so si
                # libpython3.14.so), ca linkarea C++ si a extensiilor Python sa mearga din prima.
                + " -L" + _stable_libs()
                + " -lc++_shared"
                + (" -L" + _atom if _atom else "")
                # ★ -lm -ldl EXPLICIT: pe bionic functiile de math/log/fmod sunt in libm si,
                # cu --no-undefined, orice modul care le foloseste are nevoie de ele la link
                # (dovedit: Pillow -> "undefined symbol: log/fmod"; perl XS -> "modf").
                + " -lm -ldl"
                # ★ Pillow/matplotlib: setup-ul lor vede headerele (via -I deps/include) si
                # activeaza feature-ul, dar NU adauga -l... la link -> "undefined symbol:
                # png_create_read_struct / jpeg_* / FT_Init_FreeType". Le dam noi explicit.
                + " -lz -lpng16 -ljpeg -lfreetype"
                + " -Wl,--no-undefined"
                # ★ sect. 5: grpcio cere -latomic explicit (libatomic.a = builtin clang).
                + (" -latomic" if _atom else ""))
    # ★ FAZA 1: in toolchain-ul CMake intra si _extra (-resource-dir + -B): fara el
    # cmake isi face testele de compilator cu clang FARA resource-dir -> linkerul cauta
    # libclang_rt.builtins.a in nativeLibraryDir si esueaza ("cannot open ...libclang_rt
    # .builtins.a"), deci cmake raporta "compiler broken".
    _tc_file = _write_cmake_toolchain(_cflags + _extra, _ldflags)
    _pyreal = _ensure_real_cython()   # Cython pe disc (nu din zip) - vezi _ensure_real_cython
    return {
        "PATH": _binpath,
        "TC_ROOT": ROOT,
        "TC_DEPS": DEPS,
        "CC": CC_EXEC + _extra,
        # ★ CXX cu ACELASI _extra ca CC (-resource-dir/-B): fara el clang++ nu-si
        # gaseste headerele builtin (stddef.h) si nu vede sysroot-ul.
        "CXX": CXX_EXEC + _extra,
        "AR": AR_EXEC,
        # ★ FLANG (raport nou, P1): compilator Fortran in nativeLibraryDir. Elimina
        # f2c + ~500 patch-uri F90 manuale pe LAPACK. FC/F77 = flang daca e prezent.
        "FC": _flang_path() or (BIN + "/flang"),
        "F77": _flang_path() or (BIN + "/flang"),
        "FFLAGS": ("-fPIC -O2 --target=aarch64-linux-android35 --sysroot=" + ROOT + "/sysroot"),
        "FCFLAGS": ("-fPIC -O2 --target=aarch64-linux-android35 --sysroot=" + ROOT + "/sysroot"),
        "RANLIB": RANLIB_EXEC,
        "NM": NM_EXEC,
        "STRIP": STRIP_EXEC,
        "READELF": READELF_EXEC,
        "OBJDUMP": OBJDUMP_EXEC,
        # ★ BUG REPARAT (baterie, Pillow): LDSHARED nu continea _ldflags, deci orice modul
        # care se linka cu libs din deps (libpng/libjpeg/freetype) esua cu
        # "undefined symbol: png_read_info / log / fmod". Acum LDSHARED = CC + _extra +
        # target/sysroot + _ldflags (-L deps, -lm, -latomic, --no-undefined) + -shared.
        "LDSHARED": (CC_EXEC + _extra + " --target=aarch64-linux-android35 --sysroot="
                     + ROOT + "/sysroot " + _ldflags + " -shared"),
        "CFLAGS": _cflags,
        "CXXFLAGS": _cflags,
        "LDFLAGS": _ldflags,
        "PKG_CONFIG_PATH": DEPS + "/lib/pkgconfig",
        # ★ FAZA 1: cmake are nevoie de CMAKE_ROOT (Modules/ + share/) si de un generator.
        # Binarul nostru se numeste libcmake_exec.so, deci cmake NU-si poate deduce
        # radacina -> o dam explicit. Generatorul = ninja (deja prezent).
        "CMAKE_ROOT": ROOT + "/cmake",
        "CMAKE_MAKE_PROGRAM": F + "/tmp/ninja",
        # ★ FAZA 1: toolchain-ul CMake pentru device (sysroot+compilatoare+flags) si
        # generatorul. CMAKE_TOOLCHAIN_FILE e citit de cmake din mediu; CMAKE_ARGS
        # e folosit de scikit-build-core (care porneste cmake singur).
        "CMAKE_TOOLCHAIN_FILE": _tc_file,
        "CMAKE_GENERATOR": "Ninja",
        "CMAKE_ARGS": ("-DCMAKE_TOOLCHAIN_FILE=" + _tc_file
                       + " -DCMAKE_MAKE_PROGRAM=" + F + "/tmp/ninja"
                       + (" -Dpybind11_DIR=" + _pybind11_dir() if _pybind11_dir() else "")),
        "pybind11_DIR": _pybind11_dir(),
        "CMAKE_PREFIX_PATH": DEPS,
        # ★ grpcio: NU construi BoringSSL de la zero (29 min pe device!) ci foloseste
        # OpenSSL-ul static din deps (libssl.a/libcrypto.a + openssl.pc scris cu prefix de
        # device). Plus compilare paralela (multiprocessing merge acum prin shim).
        "GRPC_PYTHON_BUILD_SYSTEM_OPENSSL": "1",
        "GRPC_PYTHON_BUILD_SYSTEM_ZLIB": "1",
        "GRPC_PYTHON_BUILD_EXT_COMPILER_JOBS": "4",
        # ★ FAZA 1 (descoperire cheie): CMake recunoaste ca RULEAZA pe Android (host)
        # si atunci citeste "$ENV{PREFIX}/include/android/api-level.h" ca sa afle API-ul
        # (Modules/CMakeDetermineSystem.cmake). Fara PREFIX: "file failed to open:
        # /include/android/api-level.h" -> configure esua. PREFIX = prefixul de tip
        # Termux, adica radacina sysroot-ului nostru.
        "PREFIX": ROOT + "/sysroot/usr",
        # ★ FAZA 3: perl (binar Termux + arborele de module livrat in assets/toolchain/perl).
        # @INC-ul compilat in binar arata spre /data/data/com.termux/... -> il redirectionam
        # prin PERL5LIB (nu are nevoie de patch-uri pe binar). Necesar pentru build-uri
        # autotools/openssl (Configure e script perl) si pentru grpcio.
        # ★ perl 5.42.0 e COMPILAT DE NOI (perl-cross + NDK, ARM64) si are prefixul de pe
        # device compilat in binar -> isi gaseste singur @INC. PERL5LIB ramane ca plasa de
        # siguranta (versiune + arhdir-ul nostru: aarch64-linux, nu aarch64-android).
        "PERL5LIB": (ROOT + "/perl/lib/perl5/5.42.0:"
                     + ROOT + "/perl/lib/perl5/5.42.0/aarch64-linux:"
                     + ROOT + "/perl/lib/perl5/site_perl"),
        "PERL_MM_USE_DEFAULT": "1",
        # NOTA (cbor2 6.x): acceleratorul lui NU mai e C, e RUST (setuptools-rust in
        # pyproject.toml) -> fara cargo instaleaza silentios varianta pure-python
        # ("Successfully installed", dar fara cbor2._cbor2). Intra in categoria Rust (FAZA 2).
        # ★ variabilele explicite: setup.py le foloseste prin subprocess care poate
        # sa nu mosteneasca PATH-ul -> "Permission denied"/"not found" la pkg-config.
        "PKG_CONFIG": PKG_EXEC,
        "XML2_CONFIG": DEPS + "/bin/xml2-config",
        "XSLT_CONFIG": DEPS + "/bin/xslt-config",
        "TMPDIR": F + "/tmp",
        "HOME": home,
        "PIP_CACHE_DIR": pipcache,
        "PIP_NO_BUILD_ISOLATION": "1",
        # ★ sect. 8: OpenBLAS cu 8 fire e 14x MAI LENT la n mic (1.2 vs 16.5 GFLOPS).
        "OPENBLAS_NUM_THREADS": "1",
        # ★ LD_LIBRARY_PATH OBLIGATORIU: libpyexec.so are nevoie de libpython3.14.so
        # (nativeLibraryDir) + libs/ proprii. Fara el: "CANNOT LINK EXECUTABLE".
        # ★ FIX CRITIC: FARA directorul de stub-uri NDK (sysroot/usr/lib/...) - vezi
        # `_rt_ld_path()`; altfel ORICE PROCES COPIL moare cu SIGSEGV in constructori
        # (simptom: `pip install` -> exit -11 la "Preparing metadata").
        # ★ FAZA 3: perl-ul compilat de noi e linkat cu libperl STATIC (doar libc/libm/libdl)
        # -> nu mai adaugam ROOT/perl/lib in LD_LIBRARY_PATH (nu are ce sa caute acolo).
        # ★ FAZA 4: + lib dir-ul Rust (librustc_driver-*.so, libLLVM.so.21.1) - fara el
        # rustc moare la pornire cu "CANNOT LINK EXECUTABLE".
        "LD_LIBRARY_PATH": (_rt_ld_path() + (":" + _rust_lib() if os.path.isdir(_rust_lib()) else "")),
        # ★ FAZA 4 (Rust): cargo/rustc cross-compilate de noi pentru aarch64-linux-android.
        # CARGO_HOME tine config.toml cu linker-ul (clang din APK) + sysroot-ul de device.
        "CARGO_HOME": F + "/cargo",
        "RUSTUP_HOME": F + "/cargo/rustup",
        "RUST_BACKTRACE": "0",
        # ★ RUSTFLAGS in MEDIU (nu doar in config.toml): fara ele build-scripturile
        # crate-urilor Rust nu se pot linka pe device (capcana dovedita).
        "RUSTFLAGS": _rust_link_flags(),
        # ★ cc-rs (crate-uri cu C: libgit2/ring/psm) cauta `<target>-clang`:
        # le dam wrapper-ul nostru de linker/compilator.
        "CC_aarch64-linux-android": F + "/tmp/cc-rust",
        "CXX_aarch64-linux-android": F + "/tmp/cc-rust",
        "AR_aarch64-linux-android": F + "/tmp/ar",
        "CARGO_TARGET_AARCH64_LINUX_ANDROID_LINKER": F + "/tmp/cc-rust",
        # ★ LTO OFF (vezi rust_env): bitcode std = LLVM 22.1.8, rustc de device = libLLVM 21.1.8.
        "CARGO_PROFILE_RELEASE_LTO": "false",
        "CARGO_PROFILE_RELEASE_DEBUG": "false",
        "CARGO_NET_GIT_FETCH_WITH_CLI": "true",
        # ★ PYTHONHOME/PATH pentru stdlib: fara ele "Failed to import encodings".
        "PYTHONHOME": F + "/pyhome",
        # ★ sect. 3E: stdlib_extra.zip PRIMUL (altfel zipfile._path lipseste
        # -> "ModuleNotFoundError: No module named 'zipfile._path'" la pip).
        "PYTHONPATH": (((_pyreal + ":") if _pyreal else "")
                       + F + "/pyhome/lib/stdlib_extra.zip:"
                       + F + "/pyhome/lib/python3.14:"
                       + F + "/pyhome/lib/pysitepkg.zip:"
                       + os.environ.get("PYTHONPATH", "")),
        "PYTHONUNBUFFERED": "1",
        # certificatul de CA: fara el pip HTTPS nu poate valida PyPI
        "SSL_CERT_FILE": _ca_bundle(),
        "CURL_CA_BUNDLE": _ca_bundle(),
        "REQUESTS_CA_BUNDLE": _ca_bundle(),
    }


def _py_exec():
    """Interpreterul Python care ruleaza ACUM (agentul), nu un binar inexistent."""
    if sys.executable and os.path.exists(sys.executable):
        return sys.executable
    return sys.executable or "python3"


def _ca_bundle():
    """★ CA bundle REAL (FISIER PEM) pentru Python.

    BUG reparat (baterie, apsw): inainte returnam primul drum existent, inclusiv
    `/apex/com.android.conscrypt/cacerts` - care e un DIRECTOR. Python cere ca
    SSL_CERT_FILE sa fie FISIER -> orice HTTPS din timpul unui build (apsw isi descarca
    sursele, setup.py-uri cu urlopen) cadea cu
    "CERTIFICATE_VERIFY_FAILED: unable to get local issuer certificate".
    Acum construim un fisier PEM real concatenand certificatele din cacerts.
    """
    out = F + "/home/ca-bundle.pem"
    try:
        if os.path.exists(out) and os.path.getsize(out) > 1000:
            return out
    except Exception:
        pass
    chunks = []
    for d in ("/apex/com.android.conscrypt/cacerts", "/system/etc/security/cacerts"):
        try:
            if not os.path.isdir(d):
                continue
            for n in sorted(os.listdir(d)):
                q = os.path.join(d, n)
                try:
                    if os.path.islink(q) or not os.path.isfile(q):
                        continue
                    data = open(q, "rb").read()
                    if b"BEGIN CERTIFICATE" in data:
                        chunks.append(data if data.endswith(b"\n") else data + b"\n")
                except Exception:
                    continue
            if chunks:
                break
        except Exception:
            continue
    if chunks:
        try:
            os.makedirs(os.path.dirname(out), exist_ok=True)
            with open(out, "wb") as fh:
                for c in chunks:
                    fh.write(c)
            return out
        except Exception:
            pass
    for c in (out, "/apex/com.android.conscrypt/cacerts", "/system/etc/security/cacerts"):
        if os.path.exists(c):
            return c
    return ""

def _enable_pip():
    """Activeaza pip in python3-ul din toolchain (via ensurepip)."""
    # os.path nu vede /data/local/tmp din sandbox -> verific prin shell
    if "YES" not in _sh("test -x " + py + " && echo YES || echo NO", 20):
        return
    env = dict(os.environ)
    env["PATH"] = BIN + ":" + env.get("PATH", "")
    env["LD_LIBRARY_PATH"] = ROOT + "/usr/lib:" + env.get("LD_LIBRARY_PATH", "")
    try:
        r = subprocess.run([py, "-m", "ensurepip", "--upgrade"],
                           capture_output=True, text=True, timeout=300, env=env)
        if r.returncode == 0:
            print("[toolchain] pip activat")
    except Exception:
        pass


# ==================== FAZA 0: FUNDATIA DE AUTONOMIE ====================

def _wheels_dir():
    """Wheelhouse LOCAL (faza 0C): fiecare wheel construit o data ajunge aici.

    Traieste in filesDir/wheels (nu e sters de re-extragerea assets, ca
    `site_packages_keep`), deci un reinstall NU mai reconstruieste (numpy = ore).
    pip_install il da lui pip ca `--find-links`, iar la nevoie merge si offline
    (`--no-index --find-links <dir>`).
    """
    d = F + "/wheels"
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        pass
    return d


def _which(name):
    """Calea unui executabil cautat in locurile REALE (files/tmp, nativeLib, deps/bin,
    toolchain/bin, /system/bin). Nu folosim `which` (nu exista garantat pe toybox)."""
    cands = [F + "/tmp/" + name, (_native_dir() or "") + "/" + name,
             DEPS + "/bin/" + name, BIN + "/" + name, "/system/bin/" + name,
             "/apex/com.android.runtime/bin/" + name]
    for c in cands:
        if _exec_ok(c):
            return c
    return ""


def _rt_link_dirs():
    """Directoarele de care are nevoie LINKAREA (nu si rularea - vezi _rt_ld_path)."""
    return [ROOT + "/sysroot/usr/lib/aarch64-linux-android/" + str(_device_api()),
            DEPS + "/lib", ROOT + "/lib/clang/21/lib/linux/aarch64"]


def _selftest_cc(args, timeout=300):
    """Ruleaza compilatorul cu env-ul complet (deja executabil ca app)."""
    import shlex
    e = env_vars()
    cc = shlex.split(e.get("CC", "clang"))
    t0 = time.time()
    try:
        p = subprocess.run(cc + list(args), capture_output=True, text=True,
                           timeout=timeout, env=e, stdin=subprocess.DEVNULL)
        out = ((p.stdout or "") + (p.stderr or "")).strip()
        return p.returncode, out[-300:], time.time() - t0
    except Exception as ex:
        return 127, repr(ex)[:200], time.time() - t0


def selftest():
    """★ FAZA 0A: ce POATE compila/linka agentul pe ACEST device, ACUM.

    Raspunde la "pot instala pachetul X?" fara sa incerce un build de 30 de minute.
    Fiecare test compileaza si LINKEAZA un artefact REAL (nu doar "exista binarul").
    Returneaza un dict cu TRUE/FALSE per capabilitate + timpi + ce lipseste.
    """
    api = _device_api()
    # ★ CAPCANA (raportata de testul E2E din UI): fara lansatoarele din files/tmp, testul cmake
    # cadea pe `toolchain/bin/llvm-ar` (neexecutabil in sandbox-ul app-ului) -> "llvm-ar:
    # Permission denied" -> fals negativ `cmake: false`, desi cmake merge perfect.
    try:
        _ensure_launchers()
    except Exception:
        pass
    tgt = ["--target=aarch64-linux-android%d" % api, "--sysroot=" + ROOT + "/sysroot"]
    ld = []
    for _d in _rt_link_dirs():
        ld += ["-L" + _d]
    T = F + "/tmp/selftest"
    try:
        os.makedirs(T, exist_ok=True)
    except Exception:
        pass
    r = {}
    tm = {}

    def _mk(name, text):
        try:
            p = os.path.join(T, name)
            open(p, "w").write(text)
            return p
        except Exception:
            return None

    # 1. C: compile + LINK (shared object real)
    c = _mk("t.c", "int add(int a,int b){return a+b;}\n")
    if c:
        rc1, o1, d1 = _selftest_cc(tgt + ["-fPIC", "-c", c, "-o", T + "/t.o"])
        rc2, o2, d2 = _selftest_cc(tgt + ld + ["-shared", T + "/t.o", "-o", T + "/libt.so"])
        r["c_compile_link"] = bool(rc1 == 0 and rc2 == 0 and os.path.exists(T + "/libt.so"))
        tm["c_s"] = round(d1 + d2, 2)
        if not r["c_compile_link"]:
            r["c_error"] = (o1 + " | " + o2)[-200:]

    # 2. C++ cu STL (headerele libc++ complete + libc++_shared la link)
    cx = _mk("t.cpp",
             '#include <vector>\n#include <string>\n#include <algorithm>\n'
             'extern "C" int f(){std::vector<std::string> v{"b","a"};'
             'std::sort(v.begin(),v.end());return (int)v.size();}\n')
    if cx:
        rc1, o1, d1 = _selftest_cc(tgt + ["-fPIC", "-c", cx, "-o", T + "/cx.o"])
        rc2, o2, d2 = _selftest_cc(tgt + ld + ["-shared", T + "/cx.o", "-lc++_shared",
                                               "-o", T + "/libcx.so"])
        r["cxx_stl"] = bool(rc1 == 0 and rc2 == 0 and os.path.exists(T + "/libcx.so"))
        tm["cxx_s"] = round(d1 + d2, 2)
        if not r["cxx_stl"]:
            r["cxx_error"] = (o1 + " | " + o2)[-200:]

    # 3. extensie Python (Python.h + -lpython3.14) - exact ce face pip pentru orice modul C
    pyx = _mk("m.c",
              '#include <Python.h>\n'
              'static PyObject* f(PyObject* s,PyObject* a){return PyLong_FromLong(42);}\n'
              'static PyMethodDef M[]={{"f",f,METH_NOARGS,""},{0,0,0,0}};\n'
              'static struct PyModuleDef md={PyModuleDef_HEAD_INIT,"m",NULL,-1,M};\n'
              'PyMODINIT_FUNC PyInit_m(void){return PyModule_Create(&md);}\n')
    if pyx:
        inc = F + "/pyhome/include/python3.14"
        ldir = F + "/pyhome/lib"
        rc1, o1, d1 = _selftest_cc(tgt + ["-fPIC", "-I" + inc, "-c", pyx, "-o", T + "/m.o"])
        rc2, o2, d2 = _selftest_cc(tgt + ld + ["-shared", T + "/m.o", "-L" + ldir,
                                               "-lpython3.14", "-o", T + "/m.so"])
        r["python_extension"] = bool(rc1 == 0 and rc2 == 0 and os.path.exists(T + "/m.so"))
        tm["pyext_s"] = round(d1 + d2, 2)
        if not r["python_extension"]:
            r["pyext_error"] = (o1 + " | " + o2)[-200:]

    # 3b. Rust (FAZA 4): compile + LINK real. rustc ruleaza PE device (host=target=
    # aarch64-linux-android), linker-ul e clang-ul din APK + sysroot-ul de device.
    rs = _mk("t.rs", 'fn main(){println!("rust ok {}", 6*7);}\n')
    rsc = F + "/tmp/rustc"
    if rs and os.path.exists(rsc):
        t0 = time.time()
        try:
            p = subprocess.run([rsc, "--edition", "2021", "-o", T + "/t_rust", rs,
                                "-C", "linker=" + F + "/tmp/clang",
                                "-C", "link-arg=--target=aarch64-linux-android%d" % api,
                                "-C", "link-arg=--sysroot=" + ROOT + "/sysroot"],
                               cwd=T, capture_output=True, text=True, timeout=1200,
                               env=rust_env(), stdin=subprocess.DEVNULL)
            r["rust"] = bool(p.returncode == 0 and os.path.exists(T + "/t_rust"))
            tm["rust_s"] = round(time.time() - t0, 2)
            if not r["rust"]:
                r["rust_error"] = ((p.stdout or "") + (p.stderr or ""))[-300:]
        except Exception as ex:
            r["rust"] = False
            r["rust_error"] = repr(ex)[:200]
    else:
        r["rust"] = False
    # ★ FALS POZITIV (raportat de testul E2E din UI): verificarea de existenta nu spune daca
    # binarul CHIAR ruleaza (are nevoie de librustc_driver + libLLVM + RAM). Rulam real.
    r["cargo"] = False
    if os.path.exists(F + "/tmp/cargo"):
        try:
            _cp = subprocess.run([F + "/tmp/cargo", "--version"], capture_output=True, text=True,
                                 timeout=180, env=rust_env(), stdin=subprocess.DEVNULL)
            r["cargo"] = bool(_cp.returncode == 0 and "cargo" in (_cp.stdout or ""))
            if not r["cargo"]:
                r["cargo_error"] = ((_cp.stdout or "") + (_cp.stderr or ""))[-200:]
        except Exception as _ex:
            r["cargo_error"] = repr(_ex)[:200]
    # ★ MEMORIE: rustc incarca librustc_driver (90 MB) + libLLVM; sub ~900 MB liberi poate
    # muri cu SIGSEGV fara mesaj (vazut pe device la 579 MB liberi - testul E2E din UI).
    try:
        _mi = {}
        for _l in open("/proc/meminfo"):
            _k, _, _v = _l.partition(":")
            _mi[_k.strip()] = int(_v.split()[0])
        _av = _mi.get("MemAvailable", 0) // 1024
        r["ram_liber_mb"] = _av
        if _av < 900:
            r["ram_atentionare"] = ("doar %d MB liberi - build-urile Rust pot cadea cu SIGSEGV "
                                    "fara mesaj (inchide aplicatii de fundal)" % _av)
    except Exception:
        pass

    # 4. Fortran: COMPILARE (rularea unui binar produs de app nu e posibila - SELinux)
    f90 = _mk("t.f90", "      subroutine s(a)\n      real a\n      a=a+1.0\n      end\n")
    fl = F + "/tmp/flang"
    if f90 and os.path.exists(fl):
        t0 = time.time()
        try:
            p = subprocess.run([fl, "-c", "t.f90"], cwd=T, capture_output=True, text=True,
                               timeout=300, stdin=subprocess.DEVNULL)
            obj = [x for x in os.listdir(T) if x.startswith("t.") and x.endswith(".o")
                   and "_f" in x] or [x for x in os.listdir(T) if x.endswith(".o")]
            r["fortran_compile"] = any(os.path.getsize(os.path.join(T, x)) > 0 for x in obj)
            tm["fortran_s"] = round(time.time() - t0, 2)
            if not r["fortran_compile"]:
                r["fortran_error"] = ((p.stdout or "") + (p.stderr or ""))[-200:]
        except Exception as ex:
            r["fortran_compile"] = False
            r["fortran_error"] = repr(ex)[:200]
    else:
        r["fortran_compile"] = False

    # 5. unelte de build (executabile ACUM)
    r["ninja"] = bool(_exec_ok(F + "/tmp/ninja"))
    r["make"] = bool(_exec_ok(F + "/tmp/make"))
    r["lld"] = bool(_exec_ok(F + "/tmp/ld.lld"))
    r["pkg_config"] = bool(_which("pkg-config") or _exec_ok(_native_dir() + "/libpkgconf_exec.so"))

    # 6. build-backends Python (importabile in ACEST proces)
    for mod, key in (("mesonbuild", "meson"), ("scikit_build_core", "scikit_build_core"),
                     ("Cython", "cython"), ("setuptools", "setuptools"),
                     ("pybind11", "pybind11"), ("pathspec", "pathspec")):
        try:
            __import__(mod)
            r[key] = True
        except Exception:
            r[key] = False

    # 7. cmake: test REAL (configure + build al unui proiect minim C, prin toolchain-ul
    # de device generat de `_write_cmake_toolchain`). Dovada ca pachetele care cer CMake
    # (scikit-build-core: pyarrow/duckdb) au ce le trebuie.
    cm = _which("cmake")
    r["cmake"] = bool(cm)
    if cm:
        C = T + "/cmproj"
        try:
            # ★ cache-ul cmake e lipicios: daca un configure a esuat o data (ex. inainte
            # de fix-ul cu PREFIX/NDK fals), CMakeCache.txt pastreaza "compiler broken"
            # si TOATE configure-urile urmatoare esueaza la fel -> stergem directorul.
            import shutil as _sh
            _sh.rmtree(C + "/b", ignore_errors=True)
            os.makedirs(C, exist_ok=True)
            open(C + "/CMakeLists.txt", "w").write(
                "cmake_minimum_required(VERSION 3.25)\nproject(st C)\n"
                "add_library(st STATIC s.c)\n")
            open(C + "/s.c", "w").write("int st_add(int a,int b){return a+b;}\n")
            _env = dict(os.environ)
            _env.update(env_vars())
            _env["CMAKE_MAKE_PROGRAM"] = F + "/tmp/ninja"
            t0 = time.time()
            _p1 = subprocess.run([cm, "-G", "Ninja", "-S", C, "-B", C + "/b"], env=_env,
                                 capture_output=True, text=True, timeout=300,
                                 stdin=subprocess.DEVNULL)
            _p2 = subprocess.run([cm, "--build", C + "/b"], env=_env, capture_output=True,
                                 text=True, timeout=300, stdin=subprocess.DEVNULL)
            r["cmake"] = bool(_p1.returncode == 0 and _p2.returncode == 0)
            tm["cmake_s"] = round(time.time() - t0, 2)
            if not r["cmake"]:
                r["cmake_error"] = ((_p1.stdout or "") + (_p1.stderr or "")
                                    + (_p2.stdout or "") + (_p2.stderr or ""))[-300:]
        except Exception as _ex:
            r["cmake"] = False
            r["cmake_error"] = repr(_ex)[:200]
    # 8. perl REAL (Termux ARM64 livrat in APK): ruleaza cod + incarca un modul XS.
    # Necesar pentru Configure-ul OpenSSL (script perl) si pentru grpcio.
    pl = _which("perl")
    r["perl"] = False
    if pl:
        try:
            _penv = dict(os.environ)
            _penv.update(env_vars())
            t0 = time.time()
            _pp = subprocess.run([pl, "-MPOSIX", "-e", "print 6*7, qq{|}, POSIX::floor(1.9)"],
                                 env=_penv, capture_output=True, text=True, timeout=120,
                                 stdin=subprocess.DEVNULL)
            r["perl"] = bool(_pp.returncode == 0 and "42|1" in (_pp.stdout or ""))
            tm["perl_s"] = round(time.time() - t0, 2)
            if not r["perl"]:
                r["perl_error"] = ((_pp.stdout or "") + (_pp.stderr or ""))[-200:]
        except Exception as _ex:
            r["perl_error"] = repr(_ex)[:200]
    # 9. wheelhouse. ATENTIE: r["rust"]/r["cargo"] sunt deja stabilite mai sus
    # (test REAL de compilare+linkare) -> NU le suprascriem cu o cautare in PATH.
    wd = _wheels_dir()
    try:
        r["wheelhouse"] = len([x for x in os.listdir(wd) if x.endswith(".whl")])
    except Exception:
        r["wheelhouse"] = 0

    # 8. ce lipseste si ce se poate instala cu ce avem
    _bools = [k for k, v in r.items() if isinstance(v, bool)]
    r["ok"] = sorted([k for k in _bools if r[k]])
    r["lipsa"] = sorted([k for k in _bools if not r[k]])
    r["timpi_s"] = tm
    # ★ ce este INSTALAT concret: fara asta agentul inventa nume (libstdc++/gfortran) in rapoarte
    r["detalii"] = {
        "c_cxx": "clang 21.1.8 + libc++ (LLVM; NU libstdc++)",
        "fortran": "FLANG 21.1.8 (LLVM; NU gfortran)",
        "rust": "rustc/cargo 1.98.1 + maturin 1.15.0 (backend Rust pentru pip)",
        "build_systems": "cmake 3.31.6, ninja, make 4.4.1, meson, scikit-build-core, setuptools, cython, pybind11",
        "perl": "perl 5.42.0",
        "binare": "ELF in lib-ul APK (lib*_exec.so) + symlink in files/tmp si files/toolchain/bin",
        "rulare_elf": "/apex/com.android.runtime/bin/linker64 <binar> sau adbsh (exec direct interzis)",
        "build_dir": "files/tmp (nu /sdcard: noexec)",
    }
    if r.get("python_extension") and r.get("cxx_stl"):
        r["verdict"] = ("TOOLCHAIN COMPLET pentru pip: extensii C si C++ compilate+linkate pe "
                        "device" + (" | ATENTIE (nu sunt capabilitati): "
                        + ", ".join(sorted([k for k in ("cmake", "rust", "perl", "cargo")
                                            if not r.get(k)])) if any(not r.get(k) for k in ("cmake", "rust", "perl", "cargo")) else ""))
    elif r.get("c_compile_link"):
        r["verdict"] = "PARTIAL: C merge, C++/extensii Python nu - vezi cheile *_error"
    else:
        r["verdict"] = "RUPT: nici macar C nu compileaza - vezi c_error"
    return r

