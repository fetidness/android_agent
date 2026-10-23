# CHANGELOG - Agent Android (net.sys32.agent)

> Generat automat din istoricul git. Documentul e **actualizat periodic** (la fiecare
> sesiune de dezvoltare majora; regula in `readme.md` -> OP.7). Format: zile
> descrescatoare, in fiecare zi commiturile grupate pe categorii.
> Ultimul commit inclus: `6a5af83` (2026-10-23).

### 2026-10-23 - ANDROIDAPI + BRIDGE: AGENTUL STIE CE POATE DEBIAN

> **Context:** operatorul a intrebat daca Debianul are acces deplin la Android "ca
> agentul". Cercetarea a aratat ca infrastructura exista deja (DShell bridge, 35
> comenzi + reflexie), dar `agent.py` nu o stia: descria Debianul ca "bash in Debian",
> deci raspundea incomplet ("doar dumpsys si senzori"). Sesiunea a adaugat doua
> tool-uri si a corectat documentatia din system prompt.

#### 1. Tool `androidapi` - date parsate peste uid 2000

`android_api(what=...)` cu 7 actiuni + `all`, fiecare intoarce dict, nu text brut:
`battery` (level_pct/voltage_mv/temp_c/health), `location` (fix GPS real + provideri),
`wifi` (ssid/bssid/ip/rssi_dbm/band/link_mbps/freq_mhz), `telephony`, `sensors`,
`accel`, `services`.

**De ce:** pentru o intrebare despre baterie agentul cheltuia 4-6 pasi (`dumpsys` apoi
`grep` apoi regex manual), iar la WiFi campurile `mWifiInfo` stau pe O singura linie
lunga, deci regex-ul scris manual greseste des. Acum e un pas, parsare scrisa o data.

**Masurat:** level_pct 63 / voltage_mv 4029 / temp_c 33.1, GPS 00.000000,00.000000
acc 12.77 m alt 74.93 m, wifi `MyWifi` -51 dBm 5180 MHz 5 GHz 1200 Mbps,
29 senzori, 470 servicii.

#### 2. Tool `bridge` - acces la reflexia arbitrara prin DShell

`run_bridge_tool(action, expr)`: orice comanda DShell, iar `action=eval` primeste
`expr` = expresia de reflexie. Verificat:
`{"op":"call","target":"ctx","method":"getSystemService","args":["wifi"]}` ->
`android.net.wifi.WifiManager` (obiect real).

Helper nou `bridge_call()` cu port auto-detectat (`ANDROID_BRIDGE`, `filesDir`,
`filesDir/home`, workspace) si **reconnectare o singura data** daca aplicatia s-a
repornit pe alt port.

#### 3. `agent.py` stie acum ce poate Debian (TOOLGUIDE + descriere `terminal`)

Bloc nou in TOOLGUIDE si in descrierea tool-ului `terminal`: Debian-ul **nu e orb la
Android**, are bridge complet, cu cifrele masurate si cu ce ramane imposibil. Fara
asta agentul subestima mediul si nu folosea bridge-ul.

#### 4. Corectii de integrare (4 puncte, nu unul)

Tool-urile noi au fost inregistrate in **toate** locurile: lista `T` (descrierea pentru
model), `_call_tool_inner` (dispatcher-ul REAL al apelurilor), `sandbox` (pentru
`run_code`) si TOOLGUIDE. Descoperit: agentul are **doua** dispatchere; un tool
inregistrat doar in `sandbox` merge in scripturi dar intoarce GOL la apel direct.

#### 5. Capcane dovedite in aceasta sesiune

- `dumpsys battery | head -12` **trunchiaza** output-ul (pipe inchis inainte de
  `level:`) -> intoarce doar `Max charging voltage: 0`. Fara `head`: 12015 B, complet.
- `TOOLGUIDE` e un TUPLU de stringuri care se inchide cu `")` pe ULTIMA linie; o linie
  adaugata cu `,)` da `TypeError: can only concatenate tuple (not "str") to tuple`.
- Editarea `agent.py` pe linii (6300+) a produs de 3 ori
  `SyntaxError: '(' was never closed` -> foloseste `str.replace` cu text verbatim.
- Procesul agentului tine codul VECHI in memorie: dupa modificare tool-ul da GOL
  desi `py_compile` trece. Nu depana codul - cere RESTART.
- `app_process` din uid 2000: `Error changing dalvik-cache ownership: Operation not
  permitted` (ART face chown, CapEff=0) -> cod Java propriu in shell imposibil.

#### 6. Ce ramane imposibil din Debian (granite, nu bug-uri)

- `/data/data/<alta.aplicatie>` (SELinux `shell:s0` vs `app_data_file`)
- `CapEff = 0` -> fara capabilitati de kernel
- root: nu exista `su`, build `user` (`ro.secure=1`)

#### Fisiere

- `assets/python/agent.py` - `android_api()`, `run_androidapi_tool()`, `bridge_call()`,
  `run_bridge_tool()`, blocuri noi in TOOLGUIDE si in descrierea `terminal`
- `assets/python/android_full.py` - client Python pentru bridge (nou)
- `assets/python/memory.md` + `assets/memory.md` - lectiile sesiunii
- `docs/debian-binder/PLAN_DEBIAN_ACCES_DEPLIN.md` - planul celor 4 cai, cu cercetarea
  masurata (app_process blocat, bridge deja existent)

### 2026-10-23 - UI SETUP + FIX-URI CRITICE DE PORNIRE (instalare curata)

> **Context:** sesiune de test E2E pe device dupa reinstalare la rece. Operatorul a
> raportat, pe rand: "liniile se sterg singure la configurare", "agentul isi da restart
> singur", "agent keep stopping", "dupa cheia API nu se intampla nimic", "[done] apar
> toate deodata si in ordine gresita". Fiecare s-a dovedit un bug real, distinct.

#### 1. `MainActivity.kt` - ecran de configurare dedicat (inlocuieste countdown-ul in terminal)

**Inainte:** 5 blocuri de text rosu scrise in terminal + `lastLine()` apelat de 31 ori
la fiecare secunda. `lastLine()` **stergea fizic ultima linie** din
`SpannableStringBuilder` si o rescria -> text care se zbatea, fara ierarhie.

**Acum:** panou propriu peste terminal, cu:
- titlu `AGENT` + subtitlu `First-time setup` + mesaj rosu `Please wait, take a coffee and relax...`
- `ProgressBar` orizontala legata de permisiunile acordate (7 = 100%)
- lista de permisiuni cu bifa LIVE (`○` -> `✓`), reimprospatata la 700 ms
- linie de status: `Waiting for N permission(s) - Xs` / `All permissions granted - starting...`
- secțiune `STARTUP` cu etapele reale: `Environment`, `Libraries`, `Bridge`, `Agent`
- fiecare etapa apare O SINGURA DATA si isi schimba doar starea (fara stergeri)

**Blocaj obligatoriu de permisiuni** (cerut de operator): la expirarea ferestrei de 30 s
fara toate permisiunile, setup-ul **NU porneste**. Apare `WARNING: N permission(s) not
granted. Setup CANNOT start until ALL are granted: ...` plus butonul
`GRANT ALL PERMISSIONS`, care reia cererile pana cand toate sunt acordate. Daca o
permisiune e refuzata definitiv (`USER_FIXED`), a doua apasare deschide Setarile aplicatiei.

#### 2. `MainActivity.kt` - `pyhome` se construieste in `extractAssets()`

**Bug:** stdlib-ul Python (`pyhome/lib/python3.14`) se construia DOAR in
`startPythonProcess()`, gate-uit de `pythonLaunching`. Daca prima incercare esua, `pyhome`
nu exista niciodata, iar setup-ul raporta toate etapele ca "ok" fara stdlib pe disc.
Simptom: dupa introducerea cheii API, toate bifele verzi si nimic altceva.

**Fix:** stdlib-ul se construieste sincron in `extractAssets()`, cu copiere
fisier-cu-fisier (`cpTree`), verificare de completitudine (`threading.py`, `encodings/`,
`os.py`), rename atomic si marker `.stdlib_ok` scris ULTIMUL.

#### 3. `MainActivity.kt` - `pyhome` nu mai e sters la fiecare `extractAssets()`

**Bug:** `File(filesDir,"pyhome").deleteRecursively()` rula la FIECARE apel, iar
`extractAssets()` e chemat si din `startCore()` (prima configurare) si din ramura
`setupDone()` (fiecare pornire). Python pornea din `pyhome`, apoi al doilea
`extractAssets` il stergea sub picioare -> proces mort -> watchdog -> bucla infinita
de restarturi ("agentul isi da restart singur").

**Fix:** se sterge doar cand lipseste efectiv `threading.py`.

#### 4. `MainActivity.kt` - crash `AssertionError` in `extractToolchain`

```
FATAL EXCEPTION: Thread-3
java.lang.AssertionError: rootDir must be verified to be directory beforehand.
  at kotlin.io.FileTreeWalk$DirectoryState.<init>
  at kotlin.io.FilesKt__UtilsKt.deleteRecursively
  at MainActivity.extractToolchain(MainActivity.kt:1525)
```
`deleteRecursively()` **arunca** (nu returneaza) cand directorul nu exista. Toate cele
3 locuri sunt acum protejate cu `runCatching { if (dest.isDirectory) ... }`.

#### 5. `MainActivity.kt` - garda anti-duplicare pentru procesul Python

3 procese Python simultane (fiecare cu worker de terminal si conexiune adb proprie),
pentru ca `onResume` si `runSetup` chemau amandoua `startPythonProcess`.
Fix: `@Volatile pythonLaunching` + eliberare in `finally`; `runSetup` idempotent prin
`runSetupStarted`; `readyAnnounced` ca "Ready." sa apara o singura data.

#### 6. `MainActivity.kt` - `onCreate` cheama `startCore()` necondiționat

**Bug:** `startCore()` se chema doar daca toate permisiunile erau deja acordate. La o
instalare curata nu sunt -> ecran gol pana nimerea `onResume` o stare buna
("a durat 2 minute pana a aparut ready").

#### 7. `MainActivity.kt` - watchdog gardat

Watchdog-ul anunta `[watchdog] procesul Python lipseste` la 45 s, **inainte** ca
extractia stdlib-ului (1688 fisiere) sa se termine. Acum nu raporteaza cat timp
`!setupDone()` sau `pythonLaunching < 180 s`.

#### 8. `agent.py` + `proot_tool.py` - setup Debian: progres live, o singura rulare

**Probleme raportate:** toate `[done]` apareau deodata la sfarsit, unele inainte de
header, si `[done] Android service access` se repeta in bucla.

**Cauze:** (a) `ensure_ready_via_adb` e sincron, deci bucla care emitea pasii rula dupa
terminarea lui; (b) setup-ul putea porni din 3 fire simultan; (c) bucla de `steps`
emitea din nou tot ce `_LIVE_CB` scrisese deja.

**Fix:**
- `proot_tool._LIVE_CB`: callback global prin care `L()` scrie in terminal in momentul
  in care pasul se termina
- garda `_SETUP_RUNNING` + `_SETUP_LOCK`: un singur setup simultan, al doilea apel iese
- header-ul (`Setting up the Linux environment`) se scrie PRIMUL, inainte de orice munca
- eliminata bucla duplicata de emitere
- eliminat ticker-ul `still working, N minute(s) elapsed`
- mesaj final: `READY !` + linie goala + `Everything is ready. You can use the terminal now.`
- header-ul instruieste explicit: `It takes a few minutes. WAIT until you see READY - do not type anything.`

#### 9. `LinuxTerminalActivity.kt` - setup Debian la deschiderea terminalului

**Cerut de operator:** configurarea Linux sa porneasca DOAR dupa apasarea butonului
TERMINAL, nu automat dupa pornirea agentului, si nu la prima comanda (care oricum
esua cu `proot_exec.so: inaccessible or not found`).

**Fix:** `onCreate` scrie `[setup] configuring the Linux environment, please wait...` si
trimite comanda `setup` in `term_in.txt` dupa 700 ms. Auto-startul din
`_terminal_file_worker` a fost eliminat.

#### 10. `agent.py` - `saveKeyAndStart` porneste setup-ul complet

Dupa salvarea cheii API, `runSetupStarted` se reseteaza si procesul Python porneste
direct (inainte, al doilea `runSetup()` iesea imediat din cauza garzii de idempotenta).

#### 11. `agent.py` - setup Debian nu mai rescrie tot fluxul daca mediul e deja configurat

**Raportat de operator:** "dupa ce mediul linux s-a configurat si inchidem terminalul si
intram iar, apare iar ca ready, everything is ready. ar trebui sa afiseze doar READY".

**Cauza:** `_run_terminal_setup_locked()` scria header-ul (`Setting up the Linux
environment` + instructiunile de "first run" + `WAIT until you see READY`) la FIECARE
deschidere a terminalului, indiferent daca `.debian_ready` exista deja.

**Fix:** prima verificare a functiei e acum existența markerului - daca mediul e deja
configurat, se scrie o singura linie `READY` si se iese imediat.

---

### 2026-10-22 - PERFORMANTA: adb_client, proot batching, aliniere terminal_server

> **Context:** sesiune de optimizare pornita din intrebarea "ce mai putem optimiza?".
> Rezultatul principal NU a fost o optimizare de flag-uri, ci un BUG gasit prin masurare.

#### 1. `adb_client.py` - comenzi tacute (CASTIG 30x)

**Bug:** `shell()` presupunea ca `r == ""` = socket desincronizat si facea
`close() + connect() + re-executie`. Dar o comanda care se termina CU SUCCES si nu
produce output returneaza legitim "".

**Cost real (inainte):**
- `true` : 485 - 1963 ms
- `cat /dev/null` : 609 ms
- `printf ''` : 721 ms
- `echo x` (are output) : 42 - 54 ms
=> fiecare comanda tacuta declansa reconectare TCP + AUTH RSAPUBLICKEY.

**Fix:** `_shell_locked()` seteaza `self._last_rc_ok = (not timed_out)`, iar `shell()`
reconecta DOAR daca `not _last_rc_ok`.

**Rezultat (dupa):** `true` = 41 ms (de la 1226 ms = **30x**), `cat /dev/null` = 43 ms,
comenzi reale (mkdir/touch/ls/id/rm) = 47-87 ms, proot /bin/true = 127 ms (de la 616 ms).

#### 2. `terminal_server.run_batch()` - mai multe comenzi intr-un proot (23x)

**Descoperire:** costul unei comenzi NU e proot si NU e exec-ul, ci pornirea procesului
+ un round-trip adb (~110 ms). Toate flag-urile proot sunt irelevante:
`-0`/fara (542 vs 597 ms), `--kill-on-exit` (592), `--sysvipc`/fara (571 vs 582),
`--link2symlink` (582), bind-uri zero vs toate (689 vs 625), minimal doar `-r` (615).

**Masuratori (1 proot cu N comenzi):** n=1 -> 114 ms/cmd, n=20 -> 4.2 ms/cmd,
n=50 -> 2.8 ms/cmd, n=100 -> **1.7 ms/cmd**.

**Comparativ cu un proot per comanda:**
- n=2  : 186 vs 440 ms   => **2.4x**
- n=5  : 224 vs 1031 ms  => **4.6x**
- n=10 : 164 vs 1792 ms  => **11.0x**
- n=20 : 167 vs 3901 ms  => **23.4x**
Output verificat IDENTIC la fiecare rulare.

**API:** `run_batch(["cmd1","cmd2",...])` -> lista de stringuri. Delimitare cu nonce
uuid. Robust la comenzi care esueaza, output cu newline, comenzi goale, exit codes.

#### 3. `terminal_server.run_in_debian` - aliniat cu `agent.py`

Functia exista in DOUA locuri, divergente. Varianta slaba avea 3 lipsuri reale:
1. fara `--bind=/storage` -> `/sdcard` si `/storage` dadeau "No such file" (fisierul
   exista pentru uid 2000)
2. fara `DEBIAN_FRONTEND=noninteractive` -> `apt install` fara -y bloca pana la timeout
3. fara transmitere base64 -> adbd sparge comanda pe spatii, argv iese greșit

Fix: aceleasi bind-uri, aceleasi variabile, comanda prin base64
(`echo <b64> | base64 -d | /bin/bash`). `run_batch` primeste aceleasi setari.

#### 4. PROOT_NO_SECCOMP - corectie de documentatie

Prima versiune a raportului afirma "+21% la exec". **FALS** - compara doua COMENZI
diferite, nu doua valori ale variabilei. Remasurat corect (200x /bin/true, 4 rulari,
mediane): 8654 ms cu vs 8620 ms fara = **zgomot** (controale identice variate
1501-2266 ms). Variabila TOTUSI opreste acceleratorul (dovada: cu ea dispare
`proot info: ptrace acceleration (seccomp mode 2) enabled` din PROOT_VERBOSE=1),
dar castigul masurabil e ZERO. Lasata setata (inofensiva), documentata ca inutila.

#### Ce NU a mers

- `mkfifo` in /data/local/tmp -> "Permission denied" (SELinux). Imposibil.
- Sesiune proot persistenta cu polling pe fisier -> functioneaza, dar adauga 40-110 ms
  latenta de polling, deci NU bate batch-ul nativ.
- Fisiere in /data/local/tmp ca canal -> procesul app NU poate scrie acolo (SELinux);
  canalul trebuie sa fie /storage (FUSE).
- proot NU vede /storage fara `--bind=/storage` explicit.

#### Lectii

- O functie duplicata in doua fisiere DIVERGHEAZA. Verifica intotdeauna care e cea
  folosita efectiv, inainte de a o repara pe cea aparenta.
- Nu declara o optimizare pe baza unei singure masuratori: compara ACEEASI comanda,
  cu controale, si verifica varianta intre ele.


### 2026-10-21 (e) - SETUP AUTOMAT: instalarea APK = mediu complet functional

> **Cerut de operator:** "aplicatia instalata de la 0 trebuie sa fie complet
> functionala" si "cand deschid prima data terminalul, sa porneasca setupul".

#### Ce se intampla acum

Dupa `adb install` + prima deschidere a TERMINALULUI, sistemul isi instaleaza
singur tot ce ii lipseste, o singura data (~3-5 minute), si scrie progresul
**exclusiv in terminal**, in engleza, fara coduri ANSI (nu se randeaza):

```
Setting up the Linux environment
------------------------------
This is the first run, so the system installs what
it needs.
It takes a few minutes. Please wait until you see
DONE.
The terminal stays open; each step is listed as it
finishes.

  [done] Linux filesystem
  [done] Linux runtime
  [done] Compiler toolchain
  [done] Android service access

DONE
Everything is ready. You can use the terminal now.
```

Comanda `setup` in terminal reia doar pasii lipsa (idempotent, flag
`files/.debian_ready`).

#### Cele 5 cauze reale ale esecurilor anterioare (fiecare dovedita pe device)

1. **`extractAssets()` copia doar `assets/python`.** `assets/binder` (sursa C,
   `bctl-android`, `install_binder.sh`) si `assets/skills` nu ajungeau
   NICIODATA pe device. La instalare curata agentul nu avea nici documentatie,
   nici installer, deci isi scria un client binder nou de la zero - cu offseturi
   gresite - si raporta "0 din 25 servicii".
2. **Erau DOUA `memory.md`** in assets: cel bun in radacina si unul vechi (690 B,
   doar antetul) in `assets/python/`. `copyDir("python")` il aducea pe cel vechi,
   deci toate lectiile despre binder se pierdeau.
3. **Aplicatia nu poate execve din `app_data_file`** (W^X SELinux): o copie a
   lui `echo` din rootfs in `files/tmp` da "No such file or directory" la exec,
   desi fisierul exista si e `-rwxr-xr-x`. `/data` NU e montat noexec - restrictia
   e SELinux.
4. **Aplicatia nu poate scrie in `/data/local/tmp`** (`drwxrwx--x shell shell`):
   `PermissionError` la `makedirs`. Doar uid 2000 (adbd) poate -> setup-ul se
   executa prin `adb_client`, nu direct.
5. **Terminalul chema `/data/local/tmp/libproot_exec.so`**, dar setup-ul
   instaleaza binarul ca `proot_exec.so` -> ORICE comanda din Debian esua cu
   "inaccessible or not found".

#### Alte bug-uri reparate

- AGP **dezactiveaza compresia** la ambalare: pe device ajunge
  `trixie-arm64.tar` NECOMPRIMAT, iar codul folosea `tar -xzf` -> "zcat: not gzip".
  Acum detectia se face pe magic bytes (gzip / zstd / tar simplu).
- Extragerea rootfs-ului pica la final din cauza nodurilor `/dev` (mknod fara
  root) si a hardlink-urilor din `/usr/bin`; acum sunt tolerate daca structura
  `bin/ etc/ usr/` exista (`/dev` e oricum legat de la gazda).
- `debian_binder.c`: `selftest` nou (numara accesibile / lazy / refuzate SELinux),
  handle citit corect (`0x80000001` = null din parcel, NU handle), buffer de reply
  256 KB (lista se trunchia la ~80 din 467), nume de serviciu pana la 256 caractere.
- Validarea de la pasul binder era gresita (cerea "android-binder" in output, dar
  scriptul se termina cu `selftest`) -> raporta fals "install failed".

#### Masuratoare reala (SM-A366B, Android 16, instalare curata)

```
din aplicatie (untrusted_app): 467 servicii, handle package=1 display=2 power=3
  call display 1 -> status=0, 1736 bytes (DisplayAddress$Physical, QCM)
  call power 5   -> status=-1 "Neither user N nor current process has
                    android.permission.DEVICE_POWER"  (eroare reala a sistemului)
din Debian (u:r:shell:s0): android-binder selftest
  servicii listate 467 | getService REUSIT 212 | lazy 3 | refuzate SELinux 251
```

~350 servicii sunt **lazy** (`activity`, `window`, `notification`,
`SurfaceFlinger`, `stats`, `media.*`): se inregistreaza in servicemanager abia
cand le cere un client din framework. Un esantion din ele da "0/N" si pare ca
binder-ul e stricat - de aceea exista acum `selftest`.

#### UI

- subtitlu fereastra principala: `Type /help` (inainte se trunchia)
- caseta de input din terminal: fara hint-ul "uid 2000 - scrie o comanda..."

### 2026-10-21 (d) - BINDER IN-PROCESS: agentul apeleaza serviciile Android direct

> **Cerut de operator:** "vreau sa implementam binder si tie direct ca agent pe
> android. sa fii la fel de capabil precum debian."

#### Rezultat

Agentul din aplicatie are acum acces Binder **nativ**, fara adb, fara bridge si
fara proot: deschide `/dev/binder` direct in procesul aplicatiei.

```
list            -> 468 servicii
check package   -> found
iface display   -> android.hardware.display.IDisplayManager
handle power    -> handle=2
call display 1  -> status=0, 1736 bytes (QCM, DisplayAddress$Physical, ...)
```

#### Ce s-a adaugat

- `assets/python/android_binder.py` - client Binder in-process (clasa `Binder`)
- `agent.py`: tool nou **`binder`** (list/check/handle/iface/call/raw), in schema,
  in dispatch, in `run_code` si in lista `_UNTRUSTED`
- `BINDER_INPROCESS.md` - documentatia modulului

#### Descoperiri (dovedite in aplicatie, u:r:untrusted_app)

- `untrusted_app` POATE deschide `/dev/binder`, `mmap` pana la 1 MB si vorbi cu
  servicemanager (pid 1000) - nu are nevoie de uid 2000
- `errno=11` (EAGAIN) la `BINDER_WRITE_READ` NU e eroare: inseamna "nimic de citit
  inca" si trebuie tratat ca `(0,0)` cu reincercare (altfel pica tot)
- bufferele trimise trebuie tinute vii (lista `_keep`) pana la sfarsitul
  tranzactiei, altfel GC-ul le colecteaza si kernelul citeste gunoi
- `checkService` intoarce status=0 si pentru servicii inexistente; diferenta e
  `offsets_size == 0`
- ordinea `ACQUIRE -> INCREFS -> FREE_BUFFER` ramane obligatorie

#### Fisiere modificate

`workspace/app/.../assets/python/agent.py` (adaugat tool `binder`),
`workspace/app/.../assets/python/android_binder.py` (nou).

---

### 2026-10-21 (c) - BINDER nativ: Debian vorbeste direct cu serviciile Android

> **Cerut de operator:** "implementeaza la nivel de debian ca el sa comunice cu
> acest binder. si el sa aiba acces complet la servicii."

#### Rezultat

Debian-ul (proot) apeleaza acum **nativ** serviciile Android prin `/dev/binder`,
fara bridge si fara procesul aplicatiei:

```
android-binder list | wc -l      -> 468  (identic cu /system/bin/service list)
android-binder iface display     -> android.hardware.display.IDisplayManager
android-binder aidlcall display android.hardware.display.IDisplayManager 1
                                 -> status=0x0, date reale
```

Din Python (modul global): `import binder; b = binder.Binder(); b.call("display", 1)`

#### Ce s-a adaugat

- `assets/binder/debian_binder.c` - client Binder nativ glibc (gcc din Debian)
- `assets/binder/binder.py` - modul Python (list / check / handle / iface / call)
- `assets/binder/install_binder.sh` - instalare in `/opt/android-binder` + symlink
- `assets/binder/bctl-android` - clientul Android echivalent (istoric)
- `DEBIAN_BINDER.md` - protocolul complet, offseturi verificate prin ptrace

#### Descoperiri tehnice (toate dovedite pe device)

- binarul Android NU ruleaza din Debian (libc incompatibil) -> compilare nativa glibc
- `setgid` INAINTE de `setuid(2000)`, altfel EPERM in proot; fara setuid SELinux
  refuza `binder_call` (proot da uid 0, contextul ramane `shell:s0`)
- secventa obligatorie inainte de primul apel:
  `BC_ACQUIRE` -> `BC_INCREFS` -> `BC_FREE_BUFFER` -> `INTERFACE_TRANSACTION` -> apel
  (daca FREE_BUFFER vine inainte de ACQUIRE/INCREFS nu mai vine niciun reply)
- `flags = 0x10` (TF_ACCEPT_FDS) obligatoriu; `code` la off 16, `data_size` la off 32
- descriptorul AIDL se obtine cu `iface`, nu se ghiceste
  (ex: serviciul `mount` are `android.os.storage.IStorageManager`)
- padding `vector<String16>`: la multiplu de 4, dar STRICT mai mare daca e deja aliniat
  -> 468/468 servicii identice cu `service list`

#### Limitari (SELinux, context shell:s0)

- `EX_SECURITY` pe media.*, stats, surfaceflinger, connectivity
- servicii lazy (activity, window, notification): `getService` intoarce null

---

---

### 2026-10-21 (b) - DShell BRIDGE integrat in agent.py + paritate 100%

> **Cerut de operator:** "fa toate modificarile necesare pentru ca aplicatia sa fie
> stabila atunci cand o reinstalam sau o compilam din codul sursa. integreaza bridge
> in agent si tot ce mai trebuie."

#### Ce s-a schimbat fata de versiunea (a)

`dshell_bridge.py` (proces separat, rulat manual cu `bg`) a fost **ABSORBIT in `agent.py`**.
Nu mai exista proces separat, deci nu se mai poate desincroniza la rebuild si nu mai
depinde de un `bg` pornit manual.

#### Integrare in agent.py

| Functie | Rol |
|---|---|
| `_dshell_port()` | portul: `DSHELL_BRIDGE_PORT` sau 46500 |
| `_dshell_serve(port)` | accepta conexiuni, thread daemon |
| `_dshell_client(conn)` | un client Debian: linii JSON in/out |
| `_dshell_handle(req)` | dispatch: ping / sh / debian / eval / orice tool |
| `_dshell_eval(expr)` | reflecție Java via `android_bridge.call("eval")` |
| `_start_dshell_bridge()` | pornire idempotenta (flag) |
| `_install_dshell_client()` | self-heal client in rootfs |
| `_start_dshell()` | ambele, chemat din blocul de startup |

Pornirea se face in `if __name__ == "__main__":`, **dupa** ce `LD_LIBRARY_PATH` e scris
in `ld_path.txt` si dupa `_start_terminal_worker()`.

#### Stabilitate la rebuild / reinstalare (cerinta principala)

1. **Idempotent** - `DSHELL_BRIDGE_STARTED` impiedica dubla pornire.
2. **Porturi alternative** - daca 46500 e ocupat de o instanta veche, incearca
   46500..46519 si scrie portul REAL. (Reparat dupa ce s-a constatat ca `bind` eșua
   silentios si bridge-ul murea fara sa scrie `dshell.port`.)
3. **Portfile in 2 locuri** - `files/tmp/dshell.port` (agentul) si
   `workspace/dshell.port` (Debian, prin bind `/sdcard`).
   `/data/local/tmp/dshell.port` a fost incercat dar **eșueaza** din procesul app
   (uid app nu are acces acolo) - nu e critic, `/sdcard` acopera cazul.
4. **Client self-heal** - `_install_dshell_client()` rescrie `dshell.py` in rootfs la
   fiecare pornire, cu comparare de bytes (nu scrie degeaba). Rootfs-ul traieste in
   `/data/local/tmp` (in afara APK), deci supravietuieste reinstalarii; doar clientul
   se resincronizeaza.
5. **`DSHELL_PORT` injectat** in `run_in_debian()` prin `env -i`, deci orice comanda
   Debian vede portul corect fara sa-l caute.

#### Paritate 100% cu tool-urile agentului

Bridge-ul expune **orice** tool, nu doar `sh`/`debian`/`eval`. `_dshell_handle()` trateaza
orice `cmd` necunoscut ca nume de tool si il deleaga la `android_bridge.call(cmd, action, **params)`.

Tool-uri testate din Debian: `ui` (read/find/click), `notif`, `ime`, `sensors`, `location`,
`battery`, `camera`, `apps`, `settings`, `system`, `storage`, `processes`, `network`,
`display`, `audio`, `telephony`, `wifi`, `nfc`, `usb`, `clipboard`, `notify`, `vibrate`,
`tts`, `volume`, `device`, `intent`, `appinfo`, `capture`, `vpn`, `guard`.

#### Bug-uri prinse in testare

- **`action` trimis greșit**: era pus in `params` in loc de argument pozitional la
  `android_bridge.call(tool, action, **params)` -> `ui read` returna `null`.
- **Cheia de raspuns**: tool-urile intorc `text` (ui), `data`, `result`, sau chei proprii
  (system -> `model`). Handler-ul accepta acum toate formele.
- **`OSError: I/O error`** la coada `evalq/` pe `/sdcard` (MediaProvider). Rezolvat prin
  **eliminarea cozii** - reflecția se face direct, suntem in procesul aplicatiei.

#### Teste end-to-end din Debian (rulate)

```
dshell ping                             -> pong
dshell eval "2+3"                       -> 5
dshell eval '{"op":"call","target":"ctx","method":"getPackageName"}' -> net.sys32.agent
dshell sh "id -u"                       -> 2000
dshell sh "getprop ro.product.model"    -> SM-A366B
dshell sh "pm list packages"            -> 416 pachete
dshell sh "settings put system screen_brightness 100"  -> aplicat (13 -> 100)
dshell ui '{"action":"read","max":10}'  -> arborele UI real
dshell ui '{"action":"find","text":"TERMINAL"}' -> buton gasit la [937,209], clickable
dshell sensors '{"action":"list"}'      -> LSM6DSV Accelerometer, MXGX300 Magnetometer
dshell battery '{"action":"full"}'      -> nivel, temperatura, tensiune
dshell system '{"action":"model"}'      -> SM-A366B, bootloader A366BXXU5BYK5
dshell display '{"action":"info"}'      -> 1080x2340, 450 dpi, 120 Hz
dshell debian "uname -r"                -> 6.1.0-debian
```

#### Limite reale (aceleasi, dovedite)

UNIX socket-uri, `/dev/net/tun`, `iptables`, root real de kernel. `getSerial` da
`SecurityException` - si pentru agent, deci nu e o diferență intre noi.

---


### 2026-10-21 - DShell BRIDGE: Debian vorbeste cu Androidul (TCP localhost)

> **Cerut de operator:** "cum putem lega debian complet de tine... adica prin debian sa
> poti sa faci absolut tot ce poti face tu ca agent."

#### Problema

Rootfs-ul Debian ruleaza in `/data/local/tmp` (context SELinux `shell_data_file`). Din acel
context, **UNIX socket-urile sunt interzise** - orice cale:

```
safesocket.Listen: listen unix /root/x.sock: bind: permission denied
safesocket.Listen: listen unix /var/run/tailscale/tailscaled.sock: bind: permission denied
```

Dovedit cu teste A/B: `socket.bind()` da `PermissionError` pe `/root`, `/var/run`,
`/data/local/tmp` si `/sdcard`; merge DOAR in `app_data_file`
(`/data/data/net.sys32.agent/files/`), unde Debian nu are acces.

Consecinta: daemonii care cer UNIX socket (tailscaled, containerd) nu pot porni din Debian.
Tailscale s-a putut INSTALA (1.104.2, 23 s, repo oficial), dar nu s-a putut PORNI.

#### Solutia: TCP pe localhost

TCP **nu** este blocat de SELinux. Dovedit:

```
python3 -c "socket.bind(('127.0.0.1',41999))"  ->  BIND_OK
```

Deci puntea este un server TCP care ruleaza **in procesul aplicatiei** (unde exista SDK
Android + `adb_client`) si pe care Debian il cheama.

#### Ce s-a livrat

| Componenta | Rol |
|---|---|
| `assets/python/dshell_bridge.py` | server RPC in procesul aplicatiei (port 45900) |
| `assets/python/dshell.py` | client pentru Debian (`/usr/local/bin/dshell`) |
| `dshell.port` (in workspace) | descoperirea portului: serverul scrie, clientul citeste |
| `evalq/` (in workspace) | coada JSON pentru reflecție Android, scriere atomica |

#### Protocol

O linie JSON per cerere, o linie JSON raspuns:

```
{"cmd":"ping"}                       -> {"ok":true,"out":"pong"}
{"cmd":"sh","arg":"id -u"}           -> {"ok":true,"out":"2000\n"}
{"cmd":"debian","arg":"uname -r"}    -> {"ok":true,"out":"6.1.0-debian\n"}
{"cmd":"eval","arg":"2+3"}           -> {"ok":true,"out":"5"}
```

#### Teste end-to-end (rulate din Debian, prin punte)

```
dshell ping                             -> pong
dshell eval "6*7"                       -> 42
dshell sh "id -u"                       -> 2000
dshell sh "getprop ro.product.model"    -> SM-A366B
dshell sh "pm list packages | head -3"  -> package:com.sec.android.RilServiceModeApp ...
dshell sh "dumpsys battery"             -> date complete baterie
dshell debian "uname -r"                -> 6.1.0-debian
```

#### Detalii de implementare

- **Worker permanent** pentru `evalq/`: `eval_worker()` porneste automat in
  `serve_forever()`, scaneaza la 50 ms si goleste coada singur (fara intervenția agentului).
- **Scriere atomica** a raspunsului: `.tmp.<base>` + `os.rename()` - cititorul nu prinde
  niciodata un fisier pe jumatate scris. (Bug prins in testare: prima versiune facea
  `open().read()` dupa ce serverul scrisese deja, si prindea fisier gol.)
- **Auto-heal ADB**: `_sh()` verifica `is_socket_healthy()` si reconecteaza inainte de
  fiecare comanda (altfel `AttributeError: NoneType has no attribute sendall`).

#### Ce NU poate face puntea (limite reale, dovedite)

- creare UNIX socket-uri -> daemonii care le cer ramin imposibili
- creare TUN din Debian -> dar aplicatia il poate crea prin `VpnService` si Debian il VEDE
  (`tun0`, IP real, prin kernelul comun)
- `iptables` -> `could not get iptables version: exit status 1`
- root real de kernel (`uid=0` in proot este cosmetic; procesul real e uid 2000)

#### Capcana importanta

`ip route add ... dev tun0` rulat din Debian a returnat **`RC=0`** dar ruta **nu exista**
in kernel (`ip route | grep -c` -> 0). Proot raporteaza succes pentru operații pe care nu
le poate face. **Nu te increde in exit code-urile din Debian pentru operații de retea.**

---


### 2026-10-20 - TERMINAL LINUX REAL IN APLICATIE (Debian 13 arm64 nativ, proot)

> **Cerut de operator:** "vreau sa fie doar terminal... in terminal vreau sa vad real date
> ca intr-un terminal adevarat... agentul are acces complet la debian si poate rula comenzi
> linux in terminal cu privilegii uid 2000."
> S-a renuntat COMPLET la GUI (VNC/LXDE/LXQt) - operatorul nu va folosi desktop grafic pe telefon.

#### Ce s-a livrat

| Componenta | Rol |
|---|---|
| `assets/python/terminal_server.py` | wrapper `run_in_debian()` (fost server de pty, acum deprecat - vezi mai jos) |
| `assets/python/agent.py` | tool nou `terminal` (status/run/open) + `_terminal_file_worker()` |
| `LinuxTerminalActivity.kt` | UI terminal: tab-uri multiple, camp de scris, bara de taste |
| `TerminalClient.kt` | canal UI <-> agent prin fisiere in `files/tmp` (zero socket) |
| `assets/proot/debian_x.sh` | pornire sesiune X11 (pastrat din etapa GUI) |
| rootfs Debian 13.7 | `/data/local/tmp/debian` (273 MB, 286 binare, extins in afara APK) |

#### ARHITECTURA (dovedita pe device)

```
UI (Kotlin)  --scrie-->  files/tmp/term_in.txt
                              |
                        agent.py: _terminal_file_worker()
                              |
                        adb_client.shared().shell()   <-- aici se face execve-ul
                              |
                        adbd (uid 2000, u:r:shell:s0)
                              |
                        proot -0 -r /data/local/tmp/debian
                              |
                        bash in Debian 13.7  /  /system/bin/sh (uid 2000)
                              |
UI (TextView) <--citeste-- files/tmp/term_out_<sid>.txt
```

#### 5 CAPCANE REALE, FIECARE CU DOVADA

1. **`/data/data` este montat `noexec`** (gasit de agentul de pe device):
   ```
   tmpfs /data/data tmpfs rw,seclabel,nosuid,nodev,noexec,relatime,mode=751
   ```
   Consecinta: rootfs-ul NU poate sta in `files/debian` daca vrem sa rulam binarele lui.
   Fix: rootfs mutat in **`/data/local/tmp/debian`** (nu e noexec pentru uid 2000).
   *30 de teste au fost pierdute cautand in LD_LIBRARY_PATH si SELinux inainte de a verifica `mount`.*

2. **`untrusted_app` nu poate `execve` nimic din `app_data_file`** (SELinux W^X):
   ```
   proot error: execve("/usr/bin/env"): Permission denied
   ```
   Fix: executia trece prin **`adb_client.shell()`** - adbd face execve-ul ca uid 2000
   (`u:r:shell:s0`), nu procesul aplicatiei. Nu e workaround, e singura cale fara root.

3. **`adb_client.shared()` moare dupa ~1 min de inactivitate** (gasit de agentul de pe device):
   ```
   AttributeError: 'NoneType' object has no attribute 'sendall'
   ```
   Fix: verificare IEFTINA a starii socket-ului inainte de fiecare apel (`s is None`, `fileno() < 0`).
   ATENTIE: `is_socket_healthy()` NU se foloseste - trimite un `echo` de test la fiecare apel =>
   2 comenzi ADB per comanda => lentoare de 10 s si dialog "Allow USB debugging" repetat.

4. **adbd sparge comanda pe spatii** in `shell,v2,raw:<cmd>`:
   ```
   /system/bin/sh: -u: inaccessible or not found     (din "sh -c id -u")
   ```
   Fix: comanda trece ca **base64** - `echo <b64> | base64 -d | sh` (o singura bucata, fara spatii).

5. **nonce-ul de re-executare ajungea in comanda**:
   ```
   /system/bin/sh: <stdin>[3]: 1792526111.2433681: inaccessible or not found
   ```
   Fix: worker-ul citeste **exact 3 linii** (flag / sid / comanda); linia a 4-a e nonce si se ignora.

#### Ce a fost eliminat

- `VncClient.kt`, `DesktopActivity.kt`, biblioteca `vernacular-vnc` (62 fisiere Java),
  10 clase shim `java.awt` - GUI complet scos.
- `terminal_server.py` ca proces separat (nu putea face proot: noexec + W^X).
- LXDE/LXQt/X11 din rootfs (~1.1 GB eliberat).

#### Ce NU se poate (dovedit)

| Limitare | Cauza |
|---|---|
| `nano`, `vim`, `htop` interactive | adbd nu trimite input in sesiunile `shell,raw`/`v2` (promptul apare, tastele nu ajung); `mkfifo` e refuzat in `/data/local/tmp` |
| pty real in aplicatie | `pty.fork()` moare la execve (W^X); `pty.openpty()` + proot nu se leaga |
| GPU nativ (`/dev/dri/renderD128`) | `Permission denied` chiar si pentru uid 2000 (context `graphics_device`) |

#### Ce functioneaza (testat pe device)

```
uid2000:~$ id -u                    -> 2000
uid2000:~$ getprop ro.product.model -> SM-A366B
uid2000:~$ pm list packages | wc -l -> 416

root@debian:~# cat /etc/debian_version -> 13.7
root@debian:~# ls /usr/bin | wc -l      -> 286
root@debian:~# apt --version | head -1  -> apt 3.0.3 (arm64)
```

**Detectie automata** (`DEBIAN_HINTS` in `run_in_debian`): `apt`, `python3`, `nano`, `git`, `make`
ruleaza automat in Debian; `pm`, `dumpsys`, `getprop`, `settings`, `am` ruleaza pe uid 2000.
Deci `apt install nano` scris in modul uid2000 merge (inainte dadea
`/system/bin/sh: apt: inaccessible or not found`).

#### UI terminal

- tab-uri multiple (`+` = sesiune noua, `/exit` = inchide tab, ultimul tab inchide ecranul)
- camp de scris VIZIBIL deasupra barei de taste (inainte era 1x1 px invizibil)
- bara de taste redusa la `CTRL` `TAB` `ESC` (eliminate F1-F12 si sagetile: inutile fara pty)
- output-ul apare pe linie noua, cu linie goala intre comenzi
- padding pentru bara de status (tab-urile nu mai stau sub ceas)

---

### 2026-10-20 - GUI VNC (INCERCAT SI ABANDONAT)

Etapele GUI au fost implementate si **dovedite functional** inainte de a fi scoase la cererea
operatorului (nu va folosi desktop grafic pe telefon). Pastrate aici ca istoric si ca lectii:

- **proot compilat cross** (NDK 29, `-mcpu=cortex-a76+crypto`); NDK 27 e RUPT (clang-18 => SIGSEGV).
- **Debian 13.7 arm64** rulat nativ prin proot (zero emulare): `uname -s` -> Linux, `uid=0`.
- **Benchmark**: overhead proot ~11% intr-un proces (bucla 20k: 0.10s vs 0.09s);
  `PROOT_NO_SECCOMP=1` NU ajuta.
- **GUI complet**: Xtigervnc + fluxbox/LXDE, client VNC scris de la zero, apoi `vernacular-vnc`.
- **LXQt NU functioneaza**: pachetul Debian `lxqt-panel 2.1.4` nu contine plugin-urile de baza
  (`libtaskbar.so`, `libmainmenu.so`, `libworldclock.so`) - desi livrara fisierele `.desktop`.
  Recompilat din sursa 2.1.4 => plugin-urile sunt STATICE in binar (`STATIC_PLUGINS`), deci
  `libtaskbar.so` nu exista nici dupa build. Panelul functioneaza cu binarul recompilat.
- **LXDE functioneaza** (openbox + lxpanel + pcmanfm), necesita `dbus-daemon --session` manual.

---


---

### 2026-10-16 (f) - ADB: UN singur dialog Allow + conexiuni fantoma curatate

> **Observat de operator:** „cand pornesc aplicatia la rece... ma intreaba direct sa ii dau allow.
> ii dau allow, apoi ii zic agentului sa isi testeze conexiunea uid 2000 si iarasi ma intreaba.
> abia a 2-a oara se salveaza allow-ul pe sesiune."

**Cauza 1 - timeout prea scurt (dovedit): `_recv(10)`** in `Adb.connect()`. Aprobarea umana poate
lua 30-60 s; la expirare `shared()` reconecta, iar FIECARE reconnect deschidea un dialog NOU.
Fix: `_recv(120)` + `_auth_left = 1` (3 incercari nu ajutau, agravau dialogul).

**Cauza 2 - HANDSHAKE NESERIALIZAT (cauza reala a celor 2 Allow-uri):** `shared()` NU era sub
`_SOCK_LOCK`, deci doua thread-uri care o chemau simultan la pornire (a11y_selfheal + primul tool)
vedeau amandoua `_SHARED is None` si deschideau CATE O CONEXIUNE -> doua dialoguri. Dovada pe
device: prima conexiune ramanea `ESTABLISHED` cu 44 B necititi (handshake abandonat) = FANTOMA.
Fix: tot `shared()` (inclusiv `connect()`) e acum sub `_SOCK_LOCK`, prin `_shared_locked()`.
Verificat: 4 thread-uri simultane -> `fd-uri distincte: {4}` = UN singur handshake.

**Cauza 3 - conexiuni fantoma:** un socket cu date in queue dar fara raspuns (handshake abandonat)
NU e "viu" desi `select()` zice ca are date; refolosirea lui otravea comanda urmatoare.
Fix: la reutilizare, daca are date in queue face un `ping()` REAL si, daca nu raspunde, il inchide
CURAT si deschide altul (nu-l lasa in ESTABLISHED).

**Cauza 4 - a11y_selfheal pornea al doilea handshake:** acum cere `shared(auto=False)` - refoloseste
conexiunea existenta si NU deschide una noua la startup (un Allow consumat inutil, cand operatorul
nu e atent).

**Rezultat:** la pornirea la rece -> UN singur dialog Allow; apoi toate comenzile (adbsh, a11y,
orice) folosesc aceeasi conexiune.

**Investigatia conexiunii "neobisnuite" raportate de agent (10.0.0.1 -> 10.0.0.2:7777/7780)**
- NU e malware: `10.0.0.2` e un **P-CSCF** (server IMS) al operatorului. Dovada din `dumpsys`:
  `PcscfAddresses: [10.0.0.2, 10.0.0.3]`, APN `ims` CONNECTED pe `rmnet_data8`,
  operator Telenor DK (MCC 238/MNC 02) prin Lebara. Porturile 7777/7780 = trafic VoLTE/IMS normal.
- "Neobisnuit" doar aparent: SIM1 e OUT_OF_SERVICE dar sesiunea IMS ramane activa (comportament
  normal cand VoLTE e inregistrat pe celalalt slot / IWLAN).

---

### 2026-10-16 (e) - ACCESIBILITATE: auto-reparare COMPLETA prin adb local (fara operator)

> **Intrebat de operator:** „daca agentul nu are adb deschis... cum reactioneaza? iar daca are acces,
> la fiecare pornire incearca sa isi deschida accesibilitatea? ca eu trebuie sa ii dau mereu
> allow cand se conecteaza prin adb".

**Descoperirea cheie:** agentul ARE deja `adbsh` (shell uid=2000, poate `pm grant`), iar
`files/op_adbkey` (cheia operatorului, deja autorizata in adbd) face ca `AUTH_SIGNATURE` sa fie
acceptata INSTANT - fara dialogul „Allow USB debugging". Deci reparatia completa e posibila
in-app, nu doar prin Kotlin (care NU poate da `pm grant`: o aplicatie nu-si poate acorda singura
o permisiune speciala).

**Nou - `a11y_selfheal()` in `agent.py`:** rulata la startup, in ACELASI thread de fundal ca
self-heal-ul, DUPA el. Daca adb local raspunde (127.0.0.1, portul din `service.adb.tcp.port`):
(1) acorda `WRITE_SECURE_SETTINGS` daca lipseste, (2) adauga serviciul in
`enabled_accessibility_services` + scrie `ACCESSIBILITY_ENABLED=1`. Fara adb: tacut, fara blocaj.

**Kotlin (`MainActivity.ensureAccessibility`):** NU mai afiseaza mesajul de alarmare
„WRITE_SECURE_SETTINGS is not granted" cand exista `op_adbkey` (Python-ul repara singur 20 s mai
tarziu); mesajul rămâne doar cand chiar nu exista nicio cale automata (si include acum hint-ul
cu copierea cheii).

**Verificare pe device (test dur, ambele scenarii)**
- Fara acces: revocat tot -> pornire -> a11y OFF, app porneste normal, mesaj clar cu `pm grant`.
- Cu acces: revocat `WRITE_SECURE_SETTINGS` + a11y oprit -> pornire app ->
  **auto-reparat ambele**: permisiunea granted, serviciul BOUND, fara dialog „Allow".
- `a11y_selfheal()` a raportat: `['granted WRITE_SECURE_SETTINGS', 'service enabled']`.
- APK construit cu Gradle local (compileDebugKotlin + assembleDebug), instalat cu aceeasi cheie.

**LIMITARE onesta:** `files/op_adbkey` (cheia autorizata) trebuie pusa O SINGURA DATA de operator
(`/data/misc/adb/adb_keys` nu poate fi citit fara root, deci agentul nu si-o poate face singur).
Dupa aceea persista peste update-uri (`pm install -r` nu sterge files/) si nu mai e nevoie de nimic.

---

### 2026-10-16 (d) - AUTO-REACTIVARE ACCESIBILITATE la pornire (Kotlin)

> **Cerut de operator:** „de IME nu ma intereseaza. dar putem pune auto-activare accesibilitate?"

**Problema (frecție reala, raportata de agent):** la FIECARE reinstalare de APK, Android reseteaza
permisiunile speciale -> `enabled_accessibility_services` devine null, iar `AgentAccessibilityService`
nu se mai leaga. Efect: agentul pierde screenshot-ul si controlul UI. Agentul l-a reactivat MANUAL
de 3 ori intr-o singura sesiune.

**Fix (MainActivity.kt):** functia NOUA `ensureAccessibility()`, apelata in `startCore()`:
- idempotenta: daca `instance != null`, nu atinge nimic;
- daca lipseste `WRITE_SECURE_SETTINGS` (permisiune speciala, acordata o data cu `pm grant`),
  NU incearca si scrie pe ecran instructiunea exacta cu `pm grant` -> operatorul stie ce sa faca;
- altfel: citeste lista `ENABLED_ACCESSIBILITY_SERVICES`, adauga `pkg/cls` daca lipseste
  (lista e separata prin ':'), scrie `ACCESSIBILITY_ENABLED=1`, apoi raporteaza pe ecran.

**Fix (AndroidBridge.kt):** `settings()` suporta acum si actiunea `set` (Secure/Global/System),
cu refuz explicit pentru cheia de accesibilitate (Android o protejeaza; se foloseste doar
`ensureAccessibility()`), pentru ca bridge-ul avea doar `get|open`.

**Verificare (pe device, test dur)**
- Dezactivat a11y (`enabled=0`, `services=null`) -> pornit app -> **auto-reactivare**: `enabled=1`,
  lista repopulata, `dumpsys accessibility` arata serviciul **BOUND**.
- Ecran: `[a11y] accessibility re-enabled automatically (added to list)`.
- Fallback testat: permisiune revocata -> a11y rămâne OFF (NU crapa), se afiseaza instructiunea.
- APK construit LOCAL cu Gradle 8.11.1 + SDK din `/home/gab/Work/Android` (nu doar repack):
  `compileDebugKotlin` + `assembleDebug` = BUILD SUCCESSFUL; instalat cu aceeasi cheie.

---

### 2026-10-16 (c) - TOOLCHAIN: Rust reparat complet + self-heal acopera rustc

> **Cerut de operator:** „citeste conversatia agentului android. a intampinat o problema cu rust"
> apoi „agentul raporteaza ca heal nu acopera si rust".

**Rust - reparație reala (fisierul lipsea fizic din APK)**
- Cauza: `assets/toolchain/rust-libs.tar` era TRUNCHIAT (264 MB / 184 fisiere, `tar: Unexpected
  EOF`), fara `librustc_driver-3ed50e27f892bfb5.so` si `libLLVM.so.21.1`. `rustc` e doar un
  wrapper de 7 KB (`librustc_exec.so`) care are nevoie de driver -> "CANNOT LINK EXECUTABLE".
- Surse gasite: `agent-full-backup.zip` de pe HDD-ul extern (`/media/gab/STOCARE1`) continea
  arhiva COMPLETA de 840 MB / 344 fisiere. Compatibilitate verificata: `librustc_exec.so` avea
  acelasi md5 (`f2731fb8...`) in ambele APK-uri, deci hash-ul cerut se potrivea exact.
- Fix: arhiva completa inlocuita in assets, APK reconstruit fara Gradle (repack + zipalign +
  semnare cu acelasi debug keystore), `pm install -r` = Success, re-extragere automata la
  pornire (mecanismul de semnatura (size,mtime) din `toolchain._ensure_rust`).

**rustc exec direct (regresie introdusa de wrapper-ul de script, reparata)**
- `rustc` pus ca SCRIPT shell in filesDir NU e executabil de untrusted_app (noexec pe shebang):
  `cargo` face `exec` DIRECT pe el -> "could not execute process `rustc -vV` ... Permission
  denied (13)". Selftest-ul trecea (il invoca prin `sh`), deci era un FALS VERDE periculos.
- Fix: acelasi tipar ca la clang/flang/cython - launcher ELF `libshwrap_exec.so` + logica in
  `rustc.sh` + binarul real in `rustc-bin`. Aplicat IDENTIC in `files/tmp/` SI `toolchain/bin/`.
- Bug ascuns gasit la testare: `made.append(...)` folosit in `_ensure_rust` (variabila exista
  doar in `_ensure_launchers`) -> `NameError` prins de `except: pass`, deci TACUT, oprea
  executia inainte de crearea `toolchain/bin/rustc`.

**Self-heal acopera acum rustc (lacuna raportata de agent)**
- Agentul a testat: a rupt `rustc`, a rulat `heal` -> "nothing to repair" desi era rupt.
  Verificarile de launcheri existente NU includeau rustc.
- Invariant NOU `("rust_launcher", ...)` in `selfheal.py`: check IEFTIN (stat/readlink, fara
  subprocess) pe cele 4 cai; semnaleaza `missing` / `dead link` / `rustc is a script`.
  Fix = `toolchain._ensure_rust()`. Faze: startup, build, error, full.

**Verificare (teste reale pe device, nu declarative)**
- `rustc --version` -> 1.98.1; `cargo build` -> binar rulat OK; selftest 18/18.
- Testul dur al agentului reprodus: rupt `rustc` (script) -> heal -> `repaired: ['rust_launcher']`,
  `unresolved: []`; rupt ambele cai + repornire app -> reparate AUTOMAT la startup.
- UI: `[self-heal] OK - environment healthy (8 checks, 39 ms)`, fara `UNSOLVED: rust_launcher`.

---

### 2026-10-16 - contorul de SESIUNE corect + footer compact (ambele agenti)

> **Cerut de operator:** „verifica agent-linux.py de ce imi scrie session tok ↑29.74M ... cand eu
> abia am pornit sesiunea", apoi „vreau sa fie afisat DOAR pentru sesiunea curenta deci cand dau
> /reset ar trebui sa o ia de la 0", apoi „fa footerul mai mic pe android ca e scrisul prea mare".

**Bug gasit si reparat - `session tok` arata totalul ISTORIC, nu sesiunea**
- In `agent-linux.py`, `_task_foot()` citea cifra din `_ins_load()` (`insights.json`), adica
  ledgerul persistent cumulat din 15 octombrie (29.79M), nu sesiunea curenta. Aparea un total
  enorm chiar la prima comanda dupa pornire. Eticheta „session" era deci mincinoasa.
- Fix: footer-ul foloseste acum `SESS` (contorul real al sesiunii, acumulat in
  `print_usage_compact`). In `agent.py` (Android) footer-ul era deja corect - nu avea bug-ul.

**Contorul de sesiune supravietuieste repornirii, dar /reset il aduce la zero (NOU)**
- Persistenta in `insights.json` sub cheia separata `"session"` (ledgerul istoric rămâne intact).
- `_sess_save()` / `_sess_load()`: salvate la fiecare runda, restaurate la pornire
  (`SESS.update(_sess_load())`). In `agent.py` incarcarea ruleaza DUPA definirea helperilor
  (INSIGHTS_FILE e mai jos in fisier decat SESS) - altfel `NameError`.
- `/reset` face `SESS.update(...)` + `_sess_save()`: zero in memorie SI pe disc.

**Footer compact, wrap-safe (NOU)**
- Pe ecran de telefon fontul monospace de 15sp incape ~34-38 caractere; footer-ul pe un rand
  (122 caractere) se rupea haotic. Acum: header pe rand propriu + `tok` / `sess` pe randuri
  aliniate (`#1 done`, `tools`, `rnd`, `tok`, `sess`). Fiecare rand <= 36 caractere.
- Linie goala intre footer si prompt. Aplicat IDENTIC in `agent-linux.py` si `agent.py`.

**Verificare**
- Ambele fisiere: `py_compile` OK; test end-to-end (restart -> supravietuieste; `/reset` ->
  zero; ledger istoric intact dupa ambele).
- Android: APK reconstruit fara Gradle (repack `assets/python/agent.py` + zipalign + semnare cu
  acelasi debug keystore `68244d4c...`), `pm install -r` = Success, verificat VIZUAL pe Samsung
  SM-A366B (capturi): footer pe 3 randuri, ZERO rupere, `session` persistat in `insights.json`.

**Curatenie**
- `insights.json` scos din git (`git rm --cached`) si adaugat in `.gitignore`: e ledger de
  consum scris la fiecare runda, nu cod - nu are ce cauta in istoric.

---

### 2026-10-15 (b) - `agent.py` OPTIMIZAT: mod SAFE, zavor pe partitii de sistem, anti-evaziune

> **Cerut de operator:** „am inlocuit acel fisier cu altul optimizat ... fa git push", apoi
> „pe baza acestora, modifica readme.md si changelogs.md apoi faci din nou push".

**Commit `f4f72b4`** - `agent.py` inlocuit cu versiunea optimizata (91 linii adaugate, 48 sterse,
5197 linii total), plus `insights.json` rescris de runtime.

**Siguranta scrierilor (principalul)**
- `WRITE_DENY_SYSTEM` (NOU): refuza scrierea in `/system`, `/vendor`, `/etc`, `/proc`, `/sys`,
  `/dev/block`, `/data/system`, `/data/misc`, `/data/adb`, `/apex`, `/product`, `/odm`, `/boot` -
  verificare pe `realpath`, deci symlink-urile nu ocolesc zavorul.
- Anti-evaziune (NOU): `_WRITE_VAR_RX` + `_SENSITIVE_HINT` prind scrierile pe cale CONSTRUITA
  din variabila care ating nume sensibile (`.ssh`, `.aws`, `.gnupg`, `.kube`, `.docker`, `.azure`,
  `.netrc`, `.gitconfig`, `.git-credentials`, `.npmrc`, `.bashrc`, `.profile`, `id_rsa`,
  `id_ed25519`, `id_ecdsa`, `authorized_keys`, `known_hosts`, `credentials`, `.config/gh|gcloud|pip`).
- Mod SAFE (NOU): `SAFEMODE`/`SAFEC`/`UNSAFEC`. Implicit SAFE = scrierea refuzata si HARDLINE
  neexecutat, mesaj `[SAFE] write REFUSED to ... - type /unsafe to override` (galben 220). Dupa
  `/unsafe`, comanda HARDLINE ruleaza cu linie de audit rosie `[UNSAFE] HARDLINE ALLOWED` (rosu 203).
  DANGEROUS ramane pe avertisment + audit, fara refuz.

**Curatenie**
- Sters codul mort `_compact_history_DISABLED()` (32 linii, pastrat "for reference only" si
  niciodata apelat) si duplicatul `GUARD_ACTION=[None,""]`; comentariul reflecta acum realitatea.
- `agent.py`: mod 644 -> **755** (executabil).

**Verificare**
- `059453b..f4f72b4  master -> master`; local HEAD = remote HEAD = `f4f72b4`.
- Clone proaspat: `sha256 88c7e56e...a8e34` identic cu fisierul local - versiunea de pe server
  este exact cea optimizata.

---

### 2026-10-15 - OPTIMIZARI DIN HERMES: cost -6x, 12 capabilitati noi, UI engleza, rebuild de la zero

> **Cerut de operator:** (a) „sa te imbunatatesti iar ca inspiratie sa ai agentul hermes de la nous
> research ... vreau sa fii la fel de inteligent precum hermes"; (b) „avem o problema grava: la
> fiecare task se fac pasi foarte marunti si de fiecare data contextul este trimis si retrimis si
> avem un cost ENORM de tokens"; (c) „nu sunt multumit cand apare `+-- step 09 [python] runs python
> agent.py` ... eu nu stiu exact ce ai facut alea 3 minute"; (d) „toate mesajele UI din aplicatia
> android sa fie in engleza"; (e) „sterge complet aplicatia de pe android ... apoi fa rebuild".

**Research Hermes.** Clonat `NousResearch/Hermes-Agent` (~9.400 fisiere .py = 262 MB), extras
**toate** cele 41.321 de simboluri (functii/clase), filtrat inteligenta portabila vs infrastructura
(gateway, MCP, plugin-uri, SQLite `hermes_state_*` 54 module, TUI, ~20 adaptoare de provideri -
declarate explicit in afara scopului). Invariant pastrat: **un fisier, zero dependinte**.

**A. Cost de tokeni: 29 runde -> 5 runde (masurat pe device).**
- ghidare noua `FEWER, BIGGER STEPS` (portata din `PARALLEL_TOOL_CALL_GUIDANCE`): planifica inainte,
  batch in acelasi turn, `run_code` pentru lanturi, `delegate` pentru investigatii laterale;
- `run_tool_calls`: executie PARALELA pentru tool-uri read-only (4 citiri in 1.01s, nu 4s),
  serializata pentru cele cu efecte; ordinea rezultatelor pastrata;
- footer corectat: `N tool calls / M rounds` (rounds = cereri la model = multiplicatorul de cost).

**B. 12 capabilitati noi, pe ambii agenti:** `tool_guardrails` (bucla de tool), `file_safety` +
`spill_safety`, `approval_detection` (hardline/dangerous), `todo`, recovery hints, `run_code` (PTC),
`delegate` (subagenti, batch paralel), `@`-references, `curator`, `moa`, `insights`, overflow
recovery. Pastrate din sesiunea anterioara: disciplina de executie, skills + `skill(name)`,
auto-learn, autoskill, redactare secrete, sanitizare mesaje, truncare.

**C. UI pasi concreti.** `describe_step()` extrage din codul propriu al pasului: comanda shell
exacta, procesul rulat, `read/wrote <fisier>`, host-ul URL, tool-urile chemate de un script PTC;
fallback = codul insusi. O singura linie per pas (fara randuri `↳`), nota de timp inline peste 5s.

**D. UI in engleza.** 19 mesaje Python + 12 Kotlin + 1 `strings.xml` traduse. Verificat 0 româna in
UI (4 straturi). Raman in româna doar comentariile/docstring-urile.

**E. Test end-to-end:** `pm uninstall` -> `gradle clean` + `assembleDebug` (40s, 35/35) -> APK 716 MB
-> `pm install -r` pe telefon gol -> `AGENT FULLY CONFIGURED AND OPERATIONAL` -> 3 taskuri reale
reușite (inclusiv **`delegate` cu 2 subagenti paraleli**, 7 tool calls / 2 rounds).

**Capcane reale reparate:** (1) `agent.py` sters accidental la curatenie cu glob -> recuperat din
`agent-linux.py`; **regula noua: backup explicit inainte de modificari, curatenie doar pe nume
exacte**; (2) `hashlib` neimportat -> guard-ul detecta fals bucle; (3) `/skill` spart la ambele cand
s-a scos `/pin` (cod orfan dupa `continue`); (4) regex redirect fara `/`; (5) 4 erori de acolade ->
rezolvate cu `json.dumps`; (6) `INSIGHTS_FILE` mutat in `HOME_DIR`; (7) `SKILLDIR` folosit inainte de
definire. **Plus:** la prima instalare, cheia API veche (`****9592`) din backup a dat Authentication
Fails - rescrisa cheia corecta in `key.txt`.

### 2026-10-08 (4) (mesaje in ENGLEZA + self-heal vizibil IMEDIAT la deschidere, in fundal)

> **Cerut de operator:** (a) „doresc sa fie in engleza toate mesajele"; (b) „as dori ca atunci
> cand deschidem agentul sa fie afisat un mesaj gen ca self healing e in progress si sa
> asteptam apoi porneste self-heal"; (c) „a aparut foarte greu ca self heal e in progress.
> trebuie sa apara exact dupa ce deschidem agentul apoi self heal in fundal sa ruleze".

**(a) Traducere completa a mesajelor in engleza** (toate fisierele Python: `agent.py`,
`toolchain.py`, `selfheal.py`, `android_build.py`, `adb_client.py`, `build.py`, `jsengine.py`,
`jsfetch.py`, `scraper.py`, `websearch.py`, `adb_setup.py`): linii de ecran, rezultate de unelte,
diagnostice, descrieri de tool-uri si **ghidul modelului** (`ANDROID_GUIDE` / MISSION RULES,
regulile 3a-3v, 4a, 4b). Renumeri pentru consistenta: coduri de diagnostic
(`rust_lipsa`→`missing_rust`, `umbrire_site_packages`→`shadowed_site_packages`, ...), chei
`toolchain.selftest()` (`lipsa`→`missing`, `detalii`→`details`, `ram_liber_mb`→`ram_free_mb`, ...),
chei `selfheal` (`reparate`→`repaired`, `nereparabile`→`unresolved`, `faza`→`phase`, ...),
etichete (`pasi:`→`steps:`, `reparat:`→`repaired:`). Raman in romana DOAR docstring-urile,
comentariile, regexurile interne de detectie a formularii si documentatia repo-ului.

**(b)+(c) Self-heal vizibil IMEDIAT + in fundal.** Problema: mesajul de progres venea din procesul
python, care porneste abia DUPA extragerea assets (zeci de secunde) -> operatorul nu vedea nimic si
credea ca aplicatia s-a blocat.

* `MainActivity.startCore()`: linie albastra **INSTANT la deschidere** (inainte de orice munca
  grea): `[self-heal] in progress, please wait - checking the environment (launchers, packages,
  toolchain)`. Verificat pe device: apare in ~2 s de la `am start`.
* Heal-ul de la pornire ruleaza **in FUNDAL**, intr-un thread daemon: promptul e disponibil
  imediat. Ca sa nu existe cursa intre un task si reparatii, `call_tool` asteapta terminarea lui
  (`_SELFHEAL_DONE.wait(60)`, de obicei < 1 s).
* Python-ul NU mai afiseaza linia de progres la startup (`show_progress=False`) - mesajul vine din
  Kotlin, deci nu se dubleaza; linia de progres cu timp scurs rămâne pentru `pip_install`,
  hook-ul de eroare si `/heal`.
* Rezultatul (python, colorat): `[self-heal] OK - 1 repaired in 305 ms: shadowed: pathspec,
  scikit_build_core,setuptools_scm` (verde) / `OK - environment healthy (7 checks, 33 ms)` (gri) /
  `UNRESOLVED: ...` (rosu).

**Build:** schimbarea din Kotlin cere un build gradle complet (`:app:assembleDebug`, ~2-3 min cu
cache-ul cald), nu doar repack de assets - APK-ul rezultat contine si assets-urile actualizate si
e semnat cu debug keystore-ul corect (`ANDROID_USER_HOME=/home/gab/.config/.android`).

**Verificat pe SM-A366B:** la 2 s dupa deschidere pe ecran: `[self-heal] in progress, please wait
- checking the environment (launchers, packages, toolchain)`; la ~42 s (dupa extragere + pornirea
python): `[self-heal] OK - 1 repaired in 305 ms: shadowed: pathspec,scikit_build_core,setuptools_scm`.

### 2026-10-08 (3) (self-heal: feedback pe ecran — linie live + rezultat colorat)

> **Cerut de operator:** „ar fi indicat sa arate pe ecran ca ruleaza procesul de self-healing
> … ca sa stim ca ruleaza ceva si ca se vindeca singur. sa scrie cu rosu sau cum crezi?"

**Decizie de design:** **rosu NU** — la noi rosu = eroare, iar vindecarea nu e o eroare (daca
scriem rosu cand merge, culoarea isi pierde sensul exact cand conteaza). Schema aleasa:
albastru = ruleaza, VERDE = a reparat, gri discret = nimic de reparat, ROSU = a rămas rupt
(`NEREZOLVAT`, adica o problema reala).

* `_selfheal_visible(phase, label)`: linie LIVE rescrisa in loc (`\r` + `\33[K`, exact mecanismul
  spinner-ului) cat timp ruleaza, stearsa la final ca scrollback-ul sa nu se umple; apoi o linie
  de REZULTAT care rămâne, colorata dupa rezultat. Ambele pe ECRAN -> 0 tokeni.
* Ruleaza la `startup`, la `pip_install` (faza build), in hook-ul de eroare si la `/heal`.
* `_safe_print`: text ASCII + fallback pe ASCII la `UnicodeEncodeError` — stdout-ul aplicatiei
  poate fi ASCII-only, iar un singur `\u27f3`/`\u2713` ar fi aruncat si linia ar fi DISPĂRUT
  silentios (exact capcana pe care am prins-o in test).
* Daca heal-ul insusi cade, eroarea se afiseaza (`[self-heal] EROARE: ...`) in loc sa fie
  inghitita: un heal mut e mai rau decat unul zgomotos.
* Comanda noua **`/selfheal`** (0 tokeni): stinge/aprinde linia „mediu sanatos"; reparatiile si
  `NEREZOLVAT` se afiseaza mereu.

**Verificat pe device (SM-A366B):** dupa update de APK -> `[self-heal] OK - 1 reparate in
307 ms: umbrire: pathspec,scikit_build_core,setuptools_scm` (verde); repornire fara update ->
`[self-heal] OK - mediu sanatos  (7 verificari, 33 ms)` (gri discret). Textul a fost confirmat
si prin `uiautomator dump` (nu doar din screenshot).

### 2026-10-08 (2) (self-heal la nivel de aplicatie: registru de invariantе, 0 tokeni)

> **Context:** dupa fix-ul umbririi (`2026-10-08 (1)`) operatorul a cerut extinderea
> auto-heal-ului la TOT nivelul aplicatiei, cu o conditie explicita: **sa nu consume tokeni
> permanent inutil**.

**De ce era necesar:** in `toolchain.py` existau deja 27 de functii de reparare dovedite
(`_ensure_launchers`, `_fix_dead_binaries`, `_ensure_pipconf`, `_patch_sysconfig_device`,
`_fix_ca_bundle`, `_ensure_git_config`, `_ensure_python_launcher`, ...) dar fiecare era chemata
ad-hoc, din alt loc; unele doar la `action=fix`, deci DOAR daca modelul avea inspiratia sa ceara
repararea. Nimic nu garanta ca ruleaza dupa un update de APK (care schimba
`nativeLibraryDir` si re-extrage assets) -> simptomul aparea ca „unealta lipseste/defecta", iar
modelul ardea 20-40 de pasi (fiecare cu tot contextul re-trimis) ca sa descopere o reparare care
exista deja in cod.

**Fix: `assets/python/selfheal.py` — registru de invariantе.** Fiecare invariant are `check()`
ieftin (doar `stat`/`readlink`/listare; fara subprocess, fara retea) si `fix()` idempotent care
reutilizeaza functiile din `toolchain.py`. Fix-ul ruleaza DOAR daca check-ul gaseste ceva rupt,
apoi check-ul e re-rulat: daca problema nu a disparut, invariantul e raportat o singura data ca
`NEREZOLVAT` si apoi tace (nu scriem aceeasi linie la fiecare pornire).

* 11 invariantе: `launchers` (linkuri moarte/nativeLibraryDir schimbat), `umbrire` (copii
  trunchiate care umbresc `pysitepkg.zip`), `directoare`, `ld_path` (stub-uri NDK in
  `LD_LIBRARY_PATH` = SIGSEGV in orice copil), `ca`, `pyexe` (`sys.executable` cu hash de APK),
  `git_identity` (fara ea `update-ref`/`fetch` = SIGSEGV), `pip_conf`, `sysconfig` (cai de
  laptop), `piese` si `chei_adb` (faza full).
* 4 faze: `startup` (la fiecare pornire, ~300 ms), `build` (inainte de `pip_install`, raportat
  in `pasi:` ca `heal:<invariante>`), `error` (automat, vezi hook-ul), `full`
  (`toolchain action=heal`).
* **HOOK in `call_tool`** (`agent.py`): orice rezultat de tool trece prin
  `looks_like_launcher_break()` (semnale STRICTE: `Permission denied` pe `files/tmp|files/toolchain`,
  `CANNOT LINK EXECUTABLE ... libc++_shared.so`, `<unealta>: not found/inaccessible` pentru
  clang/cmake/ninja/cargo/cython/python3/git..., `failed to run custom build command` +
  `Permission denied`, `ModuleNotFoundError` intr-un SUBMODUL de pachet de build). Daca semnalul
  apare: heal(`error`) si, DOAR daca a reparat ceva, O singura re-executare a uneltei +
  rezultatul bun cu nota `[selfheal: ...]`. Rate-limit: max 3/sesiune, minim 15 s intre ele.
* `call_tool` prinde acum si exceptiile uneltelor (`[tool error] Type: msg`) - un tool care
  arunca nu mai omoara procesul agentului (pierdea tot transcriptul), plus `None` -> `(fara output)`.
* **BURETUL DE TOKENI:** heal in COD = 0 tokeni; raportul e O linie pe ECRAN si DOAR cand a
  reparat ceva (a doua pornire fara update = ecran gol, verificat pe device); in contextul
  modelului ajunge doar la cerere, prin `compact()` (o linie, fara JSON cu liste). Comenzi de
  operator (0 tokeni, nu intra in context): **`/heal`** si **`/audit`**; in plus
  `toolchain action=audit` raporteaza ce e rupt fara sa repare.
* `toolchain action=fix` era ~60% NO-OP: lista apela functii inexistente (`_patch_runpath`,
  `_fix_ninja`, `_fix_cc_wrappers`, `_fix_symlinks`, `_fix_wrappers_shebang`, `_fix_sysconfig`),
  inghitite de `getattr` + `try/except`, urmate de un preflight verde. Acum foloseste numele
  reale + registrul selfheal.

**Testat:** (1) test local — 7 invariantе la startup, mediu strictat reparat (launcher mort +
nativeLibraryDir nou + LD cu stub-uri), a doua rulare idempotenta, invariant nerezolvabil
raportat o data si apoi tacere, 11/11 semnale de eroare evaluate corect (fara fals-pozitive pe
„ModuleNotFoundError: numpy" sau pe output normal); (2) E2E pe SM-A366B: dupa update de APK
`[heal] 1 reparate in 284 ms: umbrire: pathspec,scikit_build_core,setuptools_scm`, iar la a doua
pornire (fara update) terminalul e COMPLET GOL.

### 2026-10-08 (1) (fix: copiile trunchiate care UMBRESC pysitepkg.zip — heal automat)

> **Context:** raport scris de agentul de pe device (`site-packages_probleme.md` +
> `SCRAPING_NOTES.md`, in `/sdcard/Download/Agent/workspace/`): build-ul lxml a costat
> ~20 de pasi pentru ca `pip` cadea cu `ModuleNotFoundError` in SUBMODULE ale unor
> pachete de build instalate (`scikit_build_core._compat`, `setuptools_scm._integration`,
> `pathspec._backends`). Agentul le-a mutat manual in `files/backup_sbc/` si a raportat
> explicit ca problema REAPARE daca pachetul e reinstalat — si ca un script de verificare
> automata a umbririi ar fi util. Acest commit il implementeaza in COD.

**Cauza radacina (dovadita pe device):** `sys.path` are ordinea FIXA, hardcodata in binarul
CPython — `<filesDir>/pyhome/lib/python3.14/site-packages` INAINTE de
`<filesDir>/pyhome/lib/pysitepkg.zip`. Deci o copie TRUNCHIATA de pe disc UMBREȘTE pachetul
COMPLET din zip. Iar pe disc ajunge trunchiata pentru ca **AAPT2 nu ambaleaza in assets
folderele/fisierele care incep cu `_`** (`_compat/`, `_backends/`, `_integration/`,
`packaging/_*.py`). Recurenta: la fiecare update de APK, `site_packages_keep` (care contine
si el copiile trunchiate) este restaurat PESTE `site-packages`.

**Fix (in cod, nu manual):**
* `toolchain.heal_site_packages()` — REPARATIE IN LOC din `pysitepkg.zip`: daca pachetul de
  pe disc e un subset exact (aceeasi versiune in dist-info, zero fisiere in plus), copiaza
  fisierele lipsa din zip peste copia de pe disc. Nu doar muta copia rupta: caile din zip
  sunt virtuale si clang/Cython nu le pot citi (headere `.h`, `.pxd`). Pachetele cu fisiere in
  plus (alta versiune, ex. `mesonpy` din pip) NU sunt atinse. Fallback: mutare in
  `files/backup_shadowed/`. Acopera `site-packages`, `site_packages_keep` si
  `python/Lib/site-packages`; curata si `sys.modules`/cache-urile de import.
* `shadow_audit()` — doar raport (ce copii trunchiate exista si ce fisiere lipsesc).
* Ruleaza automat la **fiecare pornire** (o singura linie `[heal] ...`, doar daca a reparat
  ceva) si **inainte de orice `pip_install`**; si la cerere: `toolchain action=heal|audit`.
* `_repair_build_backends()` face heal INTÂI si abia apoi (daca mai e nevoie) reinstaleaza cu
  pip — inainte sarea direct la `pip install --force-reinstall`, care recreeaza umbrirea.
* `_classify_build_fail`: `ModuleNotFoundError` intr-un submodul de pachet de build nu mai e
  raportat ca "pachet lipsa", ci ca `umbrire_site_packages` cu pasul corect (`action=heal`).
* `pip_install` accepta acum si **CALE LOCALA / URL** (dir de surse sau `.tar.gz`), nu doar
  un nume PyPI — solutia dovedita pentru lxml, unde sdist-ul ales de PyPI cerea cerinte de
  build rupte. Calea relativa e rezolvata fata de cwd/workspace/files-tmp.
* `toolchain.py` are acum `__main__` (CLI): inainte `python toolchain.py <actiune>` rula NIMIC
  si returna gol — un esec parea "fara output", nu eroare. Actiunile: check/doctor/selftest/
  preflight/profile/env/env-file/fix/install/heal/audit.
* Promptul agentului (in cod, `agent.py`): reguli noi (4a) umbrire + heal, (4b) pip din sursa
  locala si `sh ./configure` (scripturile nu ruleaza direct din filesDir: noexec pe shebang).

**Verificat:** unit-test pe laptop cu arbore simulat (copii trunchiate din zip real) — cele 3
pachete + `packaging` detectate si reparate, pachetul cu alta versiune NEatins, a doua rulare
idempotenta. Test pe device dupa instalare.

### 2026-10-07 (2) (fix UI: „nu pot scrie în input" — fullScroll fura focusul)

> **Context:** după fix-ul de auto-scroll, userul a raportat că NU mai poate scrie în
> câmpul de input (tastatura se deschide, dar tastele nu ajung nicăieri). Reproducibil:
> `EditText.focused=false` iar IME-ul rămâne atașat de TextView-ul terminalului.

**Cauza:** `ScrollView.fullScroll(FOCUS_DOWN)` (folosit de auto-scroll) apelează intern
`scrollAndFocus()` → `findFocusableViewInBounds()` → **`requestFocus()`** pe primul view
focusabil din interiorul ScrollView-ului. TextView-ul terminalului e focusabil din cauza
`setTextIsSelectable(true)`, deci `fullScroll` îi dădea LUI focusul, furându-l de pe
`EditText`. IME-ul rămânea atașat de TextView → tastele nu mai ajungeau în input.

**Fix (`MainActivity.kt`):** auto-scroll-ul nu mai folosește `fullScroll`, ci o derulare
proprie care nu atinge focusul — `pinToBottom()`: `scroll.scrollTo(0, child.height -
scroll.height)`. `scrollTo` nu mișcă focusul deloc.

**Verificat pe device (instalare curată, date șterse):** scriere OK simplu ȘI în timpul
generării (`focused=true` păstrat după mai multe cicluri de tastatură); auto-scroll nu a
regresat (fără salt/gol la ascunderea tastaturii).

### 2026-10-07 (1) (fix: auto-scroll „moare" la ascunderea tastaturii)

> **Context:** la un task lung (multi-pas, generare continuă), dacă ascundeai tastatura
> în timp ce agentul genera, conversația „sărea" (ieșea din ecran / rămânea gol) și
> auto-scroll-ul nu mai re-fixa coada; textul nou curgea fără să fie urmărit. Reproducibil
> 100% pe Samsung (SM-A366B) cu un task de 4 pași + comut tastatură.

**Cauza:** `root` pierde padding-ul de IME la ascunderea tastaturii (insets listener din
`MainActivity`), deci `ScrollView`-ul își schimbă înălțimea. Android păstrează `scrollY`
numeric, dar re-layout-ul lasă conținutul ne-lipit de marginea de jos; și, fiindcă poziția
de scroll nu s-a schimbat, NU vine niciun eveniment de scroll care să re-armeze urmărirea.

**Fix (`MainActivity.kt`):**
- `scroll.addOnLayoutChangeListener`: când `ScrollView`-ul CREȘTE în înălțime (adică
  tastatura se ascunde) și urmăream coada (`followTail`), re-fixăm la fund după layout.
  Se face DOAR la creștere — la deschidere nu atingem scroll-ul (vezi capcana mai jos).
- `setOnScrollChangeListener`: distingem derularea REALĂ a userului de ajustarea automată
  de scroll produsă de schimbarea înălțimii (`lastScrollHeight`). Fără asta, ajustarea era
  luată drept „user a derulat sus" și oprea urmărirea pe vecie.

**Capcană descoperită și evitată:** prima variantă re-fixa coada și la DESCHIDEREA tastaturii
(inclusiv din insets listener). `fullScroll` în acel moment fura focusul de pe `EditText`
(care îl câștiga exact atunci) → nu se mai putea scrie în input. Fix corect = re-fixare doar
la creșterea viewport-ului.

**Verificat pe device:** A/B cu APK pre-fix vs post-fix, același scenariu — pre-fix: ecran
gol (conversația dispărută); post-fix: textul rămâne vizibil și lipit la fund, `followTail`
rămâne true la fiecare ciclu. Scrierea în input funcționează (`focused=true`).

### 2026-10-06 (3) (curățare: variantele istorice de agent eliminate)

> **Context:** repo-ul avea în rădăcină 7 fișiere moarte (variante inghețate din
> 25 sept 2026) plus 3 documente de lucru depășite. Le-am eliminat, iar `readme.md`
> a fost sincronizat ca să nu mai conțină linkuri moarte.

**Șterse (erau doar referință istorică, nu sursă vie):**
- `agent-original-android.py`, `agent-original-linux.py` (originalele)
- `agent-android-v2.py`, `agent-linux-v2.py` (optimizatele v2)
- `PLAN_AUTONOMIE.md`, `RAPORT_build_apk.md`, `STATUS_OPTIMIZARI.md`

**Sursa vie rămasă:**
- `workspace/app/net.sys32.agent/app/src/main/assets/python/agent.py` — agentul de pe device
- `agent-linux.py` — agentul pentru Linux/desktop

**În `readme.md`:** blocul „UNDE E CODUL SURSA" rescris pentru structura reală a clonelor,
tabelul de costuri actualizat (Android -> `assets/python/agent.py`, Linux -> `agent-linux.py`),
nota despre schema de nume corectată (nu mai există copii în rădăcină), linkurile către
`RAPORT_build_apk.md` / `PLAN_AUTONOMIE.md` redirecționate către `CHANGELOG.md`.

---

### 2026-10-06 (2) (ADB: semnătura tokenului adbd + instalare fără adb)

> **Context:** după ce fix-urile din sursă au ajuns pe device (assets re-extrase automat),
> `adbsh`/`install` tot nu funcționau; agentul raporta `adbd asteapta APROBAREA cheii
> aplicatiei` la fiecare apel. Diagnostic făcut cu protocol ADB BRUT (tunel
> `adb forward tcp:15555 tcp:5555` + cheia reală a aplicației), nu prin presupuneri.

**Cauza 1 — semnătura tokenului adbd nu putea fi produsă**
`RSA_sign(NID_sha1)` din libcrypto de SISTEM (BoringSSL) nu livrează semnătura cerută de ADB:
pe acest device fie eșua, fie **termina procesul** (`[proces terminat]` + restart de watchdog;
logcat: `Fatal signal 11 (SIGSEGV)`). Deci aplicația nu putea NICIODATĂ să dovedească posesia
cheii → trimitea doar cheia publică → adbd afișa dialogul „Allow USB debugging" la fiecare
conexiune, la infinit.
- `assets/python/adb_client.py`: semnătura se calculează **manual** (PKCS#1 v1.5 SHA-1:
  DigestInfo DER + padding + `pow(EM, d, n)`), cu **auto-verificare obligatorie** înainte de
  trimitere; `RSA_sign` rămâne doar ca referință, nu se apelează.
- n/d se extrag prin `PEM_read_bio_PrivateKey` + **`EVP_PKEY_get0_RSA`** + `RSA_get0_key`
  (fără pasul `EVP_PKEY_get0_RSA`, BoringSSL tratează structura `EVP_PKEY` ca `RSA` și citește
  pointeri din ea → SIGSEGV; bug prins și reparat în acest ciclu).
- Verificat: `openssl dgst -sha1 -verify` → **Verified OK** (și local, și pe cheia reală).

**Cauza 2 — canalul uid=2000 e indisponibil pe acest device**
Test izolat: adbd răspunde `A_AUTH/AUTH_TOKEN` chiar și la o semnătură corectă și NU afișează
dialogul de aprobare → `pm install` prin shell nu poate fi folosit.

**Fix — instalare FĂRĂ adb (o singură confirmare pe ecran)**
- `install()`: dacă adb nu e disponibil, deschide **instalatorul de sistem** prin FileProvider
  (`content://` + `ACTION_VIEW`, mime `application/vnd.android.package-archive`) și întoarce
  `installer_opened: true` + instrucțiunea de confirmare. Nu depinde de adb, shell sau root.
- `AndroidBridge.kt`: tool nou **`install`** (`action=apk|status`, `params.path`);
  `AndroidManifest.xml`: provider `androidx.core.content.FileProvider`;
  `res/xml/file_paths.xml` (files/cache/external).
- `agent.py`: descrierea tool-ului + regula **(3v)** extinsă (cum se raportează
  `installer_opened`, fără repetarea apelului în buclă).
- Pe device s-a confirmat: instalatorul de sistem se deschide corect; Android cere o dată
  permisiunea „Install unknown apps" pentru aplicația Agent (setare de securitate a
  operatorului).


### 2026-10-06 (fix regresie: symlink-uri moarte după update de APK + cod python stale în filesDir)


> **Context:** după instalarea unui APK nou, agentul a raportat (în conversația de pe device) că
> `build_apk build` cade cu `No such file or directory: .../android_build/jdk/bin/java`, că
> `setup` „a rulat dar nu a reparat nimic" și că `selftest`/`install` „nu există" — deși fuseseră
> deja adăugate în sursă. Două cauze reale, ambele reparate:

**1. `nativeLibraryDir` se schimbă la fiecare update/reinstalare de APK**
(`/data/app/~~xxxx==/net.sys32.agent-yyyy==/lib/arm64` → alt hash), deci TOATE symlink-urile din
`files/android_build` (jdk/bin/*, aapt2bin/aapt2, toolchain/bin/*, libs în jdk/lib + deps/lib,
`.so.N`) rămân MOARTE. `setup()` ieșea imediat pe marker-ul `.setup_ok` și nu repara nimic →
agentul a recreeat manual symlink-urile (pași pierduți).
- `assets/python/android_build.py`: **`repair_links()`** (nou) + `native_dir()`, `native_dir_changed()`,
  `_symlink()`; lista de unelte e acum în `JMAP`/`BMAP`.
- `setup()` **nu mai iese orbeste pe marker**: pe calea „deja configurat" rulează `repair_links()`
  + `selftest()` (ambele ieftine).
- `build()` repară link-urile în **preflight**, înainte de a porni Gradle.
- marker nou `BUILD/.native_dir` → schimbarea căii e detectată și logată explicit.

**2. Copierea assets → filesDir era condiționată de un nume HARDCODAT** (`.assets_v257`): la update
de APK, codul python din `filesDir` NU se actualiza decât dacă cineva bumpa manual numărul din
`MainActivity.kt` — de aceea fix-urile din sursă nu ajungeau pe device.
- `MainActivity.kt`: stampila devine **`.assets_stamp`**, cu valoarea derivată din APK-ul însuși
  (`versionCode-lastUpdateTime`) → orice update de APK re-extrage automat codul python, iar un APK
  neschimbat nu re-extrage nimic. Stampila legacy `.assets_v257` e ștearsă după prima re-extragere.
- Protecțiile existente rămân valide (site-packages + `files/toolchain/git` + `memory.md` se
  salvează și se restaurează).


### 2026-10-06 (build_apk fără intervenții manuale: preflight + auto-heal + instalare pe device)


> **Context:** raportul `RAPORT_build_apk.md` (scris de agent pe device după compilarea
> HelloWorld) documenta 6 probleme, dintre care **5 erau deja reparate în sursa din repo**
> (versiunea din APK era mai veche: 449 linii vs 660 în repo) și **1 rămăsese deschisă**
> (P6 — instalarea APK-ului din `filesDir`). Au fost închise toate + robustețe suplimentară.

**`assets/python/android_build.py`**
- **`selftest()` (nou)**: rulează REAL `java -version` și `aapt2 version` cu mediul de build
  și raportează `{ok, checks, healed}`. Simpla existență a binarului nu mai e considerată dovadă.
- **auto-heal `libX.so.N` (nou)**: `_heal_missing()` extrage numele lipsă din eroarea linker-ului
  (`library "libz.so.1" not found`), găsește `<lib>.so` și creează symlink-ul versionat în toate
  directoarele din `LD_LIBRARY_PATH`, apoi reîncearcă binarul. Repară exact clasa de erori
  P4/P5 care înainte cerea 4 symlink-uri manuale.
- **`build()` face preflight** (selftest înainte de Gradle) — dacă lipsesc libs, se repară înainte
  de `:app:processDebugResources`, nu după.
- **`publish()` + `install()` (P6, nou)**: `build()` copiază automat APK-ul în
  `/sdcard/Download/Agent/workspace/`; `install()` face publish -> `cp` în `/data/local/tmp` ->
  `pm install -r` **ca shell uid=2000** prin `adb_client.shared()`, pentru că `system_server`
  nu poate citi `filesDir` (context `app_data_file`). Fără el se raportează comanda manuală.
- **`setup()`**: apelează `selftest()` la final și îl loghează (`LAST_SELFTEST`).
- **`_selfheal()`**: poate re-aplica acum și `agent.py` (nu doar `android_build.py`) din
  `Download/Agent/agent_patches/`, deci patch-urile ajung pe device fără rebuild de APK.
- CLI: acțiuni noi `install` și `selftest`.

**`assets/python/agent.py`**
- tool `build_apk`: acțiuni noi `install` (apk= sau dir=) și `selftest`; descriere actualizată
  (publish automat, instalare prin shell).
- `run_build_apk_tool`: după `build` întoarce și câmpul `install` cu comanda gata de rulat.
- strategia agentului (MISSION RULES) — regula **(3v)**: fluxul corect `setup` -> `build` ->
  `install`, interzis `pm install` pe căi din `filesDir`, cu eroarea SELinux exactă de recunoscut.

**Documentație**: `readme.md` (fluxul complet + secțiunea de robustețe), `RAPORT_build_apk.md`
(raportul optimizat al agentului, cu mapa „deployat vs sursă").



> **Decizie de arhitectura:** a doua aplicatie (`net.sys32.odc_agent`) a fost **eliminata
> complet** din repo si de pe device. Exista o singura aplicatie: `net.sys32.agent`.

**De ce a fost eliminata:**
- duplica **895 din 1816 fisiere tracked (~49%)**, aproape tot `assets/python` (stdlib CPython
  + site-packages) — doua copii ale aceluiasi cod in repo;
- crea confuzie si deriva: APK-ul odc rămânea cu versiuni vechi (ex. `android_build.py` de
  21254 B fara fix-uri, cauza unei serii de 3 retry-uri la setup si a unui symlink manual);
- costul de intretinere depasea beneficiul.

**Ce s-a sters:**
- `odc_agent/` (895 fisiere) + `pc_kit_scripts/` (build odc pe PC) + `tools/make_agent_variant.sh`;
- din scripturi: `install_agents_fresh.sh` (doar agent), `wipe_device.sh` (fara odc),
  `backup_device_tools.sh` (fara `odc-build-inputs.tar`), `.gitignore` (blocul odc);
- din documentatie: `readme.md` (sectiunea "doua aplicatii" + OP.9 rescrise),
  `BUILD_ANDROID_ON_DEVICE.md` §9.1/§9.2/§9.3/§9.6, nota istorica in
  `tools/DEVICE_BACKUP_MANIFEST.md`.

**Verificat inainte de stergere:** agentul NU depinde de odc_agent nicaieri — 0 referinte
funcionale in cod (doar comentarii), 0 importuri Python, mecanismul de patch-uri
(`_pkg_patches_dir`) e generic si cade pe dir comun daca nu exista subfolderul de pachet.

**Fix `android_build.py` — `_assets_dir()` (commit `192ca9c`):**
- candidatii vechi nu gaseau NICIODATA `<filesDir>/assets/android_build` (2 se rezolvau
  amandoi la `<app-root>/assets`, cu un nivel prea sus) -> `setup()` cadea cu
  `FileNotFoundError .../sdk/platforms/android-36/package.xml`;
- fix: candidatul real (`os.path.dirname(_HERE)+'/assets/android_build'`) pus primul +
  `ASSETS` aliniat; in plus `_selfheal()` devine PER PACHET (`agent_patches/<pkg>/`).

**Fix auto-scroll UI (commit `679932d`) — "scroll-ul sare mai sus la un task nou":**
- `followTail=true` se seta doar la start / scroll manual in jos / in listener-ul de scroll,
  NU si la inceputul unui task nou -> textul curgea sub margine, scroll blocat
  (masurat: gap 722-885px, stabil peste 6-13 esantioane);
- re-armarea depindea de un eveniment de scroll; daca scroll-ul era blocat, deadlock;
- fix: `sendLine()` re-armeaza (+`scrollToBottom()`), `appendAnsi()` masoara `wasAtBottom`
  **inainte** de append si re-armeaza, `scrollToBottom(force)` dupa trunchiere, nou `atBottom()`;
- 5/5 teste de logica (`scroll_logic_test.py`), APK compilat OK.

---

### 2026-10-05 (WIPE TOTAL + INSTALARE DE LA ZERO A AMBILOR AGENTI)

> Telefonul a fost golit complet si ambii agenti reinstalati de la zero: dovada ca instalarea
> e autonoma si independenta.

- **Stergere totala**: dezinstalate toate 5 aplicatiile `net.sys32.*`, golit `/data/local/tmp`
  (9,7 GB de unelte/proiecte) si TOT `/sdcard` -> /data de la 47 GB la 17 GB folositi (205 GB liberi).
  Script reproductibil: `tools/wipe_device.sh`.
- **odc_agent are acum ACELASI payload ca agentul principal** (inclusiv Rust):
  `rust-libs.tar` 801,6 MB (`librustc_driver` + `libLLVM` + std) -> compozitia identica:
  toolchain 1007 MB / 6077 fisiere, 146 libs native, android_build 381 MB, python 54 MB.
  odc_agent se construieste acum cu **Gradle pe laptop** (nu doar pe device) -> e si debuggable.
- **Fix build**: `compressDebugAssets` (care decomprima `rust-libs.tar.gz` -> 840 MB si il
  re-comprima) murea cu `Java heap space` la build de la zero -> `org.gradle.jvmargs=-Xmx5120m`.
- **Instalare curata**: `tools/install_agents_fresh.sh` (push + `pm install -r` ambii, start,
  accessibility). Ambele `Success`; ambele au extras singure payload-ul din propriul APK
  (`files/toolchain`, `files/python`, `files/home`, marker `.assets_v257`) — fara
  `/data/local/tmp`, fara descarcari.
- **Capcana de onboarding (de stiut)**: `startCore()` (care face extragerea) ruleaza doar dupa
  ce TOATE permisiunile esentiale sunt acordate (CAMERA, RECORD_AUDIO, ACCESS_FINE_LOCATION,
  READ_CONTACTS, READ_MEDIA_IMAGES, POST_NOTIFICATIONS) — la instalare curata, fara
  READ_MEDIA_IMAGES, aplicatia asteapta si NU extrage nimic. Acordat prin `pm grant`.
- **Cheia API** scrisa in ambele (`files/python/key.txt` + `files/home/key.txt`) prin `run-as`
  (posibil acum pentru ambele, fiind debuggable) -> ambele au pornit Python.
- **Verificat final**: 2 pachete instalate, 2 procese `libpyexec.so` (unul sub fiecare aplicatie),
  `/sdcard/Download/Agent` si `/sdcard/Download/odc_agent` separate, fiecare cu `adbkey`,
  `adbkey.pub` si `workspace/` propriu; crash buffer gol.

---

### 2026-10-05 (AMBII AGENTI EGALI SI INDEPENDENTI LA INSTALARE)

> `net.sys32.agent` si `net.sys32.odc_agent` sunt acum functionali identic dupa instalare:
> fiecare are TOATE uneltele (inclusiv compilare de APK-uri, offline) si propriul spatiu pe
> /sdcard. Verificat pe device.

- **Workspace + adbkey PER APLICATIE**: `res/values/strings.xml` -> `agent_home_dir`
  (canonica `Agent` -> `/sdcard/Download/Agent`; varianta `odc_agent` -> `/sdcard/Download/odc_agent`),
  setat automat de `make_agent_variant.sh`. Inainte ambii foloseau acelasi folder.
- **Bug gasit si reparat**: `adb_setup.py` era lansat de Kotlin intr-un proces separat **fara**
  `AGENT_HOME` -> cadea pe fallback-ul hardcodat si cheia adb ajungea tot in folderul celuilalt.
  Acum ambele lansari de Python din `MainActivity.kt` seteeaza acelasi `AGENT_HOME`.
- **Agentul principal egalat cu odc_agent** (avea codul de build, dar nu payload-ul):
  +126 libs native in `jniLibs/arm64-v8a/` (libjava_exec, libjavac_exec, libjlink_exec,
  libaapt2_exec, libaapt2wrap_exec + absl/protobuf/fmt/expat/iconv/jpeg/lcms2/png/turbojpeg/z),
  +`assets/android_build/` (7 fisiere, 381 MB: openjdk-21.deb, gradle.deb, platform36.zip,
  buildtools36.zip, aapt2.deb, sqlite-jdbc, android.toolchain.cmake; md5 identic cu device).
  => **APK principal: 983 MB** (era 664), 146 libs.
- **Marker assets**: `.assets_v256` -> `.assets_v257`; `.gitignore` pentru
  `workspace/.../assets/android_build/` (fisierele mari nu se comit).
- **Verificat E2E pe device**: ambele APK-uri buildate (`BUILD SUCCESSFUL` Gradle / `BUILD OK`
  pe device) si instalate (`Success`, lastUpdateTime 12:20) -> ambele aplicatii pornesc si
  Python ruleaza ca subproces al fiecareia; agentul principal a re-extras codul unificat
  (`files/python/agent.py` 235366 B cu `build_apk`, `android_build.py`, `.assets_v257`),
  pastrand `context.json` (2,7 MB) si `memory.md`; `/sdcard/Download/Agent` (5,4 GB) si
  `/sdcard/Download/odc_agent` sunt separate, fiecare cu `adbkey`-ul lui.
- **Ghid actualizat**: `BUILD_ANDROID_ON_DEVICE.md` §8 (compozitia reala a APK-urilor, masurata)
  + **§9 nou** (o singura sursa, ambii identici, build pe laptop vs device, capcanele noi,
  instalarea de la zero). `readme.md` -> OP.9/OP.10, `odc_agent/README.md` (proiect GENERAT).
- **Nota**: terminalul agentului principal apare GOL la pornire — e by design, in `agent.py`
  scrie „linia de diagnostic NU se mai afiseaza in UI la pornire" (cerut de operator: doar erorile).

---

### 2026-10-05 (AGENTII UNIFICATI: O SINGURA SURSA, AMBII AU `build_apk`)

> `net.sys32.agent` si `net.sys32.odc_agent` au acum **aceeasi sursa de cod**. `odc_agent/`
> este GENERAT, nu mai e mentinut de mana.

- **Inventar dovedit**: dupa normalizarea numelui de pachet, cele 15 module Kotlin si toate
  fisierele Python sunt IDENTICE intre cei doi agenti; fisierele Gradle/manifest nu difera deloc.
  Singurele diferente reale: `android_build.py` (doar odc), tool-ul `build_apk` (doar odc) si
  `build.py` (odc folosea `nativeLibraryDir` dinamic in loc de hash hardcodat).
- **Script nou `tools/make_agent_variant.sh`** — genereaza o varianta (Gradle sau `--flat` pentru
  `build_apk.sh`) din sursa canonica `workspace/app/net.sys32.agent/`: rescrie pachetul in 77
  fisiere, redenumeste directorul Kotlin, seteaza eticheta, iar la `--flat` injecteaza
  `package=` + `<uses-sdk>` in manifest.
- **Unificat in agentul principal**: `assets/python/android_build.py`, `build.py` dinamic,
  tool-ul `build_apk` (lista de tool-uri: 11 -> 12) si `build_apk.sh` in sursa canonica
  (versiunea corecta, cu ambalarea `lib/` pentru jniLibs).
- **BUG REPARAT — odc_agent nu putea porni**: `agent.py` avea 3 coruptii pe intrarea `build_apk`
  (prefix `{"type":"function","function":` duplicat, intrarea `read` fara prefix, o acolada `}`
  in plus dupa descriere) => `SyntaxError` la import => creierul Python al odc_agent nu pornea
  deloc, desi `build_apk` era in APK. Acum lista se parseaza (12 tool-uri verificate in JSON).
- **Verificat E2E pe device**: `bash tools/make_agent_variant.sh … --flat` -> push in
  `/data/local/tmp/apkbuild/odc_full` -> `build_apk.sh` -> **BUILD OK** (299 clase Kotlin,
  dex 8.7 MB, 146 libs native, assets ~600 MB) -> APK **627 MB** semnat -> `pm install -r`
  = `Success` -> aplicatia porneste si Python ruleaza (`Configuring... DONE`, cere cheia
  DeepSeek). `md5(agent.py)` din APK == md5 din sursa generata (`184daeca…`).
- **Marker assets**: `.assets_v253` -> `.assets_v254` (assets s-au schimbat, obligatoriu).
- **`.gitignore`**: fisierele mari generate de odc_agent nu se comit
  (`assets/toolchain/`, `assets/android_build/`, `jniLibs/`).
- **`odc_agent/README.md`** rescris: proiect GENERAT + cum se regenereaza + regulile.
- `readme.md` -> **OP.9** cu procedura completa de unificare/regenerare/build.

---

### 2026-10-05 (BACKUP COMPLET AL UNELTELOR DE PE SAMSUNG PE LAPTOP)

> Toate uneltele de build care traiesc DOAR pe telefon (nu sunt in git) au fost salvate local
> in `build/device-backup/` + `build/device-tools-backup/`, cu script reproductibil.

- **Script nou `tools/backup_device_tools.sh`** — face 5 arhive prin `adb exec-out` + `tar cf -`
  (stream direct, fara sa umple discul telefonului), cu `run-as` pentru stocarea privata.
- **Total ~6.4 GB in 6 arhive**: `apkbuild-tools.tar` (806 MB — jdk/kotlin/d8/aapt2/gradle/sdk/
  javahost/tlib/release.keystore din `/data/local/tmp/apkbuild`), `odc-build-inputs.tar`
  (1459 MB — `odcassets` + `odclibs` = exact inputurile pentru build-ul APK-ului odc_agent),
  `app-toolchain.tar` (1856 MB — clang/cmake/ninja/deps/rust/sysroot),
  `app-state.tar` (300 MB — `python/agent.py`, `pyhome`, `site_packages_keep`, `memory.md`),
  `hdbuild-gradle.tar` (2625 MB — stack-ul Gradle cu platforma android-36 completa si
  `gradlehome` = cache OFFLINE), `sdcard-repo.tar` (69 MB — clone-ul git de pe telefon).
- **Excluse**: proiectele/iesirile (`odc*/`, `*.apk`, `work*/`, `tmp/`) si **secretele**
  (`files/home/.ssh`, `key.txt`) — nicio cheie in arhive.
- **Verificat**: `tar tf` rc=0 pe fiecare arhiva; set-diff fata de `find` pe device
  (hdbuild 66778/66770 = exact cele 8 excluderi intentionate; app-state 10361/10361 = 0
  diferente; toolchain/odc-inputs/repo identice); md5 identic device vs arhiva pe 15 fisiere
  (rust-libs.tar, android.jar, libpython3.14.so, fileHashes.bin, agent.py, memory.md...);
  224+18+2 symlink-uri pastrate. Raport: `tools/DEVICE_BACKUP_MANIFEST.md`.
- **Documentat** in `readme.md` -> OP.8 (backup/restore + capcana symlink-urilor absolute
  catre `/data/app/~~<hash>==/...`, care mor la reinstalarea javahost-ului).

---

### 2026-10-05 (odc_agent AUTONOM: compilează APK-uri pe device, complet offline)

> **odc_agent (`net.sys32.odc_agent`) e acum complet autonom** — la instalare de la zero poate
> compila aplicații Android (APK) direct pe telefon, offline. APK 617 MB, instalat + rulat.

**Ce s-a adăugat în odc_agent:**
- **Toate uneltele împachetate în APK** (zero descărcări): JDK module (openjdk-21.deb),
  Gradle 9.8, SDK platform+build-tools, sqlite-jdbc 3.46, toolchain (clang/sysroot/ninja),
  + 146 libs native în jniLibs (java/aapt2/clang/cmake/python).
- **Modul nou `android_build.py`** (integrat ca tool `build_apk` în agent): `setup()` extrage
  uneltele în filesDir, `build(dir)` compilează proiectul → APK, `verify(apk)` verifică.
- **`build()` e complet automat**: scrie gradle.properties (VFORK + aapt2 override),
  înlocuiește aapt2-ul x86_64 din Maven cache, rulează Gradle cu VFORK propagat.

**Capcane rezolvate (toate dovedite):**
- jlink/javac lansate de AGP prin `jspawnhelper` → `org.gradle.jvmargs` cu VFORK în
  gradle.properties al proiectului + `JAVA_TOOL_OPTIONS`.
- aapt2 daemon (Maven x86_64) → symlink la javahost + `android.aapt2FromMavenOverride`.
- nativeLibraryDir: `glob()`/`os.listdir("/data/app")` blocate de SELinux → citit din
  `TC_NATIVE` (env setat de MainActivity) sau `/proc/self/maps`.
- libc++ (`__*`) eliminat de AAPT2 → împachetat în `libcxx_full.zip`.

**Dovedit E2E:** proiect HelloWorld Android compilat cu `android_build.build()` → APK 0.8 MB,
instalat. Toate task-urile Gradle (aapt2, dex, packageDebug, assembleDebug) au rulat.

---

### 2026-10-05 (VOCISHD COMPILAT CU SUCCES PE DEVICE - BUILD SUCCESSFUL!)

> **REUȘIT: `assembleDebug` COMPLET pe telefon.** APK-ul VocisHD (net.sys32.vocis, v2.89,
> 38 MB) compilat, semnat, instalat și RULAT pe device. 58 task-uri, BUILD SUCCESSFUL.

**Rezultat final:** APK 38 MB (89 MB despachetat, 545 fișiere), conține `classes.dex`
(43.9 MB — Kotlin + Hilt + Compose), `libopus_jni.so` pentru **toate 7 ABI-urile**
(arm64-v8a, armeabi-v7a, armeabi, mips, mips64, x86, x86_64), `libsqlcipher.so`,
`resources.arsc`, `AndroidManifest.xml`. Instalat + pornit fără crash (PID viu).

**Toate barierele rezolvate (în ordine):**
1. java/jlink/jmod/javac → ambalate în APK ca `lib*_exec.so` (APK-gazdă `net.sys32.javahost`)
2. Gradle daemon fork (`jspawnhelper`) → `-Djdk.lang.Process.launchMechanism=VFORK`
3. `java.io.tmpdir` + `user.home` (compilate Termux) → redirecționate
4. cmake/aapt2 x86_64 ale AGP → symlink la variantele **aarch64** ale noastre
5. fake-NDK prin symlink-uri + `llvm-strip`/`llvm-ar`/`llvm-ranlib`/`llvm-nm`
6. SDK scriibil → `filesDir`
7. **aapt2 daemon** → AGP descarcă aapt2 din Maven la
   `transforms/<hash>/aapt2-9.0.1-<rev>-linux/aapt2`; îl înlocuiești cu symlink la
   `javahost/libaapt2_exec.so` + libs în `toolchain/deps/lib` (care e în LD_LIBRARY_PATH-ul
   daemonului Gradle)
8. **kapt SQLite** → `sqlite-jdbc 3.41` NU are natives Android (0 bytes);
   **`sqlite-jdbc 3.46.0.0`** ARE `Linux-Android/aarch64/libsqlitejdbc.so` real →
   `-Dorg.sqlite.lib.path=<DIRECTOR cu libsqlitejdbc.so>` (director, nu fișier!)

**Concluzie:** build-ul Android complet (Gradle + AGP + Kotlin + Compose + Hilt + Room +
kapt + **cod nativ C/NDK**) **FUNCȚIONEAZĂ pe device, fără PC**. Toate capcanele
SELinux/x86_64 rezolvate.

---

### 2026-10-05 (ISTORIC: VOCISHD pe device — etapa intermediară ~95%, vezi mai sus succesul final)

> **Al treilea experiment major: compilarea APK-ului VOCISHD (`net.sys32.vocis`,
> repo `hdvoice`) DIRECT PE TELEFON**, fără PC/Gradle pe PC. Rezultat: build-ul ajunge
> la **~95%** (39 task-uri Android executate), blocat doar la aapt2 în mod daemon.

**Ce FUNCȚIONEAZĂ pe device (dovedit):**
- **Gradle 9.8 + AGP 9.0.1 + Kotlin 2.1.21 + Compose + kapt + Hilt** se încarcă și
  configurează complet proiectul VocisHD.
- **OPUS (codec audio C, 149 fișiere) SE COMPILEAZĂ ȘI SE LINKEAZĂ** — `ninja` + `clang 21`
  (al nostru, aarch64), pentru **toate ABI-urile**: arm64-v8a, armeabi-v7a, armeabi, mips,
  mips64, x86, x86_64 (`libopus.a` + `libopus_jni.so` produse).
- **kapt TRE CE** (procesare adnotări Hilt/Room pe 93 fișiere Kotlin).
- Resurse, AndroidManifest, dex, keystore, SDK minimal, NDK fals, CMake — toate funcționale.

**Ce am construit pentru asta:**
- **`net.sys32.javahost`** — APK-gazdă (11 MB) cu binararele JDK ambalate ca
  `lib<name>_exec.so`: `libjava`, `libjlink`, `libjmod`, `libjimage`, `libjavac`, `libjar`,
  `libkeytool`, `libjarsigner`, `libaapt2` + 120 libs de suport (absl/protobuf/fmt/c++).
  Rolul lui: SELinux permite execuția DOAR din `lib/arm64/` din APK — deci Java (și aapt2)
  trebuie „ambalate" ca lib-uri ca să poată rula din procesul aplicației.
- SDK Android minimal în `filesDir` (`platforms/android-36` complet + `build-tools/36.0.0` +
  `licenses`), NDK fals prin symlink-uri, cmake/aapt2 înlocuite cu variantele aarch64.
- `-Djdk.lang.Process.launchMechanism=VFORK` (Gradle fork-ează daemonul prin `jspawnhelper`
  care nu rulează → VFORK îl ocolește), `-Djava.io.tmpdir`, `-Duser.home`.

**Bariere rezolvate (toate SELinux / binare x86_64):** java/jlink/jmod/javac → în APK ca
lib-uri; Gradle daemon fork → VFORK; `java.io.tmpdir` → redirecționat; cmake/aapt2 x86_64 ale
AGP → symlink la aarch64-ul nostru; SDK scriibil → `filesDir`; NDK oficial (x86_64) inutil →
fake-NDK; kapt SQLite → `room.verifier=false`; keystore debug → generat + `-Duser.home`.

**BLOCAJ RĂMAS (unicul):** AGP 9 lansează **`aapt2 daemon`** (mod server) pentru
transform-urile AAR (play-services, media3...). Aapt2-ul Termux 2.20 (aarch64, singurul care
rulează) **nu are opțiunea `--daemon`**; aapt2-ul oficial (cu daemon) e x86_64 →
„AAPT2 Daemon startup failed". Opțiuni neîncercate: box64 (translare x86_64), downgrade AGP,
compilare aapt2 din sursă cu daemon pentru ARM.

**Concluzie:** build-ul Android complet (inclusiv cod nativ C/NDK) **este tehnic posibil pe
device** — am dovedit fiecare verigă. Rămâne o singură incompatibilitate de unealtă
(aapt2 daemon ARM). Toate detaliile de reproducere sunt în memorie (`odc_agent/memory.md`).

---

### 2026-10-04 (BUILD APK NATIV PE DEVICE + A DOUA APLICATIE `net.sys32.odc_agent`)

> **IMPORTANT: acum exista DOUA aplicatii pe device.**
> `net.sys32.agent` = agentul ORIGINAL (activ, vorbea cu operatorul in timpul build-ului).
> `net.sys32.odc_agent` = CLONA, compilata direct pe telefon din surse, instalata ALATURI.
> Nu se re-instaleaza peste agentul original cat timp ruleaza (procesul moare la
> `pm install` -> moare si sesiunea agentului). A doua aplicatie e calea sigura.

- **Lanț complet de build Android pe device, fara PC, fara Gradle, fara Android Studio.**
  Dovedit end-to-end: source Kotlin -> APK semnat -> instalat -> rulat.
- Unelte (pachete Termux aarch64): **JDK 21** (openjdk-21), **kotlinc 2.4.20**, **d8 9.2.4**,
  **aapt2 2.20**, **apksigner 0.9** + biblotecii C++ Termux (libc++, fmt, protobuf, abseil...).
  `android.jar` API 36 de la Google (`platform-36_r01.zip`), androidx din Google Maven.
- Pipeline (script `/data/local/tmp/apkbuild/build_apk.sh`, 6 pasi):
  1. `aapt2 compile` resurse + resursele din fiecare AAR; `aapt2 link --auto-add-overlay
     --extra-packages <toate pachetele cu resurse>` -> `base.apk` + `R.java`
  2. `kotlinc` sursele `.kt` -> `classes/`
  3. `javac` SEPARAT pe R.java-urile generate (kotlinc nu compileaza `.java` fara javac)
  4. `jar` + `d8` (include kotlin-stdlib + TOATE jar-urile runtime) -> `classes.dex`
  5. ambalare dex + `assets/` in `base.apk`
  6. `keytool` (cheie noua) + `apksigner` -> APK semnat (v1+v2+v3)
- **Clona `net.sys32.odc_agent`**: transformare = inlocuire globala `net.sys32.agent` ->
  `net.sys32.odc_agent` (27 fisiere, 66 aparitii: package Kotlin, applicationId/namespace,
  cai filesDir, action strings, taskAffinity), folder java redenumit, label -> "ODC Agent".
  `build.py`: hash-ul de cale APK hardcodat -> inlocuit cu `_find_app_lib()` (glob dinamic).
- Rezultat: **282 clase**, APK **17.6 MB**, instalat si RULAT (ajunge la dialogul
  "ODC Agent wants to set up a VPN connection" + All files access) = pipeline validat pe
  a doua aplicatie.
- Capcane rezolvate la runtime (fiecare = un `ClassNotFoundException` la rand):
  kotlin-stdlib lipsa din dex; AAR-uri KMP care sunt `.klib` in loc de bytecode
  (`collection-jvm`, `lifecycle-common-jvm`, `annotation-jvm`); `kotlinx-coroutines`;
  `androidx.arch.core` (core-runtime); `R.class` generat dar necompilat;
  `R$drawable` appcompat (`--extra-packages`); `R$id` lifecycle (AAR-ul `-android`
  cu resursele reale: `view_tree_lifecycle_owner`, `view_tree_view_model_store_owner`).
- HelloWorld (`net.sys32.hello`): primul test al pipeline-ului, compilat + instalat +
  rulat (screenshot arata "Hello World de pe device! / Compilat pe telefon. / SM-A366B").

- **Reproductibil din repo:** sursa clonei e in `odc_agent/` (numele vine de la *on-device
  compiled*). Include `odc_agent/README.md` (diferente + cum se construieste) si
  `odc_agent/build_apk.sh` (scriptul de build pe device). Reteta completa de la zero
  (unelte, `android.jar`, androidx, capcane runtime) e in `readme.md` -> **OP.2-DEVICE**.
- **Redenumire completa**: package-ul clonei a trecut de la `net.sys32.agent2` la
  **`net.sys32.odc_agent`** (nume afisat „ODC Agent"), ca sa nu existe confuzii cu
  originalul. 0 aparitii de „agent2" in repo. Recompilat + reinstalat (282 clase, 17.7 MB).

- **Fix: ODC Agent complet functional (assets + libs native in APK).** Prima varianta a
  clonei (doar cod, 17.7 MB) pornea dar Python murea:
  `Cannot run program ".../lib/arm64/libpyexec.so" ... error=2` + bucla `[watchdog]`, apoi
  `Fatal Python error: Failed to import encodings module`. Cauza: build-ul manual nu
  ambala nici bibliotecile native (`jniLibs`), nici stdlib-ul Python.
- **Ce s-a adaugat** (extras din APK-ul original instalat, NU versionat in git):
  - `lib/arm64-v8a/*.so` — **25 fisiere, 392 MB** (libpyexec, libpython3.14, libcrypto/ssl/
    sqlite3_python, libc++_shared + toolchain: clang 80 MB, flang 137 MB, lld, cargo, cmake,
    ninja, perl, maturin, rustc...).
  - `assets/` — **1.0 GB** (`python/` 58 MB cu `Lib/` complet — inclusiv 123 fisiere
    `encodings` —, site-packages si ZIP-urile `pysitepkg`/`stdlib_extra`; `toolchain/` 1 GB
    cu `rust-libs.tar` 840 MB, sysroot, cmake, perl...).
  - `build_apk.sh` ambaleaza acum `lib/` si `assets/` (`jar uf`); manifest are
    `extractNativeLibs="true"`.
- **Rezultat: APK 497 MB** (originalul: 664 MB). ODC Agent ajunge la ecranul corect:
  `Configuring... DONE` -> `AGENT FULLY CONFIGURED AND OPERATIONAL` -> cere cheia DeepSeek
  (`LIPSA CHEIA DeepSeek API`). Identic functional cu originalul.
- **Capcana**: aplicatia extrage assets in `filesDir` la PRIMA rulare si nu re-extraege daca
  `pyhome` exista deja -> dupa un build nou, `pm clear net.sys32.odc_agent` forteaza
  re-extragerea.

### 2026-10-04 (UI: font terminal reglabil + text selectabil + banner mutat in bara - `.assets_v253`)

- `output` TextView: **11sp -> 15sp** implicit. Bara sus-dreapta `A-` / `<marime>` / `A+`
  (10..30 sp, pas 1sp), persistata in SharedPreferences (`agent_ui`/`font_size`) -> marimea
  se pastreaza intre lansari.
- `AGENT_COLS` se masoara acum cu `fontSizeSp` (inainte `11f` hardcodat) -> banner-ul ramine
  aliniat la fontul real la prima pornire.
- `setTextIsSelectable(true)` pe terminal -> long-press deschide bara contextuala
  **Copy / Select all / Share**. Butonul dedicat "copy" (prima varianta a schimbarii) a fost
  SCOS la cererea operatorului: copierea apare DOAR cand selectezi textul.
- **Banner mutat din terminal in bara de sus** (cerut de operator): `⚡ AGENT DeepSeek`
  (rosu 38;5;203) + `Type /help for all commands` (38;5;146) stau acum in STANGA barei,
  linga `A- 15 A+`. Print-ul din `agent.py` a fost STERS -> la pornire ecranul e complet gol
  (doar erorile mai apar, exact cum s-a cerut).
- Deci `assets/python/agent.py` a fost atins -> marker `.assets_v252` -> **`.assets_v253`**.
  Re-extragerea sterge `files/python/key.txt`; cheia se pastreaza in `files/home/key.txt`, iar
  `readStoredKey()` cauta si acolo -> agentul porneste fara re-onboarding.
- Verificat end-to-end pe device (SM-A366B): `A- 15 A+` singure in coltul dreapta-sus,
  long-press pe "DeepSeek" -> selectie + bara cu Copy; task trimis din UI -> mesajul ajunge in
  `context.json` si raspunsul se randeaza in terminal.

---

### 2026-10-03 (SCRAPING WEB + motor JavaScript NATIV + cautare/stiri - `.assets_v252`)

Sesiune pe device: agentul invata sa citeasca web-ul real (site-uri statice, SPA/React,
date in JavaScript) si sa caute informatii ACTUALE, fara cheie API. 8 commituri.

**Strat 1 - scraper.py (static, rapid):**
- `scraper.py` livrat in `assets/python/` (inainte exista doar in `workspace/tools/`).
- bug fix JSON: in trafilatura 2.x `extract_metadata().as_dict()` intoarce elemente lxml
  (`_Element`) la `body`/`commentsbody` -> `json.dumps` cadea cu TypeError. Fix: `_clean_meta()`
  (scoate/converteste valorile neserializabile) + `default=str` la afisare.
- dependinte native instalate pe device: lxml 6.1.3, parsel 1.12.1, trafilatura 2.3.0,
  feedparser 6.0.14, justext 3.0.2 (+deps); wheelhouse in `files/wheels` (13 wheel-uri,
  inclusiv lxml android_24_arm64_v8a compilat pe telefon).

**Strat 2 - jsengine.py (motor JavaScript NATIV pe device):**
- mini-racer = FUNDATURA pe Android (cere V8 din sursa / `libmini_racer.so`); playwright,
  selenium, dukpy testate si RESPINSE (fara Chromium headless / fara DOM/ES6).
- solutia: **quickjs 1.19.4 compilat NATIV** pe device
  (`quickjs-1.19.4-cp314-cp314-android_24_arm64_v8a.whl`, 449 KB).
- verificat: ES2020 complet (arrow/let/const, classes+getters, Promise/async-await,
  optional chaining, nullish, Map/Set, BigInt, template literals, destructuring, regex,
  closures) + comunicare bidirectionala Python<->JS (`ctx.add_callable()`).
- `jsengine.py`: mediu "browser" stub (window/document/console/navigator/localStorage),
  `extract_and_run()` ruleaza TOATE `<script>` inline dintr-o pagina si evalueaza o expresie.
- cand se foloseste: date in JS inline / calcule client-side (instant); randare completa
  de DOM -> `jsfetch.py`.

**Strat 3 - jsfetch.py (randare reala in Chrome-ul de pe device):**
- scraper.py NU vede continutul randat de JS (reddit/x.com = 0 chars, vuejs.org 455,
  svelte.dev 506). Solutia: deschide pagina in Chrome (V8 real), asteptare adaptiva,
  citirea arborelui de accesibilitate (`uiautomator dump`).
- masurat: vuejs.org 71 texte, react.dev 143, angular.dev 83, news.ycombinator.com 268
  (14s). Auto-dismiss cookie banner, scroll, deduplicare, fallback adb_client/subprocess.
- cost ~12-23s/pagina -> se foloseste DOAR cand scraper.py nu ajunge.

**Legatura scraper <-> jsengine (`supreme`):**
- functii noi in scraper.py: `sniff(html)` (static/hybrid/spa), `extract_js_data(html)`
  (7 patterns: `__NEXT_DATA__`, `__NUXT__`, `__INITIAL_STATE__`, `__DATA__`,
  `__PRELOADED_STATE__`, `__APOLLO_STATE__`, ld+json), `js_query(url, expr)`,
  `deep(url, keys)`, `supreme(url)` (alege si executa automat metoda optima).
- CLI nou: `sniff | jsdata | jsquery | deep | supreme`.
- dovada (BBC News 379 KB): `sniff` -> "hybrid" (59 scripturi), `supreme` -> 123 titluri
  in 287 ms (3x mai rapid ca `article()` singur pe hub-uri de stiri, 100x mai mult continut
  din JSON imbricat).
- bug reparat: `deep()` cu `keys='title,headline'` era tratat ca o singura cheie -> split pe virgula.

**Optimizare decizie (test cap-coada):**
- problema: Wikipedia (215 KB text HTML, doar 793 b ld+json) era clasata "hybrid" si trimisa
  la Chrome (27s inutil); react.dev statea 20s pe Chrome desi scraper-ul dadea continut in 0.6s.
- regula noua: cand blocul JS e mic (<2000 b), decizia depinde de TEXTUL din HTML
  (`>3000 chars` -> scraper; `<3000` -> chrome).
- rezultate: Wikipedia 1214ms (era 27095ms, **22x**), react.dev 615ms (era 20538ms),
  BBC 293ms (neschimbat). Toate cele 3 ramuri testate (static->scraper, hybrid->scraper+jsengine,
  spa->chrome).

**Detectie SPA + fallback accessibility:**
- testat pe danielpincu.com (SPA pur, tema Matrix): `sniff()` rata SPA-urile cu UN singur
  `<script type=module>` -> acum 4 semnale (script module, div#app/root/__next, src=/assets/*.js,
  bundler, body gol <60 chars); prag 2+ semnale => spa.
- `jsfetch()` murea cu "uiautomator dump: ERROR: could not get idle state" pe pagini cu
  ANIMATII CONTINUE (canvas Matrix) -> FALLBACK automat pe ACCESSIBILITY (bridge Kotlin,
  nu depinde de idle) + verificarea URL-ului tabului activ + curatare zgomot de browser.
- dovada: danielpincu.com -> 83-84 texte (inainte 0); stabil pe 2 rulari; cazurile vechi
  neatinse (bbc.com hybrid 347ms, wikipedia/example.com scraper OK).

**Cautare si stiri (fara cheie API):**
- `websearch.py`: dispecer `search(q)` bing -> wikipedia -> marginalia, cu retry/backoff;
  `bing()` cu `setlang=en` (`mkt` dadea 0 rezultate), `wikipedia()` (API MediaWiki),
  `marginalia()`, `ddg()` cu detectie CAPTCHA; `topical(q)` = stiri + web.
- `newsfeed.py`: `gnews()` Google News RSS (100+ stiri cu pubDate, gratuit), `bingnews()`,
  `rss()`, `latest()`; dict `FEEDS` (digi24/hotnews/agerpres/bbc/guardian).
- scop: informatii ACTUALE gratuite (Wikipedia nu e sursa de actualitate).

**Documentatie:**
- README: sectiunea "motor JavaScript (jsengine)" + lantul suprem de scraping (quickjs nativ,
  cele 5 functii din scraper.py, 7 patterns, CLI extins, decizia `supreme()`, de ce mini-racer
  e imposibil pe device); punctul 7 in REGULA DE AUR (scraping -> `scraper.py` default) +
  sectiunea SCRAPING WEB (8 comenzi, stack, wheelhouse, 3 capcane, rc=0 pe 8 URL-uri reale).

---

### 2026-10-03 (git reconstruit de la zero pe device dupa curatare completa + README corectat)

Sesiune pe device. Operatorul a semnalat corect ca git-ul lipsea complet (nu doar
"nu se executa"): `files/toolchain/git/` era gol, iar `files/home/.ssh/` la fel.

**Ce s-a facut (reconstruire completa, dupa `git_build_recipe.md`):**
- surse descarcate pe device (git 2.47.1, libssh2 1.11.1, nghttp2 1.64.0, dropbear 2024.86)
  si compilate nativ (clang 21 + lld); md5shim, NO_PTHREADS, CURL_CONFIG fals ca in reteta.
- git instalat in locul durabil `files/toolchain/git/` (bin/, lib/, libexec/git-core/ cu 172
  helper-e, share/git-core/templates).
- **capcana noua (helper-ele)**: `git-remote-https` si `dbclient` sunt ELF-uri; git le executa
  DIRECT -> "cannot exec 'remote-https': Permission denied" / "remote helper 'https' aborted
  session". Fix: fiecare ELF din libexec + binarele dropbear au fost invelite in lansatoare
  shwrap (`libshwrap_exec.so`), cu scriptul `<nume>.sh` in ACELASI director din care e invocat
  symlinkul (`libshwrap_exec.so` deriva scriptul din `dirname(argv[0])+basename+".sh"`).
  Fara `.sh`-ul in libexec-ul git: "files/tmp/git-remote-https.sh: No such file or directory".
- **capcana noua (chei dropbear)**: `dropbearkey -f <k>` scrie cheia in format DROPBEAR nativ,
  deci `dropbearconvert openssh dropbear <k>` da "File does not begin with OpenSSH key header".
  Ordinea corecta: intai `dropbearconvert dropbear openssh` (pentru cheia publica/privata
  OpenSSH folosita de GitHub), apoi `openssh dropbear` pentru `.db`-ul cerut de dbclient.
- **cheie SSH NOUA generata pe device** cu `dropbearkey -t ed25519` (cea veche a operatorului
  fusese stearsa); cheia publica a fost adaugata de operator in GitHub; autentificarea a fost
  confirmata ("Hi fetidness! You've successfully authenticated").
- **dovada finala**: `git clone --depth 1 git@github.com:fetidness/android_agent.git` -> rc=0,
  899 fisiere; si clone HTTPS -> rc=0.

**README corectat (4 inconsistente reale, gasite prin masurare, nu presupunere):**
- tabelul de sus spunea `.assets_v197` / `agent.py` 187 915 B / `toolchain.py` 62 737 B;
  real (masurat in clona): **`.assets_v252`** / **233 337 B** (3549 linii) / **153 965 B**.
- OP.7 spunea "acum `.assets_v184`"; real `.assets_v252`.
- afirmatia "`assets/python/agent.py` este COPIA versiunii v2" e FALSA: `agent-android-v2.py`
  din radacina e inghetat la 25 sept (180 558 B / 2696 linii), in timp ce `assets/python/agent.py`
  e codul viu (233 337 B / 3549 linii); md5 diferit, niciunul substring al celuilalt.
- OP.3 folosea exemplul v115/v116 la un marker care acum e v252 (comenzile `sed` pareau corecte
  dar se refereau la alt fisier) - actualizat la v252/v253.

**Nota de proces:** toate cifrele corectate au fost MASURATE pe clona inainte de editare
(`wc -c`, `grep -n assets_v MainActivity.kt`, `md5`); regula OP.7 din readme cere explicit asta.

### 2026-10-03 (optimizari din conversatia de build a agentului - `.assets_v252`)

- reguli noi in prompt: (3s) fara concluzii de mediu fara test ("SELinux blocheaza exec" si "grep e
  mut" au fost FALSE si au costat ~60 de pasi); (3t) fara pipe in comenzile bg; (3u) nu patch-ui
  binarul git; (3b) rescrisa (exec din filesDir se testeaza, nu se presupune).
- `_ensure_git_config()`: files/home/.gitconfig (identitate + safe.directory + fara gc/maintenance) -
  fara ea update-ref/fetch/clone crapa cu SIGSEGV (rc=139).
- launcher git: GIT_CONFIG_NOSYSTEM=1 + GIT_TEMPLATE_DIR (fara warning-uri la fiecare comanda);
  `_ensure_git_toolchain()` creeaza etc/gitattributes gol la prefixul compilat si copiaza dropbearkey.
- `(no output)` reparat in toate cele 3 locuri (bash/bg/run_su) cu mesaj explicit.
- garda adbsh nu mai blocheaza comenzile cu pipe/heredoc care doar mentioneaza filesDir.
- driver (assets) + reteta: prefix durabil, configure --host, ifndef_wrapper prin sh, CFLAGS cu
  toate -I si -DLOCALOPTIONS_H_EXISTS (command-line CFLAGS anuleaza CFLAGS += din Makefile).

### 2026-10-03 (cauza reala a pierderii git-ului: extractToolchain stergea files/toolchain - `.assets_v250`/`v251`)

- `extractToolchain()` pastreaza `files/toolchain/git` peste update-uri (mutat in `files/git_keep`
  inainte de stergere, pus la loc dupa) - altfel fiecare update de APK distrugea git-ul compilat
  pe device.
- `_ensure_git_toolchain()` accepta si `files/tmp/gb/prefix` (driverul din assets), nu doar vechiul
  `gitbuild/prefix`.
- `_ensure_git_launcher()` scrie `GIT_EXEC_PATH` spre libexec-ul DURABIL (fara el, dupa stergerea
  build tree-ului, `clone https` cade cu "remote-https is not a git command"); launcherul copiaza
  si `libexec/git-core` + template-urile.

### 2026-10-03 (git reconstruit de la zero; reteta validata si corectata - `.assets_v249`)

- reteta corectata cu 12 capcane dovedite (vezi readme Etapa 90): /sdcard fara symlink-uri, xz
  lipsa, git NU se configureaza, CC/AR/RANLIB explicite, flag-uri complete in CFLAGS, NO_CURL
  pacaleala din make, NO_PTHREADS, shim MD5 + allow-multiple-definition + start-group,
  install cu aceleasi variabile, libexec/git-core obligatoriu, dropbear (crypt/getpass/UA).
- driver livrat in assets (git_build_zero_driver.py).
- bash: output gol -> mesaj explicit.
- dovezi: git 2.47.1 de la 0; clone HTTPS rc=0; dbclient auth OK; ls-remote SSH rc=0.

### 2026-10-03 (git durabil in files/toolchain/git + reteta de reconstructie in APK - `.assets_v248`)

- `_ensure_git_toolchain()`: muta esentialul in files/toolchain/git (bin/git, dbclient,
  dropbearconvert, libnghttp2) - idempotent pe fiecare piesa, lista explicita de librarii.
  Dovada: cu LD_LIBRARY_PATH doar pe locatia durabila, git --version + ls-remote SSH merg.
- `assets/python/git_build_recipe.md`: reteta completa de reconstructie (surse, flag-uri,
  dropbearconvert, known_hosts, verificari); regula (3r) o refera.
- cheia SSH ramane DOAR in files/home/.ssh; assets verificate (fara material de cheie).

### 2026-10-03 (git prin SSH functional pe device: cheia operatorului + dropbearconvert - `.assets_v247`)

- cheia operatorului copiata in files/home/.ssh (chmod 600) si convertita in format dropbear
  (dbclient nu citeste OpenSSH: "Exited: String too long"); dropbearconvert construit pe device.
- known_hosts cu cheile GitHub verificate prin fingerprint.
- dovezi: dbclient -> "Hi fetidness! You've successfully authenticated"; git ls-remote SSH rc=0;
  clone+commit+push --dry-run rc=0.
- lansatorul git seteaza automat GIT_SSH_COMMAND (si converteste cheia daca lipseste .db).
- regula (3q): SSH preferat, HTTPS+token alternativ. Nota de securitate: revocare cheie daca
  telefonul se pierde.

### 2026-10-03 (git compilat pe device: verificat functional + lansator + regula (3q) - `.assets_v246`)

- git 2.47.1 (compilat nativ de agent) VERIFICAT: init/add/commit/log, push end-to-end (repo local),
  clone HTTPS de pe GitHub -> rc=0. "SIGSEGV-ul" raportat era un test greșit (blob intr-un branch)
  plus un lansator propriu care seta GIT_EXEC_PATH/GIT_TEMPLATE_DIR (cu ele binarul crapa -11).
- `_ensure_git_launcher()`: `files/tmp/git` + git.sh (env dovedit, identitate implicita de commit).
- regula (3q): nu recompila git; push prin HTTPS cu token.

### 2026-10-02 (checkpoint: stare verificata si consolidata - `.assets_v245`)

- readme: secțiune "STARE LA CHECKPOINT" - tabel de capabilitati cu dovezile de pe device,
  evolutia rundelor E2E (271/~130k -> 64/~7k tokeni, ultimele doua cu zero "Permission denied"),
  clasele de probleme inchise in v240-v245 si ce ramane neatins (grpcio, duckdb, kiwisolver).
- git: commit de checkpoint (docs) dupa v245.

### 2026-10-02 (clang/clang++ auto-flags; zero Permission denied in E2E - `.assets_v245`)

- `_ensure_cc_wrappers()`: clang/clang++ (shwrap + .sh) completeaza --target/--sysroot/-I/-L doar
  cand lipsesc; cmake/meson/pip (care dau flag-urile lor) merg pe calea bruta.
- dovada: C si C++ fara flag-uri -> rc=0 si ruleaza; meson setup+ninja+run OK.
- E2E v244: 64 intrari / ~7k tokeni, 0 "Permission denied".

### 2026-10-02 (deps/bin executabil, -L files/libs in LDFLAGS, mediu complet in os.environ - `.assets_v244`)

- `_fix_dead_binaries()` acopera si `deps/bin` (pkg-config/pkgconf -> symlink; xml2-config/xslt-config sterse).
- LDFLAGS: `-L<files/libs>` PRIMUL -> `-lpython3.14` se rezolva (dovada: extensie Python rc=0, import OK).
- regula (3e): exec corect = subproces din python sau linker64 (nu `sh -c`, nu /sdcard).
- os.environ primeste TOT mediul de toolchain la pornire (bash/cargo/maturin/cmake/meson).

### 2026-10-02 (verificarea sesiunii oprite: meson era tot clang-21 mort; reguli anti-drum-gresit - `.assets_v243`)

- meson: sanity check eșua pentru ca $CC = toolchain/bin/clang-21 era binarul real neexecutabil
  (fixat in v242). Dovada: meson setup rc=0 in 5s, ninja rc=0, binar ruleaza (MESON_OK 1.414).
- regula (3o): comanda care reuseste separat -> suspecteaza mediul tau, nu biblioteca.
- regula (3p): temporare in $TMPDIR, nu /tmp sau /sdcard.

### 2026-10-02 (eliminate binarele LLVM moarte din assets; symlink-uri executabile - `.assets_v242`)

- `_fix_dead_binaries()`: fisier REAL in filesDir = neexecutabil (W^X) -> symlink catre lib-ul
  APK-ului; cele fara echivalent sunt sterse (raportat: "toolchain/bin/clang-21: Permission denied").
- assets/toolchain/bin/ sters (192 MB) - numele sunt recreate ca symlink-uri la pornire.
- dovada: 20 binare reparate, `clang-21 --version` rc=0.

### 2026-10-02 (mesonpy stub din zip rupea numpy; reparatie reale de backend - `.assets_v241`)

- `_repair_build_backends()`: verifica si reinstaleaza CURAT meson-python + ninja (stub-ul din
  pysitepkg.zip nu are hook-urile PEP 517) inainte de fiecare pip_install.
- capcana: meson-python 0.22.1 n-are `prepare_metadata_for_build_wheel` si are 6 fisiere/31 kB ->
  criteriul de sanatate = `build_wheel` + `__init__.py` > 20 kB.
- dovada: metadata numpy rc=0 in 155 s (inainte: esec la metadata).
- `tools/probe_run.sh` foloseste acelasi PYTHONPATH ca agentul (probe fidele).

### 2026-10-02 (fix-uri din sesiunea cu multe erori: bg in-app, garda adbsh, env cmake, reparatie backend - `.assets_v240`)

- `bg` ruleaza implicit in procesul aplicatiei (uid app) cu mediu de toolchain; adbsh doar pentru
  /data/local/tmp, run_su sau uid=2000 explicit. Inainte: "cd files/tmp/...: Permission denied".
- garda in adbsh: comanda care atinge filesDir -> instructiune clara (confuzia uid 2000 vs app).
- env de build (PREFIX/CMAKE_ROOT/TMPDIR/CARGO_HOME) setat la pornire -> `cmake` merge fara setari.
- `_repair_build_backends()`: detecteaza si repara instalari incomplete (pathspec._backends,
  scikit_build_core._compat) inainte de pip_install.
- `.rs` -> mesaj clar (cargo, target/aarch64-linux-android/release).

### 2026-10-02 (pornire complet curata in UI - `.assets_v239`)

- scoase si liniile "[key] cheie gasita - pornesc agentul." si "[key] pornesc agentul..." /
  "[key] cheia salvata in ..." (cerut de operator). Pe ecran raman DOAR erorile (ex.
  "LIPSA CHEIA DeepSeek API"). Verificat pe device: ecran gol + prompt la pornire.

### 2026-10-02 (UI curat la pornire - `.assets_v238`)

- `[pas2] PATH aplicat` si cele 6 mesaje `[toolchain] ...` informative de la pornire NU se mai
  afiseaza in UI (cerut de operator). Raman vizibile doar erorile; diagnosticul complet se poate
  reactiva cu AGENT_VERBOSE=1.

### 2026-10-02 (runda 3 E2E de la zero: 56 intrari / 6,2k tokeni, zero erori - `.assets_v237`)

- verificat: `files/cargo/config` deprecat nu mai exista (Rust cu build.rs merge), LDFLAGS contine
  calea clang runtime pentru -latomic.
- regula noua (3l): scripturile de test ale agentului sa fie rulate si reparate (typo-uri), nu
  rescrise de la zero; flag-urile de compilare se iau din `toolchain action=env`.

### 2026-10-02 (runda 2 E2E: Rust build.rs + pip build-backend reparate - `.assets_v235`)

- `_cleanup_stale_cargo_config()` la pornire: sterge `files/cargo/config` (deprecat, preferat de
  cargo) care pastra `linker=cc-rust` -> "build-script-build: Permission denied" la orice crate cu
  build.rs. Dovada: crate cu quote -> rc=0.
- pip: interpretor `files/tmp/python3` + PYTHONPATH cu site-packages inaintea pysitepkg.zip ->
  dispare "BackendUnavailable: Cannot import setuptools.build_meta" (cmarkgfm/msgpack/ujson).
  Dovada: pip_install msgpack -> exit 0.
- garda binar: prag conservator (fals pozitiv pe 1.8KB de text).
- env: nota sa nu suprascrie PREFIX/CMAKE_ROOT.

### 2026-10-02 (test E2E cu memoria stearsa; 6 fixuri + o concluzie gresita a agentului - `.assets_v234`)

- Fortran in action=compile prin wrapper (inainte "gcc frontend command failed").
- cargo config: DOAR config.toml (duplicatele `config`/`.cargo` sterse - cargo folosea varianta veche).
- garda binar: nu mai declanseaza pe text cu ANSI (ESC exclus, prag 25%).
- PYTHONPATH: site-packages inainte de pysitepkg.zip (pybind11.get_include() corect).
- env: PREFIX=<toolchain>/sysroot/usr + CMAKE_ROOT (cmake, 4 incercari pierdute inainte).
- INFIRMAT: "Rust cu build.rs e imposibil" - de fapt merge (rc=0); cauza era target/ copiat de pe
  /sdcard. Regula noua (3k); pyo3/maturin deblocate.
- launcher-ele de module (cython/pip/f2py) se scriu si in toolchain/bin.

### 2026-10-01 (adbsh stabil: op_adbkey; helper probe in git - `.assets_v231`)

- adb_client: prefera `files/op_adbkey` (cheia autorizata a operatorului) fata de `files/adbkey`
  (pe care adb_setup o regenereaza) -> AUTH_SIGNATURE acceptata instant (0.0s, uid=2000).
- mesaj de eroare extins cu varianta op_adbkey.
- `tools/probe_run.sh` (+ temp/mk.sh) in git: versiunea veche s-a pierdut la curatenia din temp/.
- baterie post-v230: selftest lipsa=[], python3 minimal OK (+numpy), compile C/C++ rulate, pip 14s.

### 2026-10-01 (optimizari din E2E-ul de 121k tokeni - `.assets_v230`)

- `files/tmp/python3`/`python`: lansatoare auto-suficiente (PYTHONHOME/PYTHONPATH/TMPDIR/LD_LIBRARY_PATH)
  - rezolva esecul "pip install numpy (exit 1, 19s)" (pip isi lansa backend-ul fara mediu).
  Dovada: python3 cu env minimal -> PY3_OK; numpy rc=0 in 162s.
- cargo: config GLOBAL in $CARGO_HOME/config.toml (nu mai depinde de cwd) - rezolva exit 127 la Rust.
- `action=compile`: mesaj clar cand sursa lipseste (nu FileNotFoundError) + detectie Python.h sigura.
- env: exemplul cmake include export PREFIX (fara el CMakeDetermineSystem esueaza).
### 2026-10-01 (fix crash: tempfile pe /sdcard omora agentul - `.assets_v229`)

- cauza: `py()` -> `tempfile.TemporaryFile(dir=WORK)` (/sdcard, FUSE) -> excepție neprinsa -> proces mort.
- fix: fallback in lant WORK -> files/tmp -> tmp implicit -> BytesIO + `_raise_fd_limit()`;
  garda pe `call_tool` (excepția devine rezultat de tool, agentul continua).
- dovedit cu fd-uri epuizate (64): codul ruleaza in continuare.

### 2026-10-01 (adbsh reparat definitiv: AUTH_SIGNATURE; Fortran pe wrapper - `.assets_v228`)

- adbsh/uid2000: adbd ignoră RSAPUBLICKEY când cheia e deja autorizată -> acum semnăm token-ul
  (`AUTH_SIGNATURE`, RSA PKCS#1v1.5/SHA1) întâi; dovedit: `id` -> uid=2000(shell) în 0.1s.
- mesaj explicit când adbd nu răspunde (instrucțiuni Allow) + `shared()` nu mai cachează conexiuni rupte.
- app folosește cheia ADB deja autorizată a operatorului (files/adbkey) -> fără dialog.
- Fortran: doar wrapperul `files/tmp/flang` (driverul brut eȘUEAZĂ); env afișează calea corectă.
- prompt (3f): linker64 cale absolută, .so în files/libs pentru import, Fortran pe wrapper,
  nu insista pe adbsh când cere autorizare.
- proces: py_compile ÎNAINTE de push (un edit cu ghilimele duble a spart agent.py pe device).

### 2026-10-01 (preflight reparat, C++ libc++ implicit, pyext automat - `.assets_v227`)

- preflight: deleaga la selftest (varianta pe script shell folosea caile vechi -> raporta totul fals).
- LDFLAGS: `-L files/libs` + `-lc++_shared` (C++ se leaga fara flag-uri: CXX_DEFAULT=9).
- `_stable_libs()`: asigura si libpython3.14.so; compile adauga `-lpython3.14` automat pentru .so
  cu Python.h (import OK, dublu(21)=42).
- prompt: corectata afirmatia perimata despre /data/local/tmp / uid 2000.
### 2026-10-01 (optimizari din testul uid-2000 + toolchain - `.assets_v226`)

- adb_client: demultiplexare corecta shell-v2 (`_demux_shellv2`) - header-ele de substream
  (stdout/stderr/exit) nu mai ajung in output ("gunoi binar" raportat in doua sesiuni).
- `toolchain action=compile`/`run`: compilare IN PROCESUL APLICATIEI (nu prin adbsh, care nu poate
  citi filesDir) + rulare automata a binarului. Dovada: C -> HELLO_FROM_COMPILE, C++ -> CPP=5.
- prompt: regula (3d) Rust prin cargo (nu rustc direct), regula (3e) exec ELF direct / scripturi.
### 2026-10-01 (fix adbsh: nu mai executa nimic - `.assets_v225`)

- Cauza: `run_adbsh_tool` prefixa comenzile cu `. <filesDir>/toolchain_env.sh` (fisier app-privat,
  necitibil de uid=2000) -> "Permission denied" + desync de protocol -> TOATE comenzile adbsh
  returnau blob-ul binar `\x03\x01\x00\x00\x00\x01`.
- Fix: scos prefixul (inutil: toolchain-ul e al aplicatiei) + garda anti-desync (reconectare,
  o reincercare, apoi raportare explicita in loc de output binar).
- Dovada: `run_adbsh_tool('id')` -> uid=2000(shell); `echo`/`ls` reale.

### 2026-10-01 (E2E UI + rpath stabil - `.assets_v224`)

- E2E din UI: task "instaleaza cu pip_install pachetul wrapt..." -> 6 pasi, 25 s, tok ↑26.8k ↓916,
  hit 99%; wrapt instalat (exit 0), numpy 2.5.3 verificat de agent (BLAS: openblas).
- Agentul a raportat: dupa update de APK, binarul compilat anterior nu-si gaseste libc++_shared
  (rpath catre nativeLibraryDir = cale volatila).
- Fix: `_stable_libs()` (files/libs, copie stabila de libc++_shared.so) + rpath stabil in LDFLAGS.
  Verificat: binar compilat inainte de update ruleaza si dupa ("RPATH_OK=12").
- Reteta testare UI pe acest ROM: text cuvant cu cuvant + `input keyevent 62` (`%s` nu e tradus).

### 2026-10-01 (pachete refacute dupa fix-ul de site-packages)

- Reinstalate pe device: numpy 2.5.3, orjson 3.12.0, cbor2 6.1.4 (necesita setuptools-rust),
  Pillow 12.3.0, cffi 2.1.1, apsw 3.53.4.0, zstandard, lz4, msgpack, regex, simplejson.
- Neinstalat: kiwisolver (build eșuat; folosit doar de matplotlib).

### 2026-10-01 (FAZA 4j: numpy compileaza pe device - `.assets_v223`)

- `shwrap`: rezolva argv[0] prin PATH (meson il chema cu nume simplu -> "cython.sh: No such file").
  Reconstruit static cu NDK; verificat `cython -V` din orice cwd.
- launcher-e noi: `cython3`, `cython-3`, `f2py`, `pip`, `pip3`.
- `env` propriu (shwrap + env.sh): toybox env de pe Android executa gresit comenzile meson
  ("env: exec -m: No such file or directory") -> numpy pica la codegen. Pattern `[A-Za-z_]*=*`
  pentru ca calea APK contine `==`.
- rezultat: numpy 2.5.3 instalat pe device in 174 s (meson-python, ninja, clang, Cython 3.3.0,
  OpenBLAS 0.3.29); det([[1,2],[3,4]]) = -2.0 si dupa update de APK. orjson 3.12.0 reinstalat OK.

### 2026-10-01 (FIX CRITIC: pachetele pip mureau la update-ul de APK - `.assets_v220`)

- Cauza: MainActivity salva `site-packages` in `site_packages_keep` dar NU il restaura niciodata ->
  fiecare `adb install -r` stergea pachetele instalate cu pip (numpy, cbor2, orjson...).
- Fix: restaurare cu overwrite=true dupa re-extragerea assets (pachetele agentului au prioritate).
- Dovada: `pip install six` + rebuild/install APK -> six inca prezent si importabil.
- Neinchis: numpy (meson-python sanity-check exec -> Errno 13 Permission denied in files/tmp).

### 2026-10-01 (FAZA 4i: 5 bug-uri reale din "fa test complet toolchain" - `.assets_v219`)

- pip: in-process -> SUBPROCES (cauza reala a `KeyError('prefix')`); env complet + stdlib_extra primul.
- `env`: scrie efectiv `toolchain_env.sh` (inainte trimitea la un fisier inexistent); sh -n + sursare OK.
- `_toolchain_exports()`: filtreaza cheile care nu sunt identificatori shell (`CC_aarch64-...`).
- LDFLAGS: `-Wl,-rpath,nativeLibraryDir` + deps/lib -> binarul isi gaseste libc++_shared la rulare
  (inainte: "CANNOT LINK EXECUTABLE ... libc++_shared.so not found").
- Launcher-e ELF (libshwrap) pentru cython/f2py/pip, nu scripturi in filesDir
  (inainte: "cython: Permission denied").
- CFLAGS: + `-L<TC>/lib/clang/21/lib/linux` (libatomic/compiler-rt statice la build dintr-un pas).

### 2026-10-01 (selftest auto-documentat - `.assets_v218`)

- `selftest()` intoarce `detalii`: clang 21.1.8 + libc++ (NU libstdc++), FLANG (NU gfortran),
  rustc/cargo 1.98.1 + maturin 1.15.0, cmake/ninja/make/meson/scikit-build-core/setuptools/
  cython/pybind11, perl 5.42.0, binare+rulare ELF (linker64), build-dir files/tmp.
- Regula (0) din prompt: rapoartele folosesc numele reale din `detalii`.
- Confirmat: dupa optimizari, "verifica toolchain complet" = 4 pasi / ~850 tokeni (inainte 40/~7k).

### 2026-10-01 (optimizari pe baza conversatiei - `.assets_v217`)

- `toolchain action=env`: 7417 -> 2418 caractere (-67%), cu exemple copy-paste pentru C/C++/
  extensie Python/Fortran/Rust/cmake + regula de build-dir + comanda linker64.
- `multi` cu kind necunoscut: mesaj explicit (inainte executa body-ul ca bash -> "sh: all: ...").
- Prompt (3c): se compileaza in files/tmp/workspace, nu pe /sdcard (noexec -> nu se poate mapa).
- CFLAGS/LDFLAGS: `-resource-dir` + `-L.../clang/21/lib/linux` (libatomic/compiler-rt statice).

### 2026-10-01 (bug real in `pip_install` - ordinea PYTHONPATH - `.assets_v216`)

- Agentul a izolat: `toolchain action=pip_install` -> `exit 1 in 0s` / `KeyError('prefix')`.
  Cauza: zip-urile injectate in `sys.path` in ordinea gresita (`pysitepkg.zip` inaintea
  `stdlib_extra.zip`) -> `zipfile._path` lipseste -> `importlib.metadata` cade inainte de build.
  Fix: `stdlib_extra.zip` PRIMUL, in toate cele 3 locuri.
- Dovada: `pip install --force-reinstall MarkupSafe` -> rc=0 in 15s, import OK.
- CFLAGS/LDFLAGS: `-resource-dir=<TC>/lib/clang/21` (clang prin symlink isi calcula gresit
  resource-dir) + `-L<TC>/lib/clang/21/lib/linux` (libatomic/compiler-rt statice).

### 2026-10-01 (binarele sunt si in `toolchain/bin` - `.assets_v215`)

- Agentul a raportat fals "lipseste cmake" (cauta in `toolchain/bin`, unde erau doar symlink-uri
  `llvm-*` neexecutabile). Fix: symlink-uri ELF catre nativeLibraryDir pentru toate uneltele, in
  `files/tmp` SI `files/toolchain/bin` (cmake, ninja, make, perl, clang, ar, llvm-ar, rustc,
  cargo, maturin, patchelf, ld.lld, cc-rust...).
- Dovedit: `toolchain/bin/cmake --version` -> cmake 3.31.6; `selftest` -> toate True, lipsa=[].
- Regula (3a) in prompt: unde sunt binarele + cum se verifica o capabilitate (toolchain action=env).

### 2026-10-01 (selftest fara fals negativ la cmake - `.assets_v214`)

- `selftest()` chema `toolchain/bin/llvm-ar` (neexecutabil din sandbox-ul app-ului) -> raporta
  fals `cmake: false`, desi cmake real functioneaza (confirmat de agent: configure+build+run).
  Acum `selftest()` creeaza lansatoarele din `files/tmp` inainte de teste si le prefera pe ele.
- Al treilea test din UI a confirmat: C, C++, Fortran, Rust, extensii Python, cmake+ninja -
  toate compileaza SI ruleaza pe device.

---

### 2026-10-01 (executia in domeniul app-ului - lansatori ELF - `.assets_v213`)

- `untrusted_app` nu poate executa scripturile din filesDir -> wrapper-ele `cc-rust`/`flang` erau
  moarte in fluxul normal al app-ului. Inlocuite cu lansatori ELF in jniLibs
  (`libccrust_exec.so`, `libshwrap_exec.so`).
- `setuptools` reinstalat automat daca lipseste (`_ensure_setuptools`, cu marker).
- `CMAKE_ROOT` documentat pentru apeluri directe de cmake.

### 2026-10-01 (reparatii definitive din conversatia agentului - `.assets_v212`)

- Fortran/flang: wrapperul traduce acum flag-urile de driver (`-c` -> `-emit-obj`) - flang
  compileaza pe device (dovedit).
- binutils (ar/ranlib/nm/strip/readelf/objdump) primite ca lansatoare in `files/tmp` (cmake nu
  mai da fals negativ).
- Rularea binarilor compilati: documentat `/apex/com.android.runtime/bin/linker64 <binar>` +
  regula in promptul agentului.
- `adbsh`: mesaj de eroare cu instructiuni cand adbd cere autorizare (dialogul Allow).
- `selftest` -> cmake=True, rust=True, cargo=True, fortran=True, lipsa=[].

### 2026-09-30 (TEST E2E DIN UI + reparatii toolchain)

- Test end-to-end: task din interfata -> agentul compileaza/verifica pe device (33 pasi).
- Reparate dupa test: `selftest()` verifica REAL `cargo --version` (era doar existenta);
  avertisment de RAM libera (`ram_liber_mb`/`ram_atentionare`); `libc++_shared.so` inapoi in
  arhiva Rust (regresie de impachetare); regula in `agent.py` ca LD_LIBRARY_PATH se prepend.
- `.assets_v210`: `selftest` -> rust=True, cargo=True.

### 2026-09-30 (FAZA 5: MATURIN + pachete Python cu backend maturin)

- `maturin 1.15.0` construit PE DEVICE (11m46s) -> `jniLibs/libmaturin_exec.so` + lansator in
  `files/tmp` + shim Python PEP 517 scris de `toolchain._ensure_maturin()`.
- **`orjson 3.12.0` compilat pe telefon in 28 s** si verificat functional (`ORJSON_RUST_OK`).
- rustc RECONSTRUIT cu `optimize = true` (cel vechi crapa cu SIGSEGV pe `typenum`).
- Capcane noi 49-54 in `readme.md` (optimize=false -> SIGSEGV; strip inainte de patchelf;
  cc-rs; `-resource-dir` pentru headere builtin; LTO cu bitcode LLVM 22 vs libLLVM 21;
  wrapper de linker pentru build-scripturi).
- APK `.assets_v207` (619 MB).

## 2026-09-30 (FAZA 4: RUST PE DEVICE - LLVM 21.1.8 + rustc/cargo 1.98.1, compilate de la 0)

**Obiectiv atins:** pachetele Python cu acceleratoare RUST se compileaza PE TELEFON. Zero Termux,
zero artefact precompilat de la terti: LLVM-ul si Rust-ul sunt construite de noi, cross, din sursa.

### Commituri
- `bd7ecf5` - **FAZA 4: Rust pe device** (LLVM + rustc + cargo cross-compilate)
- `19d2083` - **FAZA 4b: pachete Python cu Rust** (cbor2 6.x) - wrapper de linker pentru build-scripturi

### Piese construite (cross, pe laptop)
| piesa | sursa | rezultat |
|---|---|---|
| LLVM 21.1.8 | llvm-project-21.1.8.src.tar.xz | `libLLVM.so.21.1` (dylib, PIC, doar AArch64) |
| Rust 1.98.1 | rustc-1.98.1-src.tar.gz + stage0 oficial x86_64 | `rustc` ARM64 + `librustc_driver-*.so` |
| cargo | `x.py build --stage 2 src/tools/cargo` | `cargo` ARM64 (NEEDED doar libdl/libm/libc) |
| std | `x.py build --stage 2 library/std` | `rustlib/aarch64-linux-android/lib/*.rlib` + `.rmeta` |

### Livrare in APK (`.assets_v206`)
- binarele (`rustc`, `cargo`) -> `jniLibs/arm64-v8a/lib*_exec.so` + symlink in `files/tmp`;
- librariile grele + std -> `assets/toolchain/rust-libs.tar.gz`, extrase o singura data in
  `files/toolchain/rust/lib`;
- `toolchain.py`: `_ensure_rust()` (extragere + lansatoare + `files/cargo/config.toml` +
  wrapper de linker `files/tmp/cc-rust`), `rust_env()`, pas Rust REAL in `selftest()`;
- APK: 497 MB (de la 467 MB).

### Dovezi pe device (uid de app, toolchain din APK)
- `rustc 1.98.1` si `cargo 1.98.1` ruleaza (rc=0);
- program Rust (Vec + iteratori) **compilat si LINKAT pe telefon in 1.3 s** -> ELF ARM64 229 KB;
- `toolchain.selftest()` -> **`rust=True`, `cargo=True`, `lipsa: []`** (C, C++, extensii Python,
  Fortran, cmake, perl, Rust - toate capabilitatile);
- **`cbor2 6.1.4` cu accelerator RUST compilat de la sursa pe device** (710 s, wheel
  `cbor2-6.1.4-cp314-cp314-android_24_arm64_v8a.whl`), verificat functional
  (`CBOR2_RUST_OK {'a': [1, 2, 3]}`).

### Capcane noi dovedite (36-48, detaliate in `readme.md`)
PIC la dylib-ul LLVM; bootstrap-ul Rust isi deduce `bin/` din calea `llvm-config`;
`-lLLVM-21` (nu `-lLLVM-21.1`); `patchelf --add-needed libc++_shared.so` pe `librustc_driver`;
LLVM cu `AArch64;X86` pentru bootstrap; AGP dezarhiveaza asset-urile `.gz`; filtrul `data` din
Python 3.14 arunca pe symlink-uri absolute; `libunwind.a` lipseste din NDK; std-ul e in arborele
`stage1` + `.rmeta` obligatorii; **cargo nu propaga linker-ul catre build-scripturi** (wrapper
`cc-rust`); app-ul POATE executa binare din propriul filesDir (restrictia e doar pe
`shell_data_dir`/`/data/local/tmp`).

### Raman (cunoscute)
- pachete cu backend **`maturin`** (orjson, cramjam, pydantic-core) - in lucru (build-ul
  `maturin` ruleaza pe device, urmeaza livrarea in `jniLibs`);
- grpcio (link) si duckdb (RAM) - din lista veche.

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

**VERIFICAT pe device (instalare curata `.assets_v181`):**
- `pip install regex` -> exit 0, 23s; `import regex` + match OK (wheel `cp314-android_24_arm64_v8a`)
- `pip install zstandard` -> exit 0 (C + scikit-build-core) | `msgpack` -> exit 0 (C++)
- `markupsafe` -> exit 0; logcat dupa teste: ZERO "Fatal signal 11"
- site-packages-ul instalat de pip supravietuieste update-ului de APK (`site_packages_keep`)

### ★ Sesiunea 2b - TEST REAL DIN UI pe INSTALARE CURATA + 2 bug-uri reparate

**Testul de autonomie:** dezinstalare completa (date private + `/sdcard/Download/Agent`, inclusiv
cheia ADB) -> reinstalare de la zero -> doar cheia DeepSeek lipita in onboarding -> 73 permisiuni
acordate, accessibility ON, whitelist de baterie. Task dat DIN INTERFATA, fara indicatii de tool:
*"Vreau sa folosesc pachetul Python kiwisolver in scripturile mele de pe telefon."*

Rezultat: agentul a ales SINGUR `python` -> `toolchain status` -> `toolchain pip_install` ->
`python` (test functional). Kiwisolver 1.5.1 compilat NATIV pe telefon in 41s.

**Bug #1 - `CXX` ne-executabil** (greenlet): `[Errno 13] Permission denied .../toolchain/bin/clang++`.
`CC` avea symlink executabil in `files/tmp`, dar `CXX` arata spre binarul din `filesDir`
(untrusted_app NU executa de acolo) -> orice sursa C++ cadea.
Fix: symlink `files/tmp/clang++` (cu reparare cand tinta e moarta) + `_extra` ca la CC;
`clang`/`clang++` gestionate central in `_ensure_launchers()`.

**Bug #2 - cerinte de build ascunse** (kiwisolver): `BackendUnavailable: Cannot import
'setuptools.build_meta'`. Cu `--no-build-isolation` pip NU instaleaza cerintele din
`pyproject.toml`; setuptools ridica "Missing setup required dependencies: cppy", dar pip
raporteaza doar BackendUnavailable (cauza reala invizibila fara `-v`).
Fix: prima incercare ruleaza cu `-v`; cerintele lipsa se extrag din output, se instaleaza, apoi
se reia install-ul; daca tot esueaza -> retry cu build isolation. Rezultatul tool-ului include o
linie `pasi:` (ex. `deps(cppy)=0; retry_dupa_deps=0`).

**Verificat:** greenlet 3.5.6 (C++) exit 0 | kiwisolver 1.5.1 exit 0, 39s, `deps(cppy)=0` |
fastnumbers 5.2.0 compilat real prin agent, din UI (exit 0, 39s, import functional).

**Limite ramase (Tier 3, nu sunt autonomie completa):** Rust/maturin (cramjam, orjson,
pydantic-core, polars), cmake >= 3.29 (duckdb, pyarrow, llvmlite, onnxruntime), perl (grpcio asm),
LLVM dev (llvmlite/numba), torch (build >16 GB RAM), Fortran la RULARE (segfault).

**Marker: `.assets_v182`**

### ★ FAZA 0 (autonomie) - FUNDATIA: selftest + taxonomie de esec + wheelhouse (`.assets_v184`)

- `toolchain action=selftest`: compileaza+LINKEAZA real C, C++ (STL), extensie `Python.h` si Fortran,
  verifica uneltele si backends-urile; intoarce `ok[]`/`lipsa[]`/`timpi_s`/`verdict`.
  Verificat pe device: tot TRUE mai putin `cmake`/`rust`/`perl`; C 0.18s, C++ 2.03s, pyext 0.33s.
- taxonomie de esec (`rust_lipsa`, `cmake_lipsa`, `perl_lipsa`, `ram_insuficient`,
  `wheel_inexistent`, `eroare_build`, ...) + linia `[diagnostic] cod=... | lipseste: ... | urmatorul pas: ...`
  Dovada: `cramjam` -> `rust_lipsa`.
- wheelhouse `files/wheels` + `--find-links` + install OFFLINE (`--no-index`): `xxhash` salvat si
  reinstalat fara retea, "instalat din wheelhouse local (fara retea, fara compilare)".
- regresii prinse si reparate: `pip wheel --no-build-isolation` ascunde cauza cerintelor de build
  (revenire la `pip install` pentru drumul principal; `kiwisolver` re-verificat exit 0, 38s);
  doua subcomenzi pip in acelasi proces nu mai vad `--find-links` -> install din wheelhouse in
  proces nou.
- instalare curata + task din UI ("Poti instala pyarrow?") -> raspuns corect in 16.8s
  (`CMakeNotFoundError: Could not find CMake with version >= 3.25`).



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

**Sesiunea 2 - verificare finala pe `.assets_v181`:** `lxml 6.1.3` compilat pe device in 96s
(XPath functional, libxml2 2.15.4), `cbor2 6.1.4` -> exit 0. Commituri: `8279966`, `f97b6db`,
`bd8d72b`, `91a9fdc`, `1cf1f4f`.
