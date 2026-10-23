
import time,os,sys,json,hashlib,random,socket,subprocess,resource,threading
R={}
def t(name,fn,rep=1):
    fn() # warmup
    best=1e9
    for _ in range(rep):
        s=time.perf_counter(); fn(); best=min(best,time.perf_counter()-s)
    R[name]=round(best,4)
    return best

def cpu_int():
    s=0
    for i in range(3_000_000): s+=i*i%7
    return s
def cpu_float():
    s=0.0
    for i in range(2_000_000): s+= (i*0.5)**0.5
    return s
def str_ops():
    d={}
    for i in range(400_000):
        k=str(i%5000); d[k]=d.get(k,0)+1
    return len(d)
def sortbig():
    random.seed(1); a=[random.random() for _ in range(1_500_000)]
    a.sort(); return a[0]
def hashsha():
    data=os.urandom(4_000_000)
    for _ in range(3): hashlib.sha256(data).hexdigest()
def jsonrt():
    o=[{"k":i,"v":"x"*40} for i in range(150_000)]
    s=json.dumps(o); json.loads(s); return len(s)
def byteswork():
    b=b"\x01\x02\x03\x04"*2_000_000
    return b.count(b"\x04")

t("cpu_int_3M",cpu_int,3)
t("cpu_float_2M",cpu_float,3)
t("str_counter_400k",str_ops,3)
t("sort_1.5M",sortbig,3)
t("sha256_12MB",hashsha,3)
t("json_150k_roundtrip",jsonrt,3)
t("bytes_count_8MB",byteswork,3)

# ---- IO: write / read
def io_write():
    p=os.path.join(os.environ.get("BENCH_TMP","/tmp"),"bench_io.bin")
    with open(p,"wb") as f:
        blk=os.urandom(1<<20)
        for _ in range(64): f.write(blk)
    os.unlink(p)
def io_read():
    p=os.path.join(os.environ.get("BENCH_TMP","/tmp"),"bench_rd.bin")
    blk=os.urandom(1<<20)
    with open(p,"wb") as f:
        for _ in range(64): f.write(blk)
    s=0
    with open(p,"rb") as f:
        while True:
            c=f.read(1<<16)
            if not c: break
            s+=len(c)
    os.unlink(p); return s
import tempfile
os.environ.setdefault("BENCH_TMP", tempfile.gettempdir())
t("io_write_64MB",io_write,2)
t("io_read_64MB",io_read,2)

# ---- thread scaling
def thr_work(n):
    s=0
    for i in range(n): s+=i*i
    return s
def threads(n):
    ths=[threading.Thread(target=thr_work,args=(700_000,)) for _ in range(n)]
    s=time.perf_counter()
    [x.start() for x in ths]; [x.join() for x in ths]
    return time.perf_counter()-s
R["thread_1x"]=round(threads(1),4)
R["thread_8x"]=round(threads(8),4)

# ---- socket/syscall latency
def socks():
    a,b=socket.socketpair()
    for _ in range(20000):
        a.send(b"x"); b.recv(1)
    a.close(); b.close()
t("socketpair_20k",socks,2)

def getpid_lat():
    for _ in range(200_000): os.getpid()
t("getpid_200k",getpid_lat,2)

def fork_exec():
    for _ in range(20):
        subprocess.run(["/bin/echo","x"],stdout=subprocess.DEVNULL)
t("fork_exec_20",fork_exec,2)

R["py_version"]=sys.version.split()[0]
R["platform"]=sys.platform
R["uid"]=os.getuid()
R["cpus"]=os.cpu_count()
print("BENCH_RESULT "+json.dumps(R))
