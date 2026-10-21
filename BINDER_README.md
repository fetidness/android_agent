# BINDER — ce e nevoie pentru rebuild complet

Tot codul Binder e in repo, sub trei locuri. Un rebuild al APK-ului foloseste
automat tot ce e in `assets/`.

## 1. Client Binder IN-PROCESS (ruleaza in aplicatie)

```
assets/python/android_binder.py        client Binder (clasa Binder, strings)
assets/python/agent.py                 tool-ul `binder` + _binder_client/_binder_mod
```

Aceste doua fisiere sunt COPIA EXACTA a codului care ruleaza live in aplicatie
(verificat prin sha256). Dupa modificari:

```
cp /data/data/net.sys32.agent/files/python/android_binder.py \\
   workspace/app/net.sys32.agent/app/src/main/assets/python/
cp /data/data/net.sys32.agent/files/python/agent.py \\
   workspace/app/net.sys32.agent/app/src/main/assets/python/
```

## 2. Client Binder pentru DEBIAN (compilat nativ glibc)

```
assets/binder/debian_binder.c          sursa C (gcc din Debian)
assets/binder/binder.py                modul Python pentru Debian
assets/binder/install_binder.sh        instalare in /opt/android-binder
```

Recompilare in Debian:
```
cd /root/binder && gcc -O2 -o binder debian_binder.c
cp binder /opt/android-binder/android-binder
```

## 3. Client Binder pentru ANDROID (referinta / adbsh)

```
assets/binder/binder_android.c         sursa C (compilat cu clang din APK)
assets/binder/bctl-android             binarul compilat (armeabi arm64)
```

Ruleaza din `adbsh` (uid 2000), NU din Debian (libc incompatibil).

## 4. Teste

```
assets/binder/test_binder_inprocess.py  test extrem pentru tool-ul din aplicatie
assets/binder/test_binder_debian.py     test extrem pentru clientul din Debian
```

Ruleaza:
```
# in aplicatie
python3 assets/binder/test_binder_inprocess.py

# in Debian
python3 /root/test_binder_debian.py
```

## 5. Documentatie

```
DEBIAN_BINDER.md        protocol complet: offseturi verificate prin ptrace,
                        secventa ACQUIRE/INCREFS/FREE_BUFFER, capcane
BINDER_INPROCESS.md     modulul in-process + lectii duroase (fd-uri)
```

## Compilare APK

Assets-ul e inclus automat (`src/main/assets/`). Nu exista pas suplimentar:

```
build_apk action=build dir=/root/work/android_agent/workspace/app/net.sys32.agent
```

## Ce NU e in repo (si de ce)

- rootfs-ul Debian (`/data/local/tmp/debian`) — 25 MB+, se reinstaleaza
- binarul Debian compilat — se face cu `gcc` din sursa (2 secunde)
- `bctl` pentru alte ABI — doar arm64 e necesar (device real)

## Verificare rapida dupa rebuild

```
# in aplicatie (agentul)
binder action=list                        -> 469 servicii
binder action=call name=display code=1    -> status=0, 1736 bytes

# in Debian
android-binder selftest                   -> "getService REUSIT: 213 / 469", CONCLUZIE explicita
android-binder iface package              -> android.content.pm.IPackageManager
android-binder iface display              -> android.hardware.display.IDisplayManager
```

ATENTIE (eroare reala, 2026-10-21): NU testati cu `activity`, `window`, `stats`,
`surfaceflinger`, `media.*` - sunt lazy (ENOENT) sau refuzate de SELinux si un
esantion din ele da "0/N" desi binder-ul merge perfect. Folositi `selftest`.
