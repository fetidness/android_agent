
import time,threading,json,sys,os,platform
def work(n):
    s=0
    for i in range(n): s+=i*i%7
    return s
def run(n,per=2_000_000):
    ths=[threading.Thread(target=work,args=(per,)) for _ in range(n)]
    s=time.perf_counter(); [t.start() for t in ths]; [t.join() for t in ths]
    return time.perf_counter()-s
R={}
for n in (1,2,4,8):
    R[f"thr{n}"]=round(min(run(n) for _ in range(2)),3)
# subprocess spawn cost
import subprocess
s=time.perf_counter()
for _ in range(30): subprocess.run(["/bin/echo","x"],stdout=subprocess.DEVNULL)
R["spawn30"]=round(time.perf_counter()-s,3)
R["ver"]=sys.version.split()[0]
print("THR "+json.dumps(R))
