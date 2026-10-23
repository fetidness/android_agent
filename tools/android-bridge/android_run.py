#!/usr/bin/env python3
"""android_run - ruleaza IN APP (uid app), scrie rezultatul in bridge/.
Debian il cheama: python3 android_run.py "<shell cmd>" <name>
"""
import sys, json, os, subprocess
from pathlib import Path

BR = Path("/storage/emulated/0/Download/Agent/workspace/bridge")
BR.mkdir(parents=True, exist_ok=True); os.chmod(BR, 0o777)

def shell(cmd, timeout=40):
    code = ("import sys; sys.path.insert(0,'/data/data/net.sys32.agent/files/python');"
            "import adb_client; print(adb_client.shared().shell(%r))" % cmd)
    p = subprocess.run([sys.executable,"-c",code],capture_output=True,text=True,timeout=timeout)
    return "\n".join(l for l in p.stdout.splitlines() if not l.startswith("[adb]")).strip()

def w(name, txt):
    p = BR / f"{name}.txt"
    p.write_text(txt); os.chmod(p, 0o644)
    return p

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv)>1 else "id"
    name = sys.argv[2] if len(sys.argv)>2 else "out"
    out = shell(cmd)
    p = w(name, out)
    print(f"OK -> {p} ({len(out)} bytes)")
