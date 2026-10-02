#!/bin/bash
# Ruleaza un probe Python PE DEVICE, ca aplicatia (uid app), cu mediul corect al toolchain-ului.
#   folosire: tools/probe_run.sh temp/probe_x.py
# (recreat 2026-10-01; versiunea veche temp/mk.sh nu era in git si s-a pierdut la curatenie)
set -u
ADB=/home/gab/android/platform-tools/adb
P="${1:?folosire: probe_run.sh <fisier.py>}"
F=/data/data/net.sys32.agent/files
LIB=$($ADB shell dumpsys package net.sys32.agent 2>/dev/null | grep -m1 codePath | sed 's/.*codePath=//' | tr -d '\r')/lib/arm64
[ -n "$LIB" ] || { echo "nu am gasit calea APK (device conectat? aplicatia instalata?)"; exit 1; }

$ADB push "$P" /data/local/tmp/_probe.py >/dev/null || exit 1
$ADB shell run-as net.sys32.agent cp /data/local/tmp/_probe.py $F/python/_probe.py || exit 1

cat > /tmp/_probe_runner.sh <<EOF
#!/system/bin/sh
F=$F
export PYTHONHOME=\$F/pyhome
export PYTHONPATH=\$F/pyhome/lib/stdlib_extra.zip:\$F/pyhome/lib/python3.14:\$F/pyhome/lib/pysitepkg.zip:\$F/python
export LD_LIBRARY_PATH=$LIB:\$F/libs:\$F/toolchain/deps/lib:\$F/pyhome/lib
export TMPDIR=\$F/tmp
export HOME=\$F/home
cd \$F/python
exec $LIB/libpyexec.so \$F/python/_probe.py
EOF
$ADB push /tmp/_probe_runner.sh /data/local/tmp/_probe_runner.sh >/dev/null || exit 1
$ADB shell chmod 755 /data/local/tmp/_probe_runner.sh
$ADB shell run-as net.sys32.agent sh /data/local/tmp/_probe_runner.sh
