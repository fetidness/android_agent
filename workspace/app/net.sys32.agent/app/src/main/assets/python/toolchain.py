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
    import os, sys
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
ROOT = "/data/local/tmp/tpm"
BIN = ROOT + "/usr/bin"

# pachetele necesare pentru compilare COMPLETA (inclusiv numpy/scipy-level)
PKGS = [
    "clang", "lld", "make", "pkg-config", "cmake", "ninja", "patchelf", "samurai",
    "ndk-sysroot",
    "python", "python-pip", "binutils", "libandroid-spawn",
    "zlib", "liblzma", "libbz2", "openssl", "libffi",
    "ncurses", "readline", "sqlite", "libexpat", "libxml2",
    "git", "tar", "xz-utils", "coreutils", "findutils", "grep", "sed", "gawk",
    "rust", "libc++", "binutils-libs", "termux-elf-cleaner",
]

# biblioteci bionice de pe DEVICE (libm.so real, cu simboluri C99 complete).
# clang nu linkeaza -lm implicit pe android36, iar termux nu are libm.so in prefix.
BIONIC_LIB = "/apex/com.android.runtime/lib64/bionic"
BIONIC_LIB_FALLBACK = "/system/lib64"

MARKER = F + "/.toolchain_ok"


def _sh(cmd, timeout=300):
    """Ruleaza o comanda ca uid=2000 (singurul care vede /data/local/tmp)."""
    try:
        import sys as _s
        for _p in (os.path.dirname(os.path.abspath(__file__)), F + "/python",
                   "/data/data/net.sys32.agent/files/python"):
            if _p not in _s.path:
                _s.path.insert(0, _p)
        import adb_client as _AC
        a = _AC.Adb()
        try:
            a.connect()
            out = a.shell(cmd, timeout=timeout)
            try: a.close()
            except Exception: pass
            return out or ""
        except Exception:
            try: a.close()
            except Exception: pass
            raise
    except Exception as e:
        return "[shell-error] " + str(e)[:120]


def have(binary):
    """Verifica prin shell (uid=2000) - app-ul NU vede /data/local/tmp."""
    r = _sh("test -x %s/%s && echo YES || echo NO" % (BIN, binary), 20)
    return "YES" in r


def check():
    """Returneaza dict cu ce e instalat (o singura comanda ls = robust)."""
    out = _sh("ls " + BIN + " 2>/dev/null", 30)
    present = set(out.split())
    need = {
        "clang": ("clang" in present) or ("clang-21" in present),
        "make": "make" in present,
        "python": "python3" in present,
        "pip": ("pip" in present) or ("pip3" in present),
        "cmake": "cmake" in present,
        "ninja": "ninja" in present,
        "samu": ("samurai" in present) or ("ninja" in present),
        "ld": ("ld" in present) or ("lld" in present),
        "ar": ("ar" in present) or ("llvm-ar" in present),
        "git": "git" in present,
        "pkg-config": "pkg-config" in present,
        "rust": "rustc" in present,
        "patchelf": "patchelf" in present,
        "samu": "samu" in present,
        "sysroot(crt)": "crtbegin_dynamic.o" in set(
            _sh("ls " + ROOT + "/usr/lib 2>/dev/null", 30).split()),
        "marker": os.path.exists(MARKER),
    }
    # verificare FUNCTIONALA (nu doar prezenta fisierului): chiar poate compila?
    probe = _sh(
        'cd /data/local/tmp 2>/dev/null || cd /tmp; '
        'printf "int main(void){return 0;}" > .tc_probe.c; '
        'PATH=' + BIN + ':$PATH ' + BIN + '/clang --target=aarch64-linux-android36 '
        '.tc_probe.c -o .tc_probe 2>&1; echo RC=$?', 120)
    need["compile_test"] = "RC=0" in probe
    if not need["compile_test"]:
        need["compile_hint"] = probe.strip()[-200:]
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
    """Parseaza un tar (ustar/gnu) si extrage in dest - pur Python."""
    PREF = ("./data/data/com.termux/files/usr/", "data/data/com.termux/files/usr/")
    off = 0
    n = 0
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
        # prefix (ustar)
        prefix = hdr[345:500].split(b"\x00")[0].decode("utf-8", "replace")
        if prefix:
            name = prefix + "/" + name
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
            if typeflag in (b"5",):  # dir
                os.makedirs(out, exist_ok=True)
            elif typeflag in (b"2",):  # symlink
                os.makedirs(os.path.dirname(out), exist_ok=True)
                if os.path.lexists(out):
                    os.remove(out)
                os.symlink(linkname, out)
            elif typeflag in (b"1",):  # hardlink
                os.makedirs(os.path.dirname(out), exist_ok=True)
                src_p = os.path.join(dest, linkname)
                for pref in PREF:
                    if linkname.startswith(pref):
                        src_p = os.path.join(dest, linkname[len(pref):]); break
                if os.path.exists(src_p):
                    if os.path.lexists(out): os.remove(out)
                    os.link(src_p, out)
            elif typeflag in (b"0", b"\x00", b""):  # file
                os.makedirs(os.path.dirname(out), exist_ok=True)
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
    'CANNOT LINK EXECUTABLE: library libX.so not found' (exit 127), iar
    ninja/meson raporteaza doar 'subcommand failed'.
    Fix: patch-uim RUNPATH la prefixul nostru real cu patchelf."""
    if not os.path.exists(BIN + "/patchelf"):
        print("[toolchain] patchelf lipsa - sar peste fix RUNPATH")
        return
    script = r"""
B="__BIN__"; L="__LIB__"; P="__PREFIX__"
PE="$B/patchelf"
[ -x "$PE" ] || { echo NO_PATCHELF; exit 0; }
export LD_LIBRARY_PATH="$L:$LD_LIBRARY_PATH"
# 1. binarele
for f in "$B"/*; do
  [ -f "$f" ] || continue
  case "$f" in *.orig|*.new) continue;; esac
  if readelf -d "$f" 2>/dev/null | grep -q com.termux; then
    chmod u+r "$f" 2>/dev/null
    "$PE" --set-rpath "$L" "$f" 2>/dev/null
  fi
done
# 2. bibliotecile din prefix
for f in "$L"/*.so*; do
  [ -f "$f" ] || continue
  if readelf -d "$f" 2>/dev/null | grep -q com.termux; then
    "$PE" --set-rpath "$L" "$f" 2>/dev/null
  fi
done
# 3. modulele din lib-dynload (altfel pip moare la import)
for d in "$P"/lib/python3.*/lib-dynload; do
  [ -d "$d" ] || continue
  for f in "$d"/*.so; do
    [ -f "$f" ] || continue
    if readelf -d "$f" 2>/dev/null | grep -q com.termux; then
      "$PE" --set-rpath "$L" "$f" 2>/dev/null
    fi
  done
done
echo RUNPATH_DONE
"""
    script = (script.replace("__BIN__", BIN).replace("__LIB__", ROOT + "/usr/lib")
                    .replace("__PREFIX__", ROOT + "/usr"))
    try:
        out = _sh(script, 600)
        if "RUNPATH_DONE" in out:
            print("[toolchain] RUNPATH corectat (binare + libs + lib-dynload)")
        else:
            print("[toolchain] RUNPATH: partial", out[-200:])
    except Exception as e:
        print("[toolchain] RUNPATH err:", e)


def _fix_ninja():
    """ninja din Termux e RUPT: nu poate executa NICIUN subproces
    (libandroid-spawn.so la runtime) -> 'ninja: subcommand failed', code=127.
    samurai (samu) face acelasi lucru si merge. Inlocuim ninja cu samu."""
    n = BIN + "/ninja"
    s = BIN + "/samu"
    if not os.path.exists(s):
        print("[toolchain] samu lipsa - nu pot inlocui ninja")
        return
    script = r"""
B="__BIN__"
if [ -f "$B/ninja" ] && [ ! -f "$B/ninja.orig" ]; then cp "$B/ninja" "$B/ninja.orig"; fi
cp "$B/samu" "$B/ninja" && chmod 755 "$B/ninja" && echo NINJA_DONE
"""
    script = script.replace("__BIN__", BIN)
    try:
        out = _sh(script, 120)
        if "NINJA_DONE" in out:
            print("[toolchain] ninja -> samu (ninja din Termux e rupt)")
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
# 3. binare uzuale
for pair in "clang:clang-21" "clang++:clang-21" "cc:clang-21" "c++:clang-21" \
            "ld:lld" "ld.lld:lld" "ar:llvm-ar" "ranlib:llvm-ranlib" \
            "nm:llvm-nm" "objdump:llvm-objdump" "strip:llvm-strip" \
            "readelf:llvm-readelf" "python:python3" "pip:pip3" ; do
  link=$(echo "$pair" | cut -d: -f1); tgt=$(echo "$pair" | cut -d: -f2)
  if [ -e "$B/$tgt" ] && [ ! -e "$B/$link" ]; then ln -sf "$tgt" "$B/$link"; fi
done
echo SYMLINKS_DONE
"""
    script = script.replace("__LIB__", ROOT + "/usr/lib").replace("__BIN__", BIN)
    try:
        out = _sh(script, 240)
        if "SYMLINKS_DONE" not in out:
            print("[toolchain] symlinks: partial", out[-200:])
    except Exception as e:
        print("[toolchain] symlinks err:", e)


def bootstrap_direct(packages=None, progress=None):
    """Bootstrap COMPLET: descarca .deb, extrage in staging (app),
    apoi copiaza in prefix (/data/local/tmp, prin adbsh)."""
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
    _sh("mkdir -p '%s/usr' && cp -a '%s/.' '%s/usr/' && chmod -R 755 '%s/usr/bin' '%s/usr/lib' 2>/dev/null; echo COPIED"
        % (ROOT, STAGE, ROOT, ROOT, ROOT), 1800)

    # recreez symlink-urile .so (Termux)
    print("[toolchain] recreez symlink-uri...")
    _fix_symlinks()

    # FIXURI OBLIGATORII dupa instalare (altfel compilarea NU merge):
    #  1. RUNPATH: .deb-urile Termux au calea /data/data/com.termux/... care nu exista
    #     -> orice subproces moare cu exit 127
    #  2. ninja: versiunea Termux nu poate spawn-ui procese -> samu
    print("[toolchain] aplic fixurile (RUNPATH + ninja)...")
    _patch_runpath()
    _fix_ninja()
    _fix_cc_wrappers()
    _fix_symlinks()

    # verificare
    st = check()
    if st.get("clang") or st.get("make"):
        try: open(MARKER, "w").write("ok")
        except Exception: pass
        print("[toolchain] PREFIX OK: clang=%s make=%s" % (st.get("clang"), st.get("make")))
    return ok > 0




def env_vars():
    """Variabilele de mediu pentru compilare (PATH, CC, CXX, CFLAGS, LDFLAGS...)."""
    return {
        "PATH": BIN + ":" + F + "/python:" + os.environ.get("PATH", ""),
        "PREFIX": ROOT + "/usr",
        "TERMUX_PREFIX": ROOT + "/usr",
        "CC": BIN + "/clang",
        "CXX": BIN + "/clang++",
        "AR": BIN + "/ar",
        "RANLIB": BIN + "/ranlib",
        "LD": BIN + "/ld",
        # API 36 (Android 16) - fara el, clang are target android24 si ASCUNDE
        # functiile C99 introduse ulterior (ex. ctanl/ccoshl din complex.h)
        "CFLAGS": "--target=aarch64-linux-android36 -I" + ROOT + "/usr/include",
        "LDFLAGS": ("--target=aarch64-linux-android36 -L" + ROOT + "/usr/lib"
                    + " -L" + BIONIC_LIB
                    + " -Wl,-rpath," + ROOT + "/usr/lib"),
        "PKG_CONFIG_PATH": ROOT + "/usr/lib/pkgconfig:" + ROOT + "/usr/share/pkgconfig",
        "LD_LIBRARY_PATH": ROOT + "/usr/lib:" + BIONIC_LIB + ":" + F + "/libs",
        # numpy si alte extensii C++ nu au NEEDED libc++_shared.so dar folosesc
        # simboluri din el -> fara preload: "cannot locate symbol _ZTVNSt6__ndk1..."
        "LD_PRELOAD": ROOT + "/usr/lib/libc++_shared.so",
    }


def _enable_pip():
    """Activeaza pip in python3-ul din toolchain (via ensurepip)."""
    py = BIN + "/python3"
    if not os.path.exists(py):
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
    elif cmd == "install":
        bootstrap_direct()
    elif cmd == "install_tpm":
        install(force="--force" in sys.argv)
    elif cmd == "bootstrap_direct":
        bootstrap_direct()
    elif cmd == "env":
        for k, v in env_vars().items():
            print(f'export {k}="{v}"')
