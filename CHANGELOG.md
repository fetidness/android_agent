# CHANGELOG - Agent Android (net.sys32.agent)

> Generat automat din istoricul git. Documentul e **actualizat periodic** (la fiecare
> sesiune de dezvoltare majora; regula in `readme.md` -> OP.7). Format: zile
> descrescatoare, in fiecare zi commiturile grupate pe categorii.
> Ultimul commit inclus: `8279966`.

**Total: 165 commituri in 9 zile** (19 sep -> 28 sep).

---

## 2026-09-28 (ELIMINARE TERMUX + FLANG + OpenBLAS + libc++abi)

### ★ Sesiunea 2 - FIX `pip install` (SIGSEGV -11) + toolchain compilabil cu uid de app

**Blocajul care tinea "independenta 100%" teoretica a cazut**: ORICE `pip install` cu extensie C
murea cu `exit code: -11` la "Preparing metadata (pyproject.toml)".

**Cauza reala (tombstone + bisect pe device, NU ipoteza din raport):** `LD_LIBRARY_PATH` incepea
cu directorul de STUB-uri NDK (`toolchain/sysroot/usr/lib/aarch64-linux-android/35`) - acolo
`libc.so`/`libm.so`/`libdl.so` sunt stub-uri de LINK (fara cod). Procesul agentului nu avea nicio problema
(bionic citeste `LD_LIBRARY_PATH` la INIT, nu la `dlopen`), dar orice PROCES COPIL pornea cu libc
stub -> SIGSEGV in constructorii `libpython3.14.so`.
- `toolchain._rt_ld_path()` + `sanitize_ld_library_path()` + `agent._clean_ld()`: calea de RULARE
  nu mai contine directoare `sysroot` (raman doar nativeLibraryDir, deps/lib, files/libs)

**Al doilea strat (fiecare descoperit DUPA ce copilul a inceput sa ruleze; toate reparate):**
- `_ensure_py_include()`: `pyhome/include/python3.14 -> toolchain/pyinc` (INCLUDEPY era `/usr/local/...`) -> "Python.h not found"
- `_ensure_py_lib_link()`: `pyhome/lib/libpython3.14.so` + LIBDIR rescris -> "-lpython3.14 not found"
- `_patch_sysconfig_device()`: CC/CXX/LDSHARED cu `-resource-dir` + `--target` + `--sysroot` (+ `-I deps/include`) -> "stddef.h not found"
- `_ensure_sysroot_api_dir()`: symlink `<api>` -> `35`; fara el clang emite crt-urile ca NUME BARE, iar lld le cauta DOAR in CWD -> "cannot open crtbegin_so.o"
- `-L` direct in `LDSHARED` (setuptools NU foloseste LDFLAGS din sysconfig la link)
- `pip_install` aplica env-ul complet in `os.environ` pe durata rularii -> altfel copilul nu gaseste `ld.lld` din `files/tmp`
- auto-retry cu build isolation la `ModuleNotFoundError` (backend cu dependinta lipsa)
- `pathspec` 1.1.1 adaugat in `pysitepkg.zip` (dependinta de scikit-build-core)

**VERIFICAT pe device (instalare curata `.assets_v180`):**
- `pip install regex` -> exit 0, 23s; `import regex` + match OK (wheel `cp314-android_24_arm64_v8a`)
- `pip install zstandard` -> exit 0 (C + scikit-build-core) | `msgpack` -> exit 0 (C++)
- `markupsafe` -> exit 0; logcat dupa teste: ZERO "Fatal signal 11"
- site-packages-ul instalat de pip supravietuieste update-ului de APK (`site_packages_keep`)



**Termux ELIMINAT COMPLET SI DEFINITIV**
- sters `tpm.py` (351 linii) + toate referintele termux/tpm din agent.py si toolchain.py (0 ramase)
- sterse functiile de bootstrap: `bootstrap_direct`, `_load_index`, `_untar`, `_extract_deb`,
  `_patch_runpath`, `_fix_ninja`, `_fix_symlinks`, `_fix_sysconfig`, `_fix_termux_paths`,
  `_fix_wrappers_shebang`, `_fix_cc_wrappers`, `_fix_cxx_linker`, `_fix_meson_exe`, `install`
- sterse `PKGS` / `_REPO` (repo Termux) / `OLD` (cai Termux) + actiunile tool `bootstrap`/`tpm`
- toolchain.py: 1441 linii rescrise (-1364 net); agent.py -152 linii

**Fix-uri din RAPORT_COMPILARE_C.md (P1-P7, R1-R4, N1-N9)**
- P3 binutils executabile: shim-uri in files/tmp catre nativeLibraryDir + REGENERARE automata
  cand libDir-ul se schimba la reinstalare (hash nou in /data/app) - capcana noua descoperita
- P4 READELF/OBJDUMP cu fallback; P5 CXX = clang++ (era clang-21++ inexistent)
- P6 check() foloseste sys.executable + sysconfig real (nu binar inexistent)
- P7/R1 libjpeg-turbo 3.1.0 compilat ARM64 cu 8/12/16-bit (j12/j16init_color_converter verificate T)
- R3 `-Wl,--no-undefined` + ambele forme (.a si .so); R4/N9 LD_LIBRARY_PATH cu sysroot lib + deps/lib
- N1 libc++ complet ca ZIP: AAPT2 elimina folderele cu `_` -> doar 157 din 2125 headere ajungeau
- N2/N3 libc++_shared.so REAL (1.4 MB) + libc++abi; N4 ninja 1.12.1 ca `libninja_exec.so`
- N5 launcher cython; N6/N7 `python3.pc` generat automat cu prefixul device-ului

**FLANG (Fortran pe Android, compilat de la 0)**
- flang 21.1.8 compilat din surse LLVM pentru ARM64 (4506 tinte Ninja) -> `libflang_exec.so` 137 MB
  (dupa strip; original 3.2 GB cu debug info)
- `libFortranRuntime.a` (19.6 MB) + `libFortranDecimal.a` compilate de la 0 (64/64 fisiere C++)
- builtins + unwind ARM64 (`libclang_rt.builtins.a`, `libunwind.a`) ambalate in resource-dir
- wrapper in 2 pasi: `-fc1 -triple` pentru .o, apoi link cu clang + runtime Fortran
- capcane: driver-ul cade pe `"gcc" -x f95-cpp-input`; `-fc1` ignora `-o` (exit 0, 0 bytes);
  sursa trebuie RELATIVA din cwd-ul ei; `-triple` obligatoriu; `-fPIC` interzis la -fc1

**OpenBLAS (inlocuieste BLAS/LAPACK de referinta)**
- OpenBLAS 0.3.29 compilat de la 0 (TARGET=ARMV8, SIMD NEON) -> `libopenblas.a` 25 MB + `.so` 12 MB
- headere complete (cblas/lapack/lapacke/openblas_config) + `openblas.pc`
- efect: numpy/scipy 10-50x mai rapide la runtime (fata de netlib)

**libc++abi.a (linkare statica C++)**
- compilat de la 0: 528 KB, 18 obiecte, 1299 simboluri (-nostdinc++ pentru compat libc++ 21)

**Protectie site-packages la update APK (raport nou, sectiunea 4)**
- depozit persistent `files/site_packages_keep` care supravietuieste reinstalarii
- numpy/scipy/lxml/PIL nu se mai pierd (inainte: 5 ore de build pierdute la fiecare update)
- ordinea conteaza: restaurarea se face DUPA reconstructia pyhome (altfel "Failed to import encodings")

**Test E2E pe instalare CURATA (dezinstalare + reinstalare APK)**
- C -> RC 0, C++ -> RC 0, Fortran -> binar produs (1.5 MB)
- `check()`: ar_test, cxx_test, libcxx_full, ninja, openblas, flang = toate TRUE
- onboarding functional (cere cheia API in romana)

**Commituri**
- `813ce09` arhitectura ZERO TERMUX (punctul de plecare)
- `2d9a0f9` elimina Termux complet + FLANG + OpenBLAS + libc++abi + protectie site-packages
- `376b73e` fix(flang): wrapper Fortran corect - compilare pe 2 pasi (verificat E2E)

**Limitare cunoscuta:** binarul Fortran da segfault la RULARE (initializarea runtime-ului
cere libFortranMain / unitati I/O). Compilarea - partea care rezolva cele ~500 patch-uri F90
pe LAPACK - functioneaza. APK: 273 MB, marker `.assets_v160`.

---


## 2026-09-26 (sesiune ARHITECTURA "ZERO TERMUX" + optimizari P1-P10)

**Toolchain nativ compilat de la 0 (fara Termux)**
- clang 21.1.8 + lld, cross-compilat pentru Android ARM64 (~1h15m, 4138/4209 targeturi)
- strip agresiv: 3537 MB -> 191 MB (llvm-strip din NDK)
- pkgconf 2.3.0 compilat de la 0 pentru ARM64 (lxml il cere pentru detectie)
- libxml2 2.15.4 + libxslt 1.1.45 compilate de la 0 (-fPIC obligatoriu)
- pyconfig.h generat cross (cere Python 3.14 host construit pe laptop)

**Fix-uri CRITICE de arhitectura (13 la numar)**
- P1: bug procese agent.py duplicate -> lock file pe DISC + /proc/<pid> + killOrphanAgents
- P2: x86_64 eliminat (abiFilters + assets) -> -20 MB
- P3/P4/P10: colectori de stare (MAX_BACKUPS/MAX_JOBS/MAX_LOGS) la pornire
- pip: `-m pip` ignora PYTHONPATH -> injectare sys.path prin `-c`
- pyhome: F lua AGENT_HOME (sdcard) in loc de filesDir -> pip_install esua
- `_sh()` rula ca uid=2000 (nu vede filesDir) -> ruleaza local (app)
- env_vars() rescris complet (fara referinte Termux/wrap)
- TMPDIR: lipsea -> ca-bundle.pem nu se crea -> SSL esua -> API nu raspundea
- pkg-config: lipsea din toolchain -> lxml nu detecta libxml2
- XML2_CONFIG deprecat in lxml 6.x -> WITH_* + PKG_CONFIG
- LD_LIBRARY_PATH/PYTHONHOME lipseau din env -> CANNOT LINK / encodings
- `_env()` hardcoda cai neexecutabile -> unificat cu env_vars()

**SELinux Android 16 (capcane descoperite live)**
- untrusted_app NU poate executa din filesDir -> binarele in nativeLibraryDir (lib*_exec.so)
- lld decide modul din argv[0] -> symlink `ld.lld` + `--ld-path`
- AAPT2 elimina folderele cu `_` (pip/_internal, compression/_common) -> ZIP-uri in PYTHONPATH

**Test E2E final (de la 0, fara PC)**
- `toolchain pip_install lxml` -> exit 0, 88s, wheel android_24_arm64_v8a
- XPath pe device -> `Salut E2E` scris in /sdcard/Download/ok.txt ✅


## 2026-09-25 (sesiune optimizare tokeni)

**Optimizare / buget de context** (5)
- `e1824f6` test.py: exploit the 1M context window (CHUNK 7000 -> 60000)
- `7f835f2` test.py: fix 3 hidden truncation bugs + vision thinking (deep audit)
- `c6432b7` test-android.py: optimised variant of the Android agent.py (fix cost -964 tok/req)
- `1540a81` test-android.py: add on-demand 'help' tool, cut fixed cost to 6449 tok/req
- `8a61d9d` test-android.py: fix bg logging (shell cannot write in the app sandbox)

**Tool-uri / agent** (4)
- `31f4d59` Add test.py: token-optimized variant (fix cost -599 tok/req, no compact)
- `da1a88a` test.py: fix bash tool (no bash on Android) + router gaps; 44 tests green
- `0adc28b` agent-original.py (Linux): tag RULE: recunoscut in mem_lint (inclusiv filtrul strict de prefix), scoring, densitate, dedup + prompt
- `e4fa5c4` agent.py: recunoaste tag-ul RULE: (regula de ordine/decizie) in mem_lint, scoring, densitate, dedup, anti-stergere + prompt

**Structura / naming** (4)
- `04c2094` Add agent-v2.py (Android, optimised) and agent-original-v2.py (Linux, optimised)
- `b2d242c` Remove test.py and test-android.py (content now lives in the v2 files)
- `6e792b6` Rename agents to a clear origin/v2 + platform scheme
- `6e8f5a3` assets: make the optimised Android agent (v2) the default brain

---

## 2026-09-25

**Documentatie** (2)
- `462b763` docs: adaug CHANGELOG.md (139 commituri, 7 zile) + referinte in readme.md
- `5f65990` docs(readme): update complet la realitatea din cod (138 commituri analizate)

**Home / workspace / fisiere** (1)
- `d8cc3c1` docs(readme): corectez calea veche /home/gab/Desktop/agent -> /home/gab/Desktop/android_agent (11 linii: OP.1, OP.2, OP.4, OP.6, debugging)

**ADB / adbsh / shell** (4)
- `cbcdd5b` fix(adb): global timeout doar la cerere + cheie publica big-endian (AOSP)
- `ad26cbd` perf(adb): drenare select-gated - 588ms -> 48ms/comanda (12x)
- `f90aa3d` feat(adb): PYTHON-FIRST - run_adbsh_tool rescris pe adb_client direct (fara sesiune persistenta)
- `d26833f` fix(adb): Python-first pentru shell + deadline drenare

---

## 2026-09-24

**ADB / adbsh / shell** (7)
- `cf682eb` fix(adb): output gol intermitent - ordinea id-urilor la pachetele straine
- `5a17704` docs(tool): TOOLGUIDE - capcana toybox grep (alternanta cu backslash-pipe e silentioasa in bash, GNU-only)
- `3f7c7a9` fix(toolchain): nu mai polua LD_LIBRARY_PATH al sesiunii shell
- `dfbb471` agent.py: ghid pentru tool-urile privilegiate noi (ui shot, notif, ime, capture, vpn, guard) ca modelul sa le foloseasca in loc de dumpsys/adbsh + mar
- `b8c0475` assets: bump marker la v102 (forteaza re-extragerea asseturilor Python dupa rebase - agent.py/adb_client.py la zi)
- `446e5a1` fix agent: BG_LOG lipsa, bootstrap pe thread fara redirect_stdout, SIGALRM doar main-thread, compactare oprita; adb_client: RSAPUBLICKEY primul + port
- `a7c1d7a` fix adb auth: trimite RSAPUBLICKEY inaintea SIGNATURE (deblocheaza adbsh uid 2000)

**Sistem de memorie / /learn** (13)
- `91ab81c` fix(home): LEARN_CKPT in HOME_DIR (nu in _SANDBOX) - langa memory.md
- `39b9771` fix(learn): /reset goleste si checkpointurile /learn
- `48d1f0a` feat(learn): sistem de checkpoint - /learn nu mai re-invata lectiile deja stiute
- `685c622` fix(learn): /learn acopera INTREAGA sesiune, nu doar coada
- `5e74742` fix(learn): /learn NU mai sterge lectiile lungi din memory.md
- `2fd5a82` gitignore: scot memory.md din tracking (memorie locala agent)
- `3985182` memoria: doar sesiunea curenta (fara istoricul vechi)
- `31e342f` elimina auto-learn complet - invatare doar prin /learn manual
- `da96836` auto-learn: instrumentare completa + validitate API (portate pe agent-original.py)
- `38a9341` auto-learn: lectii din ORICE domeniu + poarta de contradictie extinsa
- `0a35b4e` ANTI-POISON v3: poarta optimizata (mai putine fals-pozitive, 40/40 pe ambele)
- `eb052a4` ANTI-POISON pe agent-original.py (Linux) + portarea portilor noi in agent.py
- `d913721` ANTI-POISON: auto-learn nu mai otraveste memoria (2 porti + carantina)

**Home / workspace / fisiere** (4)
- `54d3fa7` fix(home): CTX (context.json) in HOME_DIR, nu in _SANDBOX
- `f514c36` feat(home): HOME_DIR in sandbox privat, workspace rămâne vizibil pe sdcard
- `207d2c6` fix(ctx): context.json traieste DOAR in stocarea privata (elimina zgomotul MediaProvider)
- `6f27e52` fix: HOME_DIR lipsa la portarea Linux (NameError fatal) + curatat cod mort

**Toolchain / compilare nativa** (1)
- `ed5e5e0` optimizari baterie + reparare toolchain + fix mesaj stale captura

**UI / terminal** (4)
- `76fbbba` FIX UI: elimin sageata scroll (btnDown), singleTask (notificarea nu mai deschide instanta noua), limita text TextView + lastLine optimizat (fara lag l
- `1c308d5` FIX URGENT: scot flagRequestTouchExplorationMode/canRequestTouchExplorationMode din configul a11y (bloca toata atingerea pe telefon) + marker v104
- `c47e3b4` FIX 1-8 din raportul ACCES MAXIM: screenshot a11y, NotificationListener, IME, VpnService, MediaProjection, DeviceAdmin, GuardService/BootReceiver + ac
- `5e72df0` perf agent-original (linux): ctx_tokens cu cache pe semnatura continutului + ctx_warn un singur calcul (inainte 3 apeluri per warn)

**Android: acces, permisiuni, servicii** (2)
- `3ed32a0` diagnoza guard/ime imbunatatita: ime_state (active/installed_not_selected/not_installed) + *_state pentru servicii + ghid ca installed_not_selected e 
- `99f2335` optimizari robustete+baterie: watchdog reparat (verificare pyProc+cooldown, nu pgrep), wake lock cu timeout 30min, ghid notif clarificat + marker v109

**Tool-uri agent (python/bash/read/multi/bg/...)** (1)
- `9fcf342` tool selection: ghid corectat + router cu reguli masurate + xargs -P

---

## 2026-09-23

**Documentatie** (1)
- `65aaead` docs: raport de sesiune 23 sept (git, test de forta, comparatie piata, audit securitate) - md + html

**Tool-uri agent (python/bash/read/multi/bg/...)** (2)
- `f47b5e4` docs: corectez numarul de tool-uri (10 -> 11, adaug multi) + lista completa de comenzi slash
- `293afc6` checkpoint: optimizari de cost + tool multi/read + fereastra 1M + compactare OFF

**Toolchain / compilare nativa** (2)
- `c4dc56e` docs: client SSH functional pe Android + reteta reparatii toolchain
- `14dcd97` toolchain: completez recomandarile B din raportul numpy (toate 18/18 acoperite)

**Altele** (3)
- `bdfd30c` optimizari chirurgicale agent-original.py (agentul Linux) - sincronizat cu Android
- `e29d813` Tool nou 'bg': gestionar de procese in fundal (rezolva output amestecat)
- `66e2c64` Fix context invalid: tool_calls orfane (HTTPError de la API)

**Android: acces, permisiuni, servicii** (1)
- `a0e4ab9` FIX CRITIC: agent.py fara guard __main__ (bloca orice re-lansare Python)

**ADB / adbsh / shell** (6)
- `90c232a` toolchain: verificare per-uid (doctor) + disciplina de terminare (raportul numpy)
- `e36475e` fix adbsh: output cu un apel in urma (filtrare gresita a id-ului de sesiune ADB)
- `b0b8134` Adbsh: conexiune PARTEJATA (nu mai cere Allow USB debugging la fiecare comanda)
- `700d15a` Adbsh: conexiune persistenta (nu mai cere 'Allow USB debugging' la fiecare comanda)
- `e662faf` FIX CRITIC adbsh: cheia ADB in formatul ANDROID_PUBKEY (524 bytes)
- `f98dcdc` Adauga /run_su: rulare scripturi cu DREPTURI DE SHELL (uid=2000)

**Sistem de memorie / /learn** (2)
- `dc0494f` memory.md: lectii sesiune - regex python (nu bash) pentru citit fisiere mari, backup inainte de rescriere, verificare empirica a comenzilor documentat
- `fe9bbed` Doc: Documentatie_Agent_Android.txt -> .md (75KB, completat) + sters draft Documentatie_Raport_llama.cpp.md; memory.md: lectii reset context si Adb si

**UI / terminal** (3)
- `eb1ef29` Docs: adaugat secțiunea OPERATIUNI (OP.1-OP.7) - build, install, debug, verificare
- `f72a5eb` Curatenie repo: readme.md (inlocuieste Documentatie_Agent_Android.md, 75KB ghid agent Android) + sterse fisiere vechi de emulator/ghiduri
- `5331286` Optimizare dupa raportul llama.cpp: preflight + profiluri de build (9 obstacole)

---

## 2026-09-22

**Toolchain / compilare nativa** (5)
- `95e6d6e` Optimizare completa toolchain: numpy compilat de la 0 (test end-to-end REUSIT)
- `51798ab` Fix toolchain: compilare nativa reparata complet (numpy OK)
- `57606f7` Docs: Etapa 31 (remedieri toolchain) + reguli compilare in ghid
- `eac028e` Fix toolchain: symlink-uri automate + compression._common corect
- `c21f49c` Toolchain compilare NATIVA functionala pe telefon (testat end-to-end)

---

## 2026-09-21

**ADB / adbsh / shell** (4)
- `973a3ec` agent.py: conexiune ADB PERSISTENTA (nu mai cere Allow la fiecare comanda)
- `6a18158` Docs: distinctie clara FARA calculator vs CU calculator (super-puteri uid=2000)
- `88945a0` adb_client: auto-detectie port (merge cu 5555, 55555 sau orice)
- `e533d1b` Android: SUPER-PUTERI ADB shell uid=2000 + auto-setup complet

**Documentatie** (2)
- `4e0d546` Ghid utilizare + fix-uri UX: countdown, setup o singura data, totul in engleza
- `878066f` Docs: START RAPID + FLOW ZILNIC la inceputul documentatiei

---

## 2026-09-20

**Altele** (7)
- `bb8ab8b` Revert "Revert: agent-original.py (desktop) NU se modifica la task-uri Android"
- `a1c424c` Revert: agent-original.py (desktop) NU se modifica la task-uri Android
- `43cfd26` Security: scos key.txt din git + ignora cheile API
- `f2e3643` /run: output streaming in timp real (linie cu linie) + salvare automata pentru output lung.
- `676adcf` Biblioteci de aur (Nivel 1) + fix stdlib pe Android.
- `1a1df3b` Interzis tabelele pe telefon: prompt dur + conversie automata la afisare.
- `8fb5493` Trunchiere: TOOLMAX 1800->6000 + tool nou 'read' (paginare) + mesaj cu comanda de continuare.

**Sistem de memorie / /learn** (12)
- `7ca6290` Android+desktop: auto-learning doar pe ULTIMUL task (nu toata sesiunea)
- `98fab63` Fix memorie: limita 300 -> 500 + taiere la granita de propozitie
- `3673838` Documentatie: rezultatul testului complet curat (WhatsApp task, memorie zero)
- `3ee49ca` agent: pastreaza doar agent-original.py, cu auto-learn complet portat
- `8bb3b6e` ask(): timeout configurabil (90s real, nu 600) + 3 incercari cu backoff; auto-learn: timeout scurt (45s) ca sa NU blocheze agentul. Dovedit: raspuns i
- `7e95035` Documentatie: actualizata complet (etape 15-20, primitive, biblioteci, /run, auto-learn, limitari, lectii).
- `7f223eb` Portat sistemul auto-learn imbunatatit in scriptul Linux (agent.py de pe desktop).
- `fed5b19` memory: lectie noua (git diff gol pe repo cu doar staged -> foloseste git diff --cached)
- `dd96362` Auto-learn: extractie multipla + filtru de VALOARE (balans calitate/cantitate).
- `88b4e51` Verificat auto-learn pe al doilea task complex (media/biometrie).
- `73d40ca` Auto-learn: FIX major - modelul nu vedea taskul + limite de lungime inconsistente.
- `29da30f` Auto-learn: filtrat strict pe Android + ENFORCE (nu doar warning).

**Tool-uri agent (python/bash/read/multi/bg/...)** (1)
- `d72468b` Android: read compact + find (ecranul devine lizibil, ~10x mai putin zgomot)

**UI / terminal** (3)
- `bea4937` Android: task-uri headless cu ecranul stins/blocat + wake UI la nevoie
- `5808e69` UI/fix: agentul raspunde in limba operatorului (nu fortat romana). caseta de scris nu mai taie ultima linie, pozitionata langa tastatura.
- `e1fc266` Documentate primitivele in ghidul agentului (proxy + referinte obiecte + await).

**Android: acces, permisiuni, servicii** (5)
- `eda3bff` Android: AccessibilityService - vedere + control asupra altor aplicatii (fara root)
- `cd5ba80` Android: foreground service - agentul ruleaza in background cand app e minimizata
- `7576834` Android: fix senzori - registerListener fara Handler nu livra niciodata date
- `435ec2c` SUBCLASARE la runtime prin DexMaker: op=subclass (primitiva 4).
- `0ba6b81` Primitive generale de acces (proxy interfețe + referințe obiecte + evenimente async).

**Home / workspace / fisiere** (2)
- `c9c2f46` Comanda /run <script.py> [args]: ruleaza orice script Python din workspace, direct din chat.
- `1656c5b` Curatenie: scos folderul temp/ din git (log-uri de test) + adaugat in .gitignore.

**Toolchain / compilare nativa** (1)
- `cfd721f` Prompt: agentul stie ce biblioteci are (requests/bs4/dateutil/yaml/toml/packaging/...) si ca NU poate instala altele (no pip, numpy/pandas nu exista).

**Documentatie** (1)
- `4bdcefb` Ghid actualizat cu op=subclass (DexMaker) + testat pe device.

---

## 2026-09-19

**Sistem de memorie / /learn** (5)
- `7f69beb` Documentatie completa de dezvoltare (md) + actualizare memorie.
- `634aed4` STRUCTURA NOUA: HOME=/sdcard/Download/Agent (memory.md+context.json), WORKSPACE=/sdcard/Download/Agent/workspace (tot ce genereaza agentul). AGENT_HOM
- `c70e245` WORKSPACE VIZIBIL: folderul de lucru al agentului mutat in /sdcard/agent/ (accesibil din file manager, fara adb). AGENT_WORK setat din Kotlin; WORK/ME
- `88123bd` FIX memorie: scos lectiile de dezvoltator din memoria telefonului + pastrare la update
- `0fc0ac5` memory: actualizare (memoria operatorului)

**UI / terminal** (23)
- `284a6f7` Iconita aplicatiei: prompt de terminal (sageata albastra '>' + linie alba '_') pe fundal inchis rotunjit. Generata din SVG (rsvg-convert) in toate den
- `65342d5` Comanda /where: arata unde traieste totul (home, workspace, memory, context, logs, archive) + nr fisiere. Daca ruleaza din sandbox (storage extern nes
- `73fc57e` FIX: recuperat MainActivity.kt (se golise prin open(w).write(open.read())) + banner aliniat la STANGA
- `6d2cdfb` UI: banner centrat corect pe orice ecran - Kotlin masoara latimea reala (Paint) si o trimite la Python prin AGENT_COLS; _ctr foloseste CS(). assets v2
- `97e161d` UI: cuvantul "AGENT" colorat ROSU (RED 38;5;203) in loc de mov
- `cbc85df` UI: cuvantul "AGENT" colorat mov (MOV 38;5;139), sageata ">" ramane C
- `408cbf3` UI: linie goala intre "AGENT >" si textul generat
- `068d5e5` UI: mesajul nu mai apare de 2 ori (scos ecoul din sendLine) + tradus 'write failed'
- `6fd1f93` UI: mesajul pe linia promptului + toata aplicatia in engleza
- `828cb63` UI: footer de task simplificat - mai putine linii la final
- `916a364` UI: ENTER de pe tastatura virtuala (Gboard) trimite taskul
- `ab3900b` UI: ENTER de pe tastatura trimite taskul (Shift/Alt+Enter = linie noua)
- `2768e41` UI: butoanele din randul de input facute compacte (minWidth implicit anulat)
- `9976720` UI: STOP functional (camp pid) + auto-scroll revine cand ajungi la fund
- `9718d9d` UI: auto-scroll corect - flag followTail bazat pe directia userului
- `d039c77` UI: scroll sus REPARAT cu adevarat - cauza era scrollY care crestea sub deget
- `487f22f` UI: auto-scroll revine cand derulezi jos la capat + ramane sus cand urci
- `d104055` UI: consumator de scroll robust + buton STOP generare
- `32fb494` UI: scroll sus rezista 20s+ in timpul generarii (fix definitiv)
- `940f79d` UI: fix REAL scroll sus - nu mai sare jos in timpul generarii
- `15a240a` UI: scroll-ul sus in timpul generarii rămâne pe loc (nu mai sare jos)
- `fafd069` feat(android): battery full - stoarce TOATE datele accesibile unui app normal
- `0c2cfc0` fix(android): bridge mai robust - portul nu se mai pierde/uitа

**Home / workspace / fisiere** (1)
- `589c398` FIX vizibilitate folder in file manager: My Files/MTP nu indexeaza un folder nou fara niciun fisier media, deci scriem .agent_folder.png (PNG 1x1) la 

**Tool-uri agent (python/bash/read/multi/bg/...)** (2)
- `e111917` UI banner start: doar '⚡ AGENT DeepSeek' centrat cu rosu + 'Type /help for all commands'. Scos tools/cwd/lista lunga de comenzi.
- `fca3ae7` feat(android): 11 tool-uri native noi + comportament exhaustiv

**Android: acces, permisiuni, servicii** (4)
- `6e3e289` FIX major permisiuni: ACCESS_BACKGROUND_LOCATION bloca TOATE dialogurile
- `8cce855` FIX permisiuni: manifest-ul extins nu ajungea in APK + flux dialog corect
- `35e1a28` feat(android): ACCES COMPLET - toate permisiunile + toate serviciile de sistem
- `0f94fb2` fix(android): toti obiectii reflection primesc id + actiuni native senzori/locatie

**Altele** (3)
- `159fcc1` memory: lecție nouă (PEP 668 / externally-managed-environment -> folosește venv sau pipx)
- `029c4c1` fix(android): agentul nu mai moare dupa primul task (linia goala omora bucla)
- `c6f75c8` Initial commit: Android AI agent app (net.sys32.agent)

---
