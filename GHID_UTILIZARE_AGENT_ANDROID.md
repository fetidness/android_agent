# GHID DE UTILIZARE — Agent Android (net.sys32.agent)

> Manual complet pentru instalarea si folosirea agentului pe telefon.
> Citeste de la cap la coada inainte de prima instalare.

---


## 0. CE MERGE FARA CALCULATOR vs. CU CALCULATOR

> **Cea mai importanta distinctie din tot ghidul. Citeste-o prima.**

### FARA calculator — merge instant (tool-uri de aplicatie)
Aplicatia functioneaza SINGURA dupa instalare + permisiuni:

| Tool | Ce face |
|------|---------|
| `android` | senzori, camera, GPS, baterie, clipboard, notificari, TTS, WiFi, apps, intents, reflection SDK |
| `ui` | vede + controleaza alte aplicatii (read/find/click/settext/tap) |
| `python` / `bash` / `smart` | cod, fisiere, HTTP |
| `read` / `look` | fisiere mari, analiza imagini |

**Nu ai nevoie de nimic altceva.** Doar instalezi APK-ul + aprobi permisiunile.

### CU calculator — pentru SUPER-PUTERI (uid=2000)
Tool-ul `adbsh` (comenzi de sistem ca dezvoltator) **NU poate fi activat
din aplicatie** — Android interzice unei aplicatii sa deschida portul ADB.

Pentru `adbsh` ai nevoie:
1. **Un calculator** cu `adb` (Android Platform Tools — UN singur binar, ~15 MB)
2. **Cablu USB** (sau WiFi ADB)
3. **O comanda**: `adb tcpip 5555`
4. **O data**: aprobare "Allow USB debugging"

**Frecventa:** comanda `adb tcpip 5555` se ruleaza **din nou dupa fiecare
RESTART al telefonului** (portul ADB se inchide la reboot).

### Tabel comparativ

| Capacitate | Fara calculator | Cu calculator |
|------------|-----------------|---------------|
| Senzori, camera, GPS | ✅ | ✅ |
| Citire/control ecran (ui) | ✅ | ✅ |
| Fisiere, Python, HTTP | ✅ | ✅ |
| **Comenzi sistem (adbsh)** | ❌ | ✅ |
| `pm grant` (permisiuni altor app) | ❌ | ✅ |
| `settings put` (setari ascunse) | ❌ | ✅ |
| `dumpsys` complet, `logcat` | ❌ | ✅ |
| `input` fara accessibility | ❌ | ✅ |
| `screencap`, `uiautomator dump` | ⚠️ (prin `ui`) | ✅ |

> **Concluzie:** fara calculator ai un agent bun.
> Cu calculator (30 secunde o data) ai un agent cu puteri de dezvoltator.

---

## 1. CE ESTE

Un agent AI autonom care ruleaza DIRECT PE TELEFON (Samsung/Android 8+):
- vorbeste cu DeepSeek API (internet)
- vede ecranul, controleaza alte aplicatii
- citeste senzori, camera, GPS, baterie
- **ruleaza comenzi de sistem ca uid=2000 (shell)** — putere de dezvoltator, fara root

**Totul e in APK.** Nu trebuie sa instalezi nimic altceva pe telefon.

---

## 2. CE ITI TREBUIE

### Pe TELEFON
| Cerinta | De ce | Obligatoriu? |
|---------|-------|--------------|
| Android 8+ (API 26+) | aplicatia | ✅ DA |
| Permisiuni (le cere app-ul) | senzori, camera, fisiere | ✅ DA |
| Developer Options pornit | pentru ADB | ✅ DA |
| USB debugging pornit | pentru ADB | ✅ DA |
| Accessibility (Agent) | citire/control ecran | ✅ DA (pentru tool-ul `ui`) |

### Pe CALCULATOR (o singura data, apoi din cand in cand)
| Cerinta | Detalii |
|---------|---------|
| **`adb` (Android Platform Tools)** | ~15 MB, UN SINGUR BINAR. NU ai nevoie de Android Studio, SDK, drivere. |
| **Cablu USB** | pentru prima conectare |
| **~30 secunde** | o data dupa fiecare RESTART al telefonului |

**Descarcare platform-tools** (orice OS):
- Windows: https://dl.google.com/android/repository/platform-tools-latest-windows.zip
- macOS: https://dl.google.com/android/repository/platform-tools-latest-darwin.zip
- Linux: https://dl.google.com/android/repository/platform-tools-latest-linux.zip

**Instalare:** dezarhivezi, apoi folosesti `adb` din acel folder. Atat.

> **NU trebuie:** Android Studio, SDK Manager, drivere speciale Samsung, root, conturi.

---

## 3. INSTALAREA (pas cu pas)

### PASUL 1 — Pregatirea telefonului
```
1. Settings -> About phone -> Software information
2. Apasa de 7 ori pe "Build number"  -> "Developer mode enabled"
3. Settings -> Developer options -> USB debugging: ON
4. Conecteaza telefonul la calculator prin cablu USB
5. Pe telefon apare "Allow USB debugging?" -> apasa ALLOW
   (bifeaza "Always allow from this computer")
```

### PASUL 2 — Instalarea aplicatiei
```
1. Copiaza app-debug.apk pe telefon (sau: adb install app-debug.apk)
2. Deschide aplicatia "Agent"
3. APROBA TOATE PERMISIUNILE cerute (camera, microfon, locatie,
   contacte, SMS, telefon, fisiere, notificari)
4. Asteapta "AGENT CONFIGURATION IN PROGRESS..."
   -> countdown 30 secunde
   -> "AGENT FULLY CONFIGURED AND OPERATIONAL"
```

### PASUL 3 — Accessibility (pentru tool-ul `ui`)
```
1. Settings -> Accessibility -> Installed apps (sau "Installed applications")
   (pe Samsung: e sub "Advanced settings", deruleaza in jos)
2. Gaseste "Agent (control ecran)"
3. Porneste comutatorul -> ALLOW
```
> Fara asta: agentul NU poate citi/controla ecranul (tool-ul `ui`), dar restul merge.

### PASUL 4 — Activarea portului ADB (pentru SUPER-PUTERI uid=2000)
```
Pe CALCULATOR (cu telefonul conectat USB):
   adb tcpip 5555

Rezultat: "restarting in TCP mode port: 5555"
```

**ACUM** agentul are acces la `adbsh` (uid=2000).


---

## ℹ️ NOTA DESPRE PORT (auto-detectie)

**Poti folosi ORICE port** — aplicatia il detecteaza singura!

```
adb tcpip 5555      # merge
adb tcpip 55555     # merge
adb tcpip 5556      # merge
```

Agentul citeste automat `service.adb.tcp.port` si se conecteaza pe acel port.
Daca nu-l gaseste, incearca 5555, 55555, 5556.

**Recomandat:** `adb tcpip 5555` (standard, usor de tinut minte).

Verificare:
```
adb shell getprop service.adb.tcp.port     -> portul activ al adbd
```


---

## 4. FOLOSIREA ZILNICA

### Pornirea
Deschizi aplicatia -> agentul porneste automat -> scrii taskul -> trimiti.

### Ce poti cere (exemple)
```
"Deschide WhatsApp si trimite 'salut' lui Gab"
"Citeste-mi bateria si senzorul de lumina"
"Fa un screenshot si spune-mi ce vezi"
"Acorda permisiunea CAMERA aplicatiei X"
"Ce setari de sistem am ascunse?"
"Pune modul avion si da-mi telefonul pe silent"
```

### Dupa RESTART telefon
Portul ADB se inchide. Trebuie sa rulezi din nou **o data**:
```
adb tcpip 5555
```
(cu telefonul conectat USB)

**Restul (cheia, libs, config) se pastreaza** — nu se repeta.

---

## 5. CE POATE AGENTUL (capabilitati)

### Tool-uri native (rapide, instant)
| Tool | Ce face |
|------|---------|
| `android` | senzori, camera, GPS, baterie, clipboard, notificari, TTS, WiFi, apps, intents, reflection SDK |
| `ui` | VEDE + CONTROLEAZA alte aplicatii (read/find/click/settext/tap/swipe) |
| `python` | cod Python (stdlib + requests, bs4, yaml, toml) |
| `bash` | shell in sandbox-ul aplicatiei |
| `smart` | auto-router python/bash |
| `read`, `look` | citire fisiere mari, analiza imagini |

### Super-puteri (uid=2000, prin `adbsh`)
```
pm grant/revoke permisiuni runtime     appops set
settings put secure/global             dumpsys complet
input tap/text/keyevent (fara a11y)    logcat complet
screencap, uiautomator dump            getprop/setprop
run-as pe alte aplicatii               /proc/net, ip, svc, wm
```

### Limitari (nici shell nu le are fara root)
- `/data/data` (datele private ale altor aplicatii) — Permission denied
- `su` / root — nu exista
- BLOCARE/deblocare bootloader, flash — nu

---

## 6. PROBLEME FRECVENTE

| Simptom | Cauza | Solutie |
|---------|-------|---------|
| `adbsh` da timeout | portul ADB e inchis | `adb tcpip 5555` de pe calculator |
| "Allow USB debugging" reapare | cheie noua (reinstalare) | apasa ALLOW (o data) |
| Agentul nu vede ecranul | accessibility oprit | Settings -> Accessibility -> Agent -> ON |
| "no devices" pe calculator | cablu/USB debugging | verifica cablul + USB debugging ON |
| Agentul porneste dar nu raspunde | permisiunile lipsesc | Settings -> Apps -> Agent -> Permissions -> toate |
| Dupa update APK | accessibility se reseteaza | reactiveaza-l din Settings |

---

## 7. INTREBARI FRECVENTE

**Q: Trebuie sa fiu conectat la calculator mereu?**
A: NU. Doar o data pentru `adb tcpip 5555`. Apoi agentul merge singur
   (pana la restartul telefonului).

**Q: Trebuie root?**
A: NU. Agentul obtine uid=2000 (shell) legal, prin ADB local. Nu e root.

**Q: Trebuie Android Studio?**
A: NU. Doar binarul `adb` (~15 MB).

**Q: Merge pe orice telefon?**
A: Android 8+ (API 26). Testat pe Samsung SM-A366B (Android 16).

**Q: Ce se intampla daca restarteaza telefonul?**
A: Portul ADB se inchide. Rulezi iar `adb tcpip 5555` (30 secunde).
   Cheia, configul si memoria raman.

**Q: Datele mele sunt in siguranta?**
A: Agentul foloseste DeepSeek API (internet) pentru creier.
   Fisierele pe care le acceseaza depind de task-urile tale.
   NU are acces la /data/data altor aplicatii.

**Q: Cat de puternic e?**
A: Are practic puterea unui dezvoltator cu telefonul conectat prin ADB,
   dar fara root. Poate citi/scrie setari de sistem, acorda permisiuni,
   automatiza UI in orice aplicatie, citi log-uri, senzori, etc.

---

## 8. REZUMAT RAPID (checklist)

```
INSTALARE (o data):
  [ ] Developer Options ON
  [ ] USB debugging ON
  [ ] Instaleaza APK
  [ ] Aproba TOATE permisiunile
  [ ] Asteapta config (30s)
  [ ] Accessibility -> Agent -> ON
  [ ] adb tcpip 5555   (de pe calculator)

DUPA RESTART TELEFON:
  [ ] adb tcpip 5555   (repeti doar asta)

ZILNIC:
  [ ] Deschizi app -> scrii task -> trimiti
```


---

## 9. COMPILARE NATIVA PE TELEFON (Toolchain) - si LICENTE

Agentul poate instala SINGUR un toolchain complet de compilare (clang 21,
make, cmake, ninja/samu, git, python+pip, rust, libc++, openssl) si poate:

- instala ORICE pachet PyPI, inclusiv cele cu extensii C/C++/Fortran
  (numpy, pandas, pillow...) - compilate NATIV pe telefon
- compila cod C/C++ propriu in biblioteci partajate (.so)
- instala orice binar din repo-ul Termux (nano, htop, jq...)

### Cum se foloseste (agentul o face singur, sau tu prin el)
```
toolchain action=status        # ce e instalat
toolchain action=bootstrap     # instaleaza TOT (~500MB, o singura data)
toolchain action=pip_install package=numpy
toolchain action=compile source=/sdcard/x.c out=/sdcard/x.so
toolchain action=tpm package=nano
```


### 9.1 EXEMPLE PRACTICE (toolchain)

```
# 1. Verifica ce e instalat
toolchain action=status

# 2. Instaleaza toolchain complet (~600 MB, o data, 4-5 min)
toolchain action=bootstrap

# 3. Compileaza si ruleaza un program C
toolchain action=compile source=/sdcard/prog.c out=/data/local/tmp/prog
# (agentul detecteaza .so = biblioteca, altfel executabil)

# 4. Instaleaza un pachet Python CU compilare nativa
toolchain action=pip_install package=numpy

# 5. Instaleaza un binar Termux (nano, htop, jq...)
toolchain action=tpm package=nano
```

**TESTAT:** agentul a scris `calc.c`, l-a compilat cu clang 21 si a rulat
binarul -> `6 * 7 = 42`, totul pe telefon, fara PC.

**ATENTIE:** binarele se pun in `/data/local/tmp` (NU `/sdcard` - e noexec).

### LICENTE (important)
Aplicatia **NU include** niciun binar de compilare. La `bootstrap`, agentul
**descarca** unelte open-source din **repo-ul public Termux**
(https://packages.termux.dev), exact cum face `apt` pe orice Linux.

| Pachet | Licenta |
|---|---|
| clang / LLVM | Apache-2.0 with LLVM exceptions |
| python | PSF-2.0 |
| make, cmake | GPL-3.0 |
| ninja / samu | Apache-2.0 |
| openssl | Apache-2.0 |
| zlib, xz-utils | zlib / public domain |

- Descarcarea si **folosirea locala** nu creeaza obligatii de redistribuire.
- **Nu redistribuim** binarele in APK.
- Daca cineva impacheteaza aceste binare in alt produs, trebuie sa respecte
  licentele respective (inclusiv GPL pentru make/cmake).
- Termux mentine repo-ul pentru aplicatia Termux; folosirea lui de alt client
  este tehnica permisa (repo APT public) dar **neoficiala** (fara suport).

### Cerinte
- Spatiu liber: ~600 MB (toolchain complet)
- Internet (prima instalare)
- Nu necesita PC, root, sau aplicatia Termux

---

Sfarsitul ghidului.
