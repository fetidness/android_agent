"""android_binder.py - acces Binder nativ din procesul APLICATIEI (fara adb, fara bridge).

Deschide /dev/binder direct, ca orice proces Android, si vorbeste cu servicemanager.
Functioneaza din contextul aplicatiei (u:r:untrusted_app) si din shell (u:r:shell:s0).

    from android_binder import Binder
    b = Binder()
    b.list()                       # toate serviciile (468)
    b.handle("package")            # handle binder
    b.iface("display")             # android.hardware.display.IDisplayManager
    st, data = b.call("display", 1)
"""
import os
import time
import ctypes
import struct
import fcntl
import mmap

BINDER_WRITE_READ = 0xc0306201
BC_TRANSACTION    = 0x40406300
BC_FREE_BUFFER    = 0x40086303
BC_ACQUIRE        = 0x40046304
BC_INCREFS        = 0x40046305
BC_ENTER_LOOPER   = 0x630c
BR_NOOP           = 0x720c
BR_REPLY          = 0x7206
BR_TRANSACTION_COMPLETE = 0x7211
TF_ACCEPT_FDS     = 0x10
INTERFACE_TRANSACTION = 0x5f4e5446
DUMP_PRIORITY_ALL = 0x0F


class BinderError(Exception):
    pass


class Binder:
    """Client Binder in-process. `mmap` pana la 1 MB, non-blocking."""

    # ★ NICIODATA nu inchide fd-uri binder care nu iti apartin: procesul
    # aplicatiei are propriul binder (folosit de runtime-ul Android) si daca
    # il inchizi aplicatia ramane intr-o stare instabila pana la restart.

    # fd-urile deschise de ACEST modul (ca sa nu atingem binder-ul aplicatiei)
    _MY_FDS = set()

    def __init__(self, dev="/dev/binder", rdbuf=262144, cleanup=True):
        # ★ NU inchidem fd-uri ale altor instante: mmap-ul lor poate fi inca in
        # uz, iar procesul aplicatiei are propriul binder (runtime Android).
        # Un singur client se pastreaza viu (vezi _binder_client din agent.py).
        self.fd = os.open(dev, os.O_RDWR)
        Binder._MY_FDS.add(self.fd)
        fcntl.fcntl(self.fd, fcntl.F_SETFL,
                    fcntl.fcntl(self.fd, fcntl.F_GETFL) | os.O_NONBLOCK)
        self.mapsz = 0
        for sz in (1048576, 262144, 65536, 4096):
            try:
                self.mm = mmap.mmap(self.fd, sz, mmap.MAP_SHARED, mmap.PROT_READ)
                self.mapsz = sz
                break
            except OSError:
                continue
        if not self.mapsz:
            raise BinderError("mmap pe /dev/binder a esuat")
        self.mapaddr = 0
        for line in open("/proc/self/maps"):
            if "binder" in line:
                self.mapaddr = int(line.split("-")[0], 16)
                break
        self._rd = ctypes.create_string_buffer(rdbuf)
        self.rdbuf = rdbuf
        self._rdaddr = ctypes.addressof(self._rd)
        self._keep = []
        self.last_dptr = 0
        for _ in range(8):                       # golim coada de la open
            ok, c = self._bwr(None)
            if ok < 0 or not c:
                break
        self._cmd(BC_ENTER_LOOPER)

    # ---------- primitivе ----------
    def _bwr(self, wbuf, rsz=None):
        rsz = self.rdbuf if rsz is None else rsz
        if wbuf:
            k = ctypes.create_string_buffer(bytes(wbuf), len(wbuf))
            self._keep.append(k)      # NU eliberam: kernelul poate inca citi
            wp, ws = ctypes.addressof(k), len(wbuf)
        else:
            wp, ws = 0, 0
        st = struct.pack("<6Q", ws, 0, wp, rsz, 0, self._rdaddr if rsz else 0)
        buf = ctypes.create_string_buffer(st, 48)
        try:
            fcntl.ioctl(self.fd, BINDER_WRITE_READ, buf, True)
        except OSError as e:
            self._last_errno = e.errno
            if e.errno in (11, 35):        # EAGAIN / EWOULDBLOCK: nimic de citit inca
                return 0, 0
            return -1, 0
        return 0, struct.unpack_from("<Q", buf.raw, 32)[0]

    def _cmd(self, cmd, arg=b""):
        return self._bwr(struct.pack("<I", cmd) + bytes(arg))

    # ---------- parcel ----------
    @staticmethod
    def parcel(desc, arg=None):
        o = bytearray()
        o += struct.pack("<I", 0x80000000)
        o += struct.pack("<I", 0xFFFFFFFF)
        o += struct.pack("<I", 0x53595354)          # 'TSYS'
        o += struct.pack("<I", len(desc))
        for ch in desc:
            o += struct.pack("<H", ord(ch))
        o += b"\x00" * 4                            # padding dupa descriptor
        if arg is not None:
            o += struct.pack("<I", len(arg))
            for ch in arg:
                o += struct.pack("<H", ord(ch))
            while len(o) % 4:
                o += b"\x00"
        return bytes(o)

    # ---------- tranzactie ----------
    def transact(self, handle, code, data=b"", do_free=True, timeout_s=8.0):
        """Trimite o tranzactie si intoarce (pid, data, offsets) din BR_REPLY.

        Reply-ul are 76 de octeti, cu offseturi VERIFICATE prin ptrace:
          off 0 : 0x720c BR_NOOP
          off 4 : 0x7206 BR_REPLY
          off 8 : 0x80407203 (header de comanda)
          off 12: binder_transaction_data
          pid@40  data_size@44  offsets_size@52  data.ptr@60  offsets.ptr@68
        """
        pkt = struct.pack("<I", BC_TRANSACTION)
        t = bytearray(64)
        struct.pack_into("<I", t, 0, handle)
        struct.pack_into("<I", t, 16, code)
        struct.pack_into("<I", t, 20, TF_ACCEPT_FDS)
        struct.pack_into("<Q", t, 32, len(data) if data else 0)
        if data:
            k = ctypes.create_string_buffer(bytes(data), len(data))
            self._keep.append(k)
            struct.pack_into("<Q", t, 48, ctypes.addressof(k))

        ok, rc = self._bwr(pkt + bytes(t))
        if ok < 0:
            raise BinderError("send esuat (errno=%s)" % getattr(self, "_last_errno", "?"))

        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if not rc:
                ok, rc = self._bwr(None)
                if ok < 0:
                    raise BinderError("read esuat (errno=%s)" % getattr(self, "_last_errno", "?"))
            if not rc:
                time.sleep(0.002)
                continue
            used, rc = rc, 0
            buf = self._rd.raw[:used]

            # cauta BR_REPLY in buffer (inaintea lui pot veni NOOP/COMPLETE)
            pos = 0
            while pos + 4 <= used:
                w, = struct.unpack_from("<I", buf, pos)
                if w in (BR_NOOP, BR_TRANSACTION_COMPLETE):
                    pos += 4
                    continue
                break
            if used < 76:
                continue                      # inca nu e reply complet
            w, = struct.unpack_from("<I", buf, pos)
            if (w & 0xFFFF) != BR_REPLY:
                continue

            # offseturi ABSOLUTE in buffer (verificate prin ptrace pe libbinder)
            pid, = struct.unpack_from("<I", buf, 40)
            dsz, = struct.unpack_from("<Q", buf, 44)
            osz, = struct.unpack_from("<Q", buf, 52)
            dptr, = struct.unpack_from("<Q", buf, 60)
            optr, = struct.unpack_from("<Q", buf, 68)
            self.last_dptr = dptr
            d = b""
            offs = b""
            if dsz and self.mapaddr <= dptr and dptr + dsz <= self.mapaddr + self.mapsz:
                d = self.mm[dptr - self.mapaddr:dptr - self.mapaddr + dsz]
            if osz and self.mapaddr <= optr and optr + osz <= self.mapaddr + self.mapsz:
                offs = self.mm[optr - self.mapaddr:optr - self.mapaddr + osz]
            if do_free:
                self._cmd(BC_FREE_BUFFER, struct.pack("<Q", dptr))
                self.last_dptr = 0
            return pid, d, offs
        raise BinderError("timeout la tranzactie")

    # ---------- API servicemanager ----------
    def list(self):
        pl = self.parcel("android.os.IServiceManager") + struct.pack("<I", DUMP_PRIORITY_ALL)
        r = self.transact(0, 6, pl)
        if not r:
            raise BinderError("listServices fara raspuns")
        pid, d, offs = r
        if len(d) < 8:
            raise BinderError("reply prea mic")
        st, = struct.unpack_from("<i", d, 0)
        if st != 0:
            raise BinderError("listServices status=0x%x" % (st & 0xffffffff))
        cnt, = struct.unpack_from("<I", d, 4)
        out = []
        o = 8
        for _ in range(cnt):
            if o + 4 > len(d):
                break
            L, = struct.unpack_from("<i", d, o)
            o += 4
            if L < 0 or o + L * 2 > len(d):
                break
            out.append(d[o:o + L * 2].decode("utf-16-le", "replace"))
            o += L * 2
            o = (o + 3) & ~3 if (o & 3) else o + 4      # padding AIDL (dovedit)
        return out

    def check(self, name):
        pl = self.parcel("android.os.IServiceManager", name)
        r = self.transact(0, 3, pl)
        if not r:
            return False
        pid, d, offs = r
        if len(d) < 4:
            return False
        st, = struct.unpack_from("<i", d, 0)
        # serviciu inexistent: status 0 dar FARA obiect binder (offsets_size=0)
        return st == 0 and len(offs) >= 4

    def handle(self, name):
        pl = self.parcel("android.os.IServiceManager", name)
        r = self.transact(0, 1, pl, do_free=False)   # eliberat in _prepare()
        if not r:
            return None
        pid, d, offs = r
        if len(d) < 8:
            return None
        st, = struct.unpack_from("<i", d, 0)
        if st != 0 or len(offs) < 4:
            return None                     # null: inexistent sau lazy
        off0, = struct.unpack_from("<I", offs, 0)
        if off0 + 12 > len(d):
            return None
        return struct.unpack_from("<I", d, off0 + 8)[0]

    def _prepare(self, h):
        self._cmd(BC_ACQUIRE, struct.pack("<I", h))
        self._cmd(BC_INCREFS, struct.pack("<I", h))
        if self.last_dptr:
            self._cmd(BC_FREE_BUFFER, struct.pack("<Q", self.last_dptr))
            self.last_dptr = 0

    def iface(self, name):
        h = self.handle(name)
        if h is None:
            return None
        self._prepare(h)
        r = self.transact(h, INTERFACE_TRANSACTION)
        if not r:
            return None
        pid, d, offs = r
        if len(d) >= 4:
            L, = struct.unpack_from("<i", d, 0)
            if 0 < L < 512 and 4 + L * 2 <= len(d):
                return d[4:4 + L * 2].decode("utf-16-le", "replace")
        return None

    def call(self, name, code, descriptor=None, *args):
        h = self.handle(name)
        if h is None:
            raise BinderError("serviciul '%s' nu poate fi obtinut" % name)
        if descriptor is None:
            self._prepare(h)
            r = self.transact(h, INTERFACE_TRANSACTION)
            descriptor = ""
            if r:
                d = r[1]
                if len(d) >= 4:
                    L, = struct.unpack_from("<i", d, 0)
                    if 0 < L < 512 and 4 + L * 2 <= len(d):
                        descriptor = d[4:4 + L * 2].decode("utf-16-le", "replace")
        self._prepare(h)
        pl = self.parcel(descriptor) if descriptor else b""
        for a in args:
            pl += struct.pack("<I", a & 0xffffffff)
        r = self.transact(h, code, pl)
        if not r:
            raise BinderError("fara raspuns")
        pid, d, offs = r
        st = struct.unpack_from("<i", d, 0)[0] if len(d) >= 4 else None
        return st, d

    def close(self):
        try:
            os.close(self.fd)
        except OSError:
            pass
        Binder._MY_FDS.discard(self.fd)


def strings(data):
    """Stringuri UTF-16 dintr-un parcel (debug)."""
    res, i = [], 0
    while i < len(data) - 4:
        try:
            L, = struct.unpack_from("<i", data, i)
            if 2 <= L <= 400 and i + 4 + L * 2 <= len(data):
                t = data[i + 4:i + 4 + L * 2].decode("utf-16-le")
                if t.isprintable() and len(t) > 2:
                    res.append(t)
        except Exception:
            pass
        i += 4
    return res


if __name__ == "__main__":
    b = Binder()
    svcs = b.list()
    print("servicii:", len(svcs))
    for n in ("package", "display", "input", "power"):
        print("  %-9s handle=%-4s iface=%s" % (n, b.handle(n), b.iface(n)))
    st, d = b.call("display", 1)
    print("display code=1 -> status=%s len=%d" % (st, len(d)))
    print("  ", strings(d)[:4])
