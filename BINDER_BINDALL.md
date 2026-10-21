# BINDER_BINDALL.md - legarea tuturor serviciilor AIDL

Documenteaza implementarea `bindall` (legarea masiva a serviciilor AIDL) si cele
7 bug-uri reale gasite pe SM-A366B / Android 16, in AMBELE contexte: aplicatie
(untrusted_app) si Debian (shell:s0).

## Ce face bindall

Enumeră toate serviciile din servicemanager, obtine handle pentru fiecare,
executa secventa libbinder (ACQUIRE + INCREFS + FREE_BUFFER), citeste
descriptorul AIDL prin INTERFACE_TRANSACTION si raporteaza ce e legat.

Comenzi disponibile:
- `bindall [--quiet]` - leaga toate, printeaza `BOUND<TAB>nume<TAB>h=N<TAB>descriptor`
- `probe` - apeluri AIDL reale de demonstratie
- `call <svc> <descriptor> <code> [i32...]`
- `list` - toate serviciile (code 6 + DUMP_PRIORITY_ALL)
- `handle <nume>`, `check <nume>`, `iface <nume>`

## Rulare

Aplicatie (exec direct din filesDir NU merge, foloseste linker64):
```
/apex/com.android.runtime/bin/linker64 \
  /data/data/net.sys32.agent/files/tmp/binder_android bindall
```

Debian (binar glibc):
```
cd /opt/android-binder && ./android-binder bindall
```

## CIFRE MASURATE

- servicii in servicemanager: **467**
- APP (untrusted_app): 88 legate / 222 lazy / 1 refuzat
- DEBIAN (shell:s0): 140 legate / 2 lazy / 169 refuzat
- ACELASI binar nu da aceleasi rezultate: SELinux filtreaza per context.

## Apeluri AIDL reale verificate (identice in ambele medii)

- batteryproperties (IBatteryPropertiesRegistrar, code 1) -> status 0, **24 B**
- display (IDisplayManager, code 1) -> status 0, **1736 B**
- input (IInputManager, code 1) -> status 0, **8 B**

Cross-check byte cu byte pe batteryproperties:
`00 00 00 00 | 00 00 00 00 | 01 00 00 00` (AC powered = 1).

## CELE 7 BUG-URI (fiecare a costat pasi)

1. **Handle la offset 12, nu 4.** La 4 se citeste `0x73682a85` (gunoi).
   Handle-ul real vine din flat_binder_object: `offsets_buffer[0]` = offset in
   data, iar handle-ul e la `data[off+8]`.

2. **`rep.status` la INTERFACE_TRANSACTION NU e cod de eroare.**
   0x23 / 0x24 = **lungimea descriptorului**. Se respinge doar `0xFFFFFFFF`.
   Tratarea lui ca eroare respinge toate serviciile bune.

3. **listServices = code 6**, nu 3, si cere `DUMP_PRIORITY_ALL (0x0F)` in parcel.
   Cu code 3 se primeste "Unknown error 2147483644".

4. **Aliniere String16 lipsa.** Dupa fiecare nume din lista:
   `o += L*2; while(o&3) o++;` Fara asta bucla se opreste la i=0.

5. **Buffer refolosit fara memset.** Comanda `call` folosea `pl` (parcelul de la
   getService) ca parcel AIDL, fara curatare -> "Binder invocation to an
   incorrect interface". FIX: `memset(pl,0,sizeof pl)`.

6. **INTERFACE_TRANSACTION suplimentar in `call`** consuma un reply si strica
   apelul urmator. Nu se face: doar prepare_handle.

7. **Padding dupa descriptor = +4 FIX** (dovedit, atat IServiceManager cat si
   AIDL). Alinierea `while(o%4)` rupe apelurile.

Suplimentar: `prepare_handle` trebuie sa elibereze bufferul din getService
(do_free=0 la getService, FREE in prepare_handle), altfel toate handlurile sunt 1.

## DE CE UNELE SERVICII MERG DOAR DIN DEBIAN

Cauza e **SELinux `service_manager find`**, nu binder-ul si nu codul.

- app:   `u:r:untrusted_app:s0:c163,c257,c512,c768`
- shell: `u:r:shell:s0`

Cand permisiunea lipseste, servicemanager **nu intoarce eroare**: intoarce un
flat_binder_object null, deci `offsets_size` devine **0** (nu 8). De aceea e
inselator - nu primesti "permission denied", primesti tacere.

Refuzate din app (sensibile): adb, nfc, gnss, usb, AODManagerService,
vendor.qti.hardware.perf2.IPerf.

Permise din ambele: package, mount, power, display, input, statusbar,
sensorservice, activity_task, HqmManagerService, ImsBase,
android.frameworks.stats.IStats/default.

## Fisiere

- `binder_android.c` - sursa pentru aplicatie (are bindall + probe)
- `bindall.c` - sursa variantă Debian (bindall + probe)
- `debian_binder.c` - sursa originala Debian (aidlcall, paginated)
- `bound_services_app.txt` - cele 88 legate din app
- `bound_services_debian.txt` - cele 140 legate din Debian
- `../skills/binder-app-binding/SKILL.md` - lectii pentru sesiuni viitoare

## Compilare (aplicatie, toolchain din APK)

```
TC=/data/data/net.sys32.agent/files/toolchain
$TC/bin/clang -fPIC -O2 --target=aarch64-linux-android35 \
  --sysroot=$TC/sysroot -resource-dir=$TC/lib/clang/21 \
  -I$TC/sysroot/usr/include \
  binder_android.c -o /data/data/net.sys32.agent/files/tmp/binder_android \
  -L$TC/sysroot/usr/lib/aarch64-linux-android/35 \
  -L$TC/lib/clang/21/lib/linux -lm -ldl -latomic -Wl,--no-undefined
```

## Compilare (Debian, gcc glibc)

```
gcc -O2 -o bindall bindall.c
```
