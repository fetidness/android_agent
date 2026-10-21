
"""Test EXTREM de intensiv pentru binder din DEBIAN."""
import sys, os, subprocess, time

BIN = "/opt/android-binder/android-binder"
R = {"ok":0, "fail":0, "esecuri":[]}

def sh(*args, timeout=30):
    r = subprocess.run([BIN, *map(str,args)], capture_output=True, text=True, timeout=timeout)
    return r.stdout, r.stderr, r.returncode

def H(t):
    print("\n" + "="*60); print(t); print("="*60)

t_start = time.time()

H("0. BINAR")
print("  cale:", BIN, "| exista:", os.path.exists(BIN))
print("  exec:", subprocess.run(["id","-u"],capture_output=True,text=True).stdout.strip())

H("1. LIST x10")
counts=set()
for i in range(10):
    o,e,rc = sh("list")
    if rc==0: counts.add(len(o.strip().split("\n")))
    else: R["fail"]+=1; R["esecuri"].append(("list",e[:60]))
print("  numar servicii (distincte):", counts)

H("2. CHECK pe 30 servicii")
reale = ["display","input","power","package","mount","alarm","clipboard",
         "media.audio_flinger","sensorservice","bluetooth_manager","battery",
         "settings","user","wifi","activity","window","notification","vibrator_manager",
         "telephony.registry","connectivity","appops","dropbox","device_policy","usb",
         "nfc","telephony_ims","media.camera","installd","vold","storaged"]
found=0
for s in reale:
    o,e,rc = sh("check", s)
    if "found" in o and "not found" not in o: found+=1
    if rc!=0: R["fail"]+=1
for s in ["zzz_inexistent_1","zzz_inexistent_2"]: sh("check", s)
print("  gasite: %d/%d" % (found, len(reale)))

H("3. HANDLE pe cele 30")
hok=0
for s in reale:
    o,e,rc = sh("handle", s)
    if "\t" in o: hok+=1
print("  handle obtinut: %d/%d" % (hok, len(reale)))

H("4. IFACE pe cele 30")
aidl=[]
for s in reale:
    o,e,rc = sh("iface", s)
    if "descriptor:" in o:
        aidl.append((s, o.split("descriptor:")[1].strip()))
print("  AIDL: %d/%d" % (len(aidl), len(reale)))
for s,d in aidl: print("    %-22s %s" % (s, d[:55]))

H("5. CALL code=1 pe cele 30")
cat={"status0":0,"aidl":0,"lazy":0}
for s in reale:
    o,e,rc = sh("aidlcall", s, "x", 1)
    if "status=0x0" in o: cat["status0"]+=1
    elif "status=" in o: cat["aidl"]+=1
    else: cat["lazy"]+=1
print("  ", cat)

H("6. SCANARE coduri 1-10 pe 5 servicii")
for svc in ["display","input","sensorservice","bluetooth_manager"]:
    o,e,rc = sh("iface", svc)
    desc = o.split("descriptor:")[1].strip() if "descriptor:" in o else ""
    if not desc:
        print("  %-20s (fara descriptor)" % svc); continue
    line=[]
    for c in range(1,11):
        o2,_,_ = sh("aidlcall", svc, desc, c)
        st = o2.split("status=")[1].split()[0] if "status=" in o2 else "ERR"
        line.append(st)
    print("  %-20s %s" % (svc, " ".join(line)))

H("7. ANDURANTA 200 apeluri")
t0=time.time(); ok=0; fail=0
for i in range(200):
    o,e,rc = sh("aidlcall","display","android.hardware.display.IDisplayManager",1)
    if rc==0 and "status=0x0" in o: ok+=1
    else: fail+=1
    if fail and fail<4: print("   esec",i,e[:60])
dt=time.time()-t0
print("  ok=%d fail=%d in %.1fs (%.1f ms/op)" % (ok,fail,dt,dt/200*1000))

H("8. DATE REALE")
o,e,rc = sh("aidlcall","display","android.hardware.display.IDisplayManager",1)
print("  display:", o.split("\n")[0] if o else e[:60])
o,e,rc = sh("iface","sensorservice")
print("  sensorservice:", o.split("descriptor:")[1].strip() if "descriptor:" in o else "-")

H("REZUMAT")
print("  timp total: %.1fs | esecuri: %d" % (time.time()-t_start, R["fail"]))
if R["esecuri"]: print("  ", R["esecuri"][:10])
else: print("  ZERO esecuri.")
