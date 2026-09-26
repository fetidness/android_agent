#!/bin/bash
# build_toolchain.sh - REBUILD toolchain-ul nativ (clang/lld/pkg-config/sysroot/deps)
# pentru APK. Ruleaza pe LAPTOP. Rezultatul merge in:
#   app/src/main/assets/toolchain/     (bin, lib, sysroot, deps, pyinc)
#   app/src/main/jniLibs/arm64-v8a/    (libclang_exec.so, liblld_exec.so, ...)
#
# DE CE: untrusted_app NU poate executa din filesDir (SELinux) -> binarele
# executabile trebuie sa fie in nativeLibraryDir (jniLibs, ca lib*_exec.so).
set -e
NDK=/home/gab/android/ndk/29.0.14206865/toolchains/llvm/prebuilt/linux-x86_64
SYSROOT=$NDK/sysroot
BUILD=/home/gab/Desktop/android_agent/build
APP=/home/gab/Desktop/android_agent/workspace/app/net.sys32.agent/app/src/main
TC=$APP/assets/toolchain
JNI=$APP/jniLibs/arm64-v8a

echo "1/4: LLVM (clang+lld) - vezi build/llvm-project, ~1h15m"
[ -f $BUILD/toolchain/bin/clang-21 ] || echo "  ATENTIE: ruleaza intai build-ul LLVM (vezi README)"

echo "2/4: pkgconf (pkg-config pentru ARM64)"
[ -f $BUILD/toolchain/deps/bin/pkg-config ] || echo "  vezi build/pkgconf-2.3.0"

echo "3/4: copiez toolchain in assets"
mkdir -p $TC $JNI
cp -r $BUILD/toolchain/bin $TC/ 2>/dev/null || true
cp -r $BUILD/toolchain/lib $TC/ 2>/dev/null || true
cp -r $SYSROOT/usr/include $TC/sysroot/usr/ 2>/dev/null || true
cp -r $SYSROOT/usr/lib/aarch64-linux-android/35 $TC/sysroot/usr/lib/aarch64-linux-android/ 2>/dev/null || true
cp -r $BUILD/android-deps/include $TC/deps/ 2>/dev/null || true
cp -r $BUILD/android-deps/lib $TC/deps/ 2>/dev/null || true
cp -r $BUILD/Python-3.14.7/Include $TC/pyinc/ 2>/dev/null || true
cp $BUILD/Python-3.14.7/pyconfig.h $TC/pyinc/ 2>/dev/null || true

echo "4/4: binarele EXECUTABILE in jniLibs (lib*_exec.so)"
cp $TC/bin/clang-21      $JNI/libclang_exec.so
cp $TC/bin/lld           $JNI/liblld_exec.so
cp $TC/bin/llvm-ar       $JNI/libllvmar_exec.so
cp $TC/bin/llvm-ranlib   $JNI/libllvmranlib_exec.so
cp $TC/bin/llvm-strip    $JNI/libllvmstrip_exec.so
cp $TC/bin/llvm-nm       $JNI/libllvmn_m_exec.so 2>/dev/null || cp $TC/bin/llvm-nm $JNI/libllvmnm_exec.so
cp $TC/deps/bin/pkg-config $JNI/libpkgconf_exec.so

echo "GATA. APK-ul va include toolchain + binarele executabile."
