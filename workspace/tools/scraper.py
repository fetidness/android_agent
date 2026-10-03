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

UA = {"User-Agent":"Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/126 Mobile Safari/537.36",
      "Accept-Language":"ro,en;q=0.8"}
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
    """Selectori CSS prin parsel (peste lxml)."""
    from parsel import Selector
    s = Selector(text=fetch(url))
    if attr: return s.css(sel).xpath("@"+attr).getall()
    return s.css(sel).xpath("string(.)").getall()

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

def article(url):
    """Extractie articol AUTOMATA cu trafilatura (text+metadate) - elimina nav/ads/footer."""
    import trafilatura
    h = fetch(url)
    txt = trafilatura.extract(h, include_comments=False, include_tables=True, favor_precision=True)
    meta = trafilatura.extract_metadata(h)
    return {"text": txt or "", "meta": _clean_meta(meta.as_dict() if meta else {}),
            "chars": len(txt or "")}

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
    else: print("cmd: head|rss|article|xpath|css|links|meta|table")
