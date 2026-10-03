# Agent Android (net.sys32.agent)

## ⚡ START RAPID — CITESTE ASTA PRIMUL

**Daca esti un agent proaspat resetat (memorie goala) si citesti asta, iata esenta:**

### Starea repo-ului (3 oct 2026, `.assets_v252`) — ARHITECTURA "ZERO TERMUX"

> **Nota (3 oct 2026):** valorile de mai jos sunt RE-MASURATE pe clona curenta,
> nu preluate din documentatie veche. Daca modifici o cifra aici, masoar-o intai
> (`wc -c`, `ls`, `grep -n assets_v`), pentru ca tabelul acesta a fost deja o data
> in urma cu codul (spunea v197 / 187 915 B cand realul era v252 / 233 337 B).

| Ce | Valoare reala |
|----|---------------|
| Marker assets activ | **`.assets_v252`** (in `MainActivity.kt`, singura sursa de adevar) |
| APK debug | **~282 MB** (toolchain nativ COMPLET + binare executabile) |
| `agent.py` (assets) | **233 337 B** (3549 linii) |
| `toolchain.py` (assets) | **153 965 B** |
| Module Kotlin | **15** |
| Assets Python | agent.py + toolchain.py + adb_client.py + adb_setup.py + android_bridge.py + `Lib/` + `libdynload/arm64/` + 2 ZIP-uri (pysitepkg, stdlib_extra) |
| Toolchain nativ | `assets/toolchain/` (~343 MB) + binare `lib*_exec.so` in `jniLibs/` — **NU sunt in git** (vezi `.gitignore`), se regenereaza |
| Device | RZGL102X5AT (Samsung SM-A366B, Android 16) |
| Istoric complet | **[`CHANGELOG.md`](CHANGELOG.md)** |
| Plan spre autonomie completa | **[`PLAN_AUTONOMIE.md`](PLAN_AUTONOMIE.md)** (faze 0-6, reguli de verificare, capcane, jurnal) |

#### ★ CE S-A SCHIMBAT ESENTIAL (28 sept 2026)

**Termux ELIMINAT COMPLET** (`tpm.py` sters, 0 referinte in cod) **+ compilatoare noi:**

| Componenta | Unde | Rol |
|---|---|---|
| `libflang_exec.so` | `jniLibs/` | **FLANG 21.1.8** — compilator Fortran (137 MB, de la 0) |
| `libninja_exec.so` | `jniLibs/` | ninja 1.12.1 (build-uri meson: numpy, scipy) |
| `libc++_shared.so` | `jniLibs/` | C++ runtime REAL (module C++ fara rpath) |
| `libopenblas.a/.so` | `deps/lib` | **OpenBLAS 0.3.29** (ARMv8, SIMD NEON) — 10-50x fata de netlib |
| `libFortranRuntime.a` | `sysroot/usr/lib/.../35` | runtime Fortran (64 fisiere C++, de la 0) |
| `libc++abi.a` | `sysroot/usr/lib/.../35` | 528 KB — linkare statica C++ completa |
| `libjpeg.a/.so` | `deps/lib` | libjpeg-turbo cu **8/12/16-bit** (Pillow >= 10) |
| `libcxx_include.zip` | `assets/toolchain/` | libc++ COMPLET (2125 headere; AAPT2 pierde folderele `_`) |

**Verificat pe instalare CURATA (dezinstalare + reinstalare APK):**
```
check(): ar_test/cxx_test/libcxx_full/ninja/openblas/flang = toate TRUE
C -> RC 0 | C++ -> RC 0 | Fortran -> binar produs (1.5 MB)
```
**Protectie site-packages:** un update de APK nu mai pierde numpy/scipy/lxml/PIL
(depozit `files/site_packages_keep` care supravietuieste reinstalarii).

#### ★ CE S-A SCHIMBAT ESENTIAL (26 sept 2026)

**Arhitectura „zero Termux": APK-ul vina cu toolchain de compilare COMPLET.**

| Componenta | Unde | Rol |
|---|---|---|
| `libclang_exec.so` | `jniLibs/arm64-v8a/` | clang 21.1.8 (compilat de la 0, ARM64) |
| `liblld_exec.so` | `jniLibs/` | linker lld 21.1.8 |
| `libpkgconf_exec.so` | `jniLibs/` | pkg-config 2.3.0 (compilat de la 0) |
| `libllvm*_exec.so` | `jniLibs/` | ar, ranlib, strip, nm |
| `assets/toolchain/` | assets | sysroot + headers + libxml2/libxslt + pyinc |

**Agentul compileaza NATIV pe telefon, fara PC, fara Termux, fara bootstrap:**
```python
toolchain(action="pip_install", package="lxml")   # ✅ TESTAT: exit 0, 88s
```
Rezultat: wheel `lxml-6.1.3-cp314-cp314-android_24_arm64_v8a.whl`, XPath functional.

#### 🔴 CAPCANE CRITICE (SELinux / Android 16)

1. **`untrusted_app` NU poate executa din `filesDir`** (SELinux). Singurul loc
   executabil = **`nativeLibraryDir`** (`/data/app/.../lib/arm64`). De aceea
   clang/lld/pkg-config sunt ambalate ca `lib*_exec.so` in `jniLibs`.
2. **`lld` decide modul din `argv[0]`**: cu basename `liblld_exec.so` zice
   *"lld is a generic driver"*. Fix: symlink `ld.lld` + `--ld-path`.
3. **AAPT2 elimina folderele care incep cu `_`** (`pip/_internal`,
   `compression/_common`). Fix: livrate ca ZIP-uri (`pysitepkg.zip`,
   `stdlib_extra.zip`) in PYTHONPATH.
4. **`TMPDIR` trebuie sa EXISTE**: Python scrie acolo `ca-bundle.pem` (CA store
   pentru HTTPS). Fara el: `CERTIFICATE_VERIFY_FAILED` -> API-ul nu raspunde.
5. **`-m pip` ignora PYTHONPATH** cand PYTHONHOME e setat. Fix: `sys.path` injectat
   prin `-c`.
6. **FLANG NU compileaza Fortran "din prima"**: driver-ul cade pe `"gcc" -x f95-cpp-input`
   (*"gcc frontend command failed"*). Fix: wrapper in 2 pasi — `-fc1 -triple` pentru `.o`,
   apoi link cu clang + runtime-ul Fortran. Atentie: `-fc1` **ignora `-o`** (exit 0, 0 bytes)
   si vrea sursa RELATIVA din cwd-ul ei.
7. **Symlink-urile catre `nativeLibraryDir` MOR la fiecare reinstalare** (hash nou in
   `/data/app`). Fix: `_ensure_launchers()` detecteaza tinta moarta si regenereaza;
   `_native_dir()` deduce libDir-ul din `sys.executable` daca `TC_NATIVE` lipseste.
8. **Toate `.pc`-urile trebuie sa aiba prefixul DEVICE-ului**, nu al laptopului
   (`/home/gab/...` in `.pc` = link esuat pe telefon).
9. **★ NICIODATA stub-uri de LINK in `LD_LIBRARY_PATH`** (28 sept): directorul
   `toolchain/sysroot/usr/lib/aarch64-linux-android/<api>` contine `libc.so`/`libm.so`/
   `libdl.so` STUB (fara cod). Daca e primul in `LD_LIBRARY_PATH`, **orice PROCES COPIL**
   porneste cu libc stub -> SIGSEGV in constructorii `libpython3.14.so`. Procesul agentului
   NU avea nicio problema (bionic citeste `LD_LIBRARY_PATH` la INIT, nu la `dlopen`), deci simptomul
   e inselator: `pip install` murea cu `exit code: -11` la "Preparing metadata". Fix:
   `toolchain._rt_ld_path()` / `agent._clean_ld()` (filtreaza orice cale cu `sysroot`).

#### Procedura de pornire (dupa restart telefon)

```bash
# 1. adb TCP (o data per restart):
/home/gab/android/platform-tools/adb tcpip 5555
/home/gab/android/platform-tools/adb forward tcp:5555 tcp:5555

# 2. build + install:
cd /home/gab/Desktop/android_agent/workspace/app && ./build_app.sh

# 3. cheia DeepSeek (nu e in git):
adb shell run-as net.sys32.agent sh -c 'mkdir -p /data/data/net.sys32.agent/files/python; echo -n "sk-..." > /data/data/net.sys32.agent/files/python/key.txt'
```

### Ce esti
Esti un **agent autonom Android** (`net.sys32.agent`) care ruleaza PE telefon
(Samsung SM-A366B, Android 16), compilat de la zero cu:
- **Python 3.14.7** compilat pentru ARM64 (in APK, ca `libpyexec.so`)
- **Kotlin** pentru UI + bridge + accessibility
- **DeepSeek API** pentru creier

### Ce poti face (11 tool-uri)

> Ultima revizuire a tabelului: 25 sept 2026, commit `d8cc3c1`. Tool-urile de mai jos sunt
> EXACT cele definite in `agent.py` (verificate in sursa, nu presupuse).

| Tool | Ce face | Uid |
|------|---------|-----|
| `android` | bridge Kotlin: senzori, camera, reflection SDK, sub-toolui `ui` | 10362 (app) |
| `ui` | VEDE + CONTROLEAZA alte app-uri (read/find/click/settext/tap) | 10362 |
| **`adbsh`** | **SUPER-PUTERI: shell ca uid=2000 (pm grant, dumpsys, settings, input, screencap)** | **2000 (shell!)** |
| `python` | stdlib + pachete pure-Python | 10362 |
| `bash` | shell in sandbox-ul app | 10362 |
| `smart` | auto-router python/bash | 10362 |
| `read` | **citire cu BUGET GARANTAT** (path/offset/limit/budget/grep) — nu se taie niciodata | 10362 |
| **`multi`** | **BATCH: 2-6 operatiuni independente intr-UN apel** (economie ~60-97% tokeni) | 10362 |
| `look` | analiza imagini (vision) | — |
| `bg` | **gestionar de procese in fundal** (start/status/log/kill/list/clean) — OBLIGATORIU pentru orice comanda >30s | 10362 |
| `toolchain` | compilare **C/C++/Fortran** nativa pe telefon (clang-21, lld, ninja, flang) | 10362 |

### REGULA DE AUR PENTRU ALEGEREA TOOL-URILOR
1. **Ecran** (citire/tap/text) → `android ui` (nativ, instant, 0 auth)
2. **Senzori/camera/baterie** → `android` (nativ, instant)
3. **Reflection SDK** → `android eval`
4. **Fisiere/imagini** → `python`, `bash`, `read`, `look`
5. **Super-puteri** (uid=2000) → `adbsh` **DOAR** cand app-ul NU poate:
   permisiuni (`pm grant`), `settings put`, `dumpsys`, `input` fara accessibility,
   `run-as` alte app-uri, `screencap`, `logcat`

> **NU folosi `adbsh` pentru ce face `android`/`python`** — e 10x mai lent si poate rate-limita.
6. **Mai multe verificari independente** → `multi` **O SINGURA DATA** (fiecare
   cerere retrimite TOT contextul: 2-6 ops intr-un apel = economie ~60-97% tokeni)
7. **★ SCRAPING / WEB (pagini, RSS, articole, tabele, linkuri)** → `python/scraper.py`
   (**DEFAULT**, NU requests+regex scris de mana). Vezi sectiunea "SCRAPING WEB" mai jos.


### Unde sunt fisierele (pe device)
```
/data/data/net.sys32.agent/files/
  python/          agent.py, adb_client.py, adb_setup.py, android_bridge.py, Lib/, libdynload/
  adbkey           cheia RSA privata (auto-generata)
  adbkey.pub       cheia publica (format ADB)
  tls.crt/key      certificat X.509
  libs/            libcrypto, libssl, pairing_auth, pairing_connection (din /apex)
  home/, pyhome/   HOME + PYTHONHOME
  libdir.txt       calea catre libpyexec.so (SE SCHIMBA la reinstalare!)
  bridge.port      portul bridge-ului Kotlin
/sdcard/Download/Agent/            (PARTIAL - doar ce trebuie vizibil/durabil)
  adbkey, adbkey.pub   ★ CHEIA PERSISTENTA (supravietuieste reinstalarilor)
  workspace/       fisierele de lucru (vizibil in file manager)
                   + .agent_folder.png (marker MediaScanner)
                   + logs/  archive/  __pycache__/
  .old_sdcard_home/    reziduu istoric (vechiul HOME mutat in stocarea privata)
```

⚠️ **ATENTIE (schimbat 24 sept): `context.json` si `memory.md` NU mai sunt pe /sdcard.**
Traiesc in **stocarea privata**: `/data/data/net.sys32.agent/files/`
(motiv: elimina zgomotul MediaProvider/FUSE; vezi Etapa 32). `AGENT_HOME` se
IGNORa acum pentru HOME (ramane doar pentru compat) — il folosim doar ca sa
localizam `workspace/` de pe sdcard.

### ★ SCRAPING WEB — `scraper.py` (DEFAULT pentru orice acces web)

**Regula:** pentru ORICE operatiune web (pagini, articole, RSS, tabele, linkuri, meta)
foloseste `files/python/scraper.py`. NU scrie requests+regex de mana, NU folosi
`curl | grep` pentru HTML (se sparge la HTML real) si NU parsa HTML cu regex.

**Locatia pe device:** `files/python/scraper.py`
**Sursa in repo:** `workspace/tools/scraper.py` (+ copie in `assets/python/scraper.py`)

#### Comenzi

| Comanda | Ce face |
|---------|---------|
| `head <url>` | status + content-type + lungime (HEAD, fara sa descarce corpul) |
| `meta <url>` | toate meta-urile (og:, twitter:, description, title) |
| `article <url>` | **extragere automata de articol** (trafilatura: text + metadate, fara nav/ads/footer) |
| `xpath <url> <expr>` | XPath direct pe lxml (**cel mai rapid si puternic**) |
| `css <url> <sel> [attr]` | selectori CSS (prin parsel) |
| `rss <url> [limit]` | feed RSS/Atom -> titlu/link/data/summary |
| `links <url> [pattern]` | toate linkurile (absolutizate, opțional filtrate cu regex) |
| `table <url> [idx]` | extrage tabelul N ca lista de randuri |

#### Utilizare

```bash
# ca script (CLI)
python3.14 files/python/scraper.py article https://www.bbc.com/news
python3.14 files/python/scraper.py xpath https://site.com "//h2//text()"
python3.14 files/python/scraper.py rss https://feeds.bbci.co.uk/news/rss.xml 5
python3.14 files/python/scraper.py table https://en.wikipedia.org/wiki/... 0
```
```python
# ca modul
import sys; sys.path.insert(0, "/data/data/net.sys32.agent/files/python")
import scraper
scraper.article(url)          # -> {text, meta, chars}
scraper.xpath(url, "//h2//text()")
scraper.css(url, "h2::text")
scraper.rss(url, limit=10)
scraper.table(url, idx=0)
scraper.links(url, pattern="news")
scraper.meta(url); scraper.head(url)
```

#### Stack (CAND E INSTALAT pe device)

| Pachet | Versiune | Rol |
|--------|----------|-----|
| `lxml` | 6.1.3 (C, compilat pe device) | XPath + parsare rapida |
| `parsel` | 1.12.1 | selectori CSS peste lxml |
| `trafilatura` | 2.3.0 | extragere articol + metadate |
| `feedparser` | 6.0.14 | RSS/Atom |
| `justext` | 3.0.2 | boilerplate removal |
| `requests` | (inclus) | HTTP (Session cu keep-alive + UA mobil) |
| + deps | cssselect, w3lib, courlan, htmldate, dateparser, babel, lxml_html_clean, pytz | |

**Wheelhouse local:** `files/wheels/` (13 wheel-uri) — include
`lxml-6.1.3-cp314-cp314-android_24_arm64_v8a.whl` (**compilat pe device**, ~3 MB).
La o reinstalare nu se recompileaza:
`python -m pip install --find-links files/wheels --no-index lxml trafilatura parsel feedparser justext`

#### Doua capcane REALE (reparate/constatate pe device, 3 oct 2026)

1. **`pip install <pachet>` fara `--no-build-isolation` EȘUA** cu
   ``BackendUnavailable: Cannot import 'setuptools.build_meta'`` (setuptools sta in
   `pysitepkg.zip`, iar subprocesul de build izolat nu pune zip-ul pe `sys.path`).
   Fix: **intotdeauna `--no-build-isolation`** cand instalezi pachete noi (sau foloseste
   `toolchain action=pip_install`, care merge pe calea standard).
2. **AAPT2 elimina folderele care incep cu `_`**, deci in `site-packages` lipseau
   19 fisiere din `pathspec/_backends`, `scikit_build_core/_compat`, `scikit_build_core/_vendor`,
   `setuptools_scm/_integration` — ceea ce rupea build-ul lxml
   (``ModuleNotFoundError: No module named 'scikit_build_core._compat'``).
   Fix: extras folderele `_*` din `pysitepkg.zip` in site-packages (bypass pe capcana AAPT2).
3. **`json.dumps` cadea la `article`** in trafilatura 2.x: `extract_metadata().as_dict()`
   intoarce la cheile `body`/`commentsbody` elemente lxml (`_Element`), nu string
   (``TypeError: Object of type _Element is not JSON serializable``).
   Fix aplicat in `scraper.py`: functia `_clean_meta()` care scoate/converteste
   valorile ne-serializabile + `default=str` la afisare.

#### ★ MOTOR JAVASCRIPT (jsengine.py) - site-uri cu JS

Site-urile moderne (React/Vue/Next.js) pun datele in JavaScript, nu in DOM.
`scraper.py` singur NU le vede. Solutia: **QuickJS compilat nativ pe device**.

**Instalat:** `quickjs 1.19.4` (wheel `android_24_arm64_v8a`, 449 KB) - ES2020 complet:
async/await, Promise, optional chaining (`?.`), nullish (`??`), Map/Set, classes, BigInt.
Alternativa mini-racer (V8) e IMPOSIBILA pe device: cere `just build-dll` cu V8 din sursa.

**Functii noi in scraper.py (leaga scraper + jsengine automat):**

| Functie | Ce face |
|---------|---------|
| `sniff(html)` | clasifica pagina: `static` / `hybrid` / `spa` + listeaza pattern-urile de date |
| `extract_js_data(html)` | scoate blocul JSON din `<script>` (7 patterns cunoscute) |
| `js_query(url, expr)` | extrage datele JS si le interogheaza cu JavaScript (variabila `DATE`) |
| `deep(url, keys)` | cauta recursiv chei (`title`/`headline`/`name`) in structura imbricata |
| **`supreme(url)`** | **★ ALEGE AUTOMAT metoda optima si o executa** |

**Pattern-uri de date recunoscute:** `__NEXT_DATA__`, `__NUXT__`, `__INITIAL_STATE__`,
`__DATA__`, `__PRELOADED_STATE__`, `__APOLLO_STATE__`, `ld+json`.

**CLI:**
```bash
python3.14 files/python/scraper.py sniff <url>          # ce fel de pagina e
python3.14 files/python/scraper.py jsquery <url> 'Object.keys(DATE)'
python3.14 files/python/scraper.py deep <url> title,headline
python3.14 files/python/scraper.py supreme <url>        # ★ face tot, alege singur
```

**Lantul suprem (dovada pe device, BBC News 379 KB):**
```
scraper.fetch()           195 ms   ia HTML-ul
scraper.extract_js_data()   6 ms   scoate 93 KB de JSON din <script>
jsengine (QuickJS)         20 ms   interogheaza recursiv structura
                        --------
TOTAL                     221 ms   123 titluri extrase (vs 253 chars cu article() singur)
```

**Decizia automata a lui `supreme()`:**
- `kind=static` -> `scraper.article()` (HTML normal, <1s)
- `kind=hybrid` -> scraper (reteaua) + jsengine (datele JS) - **cel mai eficient**
- `kind=spa` -> `jsfetch.fetch()` (Chrome, randare completa, 12-23s)

#### Verificat pe device (3 oct 2026, toate rc=0)

```
head   https://example.com                      -> status 200, text/html
meta   https://example.com                      -> title "Example Domain"
article https://www.bbc.com/news                -> metadate + text articol
xpath  https://www.bbc.com/news "//h2//text()"  -> titluri reale de stiri
css    https://www.bbc.com/news "h2"            -> titluri reale de stiri
links  https://www.bbc.com/news                 -> 40 linkuri (absolutizate)
rss    https://feeds.bbci.co.uk/news/rss.xml 3  -> feed "BBC News", 25 intrari
table  https://en.wikipedia.org/wiki/List_of_... -> tabel cu ~200 randuri
```

> ⚠️ Atentie la XPath: `//h1/text()` da gol daca textul e in elemente copil
> (ex. `<h1><span>Text</span></h1>`) — foloseste `//h1//text()` (dublu slash) ca sa
> prinzi tot subtree-ul. Nu e bug, e XPath standard.

---

### Cum pornesti Python-ul manual (pe device, prin adb)
```bash
LIBDIR=$(dumpsys package net.sys32.agent | grep codePath | sed 's/.*codePath=//')/lib/arm64
run-as net.sys32.agent sh -c "cd /data/data/net.sys32.agent/files/python && \
  HOME=/data/data/net.sys32.agent/files/home \
  PYTHONHOME=/data/data/net.sys32.agent/files/pyhome \
  LD_LIBRARY_PATH=/data/data/net.sys32.agent/files/libs:$LIBDIR \
  $LIBDIR/libpyexec.so SCRIPT.py"
```

### Ce NU se poate (limite reale Android — NU incerca degeaba)
1. **`adb tcpip 5555`** — app-ul NU poate rula asta (necesita sistem/root).
   Se face O DATA de pe laptop dupa restart telefon.
2. **Pairing WIRELESS (SPAKE2+TLS)** — NU functioneaza din app:
   Python `ssl` nu expune `export_keying_material` → mismatch de chei SPAKE2.
   → wireless ADB real merge DOAR cu client extern (PC).
3. **Citirea `/data/misc/adb/`** — permission denied (doar root).

### Starea actuala (functionala)
- ✅ `adbsh` → uid=2000 (cheia auto-generata + persistenta in /sdcard)
- ✅ Auto-setup la prima pornire (cheie + cert + libs)
- ✅ Alegere inteligenta a tool-urilor (testat live)
- ✅ Auto-detectie port ADB (5555, 55555 sau orice port setat)
- ✅ Setup o singura data (`.setup_done`; lansarile ulterioare = pornire directa)

### AUTONOMIE: CE E IN APK vs. CE E MANUAL

**IN APK (auto, dupa instalare):**
- Python 3.14 ARM64 + libpyexec + stdlib + libdynload
- agent.py, adb_client.py, adb_setup.py, android_bridge.py
- 15 module Kotlin: MainActivity, AndroidBridge, Reflection, Primitives, Components, Ansi,
  AgentService, AgentAccessibilityService, AgentNotificationListener, AgentIme,
  AgentVpn, AgentDeviceAdmin, ScreenCaptureService, CameraActivity, BootReceiver
- memory.md (default), key.txt (API)
- LA PRIMA PORNIRE se AUTO-GENEREAZA: cheia RSA, certificatul X.509,
  libs-urile crypto/ssl (copiate din /apex)

**MANUAL (nu se poate automatiza — limitari Android):**
| Ce | De ce | Cum | Cand |
|----|-------|-----|------|
| `adb tcpip <port>` | Android interzice app-ului sa deschida portul adbd TCP | de pe calculator: `adb tcpip 5555` | dupa fiecare RESTART telefon |
| "Allow USB debugging" | dialog de sistem Android | pe telefon, o data | la prima conectare / cheie noua |
| Accessibility ON | Android cere activare explicita din Settings | Settings > Accessibility > Agent | dupa fiecare reinstalare APK |

**FARA calculator:** agentul merge cu `android`, `ui`, `python`, `bash`,
`smart`, `read`, `look` (senzori, camera, GPS, ecran, fisiere, HTTP).

**CU calculator** (+ 30s o data): se deblocheaza `adbsh` (uid=2000):
`pm grant`, `settings put`, `dumpsys`, `logcat`, `input`, `screencap`,
`run-as`, `getprop/setprop` — puteri de dezvoltator, fara root.

---

oid (net.sys32.agent)

---



---

### FLOW ZILNIC DE OPERARE (cand telefonul a fost repornit)

    ┌─────────────────────────────────────────────────────────┐
    │ 1. VERIFICA daca adbsh merge                            │
    │    adbsh(cmd="id -u")  → trebuie "2000"                 │
    ├─────────────────────────────────────────────────────────┤
    │ 2. DACA NU merge (timeout/dialog "Allow"):              │
    │    a) pe laptop (USB): adb tcpip 5555                   │
    │    b) pe telefon: apasa "Allow" in dialog (o data)      │
    │    c) reincearca adbsh(cmd="id -u")                     │
    ├─────────────────────────────────────────────────────────┤
    │ 3. DACA merge → continua taskul normal                  │
    │    foloseste tool-urile dupa REGULA DE AUR             │
    └─────────────────────────────────────────────────────────┘

**NU e nevoie de altceva.** Cheia e persistenta, libs se copiaza singure.

---

## 🛠 OPERATIUNI (BUILD · INSTALL · DEBUG · VERIFICARE)

> **Sectiunea asta e PROCEDURA OPERATIONALA.** Daca esti un agent proaspat resetat
> si trebuie sa construiesti, instalezi sau sa debughezi aplicatia, citeste DOAR
> partea asta si urmeaz-o pas cu pas. Restul documentului explica DE CE.

---

### OP.1 — MEDIUL DE BUILD (pe laptop)

| Componenta | Valoare | Nota |
|------------|---------|------|
| JDK | `/usr/lib/jvm/java-21-openjdk-amd64` | **JDK 21** — Debian trixie NU are openjdk-17; Gradle 8.11.1 + AGP merg cu 21 |
| Android SDK | `/home/gab/android` | `ANDROID_HOME` = `ANDROID_SDK_ROOT` |
| build-tools | `34.0.0`, `35.0.0`, `35.0.1`, `36.0.0` | se foloseste automat de AGP |
| Gradle | wrapper **8.11.1** | cache in `~/.gradle/wrapper/dists/gradle-8.11.1-bin` |
| adb | `/home/gab/android/platform-tools/adb` | **NU e in PATH!** foloseste calea absoluta |
| NDK / cmake / emulator | in `/home/gab/android/` | doar pentru build nativ, nu pentru APK |
| Device | `RZGL102X5AT` (Samsung SM-A366B, Android 16) | `adb devices -l` |

**De ce conteaza:** `env.sh` din vechea structura **a fost sters** (commit `f72a5eb`).
Toate variabilele sunt setate acum de `build_app.sh`. Daca rulezi `gradlew` manual,
exporta-le tu:

```bash
export JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64
export ANDROID_HOME=/home/gab/android
export ANDROID_SDK_ROOT=/home/gab/android
export PATH=$JAVA_HOME/bin:$ANDROID_HOME/platform-tools:$PATH
```

**Verificare mediu (5 secunde):**
```bash
java -version                                  # -> openjdk 21.0.12.1
cd /home/gab/Desktop/android_agent/workspace/app/net.sys32.agent && ./gradlew --version
/home/gab/android/platform-tools/adb devices -l
```

---

### OP.2 — BUILD APK

#### Calea normala (build + install + start) — 99% din cazuri

```bash
cd /home/gab/Desktop/android_agent/workspace/app
./build_app.sh
```

Ce face scriptul (citit, verificat):
```bash
export JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64
export ANDROID_HOME=/home/gab/android
export ANDROID_SDK_ROOT=/home/gab/android
export PATH=$JAVA_HOME/bin:$ANDROID_HOME/platform-tools:$PATH
cd "$(dirname "$0")/net.sys32.agent"
./gradlew assembleDebug                        # BUILD
adb install -r app/build/outputs/apk/debug/app-debug.apk   # INSTALL
adb shell am start -n net.sys32.agent/.MainActivity        # START
```

#### Doar build (fara install)

```bash
cd /home/gab/Desktop/android_agent/workspace/app/net.sys32.agent
./gradlew assembleDebug                 # APK: app/build/outputs/apk/debug/app-debug.apk
./gradlew --offline assembleDebug       # fara retea (deps in cache) — ~14s incremental
./gradlew clean assembleDebug           # rebuild de la ZERO (lent: 59M assets + 24M libs)
./gradlew assembleRelease               # release (isMinifyEnabled=false, nesemnat)
```

| Comanda | Timp tipic | Cand |
|---------|-----------|------|
| `assembleDebug --offline` (nimic schimbat) | ~14 s | verifici ca mediul e OK |
| `assembleDebug` dupa 1 fisier `.py`/`.kt` | ~20-40 s | iteratie normala |
| `clean assembleDebug` | minute | schimbari de config/deps |

**Configurare relevanta** (`app/build.gradle.kts`): `compileSdk 36`, `minSdk 26`,
`abiFilters arm64-v8a + x86_64`, `packaging.jniLibs.useLegacyPackaging = true`
(★ obligatoriu: altfel `.so`-urile nu se pot executa pe API 29+).
`gradle.properties`: `-Xmx3072m`, `parallel`, `caching`, `android.useAndroidX`.

**Verificare APK inainte de install** (comenzi TESTATE, cu rezultatul real de pe acest proiect):
```bash
APK=app/build/outputs/apk/debug/app-debug.apk
ls -lh $APK            # -> 273M  app-debug.apk (toolchain complet inclus)
/home/gab/android/build-tools/35.0.1/aapt2 dump badging $APK 2>&1 | head -4
#   -> package: name='net.sys32.agent' versionCode='1' versionName='1.0'
#      platformBuildVersionName='16' platformBuildVersionCode='36' compileSdkVersion='36'
#      minSdkVersion:'26' / targetSdkVersion:'36'
#      uses-permission: name='android.permission.INTERNET' ...
unzip -l $APK | grep -c 'assets/python/'              # -> ~940 fisiere Python ambalate
unzip -l $APK | grep 'assets/python/agent.py'         # -> 181740  assets/python/agent.py
unzip -l $APK | grep 'lib/arm64-v8a/'
#   -> 4537664  lib/arm64-v8a/libcrypto_python.so
#        4400  lib/arm64-v8a/libpyexec.so          (mic = interpreterul)
#     5828792  lib/arm64-v8a/libpython3.14.so
#        4048  lib/arm64-v8a/libpython3.so
#      886800  lib/arm64-v8a/libsqlite3_python.so
#      956256  lib/arm64-v8a/libssl_python.so
/home/gab/android/build-tools/35.0.1/dexdump -f $APK >/dev/null 2>&1 && echo dex-ok   # -> dex-ok
```
> ⚠️ `aapt2` scrie `version` pe **stderr** (pe stdout da gol) — nu te speria de output gol acolo.
> ⚠️ AAPT2 **IGNORA** directoarele din assets care incep cu `_` → de asta
> `_path.py` / `_streams.py` sunt livrate ca FISIERE, nu ca foldere. Daca un import
> da `ModuleNotFoundError` pentru un subpachet cu `_`, asta e cauza.

---

### OP.3 — INSTALL + CELE 3 CAPCANE OBLIGATORII

```bash
ADB=/home/gab/android/platform-tools/adb
$ADB install -r app/build/outputs/apk/debug/app-debug.apk    # "Success"
$ADB shell am start -n net.sys32.agent/.MainActivity
```

**Verificare ca s-a instalat CHIAR versiunea noua:**
```bash
$ADB shell dumpsys package net.sys32.agent | grep -E 'lastUpdateTime|codePath|versionName'
stat -c '%y' app/build/outputs/apk/debug/app-debug.apk        # compara mtime APK cu lastUpdateTime
$ADB shell pm list packages | grep sys32                       # package present?
```
> ⚠️ Daca procesul VECHI inca ruleaza, ecranul poate arata codul vechi desi
> `lastUpdateTime` e nou → `am force-stop` + `am start`, sau `uninstall` + `install`.

#### ★ CAPCANA 1 — `.assets_vNN` (cea mai frecventa)

`MainActivity.kt` in `extractAssets()`:
```kotlin
val stamp = File(filesDir, ".assets_v252")   // valoarea CURENTA (verific-o cu grep, nu o presupune)
if (stamp.exists() && dest.exists()) return   // ← iese IMEDIAT daca markerul exista
```
Deci: **modificarile din `assets/` NU ajung pe device** daca nu incrementezi markerul.

**Procedura:**
```bash
# 1. gaseste markerul curent
grep -n 'assets_v' app/src/main/java/net/sys32/agent/MainActivity.kt
#    -> 693:  val stamp = File(filesDir, ".assets_v252")

# 2. incrementeaza-l (v252 -> v253)
sed -i 's/\.assets_v252/.assets_v253/' app/src/main/java/net/sys32/agent/MainActivity.kt

# 3. rebuild + install, apoi verifica PE DEVICE
$ADB shell run-as net.sys32.agent ls -la /data/data/net.sys32.agent/files/ | grep assets_v
#    -> .assets_v253  (trebuie sa fie NOU)
```

Ce face re-extragerea (util cand ceva „nu se actualizeaza"):
- salveaza `python/memory.md`, sterge `python/` si `pyhome/`, copiaza assets, **pune memoria la loc**
- sterge `pyhome/` intentionat → stdlib-ul (`Lib/`) si `site-packages/` se actualizeaza la fiecare extract

#### ★ CAPCANA 2 — `adb install -r` DEZACTIVEAZA accessibility

```bash
$ADB shell settings put secure enabled_accessibility_services net.sys32.agent/net.sys32.agent.AgentAccessibilityService
$ADB shell settings put secure accessibility_enabled 1
# verificare:
$ADB shell dumpsys accessibility | grep -A3 net.sys32.agent   # serviciul e enabled=true?
# sau din chat:  android(tool="ui", action="status")  -> {"ok":true,"enabled":true}
```
> ⚠️ Si `am force-stop` reseteaza `accessibility_enabled` la 0 → re-ruleaza cele 2 comenzi.

#### ★ CAPCANA 3 — `libdir` se schimba la fiecare reinstalare

Calea contine hash-ul instalarii: `/data/app/~~<hash>==/net.sys32.agent-<hash>==/lib/arm64`.
La fiecare install hash-ul e **altul** → `libdir.txt` de pe device devine invalid.

```bash
$ADB shell dumpsys package net.sys32.agent | grep codePath
#    -> codePath=/data/app/~~ABC==/net.sys32.agent-DEF==     (append /lib/arm64)
```

---

### OP.4 — DEBUG (7 niveluri, de la cel mai des la cel mai rar)

#### D1. LOGCAT — prima oprire mereu

```bash
ADB=/home/gab/android/platform-tools/adb
$ADB logcat -c                                                # curata INAINTE de repro
$ADB logcat --pid=$($ADB shell pidof -s net.sys32.agent)       # live, doar app-ul
$ADB logcat -d -t 300 | grep -iE 'net.sys32|AndroidRuntime'    # ultimele 300 linii
$ADB logcat -s AndroidRuntime:E                                # doar crash-uri Java/Kotlin
$ADB logcat -d | grep -iE 'DEBUG|tombstone|SIGSEGV' | tail -40 # crash NATIV (libpyexec.so)
```

> **Lectie din proiect:** *„Masoara, nu presupune. Logcat a rezolvat ce 3 incercari
> oarbe n-au reusit."* (sect. 12, lectia 1)

#### D2. TERMINALUL APP-ULUI = stdout-ul Python

Nu exista TTY de sistem. `MainActivity` citeste stdout-ul `libpyexec.so` linie cu
linie si il deseneaza in TextView. Deci **orice `print()` din `agent.py` apare pe ecran**.

Citire headless:
```bash
$ADB exec-out screencap -p > /home/gab/Desktop/android_agent/temp/shot.png   # apoi tool `look`
ls -l /home/gab/Desktop/android_agent/temp/shot.png     # ★ verifica >100KB, altfel frame gol/stale
```
Alternativa mai buna (fara OCR): scrie in `/sdcard/Download/Agent/` si citeste fisierul.
```bash
$ADB shell cat /sdcard/Download/Agent/context.json | head -c 2000
```

`uiautomator dump` pe ecranul agentului da **un singur nod multi-linie** cu `&#10;`:
```bash
$ADB shell uiautomator dump /data/local/tmp/x.xml    # ★ scrie explicit calea!
$ADB shell cat /data/local/tmp/x.xml                 # altfel citesti window_dump.xml gresit
# entitatile &#10; trebuie inlocuite cu \n
```

#### D3. PROCESUL PYTHON TRAIESTE?

```bash
$ADB shell ps -A | grep -E 'sys32|libpyexec'
$ADB shell dumpsys window | grep mCurrentFocus       # ce e in FATA (app? dialog? Settings?)
$ADB shell dumpsys power | grep -E 'mWakefulness=|net.sys32'   # Doze?
$ADB shell dumpsys deviceidle whitelist | grep sys32           # exclus de Doze?
```
> ⚠️ `ps -A | grep python3.14` **NU e fiabil** pe acest device (build-urile compilate
> nu apar cu numele asteptat) → nu-l folosi ca dovada de liveness. Foloseste screenshot-ul.

#### D4. FISIERE APP-PRIVATE (fara root, prin `run-as`)

```bash
$ADB shell run-as net.sys32.agent ls -la /data/data/net.sys32.agent/files/
$ADB shell run-as net.sys32.agent ls -la /data/data/net.sys32.agent/files/python/
$ADB exec-out run-as net.sys32.agent cat /data/data/net.sys32.agent/files/python/agent.py > /tmp/agent_on_device.py
cat /data/data/net.sys32.agent/files/python/key.txt     # NU trebuie sa apara in git!
```
> ⚠️ `exec-out run-as cat` poate da **0 bytes** pe Samsung (desi fisierul exista) →
> incearca alternativ `shell run-as ... head -50` sau `sed -n`.
> ⚠️ `run-as <pkg> cat` **pierde ultimul newline** → compara cu `md5sum` pe device, nu cu `cat`.

#### D5. STARE PERSISTENTA (memoria + contextul)

```bash
$ADB shell cat /sdcard/Download/Agent/context.json     # istoricul conversatiei
$ADB shell cat /sdcard/Download/Agent/memory.md        # lectiile invatate
```
> ⚠️ `context.json` **nu e mereu JSON valid** (poate avea „Extra data" dupa array) →
> parseaza cu `json.JSONDecoder().raw_decode(raw)` care intoarce `(obj, idx)`.

#### D6. INSPECTIA APK-ULUI

```bash
APK=/home/gab/Desktop/android_agent/workspace/app/net.sys32.agent/app/build/outputs/apk/debug/app-debug.apk
/home/gab/android/build-tools/35.0.1/aapt2 dump badging $APK 2>&1 | head -20   # ★ 2>&1: scrie pe stderr!
unzip -l $APK | grep 'assets/python/' | wc -l        # ~940 fisiere Python (masurat)
unzip -l $APK | grep 'assets/python/agent.py'        # 181740 bytes (masurat)
unzip -l $APK | grep 'lib/arm64-v8a/'                # 16 .so-uri (libpyexec 4400, libpython3.14 5828792, libflang 137M)
# ★ verificare COMPLETA a componentelor de compilare (28 sept):
unzip -l $APK | grep -E 'lib(clang|lld|pkgconf|ninja|flang)_.*exec|libc\+\+_shared'  # 6 binare + C++ runtime
unzip -l $APK | grep -E 'deps/lib/(libopenblas|libjpeg|libxml2|liblapack)'              # deps C precompilate
unzip -l $APK | grep -E 'libc\+\+abi\.a|libFortranRuntime\.a|libcxx_include\.zip'    # C++ complet + Fortran + headere
/home/gab/android/build-tools/35.0.1/dexdump -f $APK >/dev/null 2>&1 && echo dex-ok
```

#### D7. DEBUGGER KOTLIN (JDWP) — rar

```bash
./gradlew installDebug
$ADB shell am set-debug-app -w net.sys32.agent                  # asteapta debugger
$ADB forward tcp:8700 jdwp:$($ADB shell pidof net.sys32.agent)
# attach din IDE la localhost:8700
$ADB shell am clear-debug-app
```

---

### OP.5 — TABEL DIAGNOSTIC (simptom → comanda exacta)

| Simptom | Cauza probabila | Comanda / Fix |
|---------|-----------------|---------------|
| Modificarea din `assets/` „nu se vede" | marker `.assets_vNN` nebumpat | `grep -n assets_v MainActivity.kt` → `sed -i` bump → rebuild |
| Cifre/meniu vechi pe ecran dupa install | proces vechi inca ruleaza | `am force-stop net.sys32.agent` apoi `am start -n .../.MainActivity` |
| `INSTALL_FAILED_UPDATE_INCOMPATIBLE` | semnatura/versiune diferita | `$ADB uninstall net.sys32.agent` + install curat |
| `INSTALL_FAILED_NO_MATCHING_ABIS` | ABI lipsa | `unzip -l $APK \| grep lib/` (trebuie arm64-v8a) |
| `pm install` da Binder stacktrace, fara „Success" | APK nu a fost push-uit | `adb push` intai in `/data/local/tmp/`, apoi `pm install -r` de acolo |
| `libpyexec.so: No such file` | `libdir.txt` vechi (hash schimbat) | `dumpsys package ... \| grep codePath` → append `/lib/arm64` |
| `cannot locate symbol ...` | `LD_LIBRARY_PATH` gresit | pune `files/libs` **PRIMUL** in `LD_LIBRARY_PATH` |
| `ModuleNotFoundError` pe subpachet `_xxx` | AAPT2 ignora foldere cu `_` | livreaza ca `.py` simplu, nu ca director |
| Accessibility se dezactiveaza singur | `install -r` sau `force-stop` | cele 2 `settings put secure ...` |
| `ui` da `accessibility:false` | serviciul nu e activat | `dumpsys accessibility \| grep -A3 net.sys32` |
| `adbsh` timeout | adbd nu asculta pe port | `adb tcpip 5555` (o data, de pe laptop) |
| Dialog „Allow USB debugging" reapare | cheie noua / adbd resetat | apasa Allow (o data) |
| `adbsh` timed out dupa multe apeluri | rate-limit adbd | asteapta 10s / reporneste wireless debugging |
| Python nu porneste, `Fatal error: Failed to import encodings` | `PYTHONHOME` gresit | trebuie `files/pyhome`, NU `files/python` |
| Build esueaza cu `JAVA_HOME is not set` | shell nou fara export | exporta cele 4 variabile din OP.1 |
| `gradlew` da eroare de retea | deps nu-s in cache | `--offline` sau reconectare |
| Crash instant la pornire | `.so` lipsa/corupt | `unzip -l $APK \| grep lib/arm64-v8a/` |
| Agentul „uita" contextul | `context.json` invalid/corupt | `exec-out cat` + verificare `raw_decode` |
| Apel API `HTTPError` (tool_calls orfane) | mesaj `assistant` cu tool_calls nedublat de `tool` | vezi Etapa 36: repara perechile in `context.json` |

---

### OP.6 — BUILD PYTHON PENTRU ANDROID (o singura data / rar)

> ⚠️ **ATENTIE: sursele NU sunt pe disc acum.** Directorul
> `workspace/build/Python-3.14.7/` este in `.gitignore` (linia 2: `workspace/build/`)
> si **a fost sters de pe laptop** — `workspace/` contine doar `app/` si
> `android_bridge.py`. Rezultatul compilarii E in schimb in repo, in
> `app/src/main/jniLibs/` + `assets/python/Lib/`.
> Daca trebuie sa recompilezi CPython pentru Android, re-descarca sursele (vezi mai jos).

CPython 3.14 are **suport Android oficial** (`Android/android.py`) — NU trebuie
cross-toolchain manual; scriptul oficial face tot.

```bash
# 1. re-descarca sursele (odata, ~25 MB)
mkdir -p /home/gab/Desktop/android_agent/workspace/build && cd /home/gab/Desktop/android_agent/workspace/build
curl -LO https://www.python.org/ftp/python/3.14.7/Python-3.14.7.tgz
tar xf Python-3.14.7.tgz
cd Python-3.14.7

# 2. dependinte de HOST (o singura data; Debian trixie)
sudo apt-get install -y build-essential pkg-config autoconf libssl-dev zlib1g-dev \
     libffi-dev libsqlite3-dev libreadline-dev libbz2-dev liblzma-dev libgdbm-dev libncurses-dev

# 3. build
sudo apt-get install -y build-essential pkg-config autoconf libssl-dev zlib1g-dev \
     libffi-dev libsqlite3-dev libreadline-dev libbz2-dev liblzma-dev libgdbm-dev libncurses-dev
./android.py build aarch64-linux-android     # pentru TELEFON
./android.py build x86_64-linux-android      # pentru EMULATOR
```

Rezultat in `cross-build/<abi>-linux-android/prefix/`:
- `lib/python3.14/` → devine `assets/python/Lib/`
- `lib-dynload/*.so` → devine `assets/python/libdynload/<abi>/`
- `libpython3.14.so` → `jniLibs/<abi>/libpython3.14.so` (5.8 MB)
- `libpyexec.so` (4 KB, interpreterul executabil) → `jniLibs/<abi>/`
- modulele C: `_ssl`, `_hashlib`, `_sqlite3`, `zlib`, `_bz2`, `_lzma`, `_zstd`, `_ctypes`
  → devin `libssl_python.so`, `libcrypto_python.so`, `libsqlite3_python.so`
  ✔ absolut necesar: Android linker-ul rezolva `.so` dupa **soname** din caile de sistem
  → prefixarea cu `_python` evita conflictul cu vechile libs de sistem

**Lipsesc intentionat:** `_tkinter`, `readline`, `_curses`, `_gdbm`, `_uuid`.
**Verificare:** `$ADB shell run-as net.sys32.agent ... libpyexec.so -c "import ssl, sqlite3, zlib; print('ok')"`

---

### OP.7 — CHECKLIST PRE-COMMIT (ruleaza inainte sa zici „gata")

- [ ] `cd workspace/app && ./build_app.sh` → BUILD SUCCESSFUL + `Success`
- [ ] daca am atins `assets/` → `.assets_vNN` incrementat (acum **`.assets_v252`**; se citeste cu `grep -n 'assets_v' app/src/main/java/net/sys32/agent/MainActivity.kt`) **si** verificat pe device
- [ ] accessibility reactivat **si** confirmat (`ui status` → `enabled:true`)
- [ ] `$ADB devices -l` arata device-ul
- [ ] `$ADB shell dumpsys package net.sys32.agent | grep lastUpdateTime` = timpul de acum
- [ ] am citit logcat-ul dupa pornire (fara excepții)
- [ ] `grep -rn 'key.txt\|AIza\|sk-' --include='*.py' --include='*.kt' .` → **nicio cheie** in repo
- [ ] `git status --short` → doar fisierele intentionate
- [ ] `py_compile` pe fisierele Python modificate (`python3 -m py_compile agent.py`)
- [ ] `toolchain action=status` → toate verificarile TRUE (ar_test, cxx_test, libcxx_full,
      ninja, openblas, flang) — **dupa instalare curata**, nu doar dupa update
- [ ] **`CHANGELOG.md` actualizat** daca sesiunea a produs commituri noi (vezi mai jos)

#### Regenerarea `CHANGELOG.md`

`CHANGELOG.md` se genereaza din istoricul git. Rularea de mai jos rescrie
documentul cu TOATE commiturile, grupate pe zile si pe categorii (UI, ADB,
memorie, toolchain, acces Android etc.):

```bash
cd /home/gab/Desktop/android_agent
git log --format='%h|%ad|%an|%s' --date=short > temp/all_commits.txt
# apoi ruleaza generatorul (categorizare pe cuvinte cheie) si scrie CHANGELOG.md
```

> **Regula:** dupa fiecare sesiune de dezvoltare care produce commituri noi, regenereaza
> `CHANGELOG.md` si comite-l in ACELASI push. Asa istoricul rămâne sincron cu codul.

---

### REZOLVAREA PROBLEMELOR FRECVENTE

| Simptom | Cauza | Fix |
|---------|-------|-----|
| `adbsh` timeout | adbd nu asculta pe 5555 | `adb tcpip 5555` (laptop) |
| Dialog "Allow USB debugging" reapare | cheia noua / adbd resetat | apasa Allow (o data) |
| `libpyexec.so: No such file` | libdir.txt vechi | re-citeste cu `dumpsys package ... codePath` |
| `cannot locate symbol...` (libs) | LD_LIBRARY_PATH gresit | pune `files/libs` PRIMUL in LD_LIBRARY_PATH |
| `adbsh error: timed out` dupa multe apeluri | adbd rate-limit | asteapta 10s, sau repornire wireless |
| Libs lipsa dupa update APK | assets re-extrase | app le copiaza automat la pornire (adb_setup.py) |
| `code=127` / `library libX.so not found` | RUNPATH Termux hardcodat | `toolchain.py` face patch automat (patchelf) |
| `ninja: subcommand failed` | ninja Termux e rupt | se inlocuieste automat cu samu |
| `rm: inaccessible or not found` | PATH minimal la meson/ninja | wrapper-ele pun /system/bin in PATH |
| `undefined symbol ctanl/ccoshl` | clang target android24 ascunde C99 | `--target=aarch64-linux-android<API>` |
| `cannot locate symbol _ZTVNSt6__ndk1...` | lipseste libc++ la runtime | `LD_PRELOAD=libc++_shared.so` |
| `undefined symbol` la linkare cu -lm | nu exista libm.so in Termux | `-L/apex/com.android.runtime/lib64/bionic` |
| nume trunchiate in lib-dynload | tar GNU LongName (`typeflag=L`) ignorat | `_untar()` cu suport L/K/PAX (automat) |
| `Compiler cython cannot compile programs` | **toate** `.pc` au prefix Termux | `_fix_sysconfig` le rescrie (automat) |
| `cannot locate symbol _ZTVNSt6__ndk1...` | lipseste `NEEDED libc++_shared` | `_fix_libcxx_needed` + `-lc++_shared` (automat) |
| 63 scripturi "No such file or directory" | shebang Termux mort | `_fix_wrappers_shebang` (automat) |
| `python3`/`pip3` negasite | Termux nu face symlink | `_fix_symlinks` (automat) |
| RUNPATH reapare dupa reinstalare pachet | agentul reinstaleaza .deb-uri | ruleaza `_patch_runpath` din nou (bootstrap) |

### CUM REBUILDUIESTI APLICATIA (daca modifici cod)
```bash
cd /home/gab/Desktop/android_agent/workspace/app
./build_app.sh          # build + install + start (face tot)
```
**ATENTIE:**
- dupa FIECARE modificare de assets → INCREMENTEAZA `.assets_vNN` in MainActivity.kt
- `adb install -r` DEZACTIVEAZA accessibility → reactiveaza:
  ```bash
  adb shell settings put secure enabled_accessibility_services net.sys32.agent/net.sys32.agent.AgentAccessibilityService
  adb shell settings put secure accessibility_enabled 1
  ```
- libdir.txt se schimba la fiecare reinstalare → reciteste-l

### UNDE E CODUL SURSA (pe laptop, pentru dezvoltare)
```
/home/gab/Desktop/android_agent/
  agent-original-android.py                      agentul ANDROID ORIGINAL (referinta, neatins)
  agent-original-linux.py                        agentul LINUX ORIGINAL (referinta, neatins)
  agent-android-v2.py                            agentul ANDROID OPTIMIZAT (v2) - ACESTA e default-ul
  agent-linux-v2.py                              agentul LINUX OPTIMIZAT (v2)
  Documentatie_Agent_Android.md                  ACEST document
  memory.md                                      memoria agentului desktop
  workspace/app/net.sys32.agent/
    app/src/main/assets/python/agent.py          = continutul lui agent-android-v2.py (DEFAULT la clone/build)
    app/src/main/assets/python/adb_client.py     client ADB (super-puteri)
    app/src/main/assets/python/adb_setup.py      auto-setup
    app/src/main/assets/python/android_bridge.py bridge Python-side
    app/src/main/java/net/sys32/agent/*.kt       Kotlin (MainActivity, Bridge, Accessibility, Reflection)
  (workspace/build/Python-3.14.7/                sursele Python - STERSE, in .gitignore; vezi OP.6)
```

> **Schema de nume:** `agent-<platform>-<varianta>.py` unde platforma = `android` | `linux`,
> iar varianta = `original` (neatins) | `v2` (optimizat pentru context de 1M tokeni).
>
> ⚠️ **ATENTIE (corectat 3 oct 2026): `assets/python/agent.py` NU mai este copia lui
> `agent-android-v2.py`.** Fisierele `agent-*-*.py` din radacina sunt INGHETATE la
> 25 sept 2026 (ultimul commit `c71edc1`) si au ramas documentatie de referinta.
> Codul VIU este `assets/python/agent.py` (3 oct, v252): 233 337 B / 3549 linii,
> fata de 180 558 B / 2696 linii in `agent-android-v2.py` — nu sunt identice
> (`md5`: assets `455cdb63...`, v2 rădăcină `8639f8b4...`), iar niciunul nu e
> substring al celuilalt.
>
> `agent.py` este numele fix pe care il cauta codul Kotlin (`ProcessBuilder(py, "agent.py")`),
> deci versiunea care ruleaza pe device este EXCLUSIV cea din assets. Daca vrei sa
> reeditezi agentul, editeaza `assets/python/agent.py` direct — **nu** copia
> `agent-android-v2.py` peste el (ai pierde 853 linii de dezvoltare ulterioara).

---

ent Android (net.sys32.agent)

---

## Documentatie completa de dezvoltare

**Versiune:** 1.0
**Platforma:** Android 8+ (minSdk 26), target API 36 (Android 16)
**Autor:** dezvoltare asistata (sesiuni multiple)
**Ultima actualizare:** septembrie 2026

---

## CUPRINS

> **OPERATIUNI (build/install/debug/verificare): vezi sectiunea „🛠 OPERATIUNI"
> chiar inainte de „REZOLVAREA PROBLEMELOR FRECVENTE" — OP.1 pina la OP.7.**

1. Prezentare generala
2. Arhitectura
3. Componentele aplicatiei (3.1-3.6 + cele 15 module Kotlin si 9 fisiere Python)
4. Cum functioneaza Python pe Android
5. Pasii dezvoltarii de la 0 (etape 1-38, ordonate cronologic)
6. Probleme intalnite si solutii
7. Structura de fisiere a aplicatiei
8. Structura pe dispozitiv (in rulare)
9. Comenzi disponibile
10. Tool-uri si accesul la sistem
11. Limitari cunoscute
12. Lecții invatate
13. Starea finala si pasii urmatori

> Vezi si **[`CHANGELOG.md`](CHANGELOG.md)** — istoricul commiturilor (actualizat periodic).

---

## 1. PREZENTARE GENERALA

Applicatia **net.sys32.agent** este un agent autonom care ruleaza pe Android.
Vorbeste cu modelul DeepSeek, ia decizii, executa unelte si interactioneaza
cu intregul sistem Android. Interfata este un terminal cu culori ANSI.

Scop: acces cat mai complet la hardware si sistem, intr-un sandbox de aplicatie
normala (fara root), cu memorie persistenta si invatare din experienta.

---

## 2. ARHITECTURA

Trei componente care comunica intre ele:

    [ UI Kotlin ]  --deseneaza terminalul pe ecran
          |
          |  (stdout/stdin prin pipe-uri)
          v
    [ Agent Python ]  --creierul: DeepSeek API, tool-use, memorie
          |
          |  (socket TCP 127.0.0.1:port, o linie JSON/cerere)
          v
    [ Bridge Kotlin ]  --reflection pe Android SDK, acces hardware

Componenta 1 si 3 ruleaza in ACELASI proces Android (aplicatia).
Componenta 2 ruleaza ca PROCES SEPARAT (libpyexec.so agent.py).

---

## 3. COMPONENTELE APLICATIEI

### 3.1 UI (MainActivity.kt)
- TextView monospace cu scroll, culori ANSI (Ansi.kt converteste SGR)
- Paleta One Dark pe fundal #0D1117
- Font DejaVuSansMono livrat in assets (glyph-uri box-drawing continue)
- Input cu EditText: Enter de pe tastatura trimite taskul (TextWatcher,
  fiindca Gboard introduce caracterul \n in text, nu KEYCODE_ENTER)
- Butoane: trimitere (sageata), STOP (patrat rosu, linga trimitere), jos
- Auto-scroll inteligent: ramine sus cind citesti, urmareste cind esti jos
- Buton STOP trimite SIGINT procesului Python (PID luat prin reflexie din
  cimpul "pid", nu metoda - aceasta nu exista pe Android)

### 3.2 Bridge (AndroidBridge.kt)
- Server TCP pe 127.0.0.1, port aleator (ServerSocket(0, 8, 127.0.0.1))
- Portul scris in files/bridge.port si files/home/bridge.port
- Protocol: o linie JSON per cerere, o linie JSON per raspuns
- Shortcut-uri native: sensors, camera, location, battery, clipboard, notify,
  vibrate, tts, volume, wifi, device, apps, intent, settings
- Actiuni native suplimentare: system, storage, processes, network, display,
  audio, telephony, nfc, usb, appinfo

### 3.3 Reflection (Reflection.kt)
- Operatii: call, new, get, set, info, services, objs, free
- Target-uri: svc:NUME, class:FQCN, obj:ID, ctx, app, str:, int:
- Registry de obiecte cu id-uri (o0, o1, ...)
- Map de 298 servicii de sistem (cu fallback inteligent de nume)

### 3.4 Agent (agent.py)
- Bucla principala: citeste task, cheama DeepSeek, executa tool-uri
- Memorie pe termen lung (memory.md) + auto-learn
- Context persistent (context.json) cu compactare automata
- Comenzi slash (a se vedea sectiunea 9)

---

### 3.5 AgentService (foreground service)
Tine procesul Python viu in BACKGROUND, ca agentul sa poata lucra si cind aplicatia
e minimizata (ex. cind umbla prin alte aplicatii).
- notificare persistenta (canal "agent_bg", id 4711) -> procesul nu mai e candidat la kill
- PARTIAL_WAKE_LOCK -> CPU-ul nu adoarme in timpul unui task lung
- START_STICKY + onTaskRemoved -> serviciul revine daca sistemul il omoara (sau la swipe din recents)
- onDestroy-ul MainActivity NU mai omoara Python/bridge-ul cit timp serviciul ruleaza
- manifest: foregroundServiceType="specialUse", stopWithTask="false"
- merge si cu ECRANUL STINS/BLOCAT: task-urile HEADLESS (bridge, senzori, fisiere, retea)
  functioneaza 100% chiar in Doze, atita vreme cit aplicatia e in whitelist-ul de baterie
- pentru task-uri care ating UI-ul altor aplicatii (specific Android), agentul poate
  chema `ui wake` (wake lock ACQUIRE_CAUSES_WAKEUP + setShowWhenLocked/setTurnScreenOn pe
  activity): ecranul se aprinde si activitatea se arata peste lock screen
- `ui sleep` elibereaza wake lock-ul de ecran (procesul rămine viu, headless)
- `ui service` returneaza starea: foreground / accessibility / ignore_battery_opt

### 3.6 AgentAccessibilityService (vedere + control UI)
Da agentului VEDERE si CONTROL asupra oricarei alte aplicatii, FARA root.
Android interzice injectarea de input aplicatiilor normale (INJECT_EVENTS e o
permisiune de SEMNATURA - doar system apps o pot avea). AccessibilityService e
calea oficiala si singura viabila pentru un app normal.
Capabilitati expuse prin bridge (tool `ui`):
- read       - citeste arborele UI al oricarei aplicatii. COMPACT (default): lista text
               lizibila, ~10x mai mica decit JSON-ul brut. Format: [n] Cls id=x "text" @[x,y] <flags>
               (E=editabil C=clickabil K=checkable S=scrollabil). params: max, depth, textonly
- find       - CAUTA un nod dupa text/id FARA sa citeasca tot ecranul; intoarce potrivirile
               cu center=[x,y] gata de click. E calea eficienta cind cauti contact/buton/cimp
- settext    - scrie text (ACTION_SET_TEXT) in cimpul cautat / focalizat / primul editabil
- click      - apasa un nod (dupa text/id) sau un punct (x,y)
- tap/swipe  - gesturi reale prin dispatchGesture
- scroll     - scroll pe nod sau swipe pe ecran
- back/home/recents/notifications/quicksettings/screenshot/lockscreen - performGlobalAction
- openapp    - deschide orice aplicatie dupa pachet
- windows    - listeaza ferestrele vizibile

Config: res/xml/accessibility_service_config.xml (canRetrieveWindowContent=true,
canPerformGestures=true, flagReportViewIds, flagRetrieveInteractiveWindows).
Serviciul se activeaza de UTILIZATOR din Settings > Accessibility (vezi sec. 9).
### 3.7 Servicii privilegiate (FIX 1-8 ACCES MAXIM, commit `c47e3b4`)
Module Kotlin adaugate pentru acces extins fara root. Fiecare expune actiuni in
bridge, apelabile ca sub-tool-uri: `android(tool="notif", action="list")` etc.

| Modul | Ce face | Actiune bridge |
|-------|---------|----------------|
| `AgentNotificationListener.kt` | citeste notificarile altor app-uri | `notif` |
| `AgentIme.kt` | citeste text din campuri de input | `ime` |
| `AgentVpn.kt` | VpnService (interceptare trafic) | `vpn` |
| `ScreenCaptureService.kt` | MediaProjection FGS (captura ecran) | `capture` |
| `AgentDeviceAdmin.kt` | DeviceAdmin (dpm) | `guard` |
| `BootReceiver.kt` + GuardService | anti-kill + repornire la boot | - |
| `CameraActivity.kt` | captura foto/video | `camera` |
| `AgentAccessibilityService.kt` | vedere + control UI (vezi 3.6) | `ui` |

**Capcane reale (documentate in memory.md):**
- `takeScreenshot()` a11y NU merge in `/data/local/tmp` (EACCES) -> scrie in filesDir
- rate-limit: ~1 captura/secunda (limita Android, nu bug)
- MediaProjection (Android 14+) cere `registerCallback` INAINTE de `createVirtualDisplay`

### 3.8 Primitives.kt - primitive generale de reflection
Operatii de acces avansat expuse agentului (commit `c47e3b4`, etape 15):
- **proxy** de interfete (java.lang.reflect.Proxy) - implementeaza orice interfata la runtime
- **referinte la obiecte** (tin obiecte Java vii intre apeluri, cu id)
- **subclasare la runtime** prin DexMaker (`op=subclass`)
- **await/evenimente async** (asteapta emiteri de la obiecte Java)

### 3.9 AgentService.kt - foreground service
Agentul ruleaza si cind app-ul e minimizat. Notificare persistenta "AGENT ruleaza".
Wakelock cu timeout 30min + renew la inceputul fiecarui task (optimizare baterie,
commit `99f2335`). Watchdog propriu (verificare `pyProc`, nu `pgrep` - pe Android
un app NU poate lista procese ale altor uid-uri) cu cooldown 20s.

### 3.10 Componente UI (Components.kt, Ansi.kt)
- `Ansi.kt` - converteste secvente SGR in span-uri de culoare pentru TextView
- `Components.kt` - widget-uri reutilizabile
- Paleta One Dark, font DejaVuSansMono, `MAX_UI_CHARS=200000` (fix lag,
  commit `76fbbba`)

### 3.11 Fisierele Python din sandbox (`files/python/`)
`sandboxul` ruleaza 8 fisiere `.py` + `Lib/` (188 intrari) + `libdynload/`:

| Fisier | Rol |
|--------|-----|
| `agent.py` (183 434 B) | bucla principala, tool-uri, comenzi `/`, sistemul de memorie |
| `adb_client.py` | client ADB PYTHON-FIRST (drenare select-gated, 48 ms/comanda) |
| `adb_setup.py` | auto-setup: cheie RSA, certificat X.509, libs din /apex |
| `android_bridge.py` | clientul socket catre AndroidBridge.kt |
| `toolchain.py` (51 KB) | compilare C/C++/Fortran nativa pe telefon (clang, lld, ninja, flang) |
| ~~`tpm.py`~~ | **STERS** (28 sept) — Termux eliminat complet |
| `build.py` | helper de build |
| `setexec.py` | seteaza bitul de executie pe .so extrase |
| `_streams.py` | drenare neblocanta pentru subprocess (produs de AAPT2 care ignora `_`) |

## 4. CUM FUNCTIONEAZA PYTHON PE ANDROID

Aceasta este o parte importanta si usor de inteles gresit.

### 4.1 Android NU are bash si NU are "terminal"
- Shell-ul este **mksh** (MirBSD Korn Shell), la /system/bin/sh
- Utilitarele sunt **toybox** (~150 comenzi: ls, cat, grep, sed, find, tar)
- NU exista bash, grep -P, sau multe optiuni GNU
- NU exista un TTY/terminal de sistem pentru utilizator

### 4.2 Ce am facut de fapt
Am compilat **CPython 3.14.7 pentru Android** ca binar ELF nativ si l-am
rulat ca PROCES SEPARAT, NU "intr-un terminal Android".

- Python-ul este CPython 3.14.7 din sursa oficiala (are suport Android
  oficial in Android/android.py)
- Compilat pentru doua arhitecturi: arm64-v8a (telefon) si x86_64 (emulator)
- Rezultat: libpython3.14.so + libpyexec.so (interpreterul)

### 4.3 Cum porneste aplicatia Python-ul
NU face "sh -c python". Face direct:

    ProcessBuilder("/data/.../libpyexec.so", "agent.py")

Deci binarul este executat direct, fara shell intermediar. Pe API 29+
executabilele nu pot rula din filesDir, deci sint puse in nativeLibraryDir
ca libXXX.so.

### 4.4 Terminalul este construit de noi
Applicatia Kotlin citeste stdout-ul procesului Python linie cu linie, il
converteste cu Ansi.kt in text colorat (Spannable) si il deseneaza intr-un
TextView. NU folosim un terminal de sistem - nu exista unul.

### 4.5 Unde folosim totusi shell-ul
Tool-ul "bash" al agentului ruleaza de fapt "sh -c <comanda>" (mksh).
Merge pentru majoritatea comenzilor, dar fara specific bash.

    SHELL=[('sh','-c') if android else ('bash','-lc')]

### 4.6 De ce dumpsys este blocat
Tool-ul bash al agentului ruleaza sub UID-ul aplicatiei (sandbox SELinux),
nu sub "shell" (uid 2000). De aceea "dumpsys battery" returneaza
"Can't find service: battery". Accesul la sistem se face prin reflection
(svcs expuse public) si prin actiuni native Kotlin.

---

## 5. PASII DEZVOLTARII DE LA 0

### Etapa 1 - Mediul de dezvoltare
- Instalat JDK 21 (Debian trixie nu are openjdk-17)
- Instalat Android SDK in /home/gab/android: platform-tools, cmdline-tools,
  build-tools 35.0.1, Gradle 8.11.1
- Creat env.sh cu JAVA_HOME, ANDROID_HOME, ANDROID_SDK_ROOT, PATH

### Etapa 2 - Compilarea Python pentru Android
- Descoperit suportul Android oficial in CPython 3.14 (Android/android.py)
- Comanda: ./android.py build <target>
- Compilat pentru arm64-linux-android si x86_64-linux-android
- 114 module (36 built-in, 67 shared): _ssl, _hashlib, _sqlite3, zlib,
  _bz2, _lzma, _zstd, _ctypes incluse; lipsesc _tkinter, readline, _curses

### Etapa 3 - Proiectul Kotlin
- Structura Gradle: minSdk 26, targetSdk 36, namespace net.sys32.agent
- Python impachetat ca lib/libpython3.14.so + module in assets/python/libdynload/
- Extrase in files/ la prima rulare, cu sistem de stamp (.assets_vN)

### Etapa 4 - Interfata terminal
- TextView monospace + Ansi.kt (conversie SGR in Spannable)
- Paleta One Dark pe #0D1117
- Font DejaVuSansMono in assets
- Input, butoane, scroll cu auto-follow

### Etapa 5 - Podul Kotlin<->Python
- Server TCP pe 127.0.0.1, port aleator
- Protocol o linie JSON per cerere/raspuns
- Portul scris in doua fisiere (files/ si files/home/)

### Etapa 6 - Accesul la SDK prin reflection
- Reflection.kt: call, new, get, set, info, services, objs, free
- Registry de obiecte cu id-uri

### Etapa 7 - Agentul Python
- Bucla principala, DeepSeek API cu tool-use
- Memorie pe termen lung + auto-learn
- Context persistent cu compactare

### Etapa 8 - Deploy
- Emulator: android-36 google_apis x86_64, -gpu host cu offload NVIDIA
- Telefon real: Samsung SM-A366B prin USB

### Etapa 9 - Repararea accesului (faza majora)
- BUG reflection: flag "keep" implicit false -> obiectele nu primeau id ->
  fixat la true (fara asta, agentul "se invirtea" pierzind obiectele)
- Actiuni native noi: sensors stream, location fresh (fix GPS real),
  location current
- Stabilitate: agentul murea dupa primul task (linia goala oprea bucla) ->
  fixat (linia goala este ignorata, doar /exit si /quit opresc)
- Bridge: portul se pierdea la reconectare -> fixat (re-citire fisier)

### Etapa 10 - Acces complet la sistem
- Manifest: 34 -> 105 permisiuni
- Map servicii de sistem: 72 -> 298
- 11 tool-uri native noi: system, storage, processes, network, display,
  audio, telephony, nfc, usb, appinfo, sensors all
- battery full: toate datele bateriei accesibile unui app normal

### Etapa 11 - Bug-uri critice de permisiuni
- ACCESS_BACKGROUND_LOCATION in cererea principala -> TOATE dialogurile se
  inchideau instant (Android 11+ interzice combinarea) -> fixat: cerut separat
- Manifest cache-uit de Gradle -> APK avea doar 30 permisiuni din 105 ->
  rezolvat cu ./gradlew clean

### Etapa 12 - Rafinarea UI
- Scroll: ramine sus cind citesti in timpul generarii (diagnosticat cu logcat)
- Buton STOP functional (SIGINT, PID prin cimp)
- Enter de pe Gboard trimite taskul (TextWatcher pentru \n)
- Banner curat in engleza, AGENT rosu, mesaj pe linia "You >"
- Footer simplificat

### Etapa 13 - Workspace vizibil
- Mutat in /sdcard/Download/Agent/ (memorie + context)
- workspace/ (tot ce genereaza agentul)
- Comanda /where - arata unde e totul
- Marcaj media pentru indexare in My Files

### Etapa 14 - Identitate vizuala
- Iconita: prompt de terminal (sageata albastra + linie alba) pe fundal
  inchis, generata din SVG in toate densitatile

---

### Etapa 15 - Primitive generale de reflection (agent suprem)
Problema: reflection-ul pur nu putea implementa interfețe Java (ScanCallback, listeners),
nu putea pasa Context ca argument si nu putea astepta callbacks asincrone. Adaugat 4 primitive
generale in Reflection.kt + Primitives.kt:
- `op=proxy` - proxy de interfețe Java (java.lang.reflect.Proxy); fiecare apel devine un eveniment
- referințe de obiecte ca argumente: `["ref","ctx"]`, `["ref","obj:o5"]`, `["ref","svc:sensor"]`
- `op=await` / `op=events` / `op=sinks` - evenimente asincrone de la callback-uri
- `op=subclass` - SUBCLASARE LA RUNTIME prin DexMaker (genereaza o clasa reala care
  extinde orice clasa abstracta: ScanCallback, BroadcastReceiver etc.)
Rezultat: scanare BLE reala cu ScanCallback (11 dispozitive detectate), imposibil inainte.

### Etapa 16 - Biblioteci Python (Nivel 1)
Adaugate in assets/python/Lib/site-packages/ ~13 pachete PURE Python (fara cod nativ):
requests, urllib3, certifi, charset-normalizer, idna, beautifulsoup4, soupsieve,
python-dateutil, six, pyyaml, toml, packaging, typing-extensions (~3.1 MB).
Toate testate pe device (requests -> HTTP 200 real, bs4 -> parse HTML, yaml/toml -> round-trip).
NU exista pip la nivel de sistem, DAR agentul compileaza nativ cu `toolchain`
(pip_install) orice pachet cu cod C/C++/Fortran (lxml, numpy, Pillow, zstandard...).

### Etapa 17 - Bug-uri de ambalare stdlib pe Android
- AAPT2 IGNORA folderele care incep cu `_` in assets (fisierele .py merg, folderele NU).
  zipfile/_path/ nu ajungea in APK -> livrat ca zipfile/_path.py (fisier simplu, glob inline).
- six.py (fisier la radacina wheel-ului) era sarit de scriptul de copiere (copia doar foldere).
- pyhome nu se actualiza (stdlib copiat o singura data) -> se sterge la re-extragere.

### Etapa 18 - Sistem de memorie si auto-learn
- memory.md pe termen lung, incarcat o singura data la start (snapshot in system prompt)
- auto-learn: la finalul unui task (>=5 pasi SAU eroare) extrage lectii reutilizabile
- filtru de VALOARE (_lesson_value): scor 0-10; taie banalitatile si observatiile fara consecinta
- filtru de mediu: respinge lectiile de developer/desktop (nu-s despre acest telefon)
- extractie multipla: pana la N lectii valide per task (nu doar una)
- linter (mem_lint): valideaza formatul, duplicatul, lungimea

### Etapa 19 - UI: streaming, scroll, comenzi
- comanda /run <script.py> [args]: ruleaza orice script Python din workspace, direct din chat,
  cu output STREAMING in timp real (linie cu linie) + salvare automata la output lung
- scroll: derulezi sus -> ramai sus (nu te mai arunca jos la generare); revii jos -> auto-follow
- buton STOP (SIGINT) in randul de input, langa send
- Enter de pe tastatura virtuala (Gboard) trimite taskul (TextWatcher pe newline)
- caseta de scris: creste corect pe mai multe randuri, nu mai taie ultima linie
- banner curat, aliniat la stanga; cuvantul AGENT rosu
- agentul raspunde in LIMBA operatorului (nu fortat romana)
- INTERZIS tabele pe ecran mic: prompt dur + conversie automata tabel->lista la afisare

### Etapa 20 - Workspace vizibil si git
- workspace mutat in /sdcard/Download/Agent/ (memorie + context) si workspace/ (tot ce genereaza)
- comanda /where arata unde e totul
- iconita profesionala (prompt de terminal, SVG -> toate densitatile)
- repo git + push pe GitHub (SSH)

### Etapa 21 - Background: agentul lucreaza la minimizare (foreground service)
Problema: cind aplicatia era minimizata, Android suspenda/omoara procesul Python, deci
agentul nu mai putea continua un task (critic cind trebuie sa umble prin alte aplicatii).
Solutie: AgentService (foreground) + PARTIAL_WAKE_LOCK + START_STICKY + onTaskRemoved.
Verificat pe Samsung SM-A366B: proces viu >25s in background, bridge 16/16 tool-uri,
supravietuieste la am send-trim-memory RUNNING_CRITICAL, repornire curata dupa force-stop.

### Etapa 22 - Fix senzori (registerListener fara Handler)
Problema: TOTI senzorii returnau "no data from accelerometer" desi existau.
Cauza: registerListener era apelat din thread-ul de socket, care NU are Looper;
fara un Handler explicit, onSensorChanged nu se declanseaza NICIODATA.
Fix: sensorHandler = Handler(Looper.getMainLooper()) ca al 4-lea argument la toate
cele 3 apeluri (read/stream/collect). Verificat: 8/8 senzori live (light 287 lx,
proximity 5cm, gravity 9.80 m/s^2, accelerometru, magnetic, giroscop, pedometru).

### Etapa 23 - Tastare si control in ALTE aplicatii (AccessibilityService)
Problema: agentul nu putea tasta/apasa butoane in alte aplicatii. Reflection
injectInputEvent -> SecurityException INJECT_EVENTS (permisiune de semnatura).
Shell `input` din app (untrusted_app) -> "Failed transaction". Ambele imposibile fara root.
Solutie: AgentAccessibilityService (vedere + control UI, fara root).
Verificat end-to-end pe telefon: am deschis Settings, am apasat "Search settings",
am TASTAT "bluetooth" in cimpul de cautare si am citit rezultatele ("Results (27)").


### Etapa 24 - Ecran stins / telefon blocat: headless mereu, UI la nevoie
Problema: cu ecranul stins si telefonul blocat, agentul parea ca "se opreste".
Diagnostic (reprodus pe Samsung A36): procesul NU murea si wake lock-ul era activ;
ce nu raspundea era tunelul `adb forward` (suspendat de Doze) - o limitare adb, nu a app-ului.
Testat direct pe telefon (adb shell nc): bridge-ul raspundea perfect cu ecranul blocat.
Solutii implementate:
- PARTIAL_WAKE_LOCK (CPU treaz) - deja existent, confirmat activ in Doze
- `ui wake` / `ui sleep`: wake lock suplimentar ACQUIRE_CAUSES_WAKEUP + setShowWhenLocked(true)
  + setTurnScreenOn(true) + FLAG_KEEP_SCREEN_ON pe perioada unui task cu UI
- cerere automata REQUEST_IGNORE_BATTERY_OPTIMIZATIONS la prima pornire (fara ea Samsung
  suspenda agresiv procesul); se poate pune si manual: Settings > Battery > Unrestricted
- `ui service`: expune starea (foreground / accessibility / ignore_battery_opt)
Verificat: cu ecranul STINS si BLOCAT (mWakefulness=Dozing, AOD aprins):
  - 6/6 + 8/8 + 10/10 task-uri HEADLESS reusite (baterie/device/senzori)
  - task UI reusit: `ui wake` -> `ui openapp com.android.settings` -> `ui read` (20 noduri)
  - procesul rămas viu dupa toate (PID stabil)


### Etapa 25 - read compact + find (ecranul devine lizibil pentru model)
Problema (reprodusa cu un task real: "deschide WhatsApp, cauta 'gab', trimite 'salut'"):
`ui read` returna JSON brut cu TOATE metadatele pe fiecare nod
(`"enabled":true,"bounds":[0,0,1080,2340],"pkg":"com.whatsapp"` etc) -> ~120 caractere
de zgomot pentru 3 caractere de text util. Un ecran WhatsApp = 8500+ caractere, iar
raspunsul era TRUNCHIAT la 8000 -> informatia cautata ("Gab") ajungea la poz. 6375,
la un pas de taiere. Agentul primea zgomot, nu informatie, si a ajuns sa caute
contactul in agenda Android (3 contacte de serviciu) in loc de rezultatele search-ului.
Solutii:
- read COMPACT (default): arborele devine lista text `[n] Cls id=x "text" @[x,y] <flags>`.
  Rezultat masurat: 8581 -> 1949 caractere (~4.5x mai putin); "Gab" vizibil pe linia [8].
- find <text>: cauta direct un nod (text/id/descriere) si intoarce potrivirile cu
  center=[x,y] -> agentul nu mai citeste tot ecranul cind cauta ceva anume.
- trunchiere inteligenta in agent.py: ui read/find primesc 12000 chars (textul e dens),
  iar mesajul de taiere spune explicit sa foloseasca max/depth mici sau `ui find`.
Verificat end-to-end pe Samsung A36 (taskul care esuase inainte):
  WhatsApp -> find "Gab" (13 potriviri) -> tap pe contact -> camp message (id=entry)
  -> settext "salut" -> tap send -> mesaj TRIMIS (confirmat vizual: bubble verde la Gab)

TEST COMPLET CURAT (memoria + contextul STERSE, WhatsApp pe ecranul principal):
  Task: "deschide whatsapp, cauta userul gab si da i un mesaj de salut" - pornit de la zero.
  Fluxul agentului (37 mesaje, ~1 minut, 100% autonom):
    1. ui wake + apps.launch com.whatsapp
    2. ui read (textonly) -> 49 noduri, lista de chat-uri
    3. ui find "Gab"       -> gasit conversatia in lista (fara sa citeasca tot ecranul)
    4. ui tap pe contact
    5. ui find id=entry    -> gasit campul de mesaj
    6. ui settext "Salut Gab! Ce faci?"
    7. ui find (verificare ca textul e scris)
    8. ui read             -> gasit butonul Send
    9. ui tap send
   10. ui read             -> VERIFICAT ca mesajul a plecat
   11. ui sleep            -> eliberat ecranul
  Rezultat: mesaj "Salut Gab! Ce faci?" trimis la 14:12 (ora reala a telefonului),
  confirmat vizual (bubble verde + bife duble in lista de chat-uri).
  CONCLUZIE: cu read compact + find, taskul care esua inainte (17 citiri de ecran
  pierdute in JSON) acum reuseste din prima, complet autonom, de la memorie zero.


## 6. PROBLEME INTALNITE SI SOLUTII

1. SSL pe Android: URLError b'' la api.deepseek.com
   -> CA construit din /apex/com.android.conscrypt/cacerts + /system/etc/security/cacerts
   -> setat ssl._create_default_https_context si SSL_CERT_FILE

2. Nu exista bash pe Android: FileNotFoundError: 'bash'
   -> folosit sh -c

3. dumpsys blocat de SELinux pentru app
   -> acces prin reflection (servicii expuse public)

4. Proprietati Samsung SEM_BATTERY_* inaccesibile (intorc MIN_VALUE)
   -> datele bateriei luate din sticky broadcast ACTION_BATTERY_CHANGED

5. Capcana open(p,"w").write(open(p).read()) - TRUNCHIAZA fisierul la 0
   -> a golit MainActivity.kt de doua ori
   -> FIX: citeste intii intr-o variabila, apoi scrie

6. Assets nu se re-extrag daca stamp-ul (.assets_vN) are acelasi nume
   -> la orice modificare de assets: incrementeaza versiunea SI reporneste app-ul

7. Gradle foloseste manifest/dex din cache
   -> ./gradlew clean la modificari de manifest

8. Instalare peste APK cu alta semnatura: "signatures do not match"
   -> adb uninstall intii

9. Sensori: getSensorList(0) returneaza lista GOALA -> trebuie getSensorList(-1)

10. Reflection nu poate crea obiecte care implementeaza interfete Java
    (ex. SensorEventListener) -> pentru callback/stream folosim Kotlin

---

## 7. STRUCTURA DE FISIERE A APLICATIEI

    app/net.sys32.agent/
    |-- app/src/main/
    |   |-- AndroidManifest.xml          (105 permisiuni)
    |   |-- java/net/sys32/agent/
    |   |   |-- MainActivity.kt          (UI, pornire Python, input)
    |   |   |-- AndroidBridge.kt         (server TCP, tool-uri native)
    |   |   |-- Reflection.kt            (reflection SDK + primitive: proxy, ref, await, subclass)
    |   |   |-- Primitives.kt            (proxy de interfete, subclasare DexMaker, evenimente)
    |   |   |-- Ansi.kt                  (SGR -> Spannable)
    |   |   |-- Components.kt            (componente UI refolosibile)
    |   |   `-- CameraActivity.kt        (captura foto)
    |   |-- assets/python/
    |   |   |-- agent.py                 (creierul)
    |   |   |-- android_bridge.py        (client bridge)
    |   |   |-- memory.md                (schelet de memorie initiala)
    |   |   |-- libdynload/              (module .so pe arhitecturi)
    |   |   `-- Lib/                     (biblioteca standard Python)
    |   |       |-- zipfile/_path.py     (livrat ca fisier, folderul _path/ e ignorat de AAPT)
    |   |       `-- site-packages/       (13 pachete pure: requests, bs4, yaml, toml, ...)
    |   |-- res/mipmap-*/                (iconite toate densitatile)
    |   `-- lib/{arm64-v8a,x86_64}/      (libpython, libssl, libcrypto)
    `-- build.gradle.kts

---

## 8. STRUCTURA PE DISPOZITIV (IN RULARE)

    /data/data/net.sys32.agent/files/    <-- HOME_DIR (stocare PRIVATA, din 24 sept)
    |-- memory.md                        (memoria pe termen lung - lectiile)
    |-- context.json                     (istoricul conversatiei)
    |-- .learn_checkpoints.json          (checkpointuri /learn - ce s-a invatat deja)
    |-- bg_jobs.json                     (registrul job-urilor de fundal)
    |-- logs/                            (<job_id>.log per job + capturi streaming)
    |-- workspace/                       (fallback daca sdcard-ul nu e scriibil)
    |-- adbkey / adbkey.pub              (cheia RSA auto-generata)
    |-- tls.crt / tls.key                (certificat X.509)
    |-- libs/                            (libcrypto, libssl, pairing_* din /apex)
    |-- home/  pyhome/                   (HOME + PYTHONHOME)
    |-- python/                          (Python extras din assets + Lib/ + libdynload/)
    |-- bridge.port                      (portul bridge-ului Kotlin)
    |-- .setup_done                      (setup o singura data)
    |-- .assets_vNN                      (marker versiune assets)
    `-- key.txt                          (cheia API DeepSeek, optional)

    /sdcard/Download/Agent/              <-- VIZIBIL in file manager (doar ce e durabil)
    |-- adbkey, adbkey.pub               (* CHEIA PERSISTENTA - supravietuieste reinstalarilor)
    |-- workspace/                       (tot ce genereaza agentul)
    |   |-- .agent_folder.png            (marker pentru indexare MediaScanner)
    |   |-- logs/                        (output-uri complete de tool)
    |   `-- archive/                     (snapshot-uri context)
    `-- .old_sdcard_home/                (reziduu: vechiul HOME mutat in privat)

Nota: din 24 septembrie memory.md + context.json traiesc in STOCAREA PRIVATA
(fara FUSE/MediaProvider). Doar workspace-ul + cheia ADB raman pe sdcard, ca sa
fie accesibile din My Files -> Internal storage -> Download -> Agent (sau USB/MTP).
Fisierele de pe /sdcard SUPRAVIETUIESC la dezinstalare; cele din files/ NU.

---

## 9. COMENZI DISPONIBILE

    /help, /?           lista de comenzi
    /learn              actualizeaza memoria acum (INVATARE MANUALA - singura forma)
    /mem                statistici memorie (marime, bullets, densitate)
    /ctx                context + arhive/log-uri pe disc
    /compact            comprima contextul acum
    /verbose            comuta afisarea completa a codului/output-ului
    /spin on|off        linia live "se gandeste" (default ON)
    /nospin             alias: fara linia live (scrollback curat)
    /watch              urmareste un log/job in timp real
    /where              arata unde traieste totul (home, workspace, memory, ctx, logs)
    /run <script.py> [args]   ruleaza un script Python din workspace, cu output STREAMING
    /run_su <script.py>       ruleaza cu DREPTURI DE SHELL (uid=2000) - depasit de tool-ul `adbsh`
    /reset              sterge istoricul + checkpointurile /learn
    /exit, /quit        iese

Nota: `/auto-learn` a FOST ELIMINAT (24 sept, commit `31e342f`). Raspunde explicit
"ELIMINAT - memoria se actualizeaza DOAR manual, cu /learn". Invatarea automata dupa
fiecare task a fost scoasa din AMBELE fisiere (agent.py Android + agent-original.py Linux).

---

### Activare AccessibilityService (o singura data, de catre utilizator)

Ca agentul sa poata citi ecranul / tasta / apasa in ALTE aplicatii, serviciul de
accessibility trebuie activat manual (Android cere asta din motive de securitate):

1. **Settings > Accessibility > Installed apps / Downloaded apps**
   (pe Samsung: Settings > Accessibility > Installed applications)
2. Gaseste **"Agent (control ecran)"** si porneste comutatorul
3. Apare un dialog de avertizare cu datele pe care le poate accesa -> **Allow / OK**
4. Butonul devine verde (ON) -> serviciul e activ

Verificare ca e activ (din chat, tool `android`):
    android(tool="ui", action="status")   ->  {"ok":true,"enabled":true}

Verificare rapida cu adb (util dupa reinstalare, se pierde la update):
    adb shell settings put secure enabled_accessibility_services \
        net.sys32.agent/net.sys32.agent.AgentAccessibilityService
    adb shell settings put secure accessibility_enabled 1

Nota: la fiecare REINSTALARE a APK, Android dezactiveaza serviciul -> re-activeaza-l
din Settings (sau cu cele 2 comenzi adb de mai sus).

### Etapa 26 - Fix memorie: limita 300 -> 500 si taiere la granita de propozitie
Problema (observata in memoria de pe telefon): lectiile erau TRUNCHIATE la mijloc.
Dovada: din 55 de lectii, 5 se opreau fix la 299-300 chars, la mijloc de propozitie
(ex. "...pentru a verifica daca un app e semnat de" - fix-ul era taiat!).
Cauza: in auto_learn_check() linia `if len(_ln) > 300: _ln = _ln[:300].rstrip()`
MUTILA lectia in loc sa o respinga. Necorelare in 3 locuri: promptul cerea "max 300
chars", mem_lint avertiza la 300, dar auto_learn_check TAIA la 300. O lectie
`TRAP: situatie -> cauza -> fix` nu incape in 300 de caractere.
Fix (aplicat in TOATE cele 3 fisiere: desktop agent-original.py, device
files/python/agent.py, assets/python/agent.py):
- limita ridicata la 500 (prompt + mem_lint MAXLINE + trunchiere)
- taiere doar la GRANITA DE PROPOZITIE (` -> `, `. `, `; `, `, `), niciodata la
  mijloc de cuvant; daca nu gaseste separator, pastreaza tot
- scoate separatorul `->` ramas suspendat la coada
Cod nou:
    if len(_ln) > 500:
        _cut = _ln[:500]
        for _sep in (" -> ", ". ", "; ", ", "):
            _p = _cut.rfind(_sep)
            if _p > 200: _cut = _cut[:_p+len(_sep)]; break
        _ln = _cut.rstrip(" ,;-")
        while _ln.endswith("->"): _ln = _ln[:-2].rstrip(" ,;-")
Verificat pe device (Samsung A36), 4 cazuri:
  lectie 296 chars -> INTREAGA (inainte s-ar fi taiat)
  lectie 396 chars -> INTREAGA
  lectie 496 chars -> INTREAGA
  lectie 705 chars -> taiata la 286, la granita de propozitie, fara cuvant rupt
Nota: lectiile VECHI din memorie ramin trunchiate (fix-ul previne doar de acum inainte).
Deploy: assets v51 -> v52, rebuild (BUILD SUCCESSFUL), reinstall, reactivare accessibility.

### Etapa 27 - Fix auto-learning: doar ULTIMUL task (nu toata sesiunea)

**Problema (raportata de operator):** dupa fiecare task, auto-learning-ul
analiza TOATA sesiunea in loc de ultimul task. Rezultatul: agentul isi nota
mereu aceleasi lectii (reformulate), iar sistemul de dedup nu le prindea
(acelasi fapt, cuvinte diferite). Memoria se umplea artificial.

**Cauza:** in `auto_learn_check()`, apelul de decizie trimitea la model
`list(M)` = TOATA lista de mesaje acumulata in sesiune:
```python
_probe = ask(list(M)+[{"role":"user","content":AUTO_LEARN_PROMPT}], tools=[])
```
Desi promptul zicea "Look at the task that just finished above", contextul
trimis continea de fapt zeci de task-uri anterioare -> modelul re-analiza tot.

**Fix (2 schimbari):**

1. `auto_learn_check` primeste acum `task_msgs` (mesajele ULTIMULUI task):
```python
def auto_learn_check(task_steps, had_error, task_msgs=None):
    ...
    _msgs = list(task_msgs) if task_msgs is not None else list(M)
    _probe = ask(_msgs+[{"role":"user","content":AUTO_LEARN_PROMPT}], tools=[])
```
   Iar la apel, din bucla principala, se trimite `M[mark:]` (`mark=len(M)`
   este setat chiar la inceputul taskului, deci `M[mark:]` = doar taskul curent):
```python
auto_learn_check(TASK["steps"], TASK["err"], M[mark:])
```

2. **Limita de lectii per fisier dublata: 8 -> 16** (`mem_lint`):
```python
if len(lessons) > 16:   # era > 8
    out.append((0, "too many lesson lines ... - possible padding"))
```

**Test functional (izolat, cu spy pe ask):** cu o sesiune veche de 40 de
mesaje `STS-VECHI-*` si un task curent de 3 mesaje:
```
mesaje trimise la model: 4
   - TASK-CURENT: deschide whatsapp
   - ok
   - {"ok":true}
   - PROMPT-TEST
CONTINE SESIUNEA VECHE? False   <- FIX CONFIRMAT
CONTINE TASKUL CURENT? True
```

**Efect:** lectiile se scriu acum DOAR din ultimul task -> fara re-analiza
sesiunii, fara duplicare prin reformulare. Aplicat pe Android (device +
assets) si pe desktop (`agent-original.py`).

### Baterie: exclude agentul de la optimizare (pentru rulare pe ecran stins)

Ca agentul sa ramina VIU cu ecranul stins/blocat (Doze), exclude-l de la optimizarea bateriei:

1. Aplicatia cere asta automat o data, la prima pornire (dialog "Allow Agent to run in background?")
2. Sau manual: **Settings > Battery > Background usage limits > Never sleeping apps / Unrestricted**
   (pe Samsung: Settings > Battery > Background usage limits -> adauga `Agent`)
3. Verificare din chat: `android(tool="ui", action="service")` -> `ignore_battery_opt:true`

Fara asta, Samsung poate suspenda procesul dupa citeva minute de ecran stins.
Nota: task-urile care nu au nevoie de UI (bridge, senzori, fisiere, retea) merg si asa,
dar cu whitelist-ul e garantat ca procesul nu e omorit.

### Ce functioneaza cu ecranul STINS si telefonul BLOCAT

| Tip task | Functioneaza? |
|---|---|
| Bridge, senzori, baterie, wifi, fisiere, retea (HEADLESS) | ✅ DA (mereu) |
| Agentul lucreaza singur pe un task dat din interfata | ✅ DA |
| UI in alte aplicatii (tastare/click) | ✅ DA, daca agentul cheama `ui wake` intii |
| Talk cu utilizatorul prin interfata aplicatiei | ⚠️ ecran stins (normal) |

## 10. TOOL-URI SI ACCESUL LA SISTEM

### Tool-uri principale
- python   - executa cod Python (stdlib complet + 13 pachete pre-instalate)
- bash     - executa comenzi shell (sh -c pe Android; NU e bash)
- smart    - router automat (alege python vs bash)
- look     - analizeaza o imagine cu vision
- android  - acces la SDK Android (reflection + shortcut-uri native + tool `ui` pentru
             citirea ecranului, tastare, click, gesturi in ORICE aplicatie - vezi 3.6)
- read     - citeste un FISIER de la un offset, cu limita (paginare) - pentru fisiere mari/log-uri

### Actiuni ale tool-ului android
ui (read/settext/click/tap/swipe/scroll/back/home/recents/notifications/openapp/windows),
sensors (list/read/stream/all), camera, location (last/current/fresh),
battery (get/full), clipboard, notify, vibrate, tts, volume, wifi, device,
apps, intent, settings, system (get/full), storage, processes, network,
display, audio, telephony, nfc, usb, appinfo, eval (reflection)

### Operatii reflection (Reflection.kt)
call, new, get, set, info, services, objs, free
+ PRIMITIVE GENERALE (agent suprem):
  - proxy    - creeaza o instanta a oricarei INTERFETE Java (fiecare apel = eveniment)
  - subclass - creeaza o SUBCLASA LA RUNTIME a oricarei clase abstracte (DexMaker)
  - await    - asteapta un eveniment (callback) de la un proxy/subclasa
  - events   - toate evenimentele capturate
  - sinks    - proxy-urile/subclasele active

### Referinte de obiecte ca argumente
Orice argument poate fi ["ref", <valoare>]:
  ["ref","ctx"]         - Context-ul aplicatiei
  ["ref","app"]         - Application context
  ["ref","obj:o5"]      - obiect pastrat dintr-un apel anterior
  ["ref","svc:sensor"]  - un serviciu de sistem
Merge la op=call SI la op=new (constructori).

### Biblioteci Python pre-instalate (pure)
requests, urllib3, certifi, charset-normalizer, idna, beautifulsoup4, soupsieve,
python-dateutil, six, pyyaml, toml, packaging, typing-extensions.
Pachetele pure sunt pre-incluse; orice altceva (numpy, Pillow, zstandard...) se
compileaza NATIV pe telefon cu `toolchain(action="pip_install", package=...)`.

---


### Etapa 29 - TOOLCHAIN DE COMPILARE NATIV (toolchain.py + tpm.py)

**Ce face:** agentul isi instaleaza SINGUR un toolchain complet de compilare
(clang 21, make, cmake, ninja/samu, git, python+pip, rust, libc++, openssl)
si devine o masina de build autonoma - fara PC, fara root, fara Termux.

**Arhitectura:**
```
agent.py -> tool "toolchain"
   |
   +-- toolchain.py : bootstrap/status/env/pip_install/compile
   +-- tpm.py       : descarca .deb din repo Termux, extrage in
   |                  /data/local/tmp/tpm/usr (executabil!)
   +-- build.py     : compilare module C pentru pip
```

**Instalare:** /data/local/tmp/tpm/usr/ (uneltele) + marker .toolchain_ok

**DESCOPERIREA CHEIE (din jurnalul agentului):**
- ninja din Termux e RUPT (libandroid-spawn.so) -> cod 127 la toate comenzile
- SOLUTIE: samu (samurai 1.3) in loc de ninja
- numpy 2.5.3 compilat complet: 1625 C + 488 C++ + 165 Fortran + 29 Cython,
  217/217 tinte, functional (BLAS, LAPACK, FFT, ufuncs)

**CAPCANE REZOLVATE:**
1. /sdcard e montat noexec -> binarele trebuie in /data/local/tmp
2. .deb e arhiva "ar": ultimul membru e data.tar (nu primul xz)
3. "import gzip" loveste bug compression._common -> _streams.py oficial
4. file locking pe /sdcard -> build in /data/
5. meson PyPI fara modulul features -> meson vendored in PYTHONPATH
6. 24 functii C99 lipsa din bionic -> dezactivate 54 macro HAVE_C* in config.h
7. RUNPATH libc++_shared.so -> LD_LIBRARY_PATH

**LEGAL / LICENTE:**
Aplicatia NU include binare. Bootstrap-ul descarca din repo-ul PUBLIC Termux
(packages.termux.dev), ca apt. Licente: clang=Apache-2.0, python=PSF-2.0,
make/cmake=GPL-3.0, ninja/samu=Apache-2.0, openssl=Apache-2.0. Descarcarea si
folosirea locala nu creeaza obligatii de redistribuire. Daca cineva
impacheteaza binarele in alt produs, trebuie sa respecte licentele (inclusiv
GPL). Folosirea repo-ului de alt client e tehnica permisa dar neoficiala.

**TOOL NOU in agent:** "toolchain" (action=status/bootstrap/pip_install/
compile/env/tpm)

**Fisiere in APK:** assets/python/{toolchain.py, tpm.py, build.py, _streams.py}



### Etapa 30 - TOOLCHAIN COMPILARE NATIVA FUNCTIONAL (testat end-to-end)

**REZULTAT TESTAT (2026-09-22):**
Agentul a scris un program C, l-a compilat si l-a rulat SINGUR pe telefon:
```
calc.c -> toolchain action=compile -> COMPILE_OK
-> output: "6 * 7 = 42"
```
Agentul a detectat singur ca /sdcard e noexec, a copiat binarul in
/data/local/tmp, l-a facut executabil si l-a rulat.

**ARHITECTURA (bootstrap_direct - pur Python, fara adb in bucla):**
```
toolchain action=bootstrap
  -> _load_index()   : descarca Packages.gz din repo Termux (3001 pachete)
  -> _http_get()     : SSL cu CA bundle (certifi sau /apex conscrypt)
  -> _extract_deb()  : parseaza arhiva .ar, gaseste data.tar.xz
  -> _untar()        : parseaza tar PUR PYTHON (fara tarfile - bug Android)
  -> _fix_symlinks() : recreeaza libX.so.N + clang/ld/ar -> binarele reale
  -> _sh()           : copiaza staging (/sdcard) in prefix (/data/local/tmp)
```

**BUG-URI REZOLVATE (fiecare blocant):**
1. `compression._common` lipseste (AAPT2 ignora foldere cu "_")
   -> fix: _streams_data.py livrat ca fisier + recreare _common la runtime
2. `lzma` nu se putea importa (acelasi bug) -> _common recreat in pyhome
3. SSL CERTIFICATE_VERIFY_FAILED -> CA bundle
4. `tarfile` importa compression._common -> _untar pur Python (512B headers)
5. Numele membrilor .ar au "/" la final -> rstrip("/") (altfel endswith(".xz") esua)
6. app nu poate scrie/executa in /data/local/tmp (SELinux untrusted_app)
   -> staging in /sdcard, copiere prin shell uid=2000
7. `[TIMEOUT 40s]` din adb_client.py (signal.alarm(40) la import!)
   -> ADB_GLOBAL_TIMEOUT configurabil, default 600s
8. symlink-uri .deb (typeflag 2) nu se extrageau -> _fix_symlinks()
9. `ld` -> `lld`, apoi `ld.lld` -> `lld` (lld e driver generic)
10. compile rula in procesul app (uid 10378, nu exec /data/local/tmp)
    -> rulat prin adbsh (uid=2000)
11. output in /sdcard (noexec) -> mutat automat in /data/local/tmp

**TOOLCHAIN INSTALAT:** clang 21.1.8, make 4.4.1, cmake 4.4.3, ninja 1.13.2,
git 2.55.0, LLVM tools (ar/ld/nm/strip), pkg-config, python3 3.14.6, pip, zstd.

**TOOL in agent:** "toolchain" cu actiuni: status, bootstrap, compile, run,
pip_install, tpm, env.

**LICENTE:** bootstrap descarca din repo public Termux (ca apt). Aplicatia nu
include binare. Licente: clang=Apache-2.0, python=PSF-2.0, make/cmake=GPL-3.



### Etapa 31 - REMEDieri dupa testul AUTONOM real (2026-09-22)

Testul suprem: reset complet (fara memorie, fara toolchain), reinstalare,
task natural "compila un program C care afiseaza 6 ori 7" - FARA indicii
tehnice. Agentul a REUSIT (6 x 7 = 42) dar a intampinat erori pe care le-a
ocolit manual. Le-am eliminat din radacina:

**1. compression._common - fisier in loc de pachet**
Agentul crease `compression/_common.py` (fisier). Dar `lzma.py` face
`from compression._common import _streams` -> are nevoie de PACHET.
Fix: sterge `_common.py`, creeaza `_common/__init__.py` + `_common/_streams.py`.

**2. __pycache__ vechi bloca importul**
Chiar cu `_streams.py` prezent, Python folosea `__pycache__` din versiunea
goala. Fix: `shutil.rmtree(__pycache__)` dupa fiecare creare de `_common/`.

**3. _fix_symlinks rula in procesul app (nu vede /data/local/tmp)**
`os.listdir(ROOT+"/usr/lib")` returna gol (SELinux). Deci 0 symlink-uri ->
`clang` murea: `library "libz.so.1" not found`.
Fix: rescris complet ca SCRIPT SHELL (ruleaza prin adbsh, uid=2000):
- generic: libX.so.N.M.P -> libX.so.N si libX.so
- speciale: libz.so.1, libbz2.so.1.0, libexpat.so.1, libandroid-support.so
- binare: clang->clang-21, clang++->clang-21, ld->lld, ld.lld->lld,
  ar->llvm-ar, ranlib->llvm-ranlib, nm/objdump/strip/readelf->llvm-*,
  python->python3, pip->pip3

**4. app nu poate scrie/executa in /data/local/tmp**
- scriere: sursa C se scrie in /sdcard (sau files/), compilarea se face
  prin adbsh in /data/local/tmp
- executie: binarul se ruleaza prin adbsh (uid=2000), nu din procesul app

**REZULTAT DUPA FIX (testat pe device):**
```
bootstrap -> 65 pachete -> symlink-uri automate -> compile -> run
REZULTAT: 6*7=42   (FARA pasi manuali, FARA erori)
```

**REGULA DE AUR (de respectat in tot codul care atinge /data/local/tmp):**
Orice operatie pe fisiere din /data/local/tmp (listdir, stat, mkdir, cp,
chmod, exec) trebuie facuta PRIN SHELL (adb_client/adbsh uid=2000), NU cu
`os.*` din procesul aplicatiei (uid ~10300, SELinux untrusted_app).

## 11. LIMITARI CUNOSCUTE

Un app normal (fara root) NU poate:
- accesa dumpsys pentru servicii de sistem (Permission Denial)
- citi /sys/class/power_supply/* (Permission denied)
- folosi proprietatile Samsung SEM_BATTERY_* (intorc MIN_VALUE)
- accesa /data/data/<alt pachet>/, /system, kernel

Ce POATE (cu permisiunile din manifest):
- toate serviciile de sistem expuse public (156 din 301)
- toate senzoarele, camera, locatia, microfonul
- reflection pe orice clasa publica a SDK-ului
- storage extern complet, contacte, SMS, telefon, calendar

Ce NU se poate rula din exterior:
- Python-ul agentului NU poate fi rulat direct din adb/Termux: files/python/
  are permisiuni restrinse (drwx------) si run-as nu poate intra in subdirectoare.
  De aceea exista comanda /run (ruleaza scriptul in sandbox-ul aplicatiei).

Ce NU se poate instala:
- 13 pachete pure pre-incluse + orice altceva se COMPILEAZA nativ (clang 21 + lld +
  ninja + FLANG), direct pe telefon: lxml, numpy, Pillow, zstandard verificate E2E.
- Fortran (scipy) compileaza cu FLANG; la RULARE binarul standalone da segfault
  (initializarea runtime-ului Fortran) — de verificat pentru scipy complet.
  Alternativa: array + statistics (pentru calcule), sqlite3 (baze de date).

Capcane AAPT2 la ambalare assets:
- folderele care incep cu "_" sunt IGNORATE (fisierele .py merg, folderele NU).
  Ex: zipfile/_path/ a trebuit livrat ca zipfile/_path.py.
- fisierele simple .py la radacina unui wheel (ex. six.py) trebuie copiate explicit.

Aceste limitari NU se rezolva din permisiuni - doar cu root.

---

## 12. LECTII INVATATE

1. Masoara, nu presupune. Logcat a rezolvat ce 3 incercari oarbe n-au reusit.
2. Operatorul are mereu dreptate. Cind a zis "tot sare jos" si "sunt 5
   fisiere", a avut dreptate de fiecare data.
3. Citeste propria memorie. Capcana open(w).write(open.read()) era notata
   si tot am calcat pe ea.
4. Portabilitate prin API, nu hardcodare. Caile din Environment, nu constante.
5. Fallback mereu. Daca storage-ul extern nu e scriibil, cade in sandbox.
6. Reflexia nu ajunge pentru callback-uri. Am pierdut 3 sesiuni pe BLE pina am
   adaugat primitivele generale (proxy + subclass/DexMaker). Lectia: nu "muri in
   gura" (retete), ci UNELTE GENERALE pe masa - agentul decide singur cum le foloseste.
7. Documenteaza API-ul, nu comportamentul. Agentul a ghicit 9 sintaxe greșite de
   referinta pentru ca nu erau in ghid. Un tool cu sintaxa nedocumentata e inutilizabil.
8. Verifica ce CITESTE modelul, nu doar ce ii scrii. auto-learn raspundea "NO" pentru
   ca primea doar promptul, fara istoricul taskului (ask(list(M)+[prompt]) lipsea).
9. Cache-urile de build mint. Gradle a servit un manifest vechi (30/105 permisiuni)
   si un APK cu _path/ lipsa; doar ./gradlew clean a rezolvat.
10. AAPT2 ignora folderele cu "_". Fisierele .py merg, folderele NU -> livrate ca .py.

---

## 13. STAREA FINALA SI PASII URMATORI

### Stare finala
- APK ~34 MB (debug, neprotejat, arm64 + x86_64)
- Kotlin + CPython 3.14 compilat
- 11 tool-uri: android, ui, adbsh, python, bash, smart, read, look, bg, toolchain, multi
- 4 primitive reflection: proxy, referinte de obiecte, await/events, subclass (DexMaker)
- 25+ actiuni native (sensors, camera, location, battery, system, storage, network, display,
  audio, telephony, nfc, usb, appinfo, processes, ...)
- tool `ui` (AccessibilityService): citirea ecranului, TASTARE, CLICK, gesturi, scroll,
  navigare, deschidere app-uri - in ORICE alta aplicatie, fara root
- 13 biblioteci Python pre-instalate (pure): requests, bs4, dateutil, yaml, toml, packaging...
- Acces la hardware si sistem (maxim posibil fara root)
- Memorie persistenta cu auto-invatare (filtrata pe relevanta + mediu)
- Workspace vizibil: /sdcard/Download/Agent/ (memorie, context) + workspace/
- Comenzi: /help /learn /auto-learn /mem /ctx /compact /verbose /nospin /where /run /run_su /watch /reset /exit
- Interfata terminal in engleza, raspuns in limba operatorului, auto-scroll corect,
  stop generare, fara tabele pe ecran mic
- Iconita profesionala
- Ruleaza in BACKGROUND (foreground service): taskul continua cind app-ul e minimizat
- Merge si cu ECRANUL STINS/BLOCAT: task-uri headless 100%, task-uri UI prin `ui wake`
- Excludere de la optimizarea bateriei (Doze) ceruta automat la prima pornire
- Senzori functionali (fix registerListener + Handler mainLooper)
- Vedere + control asupra altor aplicatii (AccessibilityService, fara root)
- Repo git cu push pe GitHub

### De facut la final (cind codul e stabil)
- R8/ProGuard pe build release (reduce + obfuscare Kotlin)
  Nota: agent.py ramine citibil (Python in assets) - pentru protectia lui
  e nevoie de criptare assets sau PyArmor
- Reducere dimensiune: split ABI (arm64-only ~18MB), scoatere _testcapi
- Eventual: descoperire SD card extern


---

### Etapa 32 - HOME_DIR in stocarea PRIVATA (context.json/memory.md nu mai stau pe /sdcard)

**Problema:** `context.json` traia in DOUA locuri (copia privata + oglinda pe /sdcard).
MediaProvider/FUSE genera zgomot in logcat si erori de quota:
    "Failed to update quota type for .../context.json.tmp: No such file or directory"
    "Failed to revoke permissions for .../context.json from DownloadStorageProvider"

**Fix (commits `f514c36`, `54d3fa7`, `207d2c6`, `91ab81c`):**
- `HOME_DIR` = sandbox-ul PRIVAT (`/data/data/net.sys32.agent/files/`), NU sdcard-ul
- `context.json`, `memory.md`, `bg_jobs.json`, `logs/`, `.learn_checkpoints.json`
  traiesc acolo (zero FUSE, zero zgomot MediaProvider)
- `AGENT_HOME` se IGNORA acum pentru HOME (ramane doar ptr compat) - il folosim
  DOAR ca sa localizam `workspace/` de pe sdcard
- `workspace/` ramane pe /sdcard (vizibil in file manager)
- migrare automata o singura data din locatiile vechi (`/sdcard/agent`, sandbox)

**Dovada (pe device, 25 sept):** `files/context.json` = 674 KB, `files/memory.md` = 6.6 KB,
`/sdcard/Download/Agent/` contine doar `adbkey*` + `workspace/` + `.old_sdcard_home/`.

### Etapa 33 - Sistem de checkpoint la /learn (nu mai re-invata lectiile stiute)

**Problema:** `/learn` re-analiza TOATA sesiunea si rescria lectii deja existente
(reformulate), umfland artificial memoria.

**Fix (commits `48d1f0a`, `685c622`, `5e74742`, `39b9771`):**
- `/learn` acopera INTREAGA sesiune (nu doar coada)
- fisiere de checkpoint `.learn_checkpoints.json` retine ce s-a invatat deja
- `/reset` goleste SI checkpointurile, nu doar istoricul
- `/learn` NU mai sterge lectiile lungi din memory.md (regresie reparata)

### Etapa 34 - ANTI-POISON: porti de validitate inainte de scrierea in memory.md

**Obiectiv:** nicio lectie contrazicatoare/greșita sa nu ajunga in memoria permanenta.

**Fix (commits `eb052a4`, `0a35b4e`, `38a9341`, `da96836`):**
- DOUA porti inainte de scriere: poarta de CONTRADICTIE + poarta de VALIDITATE API
- lectiile blocate merg in `memory_quarantine.md`, NICIODATA in `memory.md`
- poarta optimizata: mai putine fals-pozitive (40/40 pe ambele fisiere)
- portat identic in `agent.py` (Android) si `agent-original.py` (Linux)

### Etapa 35 - ADB PYTHON-FIRST: adbsh rescris pe adb_client direct

**Problema:** sesiunea ADB persistenta aduna erori (output cu un apel in urma, output gol
intermitent, pachete straine in ordine gresita).

**Fix (commits `f90aa3d`, `d26833f`, `cf682eb`, `ad26cbd`, `cbcdd5b`):**
- `run_adbsh_tool` rescris pe `adb_client` direct (fara sesiune persistenta)
- drenare `select-gated`: **588 ms -> 48 ms/comanda (12x)**
- global timeout DOAR la cerere (nu pe fiecare comanda)
- cheie publica in format big-endian (AOSP)

### Etapa 36 - FIX 1-8 ACCES MAXIM (raportul AGENT SUPREM)

**Implementat (commit `c47e3b4`, testat 8/8 pe SM-A366B):**
- screenshot prin AccessibilityService (`takeScreenshot`)
- NotificationListener (citire notificari ale altor app-uri)
- IME (citire text din campurile de input)
- VpnService, MediaProjection FGS, DeviceAdmin
- GuardService + BootReceiver (anti-kill, repornire automata)
- actiuni noi in bridge: `notif`, `ime`, `vpn`, `capture`, `guard`

**Capcane documentate (in memory.md):**
- `takeScreenshot()` a11y NU merge in `/data/local/tmp` (EACCES) -> scrie in filesDir
- rate-limit real: ~1 captura/secunda (nu e bug)
- MediaProjection (Android 14+) cere `registerCallback` INAINTE de `createVirtualDisplay`

### Etapa 37 - FIX URGENT: touch exploration bloca TOT telefonul

**Problema (commit `1c308d5`):** flag-urile `flagRequestTouchExplorationMode` +
`canRequestTouchExplorationMode` din `accessibility_service_config.xml` activau
`touch_exploration_enabled=1` -> TOATA atingerea pe telefon devenea blocata
(prima atingere doar exploreaza, a doua apasa). Utilizatorul credea ca s-a blocat telefonul.

**Fix:** scoase AMBELE din config XML (nu sunt necesare pentru acces). Verificat:
`touch_exploration` ramane 0 chiar cu a11y activ; home/recents/tap merg normal.

**DEBLOCARE RAPIDA (daca se intampla):**
    settings put secure enabled_accessibility_services ''
    settings put secure accessibility_enabled 0
    settings put secure touch_exploration_enabled 0

### Etapa 38 - Optimizari robustete + baterie + UI

**Watchdog (commit `99f2335`):** verifica prea agresiv `pyProc.isAlive` (setat cu
intarziere in thread -> null -> repornire in bucla, 3 PID in 15s). Fix: verificare
proprie `pyProc` + cooldown 20s + `lastPythonStart` la pornire -> 1 PID stabil.

**Baterie:** wake lock cu `acquire(30min timeout)` + renew la inceputul taskului.
Idle: CPU 0%, RAM 105 MB (locul 11, sub systemui/gms).

**UI (commit `76fbbba`):**
- sageata scroll `btnDown` ELIMINATA
- `launchMode="singleTask"` (notificarea nu mai deschide instanta noua)
- limita `MAX_UI_CHARS=200000` + `lastLine()` optimizat (fara lag la revenire din bg)

---

### Etapa 28 - SUPER-PUTERI: ADB shell uid=2000 (fara root, fara PC)

**Obiectiv:** agentul sa aiba acces la comenzi de sistem (uid=2000 shell), nu doar la ce poate app-ul (uid 10362).

**Descoperirea cheie:**
- app-ul se poate autentifica la adbd-ul LOCAL (127.0.0.1:5555) prin protocolul ADB clasic
- cheia trebuie sa fie in formatul corect (`QAAAA...`, ~700 chars, FARA username)
- adbd accepta cheia de pe localhost dupa o singura aprobare "Allow"

**Ce poate face agentul acum (dovedit, 7/7):**
    adbsh id                                  -> uid=2000(shell), groups include input/adb/inet
    adbsh 'pm list packages -3 | wc -l'       -> numarul de app-uri third-party
    adbsh 'dumpsys battery | grep level'      -> bateria
    adbsh 'settings get global airplane_mode_on' -> setari (citire + scriere)
    adbsh 'screencap -p /sdcard/x.png'        -> screenshot
    adbsh 'input keyevent 3'                  -> UI automation FARA accessibility
    adbsh 'getprop ro.product.model'          -> proprietati sistem

**Ce deblocheaza (ce app code NU poate):**
    pm grant/revoke (permisiuni runtime)   appops set
    settings put secure/global             dumpsys complet
    input tap/text/keyevent                run-as pe alte app-uri
    screencap, uiautomator dump            logcat, svc, wm size/density

---

#### 28.1 - AUTO-SETUP la prima pornire (`adb_setup.py`)

Integrat in MainActivity: ruleaza inainte de `agent.py`, o singura data.

    1. LIBS: copiaza libcrypto.so, libssl.so, libadb_pairing_auth.so,
             libadb_pairing_connection.so din /apex/com.android.adbd/lib64
             (si /apex/com.android.conscrypt) in files/libs/
    2. CHEIE: genereaza RSA 2048 -> adbkey (privata) + adbkey.pub (format ADB)
              ★ SALVATA in /sdcard/Download/Agent/ (PERSISTENTA, supravietuieste
                reinstalarilor si "Clear data"!)
    3. CERT: genereaza X.509 self-signed din cheie (tls.crt + tls.key)

**Idempotent:** daca cheia exista in /sdcard, o refoloseste (nu regenereaza!).

---

#### 28.2 - Tool nou: `adbsh`

    adbsh(cmd="pm grant net.sys32.agent CAMERA")   comanda shell ca uid=2000
    adbsh(cmd="dumpsys battery")                    output complet
    adbsh(cmd="input tap 540 1200")                 UI automation

Client: `adb_client.py` (protocol ADB pur Python: CNXN/AUTH/OPEN/WRTE).
Auth: RSAPUBLICKEY direct (adbd auto-aproba pe localhost).

**AUTO-DETECTIE PORT (important!):**
    `Adb()` fara parametru citeste `getprop service.adb.tcp.port` si se
    conecteaza pe acel port (5555, 55555 SAU ORICE valoare setata de
    `adb tcpip <port>`). Daca getprop nu raspunde -> fallback: testeaza
    5555, 55555, 5556. Astfel agentul merge indiferent de portul ales.

**Formatul cheii (critic!):**
    - `adbkey.pub` = [4B len_modulus][modulus][4B len_exponent][exponent], base64
    - ~700 chars pentru RSA 2048
    - NICIODATA cu username lipit (a cauzat bucla de "Allow USB debugging")

---

#### 28.3 - CHOICE: agentul decide INTELIGENT ce tool foloseste

Adaugat in system prompt (ANDROID_GUIDE) reguli explicite:

    (1) ECRAN (read/tap/text)      -> android ui (nativ, instant, 0 auth)
    (2) SENZORI/CAMERA/BATTERIE    -> android (nativ, instant)
    (3) REFLECTION SDK             -> android eval
    (4) FISIERE/VISION             -> python, bash, read, look
    (5) SUPER-PUTERI (uid=2000)    -> adbsh DOAR cand app code NU poate:
                                      permisiuni, settings put, dumpsys, input fara a11y

**Test live (dovedit):** la 5 intrebari, agentul a ales:
    1. app pe ecran       -> android ui read   (motiv: nativ, 10x mai rapid)
    2. nr app-uri         -> adbsh (pm list -3 | wc -l)  (motiv: nevoie de pipeline shell)
    3. bateria            -> android battery get (motiv: nativ instant)
    4. senzor lumina      -> android sensor (motiv: instant)
    5. mod avion          -> android settings get (motiv: citirea e permisa nativ)

**Rezultat:** 4/5 native (rapide), 1/5 super-puteri (unde era nevoie). Ales corect + constient.

---

#### 28.4 - CE NU SE POATE (limite reale Android)

1. `adb tcpip 5555` - NU poate fi rulat de app (necesita permisiune de sistem/root)
   => o data dupa restart telefon, de pe laptop (5 secunde)
2. Aprobarea "Allow USB debugging" - dialog de sistem, o singura data
   => DAR cu cheia persistenta in /sdcard, tine pentru TOTDEAUNA (nu la reinstalare)
3. PAIRING WIRELESS (SPAKE2+TLS) - NU functioneaza din app:
   - protocolul e implementat corect (TLS+SPAKE2+PEER_INFO toate OK)
   - dar decrypt-ul final esueaza: parola SPAKE2 = cod + TLS ExportKeyingMaterial(64)
   - Python ssl NU expune export_keying_material => mismatch de chei
   - libadb_pairing_connection.so ar face export-ul, dar da fdsan/peer=NULL pe Samsung
   => singura cale wireless: client ADB extern (PC) cu `adb pair`

---

#### 28.5 - REZUMAT: ce are agentul suprem

    android      bridge Kotlin: senzori, camera, reflection SDK, ui (accessibility)
    ui           vede + controleaza alte app-uri (read/find/click/settext)
    adbsh        SUPER-PUTERI uid=2000: pm, dumpsys, settings, input, screencap...
    python       stdlib + pachete pure-Python
    bash         shell in sandbox-ul app-ului
    smart        auto-router python/bash
    read/look    fisiere mari + analiza imagini

**Autonomie:** instalezi APK-ul -> isi genereaza cheia + certul + libs SINGUR.
Singura intervenție: `adb tcpip 5555` + "Allow" o data (dupa restart).

---

## ANEXA A - PALETA DE CULORI

    Fundal:          #0D1117
    Text principal:  #ABB2BF
    Accent (albastru):#61AFEF
    AGENT (titlu):   rosu 38;5;203
    You >:           albastru 38;5;110
    TASK (chenar):   verde
    Comenzi:         ...(vezi agent.py, secțiunea de culori)

---

## ANEXA B - COMPILAREA

> **Vezi si sectiunea OPERATIUNI (OP.1-OP.7) de mai sus — acolo e procedura completa.**
> `env.sh` NU mai exista (sters); variabilele sunt setate de `build_app.sh`.

    # build + install + start (recomandat, face tot)
    cd /home/gab/Desktop/android_agent/workspace/app
    ./build_app.sh

    # sau manual:
    export JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64
    export ANDROID_HOME=/home/gab/android
    export ANDROID_SDK_ROOT=/home/gab/android
    export PATH=$JAVA_HOME/bin:$ANDROID_HOME/platform-tools:$PATH
    cd net.sys32.agent
    ./gradlew assembleDebug --offline

    # instalare
    /home/gab/android/platform-tools/adb install -r app/build/outputs/apk/debug/app-debug.apk
    # daca semnatura difera:
    /home/gab/android/platform-tools/adb uninstall net.sys32.agent

    # Python pentru Android (o singura data / rar) - vezi OP.6
    # ATENTIE: sursele NU sunt pe disc (build/ e in .gitignore) - re-descarca-le intai
    cd /home/gab/Desktop/android_agent/workspace/build/Python-3.14.7
    ./android.py build aarch64-linux-android     # telefon
    ./android.py build x86_64-linux-android      # emulator

---

Sfirsitul documentului.

---


---

## Etapa 32 - REMEDIERI TOOLCHAIN (compilarea C/C++ reparata complet)

**Context:** la sfirsitul sesiunii precedente numpy esua la pasul 1/345 cu
`ninja: subcommand failed` / `FAILED: [code=127]` si nu se stia de ce
(operatorul a intrerupt diagnosticul). Reparat acum, end-to-end.

### Cauzele REALE (4, toate inlantuite)

| # | Simptom | Cauza | Fix |
|---|---------|-------|-----|
| 1 | `code=127`, `library libX.so not found` | .deb-urile Termux au **RUNPATH hardcodat** la `/data/data/com.termux/files/usr/lib`, director care NU exista aici | `patchelf --set-rpath` pe toate binarele + .so + modulele din `lib-dynload` |
| 2 | `ninja: subcommand failed` | **ninja din Termux e RUPT**: nu poate executa NICIUN proces (nici `/system/bin/sh`) | inlocuit cu **samu** (samurai 1.9.0), care face exact acelasi lucru |
| 3 | `rm: inaccessible or not found` | subprocesele meson/ninja primesc **env minimal** (PATH doar cu prefix) -> `rm`/`sh` din `/system/bin` lipsesc | wrapper-ele adauga `/system/bin:/system/xbin` in PATH |
| 4 | `call to undeclared function ctanl/ccoshl` (numpy) | clang are target **implicit android24**; functiile C99 cu `__INTRODUCED_IN(26)` sunt ASCUNSE | wrapper `cc/clang` injecteaza `--target=aarch64-linux-android<API real>` |

**Piesa lipsa la linkare:** pachetul **`ndk-sysroot`** (nu era instalat, desi
era in lista) - aduce crt-urile (`crtbegin_dynamic.o`) si stub-urile de link.
`libm.so` NU exista in Termux: pe Android 11+ e fuzionat in libc, iar simbolurile
C99 complete (ctanl, ccoshl...) sunt in
`/apex/com.android.runtime/lib64/bionic/libm.so` -> se linkeaza cu `-L` acolo.

**Piesa lipsa la rulare:** extensiile C++ (numpy) **nu au `NEEDED libc++_shared.so`**
dar folosesc simboluri din el -> `ImportError: cannot locate symbol
_ZTVNSt6__ndk117bad_function_callE` -> fix: `LD_PRELOAD=<prefix>/lib/libc++_shared.so`.

### Functii noi in toolchain.py
- `_patch_runpath()` - corecteaza RUNPATH (binare + libs + lib-dynload)
- `_fix_ninja()`    - inlocuieste ninja rupt cu samu
- `_fix_cc_wrappers()` - wrappere cc/clang cu `--target` + PATH complet
- `_device_api()`   - detecteaza API-ul real (36 pe Android 16), cu fallback
- `check()`         - acum verifica FUNCTIONAL (compile_test), nu doar prezenta

Se apeleaza automat la finalul `bootstrap_direct()`. `env_vars()` returneaza
acum CFLAGS/LDFLAGS cu target + libm bionic, si `LD_PRELOAD`.

### REZULTAT (dovedit azi, pe telefon)
```
pip install numpy   ->  RC=0, "Successfully built numpy", "Successfully installed numpy-2.5.3"
import numpy        ->  NUMPY 2.5.3   sum=15   det=-2.0
```
Compilare nativa reala pe ARM64, fara root, fara Termux.

### CAPCANE
- `patchelf` nu se poate patch-ui PE SINE ("Text file busy") -> copie care
  patchuieste originalul.
- patch-ul pe 200+ fisiere intr-o singura bucla Python poate segfaulta la final
  (memorie) - dar lucrarea se face; verifica INTOTDEAUNA rezultatul, nu doar exit code.
- `chmod u+r` inainte de patchelf: unele binare au mod `--x` si nu pot fi citite.


---

## Etapa 33 - OPTIMIZARE COMPLETA (test end-to-end: numpy compilat de la 0)

**Testul:** app resetata complet (zero memorie, zero toolchain), task = "compileaza
numpy de la 0". **Runda 1** (fara optimizari): ~2h, blocat cu code=127, 6+ erori
nerezolvate. **Runda 2** (cu fixurile din toolchain.py): **17:54, 103 pasi, SUCCES**
(numpy 2.5.3 functional: array, matmul, det/inv/eig, FFT, random, SIMD).

### Cauzele REALE gasite (toate inlantuite, fiecare reparata la sursa)

| # | Simptom | Cauza | Fix in cod |
|---|---------|-------|-----------|
| 1 | `code=127`, `library libX.so not found` | .deb-urile Termux au RUNPATH hardcodat `/data/data/com.termux/files/usr/lib` (inexistent aici) | `_patch_runpath()` (patchelf pe binare+libs+lib-dynload) |
| 2 | `ninja: subcommand failed` | ninja din Termux e RUPT (nu executa niciun proces) | `_fix_ninja()` → samu |
| 3 | `rm: inaccessible or not found` | meson/ninja dau subprocese cu PATH minimal | wrapperele pun `/system/bin` in PATH |
| 4 | `undeclared function ctanl/ccoshl` | clang target implicit android24 ascunde C99 | `_fix_cc_wrappers()` → `--target=<API real>` |
| 5 | numele **TRUNCHIATE** in lib-dynload (`.so` dispare) | tar GNU pune numele lungi in `typeflag='L'`, `_untar` il ignora | `_untar()` cu suport `L`/`K` + PAX |
| 6 | **63 scripturi** moarte | shebang `#!/data/data/com.termux/files/usr/bin/bash` | `_fix_wrappers_shebang()` |
| 7 | `LIBDIR` = calea Termux (71 variabile!) | `_sysconfigdata` are prefixul de compilare | `_fix_sysconfig()` rescrie prefixul |
| 8 | `Compiler cython cannot compile programs` | **TOATE** `.pc` au prefix Termux (`pkg-config --cflags python3` → cale moarta) | `_fix_sysconfig()` repara **toate** `.pc` |
| 9 | `cannot locate symbol _ZTVNSt6__ndk1...` | extensiile C++ n-au `NEEDED libc++_shared.so` | `_fix_libcxx_needed()` + `-lc++_shared` in LDFLAGS |
| 10 | `CERTIFICATE_VERIFY_FAILED` (pip HTTPS) | Python Termux nu gaseste CA store | `_fix_ca_bundle()` + `SSL_CERT_FILE` |
| 11 | `python3`/`pip3` lipsesc | Termux nu face symlink-urile | `_fix_symlinks()` |
| 12 | `pip` = script cu shebang Termux | wrapper, nu binar | `_fix_symlinks()` il rescrie |
| 13 | `_prepare_dirs()` nedefinita | functie pierduta la un patch | restaurata |
| 14 | false negative la `check()` | `os.path.exists` **nu vede** `/data/local/tmp` din sandbox | toate verificarile prin `_sh` |
| 15 | `Module "features" does not exist` | numpy are nevoie de meson-ul propriu (vendored) | documentat (meson-python il foloseste automat) |
| 16 | linking fara `-lc++_shared` | meson-python nu adauga libc++ | `LDFLAGS` explicit |

### Functii noi in toolchain.py (9 fixuri automate in bootstrap)
`_prepare_dirs` · `_patch_runpath` · `_fix_ninja` · `_fix_cc_wrappers` ·
`_fix_symlinks` · `_fix_wrappers_shebang` · `_fix_sysconfig` · `_fix_ca_bundle` ·
`_fix_libcxx_needed` · `_device_api` · `check()` (functional)

### Mod de operare nou (agent.py)
- `pip_install` foloseste `_toolchain_exports()` (env complet din `env_vars()`)
  si apeleaza automat `_fix_libcxx_needed()` dupa instalare
- `compile` foloseste acelasi env complet
- `env_vars()`: PATH cu `/system/bin`, `--target`, `-L bionic`, `LD_PRELOAD`,
  `SSL_CERT_FILE`, `HOME`, `TMPDIR`, `PIP_CACHE_DIR`

### REZULTAT (masurat)
```
Runda 1: ~2h, esec (code=127)
Runda 2: 17:54, 103 pasi, SUCCES
  numpy 2.5.3 | array, matmul, det, inv, eig, FFT, random, SIMD — toate OK
```
Agentul a auto-invatat 4 lectii (identice cu diagnosticul de dezvoltare),
scrise singur in memory.md.

### CAPCANE DE RETINUT
- RUNPATH-ul se **pierde** cand agentul reinstaleaza pachete Termux → `_patch_runpath`
  trebuie re-rulat (bootstrap-ul o face).
- `patchelf` nu se poate patch-ui pe sine (Text file busy) → copie.
- patch pe 200+ fisiere intr-o bucla poate da segfault la final, dar munca se face:
  verifica REZULTATUL (readelf), nu exit code-ul.


---

## Etapa 34 - OPTIMIZARE dupa raportul llama.cpp (pre-flight + profiluri de build)

**Context:** agentul a compilat llama.cpp de la 0 (REUSIT, ~50 min, inferenta
functionala) dar a lovit **9 obstacole**; a scris singur raportul
`RAPORT_COMPILARE_llama.cpp.md` (in workspace si in repo) cu clasificarea
fiecarei probleme: necesara / evitabila, cu cost in apeluri si fix propus.

### Obstacolele raportate si fixurile aplicate

| # | Obstacol | Cauza | Fix implementat |
|---|----------|-------|-----------------|
| 1 | `git` fara `remote-https` | pachetul Termux e incomplet | documentat; `git` local merge |
| 2 | `curl` din /system/bin e rupt | legat de libcrypto incompatibil | regula: foloseste `python3 urllib` |
| 3 | `CERTIFICATE_VERIFY_FAILED` | python nu gaseste CA | `SSL_CERT_FILE` in `env_vars()` + `env.sh` (**deja**) |
| 4 | `make: /data/.../termux/sh: No such file` (cmake) | make are **SHELL hardcodat** la calea Termux | `_fix_termux_paths()` patch binarul make |
| 5 | `cmake` nu gaseste `api-level.h` | `PREFIX` nesetat | `PREFIX` in `env.sh` + profil cmake |
| 6 | `undefined symbol: std::__ndk1::cout` | `-stdlib=libc++` NU e suficient | `_fix_cxx_linker()` wrapper clang++ cu `-L -lc++_shared` |
| 7 | `undefined symbol: log2f/expf/sinf...` | `/system/lib64/libm.so` e STUB | `-L /apex/.../bionic` in profil + LDFLAGS (**deja**) |
| 8 | comenzi `adbsh` lungi blocheaza sesiunea | output bufferizat/trunchiat | documentat: scripturi in fisier + logfile |
| 9 | `git clone --depth` fara remote-helper | pachet incomplet | documentat |

### Functii noi (recomandarile R1-R9 din raportul agentului)

- **R1 `_write_env_file()`** - scrie `/data/local/tmp/tpm/env.sh` cu TOT mediul
  (PREFIX, PATH, LD_LIBRARY_PATH, SSL_CERT_FILE, CC/CXX, CFLAGS, LDFLAGS, TMPDIR,
  HOME, MAKEFLAGS). `adbsh` il **surseaza automat** la fiecare comanda, deci
  agentul nu mai scrie export-uri manual.
- **R2/R4 `preflight()`** - test de 10 secunde care compileaza si **linkeaza**
  C, C++ (STL), math (libm bionic), verifica PREFIX, make SHELL, SSL, git si
  face un **cmake+build real** de proiect C++ minim. Prinde toate problemele
  de mediu INAINTE de un build de 10 minute.
- **R3/R4b `profile("cmake"|"cflags"|"cxxflags"|"ldflags")`** - flaguri
  PREFABRICATE cu tot ce trebuie (target API, libc++, libm bionic, rpath,
  `CMAKE_SYSTEM_VERSION`). `profile("cmake")` intoarce un **script shell** gata
  de rulat (`sh prof.sh <src> <build>`) - evita problems de word-splitting.
- **R5/R6** - `adbsh` surseaza `env.sh` automat; actiunea `toolchain fix`
  re-aplica toate fixurile dupa reinstalarea de pachete Termux.
- **`_fix_cxx_linker()`** - wrappere `clang/clang++/cc/c++/gcc/g++` in
  `/data/local/tmp/wrap` care injecteaza `--target`, `-L prefix`, `-L bionic`,
  `-lc++_shared`. Orice build C++ linkeaza corect fara flaguri speciale.
- **`_fix_termux_paths()`** - patch pe binarele cmake/make (inlocuire de siruri
  cu padding NUL, caile lungi intai). NU patch-uieste libpython/libLLVM (se corup).

### Actiuni noi in tool-ul `toolchain`
`preflight` · `profile` · `fix` · `env-file` (+ enum extins, descriere actualizata
cu regula: **preflight INAINTE de orice build mare**).

### REZULTAT
```
preflight(): c_compile cxx_compile math_link prefix_hdr make_shell ssl cmake git cmake_build  -> TOATE TRUE
cmake + C++ (STL, math, vector) -> CONFIGURE OK | BUILD OK | CMAKE_CXX_MATH_OK 7
```


---

## Etapa 35 - comanda `/run_su` (rulare cu DREPTURI DE SHELL, uid=2000)

**Problema:** `/run` ruleaza scriptul in sandbox-ul aplicatiei (uid=app ~10300).
SELinux ii interzice accesul la `/data/local/tmp` si executia binarilor
compilate acolo. Deci un script care foloseste llama.cpp, toolchain-ul nativ,
modele GGUF etc. **NU putea fi rulat** din aplicatie.

**Solutia:** comanda noua `/run_su <script> [args...]` in agent.py:
- ruleaza scriptul **prin `adbsh`** (clientul ADB intern, uid=2000 shell)
- surseaza automat `/data/local/tmp/tpm/env.sh` (mediul complet)
- detecteaza tipul: `.py` -> `python3` din toolchain; `.sh` -> `sh`; altfel executabil
- streaming live al output-ului (ca `/run`), salvare automata la output lung

**Verificat pe device:**
```
/run_su test_su.sh          -> uid=2000, vede /data/local/tmp, llama-cli --version OK
/run_su run_chat.sh -p "..." -> LLM local (Qwen2.5-0.5b) a RASPUNS: 10.6 tok/s
```

**Utilizare:**
```
/run              -> uid app (sandbox, fara /data/local/tmp)
/run_su           -> uid 2000 (shell): /data/local/tmp, toolchain nativ, llama.cpp
```
Atentie la quoting: ca in orice shell, spatiile se pun intre ghilimele:
`/run_su run_chat.sh -p "Buna, cine esti?"`

**In system prompt:** agentul e instruit sa recomande `/run_su` cand operatorul
trebuie sa ruleze ceva compilat (binar, llama.cpp, model GGUF, script de chat)
si sa scrie lansatorul ca `.sh` in workspace.


---

## Etapa 36 - FIX context invalid: `tool_calls` orfane (HTTPError de la API)

**Simptom:** dupa ce operatorul scrie in chat in timpul unui task, orice mesaj
nou da:
```
[API] HTTPError: An assistant message with 'tool_calls' must be followed by
tool messages responding to each 'tool_call_id'.
(insufficient tool messages following tool_calls message)
```
Agentul devine INUTILIZABIL pana la `/reset`.

**Cauza (reala, reprodusa):** bucla principala face
`M.append({"role":"user","content":q})` **fara sa verifice** starea istoricului.
Daca task-ul anterior s-a oprit cu un mesaj `assistant` care declara
`tool_calls` (ex. bootstrap pornit, apoi API error / intrerupere), acel mesaj
ramane **orfan**. Mesajul `user` nou se adauga IMEDIAT dupa el -> API-ul
respinge intreaga cerere (cerinta protocolului: fiecare `tool_call_id` trebuie
sa aiba un mesaj `tool` inainte de orice alt rol).

**Fix (2 locuri):**
1. **`sanitize_msgs(msgs)`** - funcție noua care parcurge istoricul si, pentru
   fiecare `assistant` cu `tool_calls`, verifica ca TOATE id-urile au raspuns
   `tool` imediat dupa; cele lipsa primesc un mesaj `tool` de completare
   („not executed - the run was interrupted"). Idempotenta.
2. Apelata **inainte de fiecare cerere API** (`ask()`) SI **inainte de a adauga
   un mesaj user nou** in bucla principala. Deci contextul nu mai poate rămâne
   invalid, indiferent ce face operatorul in timpul unui task.

**Verificat:** pe contextul real care producea eroarea, `sanitize_msgs` a
reparat 1 tool_call orfan; validarea arata toate perechile `tool_calls`/`tool`
in ordine corecta; taskul nou ruleaza fara HTTPError.

**Bonus:** contextul de pe dispozitiv a fost reparat in-place (nu a fost nevoie
de `/reset`), deci operatorul nu pierde istoricul.


---

## Etapa 37 - tool `bg`: gestionar de procese in fundal (rezolva "output amestecat")

**Simptom raportat de operator:** agentul lansa procese in fundal si apoi
"uita" de ele, isi amintea pe parcurs, avea output amestecat si comenzi
amestecate pe fundal de care nu era constient.

**Dovezi din conversatia reala (llama.cpp):**
- `[73]` "pornit pid=16405" (build lansat cu nohup)
- `[79]` "Log-ul e incomplet (output-ul e in buffer). Build-ul poate inca ruleaza"
- `[85]` "se pare ca VECHIUL build inca rula in fundal si scria in build.log (confuzie de output)"
- `[121]` "Output-ul e din log-ul VECHI de configurare"
- `[131]` "Output amestecat din nou, dar 8 procese clang active"

**Cauza rădăcină:** NU exista un registru al proceselor. Agentul lansa cu
`nohup ... &` prin adbsh, apoi citea fisiere de log FARA sa stie carui job
apartin si daca sunt actuale. Doua build-uri scriau in acelasi log.

**Solutia: tool nou `bg`** (gestionar persistent de joburi):
| Actiune | Ce face |
|---------|---------|
| `start cmd=... name=...` | lanseaza in fundal cu **log unic timestampat** + PID inregistrat |
| `status` | ce ruleaza ACUM (verifica `/proc/<pid>`, nu ghiceste) + durata + marimea log-ului |
| `log job=<id> lines=N` | ultimele N linii din log-ul ACELUI job (cu antet: cand a pornit, PID) |
| `kill job=<id>` | opreste job-ul + copiii |
| `list` | toate joburile (inclusiv terminate) |
| `clean` | sterge joburile terminate si log-urile lor |

Registru persistent: `/sdcard/Download/Agent/bg.json`; loguri: `/data/local/tmp/bg/<job>.log`.

**Regula in system prompt:** "orice comanda care poate lua >30s trece prin `bg`;
NICIODATA `nohup`/`&` brut; inainte de a porni o rulare noua a aceluiasi lucru,
verifica `bg status` si omoara resturile; citeste log-ul DOAR prin `bg log`,
care iti spune carui job apartine si cand a inceput."

**Verificat:** toate cele 6 actiuni testate (start/status/log/kill/list/clean);
statusul foloseste `/proc/<pid>/stat` (prinde si procesele zombie).

---

## Etapa 38 - OPTIMIZARI DE COST (citirea fisierelor mari + tool `read`)

**Problema (masurata):** output-ul unui tool call se taie la ~8000 chars (capetele raman, mijlocul dispare).
Marcajul promitea „NOT LOST: textul complet e in logs/...log", dar **logul de pe disc era plafonat la fel** →
mijlocul nu exista nicaieri. Citirea unui fisier de 92 KB a costat ~20 de pasi de re-citire.

**Cauza rădăcină:** `TOOLMAX=1800` (fereastra) era prea mic pentru o citire deliberata, iar `_store()` scria
logul fara sa verifice ca e complet.

**Fixuri:**
| # | Ce | Detaliu |
|---|----|---------|
| 1 | `CHUNK` configurabil | `AGENT_CHUNK` (default 7000) ridica plafonul ferestrei; `0` = comportamentul vechi |
| 2 | `_budget()` | alege plafonul corect per apel |
| 3 | `_cut()` spune adevarul | scrie `NOT LOST` **doar** daca logul e verificat complet; altfel `LOST - RE-RUN` |
| 4 | `_store()` verifica | `os.path.getsize(p) == len(o.encode())`, nu presupune |
| 5 | **tool `read`** | citire paginata cu **buget GARANTAT** (`path/offset/limit/budget/grep`) + footer `NEXT: offset=N` |
| 6 | avertisment preventiv | la 90% din buget, **o singura data per task** |

**Metoda de lucru pentru fisiere mari (in system prompt):**
```
(1) read cu grep = regex   -> harta fisierului cu numere de linie, in UN apel
(2) read cu offset/limit   -> doar sectiunea de interes
```

**MASURAT:** citirea `readme.md` (92.621 chars): **18 pasi -> 2 pasi**, input **4.82M -> 0.418M chars (-91%)**.

---

## Etapa 39 - OPTIMIZARI DE COST (batching + densitate)

**Principiul descoperit (masurat):** API-ul DeepSeek e **stateless** → la fiecare cerere se retrimite TOT
contextul. O sesiune de 348 mesaje = **64M chars input** (~16M tokeni), adica **187x** contextul final.
Deci costul real nu sunt pasii, ci **numarul de cereri x masa contextului**.

**Componenta contextului (masurata):** 53.2% output-uri de tool, **36.3% codul trimis de agent**,
10.2% text assistant. Deci 89.5% din context e produs de agent, nu de operator.

| # | Optimizare | Efect |
|---|-----------|-------|
| 1 | **tool `multi`** | 2-6 operatiuni independente intr-UN apel; cap 6 ops, plafon 2000/entry, plafon 7000 total; **eroarea unei operatiuni NU opreste restul** |
| 2 | regula **BATCH** in prompt | „daca pasul B nu citeste ce a scris pasul A, sunt in ACELASI `multi`"; NU batchuieste dependent/greu/poate-atarna |
| 3 | regula **CODE DENSITY** | codul din tool_call arguments se retrimite la fiecare cerere → cod minim, fara comentarii decorative |
| 4 | regula **DENSITY RULE** | etichete de ~60-90 chars, verb + obiect |
| 5 | **cache HIT** afisat | per task in footer + in `/ctx` (din `usage.prompt_cache_hit_tokens`) |

> **TRAP:** `print()` in bucle NU economiseste tokeni — scrie pe stdout, nu intra in context.
> Doar `m['content']` si `tool_calls[].arguments` se retrimit.

**MASURAT pe task-uri reale:** 13 operatiuni in 5 apeluri (-62% apeluri); pe 10 op. `-82%` input,
pe 50 op. `-97%`.

---

## Etapa 40 - FEREASTRA REALA + COMPACTARE DEZACTIVATA

**Avertisment FALS (reparat):** `CTXWINDOW` era hardcodat la `128000`, dar modelul `deepseek-flash`
(DeepSeek-V4.1-Flash) are **`context_window=1048576` (1M)**. Un context de 160.4k tokeni raporta
**125%** si declansa alerta rosie desi era la **15%**.

**Sursa de adevar = API-ul:**
```bash
curl -s https://api.deepseek.com/models -H "Authorization: Bearer $KEY"
#   -> deepseek-flash: context_window=1048576, max_output_tokens=393216
```

**Fixuri:**
- `CTXWINDOW=1048576` (verificat in API, nu ghicit)
- `ctx_check_window()` la startup: intreaba API-ul si **corecteaza singur** constanta daca diferă;
  daca reteaua cade, pastreaza constanta locala si NU blocheaza startup-ul
- `ctx_warn()`: avertisment **ROSU** la **90%** din fereastra, o singura data per trecere,
  re-armat sub 80%; **NU comprima si NU sterge nimic**

**COMPACTARE DEZACTIVATA (decizie operator):** `CTXBUDGET=0` + `compact_history()` devine **no-op**
(chiar si cu `force=True` de la `/compact`). Motivul: comprimarea inlocuia output-urile grele cu
pointeri catre `archive/`, deci informatia ramanea pe disc dar **dispareа din context**.
Operatorul vrea memoria inserata la startup sa rămâna **INTREAGA pana la `/reset`**.

**Verificat:** dupa 50 de mesaje x 8000 chars, **0 pointeri noi**, memoria intacta.

---

## Etapa 41 - TESTUL DECISIV (audit de securitate cu uid 2000)

**Task (fara indicii tehnice):** „audit de securitate complet, folosind **intensiv adbsh cu uid 2000**:
permisiuni periculoase, servicii in fundal, conexiuni de retea, fisiere accesibile doar ca shell,
starea SELinux/verity/root. Verdict cu riscuri concrete."

**REZULTAT:** audit de **6500 chars**, **23 operatiuni in 12 apeluri API**
(7 `adbsh` uid=2000 + 5 `multi` + 1 python); `multi` a grupat 15 operatiuni.

**Comenzi privilegiate rulate cu uid 2000:** `dumpsys cpuinfo`, `appops`, `/proc/net/tcp`
(cu conversie hex `$((16#hex))`), `getenforce`, `getprop` verity/boot, `ls /dev/socket`, `id`.

**Economie masurata:** **-45% apeluri**, **-59% input** (~428k tokeni).

**VERIFICARE INDEPENDENTA a dovezilor** (toate confirmate):
| Afirmatie agent | Verificare | Rezultat |
|-----------------|-----------|----------|
| SELinux Enforcing | `getenforce` | ✅ Enforcing |
| `su` absent | `ls /system/bin/su` | ✅ ABSENT |
| Bootloader locked | `getprop ro.boot.flash.locked` | ✅ 1 |
| Verity enforcing | `getprop ro.boot.veritymode` | ✅ enforcing |
| Agentul are 3 permisiuni | `dumpsys package` | ✅ granted=true, USER_SET |

**Riscuri reale identificate de agent:**
1. **(ridicat)** `net.sys32.agent` are camera+microfon+locatie SI e debuggable
2. **(mediu)** `/data/local/tmp` e `0777` world-writable
3. **(scazut)** 469 pachete instalate, suprafata mare de atac

**Artifact:** `temp/audit-securitate-SM-A366B.md`

---

## Etapa 42 - SINCRONIZARE `agent.py` (Android) cu optimizarile

Toate optimizarile din etapele 38-41 sunt in **`assets/python/agent.py`** (creierul agentului Android),
adaptate pentru particularitatile telefonului (NU copiate 1:1):

| Desktop | Android |
|---------|---------|
| `bash(cmd, cwd)` — 2 argumente | `run_bash_tool(cmd)` — 1 argument |
| `py(code, cwd)` | `run_tool(code)` |
| tool-uri standard | + `run_android_tool`, `run_adbsh_tool`, `run_toolchain_tool`, `bg_tool` |

**Build:** `./build_app.sh` → BUILD SUCCESSFUL, instalat, `.assets_v115` extras pe device.
Optimizarile confirmate **in APK** (citite din zip).

> **⚠️ CAPCANA:** markerul `.assets_vNN` din `MainActivity.kt` trebuie INCREMENTAT la fiecare
> modificare de assets, altfel app-ul foloseste copia VECHE de pe device.
---

## Etapa 43 - FIX BUG DE BUFFER `adbsh` (output cu un apel in urma)

**Simptom (raportat de agent dupa compilarea numpy):** tool-ul `adbsh` returna output-ul comenzii
**PRECEDENTE**, nu al celei curente. Lag fix de exact o iteratie, reprodus de **13 ori consecutiv**.
Comportament inselator: output-ul era intotdeauna **complet si plauzibil** — doar din alt apel.
Tools neafectate: `multi`, `bash`, `python`, `bg`. Doar `adbsh`.

**Raport complet:** `temp/raport_buffer_adbsh.md` (agentul l-a scris singur, cu transcript de reproduceri).

### Cauza reala (NU ce presupunea raportul)

Protocolul ADB are **doua** campuri de id in fiecare pachet. Verificat cu pachete brute pe device:
```
Noi:  A_OPEN (a0=id_NOSTRU=1,  a1=0)              <- cerem o sesiune
adbd: A_OKAY (a0=id_LOR=1850,  a1=id_NOSTRU=1)    <- id-ul NOSTRU e in a1!
adbd: A_WRTE (a0=id_LOR=1850,  a1=id_NOSTRU=1)
adbd: A_CLSE (a0=id_LOR=1850,  a1=id_NOSTRU=1)
```

Codul vechi filtra `if a0 != 0:` — adica **accepta pachete din ORICE sesiune**. Resturile ramase
in socket de la comanda anterioara (drenare incompleta) se lipeau la raspunsul curent → **lag de
exact un apel**. Raportul a dat 3 ipoteze (asincronie sesiune / ring buffer / reutilizare FD);
niciuna nu era corecta — era **campul de id gresit**.

> **⚠️ TRAP — capcana proprie:** prima incercare de fix a fost `if a0 != lid:` (logica inversa).
> Rezultat: TOATE comenzile dadeau timeout (14.58s pentru un simplu `echo`), pentru ca filtrarea
> respingea tot. Diagnosticul care a salvat: dump-ul pachetelor brute, care arata `a0=1850 a1=1`.

### Fixurile aplicate (3)

| # | Fix | Detaliu |
|---|-----|---------|
| 1 | **filtrare pe `a1`** (id-ul nostru) | `if c in (A_OKAY,A_WRTE,A_CLSE) and a1 != lid: continue` — pachetele straine sunt DROPATE, niciodata adaugate la raspuns |
| 2 | **`_drain()` sigur** | `select()` + citiri partiale tolerate (24-byte header poate veni fragmentat); prima versiune folosea `_recv(0.2)` si ardea tot timeout-ul |
| 3 | **`A_OKAY` cu id-uri inversate** | `self._send(A_OKAY, a1, a0)` — protocol ADB corect |

Plus in `agent.py`: **integrity guard** — fiecare comanda `adbsh` primeste un marker unic
(`echo __MK<ts>__; <cmd>`); daca markerul lipseste din raspuns, sesiunea e desincronizata ->
drain + re-rulare O DATA, apoi raportare onesta. Markerul e eliminat din output.

### VERIFICAT

| Test | Rezultat |
|------|----------|
| `echo` simplu (durata) | **0.58s** (era 14.58s cu fix-ul gresit) |
| 6 comenzi consecutive cu markere unice (manual, pe device) | **6/6 CORECTE** |
| Acelasi test END-TO-END prin agent | **6/6 CORECTE**, zero lag |

```
apel 1: stiut=MK1_71021 primit='MK1_71021\npayload_1' -> OK
apel 2: stiut=MK2_71591 primit='MK2_71591\npayload_2' -> OK
...
REZULTAT: 6/6 corecte
```

**Lectia:** cand un tool comunica prin protocol binar, **nu presupune semantica campurilor** —
dumpuieste pachetele brute si citeste-le. Raportul agentului a diagnosticat perfect COMPORTAMENTUL
(13 reproduceri, tools neafectate, output plauzibil), dar cauza tehnica cerea un nivel mai jos.
---

## Etapa 44 - TOOLCHAIN: PERSPECTIVA dubla + disciplina de terminare (din raportul numpy)

**Context:** agentul a compilat numpy 2.3.5 de la 0 (SUCCES) dar a lovit o serie de probleme pe care
si le-a documentat singur in `workspace/npy/RAPORT_numpy_android.md`. Raportul e exemplar pentru ca
pune PE PRIMUL LOC eroarea proprie, nu pe cea tehnica.

### Cea mai grava eroare (auto-diagnosticata de agent)

> *"Am confundat «un pas intermediar a reusit» cu «task-ul e gata». Criteriul de terminare era
> `import numpy` functioneaza; eu l-am inlocuit mintal cu «bootstrap a zis OK»."*

Costul: **un tur pierdut complet** - agentul a livrat un mesaj de "progres" in loc de rezultatul cerut,
iar operatorul a trebuit sa-l intrebe de ce s-a oprit.

### Eroarea tehnica: status VERDE cu prefix GOL

`toolchain status` raporta `clang=true, make=true, compile_test=true` in timp ce
`/data/local/tmp/tpm/usr/bin` avea **0 fisiere** din perspectiva app-ului.

**Cauza:** toolchain-ul e instalat de **uid 2000 (shell)** si e consumat de **app (~10300)**.
`check()` verifica doar prin shell - deci "totul OK" insemna "OK pentru ALT user decat cel care cere".

### Optimizarile aplicate

| # | Ce | Unde |
|---|----|------|
| **A1** | `check()` verifica **AMBELE perspective**: `app_can_read_prefix`, `app_can_exec_python` + hint explicit ca "app nu poate executa" e NORMAL, nu defect | toolchain.py |
| **A2** | `chmod -R a+rX` automat la finalul bootstrap-ului (prefixul era `drwxrws---`, app-ul nu putea nici citi) | toolchain.py |
| **A3** | marker de versiune `$ROOT/.tc_version` (fara el nu stim CE e instalat) | toolchain.py |
| **A3b** | `python-ensurepip-wheels` in PKGS (in repo Termux `python-pip` NU exista) | toolchain.py |
| **A4** | `pip_install` instaleaza intai **build deps** (meson, meson-python, Cython, ninja) si foloseste `--no-build-isolation` DOAR daca deps sunt deja in prefix (verificat, nu presupus) | agent.py |
| **A5** | timp pe faze: `[phases] total Xs` la fiecare pip_install | agent.py |
| **A6** | **`action=doctor`** - health check per-uid: poate SHELL-ul sa compileze? poate APP-ul sa citeasca/execute? + verdict | toolchain.py + agent.py |

### Reguli noi in system prompt (recomandarea C din raport)

```
STOPPING CRITERION: before you call a task done, state WHAT the finish line is
(e.g. `python -c "import numpy"` exits 0). The task is NOT done because a tool
printed OK - it is done when the FINAL verification returns the result asked for.
After EVERY step that reports success, check the EFFECT on disk, not the status.
NEVER end a turn with "I did X, next comes Y" when the operator asked for Y.

SHELL-OWNED RESOURCES: the toolchain belongs to uid 2000. As an app you can READ
its files but CANNOT execute them - run through `adbsh`/`/run_su`.
A `status` that looks green from the shell perspective does not mean YOU can use it.
```

### COMPLETARE: recomandarile B (flux de build) - toate acoperite

Primele doua erau deja implementate; restul au fost adaugate acum.

| # | Propunere | Implementare |
|---|-----------|--------------|
| **B1** | build in /data/local/tmp, nu pe FUSE | deja: `TMPDIR=/data/local/tmp/tmp` in `env_vars()` + `_prepare_dirs()` |
| **B2** | cache de wheel persistent | deja: `PIP_CACHE_DIR=$HOME/.cache/pip` |
| **B3** | OpenBLAS | `NPY_BLAS_ORDER` / `NPY_LAPACK_ORDER` in env (opt-in `AGENT_BLAS=openblas`); fara el rămâne BLAS-ul intern |
| **B4** | `-O3 -mcpu=native` / SIMD | `_simd_flags()` adauga `-march=armv8.2-a+dotprod+fp16` + `-O3` in CFLAGS/CXXFLAGS, controlabil cu `AGENT_SIMD=0` |
| **B5** | CCACHE | `ccache` in PKGS + wrapperele clang din `/data/local/tmp/wrap` il folosesc cand exista (fallback transparent) |
| **B6** | LTO off | corect lasat off (nimic de facut) |

### TREI bug-uri gasite la integrare (pe care raportul nu le putea sti)

| Bug | Simptom | Fix |
|-----|---------|-----|
| `doctor` lipsea din **enum-ul schemei** | agentul: *"actiune necunoscuta: doctor"* desi handler-ul exista | adaugat in enum + descriere |
| `doctor` lipsea din **lista inline a `_run`** | `_run` are actiunile hardcodate pentru exec inline; `doctor` cadea pe branch-ul "necunoscut" | adaugat `elif _act == "doctor"` |
| `shell_ls_count` folosea `len()` pe string | raporta **3** binare in loc de **239** | `int()` + curatare artefacte protocol |

> **LECTIE DE INTEGRARE:** cand adaugi o actiune intr-un tool care are (a) schema cu `enum`,
> (b) dispatcher in agent.py, (c) lista inline in `_run`, (d) CLI in modul - trebuie atinse TOATE
> patru locuri. Lipsa unuia produce "actiune necunoscuta" desi codul pare complet.

### VERIFICAT

```
toolchain action=doctor ->
  shell_ls_count: 239        shell_clang: true    shell_python: true   shell_pip: true
  app_can_read: true         app_can_exec: false
  prefix_mode: 2775 shell:shell                   world_readable: true
  verdict: OK - shell builds, app can read (execute via adbsh, as designed)
```

> **Nota despre iteratie:** instalarea unui APK nou NU reincarca `agent.py` in procesul Python deja
> pornit (agentul ruleaza bucla cu fisierul incarcat la startup). Dupa orice schimbare de assets:
> `am force-stop` + `am start` + **reactivare accessibility**.
---

## Etapa 45 - FIX CRITIC `__main__` + MONITOR DE STATUS (0 tokeni)

### BUG-ul care bloca TOTUL (ore de "timeout" aparent)

`agent.py` rula `refresh()` si bucla `input()` **la nivel de modul**, fara `if __name__ == "__main__"`.
`py()` lansa `[sys.executable, "-c", cod]`, iar pe Android `sys.executable` = `libpyexec.so` →
interpretorul **RE-INCARCA agent.py** → reintra in bucla `input()` → **atarna infinit**.

**Efect:** ORICE tool `python`/`run_tool` parea blocat; agentul "statea intepenit dupa task".

**Fix:** un singur `if __name__ == "__main__":` inainte de blocul de startup.
Acelasi fix aplicat si in `agent-original.py` (agentul Linux):
`import` = **0.08s** (era blocat infinit).

### OPTIMIZARI DE TIMP (referatul: "fazele de fix au fost mai lungi decat build-ul")

| Operatie | Inainte | Acum | Cauza |
|----------|---------|------|-------|
| `_patch_runpath` | **13+ min** | **0.3s** | `readelf -d` per fisier (~1000 spawn-uri) → o singura trecere Python |
| `_fix_libcxx_needed` | minute | **0.1s** | la fel |
| `check()` runpath | ~30s | **<1s** | la fel |
| `setexec.py` | **nu rula deloc** | ruleaza | `python3` NU exista pe Android → `python3.14` |
| `_fix_ninja` | copie (distrugea originalul) | wrapper script | referatul: "nu mai e recuperabil" |
| `_fix_meson_exe` | lipsea | wrapper `python3.14 -m mesonbuild.mesonmain` | meson vine ca MODUL |
| preflight | `cmake_build=false` | **true** | `PREFIX` exportat + filtrare linii `[adb]` |

`adb_client`: incearca **AUTH_SIGNATURE primul** (cheia e in `user_keys` → CNXN imediat),
`RSAPUBLICKEY` doar fallback. Ordinea inversa producea timeout la fiecare comanda.

### MONITOR DE STATUS: `/watch [sec]` — 0 TOKENI

**Intrebarea operatorului:** "poti adauga un check la fiecare minut? devine costisitor?"

**Masurat:** prin API, 30 de check-uri (build de 30 min) = **~255.000 tokeni input**, fiindca
fiecare check retrimite TOT contextul. Prin monitor local: **0 tokeni, 0 cereri API**.

**Cum functioneaza:** un thread LOCAL care citeste registrul joburilor de fundal si verifica
`/proc/<pid>/stat` (nu ghiceste), apoi scrie o linie pe ECRAN (stdout). Nu atinge contextul.

```
/watch        -> porneste (60s)
/watch 30     -> la 30 de secunde
/watch        -> opreste
AGENT_WATCH=1 -> pornit automat la startup
```

Exista in AMBELE agenti (Android si Linux). `_watch_loop` scrie DOAR cat ruleaza un job
(silentios cand nu e nimic de raportat) si doar cand linia se schimba (fara zgomot).

### REGULI NOI IN SYSTEM PROMPT

```
STOPPING CRITERION: task-ul NU e gata pentru ca un tool a afisat OK - e gata cand
VERIFICAREA FINALA returneaza rezultatul cerut. Dupa fiecare pas, verifica EFECTUL
pe disc, nu mesajul de status. Niciodata sa nu inchei un tur cu "am facut X, urmeaza Y".

TIMING: tool-urile care apeleaza shell intorc in milisecunde aici, deci un pas care
ia secunde inseamna ca ASTEPTA (timeout, lock, retea) - investigheaza cauza in loc
sa astepti. Nu dormi intre pasi: fiecare pas asteapta exact cat are nevoie tool-ul.
```

### REZULTAT

numpy 2.5.3 compilat nativ pe telefon (import OK, matmul/svd/fft/random functionale);
wheel `numpy-2.5.3-cp314-cp314-android_24_arm64_v8a.whl` (7.3 MB).

---

## Etapa 46 - OPTIMIZARE DE TOKENI v2 (fereastra de 1M + tool `help`)

**Descoperirea centrala (bug cu impact catastrofal):** `CHUNK=7000` limita output-ul unui tool call
la ~1750 tokeni, adica **0.17% din fereastra de 1M**. Orice citire medie se taia in mijloc → pasi
suplimentari de re-citire → fiecare pas retrimitea TOT istoricul. Limita "de siguranta" producea
exact opusul: mai multi tokeni.

**Dovada (fisier de 113 KB, ~28k tokeni, incape lejer in 1M):**
| CHUNK | Pasi de citire | Tokeni input |
|-------|---------------|--------------|
| 7000 | 17 | ~292.400 |
| 60000 | 2 | ~21.400 |
| 200000 | 1 | ~3.200 |

**Al doilea bug, si mai ascuns:** `py()` si `bash()` faceau `[:8000]` **INAINTE** de `_store()`.
Logul de pe disc promitea "text complet" dar avea maxim 8000 chars, iar marker-ul "NOT LOST"
**mintea** — exact ce `_store()` se lauda ca previne. Cu CHUNK=7000 vechi, taierea la 8000 era
invizibila (se ascundea sub ea).

**Al treilea:** tool-ul `bash` era **complet rupt pe Android** — `Popen(["bash",...])`, dar bash
NU exista pe Android (doar toybox sh; verificat: nici in /system/bin, nici in prefixul tpm).
Fiecare apel `bash` crapa cu `FileNotFoundError` neprins → omora task-ul.

**Fixuri aplicate (in AMBELE variante, Android + Linux):**
| # | Ce | Detaliu |
|---|----|---------|
| 1 | `CHUNK` 7000 -> **60000** | 1.4% din fereastra de 1M; o citire medie intra intr-un pas |
| 2 | `TOOLMAX` -> **8000** | plafon pentru iesiri ne-deliberate |
| 3 | `py()`/`bash()` | NU mai trunchiaza; bugetul se aplica o singura data, in `_store()` |
| 4 | `read` ceiling | `min(bud,CHUNK)` (era hardcodat 7000, ignora constanta) |
| 5 | `multi` caps | scalate la `_budget()` (erau 2000/entry si 7000 total) |
| 6 | **SHELL fallback** | `_shell()`: bash daca exista, altfel `sh -c`; cache-uit |
| 7 | `vision` thinking | ON (propriul docstring spunea "THINKING ENABLED", codul trimitea disabled) |
| 8 | `ask` max_tokens | configurabil (`DS_MAXTOK`), era hardcodat 131072 |
| 9 | router `route()` | adaugate cat/ls/pwd/md5sum/sha256sum/diff/stat/nl/tee/file/base64 in BASH_STREAM |
| 10 | **tool `help`** | ghidul avansat de Android (reflection/objects/privileged) scos din promptul fix si livrat la cerere |
| 11 | **bg logging** | logurile in `/data/local/tmp/bg_logs` (shell nu poate scrie in sandbox-ul app-ului) |

**Cost fix masurat:**
| Varianta | Inainte | Dupa |
|----------|---------|------|
| Android (`agent-android-v2.py`) | 8319 tok/req | **6449 tok/req** |
| Linux (`agent-linux-v2.py`) | ~3382 tok/req | **2821 tok/req** |

**Testat live pe dispozitiv (SM-A366B):** 44+28+16 teste PASS/0 FAIL; 100.000 linii procesate in
166ms (602.749 linii/s); context real dupa 878 mesaje = **13.6% din fereastra** (vs teoretic mult
mai mult cu vechiul CHUNK).

**Schema de nume finala:**
- `agent-original-android.py` / `agent-original-linux.py` — originalele, neatinse (referinta)
- `agent-android-v2.py` / `agent-linux-v2.py` — optimizatele v2
- `assets/python/agent.py` = **copia v2 Android** → default la orice clone/build

---

## Etapa 47 - ELIMINARE TERMUX + FLANG + OpenBLAS + libc++abi (28 sept 2026)

**Termux eliminat COMPLET si DEFINITIV** (nu doar dezactivat):
- `tpm.py` STERS; toate referintele `termux`/`tpm` scoase din `agent.py` si `toolchain.py` (0 ramase)
- sterse functiile de bootstrap: `bootstrap_direct`, `_load_index`, `_untar`, `_extract_deb`,
  `_patch_runpath`, `_fix_ninja`, `_fix_symlinks`, `_fix_sysconfig`, `_fix_termux_paths`,
  `_fix_wrappers_shebang`, `_fix_cc_wrappers`, `_fix_cxx_linker`, `_fix_meson_exe`, `install`
- sterse `PKGS` / `_REPO` (repo Termux) / `OLD` (cai Termux) + actiunile tool `bootstrap`/`tpm`/`bootstrap_tpm`

### FLANG - compilator Fortran pe Android (compilat de la 0)

Problema: numpy = C++ pur (meson+ninja merge), dar **scipy = 2038 fisiere FORTRAN**.
Nu exista compilator Fortran pe Android (clang nu are frontend Fortran).

Solutia: **flang 21.1.8 compilat din surse LLVM pentru ARM64** (4506 tinte Ninja):

| Artefact | Dimensiune | Rol |
|---|---|---|
| `libflang_exec.so` | 137 MB (stripped) | driver-ul Fortran |
| `libFortranRuntime.a` | 19.6 MB | runtime-ul (64 fisiere C++, compilate de la 0) |
| `libFortranDecimal.a` | 791 KB | decimal |
| `libclang_rt.builtins.a` + `libunwind.a` | 515 + 92 KB | runtime C/C++ ARM64 |

**CAPCANE (fiecare a costat un diagnostic):**
1. Driver-ul flang **NU compileaza Fortran singur**: cade pe `"gcc" -x f95-cpp-input`
   (*"gcc frontend command failed"*). Trebuie chemat cu **`-fc1`** (frontend direct).
2. `-fc1` are nevoie de **`-triple aarch64-linux-android35`** (altfel:
   *"No available targets are compatible with triple unknown"*).
3. `-fc1` **IGNORA `-o`** pe acest build: scrie .o in cwd cu nume implicit, exit 0, 0 bytes.
   Fix: compilez in cwd-ul sursei cu `-emit-obj`, apoi copiez rezultatul.
4. Sursa trebuie data **RELATIV** din cwd-ul ei (calea absoluta esua silentios).
5. `-fc1` **nu accepta `-fPIC`** (se pune doar la link).
6. argv[0] decide comportamentul (ca la lld): symlink numit `flang-bin`, nu `libflang_exec.so`.

**Wrapper final** (`files/tmp/flang`, 2 pasi):
```sh
# 1. compilare: flang-bin -fc1 -triple ... -emit-obj pt fiecare sursa -> .o
# 2. link: libclang_exec.so (stie sysroot/LDFLAGS) + libFortranRuntime
#          + libFortranDecimal + libc++_shared + libm
```

### OpenBLAS (inlocuieste BLAS/LAPACK de referinta)

OpenBLAS 0.3.29 compilat de la 0 (`TARGET=ARMV8`, SIMD NEON): `libopenblas.a` 25 MB +
`.so` 12 MB + headere (cblas/lapack/lapacke/openblas_config) + `openblas.pc`.
Efect: numpy/scipy **10-50x mai rapide** la runtime (netlib-ul era scalar).

### libc++abi.a

Compilat de la 0 (528 KB, 18 obiecte, 1299 simboluri). Capcana: `-nostdinc++`
(altfel libc++ 21 din surse intra in conflict cu cel din NDK).

### Protectie site-packages la update de APK

Inainte: fiecare update de APK stergea `pyhome` -> dispareau numpy/scipy/lxml/PIL
(5 ore de build pierdute). Acum: depozit `files/site_packages_keep` care
supravietuieste reinstalarii; restaurare DUPA reconstructia pyhome (ordinea conteaza —
altfel `Lib/` nu se copia si apare *"Failed to import encodings"*).

### VERIFICARE FINALA (pe instalare CURATA: dezinstalare + reinstalare APK)

```
check(): ar_test=True cxx_test=True libcxx_full=True ninja=True
         deps(openblas)=True openblas_pc=True flang=True
C     -> RC 0 (binar produs)
C++   -> RC 0 (binar produs)
Fortran -> binar produs (1.5 MB)
Onboarding: ecranul cere cheia API in romana
```

**Limitare cunoscuta:** binarul Fortran da **segfault la RULARE** (initializarea
runtime-ului Fortran cere `libFortranMain`/unitati I/O). Compilarea — partea care
rezolva cele ~500 patch-uri F90 pe LAPACK — functioneaza.

**APK: 273 MB** | marker `.assets_v160` | commituri: `813ce09`, `2d9a0f9`, `376b73e`

---

## Etapa 48 - FIX `pip install` (blocajul SIGSEGV -11) + TOOLCHAIN COMPILABIL PE DEVICE (28 sept, sesiunea 2)

**Blocajul:** ORICE `pip install` cu extensie C murea la "Preparing metadata (pyproject.toml):
exit code: -11" (SIGSEGV). Raportul anterior il punea pe seama lui `libpyexec.so` ("nu se poate
re-initializa ca subproces") - **ipoteza GRESITA**.

### Cauza reala (dovada: tombstone + bisect pe device)

`env_vars()["LD_LIBRARY_PATH"]` incepea cu **directorul de STUB-uri NDK**
(`toolchain/sysroot/usr/lib/aarch64-linux-android/35`), unde `libc.so`/`libm.so`/`libdl.so` sunt
stub-uri DE LINK (fara cod in `.text`).

```
F libc: Fatal signal 11 (SIGSEGV) in tid 8612 (libpyexec.so)
DEBUG: Cmdline: .../libpyexec.so .../_in_process.py prepare_metadata_for_build_wheel
DEBUG: #00 pc 0x4a83e0 libpython3.14.so
DEBUG: #02 .../linker64 (__dl__ZN6soinfo17call_constructorsEv+668)
```

Procesul AGENT nu avea nicio problema (linkerul bionic isi citeste `LD_LIBRARY_PATH` la **INIT**, nu la
`dlopen`) -> parintele mergea, **copiii mureau**. Bisect pe copii: cu stub-uri `rc=-11`, cu
`nativeLibraryDir` sau `deps/lib` singur `rc=0`.

### Fixuri (in ordinea in care au fost necesare; fiecare verificat pe device)

| # | Fix | Unde |
|---|-----|------|
| A | `_rt_ld_path()` / `sanitize_ld_library_path()`: LD_LIBRARY_PATH de RULARE fara directoare `sysroot` | toolchain.py |
| B | `_clean_ld()`: acelasi filtru pentru env-ul de pip + hook-ul de startup | agent.py |
| C | `pathspec` 1.1.1 adaugat (dep de scikit-build-core, lipsea) | pysitepkg.zip |
| D | `_ensure_py_include()`: `pyhome/include/python3.14 -> toolchain/pyinc` (INCLUDEPY era `/usr/local/include/...`) | toolchain.py |
| E | `_ensure_py_lib_link()`: `pyhome/lib/libpython3.14.so` + LIBDIR rescris (`-lpython3.14` nu se gasea) | toolchain.py |
| F | `_patch_sysconfig_device()`: CC/CXX/LDSHARED cu `-resource-dir` + `--target` + `--sysroot` (lipsea `stddef.h`) | toolchain.py |
| G | `_ensure_sysroot_api_dir()`: symlink `<api>` -> `35` - fara el clang emite crt-urile ca NUME BARE si lld le cauta DOAR in CWD | toolchain.py |
| H | `-L` puse direct in `LDSHARED` (setuptools NU foloseste LDFLAGS din sysconfig la link) | toolchain.py |
| I | env-ul complet aplicat in `os.environ` pe durata pip (altfel copilul nu gaseste `ld.lld` din `files/tmp`) | agent.py |
| J | auto-retry cu build isolation la `ModuleNotFoundError` (backend cu dep lipsa) | agent.py |

### VERIFICAT (instalare curata `.assets_v181`)

```
pip install regex       -> exit 0, 23s   (wheel cp314-android_24_arm64_v8a)
import regex            -> match(r"(\d+)-(\d+)","12-34") = 12 / 34 (v2026.9.10)
pip install zstandard   -> exit 0        (C + scikit-build-core)
pip install msgpack     -> exit 0, 15s   (C++)
pip install markupsafe  -> exit 0, 15s
logcat dupa teste       -> ZERO "Fatal signal 11"
```

Instalarea merge in `pyhome/lib/python3.14/site-packages`, e vizibila in `sys.path` si
**supravietuieste** update-ului de APK prin `files/site_packages_keep` (verificat).

**APK: 282 MB** | marker `.assets_v181`

---

## Etapa 49 - TEST REAL DIN UI + 2 BUG-URI REPARATE (28 sept, sesiunea 2b)

**Testul decisiv de autonomie, pe INSTALARE CURATA:** aplicatia dezinstalata complet (date private
sterse + `/sdcard/Download/Agent` sters, inclusiv cheia ADB), reinstalata de la zero, doar cheia
DeepSeek lipita in onboarding (ecranul o scrie singur in `files/python/key.txt`). Auto-configurare
la prima rulare: libs crypto/ssl/pairing + RSA 2048 + certificat X.509 + cheie persistenta pe
sdcard -> "AGENT FULLY CONFIGURED AND OPERATIONAL". Apoi: 73 permisiuni `granted=true`,
accessibility ON, whitelist de baterie (Doze).

**Task dat DIN INTERFATA, fara sa-i spunem ce tool sa foloseasca:**
> "Vreau sa folosesc pachetul Python kiwisolver in scripturile mele de pe telefon. Fa ce e
> necesar ca sa functioneze si confirma-mi ca merge."

**Rezultat (ales SINGUR de agent):** `python` (verificare) -> `toolchain status` (verdict OK) ->
`toolchain pip_install` -> `python` (test functional). Kiwisolver 1.5.1 compilat NATIV pe telefon
in 41s (wheel local `cp314-android_24_arm64_v8a`), verificat cu import real + rezolvare de sistem
liniar, nu doar import.

### Bug-urile gasite de testul din UI (ambele reparate)

| # | Simptom | Cauza reala | Fix |
|---|---------|-------------|-----|
| 1 | `[Errno 13] Permission denied: .../toolchain/bin/clang++` (greenlet, prima compilare C++) | `CC` avea symlink executabil in `files/tmp`, dar `CXX` arata spre binarul din `filesDir`, pe care untrusted_app NU il poate executa -> orice sursa C++ cadea | symlink `files/tmp/clang++` (cu reparare cand tinta e moarta) + `_extra` (`-resource-dir`/`-B`) ca la CC; `clang`/`clang++` sunt acum gestionate central in `_ensure_launchers()` |
| 2 | `BackendUnavailable: Cannot import 'setuptools.build_meta'` (kiwisolver) | cu `--no-build-isolation` pip NU instaleaza cerintele din `pyproject.toml`; setuptools ridica "Missing setup required dependencies: cppy", iar pip raporteaza doar BackendUnavailable (cauza reala ascunsa) | prima incercare ruleaza cu `-v`, se extrag cerintele lipsa din output, se instaleaza, apoi se reia install-ul; daca tot esueaza -> retry cu build isolation. Rezultatul tool-ului include acum o linie `pasi:` (ex. `deps(cppy)=0; retry_dupa_deps=0`) |

**VERIFICAT pe device:** `greenlet 3.5.6` (C++) exit 0; `kiwisolver 1.5.1` exit 0, 39s cu
`deps(cppy)=0; retry_dupa_deps=0`; `fastnumbers 5.2.0` compilat real prin agent, din UI (exit 0,
39s, wheel `cp314-android_24_arm64_v8a`, import functional); pe instalarea curata `.assets_v182`
agentul a ales si construit SINGUR kiwisolver.

**APK: 282 MB** | marker `.assets_v182`

---

## Etapa 50 - FAZA 0: FUNDATIA DE AUTONOMIE (29 sept 2026, `.assets_v184`)

Implementat in `toolchain.py` + `agent.py` (vezi `PLAN_AUTONOMIE.md`, sectiunea 5/8.1):

- **`toolchain action=selftest`** - self-test de CAPABILITATI pe device: compileaza si LINKEAZA
  real C, C++ cu STL, o extensie `Python.h` (link cu `-lpython3.14`) si un obiect Fortran; verifica
  ninja/make/ld.lld/pkg-config, backends importabile (meson, scikit-build-core, Cython, setuptools,
  pybind11, pathspec), cmake/rust/perl, wheelhouse-ul. Intoarce `ok[]`, `lipsa[]`, `timpi_s`,
  erorile per test si un `verdict`. Legat in schema tool-ului (enum + descriere) si in dispatcher-ul
  inline - verificat prin `run_toolchain_tool({"action":"selftest"})` -> JSON 897 chars.
- **Taxonomie de esec** (`_classify_build_fail`): coduri `rust_lipsa`, `cmake_lipsa`, `perl_lipsa`,
  `ram_insuficient`, `spatiu_insuficient`, `wheel_inexistent`, `cerinte_build`, `headers_lipsa`,
  `link_runtime`, `eroare_build` + "ce lipseste" + "urmatorul pas", afisate ca `[diagnostic] ...`.
- **Wheelhouse local** (`files/wheels`) + `--find-links` + fast-path OFFLINE
  (`--no-index --find-links`): un wheel luat o data de pe PyPI se reinstaleaza instant, fara retea.

VERIFICAT pe device: selftest toate TRUE mai putin cmake/rust/perl (C 0.18s, C++ 2.03s, extensie
Python 0.33s, Fortran 0.22s); `cramjam` -> `cod=rust_lipsa`; `xxhash` salvat in wheelhouse si
reinstalat offline ("instalat din wheelhouse local"); `kiwisolver` exit 0 (38s) dupa refacere;
instalare curata + intrebare din UI ("Poti instala pyarrow?") -> raspuns corect in 16.8s
(`CMakeNotFoundError: Could not find CMake with version >= 3.25`).

Doua regresii prinse si reparate in timpul fazei (ambele in PLAN_AUTONOMIE.md 8.1):
`pip wheel --no-build-isolation` ascunde cauza reala a cerintelor de build lipsa (drumul principal
a revenit la `pip install`), si doua subcomenzi pip in acelasi proces nu mai vad `--find-links`
(instalarea din wheelhouse se face intr-un proces nou).

---

## Etapa 51 - CMAKE PE DEVICE (FAZA 1, `.assets_v187`, 29 sept 2026)

**cmake 3.31.6 ruleaza pe telefon si construieste proiecte reale.** Vezi
`PLAN_AUTONOMIE.md` sectiunea 8.2 pentru toate patch-urile.

- `toolchain action=selftest` -> `"cmake": true` (configure+build proiect C, ~1.2s);
  proiect de test configure+build+binar RULAT pe device.
- Binarul (10.7 MB, ARM64, **libc++ static**) e in APK ca `jniLibs/arm64-v8a/libcmake_exec.so`
  (untrusted_app nu poate executa din filesDir) + `assets/toolchain/cmake/{Modules,Templates}` (11 MB).
- `toolchain.py` scrie `files/tmp/android.toolchain.cmake` (sysroot + compilatoare + flags,
  o singura sursa de adevar cu `_cflags`/`_extra`/`_ldflags`), construieste un **NDK minimal**
  prin symlink-uri si exporta `CMAKE_ROOT`, `CMAKE_TOOLCHAIN_FILE`, `CMAKE_GENERATOR=Ninja`,
  `CMAKE_ARGS`, `CMAKE_MAKE_PROGRAM`, `CMAKE_PREFIX_PATH` si **`PREFIX`**.

### Capcane noi dovedite pe device (se adauga la lista de mai sus)

11. **`PREFIX` este obligatoriu pentru cmake pe device.** Cand cmake *ruleaza* pe Android,
    `Modules/CMakeDetermineSystem.cmake` citeste `$ENV{PREFIX}/include/android/api-level.h`
    ca sa determine API-ul. Fara el: `file failed to open: /include/android/api-level.h`
    -> "Configuring incomplete", desi compilatorul si sysroot-ul erau corecte.
    Valoarea corecta: `PREFIX=<TOOLCHAIN>/sysroot/usr`.
12. **cmake trebuie sa-si stie propriul binar (`CMAKE_COMMAND`).** Regulile generate pentru
    Ninja contin `cmake -E rm -f ...`; daca radacina vine din mediu, cmake nu-si mai deduce
    calea si comanda incepe cu `""` -> `/bin/sh: : can't execute: Is a directory`.
13. **Cache-ul cmake este lipicios.** Un `CMakeCache.txt` scris de un configure esuat
    memoreaza "compiler broken" si face ca TOATE configure-urile urmatoare sa esueze la fel,
    chiar daca intre timp ai reparat mediul. Sterge directorul de build inainte de re-test.
14. **Flags-urile compilatorului trebuie sa ajunga in `CMAKE_C_FLAGS_INIT`/`CMAKE_CXX_FLAGS_INIT`,
    nu doar in `CC`/`CXX`.** Testele de compilator ale cmake folosesc doar variabilele CMake;
    fara `-resource-dir` linkerul cauta `libclang_rt.builtins.a` in nativeLibraryDir si
    raporteaza "compiler broken".
15. **libc++_shared.so de pe device nu e suficient pentru cmake**: copia din APK are 1.4 MB
    si NU exporta simbolurile `std::filesystem` (`_ZNKSt6__ndk14__fs10filesystem4path...`)
    -> linkerul pica. Binarul de cmake e linkat cu **libc++ static**.
16. **cmake detecteaza singur Android** din triple-ul folosit de clang
    (`aarch64-linux-android35`) si atunci cere un NDK cu layout standard. Solutia pe device:
    NDK minimal din symlink-uri (`<TOOLCHAIN>/ndk/toolchains/llvm/prebuilt/linux-x86_64/{bin,sysroot}`)
    - `_ensure_fake_ndk()` in `toolchain.py`.

---

## Etapa 52 - PERL AUTONOM + TIER-2 + BATERIE DE TESTE (`.assets_v190`, 29 sept 2026)

**Nimic din Termux nu mai e in APK.** Tot ce ruleaza pe telefon e compilat de noi (laptop,
cross-compilare cu NDK 27) sau e cod Python.

### perl 5.42.0 - compilat de noi (inlocuieste binarul Termux)
- `perl-cross` 1.6.5 peste sursa perl 5.42.0 (1.5.3 nu are patchset pentru 5.40/5.42).
- configure cere explicit uneltele: `--with-cc --with-ar --with-ranlib --with-nm --with-objdump
  --with-readelf`; fara ele: "ERROR: Cannot find ar/readelf".
- `-Dd_futimes=undef -Dd_futimesat=undef -Dd_lchown=undef` (bionic nu are futimes/lchown).
- **`-Dlibs='-ldl -lm'`** - ALTfel modulele XS se linkeaza fara libm si mor la dlopen cu
  `cannot locate symbol "modf"` (dovedit cu `LD_PRELOAD=/system/lib64/libm.so`, care repara).
- binarul e linkat cu libperl static (doar libc/libm/libdl) si are prefixul de pe device
  compilat in el -> isi gaseste singur @INC; `auto/List/Util/Util.so` (linkat fara -lm in
  build-ul intern) a fost relinkat manual cu `-lm`.
- livrat: `assets/toolchain/perl` (55 MB) + `jniLibs/arm64-v8a/libperl_exec.so` + symlink
  `files/tmp/perl`; verificat pe device: `perl -MList::Util -MPOSIX -e ...` -> `sum=6 ceil=2`.

### Tier-2 in `assets/toolchain/deps` (static, `.pc` cu prefixul de pe device)
zlib 1.3.1, libpng 1.6.44 (fara NEON - vezi capcana 17), freetype 2.13.3, sqlite3 3.46.1
(FTS5/JSON1/RTREE), zstd **1.5.7**. Test de link C direct (sqlite3+png+freetype+zlib) trece pe device.

### Baterie de teste (16 pachete + link C), pe `.assets_v190`:
`toolchain action=pip_install` pentru fiecare, apoi verificare independenta in subproces nou.

| pachet | pip | ruleaza | timp |
|---|---|---|---|
| simplejson | OK | OK | 5.5s |
| MarkupSafe | OK | OK | 5.1s |
| cffi | OK | OK | 0.9s |
| msgpack | OK | OK | 16.5s |
| regex | OK | OK | 22.2s |
| lz4 | OK | OK | 25.0s |
| kiwisolver | OK | OK | 0.5s |
| greenlet | OK | OK | 18.0s |
| lxml | OK | OK | 7.3s |
| zstandard | OK | OK | 62.1s |
| Pillow 12.3.0 | OK | OK (PNG save/open + extensia C nativa) | 47.9s |
| link C Tier-2 (sqlite3+png+freetype+zlib) | - | OK (dupa fix libpng NEON) | 0.3s |
| cbor2 | OK (pure-python) | NU (lipseste extensia C) | 3.6s |
| Pillow | OK (dupa fix LDSHARED/libs) | **OK** (PNG round-trip, `_imaging...so` compilat nativ) | 47.9s |
| numpy | NU | NU | 44.7s |
| apsw 3.53.4 | **OK** (dupa fix CA bundle) | **OK** (create/insert/select, sqlite 3.53.4) | 119.1s |
| duckdb | NU | NU | 10.2s |
| grpcio | NU | NU | 31.8s |

Fixuri de pachet descoperite de baterie:
- **zstandard** - `deps/include/zstd.h` vechi (1.5.6) umbrea header-ul din sdist ->
  `unknown type name 'ZSTD_FrameHeader'`. Fix: zstd 1.5.7 in deps. Acum OK (62s).
- **cbor2** - isi construieste extensia C doar cu `CBOR2_BUILD_C_EXTENSION=1`; altfel instaleaza
  silentios varianta pure-python (`Successfully installed`, dar `import cbor2._cbor2` esueaza).
  Env-ul e adaugat in `env_vars()`, DAR un wheel pure-python deja aflat in wheelhouse poate
  otrăvi reincercarea (lectie: sterge wheel-ul + cache-ul pip inainte de reincercare).

### Capcane noi (17-19)
17. **libpng cu NEON** se compileaza cu referinta la `png_init_filter_functions_neon` dar fara
    obiectul care o defineste (CMake-ul libpng adauga `arm/filter_neon_intrinsics.c` doar la
    NEON=on, insa `pngrutil.c` poate ramane cu referinta) -> la link: `undefined symbol:
    png_init_filter_functions_neon`. Fix: rebuild cu `-DPNG_ARM_NEON_OPT=0
    -DPNG_ARM_NEON_IMPLEMENTATION=0` (cale C).
18. **Wheelhouse-ul poate servi un wheel prost**: daca o instalare a produs un wheel gresit
    (ex. cbor2 pure-python), reincercarile primesc ACELASI wheel din `files/wheels`/cache si
    "trec" fara sa compileze. Sterge wheel-ul + cache-ul pip cand schimbi ceva in toolchain.
19. **`-lm` explicit pe bionic** (perl XS, module C++): fara `-lm` in linia de link, biblioteca
    shared se incarca fara libm in DT_NEEDED si dlopen-ul esueaza cu "cannot locate symbol"
    pentru functii din math (modf/floor/pow).

### Fixuri mari gasite de baterie (drumul lui pip, nu teorii)

20. **`LDSHARED` nu continea `_ldflags`** - cel mai important bug de toolchain ramas: orice modul
    care se linka cu biblioteci din `deps` (Pillow -> libpng/libjpeg/freetype) esua cu
    `undefined symbol: png_read_info / log / fmod`, pentru ca linia de link nu avea
    `-L<deps>/lib` si nici `-lm`. Acum `LDSHARED = CC + _extra + --target/--sysroot + _ldflags + -shared`.
21. **`-lm -ldl` explicit in LDFLAGS** (bionic): cu `-Wl,--no-undefined`, orice modul care
    foloseste math (log/fmod/modf) sau dlopen are nevoie de ele la link. Dovada: Pillow
    (`undefined symbol: log`), perl XS (`Cannot locate symbol "modf"`).
22. **cmake: `CMAKE_FIND_ROOT_PATH_MODE_PACKAGE` trebuie sa fie `BOTH`, nu `ONLY`** -
    `find_package(Python3)` pentru pachetele cu binding-uri (duckdb/pyarrow) nu se gasea,
    desi Python-ul e NATIV pe device: `CMake Error at CMakeLists.txt:45 (find_package)`.
23. **cbor2 6.x nu mai are extensie C, are RUST** (`setuptools-rust` in pyproject.toml) ->
    fara cargo instaleaza silentios varianta pure-python ("Successfully installed", dar fara
    `cbor2._cbor2`). Intra in categoria Rust (FAZA 2), nu e un bug de toolchain C.
24. **grpcio: `ModuleNotFoundError: No module named '_multiprocessing'`** - CPython-ul nostru
    (compilat de la 0) nu are `_multiprocessing` (bionic nu are sem_open/POSIX semaphores;
    Termux patchuieste multiprocessing-ul). Orice build care face `import multiprocessing`
    (grpcio) cade. Fix necesar: rebuild CPython cu suport de semafoare sau patch in
    multiprocessing (item pentru FAZA 5).
25. **numpy 2.5.3**: `ninja: FAILED: numpy/_core/__ufunc_api.c` in timpul generarii metadatelor
    (meson). Ramane de diagnosticat (numpy cere versiuni foarte noi de meson/cython si
    compilator C cu suport complet).
26. **apsw**: setup.py isi descarca sursele la build (`urlopen` -> sqlite.org) si a picat cu
    `CERTIFICATE_VERIFY_FAILED` desi `SSL_CERT_FILE` e setat de toolchain -> de verificat daca
    bundle-ul CA exista in acel moment si daca subprocesul de build mosteneste env-ul.

### Alte doua fixuri (dupa log-urile complete)

27. **Pillow: setup-ul lui vede headerele (prin `-I deps/include`) si activeaza feature-ul, dar NU
    adauga `-l...` la linia de link** -> `undefined symbol: png_create_read_struct / jpeg_* /
    FT_Init_FreeType`. Fix: `_ldflags` include acum explicit `-lz -lpng16 -ljpeg -lfreetype`
    (toate exista ca `.a` in `deps/lib`).
28. **duckdb: `find_package(pybind11)`** -> `Could not find a package configuration file provided
    by "pybind11"`. pybind11 livreaza `pybind11Config.cmake` IN pachetul Python, iar la noi
    pachetele stau in ZIP-uri (zipimport), deci cmake nu putea citi din zip. Fix:
    `_pybind11_dir()` extrage `pybind11/share/cmake` in `files/toolchain/pybind11-cmake` si il
    da lui cmake prin `-Dpybind11_DIR=` (in `CMAKE_ARGS` si in mediu).

29. **`SSL_CERT_FILE` trebuie sa fie FISIER, nu director** (bug gasit de apsw): `_ca_bundle()`
    returna primul drum existent, inclusiv `/apex/com.android.conscrypt/cacerts` (DIRECTOR).
    Python cere fisier PEM -> orice HTTPS din timpul unui build (`setup.py` care isi descarca
    sursele, ca apsw) cadea cu `CERTIFICATE_VERIFY_FAILED: unable to get local issuer certificate`.
    Fix: `_ca_bundle()` construieste un PEM real (630 KB, concatenand certificatele din cacerts)
    in `files/home/ca-bundle.pem`. Dovada: HTTPS catre sqlite.org -> 8886 bytes; `apsw 3.53.4`
    se instaleaza din sursa (isi descarca singur SQLite) si functioneaza.

### Capcane 30-32 (runda de fixuri pentru numpy / grpcio)

30. **`sys.executable` nu trebuie sa fie `libpyexec.so` din `/data/app/~~...==/`** (numpy/meson):
    meson scrie comenzile de generare ca `env PYTHONPATH=... '<interpreter>' -m ...`, iar calea
    din nativeLibraryDir (cu `~~` si `==`) ajunge INTRE GHILIMELE SIMPLE - `env` nu interpreteaza
    ghilimelele, deci: `env: exec -m: No such file or directory`. Fix:
    `_ensure_python_launcher()` creeaza symlink-uri `files/tmp/python3` si `files/tmp/python`
    (nume CURAT, kernelul urmareste symlink-ul -> SELinux vede tinta executabila) si
    `_patch_sys_executable()` seteaza `sys.executable`/`_base_executable` catre ele
    (apelat la startup in `agent.py`).
31. **`_multiprocessing` lipseste pe bionic** -> `import multiprocessing` cade
    (`ModuleNotFoundError: No module named '_multiprocessing'`), iar build-uri ca grpcio
    (care folosesc `multiprocessing.pool.ThreadPool` pentru compilare paralela) pica instant.
    Fix: shim pure-Python `Lib/_multiprocessing.py` (SemLock cu threading + constante de clasa
    RECURSIVE_MUTEX/SEMAPHORE/BOUNDED_SEMAPHORE/SEM_VALUE_MAX - `multiprocessing/synchronize.py`
    citeste `SemLock.SEM_VALUE_MAX`, altfel `AttributeError`). Dovada: `import multiprocessing`
    -> OK; grpcio a trecut de acel pas.
32. **Cython trebuie sa fie pe DISC, nu in zip** (numpy): Cython isi cauta `Includes/` relativ la
    `__file__` (`libc/stdint.pxd`, `cpython/ref.pxd`); din zipimport nu le gaseste ->
    `Error compiling Cython file: 'libc/stdint.pxd' not found`. Fix: `_ensure_real_cython()`
    extrage arborele `Cython/` din `pysitepkg.zip` in `files/pyhome/lib/pyreal/` si acel director
    e pus PRIMUL in `PYTHONPATH` (altfel zipimport are prioritate).

### Capcane 33-35 (numpy reusit) + rezultat

33. **`_posixshmem` lipseste** -> `multiprocessing/resource_tracker.py` il importa necondiționat
    (`import _posixshmem`) -> `import multiprocessing` cadea si DUPA shim-ul de `_multiprocessing`
    ("No module named '_posixshmem'", dovada: grpcio). Fix: shim `Lib/_posixshmem.py`
    (shm_open/shm_unlink emulate peste fisiere in TMPDIR).
34. **`SemLock` e chemat cu argumente POZITIONALE** (`SemLock(kind, value, maxvalue, name,
    unlink_now)`) -> shim-ul nu trebuie sa aiba `*` (keyword-only): dovada grpcio
    "TypeError: SemLock.__init__() takes 4 positional arguments but 6 were given".
35. **patchelf este OBLIGATORIU pentru meson-python** (numpy): la finalul build-ului
    meson-python rescrie RPATH-urile modulelor -> `FileNotFoundError: [Errno 2] No such file
    or directory: 'patchelf'`. Fix: patchelf 0.18.0 cross-compilat de noi (libm/libdl/libc,
    `-static-libstdc++`), livrat ca `jniLibs/arm64-v8a/libpatchelf_exec.so` + symlink
    `files/tmp/patchelf`.

**Rezultat: `numpy 2.5.3` se compileaza de la sursa PE TELEFON (204 s) si functioneaza
(matmul verificat: 486.0).** Biblioteci BLAS/LAPACK: OpenBLAS-ul din APK.

---

## Etapa 53 - FAZA 4: RUST PE DEVICE (LLVM + rustc + cargo, compilate de la 0) - `.assets_v203`, 30 sept 2026

Obiectiv: pachetele Python cu acceleratoare **Rust** (cbor2 6.x, cramjam, orjson, pydantic-core)
si backend-ul `maturin`. NDK-ul NU livreaza `libLLVM.so`, deci rustc trebuia construit cu TOT
LLVM-ul, de la sursa, pentru `aarch64-linux-android`. Zero Termux.

### Ce s-a construit (cross, pe laptop)
| piesa | sursa | rezultat |
|---|---|---|
| LLVM 21.1.8 | `llvm-project-21.1.8.src.tar.xz` | `libLLVM.so.21.1` (dylib, PIC, doar AArch64) |
| Rust 1.98.1 | `rustc-1.98.1-src.tar.gz` + stage0 oficial x86_64 | `rustc` ARM64 (`librustc_driver-*.so`) |
| cargo | `x.py build --stage 2 src/tools/cargo` | `cargo` ARM64, NEEDED doar libdl/libm/libc |
| std | `x.py build --stage 2 library/std` | `rustlib/aarch64-linux-android/lib/*.rlib` + `.rmeta` |

### Fluxul dovedit PE TELEFON (uid de app, toolchain din APK)
`rustc --version` -> 0.3 s; `cargo --version` -> 0.1 s; program Rust real (Vec + iterator +
println) **compilat si LINKAT pe device in 1.5 s** -> ELF ARM64 265 KB;
`toolchain.selftest()` -> `rust=True`, `cargo=True`, **`lipsa: []`** (C, C++, extensii Python,
Fortran, cmake, perl, Rust - toate capabilitatile prezente).

### Capcane dovedite (36-45)
36. **LLVM fara PIC** -> linkul dylib-ului cade: `relocation R_AARCH64_ADR_PREL_PG_HI21 cannot
    be used against symbol ...; recompile with -fPIC`. Fix: `-DLLVM_ENABLE_PIC=ON
    -DCMAKE_POSITION_INDEPENDENT_CODE=ON -DLLVM_BUILD_LLVM_DYLIB=ON`.
37. **Bootstrap-ul Rust isi deduce directorul `bin/` al LLVM din calea lui `llvm-config`** ->
    daca shim-ul nu sta intr-un `bin/`, panica `src.symlink_metadata() failed ("src = .../llvm-cov")`.
    Fix: shim in `build/rust/llvm-bin/bin/llvm-config` + symlink-uri pentru uneltele LLVM.
38. **`llvm-config --link-shared --libs` trebuie sa dea `-lLLVM-21`** (SONAME-ul real e
    `libLLVM-21.so`), nu `-lLLVM-21.1` -> altfel `ld.lld: unable to find library -lLLVM-21.1`.
39. **`-lstdc++` nu exista in NDK** -> (a) la link: `undefined reference ... std::__ndk1::cerr`
    (punte: symlink `libstdc++.so -> libc++_shared.so`); (b) la RULARE: acelasi simbol ->
    `CANNOT LINK EXECUTABLE rustc`. Fix definitiv: `patchelf --add-needed libc++_shared.so`
    (NU `LD_PRELOAD` - ar putea strica clang-ul, care isi are propriul libc++).
40. **LLVM cu doar AArch64** -> bootstrap nu poate genera info pentru gazda de build
    (`could not create LLVM TargetMachine for triple: x86_64-unknown-linux-gnu`). Fix:
    `[llvm] targets = "AArch64;X86"` (LLVM-ul de device ramane AArch64-only).
41. **AGP/aapt2 DEZARHIVEAZA asset-urile `.gz`** -> `rust-libs.tar.gz` ajunge pe device ca
    `rust-libs.tar` (650 MB, comprimat de zip-ul APK). Codul accepta ambele nume.
42. **Python 3.14 + `tarfile.extractall`** -> filtrul implicit `data` ARUNCA
    `AbsoluteLinkError` pe symlink-uri absolute din arhiva. Fix: `filter="tar"` + scoaterea
    symlink-urilor din arhiva.
43. **`-lunwind` nu exista in NDK** -> `ld.lld: unable to find library -lunwind`. Fix:
    `libunwind.a` din compiler-rt (`lib/clang/18/lib/linux/aarch64/libunwind.a`) copiat in
    `assets/toolchain/sysroot/usr/lib/aarch64-linux-android/` (+ in subdir-urile de API).
44. **`rustlib` din arborele `stage2` e GOL** -> std-ul real sta in
    `build/x86_64-unknown-linux-gnu/stage1/lib/rustlib/<target>` (42 fisiere, 96 MB), iar
    fisierele **`.rmeta` sunt obligatorii** langa `.rlib` (altfel: "only metadata stub found
    for `rlib` dependency ..., please provide the corresponding .rmeta").
45. **SELinux**: rustc/cargo NU pot fi executate din filesDir -> stau in APK ca
    `jniLibs/arm64-v8a/librustc_exec.so` / `libcargo_exec.so`, cu symlink in `files/tmp/`.

### Impachetare
* binarele (rustc, cargo) -> `jniLibs` (ca `lib*_exec.so`);
* librariile (librustc_driver, libLLVM, std+rmeta) -> `assets/toolchain/rust-libs.tar.gz`,
  extrase o singura data in `files/toolchain/rust/lib`;
* rustc are nevoie de `LD_LIBRARY_PATH` catre acel lib dir (setat in `toolchain.env_vars()` /
  `toolchain.rust_env()`), de linker-ul `files/tmp/clang` cu `--target`/`--sysroot` (scrise in
  `files/cargo/config.toml`) si de CA bundle pentru crates.io.

### Capcane dovedite DUPA prima runda (46-48) - pachete Python cu Rust (cbor2 6.x)
46. **cargo NU propaga linker-ul catre build-scripturi** (nici prin `[target.*].linker`, nici
    prin `RUSTFLAGS`, nici cu `build.target-applies-to-host` - cheia nici nu e recunoscuta de
    cargo 1.98). Simptom: build-scripturile se linkau cu clang FARA `--target/--sysroot` ->
    `cannot open crtbegin_dynamic.o` + `unable to find library -ldl/-llog/-lm/-lc`, deci orice
    crate cu `build.rs` cadea (majoritatea). Fix: **wrapper de linker** `files/tmp/cc-rust`
    (script shell care executa clang-ul din APK cu `--target/--sysroot`) pus ca `linker` in
    `files/cargo/config.toml`. Scriptul e executabil pentru ca e interpretat de `/system/bin/sh`.
47. **App-ul POATE executa binare din propriul filesDir** (verificat: `rustc --version` rc=0
    dintr-un director din `files/`). Restrictia SELinux se aplica `shell_data_file`
    (`/data/local/tmp`), nu datelor proprii ale app-ului. Concluzie practica: build-scripturile
    cargo merg; pentru binarele "de sistem" (rustc/cargo) ramane totusi mai curat jniLibs.
48. **`cbor2 6.x` se compileaza acum de la sursa pe device**: wheel
    `cbor2-6.1.4-cp314-cp314-android_24_arm64_v8a.whl`, 710 s, rulare verificata
    (`CBOR2_RUST_OK {'a': [1, 2, 3]}`). Baza: `setuptools-rust` + cargo/rustc din APK.
    (Pachetele care folosesc `maturin` ca backend - orjson, cramjam, pydantic-core - cer
    binarul `maturin` livrat in jniLibs: pas urmator.)

---

## Etapa 54 - FAZA 5: MATURIN PE DEVICE (pachete Python cu backend maturin) - `.assets_v207`

**Rezultat: `orjson 3.12.0` compilat PE TELEFON in 28 s** (wheel `orjson-3.12.0-cp314-cp314-
android_35_arm64_v8a.whl`), verificat functional: `ORJSON_RUST_OK {'a': [1,2,3], ...}`.

### Ce s-a construit / livrat
- `maturin 1.15.0` construit PE DEVICE (`cargo install maturin`, 11m46s) -> `jniLibs/
  libmaturin_exec.so` (21 MB stripat) + lansator `files/tmp/maturin`;
- shim Python PEP 517 `maturin` scris automat in site-packages (`toolchain._ensure_maturin()`):
  pachetele cu `build-backend="maturin"` n-au wheel pentru Android, deci modulul nu exista deloc;
- rustc RECONSTRUIT cu `optimize = true` (vezi capcana 49) -> driver 87 MB in loc de 415 MB;
- APK: 619 MB.

### Capcane dovedite (49-54)
49. **`optimize = false` produce un rustc CARE CRAPA**: `SIGSEGV` la compilarea lui `typenum`
    (rc=-11, reprodus si fara cargo). bootstrap avertiza exact asta ("known to cause errors and
    should be considered unsupported"). Fix: `[rust] optimize = true` (rebuild 34 min).
50. **`patchelf --add-needed` DUPĂ `strip` rupe tabela de hash** -> bionic refuza libraria:
    "empty/missing DT_HASH/DT_GNU_HASH ... (new hash type from the future?)". Fix: **strip
    INAINTE, patchelf DUPĂ** (invers fata de cum pare natural).
51. **`cc-rs` cauta `<target>-clang`** (crate-uri cu C: libgit2/ring/zstd) -> "failed to find
    tool aarch64-linux-android-clang". Fix: `CC_/CXX_/AR_aarch64-linux-android` +
    `CARGO_TARGET_AARCH64_LINUX_ANDROID_LINKER` = wrapper-ul nostru `files/tmp/cc-rust`.
52. **clang-ul din APK nu-si gaseste headerele BUILTIN** (`float.h`): binarul e redenumit in
    `libclang_exec.so` -> "fatal error: 'float.h' file not found" (a oprit zstd-sys). Fix:
    `-resource-dir=$ROOT/lib/clang/21` in wrapper.
53. **LTO cade cu bitcode din alt LLVM**: std-ul are bitcode produs de LLVM 22.1.8 (LLVM-ul
    intern al Rust 1.98.1), rustc-ul de device e linkat cu libLLVM 21.1.8 ->
    "Unknown attribute kind (105) (Producer: 'LLVM22.1.8-rust-1.98.1-stable' Reader: 'LLVM
    21.1.8')" (dovedit cu orjson, care activeaza LTO in profilul release). Fix:
    `CARGO_PROFILE_RELEASE_LTO=false` (+ `DEBUG=false`) in `rust_env()`/`env_vars()`.
54. **cargo NU propaga linker-ul/rustflags catre build-scripturi** (nici cu
    `build.target-applies-to-host`, cheie nerecunoscuta de cargo 1.98, nici prin RUSTFLAGS) ->
    wrapper de linker `files/tmp/cc-rust` pus ca `linker` in `files/cargo/config.toml`.

---

## Etapa 55 - FAZA 4c: TEST E2E DIN UI + 3 REPARATII (`.assets_v210`)

Test real: task scris din interfata, executat de agent pe device. Agentul a lucrat corect
(33 pasi, a compilat si verificat pe device), dar a raportat de doua ori concluzii gresite -
de fiecare data din cauza unor defecte REALE ale toolchain-ului, reparate acum:

1. **`selftest()` raporta `cargo` OK doar pe EXISTENTA** binarului (fals pozitiv semnalat de
   agent). Acum ruleaza real `cargo --version` si intoarce `cargo_error`.
2. **Presiune de memorie**: cu ~579 MB liberi, `rustc` moare cu SIGSEGV fara mesaj (incarca
   librustc_driver ~90 MB + libLLVM). `selftest()` intoarce acum `ram_liber_mb` +
   `ram_atentionare` sub 900 MB, iar `agent.py` are regula: la SIGSEGV/-11/139 pe Rust,
   primul lucru verificat e RAM-ul liber.
3. **`libc++_shared.so` lipsea din `rust-libs.tar.gz`** (regresie de impachetare) ->
   "CANNOT LINK EXECUTABLE rustc: library libc++_shared.so not found". Reparat in
   `build/rust_pack.sh` (pasul 3b).

Plus: `agent.py` noteaza explicit ca `LD_LIBRARY_PATH` trebuie **PREPEND**, niciodata inlocuit
(agentul a descoperit singur ca inlocuirea pierde calea nativeLibraryDir -> segfault).

**Rezultat pe `.assets_v210`: `selftest` -> `rust=True`, `cargo=True`, `ram_liber_mb=4485`.**

---

## Etapa 56 - FAZA 4d: REPARATII DEFINITIVE DIN CONVERSATIA AGENTULUI (`.assets_v212`)

Am citit toata conversatia agentului (context.json) si am reparat tot ce a raportat ca rupt:

1. **Fortran/flang era REAL rupt** ("unknown argument: '-c'"): wrapperul pasa flag-uri de driver
   (`-c`, `-o`) catre `flang-bin -fc1`, care nu le accepta. Acum wrapperul le TRADUCE (scoate
   `-c`, pune `-emit-obj`, muta rezultatul la `-o`). Dovedit pe device: `flang -c t.f90` -> rc=0,
   obiect produs.
2. **binutils (ar/ranlib/nm/strip/readelf/objdump)** nu aveau lansatoare in `files/tmp` ->
   cmake/autotools cadeau cu "Permission denied" (fals negativ raportat de agent). Acum
   `_ensure_launchers()` le creeaza; `toolchain_env.sh` exporta caile din `files/tmp`.
3. **Executia binarilor compilati** (capcana mare descoperita de agent): procesul app NU poate
   executa un ELF proaspat compilat (SELinux `data_file_type`; Android 10+). Calea care merge:
   `/apex/com.android.runtime/bin/linker64 <binar> [args]`. Regula e acum in promptul agentului
   (3b), ca sa nu mai raporteze "build rupt" din cauza asta.
4. **ADB require autorizare** ("TimeoutError la AUTH / dialogul Allow USB debugging"): mesajul de
   eroare al `adbsh` spune acum explicit ce sa faca operatorul (reactiveaza USB debugging +
   "Always allow from this computer"), in loc de un text opac.

**Rezultat pe `.assets_v212`: `selftest` -> cmake=True, rust=True, cargo=True, fortran=True,
`lipsa: []`.**

---

## Etapa 57 - FAZA 4e: EXECUTIA IN DOMENIUL APP-ULUI (lansatori ELF) - `.assets_v213`

Al doilea test din UI a aratat exact ce lipsea: `untrusted_app` (procesul real al agentului)
**NU poate executa fisiere din filesDir** (Android 10+, W^X) - deci toate WRAPPER-ELE SCRIPT
(`cc-rust`, `flang`) functionau doar cand erau chemate prin `run-as`/shell, nu in fluxul normal
al app-ului. Dovedit de agent: "fortran - PermissionError(13)".

Fix definitiv: lansatori **ELF** in `jniLibs` (executabile din nativeLibraryDir, in ORICE context):
- `libccrust_exec.so` (build/shim/ccrust.c): executa clang-ul din ACELASI director cu
  `--target/--sysroot/-resource-dir` - inlocuieste scriptul `cc-rust` (si creeaza `cc`, `c++`);
- `libshwrap_exec.so` (build/shim/shwrap.c): executa `/system/bin/sh <nume>.sh "$@"` pentru
  wrapper-ele script (flang/flang-new/flang-21 → `files/tmp/flang.sh`).

Alte doua reparatii din acelasi test:
- **`setuptools` fusese sters** din site-packages (pip cu `--no-build-isolation` il importa
  direct) -> `_ensure_setuptools()` il reinstaleaza o data (cu marker), la primul env.
- `CMAKE_ROOT` trebuie setat la `toolchain/cmake` pentru apelurile directe de `cmake`
  (selftest-ul il foloseste deja; agentul a confirmat ca e nevoie in shell-ul lui).

Nota de mediu (confirmata de agent): `run-as net.sys32.agent sh -c ...` vede si executa
filesDir-ul; procesul app, in schimb, doar CITESTE (exec interzis) - de aceea binarul produs se
ruleaza cu `/apex/com.android.runtime/bin/linker64 <binar>`.

## Etapa 58 - FAZA 4f: SELFTEST FARA FALS NEGATIV LA CMAKE (`.assets_v214`)

Al treilea test din UI: agentul a raportat toolchain-ul **functional complet** (C, C++, Fortran,
Rust, extensii Python, cmake - toate compileaza SI ruleaza), ramanea doar un fals negativ:
`selftest` -> `lipsa: ["cmake"]` cu `llvm-ar: Permission denied`.

Cauza: `selftest()` nu chema `_ensure_launchers()`, deci testul cmake folosea
`toolchain/bin/llvm-ar` (cale neexecutabila in sandbox-ul app-ului). Fix: `selftest()` creeaza
lansatoarele intai, iar fallback-ul din `_SHIM` prefera lansatorul ELF din `files/tmp`.

**Rezultat pe `.assets_v214`: `selftest` -> toate capabilitatile True, `lipsa: []`.**

## Etapa 59 - FAZA 4g: BINARELE SUNT SI IN `toolchain/bin` (`.assets_v215`)

Al patrulea test din UI: agentul a raportat "**lipseste cmake, binarul pur si simplu nu exista**"
- pentru ca a cautat in `files/toolchain/bin/` (unde erau doar symlink-uri `llvm-*` catre NDK-ul
neexecutabil) si nu in `files/tmp/`. cmake EXISTA de fapt ca `jniLibs/libcmake_exec.so` cu
symlink in `files/tmp/cmake`.

Fix: `_ensure_launchers()` scrie acum symlink-uri ELF (catre nativeLibraryDir, deci executabile
si din filesDir - SELinux judeca TINTA) pentru TOATE uneltele, in AMBELE locuri:
`files/tmp/` si `files/toolchain/bin/` - cmake, ninja, make, perl, clang, clang++, ar, llvm-ar,
ranlib, nm, strip, readelf, objdump, pkg-config, rustc, cargo, maturin, patchelf, ld.lld, cc-rust.

Dovedit pe device: `toolchain/bin/cmake --version` -> rc=0, `cmake version 3.31.6`;
`selftest` -> cmake=True, rust=True, cargo=True, fortran=True, `lipsa: []`.

Plus regula (3a) in promptul agentului: binarele sunt ELF in lib-ul APK-ului + symlink-uri in
`files/tmp` si `files/toolchain/bin`; o unealta "lipsa" se verifica cu `toolchain action=env`
(PATH-ul returnat), nu cu `ls`.

## Etapa 60 - FAZA 4h: BUG REAL IN `pip_install` (ORDINEA PYTHONPATH) - `.assets_v216`

Al cincilea test din UI (sesiune luata de la 0): agentul a izolat singur un bug REAL al tool-ului:

**Simptom:** orice `toolchain action=pip_install` (lxml, MarkupSafe) -> `exit 1 in 0s` /
`KeyError('prefix')`.
**Cauza:** calea de pip a tool-ului injecta zip-urile in `sys.path` in ordinea GRESITA
(`pysitepkg.zip` INAINTEA `stdlib_extra.zip`). Pachetul `zipfile/` din stdlib n-are subpachetul
`_path` (e doar in `stdlib_extra.zip`), deci `importlib.metadata` (folosit de pip) cadea inainte
sa inceapa build-ul. **`stdlib_extra.zip` trebuie sa fie PRIMUL.**
**Fix:** ordinea corecta in toate cele 3 locuri (PYTHONPATH in `_env()`, in actiunea
`pip_install`, si in injectarea `sys.path[:0]`).

**Dovada pe `.assets_v216`:** `pip install --force-reinstall MarkupSafe` -> rc=0 in 15s,
wheel construit pe device, `import markupsafe` -> OK 3.0.3; `selftest` -> cmake/rust/cargo/fotran
toate True, `lipsa: []`.

Plus doua capcane raportate de agent, reparate in CFLAGS/LDFLAGS (se aplica si in cmake):
- **`-resource-dir=<TC>/lib/clang/21`** explicit in CFLAGS: clang apelat prin symlinkul din
  files/tmp isi calcula resource-dir la `/lib/lib/clang/21/...` -> "cannot open"/"stddef.h not found";
- **`-L<TC>/lib/clang/21/lib/linux`** in LDFLAGS: acolo stau `libatomic.a`/`libclang_rt.*.a`
  (statice), fara ele `-latomic` nu se rezolva.

## Etapa 61 - OPTIMIZARE PE BAZA CONVERSATIEI (`.assets_v217`)

Reanaliza conversatiei (agent nou, de la 0, 40 de pasi, ~7k tokeni) a scos 4 pierderi de timp
si de context, toate reparate:

1. **`toolchain action=env` intorcea ~7,4 KB** de `export`-uri (cel mai mare mesaj din context,
   re-trimis la fiecare pas). Acum: **2418 caractere** (-67%) cu PATH/CC/CXX/AR/CFLAGS/LDFLAGS/
   PKG_CONFIG_PATH + **exemple gata de copiat** (C, C++, extensie Python, Fortran, Rust, cmake),
   comanda de rulare (linker64) si regula de build-dir. Export-urile complete raman in
   `files/toolchain_env.sh`.
2. **Agentul ghicea flag-uri** si pierdea pasi (`-latomic` x2, `--target`, `-resource-dir`).
   Acum exemplele din `env` sunt literale copy-paste, iar `-resource-dir` si
   `-L<TC>/lib/clang/21/lib/linux` (libatomic/compiler-rt statice) sunt deja in CFLAGS/LDFLAGS.
3. **`multi` cu `kind` necunoscut rula body-ul ca bash** -> `sh: all: inaccessible or not found`
   (in conversatie: `[1] env (toolchain) --- sh: all: ...`). Acum: mesaj explicit care spune sa
   puna codul in `body` cu `kind=python`.
4. **Build pe /sdcard** (noexec) -> binarul nu se putea mapa, apoi copiere manuala in files/tmp
   (2 pasi pierduti). Regula (3c) in prompt: se compileaza in `files/tmp`/workspace, NICIODATA
   pe /storage; iar `env` afiseaza deja bucla completa de build+rulare.

## Etapa 62 - SELFTEST AUTO-DOCUMENTAT (`.assets_v218`)

Dupa optimizari, testul "verifica toolchain complet" a rulat in **4 pasi / ~850 tokeni** (inainte:
40 de pasi / ~7k tokeni) - 1 apel de tool, verdict corect. Dar raportul agentului continea doua
inexactitati pe care le INVENTA (selftest-ul nu spunea ce implementari sunt instalate):
"libstdc++" (de fapt **libc++**) si "gfortran-style" (de fapt **FLANG**).

Fix: `selftest()` intoarce acum si `detalii` - harta cu ce este instalat CONCRET:
clang 21.1.8 + libc++ (NU libstdc++), FLANG 21.1.8 (NU gfortran), rustc/cargo 1.98.1 + maturin
1.15.0, cmake 3.31.6/ninja/make 4.4.1/meson/scikit-build-core/setuptools/cython/pybind11,
perl 5.42.0, unde sunt binarele, cum se ruleaza ELF-ul (linker64/adbsh) si ca build-dir-ul e
files/tmp (nu /sdcard). Regula (0) din prompt cere agentului sa foloseasca numele reale din
`detalii` in rapoarte.

## Etapa 63 - FAZA 4i: 5 BUG-URI REALE DIN TESTUL "fa test complet toolchain" (`.assets_v219`)

Al saselea test din UI (68 de pasi, agent pornit de la 0) a sapat mult mai adanc decat selftest-ul
si a scos 5 defecte reale:

1. **`pip` in-process -> `KeyError('prefix')`** (`[pip inline exception]` la orice `pip_install`).
   Cauza: varianta veche rula `from pip._internal.cli.main import main` IN PROCESUL AGENTULUI,
   unde pip nu-si poate citi configuratia schemei. **Fix:** pip ruleaza acum intr-un SUBPROCES cu
   env-ul complet (`env_vars()` + `PYTHONPATH` cu `stdlib_extra.zip` PRIMUL), cwd=`files/tmp`.
   Dovedit: subprocesul ajunge la validarea argumentelor pip (fara `KeyError`), iar
   `pip install --force-reinstall MarkupSafe` merge rc=0/15s.
2. **`toolchain_env.sh: No such file or directory`** - `env` trimitea la un fisier care nu era scris.
   **Fix:** actiunea `env` scrie fisierul. Verificat: `sh -n` rc=0 si sursare OK.
3. **`export CC_aarch64-linux-android=...: is not an identifier`** - cheile cu cratime ajungeau in
   export-uri. **Fix:** `_toolchain_exports()` filtreaza identificatorii shell valizi.
4. **`CANNOT LINK EXECUTABLE t_f90: library "libc++_shared.so" not found`** - binarul construit nu-si
   gasea libc++ la RULARE. **Fix:** `-Wl,-rpath,<nativeLibraryDir>` + rpath deps/lib in LDFLAGS.
   Verificat: binar C++ (`std::vector`, libc++) ruleaza cu `LD_LIBRARY_PATH=/nonexistent` -> `cpp=6`.
5. **`cython: Permission denied`** - `files/tmp/cython` era SCRIPT in filesDir (untrusted_app nu
   executa scripturi de acolo). **Fix:** launcher ELF (`libshwrap_exec.so`) + `<nume>.sh`, ca la
   flang; adaugat si `pip`. Verificat: `cython --version` -> rc=0 "Cython version 3.3.0".
6. **`-latomic` nu se rezolva** la compilare+linkare intr-un singur pas: calea
   `lib/clang/21/lib/linux` (libatomic/compiler-rt statice) e acum si in CFLAGS, nu doar in LDFLAGS.

## Etapa 64 - FIX CRITIC: PACHETELE PIP MUREAU LA UPDATE-UL DE APK (`.assets_v220`)

Gasit verificand conversatia agentului: in `files/pyhome/lib/python3.14/site-packages` lipseau
numpy, cbor2, orjson (instalate anterior cu pip), in timp ce lxml/cython/pybind11 erau prezente.
Motive: cele prezente sunt LIVRATE IN ASSETS, cele lipsa fusesera instalate cu pip pe device.

**Cauza (MainActivity.kt, ~linia 700):** la fiecare re-extragere de assets, codul SALVA corect
`site-packages` in `files/site_packages_keep`... dar **nu-l punea niciodata la loc** dupa
re-extragere (comentariul promitea protectie, codul de restaurare lipsea). Deci fiecare
`adb install -r` stergea toate pachetele compilate de agent (ore de munca).

**Fix:** dupa `copyDir("python", dest)` se restaureaza `site_packages_keep` peste noul
`site-packages` (`copyRecursively(overwrite=true)` - versiunile instalate de agent au prioritate
fata de cele din APK), apoi depozitul se goleste.

**Dovada (test real end-to-end):** `pip install six` -> import OK; rebuild APK v220 + `adb install -r`
+ repornire -> `six-1.17.0.dist-info`/`six.py` inca in site-packages, `import six` OK 1.17.0.

**Ramas de rezolvat (raportat, nefixat):** numpy nu se poate reinstala - build-ul meson-python
cade la sanity-check cu `[Errno 13] Permission denied` pe binarul de test compilat in `files/tmp`
(acelasi motiv SELinux: exec din datele aplicatiei). Cbor2/orjson se pot reinstala oricand cu pip
(se compileaza pe device).

## Etapa 65 - FAZA 4j: NUMPY COMPILAT PE DEVICE (`.assets_v223`)

Dupa fix-urile din Etapa 63-64, numpy a fost atacat sistematic; au mai fost necesare 3 fix-uri:

1. **`meson` nu gasea Cython** ("Unknown compiler(s): [['cython'], ['cython3']]"). Cauza reala
   (din meson-log): `Detecting compiler via: cython -V -> 127`,
   `/system/bin/sh: cython.sh: No such file or directory`. Meson cheama launcher-ul cu NUME SIMPLU
   (gasit prin PATH), iar `shwrap` derivaba `<argv[0]>.sh` **relativ** la cwd-ul apelantului.
   **Fix in `build/shim/shwrap.c`:** daca argv[0] nu contine '/', se rezolva prin PATH (primul
   entry cu X_OK) si abia apoi se deriva scriptul din calea ABSOLUTA (+ fallback filesDir/tmp).
   Reconstruit cu NDK: `aarch64-linux-android35-clang -O2 -static -o libshwrap_exec.so`.
   Verificat: `cython -V` cu nume simplu din orice cwd -> rc=0.
2. **`cython3` lipsea** -> adaugat launcher-ele `cython3`/`cython-3` (meson cauta exact aceste nume).
3. **`env` de pe Android (toybox) executa gresit comenzile lui meson**:
   `env PYTHONPATH=... libpyexec.so -m code_generators.generate_umath` ->
   `env: exec -m: No such file or directory` (rc=127), deci numpy cadea la primul pas de codegen.
   **Fix:** launcher `env` propriu (`env.sh` + symlink la libshwrap_exec.so) primul in PATH, cu
   parsare corecta a `NAME=VALUE` (atentie: calea APK contine `==`, deci pattern-ul de nume e
   `[A-Za-z_]*=*`, nu `*=*`).

**REZULTAT (dovada pe device, `.assets_v223`):** `pip install numpy` -> **numpy 2.5.3** rc=0 in
174 s (meson-python + ninja + clang + Cython 3.3.0 + OpenBLAS 0.3.29 detectat prin pkg-config);
`import numpy` -> `numpy.arange(6).reshape(2,3).sum()` = 15; dupa un update de APK:
`numpy.linalg.det([[1,2],[3,4]])` = -2.0000000000000004 (numpy a SUPRAVIETUIT update-ului -
validarea fix-ului critic de site-packages). orjson 3.12.0 s-a reinstalat (36 s) si functioneaza.

### Etapa 65b - pachete pierdute la update-urile de APK, refacute

Dupa fix-ul de site-packages (Etapa 64) si fix-urile de la numpy (Etapa 65), pachetele pierdute in
timpul testelor au fost reinstalate pe device cu `pip_install` (toate compileaza nativ):

- numpy 2.5.3 (174 s, meson-python + ninja + Cython + OpenBLAS)
- orjson 3.12.0 (Rust/maturin), cbor2 6.1.4 (Rust/setuptools-rust, 67 s - necesita `setuptools-rust`)
- Pillow 12.3.0 (26 s), cffi 2.1.1, apsw 3.53.4.0 (107 s), zstandard 0.25.0, lz4 4.4.5,
  msgpack 1.2.3, regex 2026.9.29, simplejson 4.1.2
- ramas neinstalat: kiwisolver (doar pt. matplotlib) - build-ul lui cade pe toolchain-ul curent

## Etapa 66 - TEST E2E UI + RPATH STABIL (`.assets_v224`)

Test E2E din interfata aplicatiei (task scris in UI, executat autonom de agent):

**Task:** "instaleaza cu toolchain pip_install pachetul wrapt si verifica importul si versiunea lui"
**Rezultat:** 6 pasi, 25.0 s, `tok ↑26.8k ↓916`, hit 99%. Agentul a instalat wrapt (exit 0 - deci
calea `pip_install` reparata in Etapa 63 functioneaza din UI), apoi a raportat singur:
- **numpy 2.5.3** cu `reshape(3,4)`, `sum()=66`, `T.shape=(4,3)`, `dot` si **BLAS: openblas**
  (deci numpy compilat in Etapa 65 se leaga corect la OpenBLAS);
- module importabile: lxml, numpy, cython, pybind11, wrapt, yaml, setuptools - toate True;
- capcana gasita de el: dupa un update de APK, calea `nativeLibraryDir` se schimba
  (`/data/app/~~hash==/pkg-.../lib/arm64`), deci **binarele compilate inainte de update nu-si mai
  gaseau libc++_shared.so**.

**Fix (pornit de la raportul lui):** rpath-urile nu mai arata doar catre nativeLibraryDir (cale
volatila), ci catre o cale STABILA: `files/libs` (unde `_stable_libs()` copiaza `libc++_shared.so`
din APK), plus `deps/lib`. Verificat cu un ciclu real: binar C++ compilat -> `RPATH_OK=12`;
**update de APK** (cale noua de nativeLibraryDir) -> **acelasi binar ruleaza** -> `RPATH_OK=12`.

Note de testare UI: acest ROM nu traduce `%s` in `input text`, iar parantezele sparg shell-ul;
textul se tasteaza cuvant cu cuvant + `input keyevent 62` (spatiu).

## Etapa 67 - FIX: `adbsh` NU EXECUTA NIMIC (uid 2000) - `.assets_v225`

Sesiune noua de test din UI ("verifica uid 2000 apoi test complet toolchain"): agentul a raportat
corect ca `bash`/`smart` ruleaza ca uid 10322 (app-ul, normal) dar **`adbsh` nu executa nimic**:
intorcea mereu acelasi blob binar `\x03\x01\x00\x00\x00\x01`.

**Diagnostic (reprodus cu probe):** clientul ADB pur-Python era perfect functional
(`adb_client.shared().shell('id')` -> `uid=2000(shell)`, autorizat pe portul 5555, adbd cu
`service.adb.tcp.port=5555`). Vinovatul era `run_adbsh_tool()`, care prefixa FIECARE comanda cu
`. /data/data/net.sys32.agent/files/toolchain_env.sh` - un fisier **APP-PRIVATE**, pe care shell-ul
uid=2000 NU il poate citi ("Permission denied"). Acea eroare desincroniza protocolul si lasa in
socket bytes binari reziduali, pe care tool-ul ii returna apoi ca "output" pentru TOATE comenzile.

**Fix (2 parti):**
1. scos prefixarea cu toolchain_env.sh - n-avea oricum sens: toolchain-ul e al aplicatiei
   (binarele stau in nativeLibraryDir, neexecutabile de shell);
2. garda anti-desync in `run_adbsh_tool`: daca payload-ul (dupa marker) contine doar bytes de
   control, se reconecteaza si se reincearca o data; daca reapare, se raporteaza explicit
   "desync de protocol (raspuns binar): comanda NU a fost confirmata" in loc sa intoarca blob-ul.

**Dovada:** `run_adbsh_tool('id')` -> `uid=2000(shell) gid=2000(shell) ...`;
`run_adbsh_tool('echo TEST_ADBSH')` -> `TEST_ADBSH`; `ls /data/local/tmp | head -3` -> listare reala.

## Etapa 68 - OPTIMIZARI DIN TESTUL "uid 2000 + toolchain complet" (`.assets_v226`)

Sesiune de 185 de pasi (~20k tokeni). Agentul a REUSIT pana la urma (a dovedit uid 2000, C/C++/Rust/
pyext end-to-end), dar a pierdut zeci de pasi pe 3 probleme reale:

1. **„gunoi binar" in output-urile de shell** (`\x01\x0b\x00\x00\x00`, `\x02...`,
   `\x03\x01\x00\x00\x00\x01`). Cauza: `adb_client._shell_locked` presupunea ca fiecare pachet
   A_WRTE contine EXACT un header de substream shell-v2 (`d[0] in (1,2) -> d[5:]`). adbd poate pune
   mai multe substream-uri (stdout+stderr+exit) in ACELASI pachet sau poate sparge unul pe doua:
   atunci header-ele interioare ajungeau in textul vazut de agent (de aici si concluziile lui
   gresite ca "tool-ul returneaza mereu acelasi blob"). **Fix:** acumulam bytes brut si demultiplexam
   fluxul complet (`_demux_shellv2`: 1 byte stream + 4 bytes LE length + payload; 1=stdout, 2=stderr,
   3=exit; cadre rupte pastreaza ce s-a primit).
   Dovada: `echo OUT_OK; echo ERR_LINE 1>&2; ls /nope 2>&1; exit 3` -> output curat, zero bytes de
   framing (inainte: header-e + cadrul de exit).
2. **`toolchain action=compile` era rupt** ("clang: inaccessible or not found", ~20 de pasi pierduti):
   rula prin `adbsh` (uid 2000), care NU poate citi filesDir (toolchain-ul e al aplicatiei).
   **Fix:** compilarea se face acum IN PROCESUL APLICATIEI, cu env-ul complet din `env_vars()`
   (CC/CXX/CFLAGS/LDFLAGS), output implicit in `files/tmp`, iar binarul e RUNAT imediat (direct, cu
   fallback pe `linker64`). Dovada: C -> COMPILE_OK + `HELLO_FROM_COMPILE`; C++ (STL) -> `CPP=5`.
3. **Rust prin `rustc` direct** a consumat ~50 de pasi (linkerul implicit `cc` nu se rezolva in
   mediul spawn-uit de rustc). Calea care merge (cargo + linker-ul din `files/cargo/config.toml`)
   era deja pregatita, dar agentul nu stia. **Fix:** regula (3d) in prompt: pentru Rust se foloseste
   cargo; nu se pierde timp cu `rustc` direct. Plus regula (3e): binarele ELF din files/tmp sunt
   executabile direct (dovedit), scripturile nu (foloseste lansatoarele ELF).

## Etapa 69 - OPTIMIZARI DIN TESTUL "verificare completa toolchain" (`.assets_v227`)

Sesiune noua: 41 de pasi / ~5.7k tokeni (fata de 185/~20k la testul anterior) - deci fix-urile din
Etapa 68 isi fac efectul. Au ramas 3 probleme reale, toate reparate:

1. **`preflight` raporta TOTUL false** (`c_compile: false, cxx_compile: false, cmake: false...`) in
   timp ce `doctor`/`selftest` erau verzi - agentul a pierdut pasi verificand cine are dreptate.
   Cauza: preflight era un SCRIPT SHELL bazat pe aranjamentul VECHI (toolchain/bin/python3.14,
   ROOT/usr/lib, samu, git, LD_PRELOAD) - dupa mutarea toolchain-ului in APK si a libs in deps/*.a
   nu mai functiona nimic din el. **Fix:** preflight deleaga acum la `selftest` (compilare+linkare
   REALA in procesul aplicatiei) + `api` + nota. Dovada: preflight -> c/cxx/pyext/fortran/cmake/
   rust = True, `lipsa: []`, identic cu selftest.
2. **C++ nu se lega fara `-lc++_shared`** (agentul: "undefined symbol __gxx_personality_v0" si a
   adaugat flag-ul manual). **Fix:** LDFLAGS include acum `-L files/libs` + `-lc++_shared`.
   Dovada: `toolchain action=compile` pe un C++ cu STL, fara nici un flag suplimentar:
   COMPILE_OK + RUN rc=0 `CXX_DEFAULT=9`.
3. **Extensiile Python cereau flag-uri ghicite** ("unable to find library -lpython3.14" /
   "undefined symbol: PyModule_Create2"). **Fix:** `_stable_libs()` asigura si
   `files/libs/libpython3.14.so` (lipsa din LDFLAGS e acum acoperita de `-L files/libs`), iar
   `action=compile` adauga AUTOMAT `-lpython3.14` cand sursa include `Python.h` si iesirea e .so.
   Dovada: extensie Python.h compilata fara flag-uri -> `IMPORT OK dublu(21) = 42`.
4. **Promptul continea o afirmatie perimata** ("the toolchain in /data/local/tmp belongs to uid 2000
   ... you cannot execute them") - acum spune realitatea: uid 2000 NU poate citi filesDir (mod 700,
   alt proprietar), toolchain-ul e EXCLUSIV al aplicatiei, iar in /data/local/tmp pot exista
   wrapper-e VECHI care arata spre cai de APK demultate (de ignorat).

## Etapa 70 - FIX MAJOR: `adbsh` (uid 2000) - AUTH_SIGNATURE, nu RSAPUBLICKEY (`.assets_v228`)

Testul din UI "nu merge uid 2000?" a expus cauza reala, dupa doua sesiuni in care agentul a
raportat corect ca `adbsh` nu raspunde:

**Simptom:** clientul se conecta la adbd (`[adb] TCP conectat`), trimitea RSAPUBLICKEY si apoi
AȘTEPTA la nesfarsit -> `TimeoutError` (sau, prin tool, mesajul de "protocol desync").
**Cauza:** cand adbd are DEJA cheia in lista lui autorizata, el NU raspunde la RSAPUBLICKEY (nu are
ce sa afiseze in dialog) - așteapta dovada ca ai cheia PRIVATA, adica `AUTH_SIGNATURE`. Ordinea
veche (RSAPUBLICKEY primul, cu un comentariu "verificat pe device" din alt context) nu era corecta
pentru acest caz.
**Fix:** pe AUTH_TOKEN semnam token-ul (RSA PKCS#1 v1.5 / SHA1, exact ca `adb_auth_sign` din AOSP)
si trimitem `AUTH_SIGNATURE`; RSAPUBLICKEY rămâne fallback (pentru chei neautorizate, unde adbd
chiar afiseaza dialogul). Plus: mesaj explicit cand adbd tot nu raspunde (instructiuni pentru
dialogul Allow) si `shared()` nu mai pastreaza in cache o conexiune rupta.

**Dovada:** `[adb] AUTH -> AUTH_SIGNATURE (256 bytes)` -> `✓ AUTORIZAT` in 0.1s;
`id` -> `uid=2000(shell) gid=2000(shell) ...`; `echo ADB_OK` -> `ADB_OK`; `getprop
ro.build.version.sdk` -> `36`.

**Cheia:** aplicatia foloseste acum cheia ADB deja autorizata a operatorului (copiata in
`files/adbkey`/`adbkey.pub`), deci nu mai e nevoie de niciun dialog pe telefon.

## Etapa 71 - Fortran si capcane de rulare (`.assets_v228`)

- **Fortran**: agentul a pierdut pasi cu `toolchain/bin/flang` ("gcc frontend command failed").
  Driverul brut NU merge (cheama un `gcc` inexistent); calea corecta e wrapperul
  `files/tmp/flang` (lansator ELF -> flang.sh -> `flang-bin -fc1`). Exemplul din `toolchain env`
  arata acum wrapperul. Dovada: rc=0 si RUN -> `210`.
- Regula noua (3f) in prompt: `linker64` cere cale ABSOLUTA; un `.so` compilat nu se poate importa
  din `/sdcard` (namespace de linker) - se copiaza in `files/libs`/`files/tmp`; Fortran doar prin
  wrapper; daca adbsh cere autorizare, nu se insista la infinit (se folosesc uneltele native).
- Lectie de proces: la editarea promptului (text lung intr-un singur string Python) ghilimelele
  duble din text sparg literalul - s-a intamplat de doua ori; acum se folosesc doar backtick/ghilimele
  simple in textele inserate, iar `py_compile` se ruleaza INAINTE de push pe device.

## Etapa 72 - FIX CRASH: agentul murea la `tempfile.TemporaryFile(dir=WORK)` (`.assets_v229`)

Operatorul a raportat un crash. Traceback-ul din UI: `agent.py` -> `call_tool` -> `run_tool` ->
`py()` -> linia 1477 `tempfile.TemporaryFile(dir=WORK)` -> `tempfile._mkstemp_inner` ->
excepție propagata pana in bucla principala -> **procesul agentului murea** (taskul se pierdea).

Diagnostic: WORK (workspace-ul de pe /sdcard) e deținut de alt uid (`u0_a293`, mod 2770, grup
media_rw) - accesul functioneaza de obicei, dar pe FUSE o operație de tempfile poate cadea
tranzitoriu (fd-uri/epuizare, hiccup FUSE). Verificat pe device: scrierea normala si
TemporaryFile merg acum, deci a fost un esec TRANZITORIU - exact tipul de eroare care nu trebuie
sa omoare niciodata procesul.

**Fix (2 straturi):**
1. `py()` nu mai depinde de un singur loc: incearca `tempfile.TemporaryFile(dir=WORK)`, apoi
   `files/tmp`, apoi tempfile-ul implicit, iar in ultima instanta `io.BytesIO()` - codul se executa
   ORICUM (bufferul LIVE nu e critic). Plus `_raise_fd_limit()` (ridica soft-ul RLIMIT_NOFILE la hard).
2. Garda in bucla principala: orice excepție din `call_tool` devine un REZULTAT de tool
   (`[tool error] ...` + traceback) pe care agentul il vede si continua - nu mai omoara procesul.

**Dovada (test cu fd-uri epuizate intentionat):** limita coborata la 64, 58 fd-uri ocupate ->
`py()` a rulat codul: `COD_RULAT_CHIAR_SI_CU_FD_EPUIZAT`; in regim normal: `42`.

## Etapa 73 - OPTIMIZARI DIN TESTUL E2E "testeaza toolchain complet" (`.assets_v230`)

Sesiune de 202 pasi / ~121k tokeni (95 mesaje asistent, 105 apeluri de tool) - cea mai lunga de pana
acum. Cauzele reale, toate reparate:

1. **`pip install numpy` cadea in 19s** ("preparing metadata ... No available output").
   Cauza: pip isi lanseaza build-backend-ul prin `sys.executable`, adica prin lansatorul
   `files/tmp/python3` - care era doar un SYMLINK catre libpyexec.so, fara mediu. Pornit cu env
   minimal (cum face pip), Python nu-si gasea stdlib-ul ("Could not find platform independent
   libraries <prefix>") si nu producea nimic.
   **Fix:** `files/tmp/python3` (si `python`) sunt acum lansatoare AUTO-SUFICIENTE
   (shwrap + python3.sh) care isi exporta SINGURE PYTHONHOME, PYTHONPATH, TMPDIR si
   LD_LIBRARY_PATH (PREPEND). Dovada: `python3 -c` cu `PATH=/system/bin` -> `PY3_OK 3.14.7`;
   `pip install numpy` -> rc=0 in **162s**, `numpy.linalg.det` = -2.0.
2. **Rust cadea cu "linking with `cc` failed: exit status 127"** (~10 pasi) desi regula (3d) spunea
   sa foloseasca cargo: cargo isi lua configul doar daca era lansat din `files/`. **Fix:** configul
   e acum GLOBAL (`$CARGO_HOME/config.toml`, CARGO_HOME=files/cargo). Dovada: `cargo build
   --release` dintr-un director oarecare -> rc=0 in 1s.
3. **`COMPILE error: FileNotFoundError(2)`** la `action=compile` cu sursa lipsa. **Fix:** verificare
   explicita + lista fisierelor din director (`_(scrie fisierul intai; in <dir>: [...])_`), iar
   detectia Python.h nu mai citeste orbeste fisierul.
4. **cmake**: "CMakeDetermineSystem.cmake: file failed to open" - lipsa `PREFIX` in mediu.
   Exemplul din `toolchain env` include acum `export PREFIX=<toolchain>` explicit.
5. Regasite in aceeasi sesiune (deja acoperite de regulile (3c)/(3e)/(3f) din prompt): incercari de
   a rula `python3`/toolchain-ul prin shell uid 2000 (nu poate citi filesDir), tempfile in locuri
   nepotrivite, TMPDIR greșit la clang.

Total: 5 fix-uri de cod + 2 de prompt/env. Verificat pe device: compile C/C++ cu rulare
(`C_OK 1.414214`, `CXX_OK 11`), numpy 2.5.3 reinstalat, cargo din orice cwd.

## Etapa 74 - `adbsh` stabil: cheia operatorului (`op_adbkey`) + helper de probe (`.assets_v231`)

Dupa reinstall, `adbsh` a picat din nou: `AUTH_SIGNATURE` a fost RESPINSA si a cazut pe
RSAPUBLICKEY (dialog -> timeout). Cauza: `adb_setup.py` isi REGENEREA cheia in `files/adbkey`
(comportament corect pentru un device nou), iar cheia noua nu e autorizata de adbd.

**Fix:** clientul prefera acum cheia operatorului, tinuta intr-un nume pe care setup-ul nu-l atinge:
`files/op_adbkey` + `files/op_adbkey.pub` (fallback pe `files/adbkey`). Dovada pe device:
`AUTH -> AUTH_SIGNATURE (256 bytes)` -> `✓ AUTORIZAT` in **0.0s**; `id` -> `uid=2000(shell)`;
`getprop ro.build.version.sdk` -> 36; `ls /data/local/tmp` -> listare reala.
Mesajul de eroare spune acum si varianta cu `op_adbkey`.

**Helper recreat:** `tools/probe_run.sh` (+ `temp/mk.sh` ca symlink) - rula in probe pe device ca
aplicatia, cu mediul corect; versiunea veche traia doar in temp/ si s-a pierdut la curatenie, acum
e in git.

**Baterie de verificare post-v230 (dupa reinstall):** selftest `lipsa=[]` (C/C++/pyext/Rust/cargo/
Fortran/cmake toate True, RAM 3953MB); `python3` cu env MINIMAL -> `PY3_OK 3.14.7` + numpy 2.5.3
importabil; `action=compile` C -> `C=4.000000`, C++ -> `CPP_OK` (ambele rulate); pip (extensie C)
-> rc=0 in 14s.

## Etapa 76 - optimizari din testul E2E "de la zero" (memorie stearsa) (`.assets_v234`)

Test cu memoria STEARSA (context.json + memory.md) si 18 capabilitati verificate REAL (C, C++/STL,
extensie Python.h, Fortran, Rust, Cython, pybind11, lxml, Perl, cmake+ninja, numpy/BLAS, cffi,
OpenSSL static, dlopen, pkg-config, meson, `precompile`): 162 intrari / ~19,5k tokeni (fata de
271 / ~130k in runda anterioara). Fixuri pe frecarile reale observate:

1. **Fortran in `action=compile`** folosea driverul brut -> "gcc frontend command failed".
   Acum merge prin wrapper-ul `files/tmp/flang`. Dovada: `F_SUM= 22.4683` (suma sqrt(1..10)).
2. **Doua fisiere de config cargo** (`config` + `config.toml`): cargo avertiza si folosea varianta
   DEPRECATA, ceea ce a dus la o diagnoza gresita a esecului maturin. Acum scriem DOAR
   `config.toml` si stergem duplicatele. Dovada: warning-ul a disparut.
3. **Garda binar prea agresiva**: transforma in "output BINAR" iesiri de TEXT cu secvente ANSI
   (ESC=0x1b) - agentul a pierdut ~6 pasi ocolind-o ca sa citeasca `id`. Acum ESC nu se numara si
   pragul e 25% octeti de control. Dovada: text cu ANSI trece, ELF real e rezumat.
4. **PYTHONPATH**: site-packages INAINTE de pysitepkg.zip -> pachetele de pe disc castiga
   (`pybind11.get_include()` returna o cale din arhiva -> 3 pasi pierduti).
5. **cmake**: `PREFIX` corect = `<toolchain>/sysroot/usr` (NU `<toolchain>`) + `CMAKE_ROOT`,
   acum exportate in env. Inainte: 4 incercari pierdute cu CMakeDetermineSystem.cmake.
6. **CONCLUZIE GRESITA A AGENTULUI, INFIRMATA DE NOI**: a raportat "cratele Rust cu build.rs nu
   pot fi construite (exec din datele aplicatiei interzis)" si a declarat maturin/pyo3 imposibil.
   Fals: `cargo build` pe un crate cu build.rs -> rc=0, build script rulat (`BS_TEST BS_OK`), si
   un crate care depinde de `quote` (exact ce "cadea") -> de asemenea OK. Cauza reala: proiectul
   fusese construit pe `/sdcard` (noexec) si copiat cu tot cu `target/` in files/tmp. Regula noua
   (3k) in prompt. Asta deblocheaza pyo3/maturin (runda anterioara le construise deja cu succes).
7. (3j) Cython/pybind11 nu sunt binare: `python3 -m cython`, respectiv headerele din
   `site-packages/pybind11/include`; launcher-ele de module se scriu acum si in `toolchain/bin`
   (agentul a listat bin/ si a raportat fals ca lipsesc).

## Etapa 77 - runda 2 de optimizari din E2E (memoria stearsa, v234 -> v235)

Rularea pe v234 a dat 152 intrari / ~12,8k tokeni (fata de 162/19,5k si 271/130k). Doua probleme
reale, ambele cu cauza gasita si reparata:

1. **Rust cu dependinte care au build.rs pica** (agentul a reconfirmat gresit "limita de executie").
   Cauza reala: `files/cargo/config` (fisierul DEPRECAT, preferat de cargo) ramasese de la o
   instalare veche cu `linker = cc-rust`; linkerul cc-rust produce un build-script pe care
   kernelul il refuza la exec ("Permission denied"), iar linkwrap.sh produce un PIE normal care
   ruleaza. Curatarea o faceam doar in `_ensure_launchers()`, dar build-urile Rust pornesc prin
   `bash` (nu cheama functia) -> configul vechi supravietuia. Fix: `_cleanup_stale_cargo_config()`
   apelat la pornirea agentului. Dovada: crate cu `quote` -> rc=0 (inainte Permission denied).
2. **pip_install pica pe pachete noi** (cmarkgfm, msgpack, ujson: "BackendUnavailable: Cannot
   import setuptools.build_meta"). Cauza: `_pip_main` lansa pip cu `sys.executable` si un
   PYTHONPATH cu `pysitepkg.zip` INAINTEA `site-packages` -> build-backend-ul pip importa
   setuptoolsul din arhiva. Fix: interpretor = lansatorul auto-suficient `files/tmp/python3` si
   PYTHONPATH in ordinea dovedita (stdlib_extra, python3.14, site-packages, pysitepkg.zip).
   Dovada: `toolchain action=pip_install msgpack` -> exit 0 in 4s.
3. Garda binar: prag mult mai conservator (a doua oara a declansat fals pe ~1.8KB de text).
4. env: nota ca PREFIX/CMAKE_ROOT sunt deja corecte si NU trebuie suprascrise.

## Etapa 78 - runda 3 E2E (de la zero, v235 -> verdict curat; `.assets_v237`)

A treia rulare de la zero (memorie + istoric sterse) pe v235: **56 intrari / ~6,2k tokeni, ZERO
erori de toolchain**, `selftest.lipsa = []`, verdict "TOOLCHAIN COMPLET pentru pip"; agentul a
terminat in 31 pasi / 2:09 (C, C++, Fortran, Rust, extensie Python nativa, Cython, cmake+ninja,
pip_install — toate compilate SI rulate, cu rezultate verificate matematic).

Evolutia pe runde de la zero: 271 intrari/~130k -> 162/19,5k -> 152/12,8k -> 110/10k -> 56/6,2k.

Verificari suplimentare pe device: `files/cargo/config` (fisierul deprecat) NU mai exista (doar
`config.toml` cu `linker=linkwrap.sh`) -> Rust cu dependinte cu build.rs merge; CFLAGS/LDFLAGS
contin deja `-L .../lib/clang/21/lib/linux` (pentru -latomic).

Singura frecare rǎmasǎ: typo-uri in scripturile de test ale agentului (string neinchis, `import
time` lipsa, flag-uri scrise de mana in loc de env). Regula noua (3l) in prompt. v237 = v235 +
aceasta regula (comportament identic al toolchain-ului).

## Etapa 79 - pornire CURATA in UI: fara linii de diagnostic (`.assets_v238`, `.assets_v239`)

Cerut de operator: sub notificarea de pornire sa nu apara linii de diagnostic, doar erorile.

- **v238:** scos `[pas2] PATH aplicat` (agent.py; varianta de EROARE ramane) si cele 6 mesaje
  `[toolchain] ...` informative din toolchain.py (libc++_shared, CA bundle, pip activat, libc++
  extras). Diagnosticul complet poate fi reactivat oricand cu `AGENT_VERBOSE=1`.
- **v239:** scos si `[key] cheie gasita - pornesc agentul.` + `[key] pornesc agentul...` /
  `[key] cheia salvata in ...` (MainActivity.kt). Raman vizibile DOAR erorile - de exemplu
  "LIPSA CHEIA DeepSeek API" cu instructiunile de lipire a cheii.

Verificat pe device (screenshot dupa fiecare instalare): ecran gol + prompt `message the agent...`.

Nota de proces: un `sed` pe MainActivity.kt a schimbat markerul `.assets_vNN` - markerul trebuie
incrementat la ORICE modificare de assets/surse, altfel aplicatia nu re-extrage materialele la
update (regula 1 din lista de siguranta).

## Etapa 80 - problemele din sesiunea cu multe erori (`.assets_v240`)

Observatie-cheie a operatorului: o parte din confuzie vine din faptul ca unealta ruleaza in DOUA
contexte (uid app vs uid 2000). Reparatii:

1. **`bg` rula prin adbsh (uid 2000) -> "cd files/tmp/rustdemo: Permission denied, EXIT=2"**, deci
   exact build-urile lungi (cargo/cmake/pip) cadeau cand agentul folosea `bg`, desi regula (2) din
   prompt il trimite acolo. Acum `bg` ruleaza implicit IN PROCESUL APLICATIEI (uid app, vede
   filesDir), cu mediu complet de toolchain (PATH cu files/tmp -> cargo isi gaseste rustc), log in
   `files/logs/bg/`, liveness/citire/kill LOCALE. adbsh rămâne doar pentru ce tine de sistem
   (`/data/local/tmp`, `run_su`, `uid=2000` explicit). Dovada: job `bg` -> binar Rust construit.
2. **Garda in `adbsh`**: orice comanda care atinge filesDir primeste un mesaj clar ("uid=2000 nu
   vede filesDir; foloseste python/bash/bg/toolchain") in loc de "Permission denied" confuz.
3. **cmake fara PREFIX**: mediul de build (PREFIX=<toolchain>/sysroot/usr, CMAKE_ROOT, TMPDIR,
   CARGO_HOME, PKG_CONFIG_PATH) e acum setat in `os.environ` la pornirea agentului, deci `cmake`
   simplu merge (inainte: 4 incercari pierdute intr-o sesiune).
4. **Instalari INCOMPLETE de pachete de build** (pathspec fara `_backends`, scikit_build_core fara
   `_compat`) rupeau `pip install lxml` cu ModuleNotFoundError, iar agentul le repara manual (~20
   pasi). Acum `_repair_build_backends()` le detecteaza prin import si le reinstaleaza curat,
   apelata automat inainte de fiecare `pip_install` (si disponibila in selftest).
5. `.rs` dat la `action=compile` primeste mesaj clar (foloseste cargo; binarul iese in
   `target/aarch64-linux-android/release/`), plus regulile (3m)/(3n) in prompt.

## Etapa 81 - stub-ul mesonpy din pysitepkg.zip rupea `pip install numpy` (`.assets_v241`)

A 5-a rulare E2E (89 intrari / ~13,6k tokeni) a scos la iveala o problema reala, noua:
`pip install numpy` cadea la "Preparing metadata (pyproject.toml)" pentru ca **`mesonpy` din
`pysitepkg.zip` e un STUB** (6 fisiere, fara hook-urile PEP 517, fara `mesonpy._project`).
Agentul a diagnosticat corect (a ajuns la `mesonpy._project` lipsa) dar a consumat ~20 de pasi.

Reparat prin `_repair_build_backends()` (rulat automat inainte de fiecare `pip_install`):
meson-python si ninja sunt verificate si reinstalate CURAT in `site-packages` (care e INAINTE de
zip in PYTHONPATH, deci copia de pe disc castiga).

Capcana de verificare (dovedita cu wheel-ul oficial): meson-python 0.22.1 NU are
`prepare_metadata_for_build_wheel` (hook mutat) si are doar 6 fisiere / 31 kB - deci criteriul de
"sănătate" e `build_wheel` prezent + `__init__.py` > 20 kB (nu lista de hook-uri).

Dovada pe device: `pip install numpy` → metadata **rc=0** in 155 s, "Would install numpy-2.5.3".

Nota de proces: `temp/` e gitignored (probele nu intra in git), dar `tools/probe_run.sh` da - si
a fost actualizat sa foloseasca ACELASI PYTHONPATH ca agentul (site-packages inainte de zip),
altfel probele vad alt mediu decat agentul si diagnoza e inselatoare.

## Etapa 82 - binarele LLVM moarte din assets (`.assets_v242`)

`assets/toolchain/bin/` continea **192 MB de binare LLVM reale** (clang-21 80 MB, lld 47 MB,
llvm-*) copiate in filesDir la instalare. In filesDir ele NU pot fi EXECUTATE (W^X, Android 10+),
deci erau simultan moarte si o capcana: agentul le chema (`toolchain/bin/clang-21`) si primea
"Permission denied" (raportat in E2E), apoi pierdea pasi diagnosticand.

- `_fix_dead_binaries()`: la fiecare pornire, numele cunoscute (clang/clang-21/clang++/clang-cpp/
  clang-format/ld.lld/lld/llvm-ar/ar/llvm-ranlib/ranlib/llvm-nm/nm/llvm-strip/strip/llvm-objcopy/
  llvm-readelf/objdump/...) sunt transformate in SYMLINK-uri catre ELF-urile din lib-ul APK-ului
  (SELinux judeca tinta, deci un symlink e executabil). Cele fara echivalent (ex. llvm-objdump) sunt
  STERSE: un "not found" e mai cinstit decat un "Permission denied" pe un binar care nu poate rula.
- Assets: `assets/toolchain/bin/` STERS (192 MB) - numele sunt recreate ca symlink-uri la pornire.
  APK-ul scade dramatic.
- Dovada pe device: 20 binare reparate; `toolchain/bin/clang-21 --version` -> rc=0, "clang version
  21.1.8".

## Etapa 83 - verificarea rularii oprite de operator (`.assets_v243`)

Sesiunea raportata avea 297 intrari / ~18,8k tokeni. Doua lucruri, de natura diferita:

1. **drum greșit auto-provocat** (cffi): ~20 de pasi incercand sa explice un esec care era de fapt
   din mediul sesiunii (env poluat / __pycache__ / cwd). Agentul a ajuns singur la concluzia corecta
   ("CFFI funcționează; eșecul de dinainte era din sesiunea mea cu env poluat") - dar tarziu.
   Regula noua (3o): daca o comanda rulata separat reuseste, suspecteaza mediul tau si ruleaza
   testul intr-un subproces curat, inainte de a sapa in biblioteca.
2. **problema reala**: meson nu putea rula sanity check-ul ("Permission denied:
   .../sanity_check_for_c.exe"). Cauza: meson foloseste `$CC` = `<toolchain>/bin/clang-21`, care
   era FISIERUL REAL de 80 MB (neexecutabil) - reparat in v242 prin `_fix_dead_binaries()`.
   Reproductie proprie: un sanity check identic compileaza (mode 0777) si ruleaza.
   Dovada dupa fix: `meson setup` rc=0 in 5s (sanity check rulat), `ninja` rc=0, binarul ruleaza ->
   MESON_OK 1.414.
3. Regula (3p): fisierele temporare in $TMPDIR (files/tmp), nu in /tmp sau /sdcard (noexec).

## Etapa 84 - ultimele binare moarte (deps/bin) + LDFLAGS + mediu complet (`.assets_v244`)

Rularea E2E pe v243 (63 intrari / 7,8k tokeni, terminata in 3 minute) a scos ultimele resturi din
familia "fisier REAL in filesDir = neexecutabil (W^X)":

1. `toolchain/deps/bin/pkg-config` si `pkgconf` erau binare REALE (501 KB) -> "Permission denied";
   `xml2-config`/`xslt-config` erau scripturi shell (la fel de neexecutabile). Fix: `_fix_dead_binaries()`
   le transforma in symlink-uri catre `libpkgconf_exec.so` (respectiv le sterge), iar din assets au
   fost scoase. Dovada: `deps/bin/pkg-config --version` -> 2.3.0.
2. **`LDFLAGS` nu continea `-L<files/libs>`** -> `-lpython3.14` dadea "unable to find library"
   (raportat in mai multe sesiuni). Acum e primul `-L`. Dovada: extensie Python compilata cu
   `-lpython3.14` -> rc=0 si se importa (`py2.sq()` = 7).
3. Regula (3e) corectata: binarul se ruleaza (a) ca subproces din python sau (b) prin linker64 -
   NU prin `sh -c` si nu din /sdcard (asa apare "Permission denied" pe un binar corect).
4. **Mediul de toolchain intra COMPLET in `os.environ` la pornire** (nu doar 8 chei): orice comanda
   pornita din `bash` (cargo, maturin, cmake, meson) vede acum exact acelasi mediu ca uneltele.
   Asta inchide clasa de probleme "unealta are mediu, bash-ul nu".

## Etapa 85 - `clang`/`clang++` isi completeaza singure flag-urile (`.assets_v245`)

Rularea E2E pe v244: **64 intrari / ~7k tokeni, ZERO "Permission denied"** (familia de binare
moarte e inchisa). Restul opririlor erau flag-uri scrise manual de agent:
`$CC t_c.c -o t_c_bin $LDFLAGS` (fara $CFLAGS) -> "fatal error: 'stdio.h' file not found", apoi
`-latomic` nerezolvat - in 3 sesiuni la rand.

Fix: `_ensure_cc_wrappers()` - `clang`/`clang++` devin lansatoare shwrap cu un `<nume>.sh` care:
- daca linia de comanda contine deja `--target=`/`--sysroot=`, executa clang-ul BRUT (deci
  cmake/meson/pip, care isi dau singure flag-urile, nu sunt afectate);
- altfel adauga singur `--target/--sysroot/-resource-dir/-I/-L` (inclusiv `-L/lib/clang/21/lib/linux`
  pentru `-latomic` si `-L files/libs` pentru libpython), iar `clang++` adauga si `-lc++_shared`.

Dovezi pe device: compilare C si C++ **fara niciun flag** -> rc=0 si ruleaza (WRAP_C 1.4142 /
WRAP_CXX 6); meson setup+ninja+run (build dir proaspat) -> MESON_OK 1.414.

## Etapa 86 - STARE LA CHECKPOINT (`.assets_v245`)

### Ce e verificat pe device (dovada, nu teorie)

| Capabilitate | Dovada |
|---|---|
| C / C++ cu STL | compileaza, linkeaza, ruleaza; chiar si FARA flag-uri (lansatoarele le completeaza) |
| Extensie Python (Python.h) | compileaza cu `-lpython3.14` (LDFLAGS are `-L files/libs`) si se importa |
| Fortran (FLANG) | prin wrapper `files/tmp/flang` (si prin `toolchain action=compile`) |
| Rust (cargo, cu si fara `build.rs`) | `cargo build --release` (si cu `--target`) -> rc=0, binarul ruleaza |
| Cython / pybind11 | extensii compilate si importate |
| cmake + ninja | configure + build + run (PREFIX/CMAKE_ROOT deja in mediu) |
| meson + ninja | `meson setup` (sanity check rulat) + ninja + run -> MESON_OK |
| pip: extensii C/C++ | ujson, cmarkgfm, msgpack, pycryptodome... `exit 0` |
| pip: numpy | metadata rc=0 (mesonpy real, nu stub-ul din zip) |
| `bg` (joburi lungi) | ruleaza IN PROCESUL APLICATIEI, vede toolchain-ul, log in `files/logs/bg` |
| executabile | symlink-uri catre lib-ul APK-ului; direct-exec din python si linker64 OK |

### Evolutia rundelor E2E "de la zero" (intrari / tokeni)

    271 / ~130k  ->  162 / 19,5k  ->  152 / 12,8k  ->  110 / ~10k  ->  63 / 7,8k  ->  64 / ~7k
    (ultimele doua: ZERO "Permission denied")

### Clase de probleme inchise in v240-v245

1. binare REALE in filesDir (assets: 192 MB LLVM + deps/bin) = neexecutabile (W^X) -> symlink-uri
   catre nativeLibraryDir / sterse; assets curatate.
2. `bg` rula ca uid 2000 -> nu vedea filesDir; acum ruleaza in-app cu mediu complet.
3. mediul de toolchain intra COMPLET in `os.environ` la pornire (bash/cargo/maturin/cmake/meson
   vad exact ce vad uneltele).
4. `LDFLAGS` fara `-L files/libs` -> `-lpython3.14` nerezolvabil.
5. pachete de build incomplete (pathspec, scikit_build_core, mesonpy-stub) -> `_repair_build_backends`.
6. `clang`/`clang++` isi completeaza flag-urile cand lipsesc.
7. configul cargo deprecat (cc-rust) curatat la pornire -> build-script-urile Rust ruleaza.
8. UI curat la pornire (doar erorile se afiseaza).

### Raman (neatinse, stiute)

- grpcio (esec la LINK), duckdb (RAM), kiwisolver.
- maturin/pyo3: proiectul trebuie construit in `files/tmp`, nu pe /sdcard (regula (3k)).
- typo-urile din scripturile de test ale agentului (regula (3l)).

## Etapa 87 - GIT compilat pe device si functional (`.assets_v246`)

Context: operatorul a cerut git ca sa poata face push la GitHub. Agentul l-a COMPILAT nativ
(git 2.47.1 + libssh2 + nghttp2, binar aarch64 de 19.9 MB) dar a raportat un "SIGSEGV in
update-ref", a declarat bug de build si a ars ~200 de pasi (sesiune de 427 intrari / ~72k tokeni).

**Verificarea mea arata ca git FUNCTIOMEAZA** - concluzia de "bug" era un artefact:
- `update-ref` pe un branch cu un BLOB refuza corect ("trying to write non-commit object") - testul
  agentului era gresit (a scris hash-ul unui fisier intr-un branch);
- verificate pe device, cu lansatorul: `--version` (2.47.1), init/add/commit/log,
  `push` catre un repo (end-to-end), **clone HTTPS de pe GitHub** (README = "Hello World!");
- singurul SIGSEGV real era chiar lansatorul meu: seta `GIT_EXEC_PATH`/`GIT_TEMPLATE_DIR`, iar cu
  ele binarul crapa (-11); cu env-ul minimal dovedit merge. Nu se seteaza.

Ce am livrat:
- `_ensure_git_launcher()`: scrie `files/tmp/git.sh` (LD_LIBRARY_PATH prefix+deps, HOME,
  GIT_SSL_CAINFO din SSL_CERT_FILE, identitate implicita pentru commit) + symlink-ul shwrap
  `files/tmp/git` (binarul brut nu se poate executa direct din filesDir). Se recreeaza la pornire.
- Regula (3q) in prompt: NU recompila git; foloseste `files/tmp/git`; push prin HTTPS cu token
  (`git push https://<TOKEN>@github.com/user/repo.git main`) - calea simpla, fara chei SSH.

## Etapa 88 - git prin SSH pe device, functional (`.assets_v247`)

Operatorul a cerut SSH si a aprobat folosirea cheii lui de pe laptop. Rezultat verificat:

- **transport**: github.com:22 si ssh.github.com:443 raspund amandoua (banner SSH-2.0 GitHub);
  known_hosts populat cu cheile reale (verificate prin fingerprint: ED25519
  SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU = cea publicata de GitHub).
- **client**: dropbear `dbclient` v2024.86 (compilat de agent pe device).
- **cheia operatorului**: copiata in `files/home/.ssh/id_ed25519_github` (chmod 600) si
  CONVERTITA in format dropbear cu `dropbearconvert` (construit pe device din sursa dropbear -
  dbclient NU citeste chei OpenSSH: "Exited: String too long").
- **dovada**: `dbclient ... git@github.com` -> "Hi fetidness! You've successfully authenticated";
  `files/tmp/git ls-remote git@github.com:fetidness/android_agent.git` -> rc=0 cu refs reale;
  clone + commit + `push --dry-run` -> rc=0 ("* [new branch] HEAD -> _probe_test").

In lansatorul `git` (`_ensure_git_launcher`): daca exista cheia in `files/home/.ssh`, se seteaza
automat `GIT_SSH_COMMAND="<prefix>/bin/dbclient -i <cheie>.db"`; conversia `.db` se face singura
daca lipseste (cu dropbearconvert). Regula (3q) spune acum ambele cai (SSH preferat, HTTPS+token
alternativ).

SECURITY: cheia privata a operatorului sta acum pe device in files/home/.ssh (chmod 600). Daca
telefonul se pierde, cheia trebuie revocata din GitHub (Settings -> SSH keys) - sau se poate revoca
si inlocui cu una generata pe device (varianta 2 din discutie).

## Etapa 89 - git durabil + reteta de reconstructie (`.assets_v248`)

Problema: git-ul si clientul SSH stateau in `files/tmp/gitbuild` (648 MB de arbore de build, fragil:
o curatare de files/tmp le pierde). Azi, dupa o reinstalare obisnuita (`adb install -r`) mergeau,
dar dupa o curatare completa nu, iar promptul spunea doar "nu recompila" - fara reteta.

Ce am facut:

1. **Locatie durabila**: `_ensure_git_toolchain()` muta esentialul (idempotent, pe fiecare piesa)
   in `files/toolchain/git/`:
   - `bin/git` (2.47.1), `bin/dbclient` (dropbear SSH), `bin/dropbearconvert` (conversie chei),
   - `lib/libnghttp2.so*` (singura librarie partajata de care are nevoie gitul la rulare;
     libssh2/libssl/libcrypto sunt statice, prin deps).
   Dovada: cu LD_LIBRARY_PATH fortat DOAR pe locatia durabila -> `git --version` si
   `git ls-remote git@github.com:fetidness/android_agent.git` merg (rc=0).
   (Capcana prinsa: o rulare partiala lasa `bin/` completat si `lib/` gol -> "CANNOT LINK
   EXECUTABLE: libnghttp2.so.14 not found"; functia e acum idempotenta pe fiecare piesa, cu lista
   explicita de librarii, fara glob.)

2. **Reteta in APK**: `assets/python/git_build_recipe.md` (ajunge pe device in
   `files/python/git_build_recipe.md`). Contine: URL-urile surselor (git 2.47.1, libssh2 1.11.1,
   nghttp2 1.64.0, dropbear 2024.86), configurile cmake/make dovedite, pasul de dropbearconvert,
   popularea known_hosts (cu fingerprint-ul de verificat) si verificarile finale. Regula noua
   (3r) trimite agentul la ea si interzice improvizatia.

3. **Cheia SSH NU intra in APK**: sta doar in `files/home/.ssh/` (chmod 600). Am verificat
   `assets/` pentru material de cheie -> gol. Reteta spune explicit regula.

Nota: arborele de build din `files/tmp/gitbuild` (648 MB) poate fi sters pentru spatiu - reteta il
reconstruieste din surse. Esentialul nu depinde de el.

## Etapa 90 - git RECONSTRUIT de la zero pe device (reteta validata) (`.assets_v249`)

Operatorul a sters tot (inclusiv copia durabila) si a cerut agentului sa compileze git de la 0.
Sesiunea (199 intrari / ~24k tokeni) a lovit aproape toate capcanele posibile. Am refacut eu
build-ul pas cu pas pana a iesit complet si am corectat RETETA din assets cu ce am invatat:

1. `/sdcard` nu permite **symlink-uri** (FUSE) -> `make install`/cmake cad acolo. Totul in filesDir.
2. `tar` (toybox) nu are **xz** -> dezarhivare cu Python (`tarfile`); nu sterge arhivele pana nu
   confirmi directoarele extrase (agentul le-a sters din greseala si a re-descarcat).
3. git 2.47.1 **nu are CMakeLists** si NU trebuie configurat: `./configure` aduce 3 teste runtime
   de cross-compilare (cache-uri manuale, ~40 de pasi pierduti). Se compileaza DIRECT cu `make`.
4. `CC`/`AR`/`RANLIB` explicite: altfel make ia `cc` -> shim-ul `cc-rust` ->
   "cc-rust: exec clang: No such file or directory".
5. Flag-uri COMPLETE in CFLAGS (`--target/--sysroot/-resource-dir`): fara ele lansatorul clang
   adauga `-I<TC>/pyinc` si git isi ia headerele Python ("object.h: unknown type name Py_ssize_t").
6. **NU pune `NO_CURL`**: in make `NO_CURL=0` = "definit" -> git fara helper-ele curl ->
   "git: 'remote-https' is not a git command". Foloseste `CURL_CONFIG` catre un script fals.
7. `NO_PTHREADS=YesPlease`: Bionic nu are `pthread_setcancelstate`.
8. libcurl cere **MD5**, dar `deps/libcrypto.a` e construit fara MD5 -> shim peste EVP +
   `-Wl,--allow-multiple-definition` (libcurl isi are propriul MD5) + `--start-group` pentru
   ordinea bibliotecilor statice (altfel "undefined symbol: X509_STORE_up_ref" / "MD5_Init").
9. `make install` cu ACELEASI variabile (altfel recompileaza cu `cc` si cade).
10. In locul durabil intra si **`libexec/git-core/*`** (helper-ul `git-remote-https`!) si
    `share/git-core/templates` - fara ele `clone https://` esueaza.
11. dropbear: `--disable-zlib` + `#define DROPBEAR_SVR_PASSWORD_AUTH 0` (Android n-are `crypt()`)
    + shim `getpass` in `src/cli-auth.c` (Bionic n-are `getpass`) + download cu User-Agent.
12. Unealta `bash` raspundea "(no output)" la comenzi fara iesire, iar agentul credea ca e rupta
    (de 7 ori intr-o sesiune) -> acum spune explicit ca a rulat OK, fara output.

Reteta completa: `files/python/git_build_recipe.md`. Driverul Python folosit pentru validare:
assets `git_build_zero_driver.py` (+ sursa in `temp/build_git_zero.py`).

DOVADA (build de la zero, azi): `git --version` 2.47.1; init/add/commit/log OK;
`clone --depth 1 https://github.com/octocat/Hello-World.git` -> rc=0, README="Hello World!";
`dbclient git@github.com` -> "Hi fetidness! You've successfully authenticated";
`git ls-remote git@github.com:fetidness/android_agent.git` -> rc=0 cu refs reale.

## Etapa 91 - DE CE disparea git-ul dupa fiecare update (cauza reala) (`.assets_v250`/`v251`)

Complaintul operatorului ("l-am pus sa compileze git de la 0") nu era (doar) despre reteta greșita:
**`extractToolchain()` din MainActivity stergea tot `files/toolchain/` la fiecare schimbare de
`.assets_vNN`**, iar git-ul construit pe device traia exact acolo (`files/toolchain/git/`). Deci
fiecare update de APK distrugea rezultatul muncii agentului - inclusiv cand el il construise corect.

Fix (acelasi pattern ca `site_packages_keep`, folosit deja pentru site-packages):
- inainte de `dest.deleteRecursively()`, `files/toolchain/git` e mutat in `files/git_keep`;
- dupa re-extragerea assets-urilor si refacerea symlink-urilor, e pus la loc;
- daca `bin/git` lipseste, se copiaza inapoi recursiv.

In plus, `_ensure_git_toolchain()` cauta acum esentialul in AMBELE locatii de build:
`files/tmp/gitbuild/prefix` (build-ul vechi) si `files/tmp/gb/prefix` (driverul nou din assets,
`git_build_zero_driver.py`) - altfel un build de la zero facut de agent nu ajungea in locul durabil.

Testul de durabilitate: doua update-uri de APK consecutive (v250 -> v251) si verificare ca
`files/toolchain/git/bin/{git,dbclient,dropbearconvert}` si `libexec/git-core` sunt inca acolo.

## Etapa 92 - optimizari din conversatia de build a agentului (339 mesaje / ~39k tokeni) (`.assets_v252`)

Am citit integral conversatia in care operatorul a cerut "compileaza-mi git si sa fie complet
functional". Git a iesit pana la urma functional, dar pe drum agentul a pierdut ~150 de pasi in
doua categorii de probleme. Le-am reparat pe amandoua.

### A. CONCLUZII FALSE DESPRE MEDIU (cauza principala, ~60 pasi pierduti)
Agentul a afirmat si apoi a construit in jurul a doua lucruri care erau FALSE:
- "SELinux blocheaza exec din filesDir" - de fapt helper-ul `git-remote-http` **ruleaza** direct din
  `files/toolchain/git/libexec/git-core` (verificat acum: rc=1 cu usage = a executat). Consecinta:
  a mutat tot git-ul in `/data/local/tmp`, a construit o a doua instalare (43 MB arhiva) si a
  PATCH-UIT binarul ca sa schimbe prefixul hardcodat (apoi l-a restaurat).
- "toybox grep nu returneaza" - de fapt `grep -n` merge perfect pe device (verificat acum).

Fix: regula noua (3s) in prompt - o concluzie de mediu se scrie DOAR dupa un test care a esuat, cu
comanda si eroarea exacta; daca vrei sa spui "X e blocat", ruleaza intai `subprocess.run([cale])`
sau `grep -n x fisier`. Regula (3b) a fost rescrisa (era absoluta: "app NU poate executa un ELF din
filesDir") - acum cere testarea intai. Regula (3t): in `bg` NU se pune pipe (log-ul iese gol - s-a
intamplat de 4 ori). Regula (3u): identitatea git / prefixul se rezolva prin config, nu prin
patcharea binarului.

### B. LUCRURI REALE, REZOLVATE ACUM IN COD
1. **SIGSEGV fara identitate git** (agentul a izolat corect: `update-ref`/`fetch`/finalul lui
   `clone` dau rc=139 fara `user.name`/`user.email`; cu identitate = rc=0). Acum
   `_ensure_git_config()` scrie `files/home/.gitconfig` (identitate, safe.directory=*, gc.auto=0,
   maintenance.auto=false, defaultBranch=main) - clasa de crash dispare.
2. **Warning-uri la fiecare comanda** ("unable to access <prefix>/etc/gitattributes", "templates not
   found"): launcherul exporta acum `GIT_CONFIG_NOSYSTEM=1` si `GIT_TEMPLATE_DIR`, iar
   `_ensure_git_toolchain()` creeaza `etc/gitattributes` gol la prefixul compilat.
3. **`(no output)`** la comenzile fara iesire (7 aparitii; agentul a crezut de mai multe ori ca
   unealta e stricata): toate cele 3 locuri rămase (bash, bg/runner, run_su) raspund explicit ca
   comanda a rulat OK.
4. **Garda adbsh** bloca si comenzi legitime care doar *mentionau* calea filesDir (ex. `strings ...
   | grep <cale>`, heredoc cu SSL_CERT_FILE): ~6 pasi pierduti reformuland. Acum blocheaza doar
   comenzile simple de acces, fara pipe/heredoc.
5. **dropbearkey** intra in pachetul durabil (generare de chei SSH pe device).
6. **Driverul din assets** (`git_build_zero_driver.py`) primeste corectiile reale descoperite de
   agent: prefix = locul durabil (fara patch de binar), `configure --host`, `sh ifndef_wrapper.sh`,
   CFLAGS cu toate `-I` + `-DLOCALOPTIONS_H_EXISTS`, dropbearkey. Reteta (12 puncte) actualizata.

