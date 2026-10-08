"""websearch.py - motor de cautare web robust (Android/toybox).

STARE DOVEDITA (testat live, 2026-10-03):
  bing()       - CEL MAI BUN. NECESITA setlang=en (altfel raspunde localizat/aleator).
                 mkt= da 0 rezultate -> NU folosi mkt. Se rate-limiteaza la cereri
                 rapide repetate; retry cu pauza rezolva.
  wikipedia()  - API mediawiki, NICIODATA blocat. Cel mai sigur. Enciclopedic.
  marginalia() - motor independent, fara blocare. Rezerva.
  ddg()        - doar ~2-3 cereri, apoi CAPTCHA HTTP 202. Ultimul.
  DEAD: Ecosia(403), Brave(429), Mojeek(Captcha), Qwant API(403), Yahoo(500),
        Startpage/Bing/Brave prin selectori nepotriviti.
ORDINE dispecer: bing -> wikipedia -> marginalia.
"""
import requests, time, re
from bs4 import BeautifulSoup

UA = {"User-Agent": "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/126 Mobile Safari/537.36",
      "Accept-Language": "en-US,en;q=0.9"}

def _try(fn, *a, tries=3, pause=2.0):
    """Cheama fn cu retry/backoff (pt rate-limit tranzitoriu)."""
    last = None
    for i in range(tries):
        try:
            r = fn(*a)
            if r: return r
        except Exception as e:
            last = e
        if i < tries - 1: time.sleep(pause * (i + 1))
    return [] if last is None else {"error": str(last)}

def bing(q, n=10):
    def one():
        r = requests.get("https://www.bing.com/search",
                         params={"q": q, "setlang": "en", "cc": "US"}, headers=UA, timeout=20)
        s = BeautifulSoup(r.text, "lxml")
        out = []
        for li in s.select("li.b_algo"):
            h = li.find("h2"); a = h.find("a") if h else None
            if not a: continue
            cite = li.find("cite")
            out.append({"title": h.get_text(" ", strip=True), "url": a.get("href", ""),
                        "site": cite.get_text("", strip=True).replace(" ", "") if cite else ""})
            if len(out) >= n: break
        return out
    return _try(one)

def wikipedia(q, n=10, lang="en"):
    def one():
        r = requests.get(f"https://{lang}.wikipedia.org/w/api.php",
                         params={"action": "query", "list": "search", "srsearch": q,
                                 "srlimit": str(n), "format": "json"}, headers=UA, timeout=20)
        return [{"title": it["title"], "snippet": re.sub(r"<[^>]+>", "", it["snippet"]),
                 "url": f"https://{lang}.wikipedia.org/wiki/" + it["title"].replace(" ", "_")}
                for it in r.json()["query"]["search"]]
    return _try(one)

def marginalia(q, n=15):
    def one():
        r = requests.get("https://search.marginalia.nu/search", params={"query": q},
                         headers=UA, timeout=25)
        s = BeautifulSoup(r.text, "lxml")
        out, seen = [], set()
        for a in s.select("a"):
            href = a.get("href", ""); t = a.get_text(" ", strip=True)
            if (href.startswith("http") and "marginalia" not in href and "creativecommons" not in href
                    and t and len(t) > 8 and t not in seen and not t.startswith("http")):
                seen.add(t); out.append({"title": t, "url": href})
            if len(out) >= n: break
        return out
    return _try(one)

def ddg(q, n=10):
    r = requests.post("https://html.duckduckgo.com/html/", data={"q": q}, headers=UA, timeout=20)
    if r.status_code == 202 or "challenge" in r.text.lower():
        return {"error": "DDG CAPTCHA - use bing()/wikipedia()"}
    s = BeautifulSoup(r.text, "lxml")
    return [{"title": a.get_text(" ", strip=True), "url": a.get("href")}
            for a in s.select("a.result__a")[:n]]

def search(q, engine="auto", n=10):
    """Dispecer: bing -> wikipedia -> marginalia. Returneaza primul cu rezultate."""
    if engine == "auto":
        for fn in (bing, wikipedia, marginalia):
            res = fn(q, n)
            if res and not isinstance(res, dict):
                return {"engine": fn.__name__, "results": res}
        return {"engine": None, "results": []}
    res = globals()[engine](q, n)
    return {"engine": engine, "results": res if not isinstance(res, dict) else []}

if __name__ == "__main__":
    import sys
    q = sys.argv[1] if len(sys.argv) > 1 else "test"
    r = search(q)
    print(f"engine={r['engine']} rezultate={len(r['results'])}")
    for it in r["results"][:8]:
        print(" -", it.get("title", "")[:75])
        print("   ", (it.get("url") or it.get("site", ""))[:90])


def topical(q, n=8):
    """Cautare de ACTUALITATE: stiri (newsfeed) + web (search). Returneaza AMBELE."""
    out = {"news": [], "web": []}
    try:
        import newsfeed
        out["news"] = newsfeed.gnews(q, n=n)
    except Exception as e:
        out["news_err"] = str(e)
    out["web"] = search(q, n=n)["results"]
    return out
