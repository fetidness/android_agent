---
name: git-push-debian-ssh
description: "Cum clonezi si dai push la android_agent din Debian cu cheia SSH, plus ce fisiere trebuie sincronizate ca un rebuild APK sa reproduca comportamentul de pe device"
---
# Git push din Debian cu cheie SSH + sincronizarea assets pentru rebuild

## When to Use
- Trebuie sa urci modificari de pe device in repo-ul `android_agent` (GitHub).
- Ai primit o cheie SSH si trebuie instalata in Debian ca `git push` sa mearga.
- Inainte de un rebuild APK: trebuie sa te asiguri ca `assets/python/agent.py`
  din repo e IDENTIC cu cel care ruleaza pe device.

## Method

### 1. Verifica daca cheia exista chiar acolo
Un director poate exista si fi GOL — `ls` poate sa nu arate nimic in tool-ul bash.
Verifica din python (fiabil):
```python
import os
p="/storage/emulated/0/Download/ssh_github"
print(os.path.exists(p), os.listdir(p))
```
Rezultat asteptat: `id_ed25519` (~419 B) + `id_ed25519.pub` (~111 B).

### 2. Instaleaza cheia + pachetele in Debian
```bash
apt-get install -y git openssh-client      # dpkg da erori pe dbus/libpam-cap, ignorabile
mkdir -p ~/.ssh && chmod 700 ~/.ssh
cp /storage/emulated/0/Download/ssh_github/id_ed25519 ~/.ssh/
cp /storage/emulated/0/Download/ssh_github/id_ed25519.pub ~/.ssh/
chmod 600 ~/.ssh/id_ed25519 && chmod 644 ~/.ssh/id_ed25519.pub
```

### 3. known_hosts (OBLIGATORIU, altfel "Host key verification failed")
```bash
ssh-keyscan -t ed25519,rsa github.com >> ~/.ssh/known_hosts
ssh -o BatchMode=yes -T git@github.com
# Hi <user>! You've successfully authenticated, but GitHub does not provide shell access.
```

### 4. Clone + identitate + commit + push
```bash
cd ~ && GIT_SSH_COMMAND="ssh -o BatchMode=yes" git clone git@github.com:fetidness/android_agent.git
cd ~/android_agent
git config user.name "android-agent"; git config user.email "agent@net.sys32.local"
git add -A && git commit -q -F - <<'EOF'
... mesaj ...
EOF
GIT_SSH_COMMAND="ssh -o BatchMode=yes" git push origin master
```

### 5. Sincronizeaza agentul REAL in assets (punctul critic pentru rebuild)
Sursa care intra in APK e:
```
workspace/app/net.sys32.agent/app/src/main/assets/python/agent.py
```
Debian NU vede filesDir, deci copiaza prin /sdcard (punte):
```python
import shutil, os, hashlib
src="/data/data/net.sys32.agent/files/python/agent.py"
bridge="/storage/emulated/0/Download/Agent/workspace/_push_agent.py"
shutil.copy(src, bridge); os.chmod(bridge, 0o644)
print(hashlib.md5(open(src,'rb').read()).hexdigest())
print(hashlib.md5(open(bridge,'rb').read()).hexdigest())   # trebuie IDENTICE
```
```bash
cd ~/android_agent/workspace/app/net.sys32.agent/app/src/main/assets/python
cp /storage/emulated/0/Download/Agent/workspace/_push_agent.py agent.py
md5sum agent.py
python3 -c "import py_compile;py_compile.compile('agent.py',doraise=True);print('SINTAXA OK')"
```

### 6. Verificare finala (nu doar "push OK")
```bash
git fetch origin -q
git rev-parse HEAD; git rev-parse origin/master    # trebuie IDENTICE
git show --stat --oneline HEAD | head -25
```

## Pitfalls
- Directorul cheilor (`/storage/emulated/0/Download/ssh_github/`) poate exista si fi GOL
  -> `os.listdir()` din python e singura verificare sigura; `ls` in tool-ul bash poate da output gol fara eroare.
- `ssh -T git@github.com` fara known_hosts da `Host key verification failed` (nu e cheia stricata)
  -> `ssh-keyscan -t ed25519,rsa github.com >> ~/.ssh/known_hosts`.
- `ssh-keygen` si `ssh` lipsesc initial din rootfs-ul minimal -> `apt-get install -y openssh-client`
  (apt-ul raporteaza `E: Sub-process /usr/bin/dpkg returned an error code (1)` pe dbus/libpam-cap,
  dar binarele se instaleaza corect — verifica cu `command -v git`).
- `git config user.name/user.email` lipsesc -> commit-ul e refuzat; seteaza-le inainte.
- FilesDir nu e vizibil din Debian (`/data/data/net.sys32.agent/files` -> Permission denied)
  -> orice copiere device->repo trece prin `/storage/emulated/0/...` ca punte.
- Assets-urile din repo pot fi mai VECHI decat ce ruleaza pe device
  (masurat: repo avea 395919 B, device-ul 403699 B) -> mereu compara md5, nu te increde in `git status`.
- `.gitignore` global ignora `*.txt`, `*.py` din workspace si `memory.md`, dar
  `assets/python/memory.md` e explicit urmarit; verifica cu `git check-ignore -v <f>` sau `git status --short`
  inainte sa presupui ca un fisier intra in commit (rc=1 la check-ignore = NU e ignorat).
