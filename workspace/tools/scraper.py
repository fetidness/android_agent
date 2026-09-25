#!/usr/bin/env python3
"""scraper.py - fetcher unificat, token-efficient. NICIODATA browser pentru date in HTML.

REGULA (ordinea cailor):
 1. requests.get + parse (JSON-in-HTML / regex / bs4)  <- CEL MAI RAPID, ~50x mai putini tokeni
 2. doar daca cere JS/login -> browser (am start), nu reteta UI
 3. niciodata tap/sugestie/calendar

API:
  fetch(url)              -> text (session keep-alive)
  jsonld(url)             -> lista dict-uri din <script type=application/ld+json> (schema.org)
  json_in_html(url, keys) -> extrage obiecte JSON ingropate in HTML (politi.dk style)
  titles(url)             -> titluri din <h1..h3>, <a>, <title> (dedup)
  links(url, pattern)     -> toate link-urile care contin pattern
  article(url)            -> text curatat al articolului (fara nav/footer/script)
  head(url)               -> doar status/len/ctype (pt verificare rapida, 0 parsare)
"""
import requests, re, html, json, sys
from urllib.parse import urljoin, urlparse

UA = {"User-Agent":"Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/126 Mobile Safari/537.36",
      "Accept-Language":"ro,en;q=0.8"}
_S = requests.Session(); _S.headers.update(UA)

def fetch(url, timeout=25, raw=False):
    r = _S.get(url, timeout=timeout)
    r.raise_for_status()
    return r if raw else r.text

def head(url, timeout=15):
    """verificare ultra-rapida: status, size, ctype - fara sa parsez nimic."""
    try:
        r = _S.head(url, timeout=timeout, allow_redirects=True)
        if r.status_code >= 400:
            r = _S.get(url, timeout=timeout, stream=True)
        return {"status": r.status_code, "ctype": r.headers.get("content-type",""),
                "len": r.headers.get("content-length","?")}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}

def jsonld(url):
    """beau JSON-LD schema.org (Article, NewsArticle, Product, BreadcrumbList...)."""
    h = fetch(url)
    out = []
    for m in re.finditer(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', h, re.S|re.I):
        try:
            d = json.loads(m.group(1).strip())
            out.extend(d if isinstance(d, list) else [d])
        except Exception:
            pass
    return out

def json_in_html(url, keys=("Headline","title","name"), verbose=False):
    """obiecte JSON ingropate in HTML (escapat &quot;). keys = ce campuri ma intereseaza."""
    h = fetch(url)
    hs = html.unescape(h)
    objs = []
    # cauta obiecte {....} care contin cel putin 2 dintre chei
    for m in re.finditer(r'\{[^{}]{20,4000}\}', hs):
        s = m.group(0)
        try:
            d = json.loads(s)
        except Exception:
            continue
        if not isinstance(d, dict): continue
        if sum(1 for k in d if any(kk.lower()==k.lower() for kk in keys)) >= 2:
            objs.append(d)
    if objs: return objs
    # fallback: regex per camp (politi.dk &quot;Key&quot;:&quot;val&quot;)
    res = {}
    for k in keys:
        for m in re.finditer(r'&quot;'+re.escape(k)+r'&quot;:&quot;(.*?)&quot;', h):
            res.setdefault(k, []).append(html.unescape(m.group(1)))
        for m in re.finditer(r'"'+re.escape(k)+r'"\s*:\s*"([^"]*)"', hs):
            res.setdefault(k, []).append(m.group(1))
    return res

def titles(url, tags=("h1","h2","h3")):
    """titluri din heading-uri + <title>, dedup pe forma normalizata."""
    h = fetch(url)
    from bs4 import BeautifulSoup
    s = BeautifulSoup(h, "html.parser")
    out, seen = [], set()
    for t in s.find_all(["title"]+list(tags)):
        x = " ".join(t.get_text(" ", strip=True).split())
        if len(x) < 12: continue
        k = re.sub(r"^\d{1,2}[:.]\d{2}\s*", "", x.lower())
        k = re.sub(r"[^a-z0-9]+", "", k)[:80]
        if k in seen: continue
        seen.add(k); out.append(x)
    return out

def links(url, pattern=None, absolute=True):
    """toate link-urile (optional filtrate de pattern in href sau text)."""
    h = fetch(url)
    from bs4 import BeautifulSoup
    s = BeautifulSoup(h, "html.parser")
    out = []
    for a in s.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("javascript:","#","mailto:")): continue
        if absolute: href = urljoin(url, href)
        txt = " ".join(a.get_text(" ", strip=True).split())
        if pattern and not re.search(pattern, href+" "+txt, re.I): continue
        out.append({"href": href, "text": txt[:120]})
    # dedup pe href
    seen = set(); u = []
    for x in out:
        if x["href"] in seen: continue
        seen.add(x["href"]); u.append(x)
    return u

def article(url):
    """textul curatat al articolului (elimina nav/script/style/footer/aside)."""
    h = fetch(url)
    from bs4 import BeautifulSoup
    s = BeautifulSoup(h, "html.parser")
    for t in s(["script","style","nav","footer","aside","noscript","form","iframe","svg"]):
        t.decompose()
    # alege containerul cel mai dens in text
    best, blen = None, 0
    for cand in s.find_all(["article","main","div","section"]):
        ts = cand.get_text(" ", strip=True)
        if len(ts) > blen: blen, best = len(ts), cand
    node = best or s
    txt = " ".join(node.get_text("\n", strip=True).split("\n"))
    txt = re.sub(r"\n{2,}", "\n", txt)
    return txt


def rss(url, limit=30):
    """RSS/Atom nativ prin feedparser: titluri+linkuri+date dintr-UN request.
    Ex: rss('https://www.digi24.ro/rss') -> 270 articole in ~900ms."""
    try:
        import feedparser
    except ImportError:
        raise RuntimeError("feedparser lipseste (instaleaza prin toolchain + copiaza in app site-packages)")
    f = feedparser.parse(url)
    out = []
    for e in f.entries[:limit]:
        out.append({
            "title": (e.get("title") or "").strip(),
            "link": e.get("link") or "",
            "date": (e.get("published") or e.get("updated") or "")[:25],
            "summary": (e.get("summary") or "")[:200],
        })
    return {"feed": (f.feed.get("title") or ""), "count": len(f.entries), "entries": out}

def rss_compact(url, limit=20):
    """doar titlurile, format minim pentru cost tokeni minim."""
    d = rss(url, limit)
    return [f"{e['date'][:16]} | {e['title'][:80]}" for e in d["entries"]]

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(0)
    cmd, url = sys.argv[1], (sys.argv[2] if len(sys.argv)>2 else "")
    if cmd == "head": print(json.dumps(head(url)))
    elif cmd == "titles":
        for t in titles(url): print("-", t)
    elif cmd == "jsonld": print(json.dumps(jsonld(url), indent=1, ensure_ascii=False)[:4000])
    elif cmd == "article": print(article(url)[:3000])
    elif cmd == "rss":
        for l in rss_compact(url, int(sys.argv[3]) if len(sys.argv)>3 else 20): print("-", l)
    elif cmd == "links":
        for l in links(url, sys.argv[3] if len(sys.argv)>3 else None)[:40]:
            print("-", l["text"][:60], "->", l["href"])
    else: print("comenzi: head|titles|jsonld|article|links|rss <url> [n]")


def articles(url, container=None, sel="h2.article-title", base=None):
    """articole reale: titlu + link absolut + id, din h2.article-title (nu toate heading-urile).
    container = selector optional pentru zona de lista; sel = selector heading articol."""
    from bs4 import BeautifulSoup
    from urllib.parse import urljoin
    h = fetch(url)
    s = BeautifulSoup(h, "html.parser")
    root = s.select_one(container) if container else s
    if root is None: root = s
    if base is None:
        m = re.match(r"https?://[^/]+", url); base = (m.group(0) if m else "")
    out, seen = [], set()
    for node in root.select(sel):
        a = node.find("a", href=True)
        href = a["href"] if a else None
        ttl = " ".join((node.get("title") or node.get_text(" ", strip=True)).split())
        if not ttl or len(ttl) < 12: continue
        link = urljoin(base + "/", href) if href else None
        aid = None
        if link:
            m = re.search(r"-(\d{5,})/?$", link)
            if m: aid = m.group(1)
        if ttl in seen: continue
        seen.add(ttl)
        out.append({"title": ttl, "link": link, "id": aid})
    return out
