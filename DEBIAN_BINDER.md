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
## MASURATOARE COMPLETA (2026-10-21, dupa corectarea interpretarii)
===============================================================================

Un raport anterior al agentului mobil concluziona gresit "0 din 25 servicii
accesibile din Debian -> binder-ul nu merge". Cauza: esantionul ales continea
exact serviciile care NU pot raspunde (lazy + restrictionate SELinux), iar
handle-ul era citit din offset greșit (0x80000001 confundat cu null).

Masuratoare exhaustiva (`android-binder selftest`, toate serviciile):

```
context SELinux    : u:r:shell:s0
servicii listate   : 469
getService REUSIT  : 213     <- servicii la care ai acces REAL
lazy / ENOENT      : 3       <- inregistrate la cerere, NU eroare de binder
refuzate SELinux   : 253     <- politici per domeniu
alte erori         : 0
CONCLUZIE: binder-ul FUNCTIONEAZA din acest context; 213 servicii accesibile.
```

Exemple care merg din Debian (descriptor AIDL citit cap-coada):
```
package        -> android.content.pm.IPackageManager
power          -> android.os.IPowerManager
display        -> android.hardware.display.IDisplayManager   (status=0x22)
```

===============================================================================
## REGULI DE INTERPRETARE (ca sa nu se repete eroarea)
===============================================================================

RULE: un esec pe UN serviciu NU dovedeste ca binder-ul nu merge.
      1) verifica `android-binder selftest` (toate serviciile, numaratoare)
      2) verifica `android-binder iface <nume>` pe un serviciu de baza (package/power)
      3) abia apoi trage concluzii

TRAP: `activity`, `window`, `notification`, `media.*`, `stats`, `surfaceflinger`,
      `connectivity`, `battery` NU raspund din `shell:s0`:
      - lazy -> ENOENT (0xfffffffc): normal, se creeaza la primul client din alt proces
      - SELinux -> EX_SECURITY (0xfffffffe): politica per domeniu
      Un eșantion format din acestea da 0/N si indeparteaza atentia de la realitate.

TRAP: handle-ul din `flat_binder_object` e u32 la offset 8 in obiect, NU contine
      bit de semn. handle=1 pentru majoritatea serviciilor de sistem.
      `0x80000001` este valoarea de STATUS "null" din parcel, nu un handle.

TRAP: `listServices` cere DUMP_PRIORITY_ALL (u32 dupa descriptor) si raspunde cu
      count la offset 4, elementele incep la offset 8. Un nume poate avea
      pana la 70+ caractere (nu 64) - bufferul trebuie >=256.

TRAP: `android-binder check` care zice "not found" e SERVICIUL lazy, nu lipsa
      binder-ului. Mesajul comenzii spune asta explicit acum.

===============================================================================
## COMENZI NOI
===============================================================================
```
android-binder selftest          numara: accesibile / lazy / refuzate SELinux,
                                 cu CONCLUZIE explicita (nu mai lasa loc de gresit)
android-binder iface <nume>      descriptorul AIDL (nu cere semnatura speciala)
```

## UNDE STA BINARUL (dupa setup-ul automat, 2026-10-21)
===============================================================================
```
/data/local/tmp/debian                          rootfs-ul REAL (executabil;
                                                files/debian NU poate fi executat)
/data/local/tmp/proot_exec.so                   proot copiat executabil
/data/local/tmp/binder/                         sursa clientului (din assets/binder)
/opt/android-binder/android-binder              binarul compilat
/usr/local/bin/android-binder  (in guest)       symlink -> binar
files/.debian_ready                             flag: setup complet

DE CE: aplicatia (uid 10xxx) nu poate execve din app_data_file (W^X SELinux) si
nu poate scrie in /data/local/tmp -> setup-ul se face de adbd (uid 2000) la prima
deschidere a terminalului. Detalii in readme.md -> "SETUP AUTOMAT".
```

===============================================================================
## FISIERE
===============================================================================
P: /storage/emulated/0/Download/Agent/workspace/debian_binder.c   sursa C
P: /storage/emulated/0/Download/Agent/workspace/binder.py         modul Python
P: /storage/emulated/0/Download/Agent/workspace/bctl              client Android
P: /data/data/net.sys32.agent/files/tmp/binder_final.c            client Android src
P: /opt/android-binder/                                           instalare Debian
