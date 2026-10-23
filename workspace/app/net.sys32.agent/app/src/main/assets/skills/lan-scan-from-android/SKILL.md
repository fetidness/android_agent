---
name: lan-scan-from-android
description: "Scanarea retelei LAN de pe telefon (ce dispozitive sunt conectate) cand nmap/ARP din proot esueaza - ce merge si ce NU"
---
# Scanarea LAN de pe acest device (prin Debian proot + adbsh)

## When to Use
- Operatorul cere "ce dispozitive sunt conectate pe reteaua actuala".
- Vrei sa listezi hosturile din LAN cu nmap din Debian si obtii
  "setup_target: failed to determine route" sau 0 hosts scanned.
- Vrei ARP-scan / ping-sweep si rezultatul e gol desi reteaua are hosturi.

## Method
1. Afla reteaua reala (NU din Debian, ci din Android):
   `adbsh: ip -4 addr show wlan0`   -> ex. inet 192.168.1.100/24
   `adbsh: ip route`                -> ex. 192.168.1.0/24 dev wlan0 src 192.168.1.100
   Alternativ `android tool=network action=all` da wifi_ssid, wifi_bssid,
   link speed, RSSI, dar IP-ul vine ca intreg semnat (byte-swapped:
   -872306496 & 0xFFFFFFFF, apoi struct.pack('>I') -> 192.168.1.100).
2. Instaleaza nmap in Debian (apt merge, HTTPS OK):
   `DEBIAN_FRONTEND=noninteractive apt-get install -y -qq nmap iproute2`
   -> nmap --version => "Nmap version 7.95", aarch64-unknown-linux-gnu.
3. Verifica daca proot-ul are ruta (uneori da, uneori nu):
   `cat /proc/net/route` in Debian -> linia wlan0 cu 0001A8C0 = 192.168.1.0/24.
4. Scanarea care MERGE din Debian (TCP connect, fara privilegii):
   `nmap -sT -Pn --unprivileged --open -p 22,53,80,443,445,62078,8009,9100 <ip>-254 --host-timeout 3s -oG -`
   apoi filtreaza `grep 'Ports:'`. Doar hosturile cu porturi deschise sunt reale.
5. Confirmare/identificare fara nmap: socket Python din app (merge, are INET):
   TCP connect pe 80/443 + `s.connect((ip,22)); s.recv(120)` pentru banner
   (router OpenWrt -> "SSH-2.0-dropbear"; port 80 LuCI; DNS pe 53).
6. Cross-check ARP din Android:
   `adbsh: ip neigh show dev wlan0 | grep -v INCOMPLETE`
   Intrarea `lladdr ... REACHABLE` pentru gateway e referinta.

## Metoda PREFERATA (mai noua, ocoleste tot ce e mai sus)
Daca `/data/data/net.sys32.agent/files/nmap/nmap` exista (vezi skill-ul
nmap-native), NU mai folosi nmap din Debian: nmap-ul nativ e mai rapid si
rezolva hostname-urile prin router, in ~3 s pe /24. ATENTIE: `-PR` NU face
ARP brut nici nativ (vezi Pitfalls) - e tot CONNECT, doar ca ajunge direct la
retea si nu se impotmoleste in rutarea proot.
```
/apex/com.android.runtime/bin/linker64 /data/data/net.sys32.agent/files/nmap/nmap \
  -sn -PR 192.168.1.0/24 --datadir /data/data/net.sys32.agent/files/nmap --dns-servers 192.168.1.1
```
Rezultat real pe SM-A366B: "Nmap done: 256 IP addresses (2 hosts up) scanned in
3.49 seconds", cu "OpenWrt.lan (192.168.1.1)" si "MyPhone.lan (192.168.1.100)".
ATENTIE: cu `-d3` se vede ca nmap a folosit CONNECT pe 80/443
("Changing ping technique ... to connect to port 80"), NU ARP.
Pentru servicii: `-sT -sV -Pn -p 22,53,80,443 --datadir ... --dns-servers 192.168.1.1 <ip>`
(6.25 s pentru router: Dropbear sshd, OpenWrt uHTTPd, Cloudflare DNS).

## Pitfalls
- `nmap -sn -PR 192.168.1.0/24` din proot -> "setup_target: failed to determine
  route to 192.168.1.x ... 0 hosts scanned" (proot fara ruta proprie in acel
  namespace) -> foloseste pasul 4 (-sT) sau adbsh pentru datele de retea.
- `nmap -Pn` raporteaza toate cele 254 adrese ca "Host is up" = FALS POZITIV
  (sare peste discovery) -> ruleaza fara -Pn si crede doar `Ports:` deschise;
  am vazut 192.168.1.2-.254 toate "Up" cu zero porturi.
- socket.AF_PACKET din aplicatia Python -> `[Errno 13] Permission denied`
  (app-ul nu are CAP_NET_RAW) -> orice ARP brut din app e imposibil, nu insista.
- `/proc/net/route`, `/proc/net/arp`, `/proc/net/fib_trie` din app -> Errno 13
  Permission denied -> citeste-le doar din `adbsh` sau din Debian.
- `/dev/tcp/IP/PORT` in adbsh -> "can't create /dev/tcp/...: No such file or
  directory" (sh-ul Android e toybox sh, nu bash) -> foloseste nmap -sT sau python.
- ping sweep in adbsh (`for i in $(seq 1 254); do ping -c1 -W1 ...`) completeaza
  ARP doar pentru gateway; restul raman INCOMPLETE/FAILED (kernel limiteaza
  intrarile neigh) -> nu concluziona "retea goala", TCU/PORTS din Debian e adevarul.
- `cat > /tmp/p.py` in tool-ul bash -> "sh: can't create /tmp/p.py:
  Permission denied" -> scrie scripturile in
  /storage/emulated/0/Download/Agent/workspace si ruleaza-le de acolo.
- In Debian foloseste /tmp (scriibil acolo), in tool-ul bash NU.
- `-PR` / ARP brut NU functioneaza nicaieri pe acest device (nici app, nici
  adbsh): `socket(AF_PACKET, SOCK_RAW)` -> "[Errno 13] Permission denied";
  `CapEff: 0000000000000000` pentru uid 2000. Nu pierde pasi incercand
  nsenter/setpriv/su: "/proc/1/ns/net: Permission denied", "su: inaccessible
  or not found", setpriv lipseste. Doar root sau un PC din LAN pot face ARP.
- Daca vrei sa verifici ce tehnica a folosit nmap, ruleaza cu `-d3` si cauta
  "Changing ping technique" - altfel rezultatul arata identic si te pacaleste.

## Matricea de privilegii (MASURATA pe SM-A366B, 4 contexte, acelasi probe.py)
Probe reutilizabil: `/storage/emulated/0/Download/Agent/workspace/probe.py`
(21 teste, printeaza JSON). Rulat in: app, Debian proot, adbsh, terminal.
- CapEff: 0000000000000000 in TOATE contextele. CapBnd: app = 0 (buget ZERO,
  nimic nu poate fi mostenit de un copil!), shell = 0x8000c0.
- AF_PACKET / RAW ICMP / RAW IP: PermissionError in TOATE. Deci ARP, -sS, -O,
  sniffing = imposibile fara root. Nu mai incerca variante prin proot/adb.
- `nsenter -t 1 -n` din adbsh -> "Permission denied" la /proc/1/ns/net.
- `su` pe acest device -> "inaccessible or not found".
- Diferențe REALE intre contexte (complementare, niciunul nu e superior):
  filesDir (toolchain, binder, python APK) = doar agentul nativ;
  /data/local/tmp + listare /system/bin + `dumpsys` + `settings get` + `ip addr`
  = doar shell/adbsh; `pm list packages` si `am start` merg din AMBELE;
  `dumpsys battery` din app -> "Can't find service: battery";
  `settings get` din app -> "java.lang.SecurityException";
  `screencap` din app -> "Failed to take take screenshot. Capturing failed.";
  `ip addr` din app -> "Cannot bind netlink socket: Permission denied".
- Parametrul `terminal uid2000=true` NU da uid 2000: porneste tot proot ca
  uid 0, context u:r:shell:s0 (identic cu proot normal). Nu te baza pe el
  pentru privilegii de shell.
- `python3` NU exista in adbsh ("python3: inaccessible or not found") ->
  pentru probe in shell scrie testele ca one-lineri sh, nu rula probe.py.
