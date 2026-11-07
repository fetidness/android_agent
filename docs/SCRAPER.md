# Scraper — referinta si verificare

Modulul de scraping partajat de cei doi agenti ai proiectului. O singura sursa de adevar,
doua copii identice (sha256 egal), plus un strat de verificare care face diferenta dintre
"a scris cod" si "a dovedit ca functioneaza".

## Fisiere

| cale | rol |
|---|---|
| `workspace/tools/scraper.py` | sursa canonica, 503 linii (agent-linux.py) |
| `workspace/app/net.sys32.agent/app/src/main/assets/python/scraper.py` | copie identica, livrata in APK |
| `requirements-scraper.txt` | cele 11 dependinte |
| `workspace/tools/jsengine.py` | motor JS alternativ (optional) |

```
bfdfb546460396531e273a66719a1d330806a09c1112d0947cbb51f5f98e6455  ambele copii
```

Regula: orice fix se face in `workspace/tools/` si se copiaza in `assets/`, altfel cei doi
agenti divergeaza fara ca nimeni sa observe.

## Stack

`requests` (HTTP) + `lxml` (XPath, C) + `parsel` (selectori CSS) + `trafilatura` (extractie
articol, elimina nav/ads/footer) + `feedparser` (RSS) + `justext` (boilerplate) +
`quickjs` (JavaScript) + `brotli` (Content-Encoding).

## Cele 15 moduri

| actiune | ce face | intoarce |
|---|---|---|
| `head` | HEAD request, urmarind redirecturile | status, ctype, len |
| `fetch` | GET, text brut | HTML |
| `sniff` | clasifica pagina: static / hybrid / spa | kind, scripts, patterns, text_chars, spa_signals |
| `xpath` | XPath pe lxml | lista de noduri/stringuri |
| `css` | selectori CSS prin parsel | lista de texte/atribute |
| `links` | toate `<a href>`, cu filtru regex optional | `[{href, text}]` |
| `meta` | meta taguri + OpenGraph + JSON-LD | dict |
| `table` | al n-lea tabel, ca matrice | `{tables, rows}` |
| `article` | extractie automata trafilatura | `{text, meta, chars}` |
| `supreme` | ★ alege singur cea mai buna metoda | `{method, data, chars, ok, timp_ms}` |
| `js` | ruleaza o expresie JS pe pagina | `{ok, result, js_bytes}` |
| `deep` | cauta recursiv chei in datele JS | `{values[]}` |
| `jsdata` | dump la blocul JSON brut | `{pattern, raw}` |
| `rss` | feed RSS/Atom | `{feed, count, entries[]}` |
| `health` | starea fiecarei dependinte | `{ok, total, missing[], modes{}}` |

## Problemele rezolvate in cod

Acestea sunt reparatii reale, fiecare cu un simptom care parea altceva:

**`//h1/text()` intorcea `[]`** — nu e bug lxml: textul statea intr-un copil
(`<h1><span>T</span></h1>`). Fix: fallback pe `//x//text()` cand rezultatul e gol, si pe
`text_content()` cand serializarea HTML iese goala.

**`css("h2::text")` intorcea mereu gol** — codul aplica `xpath("string(.)")` peste un
selector care avea deja pseudo-element. Fix: daca selectorul contine `::`, `getall()` direct.

**`article()` dadea 0 caractere pe pagini pline** — `favor_precision=True` prea agresiv pe
homepage-uri. Fix: lant de fallback `trafilatura(precision)` -> `trafilatura(fara precision)`
-> `justext` -> text brut din `<body>`. Asa nu se mai raporteaza "gol" pe o pagina plina.

**`json.dumps` cadea cu TypeError pe metadate** — in trafilatura 2.x, `as_dict()` intoarce
elemente lxml la cheile `body`/`commentsbody`. Fix: `_clean_meta()` serializeaza orice
non-primitiv.

## Verificare: cum se dovedeste ca merge

Modulul are `health()`, care raporteaza fiecare dependinta separat:

```json
{"ok": 11, "total": 11, "missing": [],
 "modes": {"requests":"ok","lxml":"ok","parsel":"ok","trafilatura":"ok",
           "feedparser":"ok","justext":"ok","courlan":"ok","htmldate":"ok",
           "quickjs":"ok","brotli":"ok","charset_normalizer":"ok"}}
```

Bateria completa se ruleaza pe site-uri structural diferite — static (`example.com`),
hibrid (`arstechnica`, `wikipedia`), SPA (`quotes.toscrape/js`), comprimat br
(`cloudflare.com`) — prin wrapper, nu prin biblioteca direct.

### Rezultatul masurat (2026-11-07)

```
health   ok  11/11        article ok  11148 car. (BBC, __NEXT_DATA__)
fetch    ok  HTML real    links   ok  111 linkuri (arstechnica)
sniff    ok  hybrid       meta    ok  15 campuri
xpath    ok               css     ok
table    ok               rss     ok  20 intrari
supreme  ok  210 car.     js      ok
deep     ok  ["Cloudflare"]        jsdata  ok  ld+json complet
head     ok  200
TOTAL: 15/15
```

## Capcane dovedite

**`brotli` lipsa = esec silentios total.** Site-urile care servesc
`Content-Encoding: br` ies ca bytes decodati ca text: **0 linkuri, text gunoi, zero
eroare**. Dovada numerica pe arstechnica: fara brotli ~44 KB si 0 linkuri; cu brotli
364 KB si 207 linkuri. Nu se verifica cu "nu a aruncat exceptie", ci cu numarul de bytes
si numarul de `<a `.

**`health` verde NU dovedeste ca transportul merge.** `requests` isi fixeaza decodoarele la
import, iar `health()` importa module la cerere. Un proces pornit inainte de
`pip install brotli` raporteaza `ok: 11/11` si totusi `fetch` intoarce bytes comprimati.
Diagnosticat cu timestampuri: proces pornit 07:23, pachete instalate 11:11. Dupa restartul
procesului, `fetch` a dat HTML real din primul caracter, fara nicio schimbare de cod.
**Dupa orice instalare care schimba un decodor de transport, reporneste procesul.**

**`quickjs` lipsa** — `_has_js()` intoarce False si modurile `js`/`deep` raspund
"niciun motor JS: lipsesc jsengine.py si quickjs", desi `pip show quickjs` e in regula.
`_has_js()` trebuie sa accepte si `jsengine.py`, si `quickjs`.

**403 nu e defect de scraper.** npmjs, Product Hunt, G2 raspund 403 = blocare anti-bot a
site-ului. Similar: `links -> []` pe `example.com` e corect (pagina chiar nu are `<a>`), iar
`deep -> "pagina nu are date JS"` pe Reddit/HN e corect (chiar nu au `__NEXT_DATA__`).

**`deep` cu o cheie inexistenta da `[]`, nu eroare.** `deep(keys=["name"])` pe arstechnica
da 4 valori; `deep(keys=["title"])` da `[]` pentru ca acea cheie nu exista in blob. Nu se
confunda cu un mod rupt.

## Instalare

```bash
python3 -m pip install --user --break-system-packages -r requirements-scraper.txt
# apoi REPORNESTE procesul care foloseste scraperul
```

## Wrapper-e

`agent-linux.py` expune 15 actiuni prin `scrape_tool`; `agent.py` (Android) expune 13 prin
`run_scraper_tool(a)`, care primeste **un dict**:

```python
run_scraper_tool({"action": "article", "url": "https://...", "max_chars": 12000})
```

Nu argumente pozitionale — da `TypeError: takes 1 positional argument but 4 were given`.
Diferenta de 2 actiuni fata de Linux (`health`, `jsdata`) este deliberata; absenta lor pe
Android nu este un defect.
