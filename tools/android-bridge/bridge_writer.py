#!/usr/bin/env python3
"""bridge_writer - ruleaza IN APP, scrie date Android in bridge/*.json
Debian le citeste. Nu depinde de adbsh.
"""
import json, os, subprocess, sys
from pathlib import Path

BR = Path("/storage/emulated/0/Download/Agent/workspace/bridge")
BR.mkdir(parents=True, exist_ok=True)
os.chmod(BR, 0o777)

def w(name, obj):
    p = BR / f"{name}.json"
    p.write_text(json.dumps(obj, indent=1))
    os.chmod(p, 0o644)
    return str(p)

def sh(cmd):
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=25)
        return p.stdout
    except Exception as e:
        return f"ERR:{e}"

def write_system():
    out = sh("getprop | head -60")
    w("system_props", {"raw": out})

def write_meminfo():
    out = sh("cat /proc/meminfo | head -6")
    w("meminfo", {"raw": out})

def write_uptime():
    w("uptime", {"raw": sh("uptime")})

if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    if what in ("all","system"): write_system()
    if what in ("all","mem"): write_meminfo()
    if what in ("all","uptime"): write_uptime()
    print("done:", what)
