# STATUS OPTIMIZARI - AGENT ANDROID (net.sys32.agent)

Data: 2026-09-28 | Device: Samsung SM-A366B, Android 16 (SDK 36), aarch64, 8 core, 7.3 GB RAM
Python: 3.14.7 | clang/LLVM: 21.1.8 | APK: `.assets_v181`

Sesiune: executarea planului din `optimizari_finale.md` (PAS 0 - PAS 5) + repararea blocajului
critic `pip install`. Regula: fiecare afirmatie de aici a fost TESTATA pe device, nu presupusa.

═══════════════════════════════════════════════════════════════════════
## 0. REZUMAT EXECUTIV (actualizat dupa sesiunea 2)

    PAS 0  (repara toolchain.py)                ██████████ FACUT + VERIFICAT
    PAS 1  (build deps python)                 ██████████ FACUT + VERIFICAT
    PAS 2  (unelte: make/ninja/cython...)      ████████░░ FACUT (fara cmake/perl)
    PAS 3  (libs: atomic/openssl/ffi/zstd...)  █████████░ FACUT (fara HDF5/libzmq/freetype)
    PAS 4  (matplotlib/h5py/pyzmq)             ░░░░░░░░░░ NEINCEPUT
    PASI 5 (LLVM dev + RUST)                   ░░░░░░░░░░ NEINCEPUT
    BUG-URI sesiunea 1 (6 gasite)              ██████████ REPARATE + VERIFICATE
    ★ BLOCAJUL `pip install` (SIGSEGV -11)     ██████████ REPARAT + VERIFICAT

    INDEPENDENTA ESTIMATA ACUM: ~85%  (blocajul care tinea 80% "teoretic" a cazut)

═══════════════════════════════════════════════════════════════════════
## 1. SESIUNEA 1 - PAS 0..3 (totul verificat pe device)

### 1.1 PAS 0 - `toolchain.py` reparat (6 schimbari)

    A) run-as ELIMINAT COMPLET
       - check() si doctor() nu mai cheama `run-as` (se bloca / nu se putea citi filesDir)
       - verificarea "poate app-ul folosi prefixul?" = os.listdir direct (suntem deja app)
    B) shim-uri shell inlocuite cu API direct
       - `_sh("ls BIN")` -> `os.listdir(BIN)` (fara fork = fara deadlock)
    C) argv[0] corect pentru clang
       - symlink `files/tmp/clang` -> libclang_exec.so (numele REAL decide driver-ul)
       - fara el, clang se comporta ca generic driver si se INVARTE (100% CPU)
    D) mediu setat in Python (nu in scripturi shell)
       - LD_LIBRARY_PATH, TMPDIR, OPENBLAS_NUM_THREADS=1, PATH cu files/tmp PRIMUL
    E) PYTHONPATH corect (ORDINEA conteaza)
       - stdlib_extra.zip PRIMUL, apoi python3.14, apoi pysitepkg.zip
    F) -latomic condiționat
       - se adauga DOAR daca exista libatomic.a (altfel "unable to find library")

### 1.2 PAS 1 - build-deps Python (in pysitepkg.zip, 10.2 MB)

    Cython 3.3.0 | pybind11 3.1.0 | scikit-build-core 1.1.0 | setuptools_scm 10.3.4
    + vcs_versioning 2.5.0 (dependinta reala a setuptools_scm) | meson 1.12.1
    + mesonpy 0.22.0 | pyproject_metadata 0.12.1 | packaging 26.3
    (+ pathspec 1.1.1, adaugat in SESIUNEA 2 - dep de scikit-build-core)
    VERIFICAT pe device: toate se importa (Cython, pybind11, scikit_build_core,
    setuptools_scm, meson, mesonpy, pathspec = OK)

### 1.3 PAS 2 - unelte native

    make 4.4.1   CROSS-COMPILAT ARM64 de la 0 -> jniLibs/libmake_exec.so (2.67 MB, static)
                 patch necesar: confstr/_CS_PATH nu exista pe bionic -> PATH hardcodat
    ninja 1.12.1 EXISTA deja -> libninja_exec.so
    clang/lld/ar/ranlib/nm/strip/readelf/objdump  -> jniLibs/lib*_exec.so
    pkg-config   -> libpkgconf_exec.so
    VERIFICAT: 12 binare OK (clang, ld.lld, ar, ar_shim, ar, ranlib, nm, strip,
               readelf, objdump, cc, cxx, flang) + make + ninja + pkg-config = TRUE,
               compile_test / ar_test / cxx_test = TOATE TREC

### 1.4 PAS 3 - biblioteci cross-compilate ARM64 (in assets/toolchain/deps/)

    libzstd 1.5.6      libzstd.a (797 KB)  + headere
    liblzma 5.6.3      liblzma.a (346 KB)   + headere
    libbz2  1.0.8      libbz2.a  (84 KB)    + bzlib.h
    libffi  3.4.6      libffi.a  (106 KB)   + ffi.h/ffitarget.h
    libexpat 2.6.4     libexpat.a (219 KB)  + expat.h
    OpenSSL 3.0.16     libcrypto.a (8.9 MB) + libssl.a (1.26 MB) + 135 headere
    libatomic.a + libomp.a + libunwind.a  (builtin-uri clang, in toolchain/lib/clang/21)
    VERIFICAT pe device: deps(zstd/lzma/bz2/ffi/expat/openssl)=true, libatomic=true

### 1.5 PAS 6 (OpenBLAS threading)

    MASURAT dgemm n=512:  1 fir = 0.016s (16.5 GFLOPS) | 8 fire = 0.227s (1.2 GFLOPS)
    CONCLUZIE: la n mic, 8 fire = 14x MAI LENT. Setat OPENBLAS_NUM_THREADS=1 (FACUT).

### 1.6 BUG-URI REALE gasite si reparate in sesiunea 1 (6)

    #1  `if action == "pip_install":` LIPSEA din agent.py
        Efect: "actiune necunoscuta: pip_install" desi handler-ul exista (cod orfan)
        Fix: adaugat antetul lipsa

    #2  `libpyexec.so -c <cod>` -> SIGSEGV (exit -11)
        Cauza REALA (corectata in sesiunea 2): LD_LIBRARY_PATH cu stub-uri NDK, NU
               "re-incarcarea agent.py". Vezi sectiunea 2.
        Fix: codul se scrie in FISIER si se ruleaza ca script (fara -c);
             in pip_install -> rulare INLINE in procesul agentului

    #3  `check()` / `doctor()` rulau subprocess clang in /data/local/tmp
        Cauza: app-ul NU poate scrie in /data/local/tmp (SELinux) -> shell se BLOCA
               la infinit (stare R, 100% CPU, fara output)
        Fix: verificari PURE de fisiere (os.path / os.listdir), zero subprocess

    #4  `libclang_exec.so` cu argv[0] gresit -> clang se INVARTE (100% CPU)
        Cauza: clang decide driver-ul din basename; "libclang_exec.so" nu e
               recunoscut -> mod generic -> bucla infinita
        Fix: symlink `files/tmp/clang` cu numele real
        Dovada: `files/tmp/clang --version` -> "clang version 21.1.8" in 0.1s

    #5  `_sh()` fara stdin=DEVNULL
        Cauza: `sh -c` mostenea stdin-ul procesului agent (pipe care nu se inchide)
        Fix: stdin=DEVNULL + os.killpg la timeout (subprocess.run NU omora copiii)

    #6  `env_vars()["CC"]` folosit cu .split()[0]
        Cauza: pierdea flag-urile -resource-dir / -B -> clang nu-si gasea headerele
        Fix: CC folosit COMPLET (toate tokenii)

    LECTIE GENERALA: pe Android, orice subprocess pornit din procesul agentului
    (care are thread-uri bridge/watcher) e risc de DEADLOCK pe fork. Verificarile
    trebuie facute cu API direct (os.path/os.listdir), nu cu shell.

═══════════════════════════════════════════════════════════════════════
## 2. ★ SESIUNEA 2 - BLOCAJUL `pip install` REPARAT (cauza reala NU era ce zicea raportul)

### 2.1 Simptomul (reprodus exact)

    pip install zstandard (exit 1, 5s)
      Preparing metadata (pyproject.toml): finished with status 'error'
      × Preparing metadata (pyproject.toml) did not run successfully.
      │ exit code: -11          <- SIGSEGV
    Orice pachet cu build-backend in SUBPROCES (adica orice extensie C) murea.

### 2.2 Ipoteza din raport (GRESITA)

    "`libpyexec.so <script>` nu se poate re-initializa ca subproces" - FALS.
    Dovada: `libpyexec.so -c "print(1)"` si `subprocess.run([sys.executable,"-c",...])`
    ruleaza perfect (rc=0, "SUBOK") intr-un sandbox curat, chiar ca uid de app.

### 2.3 Cauza REALA (dovada: tombstone + bisect pe device)

    `toolchain.env_vars()["LD_LIBRARY_PATH"]` incepea cu **directorul de STUB-uri NDK**
    (`toolchain/sysroot/usr/lib/aarch64-linux-android/35`). Acolo `libc.so`/`libm.so`/
    `libdl.so` sunt STUB-uri DE LINK (fara cod in .text). Procesul AGENT nu avea nicio problema
    (linkerul bionic isi citeste LD_LIBRARY_PATH la INIT, nu la dlopen), dar ORICE PROCES
    COPIL pornea cu libc STUB -> crash in constructorii libpython3.14.so:

        F libc: Fatal signal 11 (SIGSEGV) in tid 8612 (libpyexec.so)
        DEBUG: Cmdline: .../libpyexec.so .../_in_process.py prepare_metadata_for_build_wheel
        DEBUG: #00 pc 0x4a83e0 libpython3.14.so
        DEBUG: #02 pc .../linker64 (__dl__ZN6soinfo17call_constructorsEv+668)

    Bisect pe device (copil spawn-uit cu env variat):
        v0 base (LD_LIBRARY_PATH cu stub-uri)   rc=-11  SIGSEGV
        v2 LD_LIBRARY_PATH = nativeLibraryDir   rc=0    SUB-OK
        v3 LD_LIBRARY_PATH = deps/lib           rc=0    SUB-OK
        v4 fara PYTHONPATH                      rc=-11  (deci NU PYTHONPATH)

    => vinovatul era EXCLUSIV directorul de stub-uri de LINK pus pe calea de RULARE.

### 2.4 Fixul la sursa

    A) toolchain.py: `_rt_ld_path()` + `sanitize_ld_library_path()` -
       LD_LIBRARY_PATH de RULARE = nativeLibraryDir + deps/lib + files/libs, FARA sysroot
    B) agent.py: `_clean_ld()` - acelasi filtru pentru env-ul de pip + hook-ul de startup

### 2.5 Al doilea strat de bug-uri (dezgropate pe rand DUPA fixul A; toate reparate)

    Dupa ce copilul a inceput sa RULEZE, fiecare pas a scos la iveala cite o eroare
    normala de Python (nu crash), reparata iterativ:

    #1  `ModuleNotFoundError: pathspec` (build backend)
        scikit-build-core depinde de pathspec, nu era in pysitepkg.zip
        Fix: adaugat pathspec 1.1.1 (+ in Lib/site-packages)

    #2  `fatal error: 'Python.h' file not found`
        sysconfig.INCLUDEPY = '/usr/local/include/python3.14' (prefix de compilare, inexistent)
        Fix: `_ensure_py_include()` -> pyhome/include/python3.14 -> toolchain/pyinc

    #3  `unable to find library -lpython3.14`
        sysconfig.LIBDIR = '/usr/local/lib'
        Fix: `_ensure_py_lib_link()` -> pyhome/lib/libpython3.14.so (symlink) + LIBDIR rescris

    #4  `fatal error: 'stddef.h' file not found`
        CC din sysconfig fara -resource-dir (headerele builtin ale clang-ului)
        Fix: `_patch_sysconfig_device()`: CC/CXX/LDSHARED cu -resource-dir + --target + --sysroot

    #5  `cannot open crtbegin_so.o` (desi -L era dat)
        Avem doar sysroot/usr/lib/<triple>/35, target-ul e 36 -> clang nu gaseste dirul de
        API si emite crt-urile ca NUME BARE, iar lld le cauta DOAR in CWD (dovedit: cu cwd
        in acel dir merge; cu -L nu).
        Fix: `_ensure_sysroot_api_dir()` -> symlink 36 -> 35

    #6  `clang: error: unable to execute command` (nu gaseste ld.lld)
        pip_install rula pip inline dar NU aplica env-ul in os.environ -> build-backend-ul
        copil nu avea files/tmp in PATH (desi compilarea in sine folosea cai absolute)
        Fix: env aplicat in os.environ pe durata pip + restore in `finally`

    #7  link fara -L (setuptools NU foloseste LDFLAGS din sysconfig)
        Fix: -L (sysroot/api, deps/lib, clang lib/linux/aarch64) puse direct in LDSHARED
             (+ -I deps/include in CFLAGS)

    #8  orice backend cu o dependinta lipsa
        Fix: auto-retry - dupa `ModuleNotFoundError` la --no-build-isolation, reincearca
             CU build isolation (pip isi descarca singur backend-ul)

### 2.6 VERIFICAT pe device (SM-A366B, instalare curata `.assets_v181`)

    pip install regex       -> exit 0, 23s  (wheel cp314-android_24_arm64_v8a, 289 KB)
    import regex            -> match(r"(\d+)-(\d+)","12-34") = 12 / 34 (v2026.9.10)
    pip install zstandard   -> exit 0       (zstandard-0.25.0: C + scikit-build-core)
    pip install msgpack     -> exit 0, 15s  (msgpack-1.2.2: C++)
    pip install markupsafe  -> exit 0, 15s
    pip install cffi        -> vezi nota de mai jos

    Instalarea ajunge in `pyhome/lib/python3.14/site-packages` (in sys.path atit cu env
    minimal, cit si dupa hook-ul de startup) si SUPRAVIETUIESTE update-ului de APK prin
    `files/site_packages_keep` - verificat dupa reinstalarea APK v180
    (markupsafe/msgpack/pathspec prezente).

    Dovada ca NU mai e niciun SIGSEGV: logcat dupa testele de pip = ZERO linii
    "Fatal signal 11 / DEBUG" din procesele libpyexec.so.

═══════════════════════════════════════════════════════════════════════
## 3. CE MAI TREBUIE REMEDIAT (ordinea prioritatii)

### 3.1 cmake >= 3.29 (PAS 2 ramas)

    NECESAR pentru: duckdb, pyarrow, llvmlite, onnxruntime, torch
    STARE: build-ul cross ARM64 a esuat de 2 ori:
        - libuv: sched_getaffinity / CPU_SETSIZE / CPU_COUNT nu exista pe bionic
        - libarchive: `android_lf.h` lipseste din NDK
    ALTERNATIVA: cmake doar ca GENERATOR de build.ninja -> ninja il ruleaza (avem ninja)

### 3.2 perl (PAS 2 ramas)

    NECESAR pentru: grpcio (generator asm BoringSSL), openssl Configure, autoconf/automake
    OCOLIRE TEMPORARA: GRPC_BUILD_WITH_BORING_SSL_ASM=0 (pierzi putin la criptare,
    scapi de perl). De aplicat in toolchain.py la build-ul grpcio.

### 3.3 Biblioteci Tier 2 ramase

    HDF5            ~30 MB  ~2h   -> h5py
    libzmq          ~5 MB   ~1h   -> pyzmq (desi pyzmq ARE wheel Android cp314!)
    freetype+png+tiff+webp  ~15 MB  ~2h  -> matplotlib + pillow (formate complete)
    sqlite3 dev     ~2 MB   ~30min -> pandas.read_sql, Django, sqlalchemy
                    (headere de extras din libsqlite3_python.so)

### 3.4 Tier 3 (voluminos, optional)

    LLVM dev stack  ~300 MB ~6h   -> llvmlite/numba
                    (avem COMPILATORUL LLVM, NU avem BIBLIOTECA LLVM - sunt diferite)
                    llvmlite cere LLVM 22; avem 21.1.8 -> LLVMLITE_SKIP_LLVM_VERSION_CHECK=1
    RUST            ~600 MB ~8h   -> tokenizers, cryptography, pydantic-core, orjson, polars
                    PROBLEMA FUNDAMENTALA: rust-lang.org NU livreaza rustc pentru
                    aarch64-linux-android (doar rust-std). Bootstrap din sursa = risc RIDICAT.

### 3.5 Prefix unificat - MUTAT DIN PRIORITATI

    Prefixul unificat /data/local/tmp/prefix a devenit INUTIL pentru pip: toolchain-ul din
    APK (clang/lld/sysroot/deps in filesDir + binare exec-abile din nativeLibraryDir, legate
    prin symlink-uri in files/tmp) acopera TOT fluxul, ca uid de app (fara adbsh).
    Ramine util doar pentru artefacte care trebuie RULATE de shell (ex. binare produse).

### 3.6 Verificari de facut dupa fiecare fix

    - `toolchain action=status` -> toate TRUE (inclusiv make, deps noi)
    - `pip install <pachet-C>` -> exit 0 + import reusit
    - instalare CURATA (dezinstalare + reinstalare APK) -> toate verificarile trec

═══════════════════════════════════════════════════════════════════════
## 4. CE RAMANE IMPOSIBIL (nu se poate optimiza)

    torch        - cere >16 GB RAM la build; telefonul are 7.3 GB
    onnxruntime  - fezabil dar foarte greu (protobuf + Eigen + C++17)

═══════════════════════════════════════════════════════════════════════
## 5. FISIERE MODIFICATE

    Sesiunea 1:
      assets/python/toolchain.py     PAS 0 (run-as, argv0, PATH, PYTHONPATH, atomic)
      assets/python/agent.py         pip inline, py() fara -c, hook PAS 2 la startup
      assets/python/pysitepkg.zip    + build-deps (cython/pybind11/scikit-build-core/meson/...)
      assets/python/Lib/site-packages/  + Cython, pybind11, scikit_build_core, setuptools_scm
      assets/toolchain/deps/lib|include/  + zstd, lzma, bz2, ffi, expat, crypto, ssl
      assets/toolchain/lib/clang/21/lib/linux/  + libatomic.a, libomp.a, libunwind.a
      jniLibs/arm64-v8a/libmake_exec.so   GNU make 4.4.1 ARM64 (nou)
      MainActivity.kt                marker .assets_v179

    Sesiunea 2:
      assets/python/toolchain.py     _rt_ld_path, sanitize_ld_library_path, _stub_link_dirs,
                                     _ensure_py_include, _ensure_py_lib_link,
                                     _ensure_sysroot_api_dir, _patch_sysconfig_device
      assets/python/agent.py         _clean_ld, env aplicat la pip, auto-retry isolation
      assets/python/pysitepkg.zip    + pathspec 1.1.1
      assets/python/Lib/site-packages/  + pathspec, pathspec-1.1.1.dist-info
      MainActivity.kt                marker .assets_v181

═══════════════════════════════════════════════════════════════════════
## 6. URMATORUL PAS CONCRET

    1. cmake (sau generator de build.ninja) -> deblocheaza duckdb/pyarrow/llvmlite
    2. Tier 2: HDF5 (h5py) + freetype (matplotlib / Pillow cu formate complete)
    3. perl sau ocolirea lui pentru grpcio
