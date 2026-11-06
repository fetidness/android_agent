---
name: scraper-full-capability
description: Cum verifici si repari scraper-ul (13 moduri: article/supreme/xpath/css/links/meta/table/head/fetch/sniff/rss/deep/js) pe acest device cand un mod cade dupa rebuild APK - dependinte lipsa (courlan/htmldate/feedparser_sgmllib), _quickjs.so recompilat, si fix-urile reale din scraper.py
---

# Scraper la capacitate maxima - verificare si reparare

## Verificare completa (o singura comanda, 13 moduri)
Ruleaza din `files/python`; matricea trebuie sa dea 13/13 OK.
Modurile si semnaturile REALE: `fetch(url)`, `head(url)`, `article(url)`,
`xpath(url,expr)`, `css(url,sel,attr=None)`, `links(url,pattern=None)`,
`meta(url)`, `table(url,idx=0)`, `sniff(html)` (HTML, NU url),
`rss(url,limit=30)`, `deep(url_or_html,keys=None,pattern=None,is_html=False,limit=200)`,
`js_query(url_or_html,expr,pattern=None,is_html=False)`, `supreme(url,force=None,scrolls=1)`.

## Simptome si fix-uri (masurate 2026-11-06)
TRAP: `import trafilatura` -> ModuleNotFoundError courlan -> `article` moare.
  Fix: toolchain pip_install courlan (trage tld+babel). htmldate: pip_install htmldate (trage regex+dateparser).
TRAP: `feeds` cad cu `No module named feedparser_sgmllib` desi dist-info EXISTA.
  pip zice "already installed" si nu rescrie modulul. Fix: extrage manual din
  `files/wheels/feedparser_sgmllib-2.1.0-py3-none-any.whl` in site-packages.
TRAP: `import quickjs` -> No module named `_quickjs`. Nu exista wheel android pe PyPI.
  Fix: sdist de la PyPI, compileaza cele 6 C-uri cu toolchain-ul si LINK -lpython3.14:
  `$CC -shared -fPIC o*.o -o _quickjs.so -L<tc>/sysroot/usr/lib/aarch64-linux-android/35 -lpython3.14 -lm -ldl -latomic`
  (fara -lpython3.14 da "undefined symbol PyErr_SetString"). Copiaza .so in site-packages.
SEEN: quickjs eval intoarce str/int corect; obiectele JS nu sunt JSON-serializable in python
  -> in expresie se foloseste `JSON.stringify(...)`.

## Bug-uri reale reparate in scraper.py (DE PASTRAT la rebuild)
1. `js_query` refuza sa ruleze daca pagina nu are blob __NEXT_DATA__/ld+json, chiar daca
   i-ai dat o expresie (`document.title`). Fix: pune titlul+URL-ul in stub-ul document
   si ruleaza expresia si fara DATE.
2. `deep` pe pagina fara date JS returna `ReferenceError: DATE is not defined`;
   acum mesaj curat + hint spre article/supreme.
3. `supreme` raporta `ok` fara sa dea eroare cand fetch-ul cadea (apnews 403);
   acum intoarce `error` explicit si 0 caractere => ok False.
4. Headers HTTP ridicate la profil complet de browser (Sec-Fetch-*, Accept-Language en).

## Limite ONESTE (nu sunt bug-uri de cod)
reuters.com -> 401, apnews.com -> 403, hackernews rss -> 419: blocare anti-bot pe server,
identic din requests brut cu headers de browser. Nu se rezolva din scraper.
rss.cnn.com -> SSLError (lant/cert). Foloseste alt feed.

## Metoda EXACTA de compilare _quickjs.so (verificata 2026-11-06, 6/6 fisiere rc=0)
```
TC=/data/data/net.sys32.agent/files/toolchain
D=/data/data/net.sys32.agent/files/tmp/qs/quickjs-1.19.4      # sdist quickjs-1.19.4.tar.gz de pe PyPI
$TC/bin/clang -resource-dir $TC/lib/clang/21 -B /data/data/net.sys32.agent/files/tmp \
  -fPIC -O2 --target=aarch64-linux-android35 --sysroot=$TC/sysroot \
  -I$TC/sysroot/usr/include -I$TC/pyinc \
  '-DCONFIG_VERSION="2024-01-13"' -DCONFIG_BIGNUM -D_GNU_SOURCE \
  -c <module.c|upstream-quickjs/{cutils,libbf,libregexp,libunicode,quickjs}.c> -o oN.o
$TC/bin/clang -shared o0.o o1.o o2.o o3.o o4.o o5.o -o _quickjs.so \
  -L$TC/sysroot/usr/lib/aarch64-linux-android/35 -L$TC/lib/clang/21/lib/linux \
  -lpython3.14 -lm -ldl -latomic
cp _quickjs.so files/pyhome/lib/python3.14/site-packages/_quickjs.so && chmod 644 ...
```

## Pitfalls suplimentare (masurate)
- toolchain action=pip_install accepta UN SINGUR pachet per apel: `package="courlan htmldate feedparser_sgmllib"` ->
  `pip._internal.exceptions.InstallationError: Invalid requirement ... Expected semicolon`. Un apel per pachet.
- functia `toolchain` NU exista in sandbox-ul run_code (`name 'toolchain' is not defined`) -> se apeleaza ca tool separat.
- `pip install <wheel local>` pe un pachet cu dist-info dar fara modul zice
  "is already installed with the same version ... Use --force-reinstall" si NU repara nimic ->
  extrage singur: `zipfile.ZipFile(files/wheels/<pkg>.whl)` -> scrie fiecare 'pkg/...' in site-packages.
- `quickjs.Context().eval("...")` intoarce corect str/int/float; un obiect JS iese ca `Object`
  si `json.dumps` da `TypeError: Object of type Object is not JSON serializable` ->
  cere `JSON.stringify(x)` in expresia JS.
- NU trece HTML la functiile care cer URL: `meta(url)`/`doc(url)` fac `fetch(url)` ->
  `requests.exceptions.InvalidSchema: No connection adapters were found for '<!DOCTYPE html>...'`;
  doar `sniff(html)` primeste HTML.
- Matricea de verificare trebuie sa dea 13/13; daca un mod da "EMPTY" (nu exceptie) verifica
  semnatura functiei inainte sa declari scraper-ul stricat (`inspect.signature`).

## Livrare (out of the box)
Fisierul care ruleaza e `files/python/scraper.py`; sursa din APK e
`assets/python/scraper.py`. Dupa orice patch: copiaza in assets + repo, altfel
update-ul de APK il suprascrie cu versiunea veche. Copie de siguranta:
`/storage/emulated/0/Download/Agent/workspace/patched/scraper.py`.

## CEA MAI IMPORTANTA CAUZA (gasita 6 nov): BROTLI LIPSA
TRAP: pagini servite cu `Content-Encoding: br` (arstechnica, react.dev, bbc) -> requests NU
  decomprima fara modulul brotli -> `r.text` intoarce BYTES COMPRIMATE ca text ->
  trafilatura/justext dau 0 caractere, iar pe BBC dadea etichete de meniu in loc de articol.
  Simptom-cheie: `r.headers["content-encoding"] == "br"` si `r.text` incepe cu caractere binare.
  Fix: toolchain pip_install brotli (compileaza _brotli .so nativ, ~46s). Dupa asta totul merge.
PREVENT: la orice 'extractia da 0 caractere' verifica INTOTDEAUNA content-encoding inainte de
  a da vina pe trafilatura sau pe site.

## supreme(): ordinea corecta (rescrisa 6 nov)
Textul real (article) se extrage PRIMUL. Blobul JS (__NEXT_DATA__) e DOAR fallback, pentru ca
pe un articol BBC contine etichete de meniu, nu continutul. Randarea Chrome doar daca nici JS
nu ajuta si sniff zice 'spa'. Rezultat dovedit: articol BBC -> 3094 chars text corect;
homepage BBC -> hybrid 11412 chars (text propriu prea sarac, JS castiga).
TRAP: procesul agentului tine modulul VECHI in memorie -> tool-ul `scraper` da rezultatul vechi
  desi fisierul de pe disc e corect (verificat: apel direct = corect, tool = vechi).
  Nu depana codul: cere RESTART al aplicatiei, apoi retesteaza cu tool-ul.

## Diagnostic rapid: "modul da gol / rezultat absurd" (ordinea corecta de verificare)
1. `r = scraper._S.get(url); print(r.headers.get("content-encoding"), r.text[:80])`
   -> daca `br` si textul incepe binar: lipseste brotli (vezi sectiunea BROTLI LIPSA).
2. `scraper.sniff(html)` zice `text_chars` mare dar `article()` da 0 -> NU e pagina goala,
   e compresie nedecodata (acelasi fix).
3. `inspect.getsource(scraper.article)` / `inspect.signature(...)` -> confirma ca fix-ul e
   chiar in fisierul de pe disc; apoi `python -c "import scraper; scraper.supreme(url)"`
   intr-un SUBPROCES (proces nou) ca sa nu fie mascat de modulul deja incarcat.
4. Daca subprocesul da corect dar tool-ul `scraper` din agent da vechi -> procesul agentului
   tine modulul vechi in memorie; nu edita cod, cere RESTART.

## Regula supreme() - ce alege si de ce
- `article()` (trafilatura precision -> recall -> justext -> text brut din body) se ruleaza
  INTOTDEAUNA primul; `how` spune care strategie a mers.
- JS (`__NEXT_DATA__`/`__NUXT__`/`ld+json`) doar daca textul e < 400 chars si JS da cu
  200+ chars mai mult -> `method: hybrid`.
- Randare Chrome doar daca nici JS nu ajuta si `sniff` zice `spa`.
- `force='scraper'|'hybrid'|'chrome'` sare peste decizia automata (util la diagnostic).

## Capcane dovedite pe HOST (x86_64, agent-linux.py) - 6 nov 2026

TRAP: `brotli` lipseste -> `requests` NU trimite `Accept-Encoding: br`, desi scraper.py il
cere explicit in headers -> serverul intoarce oricum `Content-Encoding: br` si requests
intoarce bytes comprimati ca text -> arstechnica.com 43870 B cu `text.count("<a ")==0`
(la fel react.dev) -> toate extractiile dau 0 linkuri si text-gunoi, FARA nicio eroare.
Fix: `pip install brotli`; dovada dupa: 364885 B si 207 linkuri pe arstechnica.
Diagnostic rapid: `scraper.health()` -> cheia `brotli`.

TRAP: `quickjs` lipseste pe host desi exista pe device (in assets) -> `_has_js()` returna
False si `js_query`/`deep` raspundeau "jsengine.py is missing" -> cele 2 moduri moarte.
Fix in scraper.py: `_js_context()` incearca `jsengine`, apoi `quickjs` direct (Context +
stub de browser); `_has_js()` accepta oricare.

TRAP: `xpath('//h1/text()')` intorcea `[]` pe Wikipedia desi `<h1>` exista, pentru ca
textul sta in `<span>` copil -> `//h1/text()` e legitim gol. Fix: fallback automat pe
`//h1//text()` cand rezultatul e gol; plus nodurile-text nu mai trec prin `lxml_tostr`.

TRAP: agentul pornit din alt director nu gasea scraper.py -> `[scrape] scraper.py
indisponibil` -> scraper_tool pune in sys.path DOAR `<dir agent-linux.py>/workspace/tools`
si `<dir>/tools` -> rulam agentul din radacina repo-ului sau punem tools/ in PYTHONPATH.

OK: toate cele 14 actiuni ale tool-ului `scrape` (head, fetch, sniff, xpath, css, links,
meta, table, article, supreme, js, deep, jsdata, health) ruleaza prin agent-linux.py
pe 4 site-uri diferite: 52/52 fara erori (wiki, arstechnica, react.dev, bbc.com, HN).

P: /home/gab/android_agent/requirements-scraper.txt -> dependintele pentru host
