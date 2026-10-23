#!/usr/bin/env python3
"""android_api - date Android reale, citite prin uid 2000.

Doua moduri de lucru, alese automat:
  1. IN APLICATIE (recomandat): importa `agent` si foloseste android_api() direct.
  2. CA SCRIPT: cheama android_run.py, care ruleaza in app si scrie in bridge/.

Uz:  python3 android_api.py battery|location|wifi|telephony|sensors|accel|services|all
"""
import json
import os
import subprocess
import sys
from pathlib import Path


def _files_dir() -> Path:
    env = os.environ.get("AGENT_FILES_DIR")
    if env and os.path.isdir(env):
        return Path(env)
    here = Path(__file__).resolve().parent
    for cand in (here, here.parent, here.parent.parent):
        if (cand / "pyhome").is_dir() or (cand / "python").is_dir():
            return cand
    return Path("/data/data/net.sys32.agent/files")


def _bridge_dir(files: Path) -> Path:
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


def _in_app() -> bool:
    """Suntem in procesul aplicatiei (agentul poate fi importat)?"""
    py = _files_dir() / "python"
    if not (py / "agent.py").is_file():
        return False
    if str(py) not in sys.path:
        sys.path.insert(0, str(py))
    try:
        import agent  # noqa: F401
        return hasattr(agent, "android_api")
    except Exception:
        return False


def _via_agent(what, limit):
    """Calea buna: functia din agent, deja parsata.

    Agentul afiseaza pasi pe stdout (_, _show_step) si loguri adb_client pe stderr;
    le capturam ca output-ul acestui script sa fie JSON curat, parsabil.
    """
    py = _files_dir() / "python"
    if str(py) not in sys.path:
        sys.path.insert(0, str(py))
    import contextlib
    import io
    buf_out, buf_err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
        import agent
        return agent.android_api(what=what, limit=limit)


def _via_runner(what, limit):
    """Fallback: ruleaza android_run.py intr-un proces al aplicatiei."""
    runner = Path(__file__).resolve().parent / "android_run.py"
    cmd = "dumpsys battery" if what == "battery" else "dumpsys %s" % what
    subprocess.run([sys.executable, str(runner), cmd, "raw_" + what],
                   capture_output=True, text=True, timeout=90)
    f = _bridge_dir(_files_dir()) / ("raw_%s.txt" % what)
    return {"raw": f.read_text() if f.exists() else "", "fallback": True}


ACTIONS = ("battery", "location", "wifi", "telephony", "sensors", "accel", "services")


def get(what="battery", limit=5):
    """Intoarce dict cu date reale. Preferă calea din agent."""
    if _in_app():
        try:
            return _via_agent(what, limit)
        except Exception:
            pass
    return _via_runner(what, limit)


def _clean(obj):
    """JSON curat: adb_client scrie pe stdout din alt thread (in afara redirect-ului)."""
    return json.dumps(obj, indent=1, ensure_ascii=False)


if __name__ == "__main__":
    w = sys.argv[1] if len(sys.argv) > 1 else "battery"
    lim = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    if w == "all":
        payload = _clean({k: get(k, lim) for k in ACTIONS})
    elif w in ACTIONS:
        payload = _clean(get(w, lim))
    else:
        payload = __doc__
    # marcaj clar: consumatorii parseaza intre BEGIN/END (adb_client scrie pe stdout
    # si din thread-ul lui, deci pot aparea linii "[adb] ..." in jurul JSON-ului)
    sys.stdout.write("<<<ANDROID_API_JSON>>>\n")
    sys.stdout.write(payload.rstrip() + "\n")
    sys.stdout.write("<<<END_ANDROID_API_JSON>>>\n")
    sys.stdout.flush()
