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
# ★ numele binarului instalat de setup-ul automat (ensure_ready_via_adb) este
# proot_exec.so; acceptam si numele vechi, ca sa nu depinda de ordinea de instalare.
PROOT = next((p for p in ("/data/local/tmp/proot_exec.so",
                          "/data/local/tmp/libproot_exec.so") if __import__("os").path.exists(p)),
             "/data/local/tmp/proot_exec.so")


def _adb():
    import adb_client
    try:
        if not adb_client.is_socket_healthy():
            adb_client.close_shared()
    except Exception:
        pass
    return adb_client.shared()


def run_in_debian(cmd, timeout=120, uid2000=False):
    """Executa o comanda in Debian (rootfs /data/local/tmp) sau ca uid 2000.

    ★ ALINIAT cu agent.py:run_in_debian (2026-10-22). Cele doua erau DUPLICATE si
    DIVERGENTE - varianta de aici nu avea --bind=/storage (=> orice acces la
    /sdcard sau /storage dadea "No such file or directory" desi fisierul exista
    pentru uid 2000), nici DEBIAN_FRONTEND=noninteractive (=> `apt install` fara -y
    bloca pana la timeout, fara sa poata raspunde nimeni la prompt), nici
    transmiterea prin base64 (=> adbd sparge comanda pe spatii si argv iese greșit).

    ★ DE CE PRIN ADB: /data/data e montat NOEXEC si untrusted_app nu poate execve
    din app_data_file (W^X). c.shell() pune adbd (uid 2000, u:r:shell:s0) sa faca
    execve-ul - singura cale corecta fara root.
    """
    import base64
    c = _adb()
    if uid2000:
        b = base64.b64encode(cmd.encode()).decode()
        return c.shell("echo " + b + " | base64 -d | /system/bin/sh", timeout=timeout) or ""
    full = (
        "%s -0 -r %s -w /root --link2symlink --sysvipc "
        "--kernel-release=6.1.0-debian "
        "--bind=/dev --bind=/proc --bind=/sys "
        "--bind=/sdcard --bind=/storage --bind=/data/local/tmp "
        "/usr/bin/env -i "
        "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin "
        "HOME=/root TERM=xterm-256color LANG=C.UTF-8 "
        "DEBIAN_FRONTEND=noninteractive "
        "APT_LISTCHANGES_FRONTEND=none "
        "DEBCONF_NONINTERACTIVE_SEEN=true "
        "PAGER=cat SYSTEMD_PAGER=cat GIT_PAGER=cat "
        "/bin/bash -c \"echo %s | base64 -d | /bin/bash\" </dev/null"
        % (PROOT, ROOTFS, base64.b64encode(cmd.encode()).decode())
    )
    return c.shell(full, timeout=timeout) or ""


def spawn(*a, **k):
    raise RuntimeError("terminal_server.spawn() a fost eliminat - foloseste run_in_debian()")

def run_batch(commands, timeout=600, stop_on_error=False):
    """Ruleaza MAI multe comenzi intr-un SINGUR proces proot.

    ★ DE CE (masurat pe SM-A366B, 2026-10-22):
      costul unei comenzi NU e proot si nici exec-ul, ci pornirea procesului +
      un round-trip adb (~110 ms). Flag-urile (-0, --kill-on-exit, --sysvipc,
      --link2symlink, bind-urile) dau toate 550-620 ms => irelevante.
      1 proot + 1 cmd = 114 ms/cmd ; 1 proot + 100 cmd = 1.7 ms/cmd.
      Comparativ cu un proot per comanda: 25.8x la 20 de comenzi.

    Returneaza lista de stringuri, cate unul per comanda (in ordine).
    Marcajele de delimitare folosesc un nonce ca sa nu se ciocneasca cu
    output-ul real al comenzilor.
    """
    import shlex, uuid
    if not commands:
        return []
    nonce = "MK_" + uuid.uuid4().hex[:12]
    parts = []
    for i, cmd in enumerate(commands):
        parts.append(
            "printf '\\n%s_%d_B\\n'; { %s\n }; printf '\\n%s_%d_E\\n'"
            % (nonce, i, cmd, nonce, i)
        )
    script = "\n".join(parts)
    # aceleasi bind-uri si aceleasi variabile ca run_in_debian (altfel batch-ul
    # nu vede /sdcard si un `apt install` poate bloca pe un prompt debconf)
    full = (
        "%s -0 -r %s -w /root --link2symlink --sysvipc "
        "--kernel-release=6.1.0-debian "
        "--bind=/dev --bind=/proc --bind=/sys "
        "--bind=/sdcard --bind=/storage --bind=/data/local/tmp "
        "/usr/bin/env -i PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin "
        "HOME=/root TERM=xterm-256color LANG=C.UTF-8 "
        "DEBIAN_FRONTEND=noninteractive APT_LISTCHANGES_FRONTEND=none "
        "DEBCONF_NONINTERACTIVE_SEEN=true PAGER=cat GIT_PAGER=cat "
        "/bin/bash -c %s" % (PROOT, ROOTFS, shlex.quote(script))
    )
    raw = _adb().shell(full, timeout=timeout) or ""
    out = []
    for i in range(len(commands)):
        b = "%s_%d_B" % (nonce, i)
        e = "%s_%d_E" % (nonce, i)
        try:
            s = raw.index(b) + len(b)
            t = raw.index(e, s)
            out.append(raw[s:t].strip("\n"))
        except ValueError:
            out.append("")
    return out
