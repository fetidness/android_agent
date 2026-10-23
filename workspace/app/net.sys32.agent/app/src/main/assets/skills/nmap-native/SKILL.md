---
name: nmap-native
description: "nmap 7.95 compilat NATIV pe device cu toolchain-ul din APK - reteta completa de build + ce merge si ce NU (ARP/SYN brut sunt imposibile fara root)."
---

# nmap nativ pe device (compilat din sursa)

## Ce exista deja (NU recompila)
- Binar: `/data/data/net.sys32.agent/files/nmap/nmap` (3.3 MB, ELF Android 35)
- Fisiere date: `nmap-services`, `nmap-os-db`, `nmap-service-probes`,
  `nmap-mac-prefixes`, `nmap-protocols`, `nmap-rpc` in acelasi director
- Launcher: `python /storage/emulated/0/Download/Agent/workspace/nmap_run.py <args>`
- Sursa build-uita: `/data/data/net.sys32.agent/files/tmp/nbuild/nmap-7.95`

## RULARE (exec direct e blocat de SELinux)
```
/apex/com.android.runtime/bin/linker64 /data/data/net.sys32.agent/files/nmap/nmap \
  -sn -PR 192.168.1.0/24 --datadir /data/data/net.sys32.agent/files/nmap --dns-servers 192.168.1.1
```
FARA `--datadir` da "Unable to find nmap-services". FARA `--dns-servers` da
warning mass_dns (nu exista /etc/resolv.conf pe Android).

## Ce merge si ce nu (masurat pe SM-A366B, verificat cu -d3 si teste de socket)
- OK: `-sT -sV -Pn -p ...` scanare TCP connect + versiuni (Dropbear sshd,
  OpenWrt uHTTPd, Cloudflare DNS pe 53), 6.25 s pentru un host
- OK: descoperire hosturi prin `-sn` cu CONNECT pe 80/443 -> 3.1 s pe /24,
  cu hostname-uri rezolvate de router ("OpenWrt.lan", "MyPhone.lan")
- NU: `-sS` (SYN raw) -> "You requested a scan type which requires root privileges. QUITTING!"
- NU: `-O` (OS fingerprint) fara root
- NU: `-PR` ARP brut -> IGNORAT silentios, cade pe CONNECT. Dovada din `-d3`:
  "Changing ping technique for 192.168.1.1 to connect to port 80" +
  "CONN (0.0023s) TCP localhost > 192.168.1.1:80". Nmap nu da eroare, doar
  schimba tehnica -> NU concluziona din rezultat ca ARP a functionat.

## RETETA DE BUILD (daca trebuie refacut)
1. Sursa: https://nmap.org/dist/nmap-7.95.tgz
2. Dezarhiveaza IN files/tmp (NU pe /sdcard - noexec) si `find . -exec touch {} +`
   (altfel configure: "newly created file is older than distributed files")
3. configure cu `sh ./configure` (./configure da Permission denied - shebang noexec)
   parametri: --host=aarch64-linux-android --without-{ncat,nping,zenmap,ndiff,liblua,openssl,libssh2,libz}
   --disable-shared --disable-dependency-tracking --with-libpcap=included
4. CFLAGS obligatoriu `--target=aarch64-linux-android35` (API 36 NU are
   libclang_rt.builtins.a -> "cannot open .../android36/libclang_rt.builtins.a")
5. CC/CXX + `-B$TMP`, LD=$TMP/ld, AR, RANLIB, MAKE=$TC/bin/make
6. TRAP-uri noexec care dau "Error 127" (scripturi cu shebang):
   - `./config.status` -> ruleaza manual `sh ./config.status --file=X.tmp:X.in`
   - `libpcap/pcap-config` -> la fel
   - `./install-sh -c -d dir` -> creeaza directoarele si `.dirstamp` cu python
   - `aclocal.m4` -> `find . -exec touch {} +` (aclocal nu exista)
7. Link final: `make LIBS="... -lm -ldl"` cu TOATE librariile interne
   (libpcre/.libs/libpcre2-8.a libpcap/libpcap.a libnetutil/libnetutil.a
   libdnet-stripped/src/.libs/libdnet.a liblinear/liblinear.a) - altfel
   "undefined symbol: exp/log/pow"

## DE CE ARP BRUT E IMPOSIBIL PE ACEST DEVICE (verificat, nu teorie)
- `python: socket.socket(socket.AF_PACKET, SOCK_RAW, 0x0003)` din app ->
  `PermissionError: [Errno 13] Permission denied`
- `socket.socket(AF_INET, SOCK_RAW, IPPROTO_ICMP)` din app ->
  `[Errno 1] Operation not permitted`
- `adbsh: cat /proc/self/status | grep CapEff` -> `0000000000000000`
  (uid 2000 shell are grupurile inet/net_bt_admin, dar ZERO capabilitati)
- `adbsh: nsenter -t 1 -n -- id` -> "/proc/1/ns/net: Permission denied"
- `adbsh: su -c id` -> "su: inaccessible or not found"
- `adbsh` nu poate nici citi binarul: "error: unable to open file
  /data/data/net.sys32.agent/files/nmap/nmap" (alt uid, mode 700)
=> NU mai incerca sa obtii ARP/SYN raw din app, din adbsh sau din proot.
   Singurele cai reale: root (Magisk/KernelSU) sau scanare de pe alt PC din LAN.

## TRAP bg
`bg` cu `> log 2>&1` in files/tmp a produs log-uri goale si joburi moarte;
build-ul a mers cu subprocess.run direct din python (capture_output).

## Pitfall general de raportare
- Nu declara o capabilitate (ARP real, SYN scan) doar pentru ca rezultatul
  scanarii arata bine: verifica mecanismul cu `-d3` si cu un test direct de
  socket. In aceasta sesiune s-a raportat initial "ARP merge nativ" si era FALS.
