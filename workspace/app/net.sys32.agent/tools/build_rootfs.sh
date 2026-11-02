#!/bin/bash
# build_rootfs.sh - construieste IMAGINEA rootfs Debian livrata in APK
#                   (assets/proot/agentroot.tar.gz -> lib/arm64-v8a/libagentroot_exec.so)
#
# DE CE: instalarea Debianului pe telefon nu are voie sa depinda de reteaua guest-ului
# (DNS, apt, gcc descarcat la runtime) - pe un telefon fara nameserver-ul corect pasul
# atarna minute si esueaza. Imaginea de aici e COMPLETA: python3, gcc, make, curl, git,
# ca-certificates, PLUS clientul android-binder precompilat, deci setup-ul din aplicatie
# doar o extrage (5 secunde, fara nicio descarcare).
#
# Rulare (pe host, cere root pentru debootstrap):
#   sudo tools/build_rootfs.sh [--force]
# Iese: app/src/main/assets/proot/agentroot.tar.gz  (~187 MB)
set -e
REPO=$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)
ASSETS=$REPO/app/src/main/assets/proot
OUT=$ASSETS/agentroot.tar.gz
WORK=${WORK:-/home/gab/android_agent/temp/rootfs_build}
[ "$(id -u)" = 0 ] || { echo "ruleaza cu sudo (debootstrap cere root)"; exit 1; }
[ -f "$OUT" ] && [ "$1" != "--force" ] && { echo "exista deja: $OUT ($(du -h "$OUT" | cut -f1))"; exit 0; }

R=$WORK/rootfs
rm -rf "$R"; mkdir -p "$R" "$ASSETS"

# 1) baza Debian 13 arm64 (binfmt/qemu face executia nativa pe x86_64)
/usr/sbin/debootstrap --arch=arm64 --variant=minbase --no-check-gpg \
  --include=apt,ca-certificates,procps,less,nano,python3,gcc,libc6-dev,make,curl,wget,git,file \
  trixie "$R" http://deb.debian.org/debian

# 2) igiena (nimic din host nu are ce cauta in imagine)
printf 'nameserver 1.1.1.1\nnameserver 8.8.8.8\n' > "$R/etc/resolv.conf"
echo 'deb http://deb.debian.org/debian trixie main' > "$R/etc/apt/sources.list"
rm -rf "$R"/var/lib/apt/lists/* "$R"/var/cache/apt/archives/*.deb "$R"/tmp/* 2>/dev/null || true

# 3) PATH/LANG pentru shell-ul din Debian
mkdir -p "$R/etc/profile.d"
cat > "$R/etc/profile.d/agent.sh" <<'PEOF'
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export LANG=C.UTF-8
export TERM=xterm-256color
PEOF
chmod 644 "$R/etc/profile.d/agent.sh"

# 4) clientul android-binder PRECOMPILAT (altfel ar fi nevoie de gcc la fiecare instalare)
SRC=$REPO/app/src/main/assets/binder/debian_binder.c
if [ -f "$SRC" ]; then
    chroot "$R" /usr/bin/env -i PATH=/usr/local/bin:/usr/bin:/bin /bin/sh -c \
      "gcc -O2 -o /usr/local/bin/android-binder /dev/stdin" < "$SRC"
    chmod 755 "$R/usr/local/bin/android-binder"
    echo "[rootfs] android-binder precompilat: $(ls -l "$R/usr/local/bin/android-binder" | awk '{print $5}') bytes"
fi

# 5) marker: instalatorul il verifica (versiune de imagine)
touch "$R/.agent_rootfs_v2"

# 6) selftest INGUST inainte de impachetare (altfel un rootfs rupt ajunge in APK)
chroot "$R" /bin/sh -c 'set -e; gcc --version | head -1; python3 -V; make --version | head -1; echo ROOTFS_SELFTEST_OK'

mkdir -p "$(dirname "$OUT")"
tar -C "$R" --numeric-owner -czf "$OUT.tmp" .
mv -f "$OUT.tmp" "$OUT"
chmod 644 "$OUT"
ls -la "$OUT"
echo PACK_OK
