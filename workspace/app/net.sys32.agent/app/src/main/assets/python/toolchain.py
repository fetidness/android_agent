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
    """Starea toolchain-ului - verificari FUNCTIONALE, nu doar prezenta fisierelor.

    Fiecare test de aici corespunde unei erori REALE intalnite pe device;
    daca unul e rosu, agentul stie exact ce fix lipseste.
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
    rp = _sh('cd %s && n=0; for f in *; do [ -f "$f" ] && readelf -d "$f" 2>/dev/null '
             '| grep -q com.termux && n=$((n+1)); done; echo $n' % BIN, 180)
    need["runpath_ok"] = (rp.strip().split("\n")[-1].strip() == "0")
    # 7. numpy (daca e cerut explicit)
    if "numpy" in " ".join(PKGS):
        need["numpy"] = "numpy" in _sh("ls %s/lib/python3.14/site-packages 2>/dev/null" % ROOT, 30)
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
    'CANNOT LINK EXECUTABLE: library libX.so not found' (exit 127), iar
    ninja/meson raporteaza doar 'subcommand failed'.
    Fix: patch-uim RUNPATH la prefixul nostru real cu patchelf."""
    # ATENTIE: os.path.exists NU vede /data/local/tmp din sandbox-ul app-ului
    # (uid ~10384, SELinux) -> verificarea trebuie facuta prin SHELL (uid=2000)
    if "YES" not in _sh("test -x " + BIN + "/patchelf && echo YES || echo NO", 30):
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
# 4. patchelf NU se poate patch-ui pe sine ("Text file busy") -> copie care
#    patchuieste originalul, apoi se sterge
if readelf -d "$PE" 2>/dev/null | grep -q com.termux; then
  cp "$PE" /data/local/tmp/.pf_copy 2>/dev/null && chmod 755 /data/local/tmp/.pf_copy
  if [ -x /data/local/tmp/.pf_copy ]; then
    LD_LIBRARY_PATH="$L" /data/local/tmp/.pf_copy --set-rpath "$L" "$PE" 2>/dev/null
    rm -f /data/local/tmp/.pf_copy
  fi
fi
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
    s = BIN + "/samu"
    # la fel: verificare prin shell, nu os.path (app-ul nu vede /data/local/tmp)
    if "YES" not in _sh("test -x " + s + " && echo YES || echo NO", 30):
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
    prefixul real (/data/local/tmp/tpm/usr).
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
    """Extensiile C++ (numpy) NU au `NEEDED libc++_shared.so` desi folosesc
    simboluri din el -> la import: `cannot locate symbol _ZTVNSt6__ndk1...`.
    Solutia corecta (nu LD_PRELOAD): patchelf --add-needed pe fiecare .so din
    site-packages. Astfel importul merge fara nicio variabila de mediu."""
    script = r"""
B="__BIN__"; L="__LIB__"; P="__PREFIX__"
PE="$B/patchelf"; [ -x "$PE" ] || { echo NO_PATCHELF; exit 0; }
export LD_LIBRARY_PATH="$L:$LD_LIBRARY_PATH"
n=0
for d in "$P"/lib/python3.*/site-packages; do
  [ -d "$d" ] || continue
  for f in $(find "$d" -name '*.so' 2>/dev/null); do
    if readelf -d "$f" 2>/dev/null | grep -q 'NEEDED.*libc++_shared'; then continue; fi
    if "$PE" --add-needed libc++_shared.so "$f" 2>/dev/null; then n=$((n+1)); fi
  done
done
echo "LIBCXX_ADDED=$n"
"""
    script = (script.replace("__BIN__", BIN).replace("__LIB__", ROOT + "/usr/lib")
                    .replace("__PREFIX__", ROOT + "/usr"))
    try:
        out = _sh(script, 900)
        if "LIBCXX_ADDED" in out:
            print("[toolchain] " + out.strip().split("\n")[-1] + " .so legate la libc++_shared")
    except Exception as e:
        print("[toolchain] libcxx err:", e)


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
echo SYMLINKS_DONE
"""
    script = script.replace("__LIB__", ROOT + "/usr/lib").replace("__BIN__", BIN)
    try:
        out = _sh(script, 240)
        if "SYMLINKS_DONE" not in out:
            print("[toolchain] symlinks: partial", out[-200:])
    except Exception as e:
        print("[toolchain] symlinks err:", e)


def _prepare_dirs():
    """Creeaza directoarele de lucru (TMPDIR, HOME, cache pip).
    pip/meson au nevoie de un HOME si TMPDIR scriibile; fara ele: erori obscure."""
    script = r"""
mkdir -p /data/local/tmp/tmp __HOME__ __HOME__/.cache/pip 2>/dev/null
chmod 777 /data/local/tmp/tmp 2>/dev/null
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

    # verificare
    st = check()
    if st.get("clang") or st.get("make"):
        try: open(MARKER, "w").write("ok")
        except Exception: pass
        print("[toolchain] PREFIX OK: clang=%s make=%s" % (st.get("clang"), st.get("make")))
    return ok > 0




def env_vars():
    """Mediul COMPLET de compilare. Folosit de bootstrap, pip_install si compile.

    Toate variabilele de aici au fost adaugate dupa ce lipsa lor a cauzat
    esecuri reale pe device:
      CFLAGS/LDFLAGS --target  -> clang default android24 ascunde functiile C99
      LD_PRELOAD               -> extensiile C++ nu au NEEDED libc++_shared.so
      LD_LIBRARY_PATH          -> RUNPATH Termux e invalid; libm e in bionic
      PATH                     -> meson/ninja cheama rm/sh din /system/bin
      SSL_CERT_FILE            -> Python Termux nu gaseste CA store -> pip HTTPS esueaza
      HOME/TMPDIR              -> pip are nevoie de cache/scriere
    """
    home = F + "/home"
    pipcache = home + "/.cache/pip"
    try:
        os.makedirs(pipcache, exist_ok=True)
    except Exception:
        pass
    return {
        "PATH": (BIN + ":/system/bin:/system/xbin:" + F + "/python:"
                 + os.environ.get("PATH", "")),
        "PREFIX": ROOT + "/usr",
        "TERMUX_PREFIX": ROOT + "/usr",
        "CC": BIN + "/clang",
        "CXX": BIN + "/clang++",
        "AR": BIN + "/ar",
        "RANLIB": BIN + "/ranlib",
        "LD": BIN + "/ld",
        "NM": BIN + "/nm",
        "STRIP": BIN + "/strip",
        "MAKE": BIN + "/make",
        "CMAKE": BIN + "/cmake",
        # ★ API-ul REAL al telefonului (36 = Android 16), nu android24 implicit
        "CFLAGS": "--target=aarch64-linux-android%s -I%s/usr/include" % (_device_api(), ROOT),
        "CXXFLAGS": "--target=aarch64-linux-android%s -I%s/usr/include" % (_device_api(), ROOT),
        # ★ -lc++_shared EXPLICIT: meson-python nu adauga libc++ la linkare,
        #   iar extensiile C++ (numpy) ramân fara NEEDED libc++_shared.so
        #   -> la import: "cannot locate symbol _ZTVNSt6__ndk1..."
        "LDFLAGS": ("--target=aarch64-linux-android%s -L%s/usr/lib -L%s"
                    " -Wl,-rpath,%s/usr/lib -lc++_shared" % (_device_api(), ROOT, BIONIC_LIB, ROOT)),
        "PKG_CONFIG_PATH": ROOT + "/usr/lib/pkgconfig:" + ROOT + "/usr/share/pkgconfig",
        "PKG_CONFIG_LIBDIR": ROOT + "/usr/lib/pkgconfig:" + ROOT + "/usr/share/pkgconfig",
        "LD_LIBRARY_PATH": ROOT + "/usr/lib:" + BIONIC_LIB + ":" + F + "/libs",
        # ★ numpy si alte extensii C++ nu au NEEDED libc++_shared.so
        "LD_PRELOAD": ROOT + "/usr/lib/libc++_shared.so",
        # ★ fara asta pip HTTPS moare cu CERTIFICATE_VERIFY_FAILED
        "SSL_CERT_FILE": ROOT + "/usr/etc/tls/cert.pem",
        "SSL_CERT_DIR": ROOT + "/usr/etc/tls",
        "REQUESTS_CA_BUNDLE": ROOT + "/usr/etc/tls/cert.pem",
        "CURL_CA_BUNDLE": ROOT + "/usr/etc/tls/cert.pem",
        "HOME": home,
        "TMPDIR": "/data/local/tmp/tmp",
        "PIP_CACHE_DIR": pipcache,
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        "CARGO_HOME": home + "/.cargo",
    }


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
    elif cmd == "install":
        bootstrap_direct()
    elif cmd == "install_tpm":
        install(force="--force" in sys.argv)
    elif cmd == "bootstrap_direct":
        bootstrap_direct()
    elif cmd == "env":
        for k, v in env_vars().items():
            print(f'export {k}="{v}"')
