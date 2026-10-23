#!/usr/bin/env python3
"""android_api - date Android reale in Debian, prin bridge fisiere.
Scrie cererea, ruleaza android_run.py in app, citeste rezultatul.
"""
import json, re, subprocess, sys
from pathlib import Path

BASE = Path("/storage/emulated/0/Download/Agent/workspace")
BR = BASE / "bridge"
PY = sys.executable

def fetch(name, cmd, timeout=90):
    """ruleaza comanda in app si intoarce textul"""
    r = subprocess.run([PY, str(BASE/"android_run.py"), cmd, name],
                       capture_output=True, text=True, timeout=timeout, cwd=str(BASE))
    f = BR / f"{name}.txt"
    return f.read_text() if f.exists() else ""

def location():
    t = fetch("location", "dumpsys location 2>&1 | grep -E 'last location=|provider:' | head -10")
    out = {"providers": {}, "raw": t[:600]}
    for line in t.splitlines():
        if "provider:" in line:
            cur = line.split("provider:")[0].strip()
            out["providers"][cur] = None
        m = re.search(r"last location=Location\[(\w+)\s+(-?[\d.]+),(-?[\d.]+)\s+hAcc=([\d.]+)", line)
        if m:
            out["providers"][cur] = m.group(1)
            if "fix" not in out:
                out["fix"] = {"provider": m.group(1), "lat": float(m.group(2)),
                              "lon": float(m.group(3)), "accuracy_m": float(m.group(4))}
            am = re.search(r"alt=([-\d.]+)", line)
            if am and "fix" in out: out["fix"]["alt_m"] = float(am.group(1))
    return out

def wifi():
    t = fetch("wifi", "dumpsys wifi 2>&1 | grep -E 'mWifiInfo SSID|Wi-Fi is' | head -3")
    d = {"raw": t[:400]}
    m = re.search(r'SSID: "([^"]*)".*?BSSID: ([\w:]+).*?IP: /([\d.]+).*?RSSI: (-?\d+).*?Link speed: (\d+)Mbps.*?Frequency: (\d+)MHz', t)
    if m:
        d.update({"ssid": m.group(1), "bssid": m.group(2), "ip": m.group(3),
                  "rssi": int(m.group(4)), "link_mbps": int(m.group(5)),
                  "freq_mhz": int(m.group(6)), "band": "5GHz" if int(m.group(6)) > 4000 else "2.4GHz"})
    if "Wi-Fi is enabled" in t: d["enabled"] = True
    return d

def telephony():
    t = fetch("telephony", "dumpsys telephony.registry 2>&1 | grep -E 'mCallState|mServiceState|mSignalStrength' | head -6")
    d = {"raw": t[:500]}
    m = re.search(r"mVoiceRegState=(\d)\((\w+)\)", t)
    if m: d.update({"voice_state": int(m.group(1)), "voice_state_name": m.group(2)})
    m = re.search(r"mDataRegState=(\d)\((\w+)\)", t)
    if m: d.update({"data_state": int(m.group(1)), "data_state_name": m.group(2)})
    m = re.search(r"mCallState=(\d)", t)
    if m: d["call_state"] = int(m.group(1))
    return d

def battery():
    t = fetch("battery", "dumpsys battery")
    d = {}
    for l in t.splitlines():
        if ":" in l:
            k,v = l.split(":",1); d[k.strip()] = v.strip()
    return d

def sensors():
    t = fetch("sensors", "dumpsys sensorservice | grep -E '^0x[0-9a-f]+\\)' | head -40")
    out = []
    for line in t.splitlines():
        m = re.match(r"0x([0-9a-f]+)\)\s+(.+?)\s+\|\s+(\S+)\s+\|\s+ver:\s*(\d+)\s+\|\s+type:\s+([\w.]+)\((\d+)\)", line)
        if m: out.append({"name":m.group(2).strip(),"vendor":m.group(3),"type":m.group(5)})
    return {"count": len(out), "sensors": out}

def accel(limit=5):
    t = fetch("accel", f"dumpsys sensorservice | grep -A{limit+1} 'Accelerometer: last'")
    evs=[]
    for line in t.splitlines():
        m = re.search(r"ts=([\d.]+).*?\)\s*(.*)$", line)
        if m and "masked" not in m.group(2):
            vals=[float(x) for x in m.group(2).split(",") if x.strip()]
            if len(vals)==3: evs.append({"ts":float(m.group(1)),"x":vals[0],"y":vals[1],"z":vals[2]})
    return {"events": evs[:limit]}

def services():
    t = fetch("services", "service list")
    out=[]
    for l in t.splitlines():
        m=re.match(r"(\d+)\s+(\S+):", l.strip())
        if m: out.append({"id":int(m.group(1)),"name":m.group(2)})
    return {"count":len(out),"services":out}

ACTIONS = {"location":location,"wifi":wifi,"telephony":telephony,"battery":battery,
           "sensors":sensors,"accel":accel,"services":services}

if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv)>1 else "all"
    if what in ACTIONS:
        print(json.dumps(ACTIONS[what](), indent=1, ensure_ascii=False))
    elif what == "all":
        res={}
        for k,f in ACTIONS.items():
            try: res[k]=f()
            except Exception as e: res[k]={"error":str(e)[:100]}
        print(json.dumps(res, indent=1, ensure_ascii=False))
    else:
        print("usage: android_api.py " + "|".join(list(ACTIONS)+["all"]))
