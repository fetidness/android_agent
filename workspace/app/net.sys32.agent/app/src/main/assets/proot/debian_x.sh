#!/system/bin/sh
# Porneste desktopul Debian in proot: Xvnc (:1, 5901) + fluxbox + xterm.
# Parametri: $1 = rootfs, $2 = libproot_exec.so, $3 = geometry (ex 1080x2340), $4 = actiune (start|stop|status)
ROOTFS="${1:-/data/local/tmp/proot/rootfs}"
PROOT="${2:-/data/local/tmp/libproot_exec.so}"
GEOM="${3:-1080x2340}"
ACTION="${4:-start}"
export PROOT_NO_SECCOMP=1
PP="$PROOT -r $ROOTFS -w /root --kill-on-exit --link2symlink --sysvipc --kernel-release=6.1.0-debian --bind=/dev --bind=/proc --bind=/sys"
E="/usr/bin/env -i PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin HOME=/root TERM=xterm DISPLAY=:1"

case "$ACTION" in
  stop)
    pkill -f Xtigervnc 2>/dev/null; pkill -f fluxbox 2>/dev/null; pkill -f "xterm" 2>/dev/null
    echo "desktop stopped"; exit 0;;
  status)
    pgrep -f Xtigervnc >/dev/null && echo "xvnc running pid=$(pgrep -f Xtigervnc)" || echo "xvnc not running"
    exit 0;;
esac

# deja pornit? nu dublam
if pgrep -f Xtigervnc >/dev/null; then echo "desktop already running"; exit 0; fi

# X socket dir (in rootfs) - proot --sysvipc + /tmp bind
$PP $E /bin/sh -c "mkdir -p /tmp/.X11-unix && chmod 1777 /tmp; echo xsetroot >/dev/null 2>&1" >/dev/null 2>&1

nohup $PP $E /usr/bin/Xtigervnc :1 -geometry "$GEOM" -depth 24 \
      -rfbport 5901 -SecurityTypes None -AlwaysShared -localhost -nolisten unix \
      > /data/local/tmp/proot/xvnc.log 2>&1 &
sleep 3
if pgrep -f Xtigervnc >/dev/null; then echo "xvnc started ($GEOM, port 5901)"; else echo "xvnc FAILED"; tail -5 /data/local/tmp/proot/xvnc.log; exit 1; fi

# fluxbox: fara avertismentul de wallpaper (xmessage) - ii dam un rootCommand gol si cream config
$PP $E /bin/sh -c "mkdir -p /root/.fluxbox && printf 'session.screen0.rootCommand:\nsession.screen0.toolbar.visible: true\nsession.styleFile: /usr/share/fluxbox/styles/bloe\n' > /root/.fluxbox/init; pkill -f xmessage 2>/dev/null; true" >/dev/null 2>&1
nohup $PP $E /usr/bin/fluxbox -no-slit > /data/local/tmp/proot/fluxbox.log 2>&1 &
sleep 2
nohup $PP $E /usr/bin/xterm -geometry 100x30+20+40 -title "Debian" > /data/local/tmp/proot/xterm.log 2>&1 &
sleep 1
echo "desktop ready: fluxbox + xterm on :1"
