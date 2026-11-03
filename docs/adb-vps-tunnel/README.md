# ADB prin VPS - tunel revers pentru acces de la distanta

Acces ADB complet catre un telefon Android aflat in spatele NAT sau CGNAT
(date mobile), prin intermediul unui VPS propriu. Fara port forwarding pe
router, fara IP public pe telefon, fara root.

Verificat functional pe: POCO 2409FPCC4G (Android 16) conectat prin date
mobile (CGNAT 10.175.147.62) -> VPS Debian -> adb din alt device.

---

## 1. De ce ai nevoie de asta

`adbd` asculta pe `[::]:5555` pe telefon, dar asta nu ajuta daca telefonul:

- nu are IP public (aproape toate retelele mobile folosesc CGNAT)
- sta in spatele unui router care nu permite port forwarding
- isi schimba IP-ul la fiecare reconectare

Solutia: telefonul **initiaza** conexiunea catre un VPS, iar VPS-ul o tine
deschisa. Tu te conectezi la VPS, nu la telefon.

```
  Debian (adb)  ->  VPS:5557  ->  tunel  ->  telefon:5555
                     ^
                     |  conexiune INITIATA de telefon (iese prin NAT)
                  telefon
```

---

## 2. Fisiere

- `tunnel_server.py` - ruleaza pe VPS. Doua porturi:
  - **5556** canal de control (telefonul se conecteaza si se declara `READY`)
  - **5557** portul public pe care intri tu cu `adb connect`
- `tunnel_client.py` - ruleaza PE TELEFON, in procesul agentului.
  Mentine conexiunea de control si deschide canale catre `127.0.0.1:5555`
  (adbd-ul propriu) la cerere.

Protocolul e simplu: control `READY`, server trimite `NEW`, client deschide
un socket nou cu `DATA`, server face pipe intre consumator si acel socket.

---

## 3. Instalare

### 3.1 Pe VPS

```bash
# copiaza serverul
scp tunnel_server.py user@vps:/home/user/

# porneste-l detasat (setsid e obligatoriu, altfel moare la logout)
cd ~
setsid nohup python3 tunnel_server.py > ~/tunnel.log 2>&1 < /dev/null &
```

Verificare:

```bash
pgrep -af tunnel_server           # trebuie sa apara procesul
ss -ltn | grep -E ':555[67]'      # ambele porturi in LISTEN pe 0.0.0.0
head -3 ~/tunnel.log              # [ctrl] asculta... / [pub] adb poate conecta...
```

### 3.2 Firewall - CAPCANA PRINCIPALA

Aici se pierde cel mai mult timp. Pe sisteme cu **nftables** (Debian 12+,
Ubuntu 22+), `ufw status` poate arata porturile permise in timp ce nftables
le arunca. UFW scrie in lanturile lui, dar daca exista un tabel `inet filter`
cu `policy drop` si o lista explicita de porturi, **acela castiga**.

Diagnostic:

```bash
sudo nft list ruleset | head -30
```

Daca vezi asa ceva, porturile tale NU sunt permise indiferent de ufw:

```
chain input {
    type filter hook input priority filter; policy drop;
    tcp dport { 22, 80, 443, 2715 } accept
}
```

Fix permanent:

```bash
sudo sed -i 's/tcp dport {22, 80, 443, 2715} accept/tcp dport {22, 80, 443, 2715, 5556, 5557} accept/' /etc/nftables.conf
```

Sau adaugare la runtime (se pierde la reboot):

```bash
sudo nft add rule inet filter input tcp dport { 5556, 5557 } accept
```

Verificare ca regula e pe locul ei:

```bash
sudo nft list chain inet filter input | grep dport
```

**Semne ca ai lovit aceasta capcana:** pachetele intra (se vad cu tcpdump),
dar nu pleaca niciun SYN-ACK, iar `ufw status` arata portul permis.

### 3.3 Pe telefon

```bash
adb push tunnel_client.py /data/local/tmp/tunnel_client.py
```

Pornirea se face **in procesul agentului**, nu din shell-ul adb - pe Android
nu exista `python3` in `/system/bin`:

```
python3 /data/local/tmp/tunnel_client.py sys32.net 5556
```

Iese:

```
[start] POCO -> sys32.net:5556, adbd local 127.0.0.1:5555
[ctrl] conectat la sys32.net:5556
```

### 3.4 Din Debian

```bash
adb connect sys32.net:5557
# sau, daca porturile sunt altfel:
adb connect <ip-vps>:5557
```

`adb devices` trebuie sa arate `sys32.net:5557   device`.

---

## 4. Diagnostic - in ce ordine verifici

Mergi in ordinea asta, fiecare pas exclude un strat:

1. **Serverul ruleaza?**
   ```bash
   ssh vps 'pgrep -af tunnel_server; ss -ltn | grep 555[67]'
   ```
2. **Porturile raspund din exterior?**
   ```bash
   python3 -c "import socket;s=socket.socket();s.settimeout(6);print(s.connect_ex(('vps',5557)))"
   # 0 = OPEN, 111 = refused (gazda vie, nimic nu asculta), 113 = no route
   ```
3. **Pachetele ajung la VPS?**
   ```bash
   ssh vps 'sudo tcpdump -i ens6 -n "tcp port 5557" -c 5'
   ```
   - vezi `Flags [S]` care intra si **niciun `[S.]`** care iese => firewall pe VPS (nftables)
   - nu vezi nimic => firewall la provider (security group)
4. **Telefonul s-a conectat?**
   ```bash
   ssh vps 'tail -5 ~/tunnel.log'
   # [ctrl] client pregatit de la ('IP', port)
   ```
5. **Telefonul poate ajunge la VPS?**
   ```bash
   adb shell 'nc -w 5 -z vps 5556 && echo REACHABLE'
   ```

---

## 5. Probleme reale intalnite si cauzele lor

**`unauthorized` / `authorizing` la infinit**
Doua cauze: (a) adbd cere acceptarea cheii si nu ai apasat Allow pe telefon,
(b) serverul are mai multi clienti conectati simultan (ex. unul vechi pe WiFi
si unul nou pe mobil) si trimite cererea la cel gresit. Fix: opreste clientul
vechi si fa `adb disconnect` + `adb connect`.

**Clientul moare cand inchizi sesiunea SSH**
Nu folosi `nohup ... &` singur. Foloseste `setsid nohup ... < /dev/null &`.
Fara `setsid`, procesul e legat de sesiunea SSH si primeste SIGHUP la logout.

**Procesul de pe telefon e omorat de sistem**
Android omoara procesele shell fara terminal. De aceea clientul trebuie sa
ruleze in procesul agentului (care are deja un serviciu in viata), nu ca
proces separat lansat din adb shell.

**Tunelul se blocheaza dupa reconectarea retelei**
Clientul are reincercare la 10 secunde, dar serverul pastreaza clientul vechi
in `ready_ctrl`. Daca IP-ul public se schimba (WiFi -> mobil), faci
`adb disconnect` + `adb connect`.

---

## 6. Securitate

`adbd` are uid=2000, adica puteri de administrare: `pm install`, `settings put`,
`input tap`, `dumpsys`, acces la `/data/local/tmp`. Cine ajunge la portul 5557
controleaza telefonul complet.

Recomandari:

- nu expune 5557 pe `0.0.0.0` daca poti folosi un tunel SSH (`ssh -L`) catre el
- limiteaza in nftables sursa: `ip saddr <ip-ta> tcp dport 5557 accept`
- autentificarea adbd se bazeaza doar pe cheia RSA, deci cheia din
  `~/.android/adbkey` trebuie tratata ca o parola
- `5556` (control) nu are autentificare deloc - oricine se poate declara client;
  nu il lasi deschis public fara restrictie de sursa

---

## 7. Oprire si curatenie

```bash
# VPS
ssh vps 'pkill -f tunnel_server'

# Debian
adb disconnect <ip-vps>:5557

# telefon: opreste clientul din agentul lui
```

Regulile nftables raman dupa reboot (sunt in `/etc/nftables.conf`).
Serverul de tunel NU porneste automat - trebuie relansat manual sau pus
sub systemd.

---

## 8. Varianta cu systemd pe VPS (optional)

`/etc/systemd/system/adb-tunnel.service`:

```ini
[Unit]
Description=ADB reverse tunnel
After=network-online.target

[Service]
User=USER
ExecStart=/usr/bin/python3 /home/USER/tunnel_server.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now adb-tunnel
sudo systemctl status adb-tunnel
```
