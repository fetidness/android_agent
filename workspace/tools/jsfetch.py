#!/usr/bin/env python3
"""jsfetch.py - scraping pe site-uri cu JAVASCRIPT (SPA/React/Vue), pe device.

DE CE: scraper.py (lxml/trafilatura) NU vede continutul randat de JS. Pe site-uri
client-side (react.dev, vuejs.org, danielpincu.com) da 0 sau putin text.
Solutia dovedita: deschide pagina in CHROME (V8 real), asteapta randarea, apoi
citeste ce e pe ecran.

DOUA metode de citire (fallback automat):
  1. `uiautomator dump`      - rapid, dar ESUEAZA pe pagini ANIMATE
                               ("ERROR: could not get idle state" - ex. canvas Matrix)
  2. accessibility (bridge)  - NU depinde de starea de idle, merge pe orice pagina,
                               dar cere serviciul de accessibility activ

DOVEDIT pe device (3 oct 2026):
  vuejs.org     -> 71 texte    | react.dev -> 143 texte
  ycombinator   -> 268 texte   | danielpincu.com -> ~80 noduri (prin accessibility;
                                   uiautomator a esuat: animatie Matrix continua)
Cost: ~12-37s per pagina. NU folosi daca scraper.py merge.

UTILIZARE:
  python jsfetch.py <url> [scrolls]      -> textele din pagina randata
  import jsfetch; jsfetch.fetch(url)
"""
import re, sys, time, subprocess, json

def _sh(cmd, timeout=60):
    """Ruleaza o comanda shell (uid 2000) prin adb_client daca e disponibil."""
    try:
        sys.path.insert(0, "/data/data/net.sys32.agent/files/python")
        import adb_client
        return str(adb_client.shared().shell(cmd))
    except Exception:
        r = subprocess.run(["sh","-c",cmd],capture_output=True,text=True,timeout=timeout)
        return (r.stdout or "")+(r.stderr or "")

def _a11y_read(max_nodes=200):
    """★ FALLBACK: citeste ecranul prin ACCESSIBILITY (nu uiautomator).

    Nu depinde de 'idle state', deci merge pe pagini cu animatii continue.
    Foloseste bridge-ul Kotlin al aplicatiei (portul din files/bridge.port).
    """
    try:
        import json as _j, socket
        port = None
        for p in ("/data/data/net.sys32.agent/files/bridge.port",
                  "/data/data/net.sys32.agent/files/home/bridge.port"):
            try:
                port = int(open(p).read().strip()); break
            except Exception:
                continue
        if not port: return []
        s = socket.create_connection(("127.0.0.1", port), timeout=20)
        req = _j.dumps({"tool":"ui","action":"read","max":max_nodes})+"\n"
        s.sendall(req.encode())
        data = b""
        while not data.endswith(b"\n"):
            chunk = s.recv(65536)
            if not chunk: break
            data += chunk
        s.close()
        obj = _j.loads(data.decode("utf-8","replace"))
        # textul vine ca lista "[1] TextView \"x\" @[..]" -> extrag doar textele
        out = []
        for line in (obj.get("text") or "").split("\n"):
            m = re.findall(r'"([^"]{3,400})"', line)
            for x in m:
                if x.strip() and not x.startswith(("http","data:")): out.append(x.strip())
        return out
    except Exception:
        return []

def _uia_dump():
    """Citire prin uiautomator. Intoarce (xml, ok) - ok=False la 'could not get idle state'."""
    r = _sh("uiautomator dump /data/local/tmp/_js.xml 2>&1")
    if "could not get idle state" in r.lower() or "ERROR" in r:
        return "", False
    xml = _sh("cat /data/local/tmp/_js.xml")
    if len(xml) < 100: return "", False
    return xml, True

def _texts_from_xml(xml):
    return [t for t in re.findall(r'text="([^"]{3,400})"', xml)
            if t.strip() and not t.startswith(("http","data:"))]

def current_url():
    """URL-ul tab-ului activ din Chrome (ca sa nu citim un tab vechi)."""
    r = _sh("dumpsys activity activities | grep -o 'dat=[^ ]*' | head -1")
    m = re.search(r"dat=(\S+)", r or "")
    return m.group(1) if m else ""

def fetch(url, scrolls=0, wait=7, min_texts=15, max_wait=30, stop_on_consent=True,
          verify_url=True):
    """Deschide url in Chrome, asteapta randarea JS, intoarce lista de texte vizibile.

    scrolls     = cate scroll-uri (pt continut lung / infinite scroll)
    wait        = secunde de asteptare initiala
    min_texts   = opreste asteptarea cand are atatea texte (incarcare adaptiva)
    verify_url  = verifica ca tab-ul activ e chiar URL-ul cerut (evita taburi vechi)
    """
    _sh("am force-stop com.android.chrome"); time.sleep(1)
    _sh("am start -a android.intent.action.VIEW -d '%s'" % url)
    t0 = time.time()
    textos, metoda = [], None
    while time.time() - t0 < max_wait:
        time.sleep(wait if not textos else 2)
        # ★ verificare URL (evita sa citim un tab vechi din Chrome)
        if verify_url:
            cu = current_url()
            if cu and url.split("//")[-1].split("/")[0] not in cu:
                continue
        xml, ok = _uia_dump()
        if ok:
            textos = _texts_from_xml(xml); metoda = "uiautomator"
        else:
            # ★ FALLBACK: uiautomator nu poate (pagina animata) -> accessibility
            textos = _a11y_read(); metoda = "accessibility"
        if not textos: continue
        if stop_on_consent and any(k in " ".join(textos).lower()
                                   for k in ("cookie","consent","gdpr")):
            if ok: _click_if(xml, ("Accept all","Accept","Agree","Accepta","Acord"))
            time.sleep(2)
        if len(textos) >= min_texts:
            break
    for _ in range(scrolls):
        _sh("input swipe 540 1500 540 600 300"); time.sleep(1.5)
    if scrolls:
        xml, ok = _uia_dump()
        textos = _texts_from_xml(xml) if ok else _a11y_read()
        metoda = "uiautomator" if ok else "accessibility"
    # curata: dedup + scoate zgomot de browser
    junk = ("webview","data:","http","about:blank","chrome","menu","tab")
    out, seen = [], set()
    for t in textos:
        k = t.strip().lower()
        if k in seen or len(k) < 3: continue
        if any(k.startswith(j) for j in junk): continue
        seen.add(k); out.append(t.strip())
    return out

def fetch_debug(url, **kw):
    """Ca fetch() dar intoarce si metoda folosita + URL-ul activ."""
    return {"texts": fetch(url, **kw), "url_activ": current_url()}

def _click_if(xml, labels):
    """Apasa primul buton clickabil care contine unul din labels."""
    for lab in labels:
        m = re.search(r'text="[^"]*%s[^"]*"[^>]*?clickable="true"[^>]*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"' % re.escape(lab), xml, re.I)
        if m:
            x = (int(m.group(1))+int(m.group(3)))//2
            y = (int(m.group(2))+int(m.group(4)))//2
            _sh("input tap %d %d" % (x,y)); return True
    return False

def fetch_text(url, **kw):
    """Ca fetch() dar intoarce un singur string."""
    return "\n".join(fetch(url, **kw))

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(0)
    url = sys.argv[1]
    sc = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    r = fetch_debug(url, scrolls=sc)
    tx = r["texts"]
    print("=== %d texte din %s ===" % (len(tx), url))
    print("(url activ: %s)" % r["url_activ"])
    for t in tx: print("-", t)
