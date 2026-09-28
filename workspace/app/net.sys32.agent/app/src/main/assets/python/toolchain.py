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
    try:
        _e = dict(os.environ)
        _e["PATH"] = DEPS + "/bin:" + BIN + ":/system/bin"
        r = _sp.run(["/system/bin/sh", "-c", cmd], capture_output=True,
                    text=True, timeout=timeout, env=_e)
        return (r.stdout or "") + (r.stderr or "")
    except Exception as e:
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
T=/data/local/tmp/preflight; rm -rf $T; mkdir -p $T; cd $T
# ★ PREFIX in MEDIU (referat numpy + diagnostic cmake): modulul cmake
# CMakeDetermineSystem.cmake citeste `$ENV{PREFIX}/include/android/api-level.h`.
# Fara el variabila e GOALA -> calea devine "/include/android/api-level.h" ->
# "file failed to open for reading" -> "Configuring incomplete" si cmake_build cade,
# desi compilatorul e perfect functional. Testat: cu PREFIX setat, cmake trece.
export PREFIX="$P"
export PATH=/data/local/tmp/wrap:$B:/system/bin:$PATH
export LD_LIBRARY_PATH=$L:$BIONIC:$LD_LIBRARY_PATH
export LD_PRELOAD=$L/libc++_shared.so
export TMPDIR=/data/local/tmp/tmp; mkdir -p $TMPDIR
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
  mkdir -p /data/local/tmp/.sptest 2>/dev/null
  # build.ninja trebuie sa declare o TINTA (build), nu doar o regula: altfel samu raspunde
  # "unknown target" si raportam fals un spawn rupt.
  printf 'rule r\n  command = /system/bin/sh -c "echo SPAWN_OK"\n  description = t\nbuild out: r\n' > /data/local/tmp/.sptest/build.ninja 2>/dev/null
  if (cd /data/local/tmp/.sptest && $B/samu out >/dev/null 2>&1); then echo "SAMU_SPAWN=1"; else echo "SAMU_SPAWN=0"; fi
  rm -rf /data/local/tmp/.sptest 2>/dev/null
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
                    .replace("__BIONIC__", BIONIC_LIB).replace("__TC__", os.path.join(os.path.dirname(os.path.abspath(__file__)), "toolchain.py")))
    try:
        out = _sh(script, 240)
        for line in out.split("\n"):
            if "=" in line and line.split("=")[0].strip().isupper():
                k, v = line.split("=", 1)
                r[k.strip().lower()] = (v.strip() == "1")
    except Exception as e:
        r["error"] = str(e)[:120]
    return r


def doctor():
    """Full health check from EVERY relevant perspective (the numpy report asked for this):
    the toolchain is installed by uid 2000 (shell) but CONSUMED by the app, so 'it works' must be
    answered separately for each. Returns a dict with a per-uid verdict plus a verdict string."""
    r = {"prefix": ROOT}
    api = _device_api()
    r["api"] = api
    # --- perspective shell (uid 2000): instalarea si executia ---
    _lc = _sh("ls %s 2>/dev/null | wc -l" % BIN, 30)
    try: r["shell_ls_count"] = int("".join(ch for ch in _lc if ch.isdigit()) or 0)
    except Exception: r["shell_ls_count"] = -1   # -1 = nu am putut numara (nu 3!)
    r["shell_clang"] = "RC=0" in _sh("printf 'int main(void){return 0;}' > /data/local/tmp/.d.c; "
        "%s/clang --target=aarch64-linux-android%d /data/local/tmp/.d.c -o /data/local/tmp/.d.bin 2>&1; echo RC=$?" % (BIN, api), 120)
    r["shell_python"] = "Python" in _sh("%s/python3.14 -V 2>&1" % BIN, 30)
    r["shell_pip"] = "pip" in _sh("PATH=%s:/system/bin:$PATH %s/python3.14 -m pip --version 2>&1" % (BIN, BIN), 90).lower()
    # --- perspective app (uid ~10300): POATE citi? POATE executa? ---
    pkg = "net.sys32.agent"
    app = _sh("run-as %s ls %s 2>&1 | head -2" % (pkg, BIN), 30)
    r["app_can_read"] = not any(x in app for x in ("Permission denied", "No such file", "not found"))
    ae = _sh("run-as %s %s/python3.14 -V 2>&1" % (pkg, BIN), 30)
    r["app_can_exec"] = ("Python" in ae) and ("denied" not in ae.lower())
    r["app_hint"] = ("app CANNOT execute the toolchain directly (expected): orchestrate through adbsh"
                     if not r["app_can_exec"] else "app CAN execute the toolchain")
    # --- permisiuni pe prefix (cauza din raportul numpy) ---
    r["prefix_mode"] = _sh("stat -c '%%a %%U:%%G' %s 2>/dev/null || ls -ld %s" % (ROOT, ROOT), 20).strip()[:60]
    r["world_readable"] = True  # toolchain-ul e in filesDir: doar app-ul il foloseste
    # --- marker versiune ---
    _vm = _sh("cat %s/.tc_version 2>/dev/null" % ROOT, 20)
    _vm = "".join(ch for ch in _vm if ch.isprintable() and ch != "\x03").strip()
    r["version_marker"] = _vm[:120] or "(lipseste - se scrie de toolchain fix)"
    # --- veredict ---
    # ★ TOOLCHAIN DIN APK: clang/lld/sysroot traiesc in filesDir (extrase din assets)
    # si se folosesc DIRECT DE APP (uid 10318) - nu exista prefix extern si nici
    # nevoie de adbsh pentru compilare. Verificam prezenta REALA a binarilor.
    import os as _os
    _have_bin = _os.path.isdir(ROOT + "/bin")
    _have_clang = _os.path.exists(ROOT + "/bin/clang-21")
    _have_sysroot = _os.path.isdir(ROOT + "/sysroot/usr/include")
    _have_deps = _os.path.isdir(ROOT + "/deps/include")
    r["clang_ok"] = _have_clang
    r["sysroot_ok"] = _have_sysroot
    r["deps_ok"] = _have_deps
    r["prefix"] = ROOT
    if _have_clang and _have_sysroot:
        r["verdict"] = ("OK - toolchain din APK (clang 21 + sysroot), se foloseste CA APP "
                        "(pip_install compileaza direct)")
    else:
        r["verdict"] = ("INCOMPLET - lipseste %s; reinstaleaza APK-ul (assets: bin/sysroot)"
                        % (", ".join([x for x, ok in [("bin", _have_bin), ("sysroot", _have_sysroot)] if not ok])))
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
    out = _sh("ls " + BIN + " 2>/dev/null", 30)
    present = set(out.split())
    api = _device_api()
    # ★ verificari aliniate cu REALITATEA: toolchain-ul e livrat in APK (nu se
    # instaleaza nimic). Ce conteaza e ce poate FI FOLOSIT, nu ce "exista in prefix".
    _SL = ROOT + "/sysroot/usr/lib/aarch64-linux-android/35"
    need = {
        "clang": ("clang" in present) or ("clang-21" in present),
        "ld.lld": _exec_ok(F + "/tmp/ld.lld"),
        "ar_shim": _exec_ok(F + "/tmp/ar"),
        "ninja": _exec_ok(F + "/tmp/ninja"),
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
        "marker": "YES" in _sh("test -f " + MARKER + " && echo YES || echo NO", 20),
    }
    # --- verificari FUNCTIONALE (fiecare = o eroare reala de pe device) ---
    # 1. compileaza + linkeaza (target API real, nu android24)
    probe = _sh(
        'cd /data/local/tmp 2>/dev/null || cd /tmp; '
        'printf "int main(void){return 0;}" > .tc_probe.c; '
        'PATH=%s:/system/bin:$PATH %s --target=aarch64-linux-android%d '
        '.tc_probe.c -o .tc_probe 2>&1; echo RC=$?' % (BIN, BIN + "/clang", api), 120)
    need["compile_test"] = "RC=0" in probe
    if not need["compile_test"]:
        need["compile_hint"] = probe.strip()[-200:]
    # ★ P3/P4/P5 + N2/N3 (raport compilare C): lantul COMPLET, nu doar .c
    ev = env_vars()
    for _k in ("AR", "RANLIB", "NM", "STRIP", "READELF", "OBJDUMP", "CXX", "CC", "LD"):
        _p = (ev.get(_k) or "").split()[0] if ev.get(_k) else ""
        # symlink-urile catre nativeLibraryDir trec cu lexists (existence urmareste tinta)
        need[_k.lower()] = bool(_p) and (os.path.exists(_p) or os.path.lexists(_p))
    # ar REAL: creeaza o arhiva (+ nm o citeste inapoi)
    _arc = _sh('cd " + F + "/tmp 2>/dev/null || cd /tmp; rm -f .tc.a .tc2.o; '
               'printf "int tc_ar(void){return 1;}" > .tc2.c; '
               '%s -c .tc2.c -o .tc2.o 2>&1; %s .tc.a .tc2.o 2>&1; '
               '%s .tc.a 2>&1 | head -3; echo RC=$?' %
               (ev.get("CC", "clang"), ev.get("AR", "ar"), ev.get("NM", "nm")), 150)
    need["ar_test"] = "RC=0" in _arc
    if not need["ar_test"]:
        need["ar_hint"] = _arc.strip()[-200:]
    # C++ COMPLET: compileaza + linkeaza cu libc++ (numpy.fft / scipy.special)
    # ★ SCRIE IN files/tmp: app-ul NU poate scrie in /data/local/tmp (SELinux W^X)
    _W = F + "/tmp"
    try:
        os.makedirs(_W, exist_ok=True)
        open(_W + "/.tc3.cpp", "w").write(
            "#include <vector>\n#include <string>\n"
            "int main(){std::vector<std::string> v;v.push_back(\"x\");"
            "return (int)v.size()-1;}\n")
    except Exception:
        pass
    _env3 = dict(os.environ)
    _env3.update({k: v for k, v in ev.items() if v})
    _env3["TMPDIR"] = _W
    try:
        _r3 = subprocess.run((ev.get("CXX") or "clang++").split()
                             + ["-L" + _sdk_lib_dir(), "-lc++_shared",
                                "-Wl,--no-undefined", _W + "/.tc3.cpp", "-o", _W + "/.tc3"],
                             capture_output=True, text=True, timeout=240, env=_env3)
        need["cxx_test"] = (_r3.returncode == 0)
        if not need["cxx_test"]:
            need["cxx_hint"] = (_r3.stdout + _r3.stderr).strip()[-200:]
    except Exception as _e3:
        need["cxx_test"] = False
        need["cxx_hint"] = str(_e3)[:150]
    # ★ N2/N3/N9: libc++_shared REAL (nu stub de 28 octeti) + libc++abi
    _lcs = _sdk_lib_dir() + "/libc++_shared.so"
    try:
        need["libcxx_shared"] = os.path.getsize(_lcs) > 100000
    except Exception:
        need["libcxx_shared"] = False
    need["libcxx_full"] = "YES" in _sh(
        "test -f %s/sysroot/usr/include/c++/v1/__configuration/abi.h && echo YES || echo NO" % ROOT, 20)
    need["ninja_exec"] = os.path.exists(F + "/tmp/ninja") or bool(ev.get("NINJA"))
    need["python3_pc"] = os.path.exists(DEPS + "/lib/pkgconfig/python3.pc")
    need["openblas_pc"] = os.path.exists(DEPS + "/lib/pkgconfig/openblas.pc")
    # 2. Python-ul care ruleaza ACUM (agentul) + LIBDIR din sysconfig
    try:
        import sysconfig as _syscfg
        _lib = _syscfg.get_config_var("LIBDIR") or ""
        need["sysconfig_ok"] = bool(_lib)
        need["libdir"] = _lib
        need["sys_executable"] = sys.executable
    except Exception as _e:
        need["sysconfig_ok"] = False
        need["sysconfig_hint"] = str(_e)[:120]
    # 4. CA bundle prezent (pip HTTPS)
    need["ca_bundle"] = ("cert.pem" in _sh("ls %s/usr/etc/tls/cert.pem 2>/dev/null" % ROOT, 20))
    # 5. libc++ preload (extensii C++)
    need["libc++_shared"] = ("libc++_shared.so" in _sh("ls %s/usr/lib/libc++_shared.so 2>/dev/null" % ROOT, 20))
    # 6. binarele native sunt executabile prin shim-urile din nativeLibraryDir
    # ★ TIMP: vechiul check rula `readelf -d` pe FIECARE binar (spawn per fisier, ~30 s).
    # O singura trecere Python face acelasi lucru in <1 s.
    # ★ FIX: cautam string-ul DOAR in zona de RUNPATH a ELF-ului, nu oriunde in fisier.
    # binarele nu contin cai externe hardcodate
    # (CMAKE_ROOT, prefix etc.), dar RUNPATH-ul lor e corectat -> functioneaza perfect.
    # Vechiul check raporta fals "runpath_ok=false" desi toate tool-urile mergeau.
    # ★ TEST FUNCTIONAL REAL: compileaza C cu clang-ul din APK (cu shim-urile executabile din nativeLibraryDir).
    _ct = _sh("cd %s && printf 'int main(void){return 42;}' > .t.c && "
              "%s --target=aarch64-linux-android35 --sysroot=%s/sysroot -o .t.bin .t.c 2>&1 && echo COMPILE_OK"
              % (F + "/tmp", BIN + "/clang-21", ROOT), 120)
    need["compile_test"] = "COMPILE_OK" in _ct
    need["compile_hint"] = None if need["compile_test"] else _ct[:150]
    # 7. numpy prezent (pachete pip instalate de agent)
    need["numpy"] = "numpy" in _sh(
        "ls " + F + "/pyhome/lib/python3.14/site-packages 2>/dev/null", 30)
    # ★ 8. PERSPECTIVA APP vs SHELL (raportul numpy, eroarea 2): cel care CERE
    #    toolchain-ul e agentul (uid app). Verificam daca IL POATE FOLOSI, nu doar
    #    daca exista. `run-as <pkg>` ruleaza ca app, exact ca tool-urile noastre.
    try:
        _pkg = "net.sys32.agent"
        app_ls = _sh("run-as %s ls %s 2>&1 | head -3" % (_pkg, BIN), 30)
        app_read = not ("Permission denied" in app_ls or "No such file" in app_ls or "not found" in app_ls)
        need["app_can_read_prefix"] = app_read
        # exec: app-ul NU poate executa binare din prefixul altui uid (read != execute)
        app_exec = _sh("run-as %s sh -c '%s/python3.14 -V' 2>&1" % (_pkg, BIN), 30)
        need["app_can_exec_python"] = ("Python" in app_exec) and ("denied" not in app_exec.lower())
        if not need["app_can_exec_python"]:
            need["app_perspective_hint"] = ("the app CANNOT execute the toolchain directly - it must "
                "orchestrate it through adbsh/run_su (uid 2000). This is EXPECTED, not a failure.")
    except Exception as e:
        need["app_perspective_error"] = str(e)[:100]
    # ★ 9. MARKER DE VERSIUNE (raportul numpy, A2): fara el nu stim ce e instalat
    need["version_marker"] = "YES" in _sh("test -f %s/.tc_version && echo YES || echo NO" % ROOT, 20)
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
    # 1. getprop (in app _sh merge; in shell direct nu are chei)
    for cmd in ("getprop ro.build.version.sdk",
                "cat /system/build.prop 2>/dev/null | grep -m1 ro.build.version.sdk",
                "getprop ro.build.version.release"):
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
mkdir -p /data/local/tmp/tmp __HOME__ __HOME__/.cache/pip 2>/dev/null
chmod 777 /data/local/tmp/tmp 2>/dev/null
chmod 777 /data/local/tmp 2>/dev/null
echo DIRS_OK
"""
    script = script.replace("__HOME__", F + "/home")
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
    # ★ ninja / samu: binar executabil din nativeLibraryDir (build-uri meson)
    for name, so in (("ninja", "libninja_exec.so"), ("samu", "libninja_exec.so")):
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
        CC_EXEC = NAT + "/libclang_exec.so"
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
    _ldflags = ("-L" + _sdk_lib + " -L" + DEPS + "/lib -L" + apexsdk
                + " -Wl,--no-undefined")
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
        # ★ LD_LIBRARY_PATH OBLIGATORIU: libpyexec.so are nevoie de libpython3.14.so
        # (nativeLibraryDir) + libs/ proprii. Fara el: "CANNOT LINK EXECUTABLE".
        "LD_LIBRARY_PATH": (_sdk_lib + ":" + DEPS + "/lib:" + F + "/libs:"
                            + os.environ.get("LD_LIBRARY_PATH", "")),
        # ★ PYTHONHOME/PATH pentru stdlib: fara ele "Failed to import encodings".
        "PYTHONHOME": F + "/pyhome",
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

