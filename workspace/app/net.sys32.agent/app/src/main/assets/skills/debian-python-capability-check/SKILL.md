---
name: debian-python-capability-check
description: "Cum verifici REAL ce poate mediul Debian (python3, retea, gcc, binder) pe acest telefon, si scriptul gata facut capcheck.py"
---
# Verificarea capabilitatilor mediului Debian de pe telefon cu Python

## When to Use
- Operatorul cere "un script simplu sa testez capabilitatile" in Debian.
- Trebuie sa afli daca python3 exista / ce module are / daca merge reteaua / gcc / binder, INAINTE de a promite ceva.
- Dupa o reinstalare a aplicatiei, cand nu stii ce mai e prezent in Debian.

## Method
1. Verifica intai daca python3 exista in Debian (NU presupune):
   `terminal action=run cmd="python3 -V; which python3"`
   Pe acest device a raspuns: `/bin/bash: line 1: python3: command not found` -> Debian 13 trixie minimal, FARA python.
2. Instaleaza-l din repo (merge, ~1 min):
   `apt-get install -y --no-install-recommends python3` -> Python 3.13.5.
3. Verifica in acelasi pas ce e deja acolo:
   `ls /usr/bin | head -50`, `which gcc cc apt-get tar openssl nano`
   Prezente: gcc, cc, apt-get, tar, openssl, nano. Lipsa: git, curl, wget, make, perl, ssh, unzip, sqlite3, vim.
4. Scrie scriptul in workspace (`/storage/emulated/0/Download/Agent/workspace/capcheck.py`) din python cu `open().write()` + `os.chmod(p, 0o755)`.
5. Scriptul are 7 sectiuni selectabile prin argv (system, disc, net, tools, python, android, priv): fiecare test face o operatie REALA, nu doar un `which` - scrie+citeste 128 KB si compara sha256, face `gcc` + ruleaza binarul, face HTTPS GET cu status, ruleaza `android-binder selftest`.
6. Ruleaza-l si verifica EFFECTUL: `cd workspace && python3 capcheck.py` -> trebuie `0 FAIL`.
7. Rezultatul real pe acest device (SM-A366B): 8 nuclee, 7380 MB RAM, 169.5 GB liberi, DNS 34 ms, HTTPS 200, gcc OK (sqrt(2)=1.414), bucla 3M in 0.16s, binder 470 servicii / 215 accesibile.

## Pitfalls
- `python3` lipseste din Debian la prima instalare -> NU raporta "nu se poate face un script python"; ruleaza `apt-get install -y --no-install-recommends python3`.
- `subprocess.run(cmd, shell=True)` cu `capture_output=True` intoarce rc=0 si pentru `ls /data/data` chiar cand calea nu exista -> fals pozitiv "acces OK". Fix: verifica `os.path.isdir(p)` INAINTE si trateaza "nu exista in acest namespace" ca WARN, nu ca OK.
- `/data/data`, `/data/app`, `/data/system` NU sunt vizibile din namespace-ul Debian (nu e eroare de permisiuni, calea nu exista) -> raporteaza-le ca WARN.
- `getprop` si `/system/build.prop` nu sunt in PATH-ul Debian (`/bin/sh: 1: getprop: not found`) -> pentru date Android foloseste `/opt/android-binder/android-binder selftest` (ruleaza si intoarce 470 listate / 215 accesibile), NU getprop.
- `android-binder --help` da `comanda necunoscuta: --help` -> comenzile reale sunt `list | check | handle | desc | call | rawcall | selftest`.
- Un script care raporteaza OK pentru orice => inutil. Regula: fiecare test trebuie sa produca un efect verificabil (hash comparat, exit code al binarului compilat, status HTTP).

## Profiluri de privilegii comparate (masurat 2026-10-23)
Script gata facut pentru oricare context: `ctxprobe.py` (in workspace) - citeste
uid/euid, grupurile, `/proc/self/attr/current`, CapEff/CapBnd din
`/proc/self/status` si testeaza socket brut. Rulare:
`python ctxprobe.py > out.txt 2>&1; tr -d '\000' < out.txt`

Rezultate reale pe SM-A366B (Android 16):

- APP (uid 10426): CTX `u:r:untrusted_app:s0:c170,c257,c512,c768`,
  CapEff `0000000000000000`, CapBnd `0000000000000000`. Citeste filesDir si
  /sdcard, NU /data/local/tmp si NU listeaza /system/bin.
- DEBIAN proot (terminal action=run): UID 0 emulat, CTX `u:r:shell:s0`,
  CapEff `0000000000000000`, CapBnd `00000000008000c0`, 12 grupuri shell.
  Citeste /data/local/tmp si /sdcard, NU filesDir (mode 700, alt owner).
- AMBELE: `socket(AF_PACKET, SOCK_RAW, 3)` -> `PermissionError [Errno 13]`,
  `socket(AF_INET, SOCK_RAW, IPPROTO_ICMP)` -> `[Errno 1] Operation not
  permitted`.

REGULA: un UID 0 in proot NU aduce capabilitati. Capabilitatile se pierd la
fork si nu se pot mosteni daca parintele (app-ul) are CapBnd=0, deci nici macar
UID 0 nu le poate recupera; in plus SELinux `shell` nu are
`capability net_raw`. Nu promite ARP/sniffing/SYN raw din Debian.
- `cat` / `read` pe un fisier care contine octeti NUL (ex. copia lui
  `/proc/self/attr/current`, care are un `\x00` la final) iese ca "[BINARY
  output binar]" si nu vezi textul -> filtreaza cu `tr -d '\000'` sau citeste
  in python ca bytes si inlocuieste `b'\x00'`.
- Concluzia "binder/nmap nativ a facut ARP scan" luata din OUTPUT-ul scanarii
  e falsa: nmap ignora `-PR` si cade pe CONNECT (se vede doar cu `-d2`/`-d3`:
  "Changing ping technique for 192.168.1.1 to connect to port 80"). Verifica
  MECANISMUL (test de socket AF_PACKET), nu rezultatul, inainte de a afirma o
  capabilitate.
