# Batching proot: 23x pe secvente de comenzi

## Descoperirea-cheie
Costul unei comenzi NU e proot si NU e exec-ul: este pornirea procesului
+ un round-trip adb (~110 ms). Toate flag-urile proot sunt irelevante:
- `-0` / fara `-0`            : 542 vs 597 ms
- `--kill-on-exit`            : 592 ms
- `--sysvipc` / fara          : 571 vs 582 ms
- `--link2symlink` / fara     : 582 ms
- bind-uri (niciunul / toate): 689 vs 625 ms
- minimal (doar `-r`)        : 615 ms
=> identice in limita zgomotului.

## Masuratori (1 proot cu N comenzi inauntru)
- n=1  : 114 ms  (113.9 /cmd)
- n=5  : 159 ms  ( 31.7 /cmd)
- n=20 :  84 ms  (  4.2 /cmd)
- n=50 : 141 ms  (  2.8 /cmd)
- n=100: 175 ms  (  1.7 /cmd)

## Comparativ cu un proot per comanda (run_in_debian xN)
- n=2  : batch 186 ms vs secvential  440 ms  =>  2.4x
- n=5  : batch 224 ms vs secvential 1031 ms  =>  4.6x
- n=10 : batch 164 ms vs secvential 1792 ms  => 11.0x
- n=20 : batch 167 ms vs secvential 3901 ms  => 23.4x
Output verificat IDENTIC la fiecare rulare.

## API
`terminal_server.run_batch(["cmd1","cmd2",...])` -> lista de stringuri,
unul per comanda. Delimitare cu nonce uuid (nu se ciocneste cu output-ul real).
Robust la: comenzi care esueaza, output cu newline, comenzi goale, exit codes.

## Ce NU a mers (si de ce)
- FIFO (`mkfifo`) in /data/local/tmp -> "Permission denied" (SELinux). Nu se poate.
- Sesiune proot persistenta cu polling pe fisier -> functioneaza, dar adauga
  ~40-110 ms latenta de polling, deci NU bate batch-ul nativ. Inutil.
- Fisiere in /data/local/tmp ca canal: procesul app NU poate scrie acolo
  (SELinux), deci canalul trebuie sa fie /storage (FUSE), accesibil la ambele.
- proot NU vede /storage fara `--bind=/storage` explicit (da "No such file").

## Regula
Cand ai >= 2 comenzi pentru Debian, foloseste `run_batch` in loc de
apeluri repetate la `run_in_debian`. Cu o singura comanda castigul e 0.
