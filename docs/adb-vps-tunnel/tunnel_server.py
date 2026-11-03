#!/usr/bin/env python3
"""Reverse tunnel server pentru ADB - ruleaza pe VPS.
Clientul (POCO) mentine o conexiune de control pe 5556 si trimite "READY".
Cand un adb se conecteaza pe 5557, serverul cere clientului o conexiune noua pe 5556,
apoi face pipe intre cele doua.
"""
import socket, threading, queue, time

CTRL_PORT = 5556
PUB_PORT  = 5557
BUF = 65536

pending = queue.Queue()   # conexiuni de date oferite de client
ready_ctrl = {"sock": None, "ts": 0}
lock = threading.Lock()

def pipe(a, b, tag):
    def fwd(src, dst):
        try:
            while True:
                d = src.recv(BUF)
                if not d: break
                dst.sendall(d)
        except Exception:
            pass
        finally:
            try: dst.shutdown(socket.SHUT_WR)
            except Exception: pass
    t = threading.Thread(target=fwd, args=(a, b), daemon=True)
    t.start()
    fwd(b, a)
    t.join(timeout=10)

def ctrl_listener():
    srv = socket.socket(); srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", CTRL_PORT)); srv.listen(8)
    print(f"[ctrl] asculta pe {CTRL_PORT}", flush=True)
    while True:
        c, a = srv.accept()
        def handle(c=c, a=a):
            try:
                hello = c.recv(32)
                if hello.startswith(b"READY"):
                    with lock:
                        old = ready_ctrl["sock"]
                        ready_ctrl["sock"] = c
                        ready_ctrl["ts"] = time.time()
                    if old:
                        try: old.close()
                        except Exception: pass
                    print(f"[ctrl] client pregatit de la {a}", flush=True)
                    # tinem conexiunea deschisa ca sa stim ca e viu
                    while True:
                        d = c.recv(1024)
                        if not d: break
                    with lock:
                        if ready_ctrl["sock"] is c: ready_ctrl["sock"] = None
                    print("[ctrl] client plecat", flush=True)
                elif hello.startswith(b"DATA"):
                    print(f"[data] canal nou de la {a}", flush=True)
                    pending.put(c)
                else:
                    c.close()
            except Exception as e:
                print("[ctrl] err:", e, flush=True)
        threading.Thread(target=handle, daemon=True).start()

def pub_listener():
    srv = socket.socket(); srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", PUB_PORT)); srv.listen(16)
    print(f"[pub] adb poate conecta pe {PUB_PORT}", flush=True)
    while True:
        c, a = srv.accept()
        def handle(c=c, a=a):
            with lock:
                ctrl = ready_ctrl["sock"]
            if not ctrl:
                try: c.sendall(b"NOCTRL\n")
                except Exception: pass
                c.close()
                print(f"[pub] {a} refuzat: niciun client", flush=True)
                return
            try:
                ctrl.sendall(b"NEW\n")
                d = pending.get(timeout=15)
            except Exception as e:
                print(f"[pub] {a}: clientul nu a livrat canal:", e, flush=True)
                c.close(); return
            print(f"[pub] {a} <-> canal activ", flush=True)
            pipe(c, d, "adb")
            print(f"[pub] {a} inchis", flush=True)
        threading.Thread(target=handle, daemon=True).start()

if __name__ == "__main__":
    threading.Thread(target=ctrl_listener, daemon=True).start()
    pub_listener()
