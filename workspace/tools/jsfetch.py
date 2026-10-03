#!/usr/bin/env python3
"""jsfetch.py - scraping pe site-uri cu JAVASCRIPT (SPA/React/Vue), pe device.

DE CE: scraper.py (lxml/trafilatura) NU vede continutul randat de JS. Pe site-uri
client-side (react.dev, vuejs.org, reddit, x.com) da 0 sau putin text.
Solutia dovedita: deschide pagina in CHROME-ul de pe telefon (V8 real), asteapta
randarea, apoi citeste arborele de accesibilitate (uiautomator dump).

DOVEDIT pe device (3 oct 2026):
  react.dev    scraper=~0 relevant  | chrome=143 texte
  vuejs.org    scraper=455 chars    | chrome= 64 texte
  svelte.dev   scraper=506 chars    | chrome= 64 texte
  angular.dev  scraper=1122 chars   | chrome= 83 texte
Cost: ~12-23s per pagina (Chrome porneste + randeaza). NU folosi daca scraper.py merge.

UTILIZARE:
  python jsfetch.py <url> [scrolls]      -> text din pagina randata
  import jsfetch; jsfetch.fetch(url)
"""
import re, sys, time, subprocess, json

def _sh(cmd, timeout=60):
    """Ruleaza o comanda prin adbsh (uid 2000). Folosim adb_client daca e disponibil."""
    try:
        sys.path.insert(0, "/data/data/net.sys32.agent/files/python")
        import adb_client
        return str(adb_client.shared().shell(cmd))
    except Exception:
        r = subprocess.run(["sh","-c",cmd],capture_output=True,text=True,timeout=timeout)
        return (r.stdout or "")+(r.stderr or "")

def fetch(url, scrolls=0, wait=7, min_texts=15, max_wait=25, stop_on_consent=True):
    """Deschide url in Chrome, asteapta randarea JS, intoarce lista de texte vizibile.

    scrolls  = cate scroll-uri (pt continut lung / infinite scroll)
    wait     = secunde de asteptare initiala
    min_texts= opreste asteptarea cand are atatea texte (incarcare adaptiva)
    """
    _sh("am force-stop com.android.chrome"); time.sleep(1)
    _sh("am start -a android.intent.action.VIEW -d '%s'" % url)
    t0 = time.time()
    textos = []
    while time.time() - t0 < max_wait:
        time.sleep(wait if not textos else 2)
        _sh("uiautomator dump /data/local/tmp/_js.xml")
        xml = _sh("cat /data/local/tmp/_js.xml")
        textos = [t for t in re.findall(r'text="([^"]{3,400})"', xml)
                  if t.strip() and not t.startswith(("http","data:"))]
        # ★ cookie banner: il detectam si incercam sa-l inchidem
        if stop_on_consent and any(k in " ".join(textos).lower()
                                   for k in ("cookie","consent","gdpr")):
            _click_if(xml, ("Accept all","Accept","Agree","Accepta","Acord"))
            time.sleep(2)
        if len(textos) >= min_texts:
            break
    for _ in range(scrolls):
        _sh("input swipe 540 1500 540 600 300"); time.sleep(1.5)
    if scrolls:
        _sh("uiautomator dump /data/local/tmp/_js.xml")
        xml = _sh("cat /data/local/tmp/_js.xml")
        textos = [t for t in re.findall(r'text="([^"]{3,400})"', xml)
                  if t.strip() and not t.startswith(("http","data:"))]
    # curata: scoate duplicate si zgomot de browser
    out, seen = [], set()
    for t in textos:
        k = t.strip().lower()
        if k in seen or len(k) < 3: continue
        seen.add(k); out.append(t.strip())
    return out

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
    tx = fetch(url, scrolls=sc)
    print("=== %d texte din %s ===" % (len(tx), url))
    for t in tx: print("-", t)
