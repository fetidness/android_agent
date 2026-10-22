# Optimizari proot (masurate pe SM-A366B, Debian trixie, Android 16)

## IMPORTANT: corectie fata de prima versiune a acestui document
Prima versiune afirma "+21% la exec cu PROOT_NO_SECCOMP=1". **Era FALS.**
Comparatia initiala masura doua COMENZI diferite, nu doua valori ale variabilei.

## Masuratoare corecta (200x /bin/true, 4 rulari, median)
- PROOT_NO_SECCOMP=1 : 8654 ms
- PROOT_NO_SECCOMP=0 : 8620 ms
- diferenta 0.4% = zgomot (varianta intre controale identice: 1501-2266 ms)

## Ce face totusi variabila (dovedit cu PROOT_VERBOSE=1)
- fara variabila -> "proot info: ptrace acceleration (seccomp mode 2) enabled"
- cu variabila    -> linia DISPARE, acceleratorul e oprit
Deci variabila functioneaza, dar pe acest device nu produce castig masurabil.

## Optimizari care RAMAN valide
- apt: fara Recommends/Suggests, fara pty, fara periodic (in /etc/apt/apt.conf.d/)
- dpkg: force-unsafe-io (elimina fsync prin ptrace)
- locale C.UTF-8 + TZ fixate
- PYTHONDONTWRITEBYTECODE=1 (fara scrieri .pyc prin ptrace)
- git: fsmonitor/untrackedCache off, gc.auto 0, pack.threads 1

## Limita structurala (netrecuta)
- 5000x stat: proot 781 ms vs nativ 17 ms = 46x
- overhead-ul e ptrace per syscall; NU se rezolva cu proot-rs
- exec e deja aproape de nativ (1035 ms vs 947 ms la 100x)

## Integrare in APK
Patch-ul e in SURSA din repo:
  workspace/app/net.sys32.agent/app/src/main/assets/python/proot_tool.py
  workspace/app/net.sys32.agent/app/src/main/assets/proot/debian_x.sh
Gradle le impacheteaza automat (src/main/assets, fara sourceSets custom).
