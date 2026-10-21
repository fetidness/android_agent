---
name: binder-app-binding
description: "Binder din APLICATIE (untrusted_app): bindall pe toate serviciile, bug-urile reale de offset/padding si de ce difera fata de Debian."
---
# Binder din aplicatie: binding masiv + capcane dovedite

## Binarele
- sursa: `files/binder/binder_android.c` (are: list, handle, call, check, get, bindall, probe)
- binar: `files/tmp/binder_android` (compilat cu toolchain clang, target aarch64-linux-android35)
- RULARE (exec direct din filesDir NU merge):
  ```bash
  /apex/com.android.runtime/bin/linker64 /data/data/net.sys32.agent/files/tmp/binder_android bindall
  ```
- Debian: `/opt/android-binder/android-binder` + sursa `debian_binder.c` (aidlcall, bindall, probe)

## Comenzi
- `bindall [--quiet]` -> leaga TOATE serviciile, printeaza `BOUND<TAB>nume<TAB>h=N<TAB>descriptor`
- `probe` -> apeluri AIDL reale demo (batteryproperties/display/input)
- `call <svc> <descriptor> <code> [i32...]`
- `list` -> toate serviciile (code 6 + DUMP_PRIORITY_ALL)

## CIFRE MASURATE PE ACEST DEVICE
- APP (untrusted_app): 467 listate / **88 legate** / 222 lazy (0xfffffffc) / 1 refuzat
- DEBIAN (shell:s0):   467 listate / **140 legate** / 2 lazy / 169 refuzat
- Aceeasi binar NU da aceleasi rezultate: SELinux filtreaza per context.

## BUG-URI REALE GASITE (fiecare a costat pasi)
TRAP: getService reply are handle la **offset 12** in data, NU la 4 (4 = garbage 0x73682a85)
TRAP: handle se citeste din flat_binder_object: `offsets_buffer[0]` = offset in data, handle la `data[off+8]`; daca offsz=0 serviciul a refuzat (nu e eroare de binder)
TRAP: `rep.status` la INTERFACE_TRANSACTION NU e cod de eroare: 0x23/0x24 = **lungimea descriptorului**. Respins doar 0xFFFFFFFF
TRAP: listServices = code **6** + `DUMP_PRIORITY_ALL(0x0F)` in parcel; code 3 da "Unknown error"
TRAP: String16 din lista se aliniaza la 4 dupa fiecare nume: `o += L*2; while(o&3) o++;` fara asta bucla se opreste la i=0
TRAP: comanda `call` refolosea bufferul `pl` de la getService fara memset -> descriptor corupt -> "Binder invocation to an incorrect interface". FIX: `memset(pl,0,sizeof pl)` inainte de mkparcel_ex
TRAP: INTERFACE_TRANSACTION suplimentar in `call` consuma reply-ul -> NU se face, doar prepare_handle (ACQUIRE+INCREFS+FREE_BUFFER)
TRAP: `prepare_handle` trebuie sa elibereze bufferul din getService (do_free=0 la getService, FREE in prepare_handle). Altfel handle-urile sunt toate 1
TRAP: padding dupa descriptor = **+4 fix** (dovedit, pentru IServiceManager SI AIDL). Alinierea `while(o%4)` rupe apelurile

## Compilare (receta exacta, dovedita)
```bash
TC=/data/data/net.sys32.agent/files/toolchain
$TC/bin/clang -fPIC -O2 --target=aarch64-linux-android35   --sysroot=$TC/sysroot -resource-dir=$TC/lib/clang/21   -I$TC/sysroot/usr/include   /data/data/net.sys32.agent/files/binder/binder_android.c   -o /data/data/net.sys32.agent/files/tmp/binder_android   -L$TC/sysroot/usr/lib/aarch64-linux-android/35   -L$TC/lib/clang/21/lib/linux -lm -ldl -latomic -Wl,--no-undefined
```
Pentru sursa din app, editeaza `files/binder/binder_android.c` direct din python
(`open(p,"w").write(...)`), NU din Debian: proot nu vede filesDir.

## Cum adaugi o comanda noua in binarul agentului
1. `src=open(".../binder_android.c").read()`; gaseste `src.rfind("    return 0;\n}")`
2. insereaza blocul `if(!strcmp(what,"nume")){ ... }` INAINTE de acel marker
3. scrie inapoi, compileaza cu receta de mai sus, ruleaza prin linker64

## Rulare lunga (467 servicii = ~10-150 s)
Nu rula in subprocess cu timeout mic: iese KeyboardInterrupt. Foloseste:
```python
f=open(log,"w")
subprocess.Popen([L,outp,"bindall"],stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
# apoi polleaza: while "refuzate" not in open(log).read(): sleep(10)
```

## De ce difera app vs Debian
Servicii Samsung/QTI (AODManagerService, nfc, gnss, usb, vendor.qti.*) intorc `offsz=0` din untrusted_app = refuz SELinux, nu bug. Din shell:s0 acelasi binar le leaga.
Servicii care merg din ambele: package, power, display, input, statusbar, sensorservice, activity_task, HqmManagerService, ImsBase, android.frameworks.stats.IStats/default.

TRAP: heredoc `cat >> file <<'EOF'` in shell-ul Debian scrie 0 bytes (fisierul ramane neschimbat, fara eroare) -> scrie din python: `open(p,"w").write(text)`
TRAP: output binar din `terminal`/`adbsh` se pierde ("[BINARY output binar: N bytes]") -> filtreaza: `comanda 2>&1 | tr -cd '[:print:]\n'`
TRAP: `python3` NU exista in Debian (proot); foloseste python din app sau gcc/bash
TRAP: `ps`/`dumpsys`/`cmd`/`service` NU exista in Debian; pentru verificari Android foloseste tool-ul `adbsh` (uid 2000)
TRAP: `terminal action=run` fara `cmd=` da "[terminal] cmd lipseste" -> pune mereu cmd
TRAP: un log de debug care printeaza doar primele N iteratii (`if(i<8)`) ascunde tocmai esecul relevant -> conditie pe esec, nu pe index

## Verificare corecta (nu te increde in "legate OK")
Apelul e real doar daca `status=0x0` SI len>4 cu date: display(1)=1736 B, batteryproperties(1)=24 B, input(1)=8 B.
Comparatie cross-check identica byte-cu-byte intre app si Debian pentru batteryproperties: `00 00 00 00 | 00 00 00 00 | 01 00 00 00`.

## De ce unele servicii merg DOAR din Debian (cauza dovedita)
Contextele difera:
- app:   `u:r:untrusted_app:s0:c163,c257,c512,c768`
- Debian:`u:r:shell:s0`
Mecanism: la getService, `servicemanager` verifica SELinux `service_manager find` pe numele
serviciului. Daca lipseste, NU intorce eroare: intorce un `flat_binder_object` NULL, deci
`offsets_size` = 0 in reply si niciun handle (`offsz=0`). De aceea arata ca "serviciu
inexistent" in loc de "permission denied".

DOVADA (acelasi binar, acelasi request, rezultat diferit):
- `handle adb` din app    -> `status=0x0 len=32 offsz=0`   (null)
- `service call adb 1` prin adbsh (uid 2000) -> `Result: Parcel(` cu date reale
- `handle package` din app -> `offsz=8` (merge din ambele)

Refuzate din app (sensibile, normal): adb, android.hardware.nfc.INfc/default,
android.hardware.gnss.IGnss/default, android.hardware.usb.IUsb/default,
AODManagerService, vendor.qti.hardware.perf2.IPerf/default.
Permise din ambele: package, mount, power, display, input, statusbar, sensorservice,
activity_task, HqmManagerService, ImsBase, android.frameworks.stats.IStats/default.

TRAP: nu confunda trei cauze diferite de esec la getService, au semnaturi distincte:
  `status=0xfffffffc` + len=16  -> serviciu LAZY/inexistent in servicemanager
  `status=0x0` + offsz=0        -> REFUZ SELINUX (null object) - nu e lazy, e politica
  `status=0x0` + offsz=8        -> ACCES OK, handle la data[(offsets_buffer[0])+8]
TRAP: `/sys/fs/selinux/policy` nu poate fi citit nici din Debian (Permission denied) si
sesearch nu exista -> nu incerca sa disectezi politica; dovedeste prin comportament
(acelasi binar in ambele contexte) si prin `service call <name> 1` din adbsh.
TRAP: nu copia binarul in /data/local/tmp din app (`cp: /data/local/tmp/...: Permission
denied`) - ruleaza-l din files/tmp prin linker64 si compara cu shell doar prin `service call`.
