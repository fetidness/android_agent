# DEBIAN ↔ ANDROID BINDER — ACCES NATIV COMPLET

Data: 2026-10-21
Device: Samsung SM-A366B, Android 16, kernel 6.6.77-android15
Debian: 13 trixie aarch64, proot, rootfs /data/local/tmp/debian

===============================================================================
## REZULTAT: Debian vorbeste NATIV cu orice serviciu Android prin /dev/binder
===============================================================================

```
$ android-binder list | wc -l
468                                   <- identic cu /system/bin/service list

$ android-binder check package
package: found

$ android-binder iface display
status=0x24 len=80
descriptor: android.hardware.display.IDisplayManager

$ android-binder aidlcall display android.hardware.display.IDisplayManager 1
status=0x0 len=1736
  ... android.view.DisplayAddress$Physical
  ... android.hardware.display.DeviceProductInfo  ... QCM ...
```

Din Python:
```python
import binder
b = binder.Binder()
print(len(b.list()))                              # 468
print(b.handle("display"))                        # 1
print(b.interface_descriptor("display"))          # android.hardware.display.IDisplayManager
st, data = b.call("display", 1)                   # status=0, date reale
print(b.strings(data)[:4])
```

===============================================================================
## DE CE MERGE (zidurile reale, masurate)
===============================================================================
OK: /dev/binder se deschide din proot -> fd valid
OK: mmap(4096, PROT_READ, MAP_SHARED) -> OK
OK: ioctl BINDER_VERSION -> version 8
OK: BINDER_WRITE_READ complet functional
OK: servicemanager raspunde (pid 1000)
NICIODATA binarul Android (bctl) - nu are libc Android, deci NU se poate
  executa din Debian ("required file not found"). Trebuie compilat NATIV
  glibc cu gcc-ul din Debian.

LIMITARI SELinux (context shell:s0, uid 2000):
  EX_SECURITY pe: media.*, stats, surfaceflinger, connectivity
  Serviciile "lazy" (activity, window, notification, SurfaceFlingerAIDL)
  NU pot fi obtinute cu getService - intorc ENOENT (null).
  getService merge pe: package, power, display, input, mount, alarm,
  clipboard, battery, device_policy, dropbox, bluetooth_manager...

===============================================================================
## INSTALARE (deja facuta pe acest device)
===============================================================================
```
/opt/android-binder/android-binder        binar nativ glibc
/opt/android-binder/binder.py             modul Python
/opt/android-binder/debian_binder.c       sursa
/usr/local/bin/android-binder             symlink -> binar
<bilsitepackages>/binder.py               modul importabil global
```

Recompilare dupa modificari:
```
cp /sdcard/Download/Agent/workspace/debian_binder.c /root/binder/
cd /root/binder && gcc -O2 -o binder debian_binder.c
cp binder /opt/android-binder/android-binder
```

===============================================================================
## COMENZI
===============================================================================
```
android-binder list                        toate serviciile (468)
android-binder check <name>                exista?
android-binder handle <name>               handle-ul binder (int)
android-binder iface <name>                descriptorul AIDL
android-binder desc <name>                 (idem, varianta veche)
android-binder call <name> <code> [i32..]  apel generic
android-binder aidlcall <name> <desc> <code> [i32..]   apel cu descriptor
android-binder rawcall <handle> <code> [i32..]
```

===============================================================================
## PROTOCOLUL (toate offseturile verificate prin ptrace pe libbinder)
===============================================================================

### PARCEL AIDL (96 bytes pentru checkService)
```
off  0 : 0x80000000   strict policy
off  4 : 0xFFFFFFFF
off  8 : 0x53595354   'TSYS'
off 12 : len(descriptor)
off 16 : UTF-16 descriptor + 4 B padding
off 72 : int32 len(arg)  (String16)
off 76 : UTF-16 arg + padding
```

### TRANZACTIE (binder_transaction_data, 64 B)
```
off  0 : target.handle  u32
off 16 : code           u32      <- NU 12
off 20 : flags          u32      <- 0x10 (TF_ACCEPT_FDS) OBLIGATORIU
off 32 : data_size      u64      <- NU 20
off 40 : offsets_size   u64
off 48 : data.ptr       u64
off 56 : data.offsets.ptr u64
```

### REPLY (76 bytes)
```
off  0 : 0x720c BR_NOOP
off  4 : 0x7206 BR_REPLY
off  8 : 0x80407203 (header separat)
off 12 : binder_transaction_data
         off 40 : sender_pid  u32    = 1000
         off 44 : data_size   u64
         off 52 : offsets_size u64
         off 60 : data.ptr     u64   in zona mmap
         off 68 : offsets.ptr  u64
```

### SECVENTA OBLIGATORIE INAINTE DE PRIMUL APEL
```
1. BC_TRANSACTION getService (handle 0)
2. BC_ACQUIRE  (0x40046304) + u32 handle
3. BC_INCREFS  (0x40046305) + u32 handle
4. BC_FREE_BUFFER (0x40086303) + u64 dptr   <- DUPA acquire/increfs!
5. INTERFACE_TRANSACTION (0x5f4e5446) pe handle
6. apelul real
```
Daca FREE_BUFFER se face INAINTE de ACQUIRE/INCREFS -> NU mai vine niciun
reply (doar BR_TRANSACTION_COMPLETE, apoi timeout).

### OPȚIONAL: obtine handle-ul
`getService` intoarce un parcel cu `flat_binder_object` la offsetul dat de
`offsets_buffer[0]`; handle-ul e la `obiect + 8` (u32).

### VECTORUL String16 din listServices
```
off 0 : int32 (0)
off 4 : int32 count (468)
off 8+: elemente: int32 len + UTF-16
        padding dupa fiecare element: la multiplu de 4, dar STRICT mai mare
        daca e deja aliniat (dedus din 468 elemente reale)
```

===============================================================================
## CAPCANE (toate dovedite)
===============================================================================
TRAP: binarul Android (bctl) NU ruleaza din Debian -> compileaza nativ glibc.
TRAP: setgid INAINTE de setuid, altfel EPERM (proot).
TRAP: proot da uid 0; SELinux ramane shell:s0 -> trebuie setuid(2000).
TRAP: getService NU elibereaza singur buffer-ul; ordinea ACQUIRE/INCREFS/FREE
      conteaza (vezi mai sus).
TRAP: serviciile AIDL cer descriptorul in parcel, altfel "Binder invocation
      to an incorrect interface" (status -1).
TRAP: descriptorii NU se ghiceste - obtine-i cu `android-binder iface <name>`.
      Exemplu: serviciul "mount" are descriptorul
      android.os.storage.IStorageManager (NU IMountService).
TRAP: serviciile lazy (activity, window) intorc ENOENT la getService.
TRAP: mmap pe /dev/binder accepta pana la 1 MB (nu doar 4096).
TRAP: proces_vm_readv din shell:s0 -> EPERM; pentru tracing foloseste
      PTRACE_PEEKDATA.

===============================================================================
## FISIERE
===============================================================================
P: /storage/emulated/0/Download/Agent/workspace/debian_binder.c   sursa C
P: /storage/emulated/0/Download/Agent/workspace/binder.py         modul Python
P: /storage/emulated/0/Download/Agent/workspace/bctl              client Android
P: /data/data/net.sys32.agent/files/tmp/binder_final.c            client Android src
P: /opt/android-binder/                                           instalare Debian
