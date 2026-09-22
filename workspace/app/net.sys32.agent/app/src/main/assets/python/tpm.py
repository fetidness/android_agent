#!/usr/bin/env python3
"""tpm.py - mini package manager Termux pentru Android (fara root, fara Termux).
Descarca pachete din repo-ul oficial Termux, le extrage si le face rulabile.

Folosire:
  python tpm.py search <cuvant>       -> cauta pachete
  python tpm.py install <pachet>      -> instaleaza (cu dependente)
  python tpm.py list                  -> listeaza pachetele instalate
  python tpm.py run <binar> [args]    -> ruleaza un binar instalat
  python tpm.py info <pachet>         -> detalii pachet
"""

# ---------------------------------------------------------------------------
# LICENTE: descarca pachete open-source din repo-ul public Termux
# (https://packages.termux.dev). Nu include/redistribuie binare. Fiecare pachet
# are licenta lui (Apache-2.0, PSF, GPL-3, MIT...). Folosire locala = fara
# obligatii de redistribuire. Vezi "termux-packages" pentru licenta fiecaruia.
# ---------------------------------------------------------------------------


# AUTO-FIX compression._common (AAPT2 ignora folderele "_") - INAINTE de importuri
def _ensure_compression():
    import os, sys
    if os.environ.get("_TC_FIXED"): return
    os.environ["_TC_FIXED"] = "1"
    cands = []
    try:
        import sysconfig
        pl = sysconfig.get_paths().get("purelib", "")
        if pl:
            cands.append(os.path.join(os.path.dirname(pl), "compression"))
            cands.append(os.path.join(pl, "compression"))
    except Exception: pass
    for d in sys.path:
        if d: cands.append(os.path.join(d, "compression"))
    for c in cands:
        if os.path.isdir(c) and os.path.exists(os.path.join(c, "_streams_data.py")):
            common = os.path.join(c, "_common")
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

import os
import sys
import re
import io
import tarfile
import subprocess
import urllib.request as _urlreq
class _Req:
    @staticmethod
    def get(url, timeout=60, **kw):
        try:
            with _urlreq.urlopen(url, timeout=timeout) as r:
                class _Resp:
                    def __init__(s, data): s.content=data; s.status_code=200; s.text=data.decode("utf-8","replace")
                return _Resp(r.read())
        except Exception as e:
            class _Err:
                def __init__(s): s.status_code=500; s.content=b""; s.text=str(e)
            return _Err()
requests = _Req()

# ocolire bug biblioteca standard (compression._common lipseste)
sys.path.insert(0, "/data/user/0/net.sys32.agent/files/pyhome/lib/python3.14/lib-dynload")
import zlib
import _lzma

# ============================================================
#  CONFIGURARE
# ============================================================
REPO = "https://packages.termux.dev/apt/termux-main"
ARCH = "aarch64"
ROOT = "/data/local/tmp/tpm"          # unde instalam (executabil!)
BIN = os.path.join(ROOT, "usr", "bin")
WS = "/storage/emulated/0/Download/Agent/workspace"
INDEX_URL = f"{REPO}/dists/stable/main/binary-{ARCH}/Packages.gz"
# ============================================================


# import adb_client pentru shell uid 2000
sys.path.insert(0, "/data/user/0/net.sys32.agent/files/python")
_ADB = None

def _get_adb():
    global _ADB
    if _ADB is None:
        from adb_client import Adb
        _ADB = Adb()
        _ADB.connect()
    return _ADB


class _Res:
    def __init__(self, out, rc=0):
        self.stdout = out
        self.stderr = ""
        self.returncode = rc


def sh(cmd, timeout=60):
    """Ruleaza comanda cu uid=2000.
    Daca ruleaza DEJA ca shell (uid 2000), foloseste subprocess direct (rapid).
    Altfel foloseste adb_client (app -> adbd -> shell)."""
    try:
        # daca suntem deja shell privileged, subprocess e suficient
        if os.geteuid() == 2000:
            rc = subprocess.run(["/system/bin/sh", "-c", cmd],
                                capture_output=True, text=True, timeout=timeout)
            r = _Res(rc.stdout + rc.stderr, rc.returncode)
            return r
    except Exception:
        pass
    try:
        out = _get_adb().shell(cmd, timeout=timeout)
        return _Res(out)
    except Exception as e:
        return _Res("[sh-error] " + str(e)[:150], 1)


def _decompress_gz(data):
    return zlib.decompressobj(16 + zlib.MAX_WBITS).decompress(data)


def _decompress_xz(data):
    d = _lzma.LZMADecompressor(format=_lzma.FORMAT_AUTO)
    return d.decompress(data)


def ensure_root():
    sh(f"mkdir -p '{BIN}' '{ROOT}/packages'")


def load_index():
    """Descarca si parseaza index-ul de pachete Termux (cache in workspace)."""
    cache = os.path.join(WS, ".tpm_index")
    if os.path.exists(cache) and os.path.getsize(cache) > 1000:
        text = open(cache, "r", encoding="utf-8", errors="replace").read()
    else:
        r = requests.get(INDEX_URL, timeout=90)
        text = _decompress_gz(r.content).decode("utf-8", "replace")
        open(cache, "w").write(text)
    return parse_index(text)


def parse_index(text):
    pkgs = {}
    for blk in text.split("\n\n"):
        if not blk.strip():
            continue
        def g(key):
            m = re.search(rf"^{key}: (.+)$", blk, re.M)
            return m.group(1).strip() if m else None
        name = g("Package")
        if not name:
            continue
        deps = g("Depends") or ""
        dep_list = []
        for d in deps.split(","):
            d = d.strip().split("|")[0].strip()
            d = re.sub(r"\s*\(.*\)", "", d)
            d = re.sub(r":.*$", "", d)
            if d and d not in ("", ":"):
                dep_list.append(d)
        pkgs[name] = {
            "version": g("Version"),
            "filename": g("Filename"),
            "size": int(g("Size") or 0),
            "deps": dep_list,
        }
    return pkgs


def resolve_deps(pkgs, name, seen=None):
    if seen is None:
        seen = []
    if name in seen or name not in pkgs:
        return seen
    seen.append(name)
    for d in pkgs[name]["deps"]:
        resolve_deps(pkgs, d, seen)
    return seen


def extract_deb(tmp_path, name):
    """Extrage data.tar din .deb direct in ROOT, prin shell uid 2000."""
    data = open(tmp_path, "rb").read()

    def members(deb):
        out = []
        off = 8
        while off < len(deb) - 60:
            h = deb[off:off+60]
            if h[58:60] != b"\x60\x0a":
                break
            nm = h[0:16].decode("ascii", "replace").strip()
            sz = int((h[48:58].decode("ascii", "replace").strip() or "0"))
            out.append((nm, off+60, sz))
            off += 60 + sz
            if off % 2: off += 1
        return out

    data_off = None
    for nm, off, sz in members(data):
        if nm.startswith("data.tar"):
            data_off = off
    if data_off is None:
        print(f"  [!] nu gasesc data.tar in {name}")
        return False

    xz = data.find(b"\xfd7zXZ\x00", data_off)
    raw = None
    if xz == data_off:
        raw = _decompress_xz(data[data_off:])
    elif xz >= 0:
        raw = _decompress_xz(data[xz:])
    if raw is None:
        print(f"  [!] format necunoscut pentru {name}")
        return False

    # scriu tar-ul brut intr-un fisier .tar in workspace, apoi shell-ul il extrage
    tar_path = os.path.join(WS, f".tpm_{name}.tar")
    open(tar_path, "wb").write(raw)
    os.chmod(tar_path, 0o666)

    # shell: extrage data.tar, copiaza usr in ROOT/usr, sterge
    work = "/data/local/tmp/tpm/.work"
    cmd = (f"rm -rf '{work}'; mkdir -p '{work}' '{ROOT}/usr'; "
           f"tar -xf '{tar_path}' -C '{work}' && "
           f"cp -a '{work}/data/data/com.termux/files/usr/.' '{ROOT}/usr/' && "
           f"chmod -R 755 '{ROOT}/usr' 2>/dev/null; "
           f"rm -rf '{work}' '{tar_path}'")
    r = sh(cmd)
    os.remove(tmp_path)
    # curata tar-ul daca a ramas
    if os.path.exists(tar_path):
        try: os.remove(tar_path)
        except: pass
    return True


def cmd_search(pkgs, term):
    hits = [n for n in pkgs if term.lower() in n.lower()]
    print(f"pachete care contin '{term}': {len(hits)}")
    for n in sorted(hits)[:40]:
        print(f"  {n:35s} {pkgs[n]['version']}")


def cmd_info(pkgs, name):
    if name not in pkgs:
        print(f"pachetul '{name}' nu exista")
        return
    i = pkgs[name]
    print(f"Pachet:     {name}")
    print(f"Versiune:   {i['version']}")
    print(f"Marime:     {i['size']} bytes")
    print(f"Dependente: {', '.join(i['deps']) or '(niciuna)'}")


def cmd_install(pkgs, name):
    if name not in pkgs:
        print(f"pachetul '{name}' nu exista in repo")
        return
    ensure_root()
    todo = resolve_deps(pkgs, name)
    print(f"de instalat ({len(todo)}): {', '.join(todo)}")
    for p in todo:
        dep = pkgs[p]
        url = f"{REPO}/{dep['filename']}"
        tmp = os.path.join(WS, f".tpm_{p}.deb")
        print(f"  -> {p} {dep['version']} ({dep['size']} bytes)...", end=" ", flush=True)
        try:
            r = requests.get(url, timeout=180)
            open(tmp, "wb").write(r.content)
        except Exception as e:
            print("EROARE download:", e)
            continue
        ok = extract_deb(tmp, p)
        print("OK" if ok else "ESEC")
    print("\ninstalat in:", ROOT)
    r = sh(f"ls -1 '{BIN}' 2>/dev/null | head -40")
    print("binare:", r.stdout or "(niciunul)")


def cmd_list():
    r = sh(f"ls -1 '{BIN}' 2>/dev/null")
    print("binare instalate:")
    print(r.stdout or "(niciunul)")


def cmd_run(args):
    if not args:
        print("Utilizare: tpm.py run <binar> [args]")
        return
    if not os.path.exists(os.path.join(BIN, args[0])):
        print(f"binarul '{args[0]}' nu e instalat. Vezi: tpm.py list")
        return
    lib = f"{ROOT}/usr/lib"
    binar = os.path.join(BIN, args[0])
    cmd = " ".join([f"LD_LIBRARY_PATH='{lib}'", binar] + args[1:])
    r = sh(cmd)
    print(r.stdout, end="")
    if r.stderr:
        print("[stderr]", r.stderr, end="")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    act = sys.argv[1]
    rest = sys.argv[2:]

    if act == "run":
        cmd_run(rest)
        return
    if act == "list":
        cmd_list()
        return

    print("incarc index-ul Termux...")
    pkgs = load_index()
    print(f"pachete disponibile: {len(pkgs)}\n")

    if act == "search":
        cmd_search(pkgs, rest[0] if rest else "")
    elif act == "info":
        cmd_info(pkgs, rest[0] if rest else "")
    elif act == "install":
        cmd_install(pkgs, rest[0] if rest else "")
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
