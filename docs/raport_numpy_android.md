# Raport build numpy 2.3.5 de la 0 pe Android (SM-A366B)

Data: 2026-09-23
Dispozitiv: Samsung SM-A366B, Android 16, aarch64, 8 core-uri
Scop: instalare numpy "de la 0" (compilat nativ, nu wheel descarcat)
Rezultat final: SUCCES - numpy 2.3.5 compilat si instalat

---

## 1. Eroarea mea principala: AM IESIT SINGUR FARA SA FINALIZEZ

Acesta e cel mai important punct al raportului, si il pun primul
tocmai ca sa nu se repete.

CE AM FACUT GRESIT:
- Dupa primul `toolchain bootstrap` care a raportat "PREFIX OK:
  clang=True make=True", am presupus ca totul e gata.
- Am dat un ultim pas de verificare (df/curl) si apoi AM TERMINAT
  TURUL fara sa instalez numpy. Am livrat un mesaj de "progres" in
  loc de rezultatul cerut.
- Operatorul a trebuit sa ma intrebe "de ce ai dat proces terminat"
  ca sa ma pun din nou pe treaba.

CAUZA REALA:
- Am confundat "un pas intermediar a reusit" cu "task-ul e gata".
  Criteriul de terminare era: `import numpy` functioneaza. Eu l-am
  inlocuit mintal cu "bootstrap a zis OK".
- M-am oprit exact in momentul cel mai inselator: status-ul
  raporta verde, dar realitatea pe disc era goala (vezi eroarea 2).

REGULA PE CARE O IAU DE AICI INAINTE:
- Task-ul e terminat DOAR cand ultimul pas de verificare (import +
  operatie reala) returneaza rezultatul cerut. "Un pas a zis OK"
  nu e criteriu de oprire.
- Daca un tool raporteaza succes, dar nu am verificat EFECTUL pe
  disc, nu am voie sa inchid tura.
- Niciodata sa nu inchei un tur cu "am facut X, urmeaza Y" cand
  operatorul a cerut Y-ul complet.

COST:
- Un tur pierdut complet + re-descarcare bootstrap + nervi.

---

## 2. EROAREA TEHNICA CEA MAI GRAVA: bootstrap "succes" dar prefix gol

SIMPTOM:
- `toolchain status` raporta: clang=true, make=true, python=true,
  pip=true, compile_test=true (toate verzi).
- Dar `/data/local/tmp/tpm/usr/bin` avea 0 fisiere.
- `du -sh /data/local/tmp/tpm` = 7.5K (doar env.sh).

CE SE INTAMPLA DE FAPT:
- Bootstrap-ul descarca 67 pachete .deb si le dezarhiveaza, apoi
  "instaleaza in prefix via shell". Instalarea propriu-zisa se face
  prin ADB SHELL (uid=2000 shell), in `/data/local/tmp/tpm/usr`.
- Acel director e creat de shell cu permisiuni `drwxrws---`
  (grup shell, NU world). Eu (agentul) rulez ca u0_a390.
- Deci: status-ul se uita la existenta unor markeri/binare prin
  adb shell (unde shell-ul are acces), deci vede "OK"; tool-urile
  mele `bash`/`python` ruleaza ca app si vad... nimic / Permission
  denied.

EROAREA DE PROIECTARE A TOOL-ULUI:
- `toolchain status` verifica din perspectiva altui user (shell)
  decat cel care va folosi rezultatul. Raporteaza succes pentru o
  instalare la care apelantul nu are acces.
- Nu exista un pas care sa valideze "poate userul curent sa
  execute clang/python?".

FIX FOLOSIT:
- Am trecut prin `adbsh` (uid shell) pentru TOATE operatiile pe
  prefix, nu prin `bash`/`python` (uid app).
- Am dat `chmod -R a+rX` pe prefix ca fisierele sa fie macar
  citibile de app.

CE AR TREBUI REPARAT IN TOOL (propunere):
- `status` sa raporteze DOUA coloane: "vazut de shell" si "vazut
  de app", si sa esueze explicit daca diff-ul e mare.
- Bootstrap sa faca `chmod -R a+rX` automat la final (sau sa
  instaleze intr-un prefix world-readable).
- Sa scrie un marker de versiune si sa-l verifice la status.

---

## 3. Eroare de mediu: PATH nu se aplica in shell-ul folosit

SIMPTOM:
- `source /data/local/tmp/tpm/env.sh; python3 -V` ->
  "sh: python3: inaccessible or not found".

CAUZA:
- env.sh exporta un PATH catre /data/local/tmp/tpm/usr/bin, dar
  la momentul respectiv prefixul era (aparent) gol din perspectiva
  userului app -> comanda negasita. De asemenea `sh -lc` din
  mediul app nu mostenea corect prefixul.

FIX:
- Am rulat totul prin `adbsh` cu env exportat inline (nu prin
  sourcing de env.sh in shell-ul app), si cu cai absolute.

---

## 4. Eroare: "can't execute: Permission denied" pe python3.14

SIMPTOM:
- Dupa ce am facut prefixul citibil, `/data/local/tmp/tpm/usr/bin/
  python3.14 -c "import numpy"` ->
  "sh: /data/local/tmp/tpm/usr/bin/python3.14: can't execute:
  Permission denied".

CAUZA:
- Chiar cu bit de read deschis, executia depinde de owner/permisiuni
  pe fisier (owner shell) si de faptul ca app-ul nu poate executa
  binare din prefixul altui uid. Read != execute pentru app.

FIX:
- Am rulat python-ul toolchain DOAR prin adbsh / /run_su (uid
  shell), niciodata direct din tool-ul `python`/`bash` al app-ului.

LECTIE:
- Toolchain-ul de pe acest telefon e "al shell-ului". Ca app, pot
  doar sa-l ORCHESTREZ prin adbsh, nu sa-l execut direct.
- Orice script pentru operator trebuie sa fie .sh si rulat cu
  /run_su (uid 2000), NU cu /run (uid app) - exact cum spune
  si memoria.

---

## 5. Lipsa meson (dependinta de build numpy moderna)

SIMPTOM:
- numpy >= 2.x se construieste cu meson-python, nu cu setuptools.
- In prefix NU exista meson dupa bootstrap.

FIX:
- `pip install meson meson-python Cython ninja pyproject-metadata
  packaging` in prefix.
- Verificat: meson 1.12.1 instalat.

NOTA:
- Am folosit `--no-build-isolation` la build ca pip sa NU mai
  descarce/construiasca dependintele intr-un mediu izolat (care
  ar eșua/pierde timp). Toate deps le-am pus manual in prefix.

---

## 6. Eroare de storage: tar pe FUSE a expirat silentios

SIMPTON:
- `tar xzf numpy-src.tar.gz` pe /storage/emulated/0 (FUSE) a
  returnat FARA OUTPUT si parea ca nu s-a intamplat nimic.

CAUZA:
- /storage/emulated e FUSE (lent); extragerea a 80MB a depasit
  fereastra de raspuns perceputa si comanda a iesit fara echo.

FIX / LECTIE:
- Am verificat EFECTUL (`du -sh`) - de fapt se extrasese (80M).
- Regula: build-ul il fac in /data/local/tmp (ext4/native, rapid),
  NU pe /storage (FUSE). Storage-ul il folosesc doar pentru
  fisierele finale pe care le vede operatorul.

---

## 7. De ce am reusit pana la urma: build-ul in fundal corect

Ce a functionat bine (de pastrat):
- Am pus build-ul intr-un `bg job` cu log dedicat, NU cu nohup/&.
- Am urmarit cu bg action=status (pid real, durata) si bg action=log
  (doar logul acelui job). Zero confuzie cu loguri vechi.
- Build numpy complet (metadata + wheel + install) a durat ~4
  minute pe telefon. Log-ul arata clar cele 3 faze pip.

Output real:
- Preparing metadata (pyproject.toml) - ~3 min (meson configure)
- Building wheel - ~1 min
- Created wheel: numpy-2.3.5-cp314-cp314-android_24_arm64_v8a.whl
  (7.0 MB, sha256 1b25e897...)
- Successfully installed numpy-2.3.5

---

## 8. Verificari finale (dovada ca task-ul E chiar gata)

- import numpy -> 2.3.5, __file__ in site-packages
- reduce: sum/mean corecte
- matmul 1000x1000: ~116 ms -> ~17 GFLOP/s
- fft 1M: ~70 ms
- linalg: det, inv, eigvals corecte
- random: functional
- pip show numpy -> Version 2.3.5
- Launcher /run_su numpy.sh -> "numpy 2.3.5 OK pe aarch64"

---

## 9. IDEI DE OPTIMIZARE (propuneri pentru reparatie)

### A. Pentru tool-ul `toolchain`
1. `status` sa aiba doua perspective: "shell" vs "app" (uid care
   va consuma rezultatul). Sa esueze explicit daca diff.
2. Bootstrap sa termine cu `chmod -R a+rX $PREFIX` (sau prefix
   world-readable din start), plus un marker `$PREFIX/.tc_version`.
3. Sa instaleze din start meson + meson-python + Cython + ninja
   (necesare pentru ORICE pachet cu C/C++ modern), nu doar pip gol.
4. `pip_install` sa foloseasca `--no-build-isolation` daca deps
   sunt deja in prefix (evita re-descarcare si build dublu).
5. Sa raporteze timpul pe faze (download / extract / install) ca
   operatorul sa vada unde se pierde timpul.
6. Un `action=doctor` care verifica: exec pe clang din perspectiva
   TUTUROR uid-urilor relevante (app + shell).

### B. Pentru fluxul de build
1. Build in /data/local/tmp (native), nu pe /storage (FUSE) -
   deja aplicat, dar merita automatizat.
2. Cache de wheel: sa pastrez
   numpy-2.3.5-cp314-...-android_24_arm64_v8a.whl undeva
   persistent, ca re-instalarea sa fie instant (nu 10 min).
3. BLAS: acum folosesc BLAS-ul intern numpy (17 GFLOP/s). Se
   poate urca mult cu OpenBLAS compilat aici, cu threading pe
   cele 8 core-uri. De testat NPY_BLAS_ORDER=openblas.
4. `-O3 -mcpu=native` / `-march=armv8.2-a+dotprod+fp16` la CFLAGS
   pentru SIMD mai bun (de testat ca nu rupe ceva).
5. CCACHE: cu ccache in PATH, rebuild-urile partiale devin
   aproape instant (numpy are mii de fisiere .c).
6. LTO off (implicit) - pe telefon creste timpul mult pentru
   castig mic; corect ca l-am lasat off.

### C. Pentru disciplina mea de agent (cel mai important)
1. Definesc "criteriul de terminare" la inceput (ex:
   `python -c "import numpy"` returneaza 0 si versiunea ceruta).
   Nu inchei turul pana nu-l ating.
2. Dupa FIECARE pas care raporteaza succes, verific EFECTUL
   (fisier exista? comanda ruleaza?), nu status-ul.
3. Daca un tool zice "OK" dar efectul lipseste -> tratez ca
   esec, nu ca succes, si investighez tool-ul.
4. Nu inchei niciodata un tur cu "am facut pasul X, urmeaza Y"
   cand sarcinile sunt clare si le pot duce la capat.

---

## 10. Rezumat pe scurt

Ce a mers: bootstrap (in final), build numpy in bg cu log, verificari.
Ce a esuat: status fals-pozitiv, permisiuni shell vs app, meson lipsa,
tar pe FUSE fara feedback, si CEL MAI GRAV - iesirea mea prematura.
Lectia cheie: "un tool a zis OK" != "task terminat". Verifica efectul,
nu raportul. Si nu te opri pana nu livrezi exact ce s-a cerut.
