#!/usr/bin/env python3
"""jsengine.py - motor JavaScript NATIV pe device (QuickJS, compilat local).

DE CE: unele pagini au datele in JavaScript (window.__DATA__, scripturi inline,
calcule client-side). scraper.py nu ruleaza JS; jsfetch.py randeaza in Chrome dar
costa 12-23s si cere ADB. jsengine.py e calea RAPIDA: ruleaza JS in proces.

DOVEDIT pe device (3 oct 2026): quickjs 1.19.4 compilat nativ
(wheel quickjs-1.19.4-cp314-cp314-android_24_arm64_v8a.whl).
Suporta ES2020 complet: async/await, Promise, optional chaining (?.),
nullish (??), Map/Set, classes, BigInt, regex, closures.
Plus: comunicare bidirectionala Python<->JS prin add_callable().

UTILIZARE:
  python jsengine.py '<js>'            -> evalueaza si afiseaza
  import jsengine
  ctx = jsengine.context()             # mediu "browser" pregatit
  ctx.eval("1+1")                      # -> 2
"""
import quickjs as _q

# functii JS care leaga motorul la dependintele pe care le avem deja
# (nu are DOM propriu - ii dam un mediu minimal + acces la lxml)
_BROWSER_STUB = r"""
var window = this;
var globalThis = this;
var self = this;
var console = { log: function(){}, warn: function(){}, error: function(){}, info: function(){} };
var document = {
    getElementById: function(){ return null; },
    querySelector: function(){ return null; },
    querySelectorAll: function(){ return []; },
    createElement: function(t){ return {tagName:t, style:{}, appendChild:function(){}, setAttribute:function(){}}; },
    body: { appendChild: function(){}, innerHTML: "" },
    documentElement: { innerHTML: "" }
};
var localStorage = { getItem: function(){return null;}, setItem: function(){}, removeItem: function(){} };
var navigator = { userAgent: "Mozilla/5.0 (Linux; Android 16) AppleWebKit/537.36 Chrome/126 Mobile Safari/537.36" };
var location = { href: "", hostname: "", pathname: "/" };
var setTimeout = function(fn, ms){ return 0; };
var clearTimeout = function(){};
var atob = function(s){ return s; };
var btoa = function(s){ return s; };
"""

def context(stub=True):
    """Creeaza un Context QuickJS, cu mediu 'browser' minimal (window/document/console)."""
    ctx = _q.Context()
    if stub:
        ctx.eval(_BROWSER_STUB)
    return ctx

def run(js, stub=True):
    """Evalueaza JS o singura data si intoarce rezultatul."""
    return context(stub).eval(js)

def extract_and_run(html, expr=None):
    """Extrage TOATE blocurile <script> inline din HTML si le executa.

    Utile pentru pagini care pun datele in window.__DATA__ sau calculeaza in JS.
    expr = expresie optionala de evaluat DUPA scripturile paginii
    (ex. 'JSON.stringify(window.__DATA__)'). Fara expr, intoarce ce a supravietuit.
    """
    import re
    ctx = context(stub=True)
    scripts = re.findall(r"<script[^>]*>(.*?)</script>", html or "", re.S | re.I)
    rule=0; erori=[]
    for s in scripts:
        s = s.strip()
        if not s or s.startswith("//"): continue
        try:
            ctx.eval(s); rule += 1
        except Exception as e:
            erori.append(str(e)[:80])
    rez = None
    if expr:
        try: rez = ctx.eval(expr)
        except Exception as e: erori.append("expr: "+str(e)[:80])
    return {"scripts_rulate": rule, "total_scripts": len(scripts),
            "erori": erori[:5], "rezultat": rez}

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(0)
    try:
        r = run(sys.argv[1])
        print(r if r is not None else "(no value)")
    except Exception as e:
        print("JS ERROR:", e); sys.exit(1)
