"""devhelper.py - adbsh + python intr-un SINGUR pas.

Problema pe care o rezolva: bash/python ruleaza ca uid=10331 (aplicatia, fara privilegii),
iar pentru dumpsys/pm/am//proc se cere uid=2000. In loc de uneltele separate, aici ai:

    import devhelper as dh
    out = dh.shell("dumpsys battery")            # ruleaza ca uid=2000
    d   = dh.lines(out)                          # parse comod
    dh.sudo("pm grant pkg perm")                 # acelasi lucru

Conexiunea adb se pastreaza (shared) + reconectare automata la eroare.
"""
import os, re, json, time, subprocess, functools

_cache = {"adb": None, "t": 0}

def adb():
    """Sesiunea adb partajata (uid=2000). Reconecteaza daca a cazut."""
    try:
        import adb_client
    except Exception as e:
        raise RuntimeError("adb_client indisponibil: %r" % (e,))
    a = _cache.get("adb")
    if a is not None:
        try:
            if adb_client.is_socket_healthy(a):
                return a
        except Exception:
            pass
    a = adb_client.shared()
    _cache["adb"] = a
    _cache["t"] = time.time()
    return a

def shell(cmd, timeout=30, as_shell=True):
    """Ruleaza o comanda. as_shell=True -> uid=2000 (privilegii adb); False -> aplicatia."""
    if not as_shell:
        r = subprocess.run(["/system/bin/sh", "-c", cmd], capture_output=True,
                           text=True, errors="replace", timeout=timeout)
        return (r.stdout or "") + (r.stderr or "")
    try:
        return adb().shell(cmd, timeout=timeout) or ""
    except Exception:
        _cache["adb"] = None
        return adb().shell(cmd, timeout=timeout) or ""

sudo = shell  # alias: shell() e deja uid=2000

def run(args, timeout=30, as_shell=False):
    """Executa un argv (fara shell parsing) - deterministic, fara probleme de quoting."""
    if as_shell:
        import shlex
        return shell(" ".join(shlex.quote(x) for x in args), timeout=timeout)
    r = subprocess.run(args, capture_output=True, text=True, errors="replace", timeout=timeout)
    return (r.stdout or "") + (r.stderr or "")

# ---------- parsing comod ----------
def lines(out):
    """Linii ne-goale, fara CR."""
    return [l.strip("\r") for l in (out or "").splitlines() if l.strip()]

def grep(out, pat, flags=0):
    """Filtreaza liniile dupa regex (in PYTHON - nu toybox grep)."""
    rx = re.compile(pat, flags)
    return [l for l in (out or "").splitlines() if rx.search(l)]

def kv(out, sep=r"[:=]"):
    """'cheie: valoare' -> dict (prima aparitie)."""
    d = {}
    for l in lines(out):
        m = re.split(sep, l, 1)
        if len(m) == 2:
            d.setdefault(m[0].strip(), m[1].strip())
    return d

def jload(out):
    """JSON din output (robust: sare peste liniile non-JSON din fata)."""
    try:
        return json.loads(out)
    except Exception:
        i = (out or "").find("{")
        j = (out or "").find("[")
        k = min([x for x in (i, j) if x >= 0] or [-1])
        if k >= 0:
            return json.loads(out[k:])
        raise

def meminfo():
    """RAM reala ca dict in kB (uid=2000)."""
    d = {}
    for l in lines(shell("cat /proc/meminfo")):
        m = re.match(r"(\w+):\s+(\d+)", l)
        if m:
            d[m.group(1)] = int(m.group(2))
    return d

def top_cpu(seconds=3, n=10):
    """Top CPU real, masurat in 2 timpi (in PYTHON) prin uid=2000. Nu foloseste top/toybox."""
    def snap():
        out = shell("for p in /proc/[0-9]*/stat; do awk '{print $1, $14+$15}' $p 2>/dev/null; done")
        d = {}
        for l in out.splitlines():
            x = l.split()
            if len(x) == 2 and x[1].isdigit():
                d[x[0]] = int(x[1])
        return d
    a = snap(); time.sleep(seconds); b = snap()
    rows = []
    for pid, j in b.items():
        if pid in a and j >= a[pid]:
            rows.append(((j - a[pid]) / float(seconds) / 10.0, pid))
    rows.sort(reverse=True)
    out = []
    for pct, pid in rows[:n]:
        nm = shell("cat /proc/%s/comm 2>/dev/null" % pid).strip()
        out.append((pct, nm, pid))
    return out

def procs():
    """Lista procese (pid, rss_kb, name) sortate dupa RSS - prin uid=2000."""
    out = shell("for p in /proc/[0-9]*; do pid=${p#/proc/}; "
                "n=$(cat $p/comm 2>/dev/null); r=$(awk '/VmRSS/{print $2}' $p/status 2>/dev/null); "
                "[ -n \"$r\" ] && echo \"$r $pid $n\"; done")
    rows = []
    for l in out.splitlines():
        x = l.split(None, 2)
        if len(x) == 3 and x[0].isdigit():
            rows.append((int(x[0]), x[1], x[2]))
    rows.sort(reverse=True)
    return rows

def is_shell_user():
    """Verifica daca adb ne da uid=2000."""
    return "uid=2000" in shell("id")
