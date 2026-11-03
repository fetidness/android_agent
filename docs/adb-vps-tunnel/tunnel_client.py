#!/usr/bin/env python3
"""Client tunel - ruleaza PE POCO (in procesul agentului).
Mentine o conexiune de control catre VPS si, la cerere, deschide canale
catre localhost:5555 (adbd-ul propriu).
"""
import socket, threading, sys, time

VPS_HOST = sys.argv[1] if len(sys.argv) > 1 else "sys32.net"
VPS_PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 5556
ADB_HOST, ADB_PORT = "127.0.0.1", 5555
BUF = 65536

def pipe(a, b):
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

def serve_data(data_sock):
    """Deschide conexiune catre adbd local si face pipe."""
    try:
        adb = socket.create_connection((ADB_HOST, ADB_PORT), timeout=10)
        print("[data] conectat la adbd local", flush=True)
        pipe(data_sock, adb)
    except Exception as e:
        print("[data] nu pot ajunge la adbd:", e, flush=True)
    finally:
        try: data_sock.close()
        except Exception: pass

def control_loop():
    while True:
        try:
            ctrl = socket.create_connection((VPS_HOST, VPS_PORT), timeout=20)
            ctrl.sendall(b"READY\n")
            print(f"[ctrl] conectat la {VPS_HOST}:{VPS_PORT}", flush=True)
            ctrl.settimeout(None)
            while True:
                cmd = ctrl.recv(64)
                if not cmd:
                    print("[ctrl] server a inchis", flush=True)
                    break
                if b"NEW" in cmd:
                    d = socket.create_connection((VPS_HOST, VPS_PORT), timeout=20)
                    d.sendall(b"DATA\n")
                    threading.Thread(target=serve_data, args=(d,), daemon=True).start()
                    print("[ctrl] canal de date deschis", flush=True)
        except Exception as e:
            print(f"[ctrl] eroare: {e} - reincerc in 10s", flush=True)
        time.sleep(10)

if __name__ == "__main__":
    print(f"[start] POCO -> {VPS_HOST}:{VPS_PORT}, adbd local {ADB_HOST}:{ADB_PORT}", flush=True)
    control_loop()
