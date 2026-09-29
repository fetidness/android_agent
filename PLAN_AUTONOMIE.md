# PLAN - AUTONOMIE COMPLETA (net.sys32.agent)

> **Sursa de adevar pentru drumul spre "agentul isi compileaza singur orice, pe telefon".**
> Document viu: se actualizeaza la fiecare faza incheiata (vezi sectiunea 8 - Jurnal de progres).
> Regula de baza mostenita din `readme.md`: **fiecare afirmatie de aici trebuie TESTATA pe device,
> nu presupusa**. Ce nu e verificat se marcheaza explicit ca "neprobat".

Data: 28 sept 2026 | Device: Samsung SM-A366B (RZGL102X5AT), Android 16 / SDK 36, aarch64, 8 core, 7.3 GB RAM
Toolchain livrat: clang/LLVM 21.1.8, Python 3.14.7, APK `.assets_v182`

---

## 0. CUPRINS

1. Definitia lui "100% autonom"
2. Reguli de executie (cum se lucreaza pe fiecare faza)
3. Starea de fapt masurata (28 sept 2026)
4. Matricea de capabilitati (ce merge, ce nu, cu dovada)
5. Fazele: 0 - FUNDATIA, 1 - CMAKE, 2 - RUST, 3 - PERL/AUTOTOOLS, 4 - TIER 2, 5 - COZI LUNGI, 6 - INCHIDERE
6. Proceduri de verificare (clean install, task din UI, marker, accessibility, cheie)
7. Capcane dovedite (lectii care nu trebuie re-invatate)
8. Jurnal de progres
9. Ce ramane imposibil (limite fizice, nu de implementare)
10. Backlog / idei optionale

---

## 1. DEFINITIA LUI "100% AUTONOM"

Un pachet este considerat instalabil autonom daca, **pe o instalare curata, fara PC, fara
interventie pe device**, agentul poate: (a) detecta ca lipseste, (b) alege singur metoda
(wheel binar inainte de compilare), (c) compila nativ daca nu exista wheel, (d) verifica
functional rezultatul, (e) raporta onest daca nu se poate si de ce.

Tinta realista: **toate pachetele PyPI cu extensii C / C++ / Fortran, plus cele care cer cmake
sau Rust**. Ramane in afara doar ce depaseste fizic telefonul (ex. torch: build >16 GB RAM).

---

## 2. REGULI DE EXECUTIE (per faza)

1. **Construim/impachetam pe laptop, verificam pe DEVICE, abia apoi declarăm faza incheiata.**
   Fara "ar trebui sa mearga".
2. Fiecare faza se inchide cu DOUA verificari:
   - instalare CURATA (dezinstalare + reinstalare APK, marker `.assets_vNNN` nou) - vezi sectiunea 6;
   - un **task dat din interfata, fara indicatii de tool** (agentul trebuie sa aleaga singur).
3. Masuram si notam: timp de build, RAM varf, spatiu ocupat in APK, rezultatul `logcat`.
4. Daca o faza nu iese in buget: o raportam ca esec onest cu cauza, NU lasam fix-uri pe jumatate.
5. Dupa fiecare faza: `readme.md` (Etapa noua), `STATUS_OPTIMIZARI.md`, `CHANGELOG.md`
   regenerat, commit + push (cheia SSH e configurata pe repo: `core.sshCommand`).
6. Orice atingere de `assets/` => **incrementeaza markerul `.assets_vNNN`** in `MainActivity.kt`,
   altfel device-ul foloseste copia veche (capcana clasica, vezi sectiunea 7).

---

## 3. STAREA DE FAPT MASURATA (28 sept 2026)

Ce este deja in APK si functioneaza ca APP (uid ~10300), fara PC si fara Termux:

    compilatoare   clang 21.1.8 (C/C++17/20), lld 21.1.8, flang 21.1.8 (Fortran, wrapper in 2 pasi)
    binutils       llvm-ar / ranlib / nm / strip (+ readelf/objdump cu fallback)
    build tools    ninja 1.12.1, GNU make 4.4.1 (cross-compilat de la 0), pkg-config (pkgconf)
    sysroot        Android API 35 (headere + stub-uri de link + crt-uri) + symlink <api> -> 35
    python headers toolchain/pyinc (Python.h complet) + symlink pyhome/include/python3.14
    runtime C++    libc++ complet (2125 headere) + libc++abi.a + libc++_shared.so
    deps precompilate  zstd 1.5.6, lzma 5.6.3, bz2 1.0.8, libffi 3.4.6, expat 2.6.4,
                       OpenSSL 3.0.16 (crypto+ssl+135 headere), libjpeg-turbo (8/12/16-bit),
                       libxml2 + libxslt, BLAS/LAPACK + OpenBLAS 0.3.29 (SIMD NEON)
    runtime Fortran libFortranRuntime.a + libFortranDecimal.a (compilate de la 0)
    build deps py   setuptools, wheel, pip, Cython 3.3.0, pybind11, scikit-build-core,
                    setuptools_scm, vcs_versioning, meson, mesonpy, pyproject_metadata,
                    packaging, pathspec (in pysitepkg.zip / Lib/site-packages)
    executabilele   doar din nativeLibraryDir; in files/tmp sunt symlink-uri cu numele REAL
                    (clang, clang++, ld.lld, ar, ranlib, nm, strip, ninja, samu, make, flang)

Mecanisme de autonomie deja implementate (fiecare verificata pe device):

    - `_patch_sysconfig_device()`: INCLUDEPY / LIBDIR / CC / CXX / LDSHARED corecte pe device
      (prefixele de cross-build `/usr/local/...` sunt rescrise), cu reincarcare in proces
    - `_ensure_py_include()` / `_ensure_py_lib_link()`: Python.h + `-lpython3.14` gasibile
    - `_rt_ld_path()` / `agent._clean_ld()`: LD_LIBRARY_PATH de RULARE fara stub-urile NDK
    - `_ensure_launchers()`: symlink-uri executabile, cu REPARARE cand tinta e moarta
      (hash nou in /data/app la fiecare reinstalare)
    - `pip_install`: prima incercare `-v` + `--no-build-isolation`; daca lipsesc cerintele de
      build -> le extrage din output, le instaleaza, reia; altfel retry cu build isolation;
      rezultatul contine linia `pasi:` (ex. `deps(cppy)=0; retry_dupa_deps=0`)
    - `files/site_packages_keep`: pachetele compilate supravietuiesc update-ului de APK

---

## 4. MATRICEA DE CAPABILITATI

| Capacitate | Status | Dovada (28 sept) |
|---|---|---|
| pachete pure-Python | MERGE | requests, bs4, yaml, toml (in APK) |
| wheel binar de pe PyPI | MERGE | simplejson 4.1.2 (wheel), cbor2 |
| extensie C (setuptools) | MERGE | regex 2026.9.10, fastnumbers 5.2.0, markupsafe |
| extensie C++ (setuptools) | MERGE | greenlet 3.5.6, msgpack 1.2.2, kiwisolver 1.5.1 |
| C++ cu libffi (dlopen) | MERGE | cffi 2.1.1 (`strlen` prin dlopen) |
| scikit-build-core / meson | MERGE | zstandard 0.25.0, lz4 4.4.5 |
| libs externe la link | MERGE | lxml 6.1.3 (libxml2 2.15.4, XPath functional) |
| cerinte de build lipsa | MERGE | kiwisolver: `pasi: deps(cppy)=0; retry_dupa_deps=0` |
| Fortran - COMPILARE | MERGE | binar produs (1.5 MB) cu flang wrapper |
| Fortran - RULARE | NU | binarul standalone da segfault (runtime init) |
| cmake >= 3.29 | NU | build cross ARM64 esuat (libuv, libarchive) - FAZA 1 |
| backend Rust / maturin | NU | cramjam: `BackendUnavailable: Cannot import 'maturin'` - FAZA 2 |
| perl / autotools | NU | grpcio (asm BoringSSL), sdists cu doar configure.ac - FAZA 3 |
| HDF5 / h5py | NU | neinceput - FAZA 4 |
| freetype / matplotlib / Pillow complet | NU | neinceput - FAZA 4 |
| LLVM dev (libLLVM) / llvmlite | NU | neinceput - FAZA 5 |
| torch | IMPOSIBIL | build >16 GB RAM; telefonul are 7.3 GB |

---

## 5. FAZELE

### FAZA 0 - FUNDATIA DE AUTONOMIE (0.5-1h, risc mic, castig imediat)

**De ce:** fara asta agentul ghiceste si repeta munca. Nu deblocheaza pachete noi, dar face
diferenta intre "merge" si "stie ca merge".

Livrabile:
- **A. Self-test de capabilitati** (`toolchain action=selftest`): compileaza si LINKEAZA pe
  device C, C++ cu STL, o extensie cu Python.h, un proiect meson si unul scikit-build-core;
  raporteaza per capabilitate TRUE/FALSE + timp. Agentul il ruleaza inainte sa promita ceva.
- **B. Taxonomie de esec + raport onest**: la esec, clasifica (`rust_lipsa`, `cmake_lipsa`,
  `perl_lipsa`, `ram_insuficient`, `wheel_inexistent`, `eroare_de_cod`) si scrie ce lipseste
  + ce alternativa exista. Fara traceback brut in fata operatorului.
- **C. Cache persistent de wheels**: fiecare build reusit se copiaza in `files/wheels`
  (protejat ca `site_packages_keep`), iar `pip_install` il foloseste la nevoie
  (`--find-links`). Rezultat: numpy compilat o data = niciodata reconstruit.
- **D. Wheel-first**: regula explicita - intai binar de pe PyPI, compilare doar daca nu exista.

Criteriu de acceptanta: task din UI **"ce poti instala pe telefon?"** => agentul ruleaza
self-testul si raspunde din raport, nu din presupuneri. Reinstall NU reconstruieste un wheel deja
in cache (dovada: timpul scade la < 5s).

### FAZA 1 - CMAKE (3-4h, cel mai mare castig)

**Deblocheaza:** duckdb, pyarrow, onnxruntime, pasii cmake din llvmlite, plus orice pachet cu
build system cmake.

**Blocaje dovedite:** libuv (`sched_getaffinity`, `CPU_SETSIZE`, `CPU_COUNT` lipsesc pe bionic);
libarchive (`android_lf.h` - header intern Android).

**Abordare (in ordine):**
1. patch libuv: `sysconf(_SC_NPROCESSORS_ONLN)` in loc de `sched_getaffinity` + definite
   `CPU_SETSIZE`/`CPU_COUNT`;
2. libarchive: adaugat header-ul minim `android_lf.h` (sau `-DHAVE_ANDROID_LF_H=0`);
3. plan B: cmake construit FARA componentele care cer libuv/libarchive (doar generatorul
   intern e suficient pentru a scrie `build.ninja`);
4. plan C (deja validat conceptual): cmake doar ca GENERATOR, executia o face ninja (il avem).

Criteriu de acceptanta: `cmake --version` pe device + `pip install duckdb` compilat (buget
20-40 min, prin `bg`) + interogare reala pe o tabela; alternativ `pyarrow` daca duckdb depaseste
bugetul de timp. Notam timpul si RAM-ul varf.

### FAZA 2 - RUST (2-3h, deblocheaza o clasa intreaga)

**Deblocheaza:** cryptography, orjson, pydantic-core, polars, tokenizers + orice backend maturin.

**Problema fundamentala:** rust-lang.org NU livreaza `rustc` pentru `aarch64-linux-android`
(doar `rust-std`). Deci nu exista cale "oficiala" prin rustup.

**Abordare:**
1. impachetam in APK (in assets/toolchain) `rustc` + `cargo` + `rust-std` precompilate pentru
   aarch64-linux-android (licente MIT/Apache-2.0 - compatibile cu distributia);
2. config `.cargo/config.toml`: linker = clang-ul nostru, `--target=aarch64-linux-android<api>`,
   `--sysroot` + `-L` catre sysroot/35 si deps/lib;
3. wrapper executabil in `files/tmp` (rustc/cargo nu pot rula din filesDir - regula SELinux);
4. verificare pe Rust pur intai (`orjson`), apoi pe Rust+C (`cryptography`).

Riscuri: numele target-ului si ABI-ul (bionic vs musl), marimea (rustc + std = sute de MB in APK),
posibil sa fie nevoie de `-Z build-std` (nightly). Plan B: build rustc din surse cu LLVM-ul
nostru (mult mai scump, 6h+, doar daca planul A pica).

Criteriu de acceptanta: `pip install orjson` -> exit 0 + import + serializare reala; `cryptography`
-> exit 0 + semnatura/verificare RSA functionala.

### FAZA 3 - PERL / AUTOTOOLS (1.5-2h)

**Deblocheaza:** sdists care aduc doar `configure.ac` (majoritatea insa aduc `configure`
pre-generat - deci intai verificam!), grpcio (asm BoringSSL), orice build cu autoconf/automake.

**Abordare:**
1. regula: daca sdist-ul are `configure` executabil -> il folosim direct (zero perl);
2. daca are doar `configure.ac` -> avem nevoie de autoconf/automake, iar autoconf cere perl;
   deci: perl minim cross-compilat ARM64 (sau miniperl) impachetat in toolchain;
3. grpcio: `GRPC_BUILD_WITH_BORING_SSL_ASM=0` aplicat automat de `pip_install` cand detecteaza
   pachetul (pierdere mica la criptare, castig: fara perl).

Criteriu de acceptanta: `pip install grpcio` -> exit 0 + server/client de test care schimba un
mesaj; un sdist cu `configure` real (ex. `libxml2-python`-style) compilat.

### FAZA 4 - BIBLIOTECI TIER 2 (4-6h)

| Lib | Marime | Deblocheaza |
|---|---|---|
| sqlite3 dev (headere din libsqlite3_python.so) | ~2 MB | pandas.read_sql, sqlalchemy, Django |
| freetype + zlib + png + tiff + webp | ~15 MB | matplotlib, Pillow cu formate complete |
| HDF5 | ~30 MB | h5py |
| libzmq | ~5 MB | pyzmq - DOAR daca nu exista wheel Android (are cp314!) |

Regula wheel-first se aplica intai (pyzmq, Pillow pot veni ca binar).

Criteriu de acceptanta: matplotlib salveaza un PNG real pe device si il putem deschide/citi;
h5py scrie si citeste un fisier .h5; Pillow deschide JPEG/PNG/TIFF/WebP; pyzmq face round-trip
pe un socket local.

### FAZA 5 - COZI LUNGI (opțional, 3-6h)

- **Fortran la RULARE** (segfault): diagnostic pe initializarea runtime-ului
  (`libFortranMain`, unitati I/O) => scipy complet. Castig mediu, risc mediu.
- **LLVM dev stack** (libLLVM + LLVMConfig.cmake, ~300 MB, ~6h) => llvmlite/numba.
  Doar daca chiar e nevoie; avem COMPILATORUL LLVM, dar nu BIBLIOTECA.
- **torch**: NU se face. Limita fizica (RAM).

### FAZA 6 - INCHIDERE (1h)

- Sectiune "CE POT / CE NU POT" in system prompt (agentul sa stie limitele si sa propuna
  alternative, nu sa incerce la infinit).
- Script de regresie in repo (`tools/smoke_autonomy.sh`): instalare curata + matrice de
  capabilitati, exact ce s-a facut manual in sesiunea 2b.
- Actualizare `readme.md` / `STATUS_OPTIMIZARI.md` / `CHANGELOG.md` + marker nou.

---

## 6. PROCEDURI DE VERIFICARE (cum se re-produce ce s-a facut deja)

**Instalare curata (dovada suprema):**
```
ADB=/home/gab/android/platform-tools/adb
$ADB uninstall net.sys32.agent
$ADB shell rm -rf /sdcard/Download/Agent
$ADB install workspace/app/net.sys32.agent/app/build/outputs/apk/debug/app-debug.apk
$ADB shell am start -n net.sys32.agent/.MainActivity
# asteapta ~60-90s: extras 282 MB + toolchain; verifica .assets_vNNN in files/
```

**Cheia DeepSeek (NU sta in git):** se lipeste in onboarding-ul aplicatiei (ecranul o scrie in
`files/python/key.txt`) - NU se tipareste si NU se comite. Dupa reinstalare trebuie re-lipita
(extragerea sterge `python/`).

**Permisiuni + accessibility + baterie (dupa fiecare reinstalare):**
```
$ADB shell settings put secure enabled_accessibility_services net.sys32.agent/net.sys32.agent.AgentAccessibilityService
$ADB shell settings put secure accessibility_enabled 1
$ADB shell dumpsys deviceidle whitelist +net.sys32.agent
# permisiuni runtime: pm grant <perm> pentru CAMERA/LOCATION/... (73 granted=true dupa grant-uri)
```

**Task dat din UI (fara indicii de tool) - mecanica:**
```
$ADB shell input tap 400 2219            # campul de input (tastatura inchisa)
$ADB shell input text "Task%scu%sspatii%sescape-uite"
$ADB shell uiautomator dump /data/local/tmp/u.xml   # citeste bounds EXACTE pentru sageata
$ADB shell input tap <x> <y>             # sageata de trimitere (se misca sus cand e tastatura)
```
Capcane: pozitia sagetei se schimba cu tastatura; parantezele in `input text` sparg shell-ul
(evita-le); urmareste rezultatul cu `screencap` (NU cu OCR, foloseste vederea pe imagine).

**Urmarirea a ce a executat agentul (fara OCR):** `/data/data/net.sys32.agent/files/context.json`
(istoricul cu tool_calls + rezultate; poate avea "extra data" dupa array, foloseste
`json.JSONDecoder().raw_decode`).

**Harness local de test (in `temp/`, gitignored):** `run_e2e.sh` + `probe_e2e.py` importa
`agent.py` ca modul si cheama EXACT handler-ul `run_toolchain_tool` (cu env-ul de startup
simulat), deci testeaza codul real fara sa astepte modelul.

---

## 7. CAPCANE DOVEDITE (nu re-invata astea)

1. **Marker `.assets_vNNN`** - orice modificare in `assets/` fara increment => device-ul foloseste
   copia veche. Verifica dupa install: `ls files/ | grep assets_v`.
2. **`LD_LIBRARY_PATH` cu stub-uri NDK** = SIGSEGV in orice PROCES COPIL (libc fara cod).
   `_rt_ld_path()` / `_clean_ld()` filtreaza `sysroot`. Doar RULARE; linkarea are nevoie de ele.
3. **untrusted_app nu executa din filesDir** - executabile = doar nativeLibraryDir + symlink-uri
   in `files/tmp`; symlink-urile mor la reinstalare (hash nou) => reparare automata.
4. **`inspectia sysconfig`**: INCLUDEPY/LIBDIR/CC/CXX/LDSHARED trebuie rescrise pe device;
   setuptools NU foloseste LDFLAGS din sysconfig la link => `-L` in LDSHARED.
5. **clang are nevoie de crt-uri** in `<sysroot>/usr/lib/<triple>/<api>`; daca dirul de API
   lipseste, emite nume BARE pe care lld le cauta doar in CWD => symlink `<api> -> <api_existent>`.
6. **`--no-build-isolation` nu instaleaza cerintele din pyproject** => "Missing setup required
   dependencies"; cauza e ascunsa fara `-v`.
7. **`-m pip` ignora PYTHONPATH cand PYTHONHOME e setat** => injectam zip-urile in `sys.path`.
8. **AAPT2 ignora folderele care incep cu `_`** => livrate ca `.py` sau ZIP.
9. **`adb install -r` + `am force-stop` dezactiveaza accessibility** => re-activeaza (2 comenzi).
10. **`libdir.txt`/symlink-urile se schimba la reinstalare** (hash nou in `/data/app`).
11. **Nu rula subprocess/shell din procesul agentului pentru verificari** (deadlock pe fork):
    `os.path` / `os.listdir` direct. `_sh()` are nevoie de `stdin=DEVNULL` + `killpg`.
12. **Cheia ADB** - se regenereaza la instalarea curata; prima comanda `adbsh` poate cere
    dialogul "Allow USB debugging" pe telefon.

---

## 8. JURNAL DE PROGRES

| Faza | Status | Data | Dovada / note |
|---|---|---|---|
| 0 - Fundatia (self-test, taxonomie, cache wheels, wheel-first) | FACUT + VERIFICAT | 29 sept | vezi sectiunea 8.1 |
| 1 - cmake | FACUT + VERIFICAT | 29 sept | vezi sectiunea 8.2 |
| 2 - Rust | NEINCEPUT | - | cercetat: rust 1.98.1 = 122 MB deb / 548 MB instalat + libllvm 165 MB; maturin nu exista in repo; nevoie de bootstrap la cerere sau build din sursa |
| 3 - perl / autotools | FACUT + VERIFICAT | 29 sept | perl 5.42.0 COMPILAT DE NOI (perl-cross 1.6.5 + NDK 27), vezi 8.3 |
| 4 - Tier 2 (sqlite3, freetype, HDF5, libzmq) | IN LUCRU (sqlite3+freetype+png+zlib+zstd gata; HDF5/libzmq lipsesc) | 29 sept | vezi 8.3 |
| 5 - Fortran la rulare / LLVM dev | NEINCEPUT | - | - |
| 6 - Inchidere + script regresie | NEINCEPUT | - | - |

Statusuri: NEINCEPUT / IN LUCRU / FACUT+VERIFICAT / ESEC (cu cauza) / AMANAT.

### 8.1 FAZA 0 - rezultat (29 sept 2026, APK `.assets_v184`)

Implementat:
- `toolchain.selftest()` - compileaza+LINKEAZA real C, C++ (STL), extensie Python.h si Fortran;
  verifica ninja/make/ld.lld/pkg-config, backends importabile (meson, scikit-build-core, Cython,
  setuptools, pybind11, pathspec), cmake/rust/perl, cate wheel-uri are wheelhouse-ul; intoarce
  `ok[]`, `lipsa[]`, `timpi_s`, erorile per test si `verdict`.
- `_classify_build_fail()` - taxonomie de esec cu coduri (`rust_lipsa`, `cmake_lipsa`,
  `perl_lipsa`, `ram_insuficient`, `spatiu_insuficient`, `wheel_inexistent`, `cerinte_build`,
  `headers_lipsa`, `link_runtime`, `eroare_build`) + "ce lipseste" + "urmatorul pas"; apare ca
  linie `[diagnostic] ...` in rezultatul tool-ului.
- Wheelhouse `files/wheels` + `--find-links` + fast-path OFFLINE (`--no-index --find-links`).

Verificat pe device (SM-A366B):
- `run_toolchain_tool({"action":"selftest"})` -> JSON 897 chars, tot TRUE mai putin
  `cmake`/`rust`/`perl`; timpi: C 0.18s, C++ 2.03s, extensie Python 0.33s, Fortran 0.22s.
- taxonomie: `cramjam` -> `cod=rust_lipsa`; `murmurhash` -> `cod=eroare_build` (Cython);
  un install offline ratat -> `cod=wheel_inexistent`.
- wheelhouse: `xxhash` (wheel de pe PyPI) -> salvat in `files/wheels`; dezinstalat si reinstalat
  cu `--no-index --find-links` -> "instalat din wheelhouse local (fara retea, fara compilare)".
- kiwisolver re-verificat dupa refacere: exit 0 (38s), import OK 1.5.1.
- instalare curata v184 + intrebare din UI ("Poti instala pyarrow?") -> raspuns corect in 2 pasi /
  16.8s: `CMakeNotFoundError: Could not find CMake with version >= 3.25` (sdists pentru pyarrow
  cer cmake; scikit-build-core nu are cmake pe device).

Regresii gasite si reparate in timpul fazei (lectii de retinut):
1. `pip wheel --no-build-isolation` NU e echivalent cu `pip install --no-build-isolation`:
   ascunde "Missing setup required dependencies: cppy" in spatele `BackendUnavailable` ->
   prefetch-ul de cerinte nu mai functiona (kiwisolver a picat). Drumul principal a revenit la
   `pip install`; wheelhouse-ul se populeaza cu `pip wheel --no-deps` DOAR dupa un install reusit
   din wheel (nu dupa compilare locala, ca sa nu compileze a doua oara).
2. Doua subcomenzi pip in ACELASI proces: a doua nu mai vede `--find-links` ("from versions: none")
   -> instalarea din wheelhouse se face intr-un PROCES NOU (`_pip_fresh`).
3. La re-extragerea assets se sterge `files/python/` (inclusiv `key.txt` scris de onboarding!), dar
   `files/home/key.txt` SUPRavietuieste -> agentul porneste. Daca se sterge si acela, trebuie
   re-lipita cheia in UI.
4. Instalarea curata regenereaza cheia ADB -> adbd cere din nou "Allow USB debugging" (dialog de
   sistem; se aproba cu `input tap` pe checkbox + Allow). Dupa aprobare, `adbsh` (uid=2000) merge.

Observatie pentru FAZA 6: la intrebari de tip "pot instala X?", agentul prefera `pip install
--dry-run` (2 pasi, 17s, raspuns corect) in loc de `selftest`; regula din system prompt care cere
`selftest` exista, dar modelele aleg uneori proba directa. Ambele sunt valide; de intarit in FAZA 6.

---

## 9. CE RAMANE IMPOSIBIL (limite fizice, nu de implementare)

    torch          build >16 GB RAM; telefonul are 7.3 GB
    proiecte C++ de ore intregi (ex. LLVM/Chromium-like) - fezabile dar nepractice pe telefon
    onnxruntime    fezabil tehnic, dar protobuf + Eigen + C++17 => timp/RAM mari

---

## 10. BACKLOG / IDEI OPTIONALE

- Cache de wheels si pe /sdcard (vizibil, transferabil intre instalari/telefoane).
- `toolchain action=capabilities` expus si in system prompt (agentul sa nu incerce ce nu se poate).
- Build-uri lungi obligatoriu prin `bg` + `/watch` (0 tokeni) - deja regula, de intarit cu
  estimare automata de durata.
- Split ABI (arm64-only, -18 MB) si R8/ProGuard pe release (cand codul e stabil).
- Test automat de regresie in CI (acelasi script de la FAZA 6, rulat pe laptop + device).
- Encodare/criptare `agent.py` in assets daca se doreste protectia sursei (PyArmor / assets criptate).

### 8.2 FAZA 1 - cmake pe device (29 sept 2026, `.assets_v187`)

**Rezultat: cmake 3.31.6 ruleaza PE TELEFON si construieste proiecte reale.**
`toolchain action=selftest` -> `"cmake": true` (configure+build proiect C, 1.2s);
proiect de test: configure 0.9s + build + binarul RULAT pe device (`HELLO_FROM_CMAKE_ON_DEVICE`).

Cum a fost obtinut:
1. **Cross-compilat cmake 3.31.6** pentru aarch64-linux-android pe laptop (NDK 27, API 35),
   cu `libc++ STATIC` (fara dependenta de libc++_shared de pe device - copia din APK/device
   are 1.4 MB si NU exporta simbolurile `std::filesystem`, care rupeau link-ul).
   Patch-uri necesare in sursele cmake (toate in `Utilities/*`):
   - `cmlibarchive/libarchive/android_lf.h` - header gol (libarchive il include, dar nu
     foloseste nimic din el; NDK-ul nu il are).
   - `cmlibuv/src/unix/core.c` - `CPU_SETSIZE` (bionic nu il are) + `uv_available_parallelism`
     prin `sysconf` in loc de `sched_getaffinity`/`CPU_COUNT`.
   - `cmlibuv/src/unix/pipe.c` - `pipe2` lipseste in NDK -> `pipe()` + fcntl.
   - `cmlibuv/src/unix/process.c` - blocul `cpumask` (cpu_set_t/CPU_ZERO/CPU_SET) dezactivat.
   - `cmlibuv/src/unix/internal.h` - workaround-ul istoric `uv__pthread_sigmask` dezactivat
     (definitia lui nu se compileaza in libuv-ul bundled -> simbol nedefinit la link).
   - `cmlibuv/CMakeLists.txt` - sursele de platforma Linux (epoll/linux-core/inotify/procfs)
     se adaugau DOAR pentru `CMAKE_SYSTEM_NAME=Linux`; pe Android lipseau ->
     `uv__platform_invalidate_fd`/`uv__hrtime` nedefinite.
   - `Source/cmAffinity.cxx` - `pthread_getaffinity_np` lipseste pe bionic -> `sysconf`.
   - `Source/cmSystemTools.cxx` - `FindCMakeResources`: radacina (`CMAKE_ROOT`) si
     `CMAKE_COMMAND` vin din variabile de mediu (pe device nu exista layout de instalare).
2. **In APK**: binarul (10.7 MB) ca `jniLibs/arm64-v8a/libcmake_exec.so` (singurul loc
   executabil pentru untrusted_app) + `assets/toolchain/cmake/{Modules,Templates}` (11 MB).
3. **In `toolchain.py`**: `env_vars()` exporta `CMAKE_ROOT`, `CMAKE_MAKE_PROGRAM` (ninja),
   `CMAKE_TOOLCHAIN_FILE`, `CMAKE_GENERATOR=Ninja`, `CMAKE_ARGS` (pentru scikit-build-core),
   `CMAKE_PREFIX_PATH` (deps) si **`PREFIX`** - si scrie `files/tmp/android.toolchain.cmake`.
   `_ensure_fake_ndk()` construieste un NDK MINIMAL prin symlink-uri (cmake detecteaza singur
   Android din triple-ul clang-ului si altfel cere un NDK complet).

Capcane noi, dovedite pe device (raman ca lectii):
- **`PREFIX` e obligatoriu**: cand cmake RULEAZA pe Android, `CMakeDetermineSystem.cmake`
  citeste `$ENV{PREFIX}/include/android/api-level.h` ca sa afle API-ul. Fara `PREFIX`:
  `file failed to open: /include/android/api-level.h` -> configure esuat (desi compilatorul
  era perfect). `PREFIX = <ROOT>/sysroot/usr`.
- **`CMAKE_COMMAND` trebuie stiut de cmake**: la generarea regulilor lui Ninja, cmake isi
  invoca propriul binar (`cmake -E rm -f ...`). Daca radacina vine din mediu si cmake nu-si
  poate deduce calea, iese `"" -E rm -f libst.a` -> `/bin/sh: : can't execute: Is a directory`.
- **cache-ul cmake e lipicios**: un `CMakeCache.txt` scris intr-un configure esuat pastreaza
  "compiler broken" si TOATE configure-urile urmatoare esueaza identic. Sterge directorul de
  build inainte de re-verificare.
- **flags-urile compilatorului trebuie sa fie in toolchain**, nu doar in `CC`/`CXX`:
  testele de compilator ale cmake primesc doar `CMAKE_C_FLAGS_INIT`; fara `-resource-dir`
  linkerul cauta `libclang_rt.builtins.a` in nativeLibraryDir -> "compiler broken".
- fara `CMAKE_SYSTEM_NAME=Android` + NDK fals, cmake tot detecteaza Android din triple si
  cere NDK; cu `Linux` ca system name, proiectele care se uita la `ANDROID` ar fi nedumerite.

Test real cu pachet de pe PyPI (build CMake + scikit-build-core): `h3` a trecut de
configure cmake + generarea Cython + startul compilarii cu ninja si a picat pe o eroare
Cython din sdist (`from .error_system cimport check_for_error`) - adica NU pe toolchain.

### 8.3 FAZA 3 - perl autonom + Tier-2 + fixuri de pachete (29 sept 2026, `.assets_v190`)

**Nimic din Termux nu mai e folosit in APK.** perl-ul vechi (binar Termux) a fost inlocuit cu
perl 5.42.0 COMPILAT DE NOI pe laptop, cross-compilat pentru aarch64-linux-android.

Reteta de cross-compilare perl (toate capcanele dovedite):
- `perl-cross` 1.6.5 (versiunea 1.5.3 NU are patchset pentru 5.40/5.42 -> "No patchset found
  for perl5-5.42.2"; 1.6.5 are patchset pentru 5.42.0).
- configure cere EXPLICIT toate uneltele: `--with-cc --with-ar --with-ranlib --with-nm
  --with-objdump --with-readelf` (fara ele: "ERROR: Cannot find ar/readelf").
- `-Dd_futimes=undef -Dd_futimesat=undef -Dd_lchown=undef` - bionic nu are futimes/lchown
  (altfel: `doio.c: error: call to undeclared function 'futimes'`).
- **`-Dlibs='-ldl -lm'`** - esential pe Android: fara `-lm` explicit, modulele XS se linkeaza
  fara DT_NEEDED libm si la dlopen mor cu `cannot locate symbol "modf"` (dovedit: cu
  `LD_PRELOAD=/system/lib64/libm.so` mergeau; dupa rebuild cu -lm, POSIX.so are NEEDED libm).
- binarul iese linkat cu libperl STATIC (doar libc/libm/libdl) si are prefixul de pe device
  compilat in el -> isi gaseste singur @INC.
- `lib/perl5/5.42.0/aarch64-linux/auto/List/Util/Util.so` se linkeaza in build-ul intern fara
  -lm -> l-am relinkat manual cu `-lm` (altfel `use List::Util` pica).
- livrat: `assets/toolchain/perl` (55 MB, cu `pod/` taiat) + `jniLibs/arm64-v8a/libperl_exec.so`
  + symlink `files/tmp/perl`; `PERL5LIB=<ROOT>/perl/lib/perl5/5.42.0:<...>/aarch64-linux:<...>/site_perl`.

Tier-2 (in `assets/toolchain/deps`, static, cu `.pc` scrise cu prefixul DE PE TELEFON):
- zlib 1.3.1 (`libz.a`), libpng 1.6.44 (`libpng16.a`), freetype 2.13.3 (`libfreetype.a`),
  sqlite3 3.46.1 (`libsqlite3.a`, FTS5+JSON1+RTREE), zstd **1.5.7** (`libzstd.a`).

Doua bug-uri reale de pachet gasite de baterie si reparate:
- **zstandard** pica la build: `deps/include/zstd.h` era vechi (1.5.6) si umbrea header-ul din
  sdist -> `unknown type name 'ZSTD_FrameHeader'`. Fix: zstd 1.5.7 in deps.
- **cbor2** se instala "cu succes" dar FARA extensia C (`import cbor2._cbor2` ->
  ModuleNotFoundError): pachetul isi construieste extensia doar cu `CBOR2_BUILD_C_EXTENSION=1`.
  Fix: variabila adaugata in `env_vars()`.

Baterie de teste (16 pachete + test de link C), prin `run_toolchain_tool(action='pip_install')`
si verificare independenta in subproces nou: vezi tabelul din `readme.md` (Etapa 52).

### 8.4 Rezultatele bateriei pe `.assets_v192` (situatia la inchiderea sesiunii)

**Pachete care se compileaza si functioneaza pe device (verificate cu import/functionalitate
in subproces nou):** simplejson, MarkupSafe, cffi, msgpack, regex, lz4, kiwisolver, greenlet,
lxml, zstandard (10) + testul de link C pentru Tier-2 (sqlite3+libpng+freetype+zlib).

**Pachete care au aratat gauri REALE in toolchain (si fixurile aplicate):**
- zstandard -> header zstd vechi in deps (fix: zstd 1.5.7) -> acum OK.
- Pillow -> `LDSHARED` fara `_ldflags` + libs de imagini necerute la link
  (fix: LDSHARED complet + `-lm -ldl -lz -lpng16 -ljpeg -lfreetype`) -> **REZOLVAT: Pillow 12.3.0
  se compileaza pe device si functioneaza (PNG save/open, `_imaging.cpython-314-aarch64-linux-android.so`)**.
- duckdb -> `find_package(pybind11)` (fix: `_pybind11_dir()` extrage cmake-ul din zip +
  `-Dpybind11_DIR`) -> de re-verificat.
- apsw -> descarca surse la build si pica pe CA (de investigat in continuare).
- numpy 2.5.3 -> `ninja: FAILED: numpy/_core/__ufunc_api.c` in generarea metadatelor.
- grpcio -> `No module named '_multiprocessing'`: CPython-ul nostru nu are
  `_multiprocessing` (bionic nu are semafoare POSIX) -> orice build care face
  `import multiprocessing` cade. Necesita rebuild CPython cu suport de semafoare.
- cbor2 6.x -> accelerator RUST (setuptools-rust), nu C -> intra la FAZA 2 (Rust).

**Rust (FAZA 2) - de ce nu e facut in aceasta sesiune:** pachetul Termux `rust 1.98.1`
(122 MB deb / 548 MB instalat) + `libllvm` (165 MB) + `maturin` (inexistent in repo, trebuie
construit cu cargo) -> varianta curata e un bootstrap LA CERERE (agentul descarca toolchain-ul
doar cand primeste un pachet Rust), nu bundling in APK (APK-ul ar sari de la ~309 MB la ~1 GB).
