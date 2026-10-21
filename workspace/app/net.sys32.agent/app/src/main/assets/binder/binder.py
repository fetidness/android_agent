#!/usr/bin/env python3
"""binder.py - acces la serviciile Android din Debian, prin /dev/binder.

Clientul nativ `binder` vorbeste direct cu servicemanager (kernel binder).
Acest modul ofera o interfata Python curata.

    from binder import Binder
    b = Binder()
    print(len(b.list()))                  # toate serviciile (468)
    print(b.handle("package"))            # handle binder
    print(b.interface_descriptor("display"))   # android.hardware.display.IDisplayManager
    st, data = b.call("display", 1)       # apel AIDL real

Limitari (SELinux, context shell:s0 ca uid 2000):
  - unele servicii dau EX_SECURITY (media, stats, surfaceflinger)
  - serviciile "lazy" (activity, window) nu pot fi obtinute cu getService
"""
import os
import struct
import subprocess
import shutil

BIN_CANDIDATES = [
    "/root/binder/binder",
    "/usr/local/bin/android-binder",
    "/opt/binder/binder",
]


class BinderError(Exception):
    pass


class Binder:
    def __init__(self, binary=None, timeout=40):
        self.bin = binary or self._find_binary()
        self.timeout = timeout

    @staticmethod
    def _find_binary():
        for p in BIN_CANDIDATES:
            if os.path.isfile(p) and os.access(p, os.X_OK):
                return p
        w = shutil.which("android-binder") or shutil.which("binder")
        if w:
            return w
        raise BinderError("binarul 'binder' lipseste; compileaza debian_binder.c")

    def _run(self, *args, check=True):
        try:
            r = subprocess.run([self.bin, *map(str, args)],
                               capture_output=True, text=True, timeout=self.timeout)
        except subprocess.TimeoutExpired:
            raise BinderError("timeout: %r" % (args,))
        if check and r.returncode != 0:
            raise BinderError(r.stderr.strip() or "eroare")
        return r.stdout

    # ---------------- API de baza ----------------
    def list(self):
        """Toate serviciile Android (echivalent `service list`)."""
        out = self._run("list")
        return [l.split("\t", 1)[1] for l in out.splitlines() if "\t" in l]

    def check(self, name):
        """True daca serviciul raspunde la checkService."""
        return ": found" in self._run("check", name, check=False)

    def handle(self, name):
        """Handle-ul binder local (int). Arunca BinderError daca nu exista."""
        out = self._run("handle", name).strip().splitlines()[0]
        return int(out.split("\t")[1])

    def try_handle(self, name):
        """Ca handle(), dar intoarce None in loc sa arunce."""
        try:
            return self.handle(name)
        except BinderError:
            return None

    def interface_descriptor(self, name):
        """Descriptorul AIDL al serviciului, sau None."""
        out = self._run("iface", name, check=False).strip()
        for line in out.splitlines():
            if line.startswith("descriptor:"):
                return line.split(":", 1)[1].strip()
        return None

    def call(self, name, code, *args, descriptor=None):
        """Apel AIDL generic. Intoarce (status, data).

        Deduce descriptorul automat (cerut de majoritatea serviciilor AIDL).
        status: 0 = succes; negativ = exceptie AIDL.
        """
        if descriptor is None:
            descriptor = self.interface_descriptor(name)
        if descriptor:
            out = self._run("aidlcall", name, descriptor, code, *args, check=False)
        else:
            out = self._run("call", name, code, *args, check=False)
        return self._parse(out)

    def aidlcall(self, name, descriptor, code, *args):
        """Apel cu descriptor explicit (necesar pentru serviciile non-AIDL)."""
        out = self._run("aidlcall", name, descriptor, code, *args, check=False)
        return self._parse(out)

    @staticmethod
    def _parse(out):
        status = None
        data = bytearray()
        for line in out.splitlines():
            if line.startswith("status="):
                v = int(line.split()[0].split("=")[1], 16)
                status = v - 0x100000000 if v >= 0x80000000 else v
            elif len(line) > 5 and line[4] == ":":
                data.extend(int(h, 16) for h in line[5:].split())
        return status, bytes(data)

    # ---------------- utilitare ----------------
    @staticmethod
    def strings(data):
        """Extrage stringurile UTF-16 dintr-un parcel (debug/explorare)."""
        res, i = [], 0
        while i < len(data) - 4:
            try:
                L = struct.unpack_from("<i", data, i)[0]
                if 2 <= L <= 400 and i + 4 + L * 2 <= len(data):
                    t = data[i + 4:i + 4 + L * 2].decode("utf-16-le")
                    if t.isprintable() and len(t) > 2:
                        res.append(t)
                i += 4
            except Exception:
                i += 4
        return res

    @staticmethod
    def ints(data):
        """Primii intregi 32-bit din parcel."""
        n = len(data) // 4
        return list(struct.unpack_from("<%di" % n, data, 0))


if __name__ == "__main__":
    b = Binder()
    svcs = b.list()
    print("servicii: %d" % len(svcs))
    for name in ("display", "input", "package", "power", "mount"):
        h = b.try_handle(name)
        d = b.interface_descriptor(name) if h else None
        print("  %-10s handle=%-4s descriptor=%s" % (name, h, d))
    st, data = b.call("display", 1)
    print("\ndisplay code=1 -> status=%d len=%d" % (st, len(data)))
    for s in b.strings(data)[:6]:
        print("   ", s)
