#!/usr/bin/env python3
"""Sets the EXECUTE bit on every real ELF binary under a prefix, and read-bits on libraries.

Why this exists (numpy referat, P2): Termux .deb members are extracted with mode -rw-rw-r--,
so binaries arrive WITHOUT the execute bit. `chmod -R a+rX` does NOT fix it (X only adds exec
where some exec bit already exists), so clang/python/samu die with "Permission denied" (RC=126)
and every build fails with no useful message.

Run:  python3 setexec.py /data/local/tmp/tpm/usr
It walks bin/, lib/, libexec/ and the python lib-dynload, and for each regular file:
  - ELF (magic \x7fELF) -> 0755  (needs exec)
  - anything else        -> 0644  (data/lib: read is enough, no exec noise)
Symlinks are followed, never rewritten (they belong to the symlink pass).
"""
import os, sys

def is_elf(path):
    try:
        with open(path, "rb") as f:
            return f.read(4) == b"\x7fELF"
    except Exception:
        return False

def main(prefix):
    n_elf = n_data = 0
    roots = [os.path.join(prefix, d) for d in ("bin", "lib", "libexec")]
    # python lib-dynload (modulele .so ale stdlib-ului)
    libpy = os.path.join(prefix, "lib")
    if os.path.isdir(libpy):
        for name in os.listdir(libpy):
            if name.startswith("python3"):
                roots.append(os.path.join(libpy, name, "lib-dynload"))
    for root in roots:
        if not os.path.isdir(root):
            continue
        for dirpath, _, files in os.walk(root):
            for fn in files:
                fp = os.path.join(dirpath, fn)
                if os.path.islink(fp):
                    continue
                try:
                    if is_elf(fp):
                        os.chmod(fp, 0o755); n_elf += 1
                    else:
                        os.chmod(fp, 0o644); n_data += 1
                except Exception:
                    pass
    print("SETEXEC_OK elf=%d data=%d" % (n_elf, n_data))
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "/data/local/tmp/tpm/usr"))
