# adb_client: fix comenzi tacute (SM-A366B, masurat 2026-10-22)

## Bug
`shell()` presupunea ca `r == ""` = socket desincronizat -> `close() + connect()` +
re-executie. Dar o comanda care se termina CU SUCCES si nu produce output
(true, cd, mkdir, touch, git commit -q, cat /dev/null) returneaza legitim "".

## Cost real (inainte)
- `true`              : 485 - 1963 ms
- `cat /dev/null`     : 609 ms
- `printf ''`         : 721 ms
- `echo x` (are output): 42 - 54 ms
=> orice comanda tacuta = reconectare TCP + AUTH RSAPUBLICKEY de fiecare data.

## Fix
1. `_shell_locked()` seteaza `self._last_rc_ok = (not timed_out)`
2. `shell()` reconecta doar daca `not getattr(self,"_last_rc_ok",False)`

## Rezultat (dupa)
- `true`          : 41 ms  (de la 1226 ms = 30x)
- `cat /dev/null` : 43 ms
- comenzi reale (mkdir/touch/ls/id/rm): 47 - 87 ms
- proot /bin/true : 127 ms (de la 616 ms = 4.8x)
- proot python -c pass: 184 ms

## Lectie generala
Costul fix pe acest device NU e proot (flag-urile -0/--kill-on-exit/--sysvipc/
--link2symlink/bind-urile dau toate 550-620 ms). Costul e un round-trip adb
(~40 ms) + pornirea procesului. BATCHING-ul e singura optimizare mare:
1 proot + 50 exec = 1792 ms (36 ms/exec) vs 50 proot = ~28000 ms.
