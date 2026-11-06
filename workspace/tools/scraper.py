#!/usr/bin/env python3
"""scraper2.py - scraping la capacitate maxima. Ruleaza pe py314 (Python compilat de la 0).

Stack: lxml (XPath+CSS rapid, C) + parsel (selectori) + trafilatura (extractie articol auto)
       + feedparser (RSS) + requests (HTTP) + justext (boilerplate removal).

Utilizare:
  python3.14 scraper2.py <cmd> <url> [args]
  cmd: fetch | head | xpath | css | rss | article | links | meta | table | crawl
sau import ca modul.
"""
import sys, json, re, html
import requests

UA = {"User-Agent":"Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36",
      "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
      "Accept-Language":"en-US,en;q=0.9,ro;q=0.8",
      "Accept-Encoding":"gzip, deflate, br",
      "Upgrade-Insecure-Requests":"1",
      "Sec-Fetch-Dest":"document","Sec-Fetch-Mode":"navigate","Sec-Fetch-Site":"none"}
_S = requests.Session(); _S.headers.update(UA)

def fetch(url, timeout=25):
    r = _S.get(url, timeout=timeout); r.raise_for_status(); return r.text

def head(url, timeout=15):
    r = _S.head(url, timeout=timeout, allow_redirects=True)
    return {"status": r.status_code, "ctype": r.headers.get("content-type",""),
            "len": r.headers.get("content-length","?")}

def doc(url):
    """Parsare lxml rapida."""
    import lxml.html
    return lxml.html.fromstring(fetch(url))

def xpath(url, expr):
    """XPath direct pe lxml (CEL MAI RAPID si puternic)."""
    d = doc(url)
    return [x if isinstance(x,str) else lxml_tostr(x) for x in d.xpath(expr)]

def lxml_tostr(el):
    try:
        import lxml.html
        return lxml.html.tostring(el, encoding="unicode")
    except Exception:
        return str(el)

def css(url, sel, attr=None):
    """Selectori CSS prin parsel (peste lxml).

    FIX 24 oct: daca selectorul contine deja un pseudo-element (::text, ::attr(x)),
    getall() direct pe el - vechiul cod aplica xpath("string(.)") peste rezultat
    si returna mereu lista goala pentru 'h2::text'.
    """
    from parsel import Selector
    s = Selector(text=fetch(url))
    if attr: return s.css(sel).xpath("@" + attr).getall()
    if "::" in sel: return [x.strip() for x in s.css(sel).getall() if x.strip()]
    out = s.css(sel).xpath("string(.)").getall()
    return [x.replace("\u200b", "").strip() for x in out]

def rss(url, limit=30):
    import feedparser
    f = feedparser.parse(fetch(url))
    out = [{"title":(e.get("title") or "").strip(), "link":e.get("link") or "",
            "date":(e.get("published") or e.get("updated") or "")[:25],
            "summary":(e.get("summary") or "")[:200]} for e in f.entries[:limit]]
    return {"feed": f.feed.get("title") or "", "count": len(f.entries), "entries": out}

def _clean_meta(d):
    """Curata metadatele trafilatura: scoate elementele lxml (body/commentsbody) si
    converteste valorile ne-serializabile in string.
    BUG reparat 3 oct: in trafilatura 2.x, as_dict() intoarce si elemente XML
    (_Element) la cheile 'body'/'commentsbody', iar json.dumps cadea cu TypeError."""
    out = {}
    for k, v in (d or {}).items():
        if v is None or isinstance(v, (str, int, float, bool)):
            out[k] = v
        elif isinstance(v, (list, tuple)):
            out[k] = [x if isinstance(x, (str, int, float, bool)) else str(x) for x in v]
        else:
            out[k] = str(v)          # include elementele lxml -> reprezentare text
    return out

def article(url, _html=None):
    """Extractie articol AUTOMATA cu trafilatura (text+metadate) - elimina nav/ads/footer.

    FALLBACK (6 nov): unele pagini (homepage-uri, site-uri cu CSS ciudat) dau 0
    caractere la favor_precision=True desi au 20 KB de text real. In acel caz se
    reincearca fara favor_precision, apoi cu justext (boilerplate removal) si in
    final cu textul brut al <body>. Asa nu mai raportam 'gol' pe o pagina plina.
    """
    import trafilatura
    h = _html if _html is not None else fetch(url)
    txt = trafilatura.extract(h, include_comments=False, include_tables=True, favor_precision=True)
    meta = trafilatura.extract_metadata(h)
    how = "trafilatura"
    if not txt:
        try:
            txt = trafilatura.extract(h, include_comments=False, include_tables=True,
                                      favor_recall=True)
            if txt: how = "trafilatura-recall"
        except Exception:
            pass
    if not txt:
        try:
            import justext
            body = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", h)
            paras = justext.justext(body, justext.get_stoplist("English"))
            good = [pp.text for pp in paras if not pp.is_boilerplate]
            cand = "\n".join(good).strip()
            if len(cand) > 200:
                txt = cand; how = "justext"
        except Exception:
            pass
    if not txt:
        try:
            import lxml.html as _lh
            d = _lh.fromstring(h)
            for bad in d.xpath("//script|//style|//nav|//footer|//header"):
                bad.getparent().remove(bad)
            cand = " ".join(" ".join(d.xpath("//body//text()")).split())
            if len(cand) > 200:
                txt = cand; how = "body-text"
        except Exception:
            pass
    out = {"text": txt or "", "meta": _clean_meta(meta.as_dict() if meta else {}),
           "chars": len(txt or ""), "how": how}
    out["_html"] = h          # pentru supreme: refolosim HTML-ul deja descarcat
    return out

def links(url, pattern=None):
    d = doc(url)
    out=[]; seen=set()
    for a in d.xpath("//a[@href]"):
        href = a.get("href")
        if not href or href.startswith(("javascript:","#","mailto:")): continue
        full = requests.compat.urljoin(url, href)
        if pattern and not re.search(pattern, full+" "+" ".join(a.itertext()), re.I): continue
        if full in seen: continue
        seen.add(full)
        out.append({"href":full, "text":" ".join(" ".join(a.itertext()).split())[:120]})
    return out

def meta(url):
    """Toate meta-urile (og:, twitter:, description, title)."""
    d = doc(url)
    m = {}
    for x in d.xpath("//meta[@name or @property]"):
        k = x.get("property") or x.get("name"); v = x.get("content")
        if k and v: m.setdefault(k, v)
    for t in d.xpath("//title/text()"): m["title"] = t.strip()
    return m

def table(url, idx=0):
    """Extrage un tabel ca lista de randuri."""
    d = doc(url)
    tabs = d.xpath("//table")
    if idx >= len(tabs): return {"error": "table %d inexistent (%d total)" % (idx, len(tabs))}
    rows=[]
    for tr in tabs[idx].xpath(".//tr"):
        cells = [" ".join(" ".join(td.itertext()).split()) for td in tr.xpath("./td|./th")]
        if cells: rows.append(cells)
    return {"tables": len(tabs), "rows": rows}

# ================== INTEGRARE CU MOTORUL JS (jsengine.py) ==================
# scraper.py = reteaua + HTML. jsengine.py = JavaScript. jsfetch.py = randare DOM.
# Functiile de mai jos leaga cele trei, cu detectare automata.

_DATA_PATTERNS = [
    ("__NEXT_DATA__", r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>'),
    ("__NUXT__",      r'window\.__NUXT__\s*=\s*(.*?);?</script>'),
    ("__INITIAL_STATE__", r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\});'),
    ("__DATA__",      r'window\.__DATA__\s*=\s*(\{.*?\});'),
    ("__PRELOADED_STATE__", r'window\.__PRELOADED_STATE__\s*=\s*(\{.*?\});'),
    ("APOLLO_STATE",  r'window\.__APOLLO_STATE__\s*=\s*(\{.*?\});'),
    ("ld+json",       r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>'),
]

def _has_js():
    try:
        import jsengine; return True
    except Exception:
        return False

def sniff(html):
    """Detecteaza ce fel de pagina e si ce date are in JS. NU descarca nimic.

    Intoarce: {kind, scripts, patterns, js_hint}
    kind: 'static'  = HTML normal (merge scraper)
          'spa'     = aproape gol, are nevoie de JS/randare (jsengine/jsfetch)
          'hybrid'  = HTML + date in <script> (scraper + jsengine)
    """
    import re
    h = html or ""
    scripts = re.findall(r"<script[^>]*>", h)
    pats = []
    for name, rx in _DATA_PATTERNS:
        if re.search(rx, h, re.S):
            pats.append(name)
    # text util fara taguri
    text = re.sub(r"<script.*?</script>", " ", h, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = " ".join(text.split())
    # ---- indicatori de SPA (aplicatie client-side) ----
    spa_signals = []
    if re.search(r'<script[^>]*type="module"', h, re.I): spa_signals.append("module")
    if re.search(r'<div[^>]*id=["\']?(app|root|__next|root-app)["\']?', h, re.I): spa_signals.append("div#app")
    if re.search(r'<script[^>]*src="[^"]*/assets/[^"]*\.js', h, re.I): spa_signals.append("assets/js")
    if re.search(r'<script[^>]*src="[^"]*/(_next|static/js|app)\.?[^"]*\.js', h, re.I): spa_signals.append("bundler")
    # container gol = SPA (body are doar div gol)
    body = re.search(r"<body[^>]*>(.*?)</body>", h, re.S | re.I)
    body_text = re.sub(r"<[^>]+>", " ", body.group(1)) if body else ""
    if len(body and body.group(1) or "") < 400 and len(" ".join(body_text.split())) < 60:
        spa_signals.append("body-gol")

    if pats:
        kind = "hybrid"
    elif len(text) < 600 and (len(scripts) > 3 or len(spa_signals) >= 2):
        kind = "spa"          # gol + (multe scripturi SAU semnale clare de SPA)
    else:
        kind = "static"
    return {"kind": kind, "scripts": len(scripts), "patterns": pats,
            "text_chars": len(text), "spa_signals": spa_signals}

def extract_js_data(html, pattern=None):
    """Extrage blocul de date JSON dintr-un <script> (fara sa ruleze JS).

    pattern = nume din _DATA_PATTERNS (ex. '__NEXT_DATA__'); None = auto (primul gasit).
    Intoarce (nume, text_json) sau (None, None).
    """
    import re
    for name, rx in _DATA_PATTERNS:
        if pattern and name != pattern: continue
        m = re.search(rx, html or "", re.S)
        if m:
            raw = m.group(1).strip()
            if raw.startswith(("window.", "var ")):      # unele au prefix
                i = raw.find("=")
                if i > 0: raw = raw[i+1:].strip().rstrip(";")
            return name, raw
    return None, None

def js_query(url_or_html, expr, pattern=None, is_html=False):
    """SUPREM: ia pagina (sau HTML dat), extrage datele JS si le interogheaza cu JS.

    url_or_html = URL (se descarca) SAU HTML direct (is_html=True)
    expr        = expresie JavaScript; variabila DATE = blocul JSON gasit
                  (ex. 'DATE.props.pageProps.title' sau 'JSON.stringify(DATE.items)')
    pattern     = fortat un anumit pattern ('__NEXT_DATA__', 'ld+json', ...)
    """
    import json as _json
    html = url_or_html if is_html else fetch(url_or_html)
    name, raw = extract_js_data(html, pattern)
    if not _has_js():
        return {"ok": False, "error": "jsengine.py is missing (pip install quickjs)"}
    import jsengine
    ctx = jsengine.context()
    # pagina reala: punem titlul si URL-ul in stub-ul document (expr poate sa le ceara)
    try:
        import re as _re, html as _htmlmod
        _t = _re.search(r"<title[^>]*>(.*?)</title>", html or "", _re.S | _re.I)
        if _t:
            ctx.eval("document.title = " + _json.dumps(_htmlmod.unescape(_t.group(1)).strip()) + ";")
        if not is_html:
            ctx.eval("location.href = " + _json.dumps(url_or_html) + ";")
    except Exception:
        pass
    if not raw:
        # fara blob de date: rulam totusi expresia pe pagina (document.title etc.)
        try:
            rez = ctx.eval(expr)
        except Exception as e:
            return {"ok": False, "error": "JS: " + str(e)[:150],
                    "patterns_incercate": [p for p, _ in _DATA_PATTERNS]}
        if isinstance(rez, (str, int, float, bool, list, dict)) or rez is None:
            return {"ok": True, "pattern": None, "result": rez,
                    "js_bytes": 0, "note": "fara date JS in pagina; expresia a rulat pe stub"}
        return {"ok": False, "error": "nicio structura de date JS gasita",
                "patterns_incercate": [p for p, _ in _DATA_PATTERNS]}
    # ld+json poate fi un array sau obiect; il incarcam tolerant
    try:
        ctx.eval("var DATE = " + raw + ";")
    except Exception:
        ctx.eval("var DATE = " + _json.dumps(raw) + ";")   # fallback: string brut
    try:
        rez = ctx.eval(expr)
    except Exception as e:
        return {"ok": False, "error": "JS: " + str(e)[:150], "pattern": name}
    return {"ok": True, "pattern": name, "result": rez,
            "js_bytes": len(raw)}

def deep(url_or_html, keys=None, pattern=None, is_html=False, limit=200):
    """Cauta recursiv chei (implicit: title/headline/name) in datele JS ale paginii.

    keys = lista de nume de chei (regex). Intoarce lista de valori gasite.
    """
    import json as _json
    if isinstance(keys, str):
        keys = [k.strip() for k in keys.split(",") if k.strip()]   # "a,b" -> ["a","b"]
    keys = keys or ["title", "headline", "name"]
    # cheile sunt comparate direct (mai sigur decat regex construit din string)
    keys_js = ",".join(repr(k) for k in keys)
    expr = ("(function(){var out=[];var KEYS=[%s];"
            "function w(o){if(!o||typeof o!=='object'||out.length>%d)return;"
            "if(Array.isArray(o)){for(var i=0;i<o.length;i++)w(o[i]);return;}"
            "for(var k in o){var v=o[k];"
            "if(KEYS.indexOf(k.toLowerCase())>=0){if(typeof v==='string'&&v.length>3)out.push(v);}"
            "else w(v);}}w(DATE);return JSON.stringify(out);})()") % (keys_js, limit)
    r = js_query(url_or_html, expr, pattern=pattern, is_html=is_html)
    if not r.get("ok"):
        err = str(r.get("error", ""))
        if "DATE" in err and "not defined" in err:
            return {"ok": False, "pattern": None, "values": [],
                    "error": "pagina nu are date JS (niciun bloc __NEXT_DATA__/__NUXT__/ld+json)",
                    "hint": "incearca scraper.article() sau scraper.supreme()"}
        return r
    import json as _json2
    try: r["values"] = _json2.loads(r["result"] or "[]")
    except Exception: r["values"] = []
    return r

def supreme(url, force=None, scrolls=1):
    """★ SCRAPING SUPREM: alege automat cea mai buna metoda pentru un URL.

    force = 'scraper' | 'hybrid' | 'chrome'  (altfel: auto)
    Intoarce dict cu {method, data, timp_ms, ...}

    Ordinea (auto):
      1) fetch + sniff  -> 'static'  => scraper (article/links)
      2) 'hybrid'       => scraper + jsengine (datele din <script>)
      3) 'spa'          => jsfetch (Chrome, randare completa)
    """
    import time as _t
    t0 = _t.time()
    out = {"url": url, "method": None, "data": None}
    try:
        html = fetch(url)
    except Exception as e:
        out["error"] = "fetch: " + str(e)[:120]; return out
    info = sniff(html)
    out["sniff"] = info
    met = force or "auto"
    out["method"] = met
    # ★ ORDINEA CORECTA (fix 6 nov): textul REAL se extrage INTOTDEAUNA primul.
    # Blobul de date JS (__NEXT_DATA__) e doar un fallback, pentru ca pe un articol
    # BBC el contine etichete de meniu, nu continutul. JS/RANDARE se folosesc
    # DOAR cand textul din HTML e sarac.
    if met in ("auto", "scraper", "hybrid"):
        try:
            a = article(url, _html=html)
        except Exception as e:
            a = {}
            out["article_error"] = str(e)[:150]
        out["data"] = a.get("text") or ""
        out["chars"] = a.get("chars") or 0
        out["how"] = a.get("how")
        out["ok"] = bool(out["chars"])
        if met == "auto":
            out["method"] = "scraper"
        # JS doar daca textul e sarac si pagina are un bloc de date JS
        if not out["ok"] or out["chars"] < 400:
            if _has_js():
                try:
                    name2, raw2 = extract_js_data(html)
                    if name2 and raw2:
                        q2 = js_query(html,
                            "(function(){var o=[];function w(x){"
                            "if(!x||typeof x!=='object'||o.length>300)return;"
                            "if(Array.isArray(x)){for(var i=0;i<x.length;i++)w(x[i]);return}"
                            "for(var k in x){var v=x[k];"
                            "if(/^(title|headline|description|summary)$/i.test(k)&&typeof v==='string'&&v.length>20)o.push(v);"
                            "else w(v)}}w(DATE);return JSON.stringify(o)})()", is_html=True)
                        js_txt = q2.get("result") or ""
                        out["js_chars"] = len(js_txt)
                        if len(js_txt) > out["chars"] + 200:
                            out["method"] = "hybrid"; out["data"] = js_txt
                            out["pattern"] = q2.get("pattern"); out["ok"] = True
                            out["chars"] = len(js_txt)
                except Exception:
                    pass
            # randare completa doar daca nici JS nu a ajutat
            if not out["ok"] and met == "auto" and info.get("kind") == "spa":
                met = "chrome"; out["method"] = "chrome"
        if not out["ok"] and met != "chrome":
            out["error"] = "extractia a dat 0 caractere (pagina goala, blocata de site sau doar JS)"
    if met == "chrome":
        try:
            import jsfetch
            tx = jsfetch.fetch(url, scrolls=scrolls, min_texts=25)
            out["data"] = tx; out["n_texts"] = len(tx); out["ok"] = len(tx) > 3
        except Exception as e:
            out["ok"] = False; out["error"] = "jsfetch: " + str(e)[:150]
    out["timp_ms"] = round((_t.time()-t0)*1000)
    return out

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(0)
    cmd, url = sys.argv[1], sys.argv[2]
    if cmd == "head": print(json.dumps(head(url)))
    elif cmd == "rss": print(json.dumps(rss(url, int(sys.argv[3]) if len(sys.argv)>3 else 10), ensure_ascii=False)[:4000])
    elif cmd == "article": 
        a=article(url); print(json.dumps(a["meta"], ensure_ascii=False, default=str)[:600]); print("---"); print(a["text"][:2000])
    elif cmd == "xpath": print(json.dumps(xpath(url, sys.argv[3])[:30], ensure_ascii=False))
    elif cmd == "css": print(json.dumps(css(url, sys.argv[3], sys.argv[4] if len(sys.argv)>4 else None)[:30], ensure_ascii=False))
    elif cmd == "links":
        for l in links(url, sys.argv[3] if len(sys.argv)>3 else None)[:40]: print("-", l["text"][:60], "->", l["href"])
    elif cmd == "meta": print(json.dumps(meta(url), ensure_ascii=False, indent=1)[:3000])
    elif cmd == "table": print(json.dumps(table(url), ensure_ascii=False)[:3000])
    elif cmd == "sniff": print(json.dumps(sniff(fetch(url)), ensure_ascii=False, indent=1))
    elif cmd == "jsdata":
        pat=sys.argv[3] if len(sys.argv)>3 else None
        print(json.dumps(extract_js_data(fetch(url), pat), ensure_ascii=False)[:3000])
    elif cmd == "jsquery":
        print(json.dumps(js_query(url, sys.argv[3]), ensure_ascii=False, indent=1)[:4000])
    elif cmd == "deep":
        keys=sys.argv[3].split(",") if len(sys.argv)>3 else None
        r=deep(url, keys); print(json.dumps(r.get("values", r), ensure_ascii=False, indent=1)[:4000])
    elif cmd == "supreme":
        r=supreme(url)
        print("metoda: %s | timp: %s ms"%(r.get("method"), r.get("timp_ms")))
        print("sniff:",r.get("sniff"))
        d=r.get("data")
        print("date:",(json.dumps(d,ensure_ascii=False)[:2500] if not isinstance(d,str) else d[:2500]))
    else: print("cmd: head|rss|article|xpath|css|links|meta|table|sniff|jsdata|jsquery|deep|supreme")
