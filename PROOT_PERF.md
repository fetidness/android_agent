# Optimizari proot (masurate pe SM-A366B, Debian trixie)

## Aplicate
- `PROOT_NO_SECCOMP=1` in /etc/profile.d/00-proot-perf.sh -> +21% la exec
- apt: fara Recommends/Suggests, fara pty, fara periodic -> instalaari mai scurte
- dpkg: `force-unsafe-io` -> elimina fsync prin ptrace
- locale C.UTF-8 + TZ fixate -> fara fallback lent
- PYTHONDONTWRITEBYTECODE=1 -> fara scrieri .pyc prin ptrace
- git: fsmonitor/untrackedCache off, gc.auto 0, pack.threads 1

## Masuratori (100x /bin/true)
- proot baseline: 1317 ms
- proot NO_SECCOMP: 1035 ms
- nativ Android: 947 ms

## Limita structurala
`stat`/`open`: 46x mai lent decat nativ (781 ms vs 17 ms / 5000 apeluri).
Nu se rezolva cu proot-rs: overhead-ul e ptrace per syscall.
