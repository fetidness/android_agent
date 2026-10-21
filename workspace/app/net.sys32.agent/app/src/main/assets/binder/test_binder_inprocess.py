
"""Test EXTREM de intensiv pentru binder (in-process, agent)."""
import sys, glob, os, time, struct
sys.path.insert(0, "/data/data/net.sys32.agent/files/python")
import agent

def bfds():
    return sorted(int(p.split("/")[-1]) for p in glob.glob("/proc/self/fd/*")
                  if os.path.exists(p) and "binder" in os.readlink(p))

def H(t):
    print("\n" + "="*62); print(t); print("="*62)

R = {"ok":0, "fail":0, "esecuri":[]}
def run(act, par, expect_ok=False):
    r = agent.run_binder_tool(act, par)
    bad = "binder error" in r
    if bad:
        R["fail"] += 1; R["esecuri"].append((act, str(par)[:50], r[:70]))
    else:
        R["ok"] += 1
    return r, bad

fds0 = bfds()
H("0. STARE INITIALA")
print("binder fds:", fds0)
print("modul:", agent._BINDER_MOD[0] is not None, "| client:", agent._BINDER[0] is not None)
t_start = time.time()

H("1. LIST x10")
counts = set()
for i in range(10):
    r, bad = run("list", {})
    if not bad:
        counts.add(r.split("\n")[0])
print("  rezultate distincte:", counts, "| fds:", bfds())

H("2. CHECK pe 30 servicii (reale + false)")
reale = ["display","input","power","package","mount","alarm","clipboard",
         "media.audio_flinger","sensorservice","bluetooth_manager","battery",
         "settings","user","wifi","activity","window","notification","vibrator_manager",
         "telephony.registry","connectivity","appops","dropbox","device_policy","usb",
         "nfc","telephony_ims","media.camera","installd","vold","storaged"]
found = 0
for s in reale:
    r, bad = run("check", {"name": s})
    if "found" in r and "not found" not in r: found += 1
for s in ["zzz_inexistent_1","zzz_inexistent_2","__gol__"]:
    run("check", {"name": s})
print("  gasite: %d/%d + 3 inexistente" % (found, len(reale)))

H("3. HANDLE pe cele 30")
hok = 0
for s in reale:
    r, bad = run("handle", {"name": s})
    if "handle=" in r: hok += 1
print("  handle obtinut: %d/%d" % (hok, len(reale)))

H("4. IFACE pe cele 30")
aidl = []
for s in reale:
    r, bad = run("iface", {"name": s})
    if ":" in r and "(fara" not in r:
        aidl.append((s, r.split(": ",1)[1]))
print("  AIDL: %d/%d" % (len(aidl), len(reale)))
for s,d in aidl: print("    %-22s %s" % (s, d[:55]))

H("5. CALL code=1 pe cele 30")
cat = {"status0":0,"aidl":0,"lazy":0}
for s in reale:
    r, bad = run("call", {"name": s, "code": 1})
    f = r.split("\n")[0]
    if "status=0" in f: cat["status0"] += 1
    elif "status=" in f: cat["aidl"] += 1
    else: cat["lazy"] += 1
print("  ", cat, "| fds:", bfds())

H("6. SCANARE coduri 1-10 pe 5 servicii")
for svc in ["display","input","sensorservice","bluetooth_manager","media.audio_flinger"]:
    line = []
    for c in range(1, 11):
        r, bad = run("call", {"name": svc, "code": c})
        f = r.split("\n")[0]
        st = f.split("status=")[1].split()[0] if "status=" in f else "ERR"
        line.append(st)
    print("  %-20s %s" % (svc, " ".join("%s"%x for x in line)))

H("7. CAZURI LIMITA")
edge = [("check",{"name":""}), ("handle",{"name":""}), ("iface",{"name":""}),
        ("call",{"name":"display","code":0}), ("call",{"name":"display","code":999999}),
        ("call",{"name":"display","code":1,"args":[0]}),
        ("call",{"name":"display","code":1,"args":[1,2,3,4,5,6,7,8,9,10]}),
        ("call",{"name":"display","code":1,"args":[-1]}),
        ("call",{"name":"display","code":1,"args":[2147483647]}),
        ("call",{"name":"zzz_inexistent","code":1}),
        ("iface",{"name":"zzz_inexistent"})]
for a,p in edge:
    r,_ = run(a,p)
    print("  %-6s %-44s -> %s" % (a, str(p)[:44], r.split("\n")[0][:44]))

H("8. ANDURANTA 200 apeluri mixte")
ops=[("call",{"name":"display","code":1}),("call",{"name":"input","code":1}),
     ("iface",{"name":"display"}),("handle",{"name":"package"}),
     ("check",{"name":"display"}),("call",{"name":"sensorservice","code":1})]
f0=bfds(); t0=time.time(); n_ok=0; n_fail=0
for i in range(200):
    a,p = ops[i % len(ops)]
    r,_ = run(a,p)
    if "binder error" in r: n_fail += 1
    else: n_ok += 1
dt=time.time()-t0
print("  ok=%d fail=%d in %.1fs (%.1f ms/op)" % (n_ok,n_fail,dt,dt/200*1000))
print("  fds: %s -> %s" % (f0, bfds()))

H("9. DATE REALE EXTRASE")
r,_ = run("call", {"name":"display","code":1})
for l in r.split("\n"):
    if l.startswith("stringuri:"): print("  display:", l[10:][:130])
r,_ = run("call", {"name":"sensorservice","code":1})
for l in r.split("\n"):
    if l.startswith("stringuri:"): print("  senzori:", l[10:][:130])

H("REZUMAT")
dt=time.time()-t_start
print("  apeluri reusite: %d | esecuri: %d | timp: %.1fs" % (R["ok"], R["fail"], dt))
print("  fds: start=%s final=%s" % (fds0, bfds()))
if R["esecuri"]:
    print("  ESECURI:")
    for e in R["esecuri"][:20]: print("   ", e)
else:
    print("  ZERO esecuri.")
