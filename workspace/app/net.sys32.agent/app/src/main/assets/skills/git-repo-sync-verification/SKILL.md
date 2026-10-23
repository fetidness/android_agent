---
name: git-repo-sync-verification
description: "Cum verifici ca un repo git contine EXACT ce ruleaza pe device inainte de un rebuild de APK (assets vs filesDir, md5 per fisier)"
---
# Verificarea sincronizarii repo <-> device inainte de rebuild

## When to Use
- inainte de un rebuild de APK, cand trebuie garantat ca sursa din repo produce
  comportamentul de acum
- dupa ce s-au modificat scripturi in filesDir (agent.py, skill-uri, assets)
- cand operatorul intreaba "ai pus tot in repo?"

## Method

### 1. Gaseste sursa care intra in build (NU presupune)
```
find . -name "agent.py" -o -name "adb_client.py"
```
Pe acest repo calea reala este:
`workspace/app/net.sys32.agent/app/src/main/assets/python/agent.py`
Fisierele din `filesDir` (`/data/data/net.sys32.agent/files/python/agent.py`)
sunt COPIA DE RULARE, nu sursa.

### 2. Copiaza prin punte (app si Debian nu se vad reciproc)
`/root` nu e vizibil din procesul app; `filesDir` nu e vizibil din Debian.
Puntea este `/storage/emulated/0/...`, vizibila din ambele:
```python
shutil.copy("/data/data/net.sys32.agent/files/python/agent.py",
            "/storage/emulated/0/Download/Agent/workspace/_push_agent.py")
```

### 3. Compara md5 per fisier, nu "git status"
Scrie md5-urile device intr-un fisier, apoi compara in Debian:
```python
# in app
h=hashlib.md5(); ... ; out.append(f"{md5}  {size}  {name}")
open("/storage/.../_dev_md5.txt","w").write("\n".join(out))
```
```bash
# in Debian
md5sum * > /tmp/repo_md5.txt
# apoi diff pe nume: doar-device / doar-repo / diferite / identice
```
Rezultatul care conteaza: numarul de IDENTICE, plus cele doua liste de diferente.

### 4. Verifica cele 4 puncte de integrare a tool-ului in agent.py
```bash
A=workspace/app/net.sys32.agent/app/src/main/assets/python/agent.py
grep -c 'if fn=="androidapi"' $A      # dispatcher-ul REAL
grep -c '"name":"androidapi"' $A      # lista T
grep -c 'def run_androidapi_tool' $A  # wrapper
grep -c 'ANDROIDAPI' $A               # TOOLGUIDE
python3 -c "import py_compile;py_compile.compile('$A',doraise=True);print('SINTAXA_OK')"
```

### 5. Verifica si fisierele ignorate care totusi conteaza
```bash
git status --ignored --porcelain | grep "^!!"
git check-ignore -v tools/x/y.py     # rc=1 = NU e ignorat
```

## Pitfalls
- `git status` curat NU dovedeste sincronizare: arata doar diferenta fata de HEAD,
  nu fata de ce ruleaza pe device -> compara md5 cu filesDir
- `files/memory.md` (canonic) difera de `files/python/memory.md` (copie veche);
  sursa corecta pentru repo este `files/memory.md`
- `key.txt` apare pe device dar NU trebuie in repo (`**/key.txt` in .gitignore) -> corect exclus
- `__pycache__/` apare ca ignorat -> normal, nu-l adauga
- skill-uri create pe device pot lipsi din repo: compara `os.listdir(filesDir/skills)`
  cu `ls assets/skills/` (asa a lipsit `git-push-debian-ssh`)
- `git clone` da tuturor fisierelor timestamp-ul clonarii -> `find -newermt` arata
  TOT, nu doar modificarile reale; foloseste `git status --porcelain` (0 linii = curat)
- scripturile auxiliare CARE trebuie sa existe dupa instalare merg in `assets/python/`,
  nu in `tools/`: `tools/` NU se instaleaza, deci acolo ramane doar ce e strict pentru
  Debian. Daca operatorul cere "out of the box", muta scriptul in `assets/python/`
- `assets/toolchain/` lipseste din repo si e CORECT: e in .gitignore (257 MB) si se
  regenereaza cu `workspace/app/build_toolchain.sh`
- `memory.md` e exclus de regula globala din .gitignore -> orice copie livrata in APK
  are nevoie de o exceptie explicita (`!workspace/.../assets/memory.md`)

## Ce extrage automat APK-ul (verificat in MainActivity.kt)

Inainte de a decide unde pui un fisier, citeste ce cere codul:
```bash
cd workspace/app/net.sys32.agent/app/src/main/java/net/sys32/agent
grep -oE 'assets\.open\("[^"]+"\)' MainActivity.kt | sort -u
grep -oE 'copyDir\("[^"]+"' MainActivity.kt | sort -u
```
Rezultat real pe acest repo:
- `assets.open("memory.md")` -> citit din RADACINA assets/, nu din assets/python/
- `copyDir("binder"|"proot"|"python"|"skills"|"toolchain")` -> copiate recursiv

Stampila de re-extractie e `versionCode-lastUpdateTime` (`.assets_stamp`), deci orice
update de APK re-extrage automat `assets/python/` in `files/python/`. Nu trebuie
bumpat nimic manual.

### Verificare "out of the box" inainte de push
```bash
cd workspace/app/net.sys32.agent/app/src/main/assets
for d in memory.md binder proot python skills toolchain; do test -e "$d" && echo "OK $d" || echo "LIPSA $d"; done
```
Daca `assets.open()` cere un fisier care nu exista, citirea esueaza SILENTIOS
(`try { } catch (_: Exception) {}`) si instalarea curata porneste fara el.

## Pitfalls specifice scripturilor livrate in assets
- caile hardcodate (`/data/data/net.sys32.agent/files/python`,
  `/storage/emulated/0/.../bridge`) crapa dupa rebuild -> auto-detecteaza filesDir
  urcand din `Path(__file__).parent` si cautand `pyhome` sau `python`; accepta
  `AGENT_FILES_DIR` / `AGENT_BRIDGE_DIR` ca override
- `adb_client` scrie `[adb] ...` pe stdout DIN ALTCONT THREAD, deci
  `contextlib.redirect_stdout` NU il prinde -> output-ul JSON se delimiteaza cu
  markere (`<<<ANDROID_API_JSON>>>` ... `<<<END_ANDROID_API_JSON>>>`) sau se
  parseaza cu `json.JSONDecoder().raw_decode()` de la primul `{`

## Verificarea finala dupa push (nu doar inainte)
```bash
cd ~/android_agent
git fetch -q origin
git rev-parse HEAD
git rev-parse origin/master     # trebuie sa fie IDENTICE
git status --porcelain | wc -l  # 0 = curat
```
Output real: `local 069286d28e80a77559305ad5a4af1cddf204d4e3`, `remote 069286d...` -> sincron.

## Pitfalls la comenzile de verificare (masurate)
- in `terminal`/`adbsh` comanda care contine `$(...)` sau `$()`+CULORI poate iesi cu
  "cmd lipseste" sau output gol -> ruleaza comenzile separat, fara substitutie de comanda
  (`git rev-parse HEAD` singur, nu `echo "$(git rev-parse HEAD)"`)
- `bash` tool-ul ruleaza cu PATH minimal si NU vede `/root` (proot) -> pentru repo-ul din
  Debian foloseste tool-ul `terminal`, nu `bash`
- redirect-urile in `adbsh` (`echo x > /data/local/tmp/f`) pot lasa canalul fara output
  pentru comenzile urmatoare -> scrie fisierele din python sau din `terminal`
- `grep` cu alternanta si backslash-pipe in `bash` da ZERO rezultate desi exista
  potriviri -> foloseste `grep -E "a|b"` sau scrie in fisier si citeste cu python
