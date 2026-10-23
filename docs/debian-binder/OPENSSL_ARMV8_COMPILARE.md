# OPENSSL CU ARMV8 CRYPTO - STARE (actualizat 2026-10-23 23:55)

## CONCLUZIE FINALA: s-a incercat si NU se rezolva fara recompilare

Am testat toate caile rapide. Rezultat: **singura solutie reala e recompilarea
OpenSSL cu ARMv8 crypto**, care ramane de facut. Mai jos e tot ce s-a incercat,
ca sa nu se repete.

### CAUZA EXACTA (masurata, nu presupusa)
`_hashlib...so` are `NEEDED: libcrypto_python.so`. Linkerul Android cauta intai
in `nativeLibraryDir` (APK lib dir), unde exista
`libcrypto_python.so` (4537664 B) compilat FARA ARMv8 activ -> 242 MB/s.
`/system/lib64/libcrypto.so` face 1444 MB/s, dar nu e folosit de Python.

### CE AM INCERCAT SI DE CE A ES ESUAT (toate testate azi)

1. **Copie libcrypto din sistem ca libcrypto_python.so in files/libs**
   -> linkerul prefera tot APK-ul (nativeLibraryDir are prioritate fixa)
   -> `_hashlib` incarca in continuare cel din APK

2. **LD_PRELOAD=<copia din files/libs>**
   -> **SIGSEGV** (rc=-11), conflict de simboluri

3. **ctypes.CDLL(sistem, RTLD_GLOBAL) inainte de import hashlib**
   -> ambele biblioteci incarcate, dar `_hashlib` foloseste tot cea din APK
   -> ramane 242 MB/s

4. **Patch pe binarul _hashlib**: schimbat stringul `libcrypto_python.so`
   in `libcrypto.so` (acelasi offset, lungime diferita -> rescris)
   -> `_hashlib` a luat `libcrypto.so` din files/libs (268 MB/s)
   -> **DAR: `dlopen failed: cannot locate symbol "EVP_MD_get_type"`**
   -> versiunea din sistem NU e compatibila cu `_hashlib` compilat pentru
      `libcrypto_python.so` (API diferit / simboluri lipsa)
   -> RESTAURAT din `.orig`, verificat ca totul merge din nou (243 MB/s, ssl OK)

### DE CE NU MERGE NICIO SCURTATURA
`libcrypto_python.so` din APK si `libcrypto.so` din Android sunt **build-uri
diferite de OpenSSL** cu seturi de simboluri diferite. `_hashlib` a fost
compilat impotriva celui dintâi. Deci:
- fie `_hashlib` ramane cu cel din APK (242 MB/s, dar merge)
- fie se RECOMPILA `_hashlib` + `libcrypto_python.so` impreuna, cu ARMv8 activ

## DE FACUT (raman variantele de compilare din documentul anterior)

Compilarea OpenSSL a ajuns la blocajul cu `aarch64-linux-android-gcc`.
Solutia de incercat (Varianta 1 din sectiunea de mai jos): creeaza
`files/tmp/aarch64-linux-android-gcc.sh` (wrapper-ul libshwrap_exec.so cauta
acest script dupa argv[0]).

Alternativ, mai simplu: compileaza OpenSSL ca `libcrypto_python.so` cu
`-DOPENSSL_armcap=...` si inlocuieste-l pe cel din APK **prin rebuild APK**
(pune-l in jniLibs), nu prin patch pe device.

## IMPORTANT
Starea actuala a device-ului e **sanatoasa**: `_hashlib` restaurat, SHA-256 la
243 MB/s, `import ssl` OK. Nu s-a stricat nimic.

---

## ISTORIC: ce am facut anterior


Scris: 2026-10-23 seara. Oprire intentionata, reluare maine.

## ★ CITESTE ASTA PRIMUL: s-ar putea sa NU mai fie nevoie de compilare

Am gasit la finalul sesiunii cauza reala, si e mai simpla decat credeam:

| libcrypto | SHA-256 masurat |
|---|---|
| /data/data/net.sys32.agent/files/libs/libcrypto.so (cel folosit ACUM de Python) | **242 MB/s** |
| /system/lib64/libcrypto.so (cel din Android, incarcat prin ctypes) | **1447 MB/s** |

Test reprodus:
```
python3 -c "
import ctypes, time, os
lib = ctypes.CDLL('/system/lib64/libcrypto.so')
lib.SHA256.restype = ctypes.POINTER(ctypes.c_ubyte)
lib.SHA256.argtypes = [ctypes.c_char_p, ctypes.c_size_t, ctypes.c_char_p]
d = os.urandom(32 << 20); out = ctypes.create_string_buffer(32)
t = time.time(); lib.SHA256(d, len(d), out)
print('%.1f MB/s' % (32 / (time.time() - t)))"
-> 1447.7 MB/s
```

Deci **libcrypto.so din Android e deja compilat cu ARMv8 crypto activ**. Problema
este DOAR ca Python-ul incarca versiunea din `files/libs/`.

### De ce o incarca pe aia
`LD_LIBRARY_PATH` contine `/data/data/net.sys32.agent/files/libs` INAINTE de
calea de sistem, deci linkerul o prefera pe cea din files/libs.

### Inca o pista neconfirmata
`readelf -d _hashlib...so` arata `NEEDED: libcrypto_python.so` - o biblioteca
care **NU EXISTA** pe device (`find` nu o gaseste). De investigat maine: poate
a fost redenumita, iar `_hashlib` cade pe alt mecanism.

## DE FACUT MAINE, IN ORDINE (prima varianta are cele mai mari sanse)

### Varianta 0 ★ (2 minute, incepe cu asta)
Testeaza daca `files/libs/libcrypto.so` poate fi inlocuit cu cel din sistem:
```
cd /data/data/net.sys32.agent/files/libs
cp libcrypto.so libcrypto.so.orig
# ATENTIE: dimensiuni diferite (1.97MB app vs 1.57MB sistem) - posibil ABI incompatibil
# test INAINTE de a inlocui permanent:
python3 -c "import ssl; print(ssl.OPENSSL_VERSION)"   # trebuie sa mearga
```
Daca merge si SHA-256 urca la ~1400 MB/s -> GATA, fara compilare.
Daca `import ssl` crapa -> restaureaza `libcrypto.so.orig` imediat.

### Varianta 0b (daca ABI-ul nu se potriveste)
Reordoneaza `LD_LIBRARY_PATH` pentru procesul Python, ca sa gaseasca intai
`/system/lib64`. Se face in `agent.py`/launcher, nu prin compilare.
De verificat unde se seteaza LD_LIBRARY_PATH (probabil la pornirea procesului
Python, in MainActivity.kt sau in toolchain_env.sh).

### Varianta 1 - scriptul wrapper lipsa (~5 min)
Doar daca 0/0b esueaza si chiar vrem OpenSSL compilat de noi.
`clang` din toolchain/bin e un symlink la `libshwrap_exec.so`, un WRAPPER care
se uita la argv[0] si executa `<nume>.sh` din files/tmp. Pentru numele
`aarch64-linux-android-gcc` cauta `files/tmp/aarch64-linux-android-gcc.sh`.
Creeaza acele scripturi (uita-te intai cum arata `files/tmp/clang.sh`).

### Varianta 2 - ocolirea prefixului triplu (~10 min)
Seteaza CC/CXX/AR/RANLIB explicit in Configure, sau CROSS_SYSROOT in loc de
ANDROID_NDK_ROOT (vezi Configurations/15-android.conf).

## CE AM FACUT DEJA## CE AM FACUT DEJA (nu repeta)

### 1. Descarcat si dezarhivat sursa
- sursa OK de la: https://www.openssl.org/source/openssl-3.5.7.tar.gz (53 MB)
- dezarhivat in: /data/data/net.sys32.agent/files/tmp/ossl/openssl-3.5.7
  (58 fisiere la nivel de top, verificat)

### 2. Verificat uneltele din toolchain (toate functioneaza)
- clang 21.1.8 OK
- GNU Make 4.4.1 OK
- perl v5.42.0 OK (testat cu `perl -e 'print $^V'`)
- llvm-ar, llvm-ranlib, llvm-nm, llvm-strip, ld.lld: toate prezente

### 3. Configurat OpenSSL cu target android-arm64
Comanda care a ajuns cel mai departe:
```
cd /data/data/net.sys32.agent/files/tmp/ossl/openssl-3.5.7
TC=/data/data/net.sys32.agent/files/toolchain
ANDROID_NDK_ROOT=$TC/ndk PATH=$TC/bin:/system/bin \
  $TC/bin/perl Configure android-arm64 no-shared no-tests no-ssl3 \
  -D__ANDROID_API__=35 --prefix=/data/data/net.sys32.agent/files/tmp/ossl/out
```
Rezultat: "Configuring OpenSSL version 3.5.7 for target android-arm64",
apoi a cerut `aarch64-linux-android-gcc` pe PATH.

## BLOCAJUL CURENT (aici s-a oprit)

OpenSSL cere un compilator numit `aarch64-linux-android-gcc` (prefix triplu).
Am incercat 3 variante, toate esuate DAR cu cauze diferite:

a) **script shell wrapper** in files/tmp/ossl/bin/aarch64-linux-android-gcc
   -> `Permission denied` (scripturile din filesDir NU se executa - SELinux)

b) **copie a binarului** cu numele nou, in files/tmp/ossl/bin sau toolchain/bin
   -> `Permission denied` (copiile ELF din filesDir NU se executa)

c) **symlink** la tinta reala (APK lib) cu numele nou
   -> `Error: /data/data/net.sys32.agent/files/tmp/aarch64-linux-android-gcc.sh:
      No such file or directory`

CAUZA REALA a esecului (c): `clang` din toolchain/bin NU e clang direct, e un
symlink la `/data/app/.../lib/arm64/libshwrap_exec.so` - un WRAPPER care se uita
la argv[0], cauta un script `<nume>.sh` si il executa. Pentru numele `clang`
gaseste `files/tmp/clang.sh`. Pentru `aarch64-linux-android-gcc` cauta
`files/tmp/aarch64-linux-android-gcc.sh` - care NU exista.

## SOLUTIA DE INCERCAT MAINE (in ordinea sanselor)

### Varianta 1 (cea mai probabila, ~5 min)
Creeaza scriptul lipsa in `files/tmp/`:
```
files/tmp/aarch64-linux-android-gcc.sh   -> exec $TC/bin/clang --target=... "$@"
files/tmp/aarch64-linux-android-ar.sh     -> exec $TC/bin/llvm-ar "$@"
files/tmp/aarch64-linux-android-ranlib.sh -> exec $TC/bin/llvm-ranlib "$@"
```
ATENTIE: scripturile din filesDir nu se executa direct, DAR wrapper-ul
libshwrap_exec.so le executa prin `/system/bin/sh <script>` - deci pot functiona
in acest context. Verifica intai cum arata `files/tmp/clang.sh` existent si
copiaza structura exact.

### Varianta 2 (~10 min)
Ocoleste wrapper-ul: seteaza explicit in Configure variabilele de compilator
ca sa nu caute prefixul triplu:
```
CC="$TC/bin/clang --target=aarch64-linux-android35 --sysroot=$TC/sysroot" \
CXX="$TC/bin/clang++ ..." \
AR="$TC/bin/llvm-ar" RANLIB="$TC/bin/llvm-ranlib" \
  perl Configure android-arm64 ...
```
Verifica daca 15-android.conf accepta `CROSS_SYSROOT` in loc de ANDROID_NDK_ROOT
(sursa: /tmp/ossl/openssl-3.5.7/Configurations/15-android.conf, linia ~40).

### Varianta 3 (daca 1+2 esueaza)
Compileaza in **Debian** (proot) cu gcc-ul de acolo + target android? NU -
Debian nu are sysroot Android. Varianta corecta: compileaza OpenSSL IN DEBIAN
pentru GLIBC (nu ajuta la app) sau renunta.

### Varianta 4 - ALTERNATIVA SIMPLA, poate cea mai buna
Nu recompila OpenSSL. Inlocuieste `files/libs/libcrypto.so` cu cel din
`/system/lib64/libcrypto.so` (cel folosit de `find_library`), care s-ar putea
sa aiba detectia runtime corecta deja facuta de Android.
RISC: incompatibilitate ABI cu Python-ul compilat. DE TESTAT PRIMUL, e 2 minute:
```
cp /system/lib64/libcrypto.so /data/data/net.sys32.agent/files/libs/libcrypto.so.bak
# apoi test: python3 -c "import hashlib,os,time; d=os.urandom(32<<20); print(32/(time.time()-hashlib.sha256(d).hexdigest() and 0))"
```
Masoara inainte/dupa. Daca nu se imbunatateste, restaureaza .bak.

## IMPORTANT - ce NU trebuie uitat

- Oricare varianta castiga -> **NU se pune in git** (libcrypto.so e binar mare).
  Se documenteaza in memory.md + README ca pas de build.
- Castigul asteptat: 242 -> ~1400 MB/s la SHA-256 (masurat in Debian: 1454 MB/s).
- Daca nimic nu merge, NU e o problema grava: agentul nu face hashing intensiv,
  iar Debian are deja SHA-256 rapid (se foloseste `dshell debian`).

## Fisiere utile maine
- sursa:      /data/data/net.sys32.agent/files/tmp/ossl/openssl-3.5.7
- env:        /data/data/net.sys32.agent/files/tmp/ossl/env.sh
- conf Android: .../Configurations/15-android.conf
- wrapper sursa: /data/app/~~OxOgBbT-fYKugDGOafOoGQ==/net.sys32.agent-1EA_VUKcggNPd2jLhN-PFA==/lib/arm64/libshwrap_exec.so
- scripturi wrapper existente: /data/data/net.sys32.agent/files/tmp/*.sh (ex. clang.sh)

## Stare git la oprire
- ultimul commit: e6e7773 (libdynload comis), local == remote, working tree curat
- NICIO modificare de azi seara nu e comisa (toate in files/tmp, temporare)
