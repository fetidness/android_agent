#!/usr/bin/env python3
"""
selfheal.py - REGISTRU DE INVARIANTE AUTO-VINDECATE (nivel aplicatie).

DE CE: pe device, starea "sanatoasa" se strica SINGURA in momente previzibile -
in principal la fiecare update de APK (Kotlin re-extrage assets si schimba
nativeLibraryDir: /data/app/~~x==/pkg-y==/lib/arm64 primeste alt hash) si la
orice operatie care scrie in site-packages. Simptomele nu arata ca o problema de
mediu, arata ca "unealta lipseste/defecta", iar agentul consuma 20-40 de pasi
(plus tokenii aferenti, cu TOT contextul re-trimis la fiecare pas) ca sa
descopere singur ce se reparase deja de 27 de ori in toolchain.py.

CE FACE: fiecare invariant are check() IEFTIN (stat/readlink/lista, fara
subprocess, fara retea) si fix() IDEMPOTENT care REUTILIZEAZA functiile de
reparare deja dovedite din toolchain.py. Fix-ul ruleaza DOAR daca check-ul a
gasit ceva rupt - de asta pornirea rămâne ieftina chiar daca registrul e mare.

BURETUL DE TOKENI (regula de baza): heal-ul ruleaza in COD, deci 0 tokeni.
Rezultatul se afiseaza pe ECRAN (0 tokeni) intr-o singura linie, si DOAR daca a
reparat ceva. In contextul modelului ajunge doar la cerere (action=heal), intr-o
linie. Nimic din acest modul nu are voie sa vorbeasca singur modelului.

Faze:
  startup - la fiecare pornire a agentului (doar verificari ieftine)
  build   - inainte de orice pip_install / compile (include pip.conf/sysconfig)
  error   - automat, cand un tool intoarce un simptom de "launcher mort"/mediu
            patat (apelat de agent.py; rate-limited acolo)
  full    - la cerere (action=heal): include si reparatiile mai scumpe (offline)
"""

import os
import sys
import json
import time

F = "/data/data/net.sys32.agent/files"
MARK = F + "/.selfheal_state"

_TC = None


def _tc():
    """toolchain.py (sursa unica a fix-urilor dovedite) - incarcat o singura data."""
    global _TC
    if _TC is not None:
        return _TC
    try:
        import toolchain as _m                    # calea normala (agentul il are in sys.path)
        _TC = _m
        return _TC
    except Exception:
        pass
    try:
        import importlib.util as _ilu
        _p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "toolchain.py")
        _sp = _ilu.spec_from_file_location("_selfheal_tc", _p)
        _m = _ilu.module_from_spec(_sp)
        _sp.loader.exec_module(_m)
        _TC = _m
    except Exception:
        _TC = None
    return _TC


# ---------------------------------------------------------------------------
# stare persistenta (doar ca sa prindem SCHIMBAREA de nativeLibraryDir,
# care e cel mai ieftin semnal ca linkurile din files/ sunt moarte)
# ---------------------------------------------------------------------------
def _state():
    try:
        with open(MARK, encoding="utf-8") as fh:
            d = json.load(fh)
            return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _save_state(d):
    try:
        with open(MARK, "w", encoding="utf-8") as fh:
            json.dump(d, fh)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# INVARIANTE (check ieftin / fix idempotent, reutilizand toolchain.py)
# ---------------------------------------------------------------------------
def _chk_launchers():
    """Linkurile catre ELF-urile din lib-ul APK-ului: mor la fiecare update."""
    tc = _tc()
    if not tc:
        return []
    nat = tc._native_dir() or ""
    if not nat:
        return []
    st = _state()
    old = st.get("nl") or ""
    if old and old != nat:
        return ["nativeLibraryDir changed (%s -> %s)" % (old[-10:], nat[-10:])]
    pr = []
    # esantion de launcher-e critice (fiecare a fost candva raportat "lipsa")
    for p in (F + "/tmp/clang", F + "/tmp/cmake", F + "/tmp/ninja", F + "/tmp/make",
              F + "/tmp/python3", F + "/tmp/git", F + "/tmp/cargo", F + "/tmp/maturin",
              F + "/tmp/cython3", F + "/tmp/flang"):
        if os.path.lexists(p) and not tc._exec_ok(p):
            pr.append("dead launcher: " + p)
    return pr


def _fix_launchers():
    tc = _tc()
    n = 0
    try:
        n += int(tc._fix_dead_binaries() or 0)
    except Exception:
        pass
    for fn in ("_ensure_launchers", "_ensure_python_launcher", "_ensure_git_launcher",
               "_ensure_cc_wrappers"):
        try:
            getattr(tc, fn)()
            n += 1
        except Exception:
            pass
    st = _state()
    st["nl"] = tc._native_dir() or ""
    _save_state(st)
    return "launchers (%d)" % max(n, 1)


def _chk_shadow():
    """Copiile trunchiate care umbresc pysitepkg.zip (vezi toolchain.heal_site_packages)."""
    tc = _tc()
    if not tc:
        return []
    try:
        a = tc.shadow_audit()
    except Exception:
        return []
    return ["shadowed: " + r["pachet"] for r in (a.get("rupte") or [])]


def _fix_shadow():
    tc = _tc()
    r = tc.heal_site_packages()
    names = sorted({str(x).split("(")[0]
                    for x in (r.get("reparate") or []) + (r.get("mutate") or [])})
    return "shadowed: " + ",".join(names)


def _chk_dirs():
    return [d for d in (F + "/tmp", F + "/libs", F + "/home", F + "/wheels")
            if not os.path.isdir(d)]


def _fix_dirs():
    for d in (F + "/tmp", F + "/libs", F + "/home", F + "/wheels"):
        try:
            os.makedirs(d, exist_ok=True)
        except Exception:
            pass
    return "dirs"


def _chk_ld():
    """Stub-urile NDK in LD_LIBRARY_PATH omoara ORICE proces copil (SIGSEGV)."""
    return ["LD_LIBRARY_PATH with %s" % p
            for p in os.environ.get("LD_LIBRARY_PATH", "").split(":") if "sysroot" in p][:2]


def _fix_ld():
    tc = _tc()
    cur = os.environ.get("LD_LIBRARY_PATH", "")
    try:
        new = tc.sanitize_ld_library_path(cur)
    except Exception:
        new = ":".join(p for p in cur.split(":") if p and "sysroot" not in p)
    os.environ["LD_LIBRARY_PATH"] = new
    return "LD_LIBRARY_PATH"


def _chk_ca():
    pr = []
    for v in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE"):
        p = os.environ.get(v)
        if p and not os.path.exists(p):
            pr.append("CA: %s -> %s" % (v, p))
    return pr


def _fix_ca():
    tc = _tc()
    tc._fix_ca_bundle()
    return "CA bundle"


def _chk_pyexe():
    """sys.executable cu hash de APK (~~x==) e citat gresit de backend-uri -> 'env: exec -m'."""
    ex = sys.executable or ""
    if "==" in ex or "~~" in ex:
        return ["sys.executable = " + ex[-24:]]
    return []


def _fix_pyexe():
    tc = _tc()
    try:
        tc._ensure_python_launcher()
    except Exception:
        pass
    try:
        tc._patch_sys_executable()
    except Exception:
        pass
    return "clean sys.executable"


def _chk_gitid():
    """Fara identitate git, update-ref/fetch = SIGSEGV (rc 139)."""
    has_git = os.path.exists(F + "/toolchain/git") or os.path.lexists(F + "/tmp/git")
    if not has_git:
        return []
    try:
        s = open(F + "/home/.gitconfig", encoding="utf-8", errors="ignore").read()
        if "[user]" in s and "email" in s:
            return []
    except Exception:
        pass
    return ["missing git identity"]


def _fix_gitid():
    tc = _tc()
    tc._ensure_git_config()
    return "git identity"


def _chk_pipconf():
    pr = []
    for c in (F + "/pip.conf", F + "/python/Lib/site-packages/pip.conf",
              F + "/pyhome/lib/python3.14/site-packages/pip.conf"):
        try:
            if "no-build-isolation" not in open(c, encoding="utf-8").read():
                pr.append(c)
        except Exception:
            pr.append(c)
    return pr


def _fix_pipconf():
    tc = _tc()
    tc._ensure_pipconf()
    return "pip.conf"


def _chk_sysconfig():
    """Cai de LAPTOP ramase in sysconfig (cross-build) -> 'headers_lipsa' la orice build."""
    pr = []
    for f in (F + "/python/Lib/_sysconfigdata__android_aarch64-linux-android.py",
              F + "/python/Lib/_sysconfigdata__linux_aarch64-linux-android.py"):
        try:
            if "/home/gab" in open(f, encoding="utf-8", errors="ignore").read():
                pr.append(os.path.basename(f))
        except Exception:
            continue
    return pr


def _fix_sysconfig():
    tc = _tc()
    tc._patch_sysconfig_device()
    try:
        tc._write_env_file()
    except Exception:
        pass
    return "sysconfig"


def _chk_full_dirs():
    """Piese care se pierd la update si pe care le folosesc toate build-urile."""
    pr = []
    if not os.path.isdir(F + "/pyhome/lib/python3.14/site-packages"):
        pr.append("pyhome/site-packages")
    for p in (F + "/toolchain/pyinc/Python.h",
              F + "/pyhome/lib/libpython3.14.so",
              F + "/libs/libc++_shared.so"):
        if not os.path.lexists(p):
            pr.append(p.replace(F + "/", ""))
    return pr


def _fix_full_dirs():
    tc = _tc()
    for fn, args in (("_prepare_dirs", ()), ("_ensure_py_include", ()),
                     ("_ensure_py_lib_link", ()), ("_ensure_libcxx", ()),
                     ("_ensure_sysroot_api_dir", (tc._device_api(),)),
                     ("_ensure_python_pc", ()), ("_ensure_real_cython", ()),
                     ("_ensure_fake_ndk", ())):
        try:
            getattr(tc, fn)(*args)
        except Exception:
            pass
    return "toolchain parts"


def _chk_adbkeys():
    return [p for p in (F + "/adbkey", F + "/tls.crt", F + "/tls.key")
            if not os.path.exists(p)]


def _fix_adbkeys():
    """Cheia/certificatul le genereaza adb_setup.py (acelasi lucru pe care il face Kotlin)."""
    import subprocess as _sp
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "adb_setup.py")
    env = dict(os.environ)
    env.setdefault("PYTHONHOME", F + "/pyhome")
    env.setdefault("HOME", F + "/home")
    try:
        _sp.run([sys.executable, p], capture_output=True, text=True, timeout=180,
                cwd=os.path.dirname(p), env=env, stdin=_sp.DEVNULL)
    except Exception:
        pass
    return "adb/tls keys"


def _chk_rust():
    """★ LACUNA raportata de agent (testat: a rupt rustc, heal a zis "nothing to repair").

    `cargo` face `exec` DIRECT pe `rustc`; daca `tmp/rustc` e un SCRIPT (nu launcher ELF) sau
    symlink-ul lui e MORT (nativeLibraryDir schimbat la update de APK) -> "could not execute
    process `rustc -vV` ... Permission denied (13)". Verificarile de launcheri de mai sus NU
    acopera rustc, deci mediul parea sanatos. Check IEFTIN: doar stat/readlink, fara subprocess.
    """
    tc = _tc()
    if not tc:
        return []
    nat = tc._native_dir() or ""
    if not nat:
        return []
    pr = []
    # fiecare cale trebuie sa fie un executabil VIU si, pentru launcher, sa duca spre libshwrap
    for p in (F + "/tmp/rustc", F + "/tmp/rustc-bin",
              F + "/toolchain/bin/rustc", F + "/toolchain/bin/rustc-bin"):
        if not os.path.lexists(p):
            pr.append("missing: " + p)
            continue
        if not tc._exec_ok(p):
            pr.append("dead link: " + p)
            continue
        # rustc trebuie sa fie launcher ELF (libshwrap), NU script shell: cargo face exec direct
        if p.endswith("/rustc") and not os.path.islink(p):
            pr.append("rustc is a script (cargo exec fails): " + p)
    return pr


def _fix_rust():
    """Reconstruieste wiring-ul rustc (launcher ELF + script + binar) prin _ensure_rust()."""
    tc = _tc()
    try:
        tc._ensure_rust()
    except Exception:
        pass
    return "rust launcher"


# (nume, faze, check, fix)
INVARIANTS = (
    ("launchers", ("startup", "build", "error", "full"), _chk_launchers, _fix_launchers),
    ("rust_launcher", ("startup", "build", "error", "full"), _chk_rust, _fix_rust),
    ("shadowed", ("startup", "build", "error", "full"), _chk_shadow, _fix_shadow),
    ("dirs", ("startup", "build", "error", "full"), _chk_dirs, _fix_dirs),
    ("ld_path", ("startup", "build", "error", "full"), _chk_ld, _fix_ld),
    ("ca_bundle", ("startup", "full"), _chk_ca, _fix_ca),
    ("pyexe", ("startup", "build", "full"), _chk_pyexe, _fix_pyexe),
    ("git_identity", ("startup", "full"), _chk_gitid, _fix_gitid),
    ("pip_conf", ("build", "error", "full"), _chk_pipconf, _fix_pipconf),
    ("sysconfig", ("build", "error", "full"), _chk_sysconfig, _fix_sysconfig),
    ("toolchain_parts", ("full",), _chk_full_dirs, _fix_full_dirs),
    ("adb_keys", ("full",), _chk_adbkeys, _fix_adbkeys),
)


def run(phase="startup", only=None):
    """Ruleaza invariantеle fazei date. Intoarce un dict COMPACT (nu se printeaza aici).

    Fiecare invariant: check() -> probleme; daca exista probleme -> fix() (idempotent).
    ★ FIX-APOI-VERIFICA: dupa fix re-rulam check()-ul si numai daca problemele au DISPARUT
    raportam "reparat". Daca fix-ul nu a rezolvat (altfel ne-am minti singuri si am scrie
    aceeasi linie la fiecare pornire), invariantul intra o data in starea persistenta ca
    "nereparabil" si de atunci tace (rămâne vizibil in `audit` si in detalii).
    Buget: check-urile sunt stat/readlink, iar fix-urile ruleaza doar cand e ceva rupt.
    """
    t0 = time.time()
    verificate, reparate, det, noi_bad = 0, [], {}, []
    st = _state()
    bad_known = st.get("bad") or {}
    for name, phases, chk, fix in INVARIANTS:
        if phase not in phases:
            continue
        if only and name not in only:
            continue
        verificate += 1
        try:
            pr = chk() or []
        except Exception:
            pr = []
        if not pr:
            continue
        try:
            what = fix()
        except Exception as ex:
            det[name] = {"error": ("%s: %s" % (type(ex).__name__, ex))[:140]}
            continue
        try:
            ramas = chk() or []
        except Exception:
            ramas = []
        if ramas:
            det[name] = {"what": str(what), "verified": "STILL broken",
                         "probleme": [str(x)[:120] for x in ramas][:2]}
            if name not in bad_known:
                bad_known[name] = int(time.time())
                noi_bad.append(name)
            continue
        det[name] = {"what": str(what), "problems": [str(x)[:120] for x in pr][:3]}
        reparate.append(name)
        bad_known.pop(name, None)
    # ★ RE-CITIM starea: fix-urile isi scriu singure marker-ul (ex. nativeLibraryDir), iar o
    # copie veche tinuta in memorie l-ar SUPRASCRIE -> la urmatoarea pornire "launcher mort"
    # reaparea, desi mediul era reparat (bug prins in testul de faza).
    st2 = _state()
    if bad_known:
        st2["bad"] = bad_known
    else:
        st2.pop("bad", None)
    if st2 != _state():
        _save_state(st2)          # scriem DOAR daca s-a schimbat ceva (fara I/O degeaba)
    if noi_bad:
        det.setdefault("_unresolved", {})["what"] = ",".join(noi_bad)
    return {"phase": phase, "checked": verificate, "repaired": reparate,
            "unresolved": noi_bad, "details": det, "ms": int((time.time() - t0) * 1000)}


def audit(phase="full"):
    """Doar RAPORT (fara reparatii) - pentru `action=audit` si pentru diagnoza manuala."""
    out = []
    for name, phases, chk, fix in INVARIANTS:
        if phase != "all" and phase not in phases:
            continue
        try:
            pr = chk() or []
        except Exception as ex:
            pr = ["check error: %s" % ex]
        if pr:
            out.append({"invariant": name, "problems": [str(x)[:160] for x in pr][:5]})
    return {"phase": phase, "invariants": len(INVARIANTS), "problems": out}


def report(d):
    """O SINGURA linie, FARA prefix (0 tokeni cand nu s-a reparat nimic: intoarce '')."""
    rep = (d or {}).get("repaired") or []
    bad = (d or {}).get("unresolved") or []
    if not rep and not bad:
        return ""
    det = (d or {}).get("details") or {}
    scurt = [(det.get(r) or {}).get("what") or r for r in rep]
    out = ""
    if rep:
        out = "%d repaired in %d ms: %s" % (len(rep), (d or {}).get("ms", 0),
                                            "; ".join(scurt)[:280])
    if bad:
        out = (out + " | " if out else "") + "UNRESOLVED: " + ",".join(bad)
    return out


def compact(d):
    """Text COMPACT pentru rezultatul unei unelte (intra in context: max ~300 caractere)."""
    fase = (d or {}).get("phase", "?")
    err = [k for k, v in ((d or {}).get("details") or {}).items()
           if isinstance(v, dict) and v.get("error")]
    body = report(d)
    if not body:
        body = "nothing to repair (%d checks, %d ms)" % (
            (d or {}).get("checked", 0), (d or {}).get("ms", 0))
    out = "heal[%s]: %s" % (fase, body)
    if err:
        out += " | errors: " + ",".join(err)
    return out


# ---------------------------------------------------------------------------
# SEMNALE DE EROARE: cand un tool intoarce un simptom de "launcher mort"/mediu
# patat, merita o incercare de heal + O re-executare (agent.py face retry-ul).
# ---------------------------------------------------------------------------
SIGNALE = (
    "permission denied", "cannot execute", "can't execute", "not executable",
    "inaccessible or not found", "exec format error",
    "no such file or directory: 'lib", "cannot link executable",
    "failed to run custom build command", "library \"libc++_shared.so\" not found",
    "modulenotfounderror", "backendunavailable",
)


# pachetele de BUILD care, daca le lipseste un SUBMODUL, sunt umbrite (nu lipsa)
_BUILD_PKGS = ("pathspec", "scikit_build_core", "scikit-build-core", "setuptools_scm",
               "setuptools-scm", "packaging", "pyproject_metadata", "pyproject_hooks",
               "vcs_versioning", "mesonpy", "mesonbuild", "meson-python", "pybind11",
               "cython", "setuptools", "wheel", "pip", "ninja")


def looks_like_launcher_break(text):
    """True doar pentru simptomele care in mod REAL indica un launcher/mediu rupt.

    ★ Semnalele sunt STRICTE intentionat: hook-ul din call_tool ruleaza heal + o
    re-executare, deci un fals pozitiv costa un heal inutil. 'No module named' simplu
    NU e destul - cerem fie un SUBMODUL (punct in nume), fie un pachet de BUILD cunoscut.
    """
    if not text:
        return False
    low = str(text)[:200000].lower()
    if "permission denied" in low and ("files/tmp" in low or "files/toolchain" in low
                                       or "lib" in low):
        return True
    if "cannot link executable" in low or "exec format error" in low:
        return True
    if "failed to run custom build command" in low and "permission denied" in low:
        return True
    # o unealta de build (sau un launcher Python) chemata si "not found"/"inaccessible"
    for tool in ("clang", "clang++", "ld.lld", "lld", "cmake", "ninja", "cargo", "rustc",
                 "maturin", "cython", "cython3", "f2py", "perl", "flang", "flang-bin", "gcc",
                 "cc", "cc-rust", "c++", "make", "meson", "patchelf", "python3", "pip",
                 "pip3", "git", "ar", "ranlib", "strip", "pkg-config", "pkgconf"):
        if ("%s: not found" % tool) in low or ("%s: inaccessible" % tool) in low \
                or ("%s: no such file" % tool) in low or ("exec: %s" % tool) in low:
            return True
    # umbrirea: ModuleNotFoundError intr-un SUBMODUL al unui pachet de build
    _i = low.find("no module named")
    if _i >= 0:
        import re as _re
        _m = _re.search(r"no module named ['\"]?([a-z0-9_.\-]+)", low[_i:_i + 200])
        if _m:
            name = _m.group(1)
            top = name.split(".")[0]
            if "." in name or top in _BUILD_PKGS:
                return True
    return False
