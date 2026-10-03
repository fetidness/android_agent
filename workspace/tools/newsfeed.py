"""newsfeed.py - informatii ACTUALE gratuit (fara cheie API).

SURSE (dovedite 2026-10-03):
  gnews(q)   - Google News RSS: agregator global, 100+ stiri, CU DATA (pubDate).
               CEL MAI BUN pt actualitate. Gratuit, fara cheie, fara blocare.
  bingnews(q)- Bing News: vertical de stiri, cu sursa + link (HTML, se poate rata).
  rss(url)   - orice feed RSS direct (Digi24 214 itemi, BBC 25, Guardian 45...).
  FEEDS      - feed-uri romanesti si internationale gata de folosit.
"""
import requests, re
from bs4 import BeautifulSoup
from email.utils import parsedate_to_datetime

UA = {"User-Agent": "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/126 Mobile Safari/537.36",
      "Accept-Language": "en-US,en;q=0.9"}

FEEDS = {
    "digi24":    "https://www.digi24.ro/rss",
    "hotnews":   "https://www.hotnews.ro/rss",
    "agerpres":  "https://www.agerpres.ro/rss",
    "bbc":       "https://feeds.bbci.co.uk/news/rss.xml",
    "guardian":  "https://www.theguardian.com/world/rss",
    "reuters":   "https://news.google.com/rss/search?q=reuters&hl=en",
}

def _date(s):
    try:
        return parsedate_to_datetime(s).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return s[:25]

def gnews(q, n=20, lang="en", country="RO"):
    """Google News RSS - agregator de actualitate, cu data. CEL MAI BUN."""
    u = f"https://news.google.com/rss/search?q={requests.utils.quote(q)}&hl={lang}&gl={country}&ceid={country}:{lang}"
    r = requests.get(u, headers=UA, timeout=20)
    s = BeautifulSoup(r.text, "xml")
    out = []
    for it in s.find_all("item")[:n]:
        src = it.find("source")
        out.append({
            "title": it.title.get_text(),
            "date": _date(it.pubDate.get_text()) if it.pubDate else "",
            "source": src.get_text() if src else "",
            "url": it.link.get_text() if it.link else "",
        })
    return out

def bingnews(q, n=15):
    """Bing News - vertical de stiri (poate fi inconsistent)."""
    r = requests.get("https://www.bing.com/news/search",
                     params={"q": q, "setlang": "en"}, headers=UA, timeout=20)
    s = BeautifulSoup(r.text, "lxml")
    out = []
    for a in s.select("a.title"):
        if not a.get("href"): continue
        parent = a.find_parent(["div", "article"])
        src = parent.select_one(".source, .t_s, [class*=source]") if parent else None
        out.append({"title": a.get_text(" ", strip=True),
                    "url": a.get("href", ""),
                    "source": src.get_text(" ", strip=True) if src else ""})
        if len(out) >= n: break
    return out

def rss(url, n=30):
    """Orice feed RSS: titlu + data + link."""
    r = requests.get(url, headers=UA, timeout=20)
    s = BeautifulSoup(r.text, "xml")
    out = []
    for it in s.find_all("item")[:n]:
        out.append({"title": it.title.get_text() if it.title else "",
                    "date": _date(it.pubDate.get_text()) if it.pubDate else "",
                    "url": it.link.get_text() if it.link else ""})
    return out

def latest(topic=None, n=20, lang="en"):
    """Stiri de ultima ora: fara topic -> feed-uri RO; cu topic -> Google News."""
    if topic:
        return gnews(topic, n=n, lang=lang)
    out = []
    for name, url in FEEDS.items():
        try:
            items = rss(url, n=n // len(FEEDS) + 3)
            for it in items: it["feed"] = name
            out.extend(items)
        except Exception:
            pass
    out.sort(key=lambda x: x.get("date", ""), reverse=True)
    return out[:n]

if __name__ == "__main__":
    import sys
    q = sys.argv[1] if len(sys.argv) > 1 else None
    for it in (gnews(q, 10) if q else latest(n=10)):
        print(f"[{it.get('date','?')}] {it.get('source','') or it.get('feed','')}")
        print(f"  {it['title'][:80]}")
