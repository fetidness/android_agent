#!/usr/bin/env python3
"""
android_build.py - COMPILARE APK PE DEVICE, COMPLET OFFLINE.
Toate uneltele vin cu APK-ul (assets/android_build/ + jniLibs/*.so). ZERO descarcari.

Arhitectura (vezi BUILD_ANDROID_ON_DEVICE.md):
  - Binararele EXECUTABILE (java, aapt2) sunt in APK lib/arm64 ca lib*_exec.so
    (SELinux permite exec doar de acolo).
  - Restul (modulele JDK, Gradle, SDK, NDK, sqlite) se extrag din assets in filesDir.

Folosire:
  import android_build
  android_build.setup()                      # extrage tot (o singura data)
  apk = android_build.build("/path/project")
  print(android_build.verify(apk))
"""
import os, sys, shutil, subprocess, zipfile, tarfile, io, time, glob, json

_HERE = os.path.dirname(os.path.abspath(__file__))
# _HERE = <filesDir>/python ; filesDir = parintele
F = os.path.dirname(os.path.dirname(_HERE))
# caz: python e in <filesDir>/python
if not os.path.isdir(F):
    F = "/data/data/net.sys32.agent/files"

BUILD = F + "/android_build"
ASSETS = _HERE + "/../assets/android_build"      # langa python/ sunt assets? de obicei nu
# assets-ul real ajunge in filesDir la prima rulare (MainActivity le copiaza) - incercam mai multe
def _assets_dir():
    for c in [F + "/assets/android_build",
              os.path.dirname(F) + "/assets/android_build",
              os.path.dirname(os.path.dirname(_HERE)) + "/assets/android_build",
              _HERE + "/../../assets/android_build"]:
        if os.path.isdir(c) and os.path.exists(c + "/platform36.zip"): return c
    # niciuna nu are platform36.zip: intoarce prima care exista (macar e un inceput)
    for c in [F + "/assets/android_build",
              os.path.dirname(F) + "/assets/android_build",
              _HERE + "/../../assets/android_build"]:
        if os.path.isdir(c): return c
    return F + "/assets/android_build"

def _find_base_apk():
    """Gaseste base.apk al acestei aplicatii (assets-urile stau in APK, nu pe disc)."""
    # 1) din /proc/self/maps (SELinux poate bloca scandir pe /data/app - dar nu pe APK-ul propriu)
    try:
        import re as _re
        for line in open("/proc/self/maps"):
            m = _re.search(r"(/data/app/[^\s]+/base\.apk)", line)
            if m:
                return m.group(1)
    except Exception: pass
    # 2) glob pe /data/app (poate esua pe SELinux - ignoram)
    try:
        for apk in glob.glob("/data/app/*/net.sys32.agent*/base.apk") + glob.glob("/data/app/*/*/base.apk"):
            if os.path.exists(apk + ".nonexistent") is False and os.path.exists(apk):
                return apk
    except Exception: pass
    # 3) 'pm path' (daca putem rula shell)
    for pkg in ["net.sys32.agent", "net.sys32.javahost"]:
        try:
            out = subprocess.run(["pm", "path", pkg], capture_output=True, text=True, timeout=10).stdout
            for line in out.splitlines():
                if line.startswith("package:"):
                    return line[len("package:"):].strip()
        except Exception: pass
    return None

def _extract_assets_from_apk(dest=None, force=False):
    """Extrage assets/android_build/* din base.apk in filesDir (setup le cauta pe disc).
       Idempotent: sare peste fisierele deja extrase cu dimensiune corecta."""
    dest = dest or (F + "/assets/android_build")
    if os.path.isdir(dest) and os.path.exists(dest + "/platform36.zip") and not force:
        return dest
    apk = _find_base_apk()
    if not apk or not os.path.exists(apk):
        log("  assets: base.apk negasit - nu pot extrage")
        return dest if os.path.isdir(dest) else None
    try:
        with zipfile.ZipFile(apk) as z:
            need = [n for n in z.namelist()
                    if n.startswith("assets/android_build/") and not n.endswith("/")]
            if not need:
                return None
            log(f"  assets: extrag {len(need)} fisiere din {os.path.basename(apk)}...")
            os.makedirs(dest, exist_ok=True)
            for n in need:
                rel = n[len("assets/android_build/"):]
                out = os.path.join(dest, rel)
                try:
                    info = z.getinfo(n)
                    if os.path.exists(out) and os.path.getsize(out) == info.file_size:
                        continue
                    os.makedirs(os.path.dirname(out), exist_ok=True)
                    with z.open(n) as s, open(out, "wb") as o:
                        while True:
                            b = s.read(1 << 20)
                            if not b: break
                            o.write(b)
                except Exception as e:
                    log("    extract err:", rel, e)
        log("  assets extrase OK")
    except Exception as e:
        log("  assets extract err:", e)
    return dest

def _link_versions(src, dest_dir, versions=("1", "2", "3")):
    """Creeaza in dest_dir symlink-uri <lib>.so.N -> src, daca binarul cere nume versionat
       (ex: java cere libz.so.1, aapt2 cere libexpat.so.1, dar APK-ul are doar libz.so)."""
    try:
        os.makedirs(dest_dir, exist_ok=True)
    except Exception:
        return
    base = os.path.basename(src)
    if not base.endswith(".so"):
        return
    for v in versions:
        l = os.path.join(dest_dir, base + "." + v)
        if not os.path.lexists(l):
            try: os.symlink(src, l)
            except Exception: pass

def _link_all_versions(lib_dir, dest_dirs, versions=("1", "2", "3")):
    """Pentru toate *.so din lib_dir creeaza symlink-uri versionate in fiecare dest_dir.
       Rezolva clasa de erori 'library libX.so.N not found' (java/aapt2/etc)."""
    if not os.path.isdir(lib_dir): return 0
    n = 0
    for f in os.listdir(lib_dir):
        if f.endswith(".so"):
            for d in dest_dirs:
                _link_versions(os.path.join(lib_dir, f), d, versions)
                n += 1
    return n

JDK = BUILD + "/jdk"
GRADLE = BUILD + "/gradle"
GRADLEHOME = BUILD + "/gradlehome"
SDK = BUILD + "/sdk"
TC = F + "/toolchain"
TMP = BUILD + "/tmp"
NATIVE = None    # nativeLibraryDir (lib*_exec.so), setat in _find_javahost_lib

def log(*a): print("[android_build]", *a, flush=True)

def _find_javahost_lib():
    """nativeLibraryDir al acestei aplicatii (contine lib*_exec.so).
       glob() NU functioneaza pe /data/app (SELinux blocheaza scandir) - citim /proc/self/maps."""
    global NATIVE
    if NATIVE: return NATIVE
    # 1) TC_NATIVE din env (setat de MainActivity = applicationInfo.nativeLibraryDir) - CEL MAI SIGUR
    tn = os.environ.get("TC_NATIVE")
    if tn and os.path.exists(tn + "/libjava_exec.so"):
        NATIVE = tn; return tn
    import re as _re
    try:
        for line in open("/proc/self/maps"):
            m = _re.search(r"(/data/app/[^\s]+/lib/arm64)/", line)
            if m:
                d = m.group(1)
                if os.path.exists(d + "/libjava_exec.so"):
                    NATIVE = d; return d
    except Exception: pass
    # fallback: 'pm path <pkg>' (shell) pentru APK-uri cunoscute
    for pkg in ["net.sys32.agent", "net.sys32.javahost"]:
        try:
            out = subprocess.run(["pm", "path", pkg], capture_output=True, text=True, timeout=10).stdout
            for line in out.splitlines():
                if line.startswith("package:"):
                    apk = line[len("package:"):].strip()
                    d = apk.rsplit("/", 1)[0] + "/lib/arm64"
                    if os.path.exists(d + "/libjava_exec.so"):
                        NATIVE = d; return d
        except Exception: pass
    return None

def _ar_members(path):
    with open(path, "rb") as f:
        assert f.read(8) == b"!<arch>\n"
        out = []
        while True:
            hdr = f.read(60)
            if len(hdr) < 60: break
            nm = hdr[0:16].decode(errors="ignore").strip().rstrip("/")
            try: size = int(hdr[48:58].decode().strip())
            except: break
            off = f.tell(); out.append((nm, size, off)); f.seek(off + size + (size % 2))
        return out

def _deb_extract(deb, dest, strip_prefix=True, only=None):
    """Extrage un .deb (ar -> data.tar.{xz,gz,zst}). only=functie(nume)->bool."""
    raw = open(deb, "rb").read()
    dm = [m for m in _ar_members(deb) if m[0].startswith("data.tar")][0]
    n, s, o = dm; blob = raw[o:o + s]
    mode = "r:xz" if blob[:6] == b"\xfd7zXZ\x00" else ("r:gz" if blob[:2] == b"\x1f\x8b" else "r:zst")
    os.makedirs(dest, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(blob), mode=mode) as tf:
        for m in tf.getmembers():
            nm = m.name
            if strip_prefix:
                for pre in ["data/data/com.termux/files/usr/", "./data/data/com.termux/files/usr/"]:
                    if nm.startswith(pre):
                        nm = nm[len(pre):]; break
            if only and not only(nm): continue
            m.name = nm
            if nm.startswith("..") or nm.startswith("/"): continue
            try: tf.extract(m, dest, filter="fully_trusted")
            except Exception: pass

# ★ SURSA DE ADEVAR pentru patch-uri: copia de pe sdcard (supravietuieste clear data)
# calea patch-urilor de supravietuire (pentru restore dupa clear data); configurabila prin env
PATCHES = os.environ.get("AGENT_PATCHES_DIR", "/storage/emulated/0/Download/Agent/agent_patches")
_SELF = os.path.abspath(__file__)

def _selfheal(files=None):
    """Re-aplica versiunile optimizate din PATCHES peste cele extrase din APK.
       Ruleaza automat la setup(): la clear data, assets-urile din APK sunt VECHI
       (bug-uri: assets/libz/libexpat/raportare) -> le inlocuim cu cele bune.
       Nu face nimic daca PATCHES nu exista (nu e fatal)."""
    if not os.path.isdir(PATCHES):
        return
    mine = files or ["android_build.py", "git_build_zero_driver.py", "devhelper.py"]
    healed = []
    for f in mine:
        s = PATCHES + "/" + f
        d = os.path.dirname(_SELF) + "/" + f
        try:
            if not os.path.exists(s):
                continue
            # daca fisierul de pe disc e deja >= (optimizat), sari
            if os.path.exists(d) and os.path.getsize(d) >= os.path.getsize(s):
                continue
            shutil.copy2(s, d)
            healed.append(f)
        except Exception:
            pass
    # memoria: in filesDir radacina
    try:
        sm = PATCHES + "/memory.md"
        dm = F + "/memory.md"
        if os.path.exists(sm) and (not os.path.exists(dm) or os.path.getsize(dm) < os.path.getsize(sm)):
            shutil.copy2(sm, dm); healed.append("memory.md")
    except Exception:
        pass
    if healed:
        log("self-heal: re-aplicat din sdcard ->", ", ".join(healed),
            "(reincarca modulul pentru a folosi versiunile noi)")
    return healed

def setup(force=False):
    """Extrage TOATE uneltele din assets in filesDir. Idempotent."""
    _selfheal()
    marker = BUILD + "/.setup_ok"
    if os.path.exists(marker) and not force:
        return True
    log("setup: extrag uneltele (poate dura)...")
    os.makedirs(BUILD, exist_ok=True); os.makedirs(TMP, exist_ok=True)
    A = _assets_dir()
    if not (os.path.isdir(A) and os.path.exists(A + "/platform36.zip")):
        # assets-urile vin in base.apk (nu pe disc) - le extragem noi
        A = _extract_assets_from_apk(F + "/assets/android_build") or A
    log("assets:", A, "exista:", os.path.isdir(A))
    _find_javahost_lib()

    # ---- 1) JDK module (din openjdk deb) ----
    if not os.path.exists(JDK + "/lib/libjvm.so"):
        deb = A + "/openjdk-21.deb"
        if os.path.exists(deb):
            _deb_extract(deb, BUILD + "/_jdk_tmp")
            # muta lib/jvm/java-21-openjdk -> jdk
            src = BUILD + "/_jdk_tmp/lib/jvm/java-21-openjdk"
            if os.path.isdir(src):
                if os.path.exists(JDK): shutil.rmtree(JDK)
                shutil.move(src, JDK)
                log("  JDK module extrase")
    # JAVA_HOME/bin: symlink la lib*_exec.so din APK
    if NATIVE and os.path.isdir(JDK + "/bin"):
        jmap = {"java":"libjava_exec.so","jlink":"libjlink_exec.so","jmod":"libjmod_exec.so",
                "jimage":"libjimage_exec.so","javac":"libjavac_exec.so","jar":"libjar_exec.so",
                "keytool":"libkeytool_exec.so","jarsigner":"libjarsigner_exec.so"}
        for tool, lib in jmap.items():
            p = JDK + "/bin/" + tool
            if os.path.lexists(p): os.remove(p)
            os.symlink(NATIVE + "/" + lib, p)
        log("  JAVA_HOME/bin -> APK libs")
        # libs in jdk/lib (E in LD_LIBRARY_PATH-ul daemonului Gradle): symlink toate libs din APK
        try:
            jlib = JDK + "/lib"; os.makedirs(jlib, exist_ok=True)
            deps = TC + "/deps/lib"; os.makedirs(deps, exist_ok=True)
            for f in os.listdir(NATIVE):
                if f.endswith(".so"):
                    src = NATIVE + "/" + f
                    for dd in (jlib, deps):
                        dst = dd + "/" + f
                        if not os.path.lexists(dst):
                            try: os.symlink(src, dst)
                            except Exception: pass
            log("  libs -> jdk/lib + toolchain/deps/lib")
        except Exception as e: log("  libs symlink err:", e)

    # ---- 2) Gradle ----
    if not os.path.exists(GRADLE + "/lib/gradle-launcher-9.8.0.jar"):
        deb = A + "/gradle.deb"
        if os.path.exists(deb):
            _deb_extract(deb, BUILD + "/_gr_tmp", only=lambda n: n.startswith("opt/gradle"))
            src = BUILD + "/_gr_tmp/opt/gradle"
            if os.path.isdir(src):
                if os.path.exists(GRADLE): shutil.rmtree(GRADLE)
                shutil.move(src, GRADLE)
                log("  Gradle extras")
    # libnative-platform.so din jar
    lp = GRADLE + "/lib/libnative-platform.so"
    if not os.path.exists(lp):
        jars = glob.glob(GRADLE + "/lib/native-platform-linux-aarch64*.jar")
        for j in jars:
            try:
                with zipfile.ZipFile(j) as z:
                    for n in z.namelist():
                        if n.endswith(".so"):
                            d = z.read(n); outp = GRADLE + "/lib/" + os.path.basename(n)
                            open(outp, "wb").write(d); os.chmod(outp, 0o755)
            except Exception: pass
        log("  libnative-platform extras")

    # ---- 3) SDK ----
    plat = SDK + "/platforms/android-36"
    if not os.path.exists(plat + "/android.jar"):
        zp = A + "/platform36.zip"
        if not os.path.exists(zp):
            # ★ assets lipsa = setup imposibil; spunem EXPLICIT ce si de unde (nu eroare obscura)
            log("  EROARE: lipseste %s" % zp)
            log("  assets dir = %s (exista: %s)" % (A, os.path.isdir(A)))
            log("  repara: _extract_assets_from_apk() sau reinstaleaza APK-ul")
            raise RuntimeError("assets/android_build/platform36.zip lipseste - setup imposibil")
        if os.path.exists(zp):
            with zipfile.ZipFile(zp) as z:
                for name in z.namelist():
                    if name.startswith("android-36/") and not name.endswith("/"):
                        rel = name[len("android-36/"):]
                        dst = os.path.join(plat, rel)
                        os.makedirs(os.path.dirname(dst), exist_ok=True)
                        with z.open(name) as s, open(dst, "wb") as o:
                            o.write(s.read())
            log("  SDK platform extras")
    # package.xml platforma
    # ★ fara makedirs aici: daca zip-ul nu s-a extras (lipsa/corupt), 'plat' nu exista
    #   si chiar open(px,"w") cadea cu FileNotFoundError (bug-ul original)
    os.makedirs(plat, exist_ok=True)
    px = plat + "/package.xml"
    if not os.path.exists(px):
        open(px, "w").write('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<ns2:repository xmlns:ns2="http://schemas.android.com/repository/android/common/02" '
            'xmlns:ns5="http://schemas.android.com/sdk/android/repo/repository2/03" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            '<license id="android-sdk-license" type="text">8933bad161af4178b1185d1a37fbf41ea5269c55</license>'
            '<localPackage path="platforms;android-36" obsolete="false">'
            '<type-details xsi:type="ns5:platformDetailsType"><api-level>36</api-level><codename></codename></type-details>'
            '<revision><major>1</major></revision><display-name>Android SDK Platform 36</display-name>'
            '</localPackage></ns2:repository>')
    # build-tools
    bt = SDK + "/build-tools/36.0.0"
    if not os.path.exists(bt + "/aapt2") and not os.path.islink(bt + "/aapt2"):
        zp = A + "/buildtools36.zip"
        if os.path.exists(zp):
            os.makedirs(bt, exist_ok=True)
            with zipfile.ZipFile(zp) as z:
                root = z.namelist()[0].split("/")[0]
                for name in z.namelist():
                    if name.startswith(root + "/") and not name.endswith("/"):
                        rel = name[len(root + "/"):]
                        dst = os.path.join(bt, rel)
                        os.makedirs(os.path.dirname(dst), exist_ok=True)
                        with z.open(name) as s, open(dst, "wb") as o:
                            o.write(s.read())
            log("  SDK build-tools extras")
    # licenses
    lic = SDK + "/licenses"; os.makedirs(lic, exist_ok=True)
    open(lic + "/android-sdk-license", "w").write(
        "\n8933bad161af4178b1185d1a37fbf41ea5269c55\nd56f5187479451eabf01fb78af6dfcb131a6481e\n"
        "24333f8a63b6825ea9c5514f83c2829b004d1fee\n")
    open(lic + "/android-sdk-preview-license", "w").write("\n84831b9409646a918e30573bab4c9c91346d8abd\n")

    # ---- 4) aapt2 in build-tools + fake aapt2 (override) ----
    if NATIVE:
        pa = bt + "/aapt2"
        if os.path.lexists(pa): os.remove(pa)
        os.symlink(NATIVE + "/libaapt2_exec.so", pa)
        # dir aapt2 (fara .so) pt aapt2FromMavenOverride
        ad = BUILD + "/aapt2bin"; os.makedirs(ad, exist_ok=True)
        ap = ad + "/aapt2"
        if os.path.lexists(ap): os.remove(ap)
        os.symlink(NATIVE + "/libaapt2_exec.so", ap)

    # ---- 4b) toolchain (extras din assets/toolchain + symlink-uri bin) ----
    A_tc = A + "/toolchain"
    if os.path.isdir(A_tc) and not os.path.exists(TC + "/sysroot/usr/include"):
        log("  extrag toolchain (sysroot/deps/lib/cmake)...")
        os.makedirs(TC, exist_ok=True)
        for item in os.listdir(A_tc):
            s = A_tc + "/" + item; d = TC + "/" + item
            if os.path.exists(d): continue
            try:
                if os.path.isdir(s): shutil.copytree(s, d, symlinks=False)
                else: shutil.copy(s, d)
            except Exception as e: log("  toolchain copy err:", item, e)
    # libc++ (folderele __* sunt in ZIP, AAPT2 le elimina din assets)
    zf = A_tc + "/libcxx_full.zip"
    incv1 = TC + "/sysroot/usr/include/c++/v1"
    if os.path.exists(zf) and not os.path.isdir(incv1):
        try:
            os.makedirs(incv1, exist_ok=True)
            with zipfile.ZipFile(zf) as z:
                z.extractall(TC + "/sysroot/usr/include")
            log("  libc++ extras din zip")
        except Exception as e: log("  libcxx err:", e)
    # symlink-uri bin (clang/cmake/ninja/etc -> APK libs)
    if NATIVE:
        os.makedirs(TC + "/bin", exist_ok=True)
        bmap = {"clang":"libclang_exec.so","clang++":"libclang_exec.so","clang-21":"libclang_exec.so",
                "clang++-21":"libclang_exec.so","ld.lld":"liblld_exec.so","lld":"liblld_exec.so",
                "ar":"libllvmar_exec.so","ranlib":"libllvmranlib_exec.so","strip":"libllvmstrip_exec.so",
                "nm":"libllvmnm_exec.so","cmake":"libcmake_exec.so","ninja":"libninja_exec.so",
                "make":"libmake_exec.so","perl":"libperl_exec.so","pkgconf":"libpkgconf_exec.so",
                "pkg-config":"libpkgconf_exec.so","flang":"libflang_exec.so"}
        for name, lib in bmap.items():
            p2 = TC + "/bin/" + name
            src = NATIVE + "/" + lib
            if os.path.exists(src):
                if os.path.lexists(p2): os.remove(p2)
                os.symlink(src, p2)

    # ---- 5) fake-NDK ----
    ndk = TC + "/ndk"
    pn = ndk + "/toolchains/llvm/prebuilt/linux-x86_64"
    os.makedirs(pn + "/bin", exist_ok=True)
    open(ndk + "/source.properties", "w").write("Pkg.Desc = Android NDK (offline)\nPkg.Revision = 27.1.12297006\n")
    os.makedirs(ndk + "/build/cmake", exist_ok=True)
    tccmake = TC + "/tmp/android.toolchain.cmake"
    if os.path.exists(tccmake):
        shutil.copy(tccmake, ndk + "/build/cmake/android.toolchain.cmake")
    for name in ["clang","clang++","ld","ld.lld","ar","ranlib","strip","nm",
                 "llvm-strip","llvm-ar","llvm-ranlib","llvm-nm"]:
        srcn = name.replace("llvm-","")
        src = TC + "/bin/" + srcn
        dst = pn + "/bin/" + name
        if os.path.exists(src):
            if os.path.lexists(dst): os.remove(dst)
            os.symlink(src, dst)
    sr = pn + "/sysroot"
    if os.path.islink(sr): os.remove(sr)
    elif os.path.isdir(sr): import shutil as _sh; _sh.rmtree(sr, ignore_errors=True)
    if not os.path.lexists(sr):
        os.symlink(TC + "/sysroot", sr)

    # ---- 6) cmake/ninja in SDK ----
    cm = SDK + "/cmake/3.22.1/bin"; os.makedirs(cm, exist_ok=True)
    for t in ["cmake","ninja"]:
        src = TC + "/bin/" + t
        if os.path.exists(src):
            p = cm + "/" + t
            if os.path.lexists(p): os.remove(p)
            os.symlink(src, p)

    # ---- 7) libs aapt2 in toolchain/deps/lib (LD path-ul daemonului) ----
    deps = TC + "/deps/lib"; os.makedirs(deps, exist_ok=True)
    if NATIVE:
        for f in os.listdir(NATIVE):
            if f.endswith(".so") and not any(x in f for x in ["java","python","aapt2","llvm","clang","cmake","ninja","perl","rust","make","cargo","flang","pkgconf","lld","patchelf","maturin","shwrap","ccrust"]):
                dst = deps + "/" + f
                if not os.path.exists(dst):
                    try: os.symlink(NATIVE + "/" + f, dst)
                    except Exception: pass
    # glibc shim
    for name, tgt in [("libm.so.6","/system/lib64/libm.so"),("libpthread.so.0","/system/lib64/libc.so"),
                      ("libdl.so.2","/system/lib64/libdl.so"),("libc.so.6","/system/lib64/libc.so")]:
        p = deps + "/" + name
        if not os.path.lexists(p):
            try: os.symlink(tgt, p)
            except Exception: pass

    # ---- 7b) symlink-uri VERSIONATE (.so.N) pentru libs native ----
    # APK-ul are libz.so / libexpat.so, dar binaroii (java, aapt2) cer libz.so.1 / libexpat.so.1.
    # Fara astea: 'CANNOT LINK EXECUTABLE java: library libz.so.1 not found'
    #             'aapt2: library libexpat.so.1 not found: needed by main executable'
    try:
        targets = [JDK + "/lib", deps, BUILD + "/aapt2bin", TC + "/bin", SDK + "/build-tools"]
        _link_all_versions(JDK + "/lib", targets)
        if NATIVE:
            _link_all_versions(NATIVE, targets)
        # libexpat/libz sunt cerute frecvent - asigura-le explicit si in deps
        for cand in [JDK + "/lib/libexpat.so", TC + "/deps/lib/libexpat.so"]:
            if os.path.exists(cand):
                for v in ("1", "2", "3"):
                    l = deps + "/libexpat.so." + v
                    if not os.path.lexists(l):
                        try: os.symlink(cand, l)
                        except Exception: pass
        log("  symlink-uri versionate (.so.N) create")
    except Exception as e:
        log("  links versionate err:", e)

    # ---- 8) sqlite-jdbc 3.46 (pt kapt/Room) + dir org.sqlite.lib.path ----
    sq = BUILD + "/sqlitedir"; os.makedirs(sq, exist_ok=True)
    sqj = A + "/sqlite-jdbc-3.46.0.0.jar"
    if os.path.exists(sqj):
        try:
            with zipfile.ZipFile(sqj) as z:
                so = [n for n in z.namelist() if "Linux-Android/aarch64/libsqlitejdbc.so" in n]
                if so:
                    open(sq + "/libsqlitejdbc.so", "wb").write(z.read(so[0]))
                    os.chmod(sq + "/libsqlitejdbc.so", 0o755)
                    log("  sqlite-jdbc Android extras")
        except Exception as e: log("  sqlite err:", e)

    # ---- 9) keystore debug ----
    kd = BUILD + "/.android"; os.makedirs(kd, exist_ok=True)
    ks = kd + "/debug.keystore"
    if not os.path.exists(ks) and NATIVE:
        _env_run([JDK + "/bin/keytool","-genkeypair","-keystore",ks,"-alias","androiddebugkey",
                  "-storepass","android","-keypass","android","-keyalg","RSA","-keysize","2048",
                  "-validity","10000","-dname","CN=Android Debug,O=Android,C=US"])

    open(marker, "w").write(str(time.time()))
    log("setup OK")
    return True

def _env(jh_lib=None):
    jh_lib = jh_lib or NATIVE or _find_javahost_lib()
    env = dict(os.environ)
    env["JAVA_HOME"] = JDK
    env["GRADLE_USER_HOME"] = GRADLEHOME
    env["ANDROID_HOME"] = SDK; env["ANDROID_SDK_ROOT"] = SDK
    env["HOME"] = BUILD; env["TMPDIR"] = TMP
    env["PATH"] = f"{TC}/bin:{F}/tmp:{env.get('PATH','')}"
    ld = f"{BUILD}/tlib:{TMP}:{GRADLE}/lib:{TC}/deps/lib"
    if jh_lib: ld += f":{jh_lib}"
    ld += f":{JDK}/lib:{JDK}/lib/server"
    env["LD_LIBRARY_PATH"] = ld
    env["JAVA_TOOL_OPTIONS"] = (f"-Duser.home={BUILD} -Djdk.lang.Process.launchMechanism=VFORK "
                                f"-Djava.io.tmpdir={TMP}")
    return env

def _env_run(cmd, timeout=120):
    r = subprocess.run(cmd, env=_env(), capture_output=True, text=True, timeout=timeout)
    return r

def build(project_dir, task="assembleDebug", timeout=3600):
    setup()
    _find_javahost_lib()
    # setup() e sarit cand .setup_ok exista: re-asiguram totusi symlink-urile versionate
    # (altfel java/aapt2 dau 'library libX.so.N not found' la prima compilare dupa curatare)
    try:
        tgt = [JDK + "/lib", TC + "/deps/lib", BUILD + "/aapt2bin", TC + "/bin"]
        _link_all_versions(JDK + "/lib", tgt)
        if NATIVE: _link_all_versions(NATIVE, tgt)
        for cand in [JDK + "/lib/libexpat.so", TC + "/deps/lib/libexpat.so"]:
            if os.path.exists(cand):
                for v in ("1", "2", "3"):
                    l = TC + "/deps/lib/libexpat.so." + v
                    if not os.path.lexists(l):
                        try: os.symlink(cand, l)
                        except Exception: pass
    except Exception as e:
        log("links versionate warn:", e)
    env = _env()
    launcher = GRADLE + "/lib/gradle-launcher-9.8.0.jar"
    if not os.path.exists(launcher):
        log("EROARE: gradle-launcher lipsa"); return None
    cmd = [JDK + "/bin/java",
           f"-Duser.home={BUILD}", "-Djdk.lang.Process.launchMechanism=VFORK",
           f"-Djava.io.tmpdir={TMP}", f"-Djava.library.path={TMP}:{GRADLE}/lib",
           "-cp", launcher, "org.gradle.launcher.GradleMain", task]
    # asigura gradle.properties cu VFORK + aapt2 override + tmpdir (altfel jlink/aapt2 esueaza)
    try:
        gp = os.path.join(project_dir, "gradle.properties")
        props = ""
        if os.path.exists(gp): props = open(gp).read()
        add = []
        if "jdk.lang.Process.launchMechanism" not in props:
            add.append("org.gradle.jvmargs=-Xmx2g -Djava.io.tmpdir=" + TMP +
                       " -Djdk.lang.Process.launchMechanism=VFORK -Duser.home=" + BUILD)
        if "aapt2FromMavenOverride" not in props:
            add.append("android.aapt2FromMavenOverride=" + BUILD + "/aapt2bin/aapt2")
        if "org.gradle.daemon" not in props:
            add.append("org.gradle.daemon=false")
        if add:
            with open(gp, "a") as f: f.write("\n" + "\n".join(add) + "\n")
        # asigura aapt2bin/aapt2 (symlink fara .so)
        ad = BUILD + "/aapt2bin"
        try: os.makedirs(ad, exist_ok=True)
        except Exception: pass
        ap = ad + "/aapt2"
        if NATIVE and not os.path.lexists(ap):
            try: os.symlink(NATIVE + "/libaapt2_exec.so", ap)
            except Exception: pass
    except Exception as e: log("gradle.properties warn:", e)
    # inlocuieste aapt2 din Maven transforms cache cu symlink la al nostru (AGP il descarca x86_64)
    if NATIVE:
        try:
            for a in glob.glob(GRADLEHOME + "/caches/**/aapt2-*-linux/aapt2", recursive=True):
                if not os.path.islink(a):
                    try: os.rename(a, a + ".x86.bak")
                    except Exception: pass
                if os.path.lexists(a): os.remove(a)
                os.symlink(NATIVE + "/libaapt2_exec.so", a)
        except Exception as e: log("aapt2 cache warn:", e)
    log("build:", project_dir, task)
    t0 = time.time()
    r = subprocess.run(cmd, cwd=project_dir, env=env, capture_output=True, text=True, timeout=timeout)
    # ★ succesul se decide dupa OUTPUT-ul produs, nu doar dupa textul din log:
    #   Gradle poate scrie "BUILD SUCCESSFUL" pe stderr sau poate folosi progres nou;
    #   un APK proaspat (mtime > t0) este dovada reala ca build-ul a reusit.
    txt = (r.stdout or "") + "\n" + (r.stderr or "")
    said_ok = ("BUILD SUCCESSFUL" in txt) or ("BUILD FAILED" not in txt and r.returncode == 0)
    apks = sorted(glob.glob(project_dir + "/app/build/outputs/apk/**/*.apk", recursive=True),
                  key=os.path.getmtime)
    fresh = [a for a in apks if os.path.getmtime(a) >= t0 - 2]
    ok = bool(fresh) or (said_ok and bool(apks))
    log("BUILD SUCCESSFUL" if ok else "BUILD FAILED")
    if not ok:
        log(txt[-3000:]); 
    apk = (fresh[-1] if fresh else (apks[-1] if apks else None))
    return apk if ok else None

def verify(apk):
    if not apk or not os.path.exists(apk):
        return {"ok": False, "error": "apk lipsa"}
    out = {"ok": True, "path": apk, "size_mb": round(os.path.getsize(apk)/1e6, 1)}
    try:
        with zipfile.ZipFile(apk) as z:
            names = z.namelist()
            out["has_dex"] = any(n.startswith("classes") and n.endswith(".dex") for n in names)
            out["has_arsc"] = "resources.arsc" in names
            out["has_manifest"] = "AndroidManifest.xml" in names
            out["libs"] = len([n for n in names if n.startswith("lib/")])
            out["files"] = len(names)
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return out

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("folosire: android_build.py setup|build <dir>|verify <apk>"); sys.exit(1)
    c = sys.argv[1]
    if c == "setup": print(json.dumps({"ok": setup()}))
    elif c == "build": apk = build(sys.argv[2]); print(json.dumps(verify(apk) if apk else {"ok": False}))
    elif c == "verify": print(json.dumps(verify(sys.argv[2]), indent=2))
