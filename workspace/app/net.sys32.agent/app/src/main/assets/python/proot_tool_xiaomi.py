"""proot_tool_xiaomi.py - instalare Debian OFFLINE pentru telefoane fara root (Xiaomi etc).

De ce exista separat: helper-ul original (proot_tool.py) merge pe Samsung, unde `adb root`
este disponibil si rootfs-ul se aranjeaza o singura data, manual. Pe telefoane FARA root
(Xiaomi 2409FPCC4G, Android 16) instalarea originala se bloca, cu aceste cauze DOVEDITe:
  1. verifica `usr/local/bin/android-binder` ca semn de "gata" - binarul se compila abia la
     pasul 5, deci verificarea nu putea iesi OK si setup-ul repornea de la zero la infinit;
  2. `os.path.exists(usr/bin/python3)` pe un SYMLINK creat de alt user intoarce FALSE pe
     Android -> folosim fisierele reale (python3.13 / gcc-14);
  3. toybox `tar` nu pastreaza modurile: extrage 0700 (drwx------) si proot nu poate intra
     in usr/bin -> normalizam 0755/0644;
  4. `apt-get install gcc` la runtime depindea de DNS-ul guest-ului si atarna minute;
     imaginea livrata are deja gcc + python3, deci nu se descarca nimic;
  5. sursele binder nu puteau fi scrise in /data/local/tmp de aplicatie (uid 10xxx) - acum
     le scrie adbd (uid 2000), iar binarul e deja compilat in imagine.
NU se atinge nimic din proot_tool.py: acesta ramane calea pentru Samsung.
"""
import os
import time

ROOTFS_LIB = "libagentroot_exec.so"        # numele imaginii in nativeLibraryDir
PROOT_LIB = "libproot_exec.so"
READY_MARK = "v3"                          # marker diferit: nu se amesteca cu originalul
ADB_WAIT_S = 180                          # cat asteptam autorizarea adbd (3 min)


def _pt():
    import proot_tool
    return proot_tool


def _say(line=""):
    """Scrie o linie DIRECT in terminal (files/tmp/term_out_*.txt), imediat."""
    import glob
    try:
        for f in glob.glob("/data/data/net.sys32.agent/files/tmp/term_out_*.txt"):
            with open(f, "a", encoding="utf-8", errors="replace") as fh:
                fh.write(line + "\n")
    except Exception:
        pass


def available():
    """Modul nou se aplica doar daca APK-ul chiar contine imaginea completa."""
    pt = _pt()
    nd = pt._native_dir()
    if not nd:
        return False
    return os.path.exists(os.path.join(nd, ROOTFS_LIB))


def _adb(cmd, timeout=1800):
    return _pt()._adb_shell(cmd, timeout=timeout)


def _proot_prefix():
    return ("PROOT_NO_SECCOMP=1 PROOT_TMP_DIR=/data/local/tmp TMPDIR=/data/local/tmp "
            "/data/local/tmp/proot_exec.so -0 -r /data/local/tmp/debian -w /root "
            "--kill-on-exit --link2symlink --sysvipc --kernel-release=6.1.0-debian "
            "--bind=/dev --bind=/proc --bind=/sys "
            "--bind=/dev/urandom:/dev/random --bind=/proc/self/fd:/dev/fd "
            "--bind=/data/local/tmp ")


def _env():
    return ("/usr/bin/env -i PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin "
            "HOME=/root TERM=xterm LANG=C.UTF-8 DEBIAN_FRONTEND=noninteractive ")


def ready():
    """Rootfs complet: marker + structura + toolchain REAL (nu symlink)."""
    rf = "/data/local/tmp/debian"

    def has(*r):
        return os.path.exists(os.path.join(rf, *r))
    return (has(".agent_rootfs_" + READY_MARK) and os.path.isdir(os.path.join(rf, "etc")) and
            os.path.isdir(os.path.join(rf, "usr", "bin")) and
            (has("usr", "bin", "python3.13") or has("usr", "bin", "python3") or
             has("usr", "bin", "gcc-14") or has("usr", "bin", "gcc")))


def version():
    out = _adb("cat /data/local/tmp/debian/etc/debian_version 2>/dev/null", timeout=60)
    return (out.strip() or "?")


def _lock():
    """Lock pe disc: un singur setup o data, chiar daca doua fire/app porniri il cer simultan."""
    import fcntl
    f = open("/data/data/net.sys32.agent/files/tmp/.setup_linux.lock", "w")
    return f


def ensure(progress=True):
    """Instalare completa. Idempotenta. Intoarce dict cu ok/steps/error (ca originalul).

    ★ Un singur setup simultan: la prima lansare il porneste aplicatia automat, iar daca
    operatorul deschide si terminalul, al doilea apel NU mai reinstaleaza (altfel logul se
    dubleaza si se copiaza imaginea de doua ori degeaba).
    """
    import fcntl
    _lkf = _lock()
    try:
        fcntl.flock(_lkf, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except Exception:
        _lkf.close()
        return {"ok": True, "skipped": True,
                "steps": ["setup already running in another thread"]}
    try:
        return _ensure_locked(progress)
    finally:
        try:
            fcntl.flock(_lkf, fcntl.LOCK_UN)
            _lkf.close()
        except Exception:
            pass


def _ensure_locked(progress=True):
    pt = _pt()
    steps = []
    live = pt._LIVE_CB[0] if hasattr(pt, "_LIVE_CB") else None

    def L(label, detail=""):
        steps.append(label if not detail else label + ": " + detail)
        try:
            pt._logline(label + (" | " + detail if detail else ""))
        except Exception:
            pass
        if live is not None:
            try:
                live(label, detail or "OK")
            except Exception:
                pass

    # ---- 0) adbd: asteptam AUTORIZAREA (dialogul "Allow USB debugging") ----
    #  Un telefon fara root nu permite aplicatiei sa ruleze Linux singura (SELinux opreste
    #  execve in app_data_file), deci adbd e obligatoriu. Daca poarta nu e deschisa, mesajul
    #  spune EXACT ce sa faca operatorul, iar instalarea reporneste SINGURA dupa autorizare
    #  (bucla de mai jos), fara sa mai fie nevoie sa tasteze `setup` din nou.
    ok = False
    waited = 0
    while waited <= ADB_WAIT_S:
        try:
            out = _adb("echo ADB_OK", timeout=60)
        except Exception as e:
            out = "ADB_FAIL " + str(e)
        if "ADB_OK" in out:
            ok = True
            break
        if waited == 0:
            L("Android shell", "waiting for USB debugging authorisation")
            _say("")
            _say("Waiting for the Android shell (adbd) ...")
            _say("On the phone: Settings -> Developer options -> enable 'USB debugging',")
            _say("then accept the 'Allow USB debugging' dialog. Setup continues by itself.")
        time.sleep(5)
        waited += 5
    if not ok:
        return {"ok": False,
                "error": "USB debugging is not authorised",
                "hint": ("Settings -> Developer options -> USB debugging must be ON and the "
                         "'Allow USB debugging' dialog accepted. Then tap TERMINAL again."),
                "steps": steps}
    if waited:
        L("Android shell", "authorised after %ss" % waited)

    if ready():
        L("Linux filesystem", "already installed (Debian %s)" % version())
    else:
        src = os.path.join(pt._native_dir(), ROOTFS_LIB)
        L("Linux filesystem", "staging image (%.0f MB)" % (os.path.getsize(src) / 1e6))
        r = _adb("rm -rf /data/local/tmp/debian; cp -f %s /data/local/tmp/agentroot.tar.gz && "
                 "mkdir -p /data/local/tmp/debian && "
                 "tar -xzf /data/local/tmp/agentroot.tar.gz -C /data/local/tmp/debian 2>&1 | tail -2; "
                 "test -f /data/local/tmp/debian/etc/debian_version && echo EXTRACT_OK || echo EXTRACT_FAIL"
                 % src, timeout=1800)
        if "EXTRACT_OK" not in r:
            return {"ok": False, "error": "cannot install the Linux filesystem",
                    "out": r[-400:], "steps": steps}
        # toybox tar pierde modurile -> proot nu poate intra in usr/bin
        _adb("chmod 755 /data/local/tmp/debian; "
             "find /data/local/tmp/debian -type d -exec chmod 755 {} + 2>/dev/null; "
             "find /data/local/tmp/debian -type f -perm -u+x -exec chmod 755 {} + 2>/dev/null; "
             "touch /data/local/tmp/debian/.agent_rootfs_%s" % READY_MARK, timeout=600)
        L("Linux filesystem", "Debian " + version())

    nd = pt._native_dir()
    _adb("cp -f %s /data/local/tmp/proot_exec.so && chmod 755 /data/local/tmp/proot_exec.so"
         % os.path.join(nd, PROOT_LIB), timeout=300)
    L("Linux runtime", "proot ready")

    out = _adb(_proot_prefix() + _env() +
               "/bin/sh -c 'echo GUEST_OK; cat /etc/debian_version; python3 -V'", timeout=300)
    if "GUEST_OK" not in out:
        return {"ok": False, "error": "the Linux environment does not start",
                "out": out[-300:], "steps": steps}
    ls = [x.strip() for x in out.strip().splitlines() if x.strip()]
    L("Linux runtime", "Debian %s, %s" % (ls[1] if len(ls) > 1 else "?",
                                          ls[2] if len(ls) > 2 else ""))

    chk = _adb("test -x /data/local/tmp/debian/usr/local/bin/android-binder && echo AB_OK || echo AB_NO",
               timeout=60)
    if "AB_OK" in chk:
        st = _adb(_proot_prefix() + _env() +
                  "/bin/sh -c 'timeout 90 android-binder selftest 2>&1 | tail -3'", timeout=200)
        summ = " ".join(x.strip() for x in st.splitlines()
                        if x.strip().startswith(("servicii", "CONCLUZIE")))
        L("Android service access", summ[:150] or "client present")
    else:
        L("Android service access", "not in image (optional)")

    try:
        open(pt.READY_FLAG, "w").write("ok")
    except Exception:
        pass
    return {"ok": True, "steps": steps}
