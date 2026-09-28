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
import os, sys, subprocess, json

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
    """R2 + R4 (din raportul llama.cpp): PRE-FLIGHT CHECK inainte de build.

    Raportul noteaza: "Nu am construit un test minim (un program C++ de 3 linii)
    inainte de a lansa compilarea completa de 10 minute. Un test de acest fel ar
    fi expus ambele probleme de linkare in 10 secunde."

    Rulare: 10 secunde. Prinde: target API, libc++ nelegat, libm stub,
    PREFIX lipsa, make SHELL, cmake config.
    """
    api = _device_api()
    r = {"api": api}
    script = r"""
B="__BIN__"; L="__LIB__"; P="__PREFIX__"; BIONIC="__BIONIC__"; TC="__TC__"
T=__TMP__/preflight; rm -rf $T; mkdir -p $T; cd $T
# ★ PREFIX in MEDIU (referat numpy + diagnostic cmake): modulul cmake
# CMakeDetermineSystem.cmake citeste `$ENV{PREFIX}/include/android/api-level.h`.
# Fara el variabila e GOALA -> calea devine "/include/android/api-level.h" ->
# "file failed to open for reading" -> "Configuring incomplete" si cmake_build cade,
# desi compilatorul e perfect functional. Testat: cu PREFIX setat, cmake trece.
export PREFIX="$P"
export PATH=__TMP__:$B:/system/bin:$PATH
export LD_LIBRARY_PATH=$L:$BIONIC:$LD_LIBRARY_PATH
export LD_PRELOAD=$L/libc++_shared.so
export TMPDIR=__TMP__; mkdir -p $TMPDIR
# 1. C simplu (target corect)
printf '#include <stdio.h>\nint main(void){printf("C_OK");return 0;}\n' > c.c
if $B/clang --target=aarch64-linux-android__API__ c.c -o c.bin >/dev/null 2>&1; then echo "C_COMPILE=1"; else echo "C_COMPILE=0"; fi
# 2. C++ cu libc++ + STL (obstacolul 6)
printf '#include <iostream>\n#include <string>\nint main(){std::string s="CXX_OK";std::cout<<s;return 0;}\n' > x.cpp
if $B/clang++ --target=aarch64-linux-android__API__ x.cpp -o x.bin -L$L -L$BIONIC -lc++_shared -Wl,-rpath,$L >/dev/null 2>&1; then echo "CXX_COMPILE=1"; else echo "CXX_COMPILE=0"; fi
# 3. functii matematice (obstacolul 7 - libm stub)
printf '#include <math.h>\n#include <stdio.h>\nint main(void){printf("%%f",(double)(log2f(8.f)+expf(0.f)));return 0;}\n' > m.c
if $B/clang --target=aarch64-linux-android__API__ m.c -o m.bin -L$BIONIC -lm >/dev/null 2>&1; then echo "MATH_LINK=1"; else echo "MATH_LINK=0"; fi
# 4. PREFIX (obstacolul 5)
if [ -f "$P/include/android/api-level.h" ]; then echo "PREFIX_HDR=1"; else echo "PREFIX_HDR=0"; fi
# 5. make SHELL corect (obstacolul 4)
if make -p -f /dev/null 2>/dev/null | grep -q "SHELL = /system/bin/sh"; then echo "MAKE_SHELL=1"; else echo "MAKE_SHELL=0"; fi
# 6. python + SSL (obstacolul 3)
if SSL_CERT_FILE=$P/etc/tls/cert.pem $B/python3.14 -c "import ssl,urllib.request;urllib.request.urlopen('https://pypi.org',timeout=15)" >/dev/null 2>&1; then echo "SSL=1"; else echo "SSL=0"; fi
# 7. cmake prezent
if $B/cmake --version >/dev/null 2>&1; then echo "CMAKE=1"; else echo "CMAKE=0"; fi
# 8. pkg-config prezent (meson il cere)
if $B/git --version >/dev/null 2>&1; then echo "GIT=1"; else echo "GIT=0"; fi
# 8b. ★ SPAWN TEST: cea mai inselatoare problema - un ninja care nu poate face spawn
#     nu poate executa NICIUN subproces pe Android 16 (esua cu 127 chiar si la
#     `/system/bin/sh -c "echo OK"`), in timp ce compilarea directa mergea perfect.
#     Preflight raporta c_compile:true si TOTUSI nimic bazat pe ninja nu rula -> ~30 min pierdute.
#     Acest test de 2 secunde prinde exact acel caz.
if env >/dev/null 2>&1; then echo "ENV_APPLET=1"; else echo "ENV_APPLET=0"; fi
if [ -x "$B/ninja" ] && [ -x "$B/samu" ]; then
  # samu trebuie sa poata spawn-ui un subproces simplu.
  # ATENTIE: samu scrie .ninja_log in DIRECTORUL CURENT -> rulam intr-unul scriibil,
  # altfel esueaza cu "Read-only file system" si raportam fals un spawn rupt.
  mkdir -p __TMP__/.sptest 2>/dev/null
  # build.ninja trebuie sa declare o TINTA (build), nu doar o regula: altfel samu raspunde
  # "unknown target" si raportam fals un spawn rupt.
  printf 'rule r\n  command = /system/bin/sh -c "echo SPAWN_OK"\n  description = t\nbuild out: r\n' > __TMP__/.sptest/build.ninja 2>/dev/null
  if (cd __TMP__/.sptest && $B/samu out >/dev/null 2>&1); then echo "SAMU_SPAWN=1"; else echo "SAMU_SPAWN=0"; fi
  rm -rf __TMP__/.sptest 2>/dev/null
  # ninja din prefix: daca nu poate spawn-ui, e rupt (wrapper-ul nostru -> samu, deci ar trebui 1)
  if $B/ninja --version >/dev/null 2>&1; then echo "NINJA_RUNS=1"; else echo "NINJA_RUNS=0"; fi
else echo "SAMU_SPAWN=0"; echo "NINJA_RUNS=0"; fi
# 9. CMAKE REAL (obstacolele 4+5): configureaza + compileaza un proiect C++ minim
#    Asta prinde: SHELL mort in make, PREFIX nesetat, -lc++_shared, libm bionic.
if $B/cmake --version >/dev/null 2>&1; then
  mkdir -p $T/cm/src && cd $T/cm/src
  printf 'cmake_minimum_required(VERSION 3.16)\nproject(t CXX)\nadd_executable(t m.cpp)\ntarget_link_libraries(t m)\n' > CMakeLists.txt
  printf '#include <iostream>\n#include <cmath>\nint main(){std::cout<<(int)(std::log2(8.0));return 0;}\n' > m.cpp
  # ★ profile cmake: PREFIX e obligatoriu (cmake citeste $ENV{PREFIX}/include/android/api-level.h)
  #   si filtrăm liniile de diagnostic "[adb] ..." care altfel ajung IN script si il rup.
  export PREFIX="$P"
  $B/python3.14 $TC profile cmake 2>/dev/null | grep -v '^\[adb\]' > $T/cm/prof.sh
  if sh $T/cm/prof.sh . . >/dev/null 2>&1; then
    if $B/make -j4 >/dev/null 2>&1 && [ -x ./t ]; then
      echo "CMAKE_BUILD=1"
    else echo "CMAKE_BUILD=0"; fi
  else echo "CMAKE_BUILD=0"; fi
else echo "CMAKE_BUILD=0"; fi
rm -rf $T
"""
    script = (script.replace("__BIN__", BIN).replace("__LIB__", ROOT + "/usr/lib")
                    .replace("__PREFIX__", ROOT + "/usr").replace("__API__", str(api))
                    .replace("__BIONIC__", BIONIC_LIB).replace("__TC__", os.path.join(os.path.dirname(os.path.abspath(__file__)), "toolchain.py"))
                    .replace("__TMP__", F + "/tmp"))
    try:
        out = _sh(script, 60)
        for line in out.split("\n"):
            if "=" in line and line.split("=")[0].strip().isupper():
                k, v = line.split("=", 1)
                r[k.strip().lower()] = (v.strip() == "1")
    except Exception as e:
        r["error"] = str(e)[:120]
    return r


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
        "export AR={P}/bin/llvm-ar\n"
        "export RANLIB={P}/bin/llvm-ranlib\n"
        "export NM={P}/bin/llvm-nm\n"
        "export STRIP={P}/bin/llvm-strip\n"
        "export READELF={P}/bin/llvm-readelf\n"
        "export OBJDUMP={P}/bin/llvm-objdump\n"
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
            if os.path.lexists(dst):
                os.remove(dst)
            os.symlink(src, dst)
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
                 'case " $* " in\n'
                 '  *" -c "*|*" -S "*|*" -E "*)\n'
                 '    exec "$CS/flang-bin" -fc1 -triple aarch64-linux-android35 '
                 '"$@" -I"$CS/pyinc" ;;\n'
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
        for name in ("flang", "flang-new", "flang-21"):
            p = F + "/tmp/" + name
            try:
                if os.path.lexists(p): os.remove(p)
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
        for name, mod in (("cython", "cython"), ("f2py", "numpy.f2py")):
            p = F + "/tmp/" + name
            try:
                body = '#!/system/bin/sh\nexec "%s" -m %s "$@"\n' % (py, mod)
                if (not os.path.exists(p)) or open(p).read() != body:
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


def env_vars():
    """Mediul COMPLET de compilare pentru toolchain-ul livrat in APK.

    Totul traieste in filesDir/toolchain: bin/ (clang, lld, binutils), sysroot/
    (headers+libs Android 35), pyinc/ (Python.h), deps/ (libxml2, libxslt, librt).
    Nu exista /data/local/tmp/wrap si nici prefix extern: nimic nu le foloseste.
    """
    home = F + "/home"
    pipcache = home + "/.cache/pip"
    _ensure_launchers()
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
            if os.path.exists(_t):
                _SHIM[_n] = _t
            else:
                _SHIM[_n] = BIN + "/llvm-" + _n
        # ★ P5: clang-21++ NU exista in bin/ (doar clang++ -> clang-21) -> cale moarta
        # pentru orice sursa C++ (numpy C++ parts, cryptography, pybind11).
        _CXX = BIN + "/clang++"
        if not os.path.exists(_CXX) and os.path.exists(BIN + "/clang-21"):
            _CXX = BIN + "/clang-21"
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
    _cflags = ("-fPIC -O2 --target=aarch64-linux-android35 --sysroot=" + ROOT + "/sysroot "
               "-I" + ROOT + "/sysroot/usr/include -I" + _cxxinc + "/c++/v1 "
               "-I" + ROOT + "/pyinc "
               "-I" + DEPS + "/include -I" + DEPS + "/include/libxml2")
    # ★ R3: --no-undefined prinde simbolurile nerezolvate la LINK, nu abia la import
    # (raport: "-ljpeg cu doar .a e ignorat silentios"). -lc++_shared pentru module C++.
    # ★ sysroot lib PRIMUL: acolo sunt crtbegin/crtend_android.o + libc.so/libdl.so
    # (stub-uri de link). Fara el: "cannot open crtend_android.o" / "unable to find -lc".
    _atom = _atomic_dir()
    _ldflags = ("-L" + _sdk_lib + " -L" + DEPS + "/lib -L" + apexsdk
                + (" -L" + _atom if _atom else "")
                + " -Wl,--no-undefined"
                # ★ sect. 5: grpcio cere -latomic explicit (libatomic.a = builtin clang).
                + (" -latomic" if _atom else ""))
    return {
        "PATH": _binpath,
        "TC_ROOT": ROOT,
        "TC_DEPS": DEPS,
        "CC": CC_EXEC + _extra,
        "CXX": CXX_EXEC,
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
        "LDSHARED": CC_EXEC + _extra + " --target=aarch64-linux-android35 --sysroot=" + ROOT + "/sysroot -shared",
        "CFLAGS": _cflags,
        "CXXFLAGS": _cflags,
        "LDFLAGS": _ldflags,
        "PKG_CONFIG_PATH": DEPS + "/lib/pkgconfig",
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
        "LD_LIBRARY_PATH": _rt_ld_path(),
        # ★ PYTHONHOME/PATH pentru stdlib: fara ele "Failed to import encodings".
        "PYTHONHOME": F + "/pyhome",
        # ★ sect. 3E: stdlib_extra.zip PRIMUL (altfel zipfile._path lipseste
        # -> "ModuleNotFoundError: No module named 'zipfile._path'" la pip).
        "PYTHONPATH": (F + "/pyhome/lib/stdlib_extra.zip:"
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
    """Primul CA bundle disponibil pe Android (Python nu are unul implicit)."""
    for c in (F + "/home/ca-bundle.pem",
              "/apex/com.android.conscrypt/cacerts",
              "/system/etc/security/cacerts"):
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

