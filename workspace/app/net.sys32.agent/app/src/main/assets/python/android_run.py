#!/usr/bin/env python3
"""android_run - executa o comanda ca uid 2000 (prin adb_client) si scrie rezultatul.

Rulat din procesul aplicatiei (uid app). Debian il poate chema daca are acces
la acest fisier; altfel se foloseste modulul android_api.

Uz: python3 android_run.py "<shell cmd>" [nume]
Rezultat: bridge/<nume>.txt (citibil din Debian)
"""
import sys, os, subprocess
from pathlib import Path


def _files_dir():
    """filesDir-ul aplicatiei, fara cai hardcodate."""
    env = os.environ.get("AGENT_FILES_DIR")
    if env and os.path.isdir(env):
        return Path(env)
    here = Path(__file__).resolve().parent
    for cand in (here, here.parent, here.parent.parent):
        if (cand / "pyhome").is_dir() or (cand / "python").is_dir():
            return cand
    return Path("/data/data/net.sys32.agent/files")


def _bridge_dir(files: Path) -> Path:
    """Directorul de schimb cu Debian: workspace-ul de pe /sdcard daca exista."""
    env = os.environ.get("AGENT_BRIDGE_DIR")
    if env:
        p = Path(env)
    else:
        p = Path("/storage/emulated/0/Download/Agent/workspace/bridge")
        if not p.parent.parent.is_dir():
            p = files / "bridge"
    p.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(p, 0o777)
    except Exception:
        pass
    return p


def shell(cmd, timeout=40):
    """Ruleaza comanda ca uid 2000 prin adb_client (modulul e langa acest fisier)."""
    py = _files_dir() / "python"
    if py.is_dir() and str(py) not in sys.path:
        sys.path.insert(0, str(py))
    from adb_client import shared
    out = shared().shell(cmd, timeout=timeout) or ""
    return "\n".join(l for l in out.splitlines() if not l.startswith("[adb]")).strip()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "id"
    name = sys.argv[2] if len(sys.argv) > 2 else "out"
    text = shell(cmd)
    dest = _bridge_dir(_files_dir()) / (name + ".txt")
    dest.write_text(text)
    try:
        os.chmod(dest, 0o644)
    except Exception:
        pass
    print("OK -> %s (%d bytes)" % (dest, len(text)))
