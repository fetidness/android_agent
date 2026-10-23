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
# ★ /data/data este montat NOEXEC: nimic din files/debian nu poate fi executat de proot.
# Rootfs-ul de LUCRU sta deci in /data/local/tmp (calea dovedita, accesibila uid-ului 2000).
ROOTFS = HOME + "/debian"                 # copia din APK (surse, nu se executa)
EXEC_ROOTFS = "/data/local/tmp/debian"    # rootfs-ul REAL, executabil
READY_FLAG = HOME + "/.debian_ready"      # setup complet, nu se mai repeta
WORKAREA = "/sdcard/Download/Agent/setup"  # zona citibila si de adbd (FUSE)
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
    rf = rootfs or EXEC_ROOTFS
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
         "HOME=/root", "TERM=xterm", "LANG=C.UTF-8", "DISPLAY=" + DISPLAY,
         "PROOT_NO_SECCOMP=1", "PYTHONDONTWRITEBYTECODE=1"]
    e.extend(extra)
    return e


def _proot_env():
    """PROOT_NO_SECCOMP=1 dezactiveaza acceleratorul seccomp al proot.
    Masurat pe SM-A366B: efect NUL la exec (zgomot +/-50%), dar opreste
    acceleratorul (dovedit cu PROOT_VERBOSE=1) - pastrat pentru predictibilitate."""
    e = dict(os.environ)
    e["PROOT_NO_SECCOMP"] = "1"
    e.setdefault("PROOT_TMP_DIR", TMP)
    e.setdefault("TMPDIR", TMP)
    return e


def _run(argv, timeout=600, cwd=None):
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, cwd=cwd,
                           env=_proot_env() if argv and "proot" in str(argv[0]).lower() else None)
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


# ------------------------------------------------------------------ bootstrap 1x
def _log(msg):
    """Progress trace to files/tmp/setup.log only (never stdout).

    stdout of the agent process is shown in the app's main window; the operator
    asked for provisioning output in the TERMINAL only.
    """
    try:
        os.makedirs(os.path.dirname(ADB_LOG), exist_ok=True)
        with open(ADB_LOG, "a") as f:
            f.write("[setup] " + msg + "\n")
    except Exception:
        pass


def _proot_exe_exec():
    """Copiaza libproot_exec.so intr-un loc EXECUTABIL din /data/local/tmp.

    files/tmp/proot e un symlink catre lib/arm64/libproot_exec.so: merge cand e lansat
    de aplicatie, dar NU e vizibil/executabil pentru adbd. /data/local/tmp e calea
    dovedita pentru exec din afara app-ului.
    """
    nd = _native_dir()
    if not nd:
        return None
    dst = "/data/local/tmp/proot_exec.so"
    src = os.path.join(nd, "libproot_exec.so")
    try:
        if (not os.path.exists(dst)) or os.path.getsize(dst) != os.path.getsize(src):
            import shutil as _sh
            _sh.copyfile(src, dst)
            os.chmod(dst, 0o755)
    except Exception:
        return None
    return dst if os.path.exists(dst) else None


def _copy_tree(src, dst):
    """Copiaza rootfs-ul din files/ in /data/local/tmp (dir -> dir)."""
    import shutil as _sh
    _sh.copytree(src, dst, symlinks=True, dirs_exist_ok=True)


def _extract_rootfs(src_archive, dest):
    """Extrage arhiva rootfs in `dest`, detectand formatul dupa magic bytes.

    ★ AGP dezactiveaza compresia la ambalare: pe device ajunge trixie-arm64.tar
    NECOMPRIMAT, desi in sursa e .tar.gz. `tar -xzf` pe el da "zcat: not gzip".
    Erorile pe nodurile din /dev (mknod fara root) si pe hardlink-uri sunt tolerate:
    /dev e oricum legat de la gazda prin --bind=/dev.
    """
    os.makedirs(dest, exist_ok=True)
    try:
        with open(src_archive, "rb") as f:
            magic = f.read(4)
    except Exception:
        magic = b""
    if magic[:2] == b"\x1f\x8b":
        argv = ["tar", "-xzf", src_archive, "-C", dest]
    elif magic[:4] == b"\x28\xb5\x2f\xfd":
        dec = _which("unzstd") or _which("zstd")
        if not dec:
            return -4, "no zstd decompressor"
        argv = ["sh", "-c", "%s -dc %s | tar -xf - -C %s" % (dec, src_archive, dest)]
    else:
        argv = ["tar", "-xf", src_archive, "-C", dest]
    rc, out = _run(argv, timeout=3600)
    ok_struct = all(os.path.isdir(os.path.join(dest, d)) for d in ("bin", "etc", "usr"))
    if rc != 0 and not ok_struct:
        return rc, out[-600:]
    return 0, out[-300:]


def ensure_ready(progress=True):
    """★ SETUP COMPLET, o singura data, la prima pornire dupa instalare.

    Face tot ce e nevoie ca binder-ul (si Debianul) sa functioneze imediat:
      1. copiaza rootfs-ul din assets in /data/local/tmp (executabil, nu in files/)
      2. copiaza proot intr-un loc executabil (/data/local/tmp/proot_exec.so)
      3. instaleaza gcc in Debian (necesar pentru clientul binder nativ)
      4. compileaza si instaleaza android-binder (sursa livrata in APK)
      5. verifica: android-binder selftest
    Idempotent: dupa reusita scrie READY_FLAG si iese imediat la urmatoarele porniri.
    """
    steps = []
    def L(m):
        steps.append(m)
        if progress:
            _log(m)

    # rootfs-ul deja pregatit? -> nimic de facut
    _ab = os.path.join(EXEC_ROOTFS, "usr/local/bin/android-binder")
    if os.path.exists(READY_FLAG) and os.path.isdir(os.path.join(EXEC_ROOTFS, "etc")) and os.path.exists(_ab):
        return {"ok": True, "skipped": True, "steps": ["already ready"]}

    # 1) rootfs in /data/local/tmp
    if os.path.isdir(os.path.join(EXEC_ROOTFS, "etc")):
        L("rootfs Debian: deja in /data/local/tmp")
    else:
        L("rootfs Debian: extragere in /data/local/tmp (poate dura 1-2 minute)...")
        archive = None
        for c in (HOME + "/proot/trixie-arm64.tar", HOME + "/proot/trixie-arm64.tar.gz",
                  HOME + "/proot/trixie-arm64.tar.zst", HOME + "/proot/trixie-arm64.tar.xz"):
            if os.path.exists(c):
                archive = c
                break
        if not archive:
            return {"ok": False, "error": "rootfs archive missing", "steps": steps}
        rc, out = _extract_rootfs(archive, EXEC_ROOTFS)
        if rc != 0:
            return {"ok": False, "error": "extract failed", "out": out, "steps": steps}
        L("rootfs Debian: extras (%s MB)" % _size_mb(EXEC_ROOTFS))

    # 2) proot executabil in /data/local/tmp
    exe = _proot_exe_exec()
    if not exe:
        return {"ok": False, "error": "cannot install proot to /data/local/tmp", "steps": steps}
    L("proot: %s" % exe)

    def _deb(cmd, timeout=1800):
        argv = [exe, "-0", "-r", EXEC_ROOTFS, "-w", "/root", "--link2symlink", "--sysvipc",
                "--kernel-release=6.1.0-debian", "--bind=/dev", "--bind=/proc", "--bind=/sys",
                "--bind=/data/local/tmp",
                "/usr/bin/env", "-i",
                "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                "HOME=/root", "DEBIAN_FRONTEND=noninteractive", "/bin/sh", "-c", cmd]
        return _run(argv, timeout=timeout)

    # 3) gcc (o singura data)
    rc, out = _deb("command -v gcc >/dev/null && echo HAVE || echo MISSING", timeout=120)
    if "HAVE" not in out:
        L("Debian: instalez gcc + libc6-dev (apt, o singura data)...")
        rc, out = _deb("apt-get update -qq && apt-get install -y -qq gcc libc6-dev", timeout=3600)
        if rc != 0:
            return {"ok": False, "error": "apt install gcc failed", "out": out[-500:], "steps": steps}
        L("Debian: gcc instalat")

    # 4) clientul binder, compilat din sursa livrata in APK
    binder_src = HOME + "/binder"
    if not os.path.exists(binder_src + "/debian_binder.c"):
        return {"ok": False, "error": "assets/binder missing (files/binder)", "steps": steps}
    # ★ sursa trebuie sa fie VIZIBILA in Debian: files/ nu e legat in guest, deci o
    # copiem in /data/local/tmp/binder (legat prin --bind=/data/local/tmp).
    try:
        import shutil as _sh
        _dst = "/data/local/tmp/binder"
        _sh.copytree(binder_src, _dst, dirs_exist_ok=True)
        os.chmod(os.path.join(_dst, "install_binder.sh"), 0o755)
    except Exception as _e:
        return {"ok": False, "error": "cannot stage binder sources: %s" % _e, "steps": steps}
    L("binder: sursa pregatita in /data/local/tmp/binder")
    L("binder: compilez clientul nativ din sursa din APK...")
    rc, out = _deb("sh /data/local/tmp/binder/install_binder.sh /data/local/tmp/binder", timeout=900)
    if rc != 0 and "selftest" not in out:
        return {"ok": False, "error": "binder install failed", "out": out[-600:], "steps": steps}
    L("binder: android-binder instalat")

    # 5) verificare
    rc, out = _deb("android-binder selftest", timeout=900)
    summary = ""
    for line in out.splitlines():
        if line.startswith(("servicii listate", "getService REUSIT", "CONCLUZIE")):
            summary += line.strip() + " | "
    if "FUNCTIONEAZA" in out:
        try:
            open(READY_FLAG, "w").write("ok")
        except Exception:
            pass
        L("binder: " + summary.rstrip(" |"))
        return {"ok": True, "steps": steps, "summary": summary}
    return {"ok": False, "error": "selftest failed", "out": out[-500:], "steps": steps}


# --------------------------------------------------- bootstrap prin ADB (uid 2000)
# ★ DE CE PRIN ADB SI NU DIRECT (dovedit pe device 2026-10-21):
#   - aplicatia (uid 10xxx) NU poate scrie in /data/local/tmp (drwxrwx--x shell shell)
#   - aplicatia NU poate execve nimic din app_data_file (W^X SELinux): un `cp` al lui
#     `echo` din rootfs in files/tmp da "No such file or directory" la exec
#   Deci rootfs-ul executabil + proot TREBUIE instalate de adbd (uid 2000, ctx shell:s0).
#   Progresul e scris intr-un fisier pe care aplicatia il citeste si il afiseaza.

ADB_LOG = HOME + "/tmp/setup.log"


def _adb_shell(cmd, timeout=1800):
    """Ruleaza o comanda ca uid 2000 prin adbd (calea dovedita)."""
    import adb_client as _ac
    c = _ac.shared()
    try:
        if not _ac.is_socket_healthy():
            _ac.close_shared()
            c = _ac.shared()
    except Exception:
        pass
    out = c.shell(cmd, timeout=timeout)
    if isinstance(out, bytes):
        out = out.decode("utf-8", "replace")
    return out or ""


def _logline(msg):
    """Progress trace for diagnostics ONLY (files/tmp/setup.log).

    ★ Nu scrie in stdout: stdout-ul procesului agentului ajunge in fereastra
    principala a aplicatiei, iar operatorul a cerut ca instalarea sa apara
    EXCLUSIV in terminal (vezi _run_terminal_setup din agent.py).
    """
    try:
        os.makedirs(HOME + "/tmp", exist_ok=True)
        with open(ADB_LOG, "a") as f:
            f.write("[setup] " + msg + "\n")
    except Exception:
        pass


# ★ Callback de progres LIVE: agent.py seteaza aici o functie care scrie DIRECT in
#   terminal (files/tmp/term_out_*.txt), ca fiecare pas sa apara cand se termina.
_LIVE_CB = [None]


def ensure_ready_via_adb(progress=True):
    """★ SETUP COMPLET la prima deschidere a TERMINALULUI.

    Toate operatiile grele ruleaza ca uid 2000 prin adbd (singura cale care poate
    executa din /data/local/tmp). Idempotent prin flag-ul files/.debian_ready.

    Ordinea:
      1. rootfs -> /data/local/tmp/debian (extras din tar-ul livrat in APK)
      2. proot  -> /data/local/tmp/proot_exec.so (din lib/arm64, cale citibila de adbd)
      3. sursa binder -> /data/local/tmp/binder (din files/binder)
      4. apt-get install gcc (o singura data)
      5. compilare + instalare android-binder
      6. android-binder selftest
    """
    steps = []
    # ★ _live e citit la INTRAREA in functie, dar callback-ul e setat de apelant INAINTE,
    #   deci il luam din nou aici (inainte ramanea None daca functia era apelata din alt
    #   loc, iar liniile [done] apareau doar la final, toate deodata).
    _live = _LIVE_CB[0]

    def L(m):
        steps.append(m)
        if progress:
            _logline(m)
        # ★ PROGRES LIVE (cerut de operator: "sa scrie progresiv ... una dupa alta"):
        #   inainte toate liniile [done] erau emise DUPĂ ce setup-ul se termina, deci
        #   utilizatorul vedea un bloc de text dintr-o data. Acum fiecare pas se scrie in
        #   terminal in momentul in care se termina.
        if _live is not None:
            try:
                _live(m)
            except Exception:
                pass

    try:
        os.remove(ADB_LOG)
    except Exception:
        pass

    # 0) deja pregatit?
    chk = _adb_shell("ls /data/local/tmp/debian/etc >/dev/null 2>&1 && "
                     "ls /data/local/tmp/debian/usr/local/bin/android-binder >/dev/null 2>&1 && echo READY || echo NO")
    if "READY" in chk and os.path.exists(READY_FLAG):
        return {"ok": True, "skipped": True, "steps": ["already ready"]}

    # 1) rootfs
    if "READY" in chk:
        L("rootfs Debian: deja instalat in /data/local/tmp")
    else:
        L("rootfs Debian: extragere in /data/local/tmp (1-2 minute)...")
        archive = None
        for c in (HOME + "/proot/trixie-arm64.tar", HOME + "/proot/trixie-arm64.tar.gz",
                  HOME + "/proot/trixie-arm64.tar.zst"):
            if os.path.exists(c):
                archive = c
                break
        if not archive:
            return {"ok": False, "error": "rootfs archive missing (files/proot)", "steps": steps}
        # tar-ul e in app_data_file: adbd NU poate citi de acolo (SELinux) -> il copiem
        # intai in /data/local/tmp cu o comanda care citeste prin aplicatie.
        # Metoda: scriem arhiva in bucati prin `cat` peste adb shell (stdin) nu e posibil;
        # de aceea o copiem in files/tmp si o facem citibila, apoi adbd o citeste dupa
        # ce o mutam in /sdcard (FUSE, citibil de orice context).
        try:
            import shutil as _sh
            dst = WORKAREA + "/trixie.tar"
            os.makedirs(WORKAREA, exist_ok=True)
            if not os.path.exists(dst) or os.path.getsize(dst) != os.path.getsize(archive):
                _sh.copyfile(archive, dst)
        except Exception as e:
            return {"ok": False, "error": "cannot stage rootfs archive: %s" % e, "steps": steps}
        L("rootfs: arhiva pregatita pentru adbd")
        r = _adb_shell("mkdir -p /data/local/tmp/debian && "
                       "tar -xf %s -C /data/local/tmp/debian 2>&1 | tail -3; "
                       "ls /data/local/tmp/debian/etc >/dev/null 2>&1 && echo EXTRACT_OK || echo EXTRACT_FAIL"
                       % dst, timeout=3600)
        if "EXTRACT_OK" not in r:
            return {"ok": False, "error": "extract failed", "out": r[-500:], "steps": steps}
        L("rootfs Debian: extras")

    # 2) proot executabil
    nd = _native_dir()
    if not nd:
        return {"ok": False, "error": "lib/arm64 not found", "steps": steps}
    src = os.path.join(nd, "libproot_exec.so")
    r = _adb_shell("cp -f %s /data/local/tmp/proot_exec.so && chmod 755 /data/local/tmp/proot_exec.so && "
                   "ls /data/local/tmp/proot_exec.so" % src)
    if "proot_exec.so" not in r:
        return {"ok": False, "error": "cannot install proot: %s" % r[-200:], "steps": steps}
    L("proot: /data/local/tmp/proot_exec.so")

    # 3) sursa binder -> /data/local/tmp/binder
    bsrc = HOME + "/binder"
    if not os.path.exists(os.path.join(bsrc, "debian_binder.c")):
        return {"ok": False, "error": "files/binder missing", "steps": steps}
    try:
        import shutil as _sh2
        _sh2.copytree(bsrc, WORKAREA + "/binder", dirs_exist_ok=True)
    except Exception as e:
        return {"ok": False, "error": "stage binder: %s" % e, "steps": steps}
    src_binder = WORKAREA + "/binder"
    _adb_shell("mkdir -p /data/local/tmp/binder")
    for fn in ("debian_binder.c", "binder.py", "install_binder.sh"):
        _adb_shell("cp -f %s/%s /data/local/tmp/binder/%s 2>/dev/null" % (src_binder, fn, fn))
    r = _adb_shell("chmod 755 /data/local/tmp/binder/install_binder.sh; "
                   "ls /data/local/tmp/binder/debian_binder.c")
    if "debian_binder.c" not in r:
        return {"ok": False, "error": "cannot stage binder sources: %s" % r[-200:], "steps": steps}
    L("binder: sursa in /data/local/tmp/binder")

    def deb(cmd, timeout=3600):
        return _adb_shell("PROOT_NO_SECCOMP=1 TMPDIR=/data/local/tmp "
                          "/data/local/tmp/proot_exec.so -0 -r /data/local/tmp/debian -w /root "
                          "--link2symlink --sysvipc --kernel-release=6.1.0-debian "
                          "--bind=/dev --bind=/proc --bind=/sys --bind=/data/local/tmp "
                          "/usr/bin/env -i PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin "
                          "HOME=/root DEBIAN_FRONTEND=noninteractive "
                          "/bin/bash -c " + repr(cmd), timeout=timeout)

    # 4) gcc
    if "HAVE" not in deb("command -v gcc >/dev/null && echo HAVE || echo MISSING", timeout=180):
        L("Debian: apt-get install gcc (o singura data)...")
        out = deb("apt-get update -qq >/dev/null 2>&1; apt-get install -y -qq gcc libc6-dev >/dev/null 2>&1; "
                  "command -v gcc >/dev/null && echo GCC_OK || echo GCC_FAIL")
        if "GCC_OK" not in out:
            return {"ok": False, "error": "gcc install failed", "out": out[-400:], "steps": steps}
        L("Debian: gcc instalat")

    # 5) binder
    L("binder: compilez din sursa din APK...")
    out = deb("sh /data/local/tmp/binder/install_binder.sh /data/local/tmp/binder 2>&1 | tail -12")
    # ★ FIX: install_binder.sh se termina cu `selftest`, deci output-ul nu contine
    # neaparat "android-binder"; verificam binarul PE DISC si rezultatul selftest.
    _chk = deb("ls /usr/local/bin/android-binder >/dev/null 2>&1 && echo BIN_OK || echo BIN_NO")
    if "BIN_OK" not in _chk and "package: found" not in out and "FUNCTIONEAZA" not in out:
        return {"ok": False, "error": "binder install failed", "out": out[-500:], "steps": steps}
    L("binder: android-binder instalat")

    # 6) selftest
    out = deb("android-binder selftest 2>&1 | tail -8", timeout=900)
    summary = " | ".join(l.strip() for l in out.splitlines()
                         if l.startswith(("servicii listate", "getService REUSIT", "CONCLUZIE")))
    if "FUNCTIONEAZA" in out:
        try:
            open(READY_FLAG, "w").write("ok")
        except Exception:
            pass
        L("binder: " + summary)
        return {"ok": True, "steps": steps, "summary": summary}
    return {"ok": False, "error": "selftest failed", "out": out[-400:], "steps": steps}


# ------------------------------------------------------------------ actiuni
def status():
    exe = _launcher()
    nd = _native_dir()
    rootfs_ok = os.path.isdir(os.path.join(EXEC_ROOTFS, "etc")) and os.path.exists(os.path.join(EXEC_ROOTFS, "bin", "bash"))
    r = {
        "proot_binary": exe or "MISSING",
        "native_dir": nd or "not found",
        "rootfs": EXEC_ROOTFS if rootfs_ok else "not installed",
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
            HOME + "/proot/trixie-arm64.tar",       # ★ AGP DEZARHIVEAZA .gz la ambalare:
            HOME + "/proot/trixie-arm64.tar.zst",   # pe device ajunge .tar NEcomprimat
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
            # ★ FIX 2026-10-21: AGP DEZARHIVEAZA assets-urile `.gz` la ambalare, deci pe
            # device ajunge `trixie-arm64.tar` NECOMPRIMAT. `tar -xzf` pe el da
            # "zcat: not gzip / tar: had errors". Detectam formatul dupa magic bytes.
            try:
                with open(src, "rb") as _f:
                    _magic = _f.read(4)
            except Exception:
                _magic = b""
            if _magic[:2] == b"\x1f\x8b":          # gzip
                _tf = ["tar", "-xzf", src, "-C", ROOTFS]
            elif _magic[:4] == b"\x28\xb5\x2f\xfd":  # zstd
                _dec = _which("unzstd") or _which("zstd")
                if not _dec:
                    return {"ok": False, "error": "no zstd decompressor",
                            "hint": "use trixie-arm64.tar.gz instead"}
                _tf = ["sh", "-c", "%s -dc %s | tar -xf - -C %s" % (_dec, src, ROOTFS)]
            else:                                    # tar necomprimat
                _tf = ["tar", "-xf", src, "-C", ROOTFS]
            rc, out = _run(_tf, timeout=1800)
        steps.append("extract rc=%s" % rc)
        # ★ FIX 2026-10-21: tar iese cu eroare pe nodurile din /dev (mknod fara root) si pe
        # link-urile hard in /usr/bin (uid diferit in tar). Astea NU invalideaza rootfs-ul:
        # /dev e oricum legat de la gazda (--bind=/dev), iar hardlink-ul are copie.
        # Acceptam extractia daca a aparut structura de baza (bin/ + etc/ + usr/).
        _rf_ok = all(os.path.isdir(os.path.join(ROOTFS, d)) for d in ("bin", "etc", "usr"))
        if rc != 0 and not _rf_ok:
            return {"ok": False, "error": "extract failed", "out": out[-800:]}
        if rc != 0:
            steps.append("extract: erori ignorate (doar noduri /dev si hardlink)")
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
