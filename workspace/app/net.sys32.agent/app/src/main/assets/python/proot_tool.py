"""proot_tool.py - container Debian arm64 nativ pe Android (proot + X11/VNC).

Tool al agentului: `proot(action=...)`.
  status   - stare completa: binare, rootfs, desktop, porturi, RAM, spatiu
  install  - extrage rootfs din assets (o singura data) + launcher (idempotent)
  login    - ruleaza o comanda in Debian (cmd="apt update")
  gui      - porneste desktopul (Xtigervnc :1 + fluxbox + xterm)
  desktop  - porneste GUI-ul si deschide DesktopActivity (client VNC integrat)
  stop     - opreste desktopul
  bench    - benchmark proot vs nativ (dovada de performanta)
  bind     - listeaza/adauga bind-uri (ex: /sdcard)

Design (lectii din build):
  * proot e livrat ca libproot_exec.so in nativeLibraryDir si e chemat prin
    symlink din files/tmp (SELinux judeca TINTA, nu symlink-ul).
  * rootfs sta in files/debian (ext4/f2fs, NU /sdcard FUSE) - proot face un
    syscall per path resolution.
  * bind minim: /dev /proc /sys /dev/urandom->/dev/random /proc/self/fd->/dev/fd
    (fara /proc, xterm nu poate aloca pty).
  * --link2symlink + --sysvipc (X11 are nevoie de shm/semafoare).
  * fara -0: rootul din rootfs e deja root; -0 doar adauga overhead.
"""
import json
import os
import shutil
import subprocess
import time

HOME = "/data/data/net.sys32.agent/files"
ROOTFS = HOME + "/debian"
TMP = HOME + "/tmp"
PORT = 5901
DISPLAY = ":1"


def _native_dir():
    """Directorul nativeLibraryDir (unde stau executabilele din APK)."""
    exe = os.readlink("/proc/self/exe") if os.path.exists("/proc/self/exe") else ""
    for cand in (
        os.path.dirname(os.path.realpath(exe)),
        os.path.join(os.path.dirname(HOME), "lib"),
    ):
        p = os.path.join(cand, "libproot_exec.so")
        if os.path.exists(p):
            return cand
    # fallback: cauta in /data/app
    import glob
    for p in glob.glob("/data/app/*/net.sys32.agent-*/lib/arm64"):
        if os.path.exists(os.path.join(p, "libproot_exec.so")):
            return p
    return None


def _launcher():
    """Symlink files/tmp/proot -> libproot_exec.so din APK (executabil)."""
    nd = _native_dir()
    if not nd:
        return None
    os.makedirs(TMP, exist_ok=True)
    link = os.path.join(TMP, "proot")
    target = os.path.join(nd, "libproot_exec.so")
    try:
        if os.path.islink(link):
            if os.path.realpath(link) != os.path.realpath(target):
                os.unlink(link)
        if not os.path.exists(link):
            os.symlink(target, link)
    except OSError:
        pass
    return link if os.path.exists(link) else None


def _proot_cmd(rootfs=None, extra_binds=()):
    exe = _launcher()
    if not exe:
        return None
    rf = rootfs or ROOTFS
    cmd = [
        exe, "-r", rf, "-w", "/root",
        "--kill-on-exit", "--link2symlink", "--sysvipc",
        "--kernel-release=6.1.0-debian",
        "--bind=/dev", "--bind=/proc", "--bind=/sys",
        "--bind=/dev/urandom:/dev/random",
        "--bind=/proc/self/fd:/dev/fd",
    ]
    for b in extra_binds:
        cmd.append("--bind=" + b)
    return cmd


def _env(*extra):
    e = ["/usr/bin/env", "-i",
         "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
         "HOME=/root", "TERM=xterm", "LANG=C.UTF-8", "DISPLAY=" + DISPLAY]
    e.extend(extra)
    return e


def _run(argv, timeout=600, cwd=None):
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, cwd=cwd)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return -9, "timeout after %ss" % timeout
    except Exception as e:
        return -1, "%s: %s" % (type(e).__name__, e)


def _which(name):
    for d in ("/system/bin", "/system/xbin", os.path.join(HOME, "toolchain/bin"), os.path.join(HOME, "tmp")):
        p = os.path.join(d, name)
        if os.path.exists(p):
            return p
    return None


def _size_mb(path):
    try:
        out = subprocess.run(["du", "-s", "-k", path], capture_output=True, text=True, timeout=30).stdout
        return int(out.split()[0]) // 1024
    except Exception:
        return -1


# ------------------------------------------------------------------ actiuni
def status():
    exe = _launcher()
    nd = _native_dir()
    rootfs_ok = os.path.isdir(os.path.join(ROOTFS, "etc")) and os.path.exists(os.path.join(ROOTFS, "bin", "bash"))
    r = {
        "proot_binary": exe or "MISSING",
        "native_dir": nd or "not found",
        "rootfs": ROOTFS if rootfs_ok else "not installed",
    }
    if rootfs_ok:
        rc, out = _run(_proot_cmd() + _env("/bin/sh", "-c", "uname -s; cat /etc/debian_version; dpkg -l | grep -c ^ii"), timeout=90)
        r["debian_check_rc"] = rc
        r["debian"] = out.strip().splitlines()[-3:]
    # desktop
    rc, out = _run(["sh", "-c", "pgrep -f Xtigervnc >/dev/null && echo running || echo stopped"], timeout=20)
    r["desktop"] = out.strip()
    rc, out = _run(["sh", "-c", "netstat -ln 2>/dev/null | grep -c 5901 || echo 0"], timeout=20)
    r["vnc_port_5901"] = out.strip()
    return r


def install(asset_zip=None):
    """Extrage rootfs-ul Debian din assets (o singura data) si pregateste launcher-ul."""
    steps = []
    if os.path.isdir(os.path.join(ROOTFS, "etc")):
        steps.append("rootfs already installed")
    else:
        # asset-urile extrase de MainActivity stau in files/proot/
        cands = [asset_zip] if asset_zip else []
        cands += [
            HOME + "/proot/trixie-arm64.tar.zst",
            HOME + "/proot/trixie-arm64.tar.gz",
            HOME + "/proot/trixie-arm64.tar.xz",
        ]
        src = next((c for c in cands if c and os.path.exists(c)), None)
        if not src:
            return {"ok": False, "error": "rootfs archive missing", "looked": cands}
        if not os.path.exists(src):
            return {"ok": False, "error": "rootfs archive missing", "looked": src}
        os.makedirs(ROOTFS, exist_ok=True)
        if src.endswith(".zst"):
            # toybox tar nu are zstd, iar stdlib-ul nu are zstd: folosim `unzstd`
            # daca exista in toolchain; altfel raportam clar ce lipseste.
            dec = os.path.join(HOME, "toolchain/bin/unzstd")
            if not os.path.exists(dec):
                dec = _which("unzstd") or _which("zstd")
            if not dec:
                return {"ok": False, "error": "no zstd decompressor",
                        "hint": "use trixie-arm64.tar.gz instead (.tar.zst needs zstd)"}
            rc, out = _run(["sh", "-c", "%s -dc %s | tar -xf - -C %s" % (dec, src, ROOTFS)], timeout=1800)
        else:
            rc, out = _run(["tar", "-xzf", src, "-C", ROOTFS], timeout=1800)
        steps.append("extract rc=%s" % rc)
        if rc != 0:
            return {"ok": False, "error": "extract failed", "out": out[-800:]}
    exe = _launcher()
    steps.append("launcher=%s" % exe)
    return {"ok": bool(exe), "steps": steps}


def login(cmd, timeout=600, binds=()):
    argv = _proot_cmd(extra_binds=binds) + _env("/bin/sh", "-lc", cmd)
    rc, out = _run(argv, timeout=timeout)
    return {"rc": rc, "out": out[-6000:]}


def gui(geometry=None, start=True):
    if not start:
        rc, out = _run(["sh", "-c", "pkill -f Xtigervnc; pkill -f fluxbox; pkill -f 'xterm -geometry'"], timeout=30)
        return {"ok": True, "stopped": out.strip()}
    geo = geometry or _screen_geometry()
    script = "/data/local/tmp/debian_x.sh"
    if not os.path.exists(script):
        return {"ok": False, "error": "debian_x.sh missing"}
    exe = _launcher()
    rc, out = _run(["sh", script, ROOTFS, exe, geo, "start"], timeout=180)
    return {"ok": rc == 0, "geometry": geo, "out": out.strip()[-1200:]}


def _screen_geometry():
    try:
        p = subprocess.run(["sh", "-c", "wm size"], capture_output=True, text=True, timeout=20).stdout
        # "Physical size: 1080x2340"
        for line in p.splitlines():
            if "size:" in line:
                return line.split("size:")[1].strip()
    except Exception:
        pass
    return "1080x2340"


def bench():
    """Compara proot vs nativ pe device (dovada de performanta, nu impresii)."""
    exe = _launcher()
    sh = ("dd if=/dev/zero bs=1M count=50 2>/dev/null > /data/local/tmp/z.bin; "
          "echo NB; { time sha256sum /data/local/tmp/z.bin >/dev/null; } 2>&1 | grep real; "
          "{ time gzip -3 -c /data/local/tmp/z.bin >/dev/null; } 2>&1 | grep real")
    rc1, native = _run(["sh", "-c", sh], timeout=300)
    sh2 = ("echo PB; { time sha256sum /data/local/tmp/z.bin >/dev/null; } 2>&1 | grep real; "
           "{ time gzip -3 -c /data/local/tmp/z.bin >/dev/null; } 2>&1 | grep real; rm -f /data/local/tmp/z.bin")
    rc2, deb = _run(_proot_cmd() + _env("/bin/sh", "-c", sh2), timeout=300)
    return {"native": native.strip(), "proot": deb.strip()}


def handle(args):
    a = (args.get("action") or "status").lower()
    if a == "status":
        return status()
    if a == "install":
        return install(args.get("archive"))
    if a == "login":
        return login(args.get("cmd") or "id", timeout=int(args.get("timeout") or 600),
                     binds=tuple(args.get("bind") or ()))
    if a == "gui":
        return gui(args.get("geometry"), start=(args.get("start") is not False))
    if a == "stop":
        return gui(None, start=False)
    if a == "bench":
        return bench()
    return {"error": "unknown action: " + a,
            "actions": ["status", "install", "login", "gui", "stop", "bench"]}


if __name__ == "__main__":
    import sys
    act = sys.argv[1] if len(sys.argv) > 1 else "status"
    cmd = sys.argv[2] if len(sys.argv) > 2 else "id"
    print(json.dumps(handle({"action": act, "cmd": cmd}), indent=1, ensure_ascii=False))
