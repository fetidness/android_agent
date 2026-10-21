---
name: binder-service-access-audit
description: "Binder pe acest device: ce comanda folosesti, cu ce context, ce e lazy vs blocat SELinux, si cum verifici corect. INCARCA-L inainte de orice test binder."
---
# Binder: cum se verifica CORECT (SM-A366B / Android 16)

## REGULA ZERO (cea care a costat 4 rapoarte false)
Inainte sa scrii UN SINGUR rand de client binder nou, verifica daca exista deja:
```bash
android-binder selftest          # in Debian (proot)
binder action=list               # in aplicatie (tool-ul binder)
```
Daca exista, FOLOSESTE-L. Codul care merge e deja in `assets/binder/debian_binder.c`
si in `assets/python/android_binder.py`. Un client scris de la zero in paralel a produs
"0 din 25 servicii" din cauza offseturilor gresite (code la 12 in loc de 16,
data_size la 20 in loc de 32, lipsa TF_ACCEPT_FDS, lipsa BC_ACQUIRE/BC_INCREFS,
getService cod 2 in loc de 1, uintptr tratat pe 4 bytes).

## Din APLICATIE (uid u0_aXXX, untrusted_app) - calea buna
```python
import android_binder                  # files/python/android_binder.py
b = android_binder.Binder()
len(b.list())                          # ~466 servicii
b.handle("package")                    # 1
b.interface_descriptor("display")      # android.hardware.display.IDisplayManager
st, data = b.call("display", 1)        # status=0, 1736 bytes, date reale
```
Dovedit functional: display(code 1)=1736 B, input(code 1)=8 B,
batteryproperties(code 1)=24 B, power(code 5)= eroare de permisiune reala
"Neither user N nor current process has android.permission.DEVICE_POWER".

## Din DEBIAN (proot, ctx u:r:shell:s0)
```bash
android-binder selftest     # 469 listate / ~213 getService OK / 3 lazy / ~253 null
android-binder iface package  -> android.content.pm.IPackageManager
android-binder iface power    -> android.os.IPowerManager
```

## Ce NU e eroare
- `null` la getService pentru ~350 servicii = **LAZY** (activity, window, notification,
  SurfaceFlinger, connectivity, stats, media.*). Nu sunt inregistrate in servicemanager
  pana nu le cere un client din framework. NU e SELinux, NU e binder stricat.
- `service check <nume>` din Android raspunde `found` pentru TOATE (469) - nu dovedeste acces.
- `0x80000001` in reply = NULL din parcel, nu un handle. Handle-ul real e u32 la offset 8
  in flat_binder_object si e 1 pentru majoritatea serviciilor de sistem.

## Capcane dovedite
TRAP: proot se lanseaza cu `-0` (root aparent) dar SELinux rămâne shell:s0; setuid(2000) nu schimba contextul
TRAP: `bctl-android` (binar Android) NU ruleaza din Debian (fara libc Android) - compileaza nativ cu gcc
TRAP: INTERFACE_TRANSACTION nu raspunde pe serviciile lazy -> foloseste un serviciu de baza (package/power/display)
TRAP: in aplicatie, un eval/reflexie costa ~60s; nu incerca sweep de 469 intr-un script (PTC 1800s)
