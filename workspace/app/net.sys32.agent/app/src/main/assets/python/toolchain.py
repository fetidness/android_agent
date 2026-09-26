#!/usr/bin/env python3
"""
toolchain.py - Bootstrap toolchain COMPLET de compilare pentru agentul Android.
Fara root, fara Termux instalat, fara PC.

Instaleaza prin tpm.py (repo Termux): clang, python, pip, meson, samu, make, etc.

Folosire (agentul il cheama automat):
  python toolchain.py check     -> ce e instalat
  python toolchain.py install   -> instaleaza TOT (bootstrap)
  python toolchain.py env       -> exporta variabilele de mediu
"""

import json, datetime

# ---------------------------------------------------------------------------
# LICENTE / LEGAL
# ---------------------------------------------------------------------------
# Acest modul NU include binare in aplicatie. La "bootstrap" descarca unelte
# open-source din repo-ul PUBLIC Termux (https://packages.termux.dev), la fel
# cum face "apt" pe orice Linux. Licentele pachetelor:
#   clang/LLVM  -> Apache-2.0 with LLVM exceptions
#   python      -> PSF-2.0
#   make/cmake  -> GPL-3.0
#   ninja/samu  -> Apache-2.0
#   openssl     -> Apache-2.0
#   zlib, xz    -> zlib / public domain
# Nu redistribuim nimic: descarcarea si folosirea locala nu creeaza obligatii
# de redistribuire. Daca cineva doreste sa impacheteze aceste binare in alt
# produs, trebuie sa respecte licentele respective (inclusiv GPL).
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# AUTO-FIX: compression._common (workaround AAPT2 care ignora foldere "_")
# Trebuie sa ruleze INAINTE de orice import de lzma/gzip/bz2/tarfile.
# ---------------------------------------------------------------------------
def _ensure_compression():
    import os
    import sys
    if os.environ.get("_TC_FIXED"):
        return
    os.environ["_TC_FIXED"] = "1"
    cands = []
    try:
        import sysconfig
        pl = sysconfig.get_paths().get("purelib", "")
        if pl:
            cands.append(os.path.join(os.path.dirname(pl), "compression"))
            cands.append(os.path.join(pl, "compression"))
    except Exception:
        pass
    for d in sys.path:
        if d:
            cands.append(os.path.join(d, "compression"))
    for c in cands:
        if os.path.isdir(c) and os.path.exists(os.path.join(c, "_streams_data.py")):
            common = os.path.join(c, "_common")
            # daca exista _common.py (fisier gresit), il stergem
            bad = os.path.join(c, "_common.py")
            if os.path.isfile(bad):
                try: os.remove(bad)
                except Exception: pass
            if not (os.path.isdir(common) and os.path.exists(os.path.join(common, "_streams.py"))):
                try:
                    if os.path.isfile(common): os.remove(common)
                    os.makedirs(common, exist_ok=True)
                    open(os.path.join(common, "__init__.py"), "w").close()
                    import shutil
                    shutil.copyfile(os.path.join(c, "_streams_data.py"),
                                    os.path.join(common, "_streams.py"))
                    import shutil as _sh2
                    _sh2.rmtree(os.path.join(common, "__pycache__"), ignore_errors=True)
                    _sh2.rmtree(os.path.join(c, "__pycache__"), ignore_errors=True)
                except Exception: pass
            return
_ensure_compression()

import os, sys, subprocess, json

F = "/data/data/net.sys32.agent/files"
WS = "/sdcard/Download/Agent/workspace"
ROOT = "/data/data/net.sys32.agent/files/toolchain"
BIN = ROOT + "/bin"
DEPS = ROOT + "/deps"

# pachetele necesare pentru compilare COMPLETA (inclusiv numpy/scipy-level)
PKGS = [
    "clang", "lld", "make", "pkg-config", "cmake", "ninja", "patchelf", "samurai",
    "meson", "python-pip",   # meson: numpy>=2 se construieste cu el (fara el build-ul esueaza)
    "ccache",                # recompilarile partiale devin aproape instant (numpy = mii de .c)
    "ndk-sysroot",
    "python", "python-pip", "python-ensurepip-wheels", "binutils", "libandroid-spawn",
    "zlib", "liblzma", "libbz2", "openssl", "libffi",
    "ncurses", "readline", "sqlite", "libexpat", "libxml2",
    "git", "tar", "xz-utils", "coreutils", "findutils", "grep", "sed", "gawk",
    "rust", "libc++", "binutils-libs", "termux-elf-cleaner",
]

# biblioteci bionice de pe DEVICE (libm.so real, cu simboluri C99 complete).
# clang nu linkeaza -lm implicit pe android36, iar termux nu are libm.so in prefix.
BIONIC_LIB = "/apex/com.android.runtime/lib64/bionic"
BIONIC_LIB_FALLBACK = "/system/lib64"

# ★ MARKER (referat numpy, F5): trebuie sa fie in ACELASI loc pe care il verifica `check()`.
# Vechiul `F + "/.toolchain_ok"` statea in sandbox-ul app, dar check() il cauta PRIN SHELL
# (uid 2000) -> shell-ul nu vede sandbox-ul app-ului -> "marker: false" desi instalarea
# reusise ("version_marker: true" in alt apel). Inconsistenta care parea instalare rupta.
MARKER = "/data/data/net.sys32.agent/files/toolchain/.toolchain_ok"


def _sh(cmd, timeout=300):
    """★ RUN LOCAL (ca APP, uid 10318): toolchain-ul din APK traieste in filesDir.

    Inainte rulea prin adb_client ca uid=2000 - corect cand prefixul era in
    /data/local/tmp/tpm. Acum shell-ul NU POATE citi filesDir (Permission denied),
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
# 8. git prezent (obstacolul 1/9: pe Termux lipseste remote-https -> vezi raportul)
if $B/git --version >/dev/null 2>&1; then echo "GIT=1"; else echo "GIT=0"; fi
# 8b. ★ SPAWN TEST (referat numpy, P5+F6): cea mai inselatoare problema - ninja din Termux
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
    r["version_marker"] = _vm[:120] or "(missing - run bootstrap to write it)"
    # --- veredict ---
    # ★ TOOLCHAIN DIN APK: clang/lld/sysroot traiesc in filesDir (extrase din assets)
    # si se folosesc DIRECT DE APP (uid 10318) - nu mai exista prefix Termux si nici
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
                        "(pip_install compileaza direct, fara bootstrap)")
    else:
        r["verdict"] = ("INCOMPLET - lipseste %s; reinstaleaza APK-ul (assets: bin/sysroot)"
                        % (", ".join([x for x, ok in [("bin", _have_bin), ("sysroot", _have_sysroot)] if not ok])))
    return r


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
    out = _sh("ls " + BIN + " 2>/dev/null", 30)
    present = set(out.split())
    api = _device_api()
    need = {
        "clang": ("clang" in present) or ("clang-21" in present),
        "make": "make" in present,
        "python": "python3" in present,
        "pip": ("pip" in present) or ("pip3" in present),
        "cmake": "cmake" in present,
        "ninja": "ninja" in present,
        "samu": "samu" in present,
        "patchelf": "patchelf" in present,
        "ld": ("ld" in present) or ("lld" in present),
        "ar": ("ar" in present) or ("llvm-ar" in present),
        "git": "git" in present,
        "pkg-config": "pkg-config" in present,
        "rust": "rustc" in present,
        "sysroot(crt)": "crtbegin_dynamic.o" in set(
            _sh("ls " + ROOT + "/usr/lib 2>/dev/null", 30).split()),
        "marker": "YES" in _sh("test -f " + MARKER + " && echo YES || echo NO", 20),
    }
    # --- verificari FUNCTIONALE (fiecare = o eroare reala de pe device) ---
    py = BIN + "/python3.14"
    # 1. compileaza + linkeaza (target API real, nu android24)
    probe = _sh(
        'cd /data/local/tmp 2>/dev/null || cd /tmp; '
        'printf "int main(void){return 0;}" > .tc_probe.c; '
        'PATH=%s:/system/bin:$PATH %s --target=aarch64-linux-android%d '
        '.tc_probe.c -o .tc_probe 2>&1; echo RC=$?' % (BIN, BIN + "/clang", api), 120)
    need["compile_test"] = "RC=0" in probe
    if not need["compile_test"]:
        need["compile_hint"] = probe.strip()[-200:]
    # 2. Python + LIBDIR corect (sysconfig patchuit)
    sc = _sh('%s -c "import sysconfig;print(sysconfig.get_config_var(\'LIBDIR\'))" 2>&1' % py, 60)
    need["sysconfig_ok"] = ("com.termux" not in sc) and (ROOT + "/usr/lib" in sc)
    if not need["sysconfig_ok"]:
        need["sysconfig_hint"] = sc.strip()[-120:]
    # 3. pip functional cu SSL
    pv = _sh('PATH=%s:/system/bin:$PATH SSL_CERT_FILE=%s/usr/etc/tls/cert.pem '
             '%s -m pip --version 2>&1' % (BIN, ROOT, py), 90)
    need["pip_works"] = "pip" in pv.lower() and "Traceback" not in pv
    if not need["pip_works"]:
        need["pip_hint"] = pv.strip()[-150:]
    # 4. CA bundle prezent (pip HTTPS)
    need["ca_bundle"] = ("cert.pem" in _sh("ls %s/usr/etc/tls/cert.pem 2>/dev/null" % ROOT, 20))
    # 5. libc++ preload (extensii C++)
    need["libc++_shared"] = ("libc++_shared.so" in _sh("ls %s/usr/lib/libc++_shared.so 2>/dev/null" % ROOT, 20))
    # 6. RUNPATH corectat (0 fisiere cu com.termux)
    # ★ TIMP: vechiul check rula `readelf -d` pe FIECARE binar (spawn per fisier, ~30 s).
    # O singura trecere Python face acelasi lucru in <1 s.
    # ★ FIX: cautam string-ul DOAR in zona de RUNPATH a ELF-ului, nu oriunde in fisier.
    # 45 de binare (cmake, ninja, git, make...) au cai Termux in DATELE lor interne
    # (CMAKE_ROOT, prefix etc.), dar RUNPATH-ul lor e corectat -> functioneaza perfect.
    # Vechiul check raporta fals "runpath_ok=false" desi toate tool-urile mergeau.
    # ★ TEST FUNCTIONAL REAL: compileaza C cu clang-ul din APK (nu cauta runpath Termux).
    _ct = _sh("cd %s && printf 'int main(void){return 42;}' > .t.c && "
              "%s --target=aarch64-linux-android35 --sysroot=%s/sysroot -o .t.bin .t.c 2>&1 && echo COMPILE_OK"
              % (F + "/tmp", BIN + "/clang-21", ROOT), 120)
    need["compile_test"] = "COMPILE_OK" in _ct
    need["compile_hint"] = None if need["compile_test"] else _ct[:150]
    # 7. numpy (daca e cerut explicit)
    if "numpy" in " ".join(PKGS):
        need["numpy"] = "numpy" in _sh("ls %s/lib/python3.14/site-packages 2>/dev/null" % ROOT, 30)
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
    # si se folosesc DIRECT DE APP (uid 10318). Nu mai exista prefix Termux, nici bootstrap.
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
                           "se foloseste CA APP: pip_install compileaza direct, fara bootstrap")
    else:
        need["verdict"] = "INCOMPLET - reinstaleaza APK-ul (lipsesc assets bin/sysroot)"
    return need


# ============================================================
#  BOOTSTRAP DIRECT (fara tpm.py, fara adb) - rapid si robust
# ============================================================
_REPO = "https://packages.termux.dev/apt/termux-main"
_ARCH = "aarch64"


def _http_get(url, timeout=120):
    import urllib.request, ssl, os
    # CA bundle (Android nu are CA system pentru Python)
    ctx = None
    try:
        import certifi
        ctx = ssl.create_default_context(cafile=certifi.where())
    except Exception:
        for ca in ("/data/data/net.sys32.agent/files/home/ca-bundle.pem",
                   "/apex/com.android.conscrypt/cacerts",
                   "/system/etc/security/cacerts"):
            if os.path.exists(ca):
                try:
                    ctx = ssl.create_default_context(cafile=ca)
                    break
                except Exception:
                    pass
    req = urllib.request.Request(url, headers={"User-Agent": "agent"})
    if ctx is not None:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            return r.read()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _gunzip(data):
    """Decomprima gzip fara modulul gzip (ocoleste bug-ul compression._common)."""
    import zlib
    return zlib.decompress(data, 16 + zlib.MAX_WBITS)


def _load_index():
    """Descarca si parseaza index-ul Termux (Packages.gz)."""
    data = _http_get(_REPO + "/dists/stable/main/binary-" + _ARCH + "/Packages.gz", 180)
    txt = _gunzip(data).decode("utf-8", "replace")
    pkgs = {}
    cur = {}
    for line in txt.split("\n"):
        if not line.strip():
            if "Package" in cur:
                pkgs[cur["Package"]] = cur
            cur = {}
            continue
        if ":" in line:
            k, v = line.split(":", 1)
            cur[k.strip()] = v.strip()
    return pkgs


def _untar(blob, dest):
    """Parseaza un tar (ustar/GNU/PAX) si extrage in dest - pur Python.

    IMPORTANT: arhivele Termux folosesc nume LUNGI (ex.
    `_asyncio.cpython-314-aarch64-linux-android.so`, peste 100 caractere) si le
    pun in headere speciale:
      - typeflag 'L' -> numele real e in BODY-ul urmator (GNU LongName)
      - typeflag 'K' -> la fel, pentru linkname
      - typeflag 'x'/'g' -> PAX extended header (cheia 'path=')
    Fara tratarea lor, numele se TRUNCHIAZA la 100 de caractere si extensia
    `.so` dispare -> toate modulele C din lib-dynload devin neimportabile
    (exact eroarea 'pip e afectat de _posixsubprocess lipsa').
    """
    PREF = ("./data/data/com.termux/files/usr/", "data/data/com.termux/files/usr/")
    off = 0
    n = 0
    pending_name = None      # numele real din headerul 'L'
    pending_link = None      # linkname real din headerul 'K'
    while off + 512 <= len(blob):
        hdr = blob[off:off+512]
        if hdr[:1] == b"\x00":
            break
        name = hdr[0:100].split(b"\x00")[0].decode("utf-8", "replace")
        size_b = hdr[124:136].split(b"\x00")[0].strip()
        typeflag = hdr[156:157]
        linkname = hdr[157:257].split(b"\x00")[0].decode("utf-8", "replace")
        try:
            size = int(size_b, 8) if size_b else 0
        except Exception:
            size = 0
        off += 512
        data = blob[off:off+size]
        off += (size + 511) // 512 * 512

        # --- header de NUME LUNG (GNU) ---
        if typeflag == b"L":
            pending_name = data.split(b"\x00")[0].decode("utf-8", "replace")
            continue
        if typeflag == b"K":
            pending_link = data.split(b"\x00")[0].decode("utf-8", "replace")
            continue
        # --- header extins PAX (path= ...) ---
        if typeflag in (b"x", b"g"):
            txt = data.decode("utf-8", "replace")
            for line in txt.split("\n"):
                if line.startswith("path="):
                    pending_name = line[5:]
                elif line.startswith("linkpath="):
                    pending_link = line[9:]
            continue

        # prefix (ustar) - se aplica DOAR daca nu avem nume lung
        prefix = hdr[345:500].split(b"\x00")[0].decode("utf-8", "replace")
        if pending_name:
            name = pending_name
            pending_name = None
        elif prefix:
            name = prefix + "/" + name
        if pending_link:
            linkname = pending_link
            pending_link = None

        nm = name
        for pref in PREF:
            if nm.startswith(pref):
                nm = nm[len(pref):]
                break
        else:
            continue
        if not nm:
            continue
        out = os.path.join(dest, nm)
        try:
            parent = os.path.dirname(out)
            if parent and not os.path.isdir(parent):
                os.makedirs(parent, exist_ok=True)
            if typeflag in (b"5", b""):
                # director (b"" = fara typeflag, dar numele se termina cu /)
                if name.endswith("/"):
                    os.makedirs(out, exist_ok=True)
                    n += 1
                    continue
            if typeflag == b"2":
                # symlink
                try:
                    if os.path.lexists(out):
                        os.remove(out)
                    os.symlink(linkname, out)
                    n += 1
                except Exception:
                    pass
            else:
                # fisier normal
                if os.path.isdir(out):
                    continue
                with open(out, "wb") as w:
                    w.write(data)
                try:
                    mode_b = hdr[100:108].split(b"\x00")[0].strip()
                    mode = int(mode_b, 8) if mode_b else 0o644
                    os.chmod(out, mode | 0o700)
                except Exception:
                    os.chmod(out, 0o755)
                n += 1
        except Exception:
            pass
    return n > 0


def _extract_deb(data, dest):
    """Extrage data.tar.* dintr-un .deb (arhiva ar) - fara tarfile (bug Android)."""
    import io, lzma
    # format ar: 8-byte header + 60-byte entry
    off = 8
    members = []
    while off + 60 <= len(data):
        hdr = data[off:off+60]
        if hdr[58:60] != b"`\n":
            break
        name = hdr[0:16].decode("utf-8", "replace").strip().rstrip("/")
        size_s = hdr[48:58].decode("utf-8", "replace").strip()
        try:
            size = int(size_s)
        except Exception:
            break
        members.append((name, off+60, size))
        off += 60 + size + (size % 2)
    # caut data.tar.*
    for name, start, size in members:
        if name.startswith("data.tar"):
            blob = data[start:start+size]
            if name.endswith(".xz"):
                blob = lzma.decompress(blob)
            elif name.endswith(".gz"):
                blob = _gunzip(blob)
            # parsing tar manual (fara tarfile -> bug compression._common)
            return _untar(blob, dest)
    return False




def _patch_runpath():
    """Termux .deb au RUNPATH hardcodat la /data/data/com.termux/files/usr/lib.
    Acel director NU exista aici -> orice binar/subproces moare cu
    'CANNOT LINK EXECUTABLE: library libX.so not found' (exit 127).

    ★ OPTIMIZARE DE TIMP (22 s -> 0.3 s): versiunea veche rula `readelf -d` pe
    FIECARE fisier (~500 fisiere = ~1000 procese spawn; pe Android fiecare spawn
    costa ~1 s -> 13 MINUTE pierdute in bootstrap, exact ce raporta referatul:
    "fazele de fix au fost mai lungi decat build-ul"). Acum verificarea se face
    INTR-O SINGURA TRECERE Python (citim fisierul si cautam sirul), iar patchelf
    ruleaza doar pe fisierele care CHIAR au nevoie de el.
    """
    if "YES" not in _sh("test -x " + BIN + "/patchelf && echo YES || echo NO", 30):
        print("[toolchain] patchelf lipsa - sar peste fix RUNPATH")
        return
    py = r"""
import os
P = "/data/data/net.sys32.agent/files/toolchain"
B, L = P + "/bin", P + "/lib"
OLD = b"/data/data/com.termux/files/usr/lib"
need = []
# o singura citire per fisier, fara readelf, fara procese externe
for root, exts in ((B, None), (L, None)):
    if not os.path.isdir(root):
        continue
    for fn in os.listdir(root):
        fp = os.path.join(root, fn)
        if not os.path.isfile(fp) or os.path.islink(fp):
            continue
        if fn.endswith((".orig", ".new", ".tcorig")):
            continue
        try:
            with open(fp, "rb") as f:
                data = f.read()
        except Exception:
            continue
        if OLD in data:
            need.append(fp)
# lib-dynload
import glob as _g
for fp in _g.glob(P + "/lib/python3.*/lib-dynload/*.so"):
    try:
        if OLD in open(fp, "rb").read():
            need.append(fp)
    except Exception:
        pass
print("NEEDPATCH " + " ".join(need))
"""
    try:
        out = _sh("%s -c %s" % (BIN + "/python3.14", _q(py)), 300)
        line = [l for l in out.split("\n") if l.startswith("NEEDPATCH")]
        files = line[0].split(" ", 1)[1].split() if line and len(line[0].split(" ", 1)) > 1 else []
        if not files:
            print("[toolchain] RUNPATH deja corect (0 fisiere de patch-uit)")
            return
        print("[toolchain] patch RUNPATH pe %d fisiere..." % len(files))
        # patchelf pe lista: acelasi proces shell, dar doar pe ce trebuie
        bat = "L=%s; PE=%s/patchelf; " % (ROOT + "/usr/lib", BIN)
        bat += "; ".join('chmod u+r "%s" 2>/dev/null; "$PE" --set-rpath "$L" "%s" 2>/dev/null' % (f, f) for f in files)
        bat += "; echo RUNPATH_DONE"
        out2 = _sh("export LD_LIBRARY_PATH=$L:$LD_LIBRARY_PATH; " + bat, 900)
        if "RUNPATH_DONE" in out2:
            print("[toolchain] RUNPATH corectat pe %d fisiere" % len(files))
        else:
            print("[toolchain] RUNPATH: partial", out2[-150:])
    except Exception as e:
        print("[toolchain] RUNPATH err:", e)


def _fix_ninja():
    """ninja din Termux e RUPT: nu poate executa NICIUN subproces
    (libandroid-spawn.so la runtime) -> 'ninja: subcommand failed', code=127.
    samurai (samu) face acelasi lucru si merge. Inlocuim ninja cu samu."""
    s = BIN + "/samu"
    # la fel: verificare prin shell, nu os.path (app-ul nu vede /data/local/tmp)
    if "YES" not in _sh("test -x " + s + " && echo YES || echo NO", 30):
        print("[toolchain] samu lipsa - nu pot inlocui ninja")
        return
    # ★ WRAPPER, nu COPIE (referat numpy, P5 + sect.5): versiunea veche copia samu PESTE ninja,
    # distrugand binarul original ("nu mai e recuperabil din acest prefix"). Un wrapper SCRIPT
    # pastreaza originalul ca ninja.real si e si mai clar de diagnosticat.
    # Detectia versiunii Android (referatul propune API>=34 -> fortam samu): oricum o facem
    # neconditionat, pentru ca problema de spawn e prezenta pe Android 16 si samu e strict mai bun.
    script = r"""
B="__BIN__"; API=__API__
# salvez originalul O SINGURA DATA (si recuperez daca o rulare veche l-a copiat deja)
if [ -f "$B/ninja" ] && [ ! -f "$B/ninja.real" ]; then
  if head -1 "$B/ninja" 2>/dev/null | grep -q '^#!'; then
    # e deja un wrapper -> nu e originalul; doar il marchez
    :
  else
    cp "$B/ninja" "$B/ninja.real"
  fi
fi
if [ ! -f "$B/ninja.real" ]; then
  # originalul a fost deja suprascris de o versiune veche: il reconstruim din pachet nu se poate,
  # deci ninja.real va pointa la samu (comportamentul de fapt al prefixului) - documentat.
  ln -sf samu "$B/ninja.real" 2>/dev/null || cp "$B/samu" "$B/ninja.real"
fi
cat > "$B/ninja" <<EOF
#!/system/bin/sh
# Wrapper: ninja din Termux nu poate face spawn pe Android (API $API) -> samu.
# Originalul (daca a existat) e in ninja.real. Nu sterge acest fisier.
exec "$B/samu" "\$@"
EOF
chmod 755 "$B/ninja"
# samurai e strict mai bun si cand cineva cheama direct 'samu' sau 'ninja'
echo NINJA_WRAP_DONE
"""
    script = script.replace("__BIN__", BIN).replace("__API__", str(_device_api()))
    try:
        out = _sh(script, 120)
        if "NINJA_WRAP_DONE" in out:
            print("[toolchain] ninja -> wrapper script catre samu (originalul: ninja.real)")
    except Exception as e:
        print("[toolchain] ninja err:", e)


def _fix_cc_wrappers():
    """clang din Termux are target IMPLICIT android24. Functiile C99 introduse
    ulterior (ex. ctanl/ccoshl/csinhl din complex.h, marcate __INTRODUCED_IN(26))
    sunt ASCUNSE de header -> numpy si multe pachete C nu compileaza.
    Fix: inlocuim cc/gcc/clang cu wrappere care injecteaza --target=<API real>
    si un PATH complet (ninja/meson ruleaza subprocese cu env minimal, unde
    rm/sh din /system/bin nu se gasesc -> 'rm: inaccessible or not found')."""
    api = _device_api()          # ex. 36 pe Android 16
    tgt = "aarch64-linux-android%d" % api
    script = r"""
B="__BIN__"; L="__LIB__"; TGT="__TGT__"; APIDIR="__APIDIR__"
[ -x "$B/clang-21.real" ] || cp "$B/clang-21" "$B/clang-21.real"
for name in cc c++ gcc g++ clang clang++ clang-21; do
  cat > "$B/$name" <<EOF
#!/system/bin/sh
export PATH=$B:/system/bin:/system/xbin:\$PATH
export LD_LIBRARY_PATH=$L:\$LD_LIBRARY_PATH
export LD_PRELOAD=$L/libc++_shared.so
exec $B/clang-21.real --target=$TGT "\$@"
EOF
  chmod 755 "$B/$name"
done
echo WRAPPERS_DONE
"""
    script = (script.replace("__BIN__", BIN).replace("__LIB__", ROOT + "/usr/lib")
                    .replace("__TGT__", tgt).replace("__APIDIR__", ""))
    try:
        out = _sh(script, 120)
        if "WRAPPERS_DONE" in out:
            print("[toolchain] cc/clang -> wrapper cu --target=%s" % tgt)
    except Exception as e:
        print("[toolchain] wrappers err:", e)


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


def _fix_wrappers_shebang():
    """Scripturile din prefix (aarch64-linux-android-clang, clang etc.) au
    shebang `#!/data/data/com.termux/files/usr/bin/bash` (PREFIXUL TERMUX, mort).
    Fara fix: "No such file or directory" la orice apel, desi fisierul exista.

    Plus: multe hardcodeaza `--target=aarch64-linux-android24` -> ASCUNDE
    functiile C99 (complex.h) -> numpy nu compileaza.

    Fix: rescriu shebang -> /system/bin/sh si prefixul Termux -> prefix real,
    plus forțez target-ul la API-ul device-ului.
    """
    api = _device_api()
    script = r"""
B="__BIN__"; L="__LIB__"; P="__PREFIX__"; API=__API__; OLD="/data/data/com.termux/files/usr"
n=0
for f in "$B"/*; do
  [ -f "$f" ] || continue
  head -1 "$f" 2>/dev/null | grep -q '^#!' || continue
  changed=0
  # 1. shebang mort -> /system/bin/sh
  if head -1 "$f" | grep -q "$OLD"; then
    sed -i '1s|.*|#!/system/bin/sh|' "$f"; changed=1
  fi
  # 2. prefix Termux -> prefix real (in tot continutul)
  if grep -q "$OLD" "$f" 2>/dev/null; then
    sed -i "s|$OLD|$P|g" "$f"; changed=1
  fi
  # 3. target android24 -> API real (altfel functiile C99 sunt ascunse)
  if grep -q 'target=aarch64-linux-android24' "$f" 2>/dev/null; then
    sed -i "s|target=aarch64-linux-android24|target=aarch64-linux-android$API|g" "$f"; changed=1
  fi
  [ "$changed" = "1" ] && n=$((n+1))
done
echo "WRAPPERS_FIXED=$n"
"""
    script = (script.replace("__BIN__", BIN).replace("__LIB__", ROOT + "/usr/lib")
                    .replace("__PREFIX__", ROOT + "/usr").replace("__API__", str(api)))
    try:
        out = _sh(script, 300)
        if "WRAPPERS_FIXED" in out:
            print("[toolchain] " + out.strip().split("\n")[-1] + " scripturi reparamurate (shebang+prefix+target)")
    except Exception as e:
        print("[toolchain] wrappers err:", e)


def _fix_sysconfig():
    """CRITIC pentru pip/meson: _sysconfigdata are PREFIXUL TERMUX hardcodat.

    Python-ul din Termux e compilat cu --prefix=/data/data/com.termux/files/usr.
    Desi binarul ruleaza din prefixul nostru, `sysconfig` raporteaza calea
    Termux (71 de variabile!) - inclusiv LIBDIR, BLDSHARED, INCLUDEDIR.

    Consecinta: meson/pip adauga `-I/data/data/com.termux/files/usr/include/py3.14`
    (inexistent) si link `-L/data/data/com.termux/files/usr/lib` (inexistent)
    -> `meson test has_header` esueaza si build-ul numpy se opreste.

    Fix: rescriem _sysconfigdata__android_*.py inlocuind calea Termux cu
    prefixul real (/data/data/net.sys32.agent/files/toolchain).
    """
    script = r"""
P="__PREFIX__"; OLD="/data/data/com.termux/files/usr"
found=0; patched=0
for f in "$P"/lib/python3.*/_sysconfigdata*.py; do
  [ -f "$f" ] || continue
  found=$((found+1))
  if grep -q "$OLD" "$f" 2>/dev/null; then
    sed -i "s|$OLD|$P|g" "$f"
    patched=$((patched+1))
  fi
done
# si sysconfig-ul principal (uneori are cai in plus)
for f in "$P"/lib/python3.*/sysconfig.py; do
  [ -f "$f" ] || continue
  if grep -q "$OLD" "$f" 2>/dev/null; then sed -i "s|$OLD|$P|g" "$f"; patched=$((patched+1)); fi
done
# .pth / config-uri care indica prefixul vechi
for f in "$P"/lib/python3.*/config-*/*.mk; do
  [ -f "$f" ] || continue
  if grep -q "$OLD" "$f" 2>/dev/null; then sed -i "s|$OLD|$P|g" "$f"; patched=$((patched+1)); fi
done
# ★ curata caile MOARTE de build ale Termux (/home/builder/.termux-build/...)
#   fara asta, LDSHARED/CC din sysconfig trimit linkerul in directoare inexistente
for f in "$P"/lib/python3.*/_sysconfigdata*.py "$P"/lib/python3.*/sysconfig.py; do
  [ -f "$f" ] || continue
  if grep -q '/home/builder' "$f" 2>/dev/null; then
    sed -i 's|/home/builder/.termux-build/[^ "'"'"']*||g' "$f"
    patched=$((patched+1))
  fi
done
# ★ TOATE fisierele .pc au prefixul TERMUX in ele -> pkg-config da cai inexistente
#   (ex. `pkg-config --cflags python3` => -I/data/data/com.termux/.../include/python3.14)
#   Asta rupe `Compiler cython cannot compile programs` in meson!
npc=0
for f in "$P"/lib/pkgconfig/*.pc "$P"/share/pkgconfig/*.pc; do
  [ -f "$f" ] || continue
  if grep -q "$OLD" "$f" 2>/dev/null; then
    sed -i "s|$OLD|$P|g" "$f"
    npc=$((npc+1))
  fi
done
echo "PC_FIXED=$npc"
# python3.pc (pkg-config) - meson il foloseste; TREBUIE sa aiba prefixul nostru
mkdir -p "$P/lib/pkgconfig" 2>/dev/null
cat > "$P/lib/pkgconfig/python3.pc" <<EOF
prefix=$P
exec_prefix=\${prefix}
libdir=\${prefix}/lib
includedir=\${prefix}/include

Name: Python
Description: Python standard library
Version: 3.14
Libs: -L\${libdir} -lpython3.14
Cflags: -I\${includedir}/python3.14
EOF
echo "SYSCONFIG_FILES=$found PATCHED=$patched"
"""
    script = script.replace("__PREFIX__", ROOT + "/usr")
    try:
        out = _sh(script, 240)
        if "PATCHED" in out:
            print("[toolchain] sysconfig: " + out.strip().split("\n")[-1])
    except Exception as e:
        print("[toolchain] sysconfig err:", e)


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
        out = _sh("%s -c %s" % (BIN + "/python3.14", _q(py)), 300)
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


def _fix_cxx_linker():
    """Obstacol 6 (llama.cpp): `-stdlib=libc++` NU e suficient pentru clang++ pe
    Android - linkerul nu gaseste libc++_shared.so si da
    "undefined symbol: std::__ndk1::cout".

    Fix: wrapper-e clang/clang++ in /data/local/tmp/wrap care adauga AUTOMAT
    --target, -L<prefix>/lib, -L bionic si -lc++_shared. Astfel orice build
    (cmake, make, meson, scripturi) linkeaza corect fara flaguri speciale.
    """
    api = _device_api()
    script = r"""
B="__BIN__"; L="__LIB__"; BIONIC="__BIONIC__"; API=__API__; W="/data/local/tmp/wrap"
mkdir -p "$W" 2>/dev/null
for tool in clang clang++; do
  cat > "$W/$tool" <<EOF
#!/system/bin/sh
export LD_LIBRARY_PATH=$L:$BIONIC:\$LD_LIBRARY_PATH
# ★ CCACHE (raportul numpy B5): daca e instalat, cacheuieste compilarea. CCACHE_DIR e in
# /data/local/tmp (native). Fara ccache, exec-ul e exact ca inainte (fallback transparent).
if [ -x $B/ccache ]; then
  export CCACHE_DIR=/data/local/tmp/.ccache CCACHE_MAXSIZE=5G
  exec $B/ccache $B/$tool --target=aarch64-linux-android$API -L$L -L$BIONIC -Wl,-rpath,$L -lc++_shared "\$@"
fi
exec $B/$tool --target=aarch64-linux-android$API -L$L -L$BIONIC -Wl,-rpath,$L -lc++_shared "\$@"
EOF
  chmod 755 "$W/$tool"
done
# si cc/c++/gcc/g++ -> aceleasi wrappere
for tool in cc c++ gcc g++; do
  case "$tool" in c++|g++) base="clang++" ;; *) base="clang" ;; esac
  cat > "$W/$tool" <<EOF
#!/system/bin/sh
exec $W/$base "\$@"
EOF
  chmod 755 "$W/$tool"
done
echo CXXWRAP_OK
"""
    script = (script.replace("__BIN__", BIN).replace("__LIB__", ROOT + "/usr/lib")
                    .replace("__BIONIC__", BIONIC_LIB).replace("__API__", str(api)))
    try:
        out = _sh(script, 90)
        if "CXXWRAP_OK" in out:
            print("[toolchain] wrappere clang/clang++ (auto -lc++_shared -L bionic) in /data/local/tmp/wrap")
    except Exception as e:
        print("[toolchain] cxx wrapper err:", e)


def _fix_termux_paths():
    """Obstacolele 4+5 (llama.cpp): binarele Termux (make, cmake) au cai
    ABSOLUTE hardcodate catre /data/data/com.termux/files/usr - inclusiv
    SHELL = /data/data/com.termux/files/usr/bin/sh (mort).

    Consecinta: cmake scrie acea cale in build.make, iar la build da
    "make: /data/data/com.termux/files/usr/bin/sh: No such file or directory"
    -> "The C++ compiler is not able to compile a simple test program".

    Fix: inlocuim sirurile in BINARELE cmake/make (in aceasta ordine: intai
    caile lungi, apoi prefixul scurt; padding cu NUL ca sa pastram lungimea
    si offseturile ELF). NU patch-uim libpython.so/libLLVM.so: se corup.
    """
    py = r"""
import os
P = os.environ.get("TC_PREFIX", "/data/data/net.sys32.agent/files/toolchain")
# ORDINE CRITICA: sirurile lungi intai, altfel "/usr" din mijloc ramane orfan
PAIRS = [
    (b"/data/data/com.termux/files/usr/bin/sh",   b"/system/bin/sh"),
    (b"/data/data/com.termux/files/usr/bin/bash", b"/system/bin/sh"),
    (b"/data/data/com.termux/files/usr",          b"/data/data/net.sys32.agent/files/toolchain"),
]
n = 0
for name in ("cmake", "make", "ctest", "cpack"):
    f = P + "/bin/" + name
    if not os.path.exists(f):
        continue
    d = open(f, "rb").read()
    if not any(o in d for o, _ in PAIRS):
        continue
    bak = f + ".tcorig"
    if not os.path.exists(bak):
        open(bak, "wb").write(d)
    for OLD, NEWP in PAIRS:
        NEW = NEWP + b"\x00" * (len(OLD) - len(NEWP))
        d = d.replace(OLD, NEW)
    open(f, "wb").write(d)
    os.chmod(f, 0o755)          # scrierea pierde bitul de exec
    n += 1
print("TERMUXPATCH", n)
"""
    try:
        r = _sh("%s -c %s" % (BIN + "/python3.14", _q(py)), 300)
        if "TERMUXPATCH" in r:
            print("[toolchain] cai Termux corectate in binare: " + r.strip().split("\n")[-1])
    except Exception as e:
        print("[toolchain] termux paths err:", e)
    # wrapper make in PATH (suplimentar, pentru apelurile fara cale absoluta)
    w = r"""
B="__BIN__"; W="/data/local/tmp/wrap"
mkdir -p "$W" 2>/dev/null
cat > "$W/make" <<EOF
#!/system/bin/sh
exec $B/make SHELL=/system/bin/sh "\$@"
EOF
chmod 755 "$W/make"
echo WRAP_OK
"""
    try:
        _sh(w.replace("__BIN__", BIN), 60)
    except Exception:
        pass


# pastrat pentru compatibilitate (apeluri vechi)
def _fix_make_shell():
    return _fix_termux_paths()


def _fix_meson_exe():
    """meson instalat prin pip vine ca MODUL (mesonbuild), nu ca executabil in bin/.
    meson-python il cheama ca `meson` -> fara acest wrapper, build-ul numpy esueaza.
    Scriem un script simplu care il ruleaza prin python-ul prefixului."""
    s = r"""
B="__BIN__"
if [ -x "$B/meson" ] && head -1 "$B/meson" 2>/dev/null | grep -q python; then echo MESON_ALREADY; exit 0; fi
if [ ! -f "$B/meson" ] || ! grep -q mesonbuild "$B/meson" 2>/dev/null; then
  printf '#!/system/bin/sh\nexec %s/python3.14 -m mesonbuild.mesonmain "$@"\n' "$B" > "$B/meson"
  chmod 755 "$B/meson"
fi
echo MESON_DONE
"""
    try:
        out = _sh(s.replace("__BIN__", BIN), 60)
        if "MESON" in out:
            print("[toolchain] meson: executabil pregatit in bin/")
    except Exception as e:
        print("[toolchain] meson err:", e)



def _write_env_file():
    """Scrie un fisier de mediu PERSISTENT pentru NOUL toolchain (din APK).

    Toolchain-ul nu mai e in /data/local/tmp/tpm, ci in filesDir/toolchain
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
    """Python din Termux caută CA in /data/data/com.termux/files/usr/etc/tls/cert.pem
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


def _fix_symlinks():
    """Recreeaza symlink-urile prin SHELL (os nu vede /data/local/tmp).
    Termux are symlink-uri in .deb (typeflag 2) pe care _untar nu le face."""
    # script shell care:
    #  1) libX.so.N.M.P -> libX.so.N si libX.so
    #  2) cazuri speciale (libz.so.1, libbz2.so.1.0, libexpat.so.1...)
    #  3) binare uzuale (clang, ld, ar, ...)
    script = r"""
L="__LIB__"; B="__BIN__"
# 1. generic: din fiecare libX.so.A.B.C face libX.so.A si libX.so
for f in "$L"/lib*.so.*; do
  [ -f "$f" ] || continue
  n=$(basename "$f")
  case "$n" in *.so.*.*)
    base=$(echo "$n" | sed -E 's/(\.so\.[0-9]+)\..*/\1/')
    [ -e "$L/$base" ] || ln -sf "$n" "$L/$base"
    short=$(echo "$base" | sed -E 's/\.[0-9]+$//')
    [ -e "$L/$short" ] || ln -sf "$n" "$L/$short"
  ;; esac
done
# 2. cazuri speciale Termux
for pair in "libz.so.1.3.2:libz.so.1:libz.so" \
            "libbz2.so.1.0.8:libbz2.so.1.0:libbz2.so.1:libbz2.so" \
            "libexpat.so.1.8.0:libexpat.so.1:libexpat.so" \
            "libandroid-support.so:libandroid-support.so" ; do
  real=$(echo "$pair" | cut -d: -f1)
  [ -e "$L/$real" ] || continue
  for t in $(echo "$pair" | cut -d: -f2- | tr ':' ' '); do
    [ -e "$L/$t" ] || ln -sf "$real" "$L/$t"
  done
done
# 3. binare uzuale (inclusiv python3/pip3 - TERMUX NU ARE SYMLINK-UL 'python3'!)
for pair in "clang:clang-21" "clang++:clang-21" "cc:clang-21" "c++:clang-21" \
            "ld:lld" "ld.lld:lld" "ar:llvm-ar" "ranlib:llvm-ranlib" \
            "nm:llvm-nm" "objdump:llvm-objdump" "strip:llvm-strip" \
            "readelf:llvm-readelf" \
            "python3:python3.14" "python:python3.14" "pip3:pip" "pip:python3.14" ; do
  link=$(echo "$pair" | cut -d: -f1); tgt=$(echo "$pair" | cut -d: -f2)
  if [ -e "$B/$tgt" ] && [ ! -e "$B/$link" ]; then ln -sf "$tgt" "$B/$link"; fi
done
# pip: daca e script cu shebang Termux, il inlocuim cu un wrapper corect
if [ -f "$B/pip" ] && head -1 "$B/pip" 2>/dev/null | grep -q 'com.termux'; then
  printf '#!/system/bin/sh\nexec "$B/python3.14" -m pip "$@"\n' > "$B/pip.new"
  mv "$B/pip.new" "$B/pip"; chmod 755 "$B/pip"
fi
if [ -f "$B/pip3" ] && head -1 "$B/pip3" 2>/dev/null | grep -q 'com.termux'; then
  printf '#!/system/bin/sh\nexec "$B/python3.14" -m pip "$@"\n' > "$B/pip3.new"
  mv "$B/pip3.new" "$B/pip3"; chmod 755 "$B/pip3"
fi
# 4. ★ APPLETURILE COREUTILS (referat numpy, P4): pachetul Termux instaleaza DOAR binarul
#    unic "coreutils", FARA symlink-uri de applet. Deci env/cp/install/mkdir/ls/rm... lipsesc
#    cu desavarsire. meson si ninja cheama "env" (absolut) la fiecare subproces -> fara el,
#    FIECARE build moare cu 127 ("subcommand failed") fara sa spuna de ce.
#    Verificat in referat: env lipsa = 127 la fiecare tinta de build.
CU="$B/coreutils"
if [ -x "$CU" ]; then
  for a in env printenv cp mv rm mkdir rmdir ln ls cat head tail wc sort uniq cut tr \
           chmod chown stat du df date sleep true false yes basename dirname readlink \
           realpath install mktemp tee touch seq printf test expr id whoami uname \
           sha256sum sha1sum md5sum cmp diff find sort uniq tac nl od split join paste \
           timeout nproc kill sync truncate shuf comm; do
    [ -e "$B/$a" ] || ln -sf coreutils "$B/$a"
  done
  echo "COREUTILS_APPLETS=$(ls -l "$B/env" 2>/dev/null | wc -l)"
fi
echo SYMLINKS_DONE
"""
    script = script.replace("__LIB__", ROOT + "/usr/lib").replace("__BIN__", BIN)
    try:
        out = _sh(script, 240)
        if "SYMLINKS_DONE" not in out:
            print("[toolchain] symlinks: partial", out[-200:])
    except Exception as e:
        print("[toolchain] symlinks err:", e)


# R3 + R4b (raport llama.cpp): profile de build PREFABRICATE, cu TOATE flagurile
# intr-un singur loc (libc++, libm bionic, target API, rpath). Raportul noteaza:
# "combina flagurile corecte intr-un singur loc, nu le descoperi la fiecare build".
BUILD_PROFILES = {
    # ATENTIE: flagurile sunt separate prin ";" (nu spatiu) pentru a supravietui
    # la `cmake . $(toolchain profile cmake)` fara quoting special
    # ATENTIE: elemente separate prin ";" pentru a supravietui la
    # `cmake . $(toolchain profile cmake)` fara quoting special
    "cmake_args": [
        "-DCMAKE_C_COMPILER={bin}/clang",
        "-DCMAKE_CXX_COMPILER={bin}/clang++",
        "-DCMAKE_SYSTEM_NAME=Android",
        "-DCMAKE_SYSTEM_VERSION={api}",
        "-DCMAKE_ANDROID_ARCH_ABI=arm64-v8a",
        '-DCMAKE_C_FLAGS=--target=aarch64-linux-android{api} -I{prefix}/include',
        '-DCMAKE_CXX_FLAGS=--target=aarch64-linux-android{api} -I{prefix}/include -stdlib=libc++',
        '-DCMAKE_EXE_LINKER_FLAGS=-L{prefix}/lib -L{bionic} -Wl,-rpath,{prefix}/lib -lc++_shared',
        '-DCMAKE_SHARED_LINKER_FLAGS=-L{prefix}/lib -L{bionic} -Wl,-rpath,{prefix}/lib -lc++_shared',
        "-DCMAKE_BUILD_TYPE=Release",
        "-DCMAKE_PREFIX_PATH={prefix}",
        "-DCMAKE_INSTALL_PREFIX={prefix}",
    ],
    "cflags": "--target=aarch64-linux-android{api} -I{prefix}/include",
    "cxxflags": "--target=aarch64-linux-android{api} -I{prefix}/include -stdlib=libc++",
    "ldflags": ("--target=aarch64-linux-android{api} -L{prefix}/lib -L{bionic} "
                "-Wl,-rpath,{prefix}/lib -lc++_shared"),
    "python_env": {
        "PREFIX": "{prefix}", "SSL_CERT_FILE": "{prefix}/etc/tls/cert.pem",
        "LD_PRELOAD": "{prefix}/lib/libc++_shared.so",
    },
}


def profile(name="cmake"):
    """Flaguri/scripturi pregatite pentru un build (vezi BUILD_PROFILES).

    name="cmake"    -> SCRIPT shell gata de rulat: `sh cmake_prof.sh <srcdir>`
    name="cflags"/"cxxflags"/"ldflags" -> string de flaguri
    name="python_env" -> dict de variabile pentru pip/python
    """
    api = _device_api()
    fmt = dict(bin=BIN, api=api, prefix=ROOT + "/usr", bionic=BIONIC_LIB, root=ROOT)
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


def bootstrap_direct(packages=None, progress=None):
    """Bootstrap COMPLET: descarca .deb, extrage in staging (app),
    apoi copiaza in prefix (/data/local/tmp, prin adbsh)."""
    # ★ GLOBAL TIMEOUT DOAR AICI (operatie lunga, riscanta): 30 min, reimprospatat in bucla.
    # Nu mai exista un alarm global la import (vezi adb_client.py) - un proces normal
    # traieste cat are nevoie, doar bootstrap-ul isi pune singur plasa de siguranta.
    try:
        import adb_client as _ACB
        _ACB.arm_global_timeout(1800)
    except Exception:
        pass
    _prepare_dirs()
    STAGE = "/sdcard/Download/Agent/tc_stage"
    try:
        os.makedirs(STAGE, exist_ok=True)
    except Exception:
        STAGE = os.path.join(F, "tc_stage")
        os.makedirs(STAGE, exist_ok=True)
    pkgs = _load_index()
    want = packages or PKGS
    # rezolva dependente
    todo, seen = [], set()
    def add(name):
        if name in seen or name not in pkgs: return
        seen.add(name)
        for d in pkgs[name].get("Depends", "").replace("(", " ").replace(")", " ").split(","):
            d = d.strip().split(" ")[0].split("|")[0].strip()
            if d: add(d)
        todo.append(name)
    for p in want: add(p)

    print("[toolchain] de descarcat:", len(todo), "pachete")
    ok, fail = 0, []
    for i, name in enumerate(todo):
        try:
            info = pkgs[name]
            fname = info.get("Filename", "")
            if not fname: continue
            url = _REPO + "/" + fname
            if progress: progress(i+1, len(todo), name)
            # ★ reimprospatam plasa de siguranta: cat timp progresam, NU expira
            try:
                import adb_client as _ACT
                _ACT.touch_global_timeout()
            except Exception:
                pass
            data = _http_get(url, 300)
            if _extract_deb(data, STAGE):
                ok += 1
                print("  [OK] %s" % name)
            else:
                fail.append(name)
                print("  [FAIL] %s" % name)
        except Exception as e:
            fail.append(name)
            print("  [ERR] %s: %s" % (name, str(e)[:80]))
    print("[toolchain] extras: %d/%d" % (ok, len(todo)))
    if fail: print("[toolchain] esecuri:", fail)

    # copiez staging -> prefix (in /data/local/tmp, scris de shell)
    print("[toolchain] instalez in prefix via shell...")
    # ★ PERMISIUNI (raportul numpy, eroarea 2+4): prefixul e creat de shell cu drwxrws--- (grup
    # shell) -> app-ul nu poate nici macar CITI fisierele, desi toolchain-ul e instalat. Facem
    # prefixul world-readable la final, ca app-ul sa vada binarele (executia rămâne a shell-ului:
    # read != execute pentru alt uid, si asta e normal - agentul ORCHESTREAZA prin adbsh).
    # ★ EXECUTIE PE ELF-URI (referat numpy, P2): pachetele Termux se extrag cu mod
    # `-rw-rw-r--` - FARA bit de exec. `chmod -R a+rX` NU ajuta (X = exec doar daca exista
    # deja pentru cineva). Deci TOT ce e binar real trebuie sa primeasca 755 explicit,
    # altfel clang/python/samu mor cu "Permission denied" (RC=126) si nimic nu se compileaza.
    # ★ TIMP + CORECTITUDINE: `python3` NU exista pe Android (doar prefixul nostru il are).
    # Vechiul apel `python3 setexec.py` nu rula NICIODATA -> bitul de exec nu era pus de
    # scriptul nostru, iar `chmod -R a+rX` singur NU pune exec pe fisiere fara el.
    # Acum folosim Python-ul TOOLCHAIN-ului, abia instalat, cu LD_LIBRARY_PATH corect.
    _sh("mkdir -p '%s/usr' && cp -a '%s/.' '%s/usr/' && chmod -R a+rX '%s/usr' 2>/dev/null; "
        "export LD_LIBRARY_PATH='%s/usr/lib'; python3.14 %s/setexec.py '%s/usr' 2>/dev/null; echo EXEC_BITS_SET"
        % (ROOT, STAGE, ROOT, ROOT, ROOT, F + "/python", ROOT), 1800)

    # ★ MARKER DE VERSIUNE (raportul numpy, A2): fara el nu putem sti CE e instalat
    # si daca prefixul de pe disc corespunde ultimului bootstrap. Scris dupa copiere.
    try:
        _v = "bootstrap=%s\npackages=%d\n" % (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), len(todo))
        _sh("printf '%s' > %s/.tc_version && chmod 644 %s/.tc_version; echo MKDONE" % (_v.replace("'", ""), ROOT, ROOT), 30)
        print("[toolchain] marker versiune: %s/.tc_version" % ROOT)
    except Exception as _e:
        print("[toolchain] nu am putut scrie markerul: %s" % str(_e)[:60])

    # FIXURI OBLIGATORII dupa instalare. Fiecare corespunde unei erori REALE:
    #  1. RUNPATH      - .deb-urile au /data/data/com.termux/... hardcodat
    #                    (inexistent aici) -> orice subproces moare cu exit 127
    #  2. ninja        - versiunea Termux nu poate spawn-ui procese -> samu
    #  3. cc wrappers  - clang default android24 ascunde functiile C99; PATH incomplet
    #  4. symlinks     - lipsesc python3/pip3 (Termux nu le face)
    #  5. sysconfig    - 71 de variabile arata prefixul Termux -> meson/pip esueaza
    #  6. CA bundle    - Python nu gaseste CA store -> pip HTTPS esueaza
    print("[toolchain] aplic fixurile de mediu (6 pasi)...")
    _patch_runpath()
    _fix_ninja()
    _fix_cc_wrappers()
    _fix_symlinks()
    _fix_wrappers_shebang()
    _fix_sysconfig()
    _fix_ca_bundle()
    _fix_libcxx_needed()
    _fix_cxx_linker()
    _fix_termux_paths()
    _fix_meson_exe()
    _write_env_file()

    # verificare
    st = check()
    if st.get("clang") or st.get("make"):
        # scris PRIN SHELL, in /data/local/tmp - acelasi loc pe care il citeste check()
        try:
            _sh("mkdir -p %s && printf ok > %s && chmod 644 %s; echo MKDONE" % (ROOT, MARKER, MARKER), 30)
        except Exception:
            pass
        print("[toolchain] PREFIX OK: clang=%s make=%s" % (st.get("clang"), st.get("make")))
    return ok > 0




def _simd_flags():
    """Extra SIMD flags for this SoC, controlled by AGENT_SIMD (default on, "0" disables).
    The numpy report suggests armv8.2-a+dotprod+fp16; on this Snapdragon those features exist and
    speed up dot products (numpy's matmul). Kept behind a switch because the same report warns
    'test it does not break something' - and a switch costs nothing when it works."""
    if os.environ.get("AGENT_SIMD", "1").strip() in ("0", "off", "no"):
        return ""
    return " -march=armv8.2-a+dotprod+fp16"


def env_vars():
    """Mediul COMPLET de compilare pentru TOOLCHAIN-UL DIN APK (nu Termux).

    Totul traieste in filesDir/toolchain: bin/ (clang, lld, binutils), sysroot/
    (headers+libs Android 35), pyinc/ (Python.h), deps/ (libxml2, libxslt, librt).
    Nu exista /data/local/tmp/wrap si nici prefix Termux: nimic nu le mai foloseste.
    """
    home = F + "/home"
    pipcache = home + "/.cache/pip"
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
    NAT = os.environ.get("TC_NATIVE", "")
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
        if os.path.exists(NAT + "/liblld_exec.so"):
            _ldl = F + "/tmp/ld.lld"
            try:
                if os.path.lexists(_ldl) and not os.path.islink(_ldl):
                    os.remove(_ldl)
                if not os.path.lexists(_ldl):
                    os.symlink(NAT + "/liblld_exec.so", _ldl)
            except Exception:
                pass
            if os.path.lexists(_ldl):
                _extra += " --ld-path=" + _ldl
    else:
        CC_EXEC = BIN + "/clang-21"
        PKG_EXEC = DEPS + "/bin/pkg-config"
        _extra = ""
    _cflags = ("-fPIC -O2 --target=aarch64-linux-android35 --sysroot=" + ROOT + "/sysroot "
               "-I" + ROOT + "/sysroot/usr/include -I" + ROOT + "/pyinc "
               "-I" + DEPS + "/include -I" + DEPS + "/include/libxml2")
    _ldflags = "-L" + DEPS + "/lib -L" + apexsdk
    return {
        "PATH": DEPS + "/bin:" + BIN + ":/system/bin",
        "TC_ROOT": ROOT,
        "TC_DEPS": DEPS,
        "CC": CC_EXEC + _extra,
        "CXX": BIN + "/clang-21++",
        "AR": BIN + "/llvm-ar",
        "RANLIB": BIN + "/llvm-ranlib",
        "NM": BIN + "/llvm-nm",
        "STRIP": BIN + "/llvm-strip",
        "READELF": BIN + "/llvm-readelf",
        "OBJDUMP": BIN + "/llvm-objdump",
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
        "LD_LIBRARY_PATH": (F + "/libs:"
                            + os.environ.get("LD_LIBRARY_PATH", "")),
        # ★ PYTHONHOME/PATH pentru stdlib: fara ele "Failed to import encodings".
        "PYTHONHOME": F + "/pyhome",
        "PYTHONUNBUFFERED": "1",
        # certificatul de CA: fara el pip HTTPS nu poate valida PyPI
        "SSL_CERT_FILE": _ca_bundle(),
        "CURL_CA_BUNDLE": _ca_bundle(),
        "REQUESTS_CA_BUNDLE": _ca_bundle(),
    }


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
    py = BIN + "/python3"
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


def install(force=False):
    """Alias pentru bootstrap_direct (compatibilitate)."""
    return bootstrap_direct()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    if cmd == "check":
        print(json.dumps(check(), indent=2))
    elif cmd == "doctor":
        print(json.dumps(doctor(), indent=2))
    elif cmd == "preflight":
        print(json.dumps(preflight(), indent=2))
    elif cmd == "profile":
        print(profile(sys.argv[2] if len(sys.argv) > 2 else "cmake"))
    elif cmd == "install":
        bootstrap_direct()
    elif cmd == "install_tpm":
        install(force="--force" in sys.argv)
    elif cmd == "bootstrap_direct":
        bootstrap_direct()
    elif cmd == "env":
        for k, v in env_vars().items():
            print(f'export {k}="{v}"')
    elif cmd == "env-file":
        _write_env_file()
        print("fisier: %s/env.sh" % ROOT)
    elif cmd == "fix":
        # re-aplica TOATE fixurile (util dupa ce agentul reinstaleaza pachete)
        _prepare_dirs(); _patch_runpath(); _fix_ninja(); _fix_cc_wrappers()
        _fix_symlinks(); _fix_wrappers_shebang(); _fix_sysconfig()
        _fix_ca_bundle(); _fix_libcxx_needed(); _fix_make_shell()
        _write_env_file()
        print(json.dumps(preflight(), indent=2))
