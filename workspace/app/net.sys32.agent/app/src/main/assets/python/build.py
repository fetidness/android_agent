#!/usr/bin/env python3
"""build.py - compileaza o extensie Python C pe Android, fara setuptools.
Foloseste clang-ul Termux din /data/local/tmp/tpm.

Folosire:
  python build.py <cale_fisier.c> <nume_modul>
Exemplu:
  python build.py src/_speedups.c markupsafe._speedups
"""

import os
import sys
import subprocess

sys.path.insert(0, "/data/user/0/net.sys32.agent/files/python")
_ADC = None

def _sh(cmd, timeout=120):
    """Ruleaza prin adb shell (uid 2000)."""
    global _ADC
    if _ADC is None:
        from adb_client import Adb
        _ADC = Adb(); _ADC.connect()
    return _ADC.shell(cmd, timeout=timeout)


TPM = "/data/local/tmp/tpm/usr"                       # clang + header-e + libs
APP_LIB = ("/data/app/~~EiKG4WRW2l4No1sMw8fAdw==/"
           "net.sys32.agent-ccx5_u8wk-sEPxPW4EMMpg==/lib/arm64")  # libpython
SITE = ("/data/user/0/net.sys32.agent/files/pyhome/lib/python3.14/site-packages")
LIBS = "/data/user/0/net.sys32.agent/files/libs"      # unde linker-ul vede .so
EXT_SUFFIX = ".cpython-314-aarch64-linux-android.so"


def compile_c(c_file, module_name):
    """Compileaza c_file in .so; module_name ex 'pkg.mod' -> pkg/mod<suffix>."""
    out_name = module_name.split(".")[-1] + EXT_SUFFIX
    out_dir = os.path.dirname(c_file) or "."
    out_path = os.path.join(out_dir, out_name)

    # compilarea ruleaza prin adb shell (uid 2000): Python-ul app nu poate exec clang
    cmd = (f"LD_LIBRARY_PATH={TPM}/lib {TPM}/bin/clang -shared -fPIC -O2 "
           f"-o '{out_path}' '{c_file}' "
           f"-I{TPM}/include/python3.14 -I{TPM}/include "
           f"-L{APP_LIB} -lpython3.14 2>&1")
    print("compilare prin shell uid 2000...")
    out = _sh(cmd, timeout=180)
    print(out.strip()[:800])
    if not os.path.exists(out_path):
        print("EROARE: nu s-a produs .so")
        return None
    print("compilat:", out_path, os.path.getsize(out_path), "bytes")
    return out_path


def install(so_path, module_name):
    """Copiaza .so la locul potrivit in site-packages si in libs."""
    parts = module_name.split(".")
    if len(parts) == 1:
        dst_dir = SITE
    else:
        dst_dir = os.path.join(SITE, *parts[:-1])
        os.makedirs(dst_dir, exist_ok=True)
    dst = os.path.join(dst_dir, parts[-1] + EXT_SUFFIX)

    import shutil
    shutil.copy2(so_path, dst)
    # copie si in libs (pentru linker namespace)
    os.makedirs(LIBS, exist_ok=True)
    shutil.copy2(so_path, os.path.join(LIBS, os.path.basename(dst)))
    print("instalat:", dst)
    return dst


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return
    c_file = sys.argv[1]
    module = sys.argv[2]
    if not os.path.exists(c_file):
        print("nu exista:", c_file); return
    so = compile_c(c_file, module)
    if so:
        install(so, module)
        print("\nOK. Testeaza cu: python -c 'import', ".join(["", module.split(".")[0]]))


if __name__ == "__main__":
    main()
