# terminal_server.py aliniat cu agent.py (2026-10-22)

## Problema
`run_in_debian` exista in DOUA locuri, cu implementari DIVERGENTE:
- `agent.py` (linia ~3917) - varianta completa
- `terminal_server.py` (linia 40) - varianta slaba

Varianta slaba avea 3 lipsuri reale:
1. **fara `--bind=/storage`** -> orice acces la `/sdcard` sau `/storage` dadea
   "No such file or directory", desi fisierul EXISTA pentru uid 2000.
   (dovedit: m-a costat iteratii la construirea batching-ului)
2. **fara `DEBIAN_FRONTEND=noninteractive`** -> `apt install` fara `-y` bloca
   pana la timeout, fara ca nimeni sa poata raspunde la prompt.
3. **fara transmitere base64** -> adbd despacheteaza `shell,v2,raw:<service>` si
   SPARGE pe spatii, dand bucatile ca argv separate (`sh -c id -u` -> argv
   ["id","-u"] -> "sh: -u: inaccessible or not found").

## Fix
`terminal_server.run_in_debian` aliniat la varianta din `agent.py`:
- bind-uri: `/dev /proc /sys /sdcard /storage /data/local/tmp`
- `DEBIAN_FRONTEND=noninteractive`, `APT_LISTCHANGES_FRONTEND=none`,
  `DEBCONF_NONINTERACTIVE_SEEN=true`, `PAGER=cat`, `GIT_PAGER=cat`
- comanda trece ca base64: `echo <b64> | base64 -d | /bin/bash`
- calea uid2000 la fel: `echo <b64> | base64 -d | /system/bin/sh`

`run_batch` primeste aceleasi bind-uri si aceleasi variabile.

## Verificat pe device
- `run_in_debian("ls /storage/.../workspace")` -> lista reala (inainte: No such file)
- `run_in_debian("ls /sdcard/.../workspace")` -> lista reala
- `run_in_debian("uname -m")` -> aarch64
- `run_in_debian("id -u", uid2000=True)` -> 2000
- `run_in_debian("getprop ro.product.model", uid2000=True)` -> SM-A366B
- comenzi cu spatii/ghilimele -> corect (`echo 'a b  c'` merge)
- `run_batch(["echo A","uname -m","echo B"])` -> ['A','aarch64','B'] in 197 ms

## Lectie
Cand aceeasi functie exista in doua fisiere, ele DIVERGHEAZA. Verifica intotdeauna
care e cea folosita efectiv, inainte de a o repara pe cea aparenta.
