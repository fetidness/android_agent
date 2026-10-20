#!/usr/bin/env python3
"""terminal_server.py - DEPRECAT ca proces separat.

★ ISTORIC (2026-10-20): a fost scris ca server de pty ca sa ofere un terminal
interactiv in aplicatie. NU functioneaza si NU mai e folosit:

  1. adbd NU trimite A_WRTE catre stdin-ul procesului in sesiunile shell,raw/v2
     (dovedit pe device: promptul apare, tastele nu ajung) -> bash interactiv
     imposibil pe aceasta cale.
  2. procesul separat nu poate rula proot: /data/data e montat NOEXEC, iar
     untrusted_app nu poate execve binarare din app_data_file (SELinux W^X).

Calea CORECTA (dovedita, folosita de agent.py):
  adb_client.shared().shell()  ->  adbd executa ca uid 2000 (u:r:shell:s0)
                               ->  proot -0 -r /data/local/tmp/debian
                               ->  bash in Debian, output real

Fisierul rămâne doar ca sa nu se sparga importurile vechi din agent.py.
"""

HOME = "/data/data/net.sys32.agent/files"
ROOTFS = "/data/local/tmp/debian"
PROOT = "/data/local/tmp/libproot_exec.so"


def _adb():
    import adb_client
    try:
        if not adb_client.is_socket_healthy():
            adb_client.close_shared()
    except Exception:
        pass
    return adb_client.shared()


def run_in_debian(cmd, timeout=120, uid2000=False):
    """Executa o comanda in Debian (sau ca uid 2000) prin ADB intern."""
    import shlex
    c = _adb()
    if uid2000:
        return c.shell(cmd, timeout=timeout) or ""
    full = (
        "%s -0 -r %s -w /root --link2symlink --sysvipc "
        "--kernel-release=6.1.0-debian --bind=/dev --bind=/proc --bind=/sys "
        "/usr/bin/env -i PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin "
        "HOME=/root TERM=xterm-256color LANG=C.UTF-8 "
        "/bin/bash -c %s" % (PROOT, ROOTFS, shlex.quote(cmd))
    )
    return c.shell(full, timeout=timeout) or ""


def spawn(*a, **k):
    raise RuntimeError("terminal_server.spawn() a fost eliminat - foloseste run_in_debian()")
