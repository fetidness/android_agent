
import time,hashlib,os
# sustained 10s workload, report throughput per second bucket -> detects throttling
data=os.urandom(1<<20)
start=time.time(); buckets=[]
end=start+10; last=start; n=0
while time.time()<end:
    hashlib.sha256(data).digest(); n+=1
    now=time.time()
    if now-last>=1.0:
        buckets.append(round(n/(now-last),1)); n=0; last=now
print("SUSTAIN_THROUGHPUT_MBps", buckets)
