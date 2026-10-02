#!/usr/bin/env python3
import base64,contextlib,datetime,io,json,os,random,re,shlex,shutil,signal,subprocess,sys,tempfile,threading,time,urllib.request

# --- ANDROID FIX: folosim certificatele CA ale sistemului Android pentru HTTPS ---
if sys.platform=="android" or os.path.exists("/system/bin/linker64"):
    try:
        import ssl as _ssl, glob as _glob
        _b=os.path.join(tempfile.gettempdir(),"ca-bundle.pem")
        if not os.path.exists(_b):
            with open(_b,"w") as _o:
                for _d in ("/apex/com.android.conscrypt/cacerts","/system/etc/security/cacerts"):
                    for _f in sorted(_glob.glob(_d+"/*")):
                        try:
                            _z=open(_f,"rb").read()
                            if b"BEGIN CERTIFICATE" in _z: _o.write(_z.decode("utf-8","replace"))
                        except Exception: pass
        _ssl._create_default_https_context=lambda cafile=None,capath=None,cadata=None,_b=_b: _ssl.create_default_context(cafile=_b)
        os.environ.setdefault("SSL_CERT_FILE",_b)
    except Exception: pass

# --- SHELL: Android nu are bash, doar sh (mksh). Desktop ramane bash -lc. ---
SHELL=[("sh","-c") if (sys.platform=="android" or os.path.exists("/system/bin/linker64")) else ("bash","-lc")]
E="\33"                                     # ESC, kept separate so regexes never touch it
D={"h1":E+"[1;38;5;213m","h2":E+"[1;38;5;51m","h3":E+"[1;38;5;226m","h4":E+"[1;38;5;118m",
   "h5":E+"[1;38;5;208m","h6":E+"[1;38;5;141m","b":E+"[1;38;5;231m","i":E+"[3;38;5;219m",
   "s":E+"[9;38;5;244m","hl":E+"[1;38;5;226m","code":E+"[38;5;231m",
   "bul":E+"[1;38;5;208m","num":E+"[1;38;5;196m","txt":E+"[38;5;255m","quote":E+"[38;5;117m",
   "tbl":E+"[38;5;186m","tblh":E+"[1;38;5;51m","link":E+"[4;38;5;213m","url":E+"[38;5;245m","hr":E+"[38;5;105m",
   "done":E+"[1;38;5;46m","todo":E+"[1;38;5;220m","cln":E+"[38;5;252m",
   "cfence":E+"[1;38;5;82m","ckw":E+"[1;38;5;205m","cst":E+"[38;5;228m","cnum":E+"[38;5;123m","ccm":E+"[38;5;245m","cop":E+"[38;5;203m","off":E+"[0m"}
KWP=re.compile(r"\b(?:import|from|def|class|return|if|elif|else|for|while|in|not|and|or|try|except|finally|with|as|lambda|print|None|True|False|raise|yield|global|pass|break|continue|async|await|int|str|float|list|dict|set|len|open|range|self)\b")
BLK=re.compile(r"(```[^\n]*\n[\s\S]*?```)")
RUL=re.compile(r"`[^`\n]+`|\*\*?[^*\n]+\*\*?|__?[^_\n]+__?|~~[^~\n]+~~|==[^=\n]+==|\[[^\]\n]+\]\([^)\n]+\)|^[ \t]*(?:#{1,6} |(?:[-+*] |\d+\. )|\||> ?).*$",re.M)
BLANKMAX=0   # blank lines kept in the final answer: 0 = compact (one blank line ONLY before a heading)
EMPTY_RETRY=3   # how many times we retry when the model answers with an EMPTY message (no text, no tool_calls)
def _empty(m):
    """Message with no text AND no tool_calls: the model answered empty (a disguised glitch/timeout).
    It does NOT mean 'task finished' - if we miss it, the agent stops in the middle of the work."""
    return not (m.get("content") or "").strip() and not (m.get("tool_calls") or [])
def _compact(s):
    """Compact layout: any run of blank lines collapses to ONE; that single blank line is KEPT only
    before a heading (so sections stay readable), and removed right after a heading and inside the body
    (a heading sticks to its own content). BLANKMAX>0 keeps that many blank lines instead."""
    if BLANKMAX<=0:
        s=re.sub(r"[ \t]*\n(?:[ \t]*\n)+","\n\n",s)          # every blank run -> exactly one blank line
        s=re.sub(r"\n{2,}(?=[ \t]*#{1,6} )","\n\n",s)          # headings: exactly one blank line before
        return re.sub(r"([ \t]*#{1,6} [^\n]*)\n\n+","\\1\n",s)  # heading: no blank line after it
    s=re.sub(r"[ \t]*\n(?:[ \t]*\n)+","\n"*(BLANKMAX+1),s)
    return re.sub(r"\n{2,}(?=[ \t]*#{1,6} )","\n",s)

def _paint(line):
    line=line.replace("\t","    "); n=len(line); marks=[]
    def add(a,b,tag):
        marks.append((a,b,tag))
    for m in re.finditer(r"#[^\n]*$",line): add(m.start(),m.end(),"c")
    q=chr(34); ap=chr(39)
    for m in re.finditer("["+q+ap+"][^"+q+ap+"\\\n]*["+q+ap+"]",line): add(m.start(),m.end(),"s")
    for m in KWP.finditer(line): add(m.start(),m.end(),"k")
    for m in re.finditer(r"(?<![\w#.])\d+\.?\d*",line): add(m.start(),m.end(),"n")
    for m in re.finditer(r"[^\w\s]+",line): add(m.start(),m.end(),"o")
    prio={"o":0,"n":1,"k":2,"s":3,"c":4}
    cur=[None]*n
    for a,b,tag in marks:
        for i in range(a,min(b,n)):
            if cur[i] is None or prio[tag]>=prio[cur[i]]: cur[i]=tag
    o=[];last=None
    for i,c in enumerate(line):
        t=cur[i]
        if t!=last:
            o.append({"k":D["ckw"],"s":D["cst"],"n":D["cnum"],"c":D["ccm"],"o":D["cop"],None:D["cln"]}[t]); last=t
        o.append(c)
    return "".join(o)
def _box(info,body):
    o=[D["cfence"]+"  "+D["ckw"]+info+D["off"]]
    for l in body: o.append("  "+D["cln"]+_paint(l.rstrip())+D["off"])
    return "\n".join(o)
SPAN=re.compile(r"`[^`\n]+`|\*\*?[^*\n]+\*\*?|__?[^_\n]+__?|~~[^~\n]+~~|==[^=\n]+==|\[[^\]\n]+\]\([^)\n]+\)")
def _sp(m):
    t=m.group()
    if t[0]=="`": return D["code"]+t.strip("`")+D["off"]
    if t[:2] in("**","__"): return D["b"]+t[2:-2]+D["off"]
    if t.startswith("~~"): return D["s"]+t[2:-2]+D["off"]
    if t.startswith("=="): return D["hl"]+t[2:-2]+D["off"]
    if t[0] in"*_":
        if t[:2] in("**","__") or t[-2:] in(t[0]*2): return D["b"]+t.strip("*_")+D["off"]
        return D["i"]+t[1:-1]+D["off"]
    if t.startswith("["):
        a,b=re.match(r"\[([^\]]+)\]\(([^)]+)\)",t).groups(); return D["link"]+a+D["off"]+" "+D["url"]+"⟶ "+b+D["off"]
    return t
def _in(s): return SPAN.sub(_sp,s)
def _vislen(s):
    """VISIBLE length of a string: ignores the ANSI sequences (colours)."""
    return len(re.sub(r"\x1b\[[0-9;]*m","",s))
def _tbl_cells(line):
    r"""The cells of one table row: trims the edge pipes, respects `code`
    and the escaped pipes (\|)."""
    raw=line.strip()
    if raw.startswith("|"): raw=raw[1:]
    if raw.endswith("|"): raw=raw[:-1]
    out=[];buf=[];tick=0;i=0
    while i<len(raw):
        c=raw[i]
        if c=="\\" and i+1<len(raw) and raw[i+1]=="|": buf.append("|");i+=2;continue
        if c=="`": tick^=1
        if c=="|" and not tick: out.append("".join(buf));buf=[];i+=1;continue
        buf.append(c);i+=1
    out.append("".join(buf))
    return [x.strip() for x in out]
SEPCELL=re.compile(r"^:?-+:?$")
def _is_sep(line):
    parts=_tbl_cells(line)
    return bool(parts) and any("-" in p for p in parts) and all(SEPCELL.match(p) for p in parts if p!="")
def _tbl_align(cells):
    return ["c" if (c.startswith(":") and c.endswith(":")) else "r" if c.endswith(":") else "l" for c in cells]
def _tbl_row(cells,w,al):
    parts=[]
    for k,c in enumerate(cells):
        txt=_in(c); pad=max(w[k]-_vislen(txt),0)
        a=al[k] if k<len(al) else "l"
        if a=="r": l,r=pad,0
        elif a=="c": l,r=pad//2,pad-pad//2
        else: l,r=0,pad
        parts.append(" "*l+txt+" "*r)
    return " \u2502 ".join(parts)   # NO rstrip and no outer padding: _table adds the box
def _wrap(s,W):
    """Word wrap: at most W visible characters per line. A token longer than W is HARD-split,
    so a long path or file name can never push the row past the terminal width."""
    out=[]; cur=""
    for w in str(s).split(" "):
        while len(w)>W:   # hard-split an over-long token (a long path)
            if cur: out.append(cur); cur=""
            out.append(w[:W]); w=w[W:]
        if not cur: cur=w
        elif len(cur)+1+len(w)<=W: cur+=" "+w
        else: out.append(cur); cur=w
    if cur: out.append(cur)
    return out or [""]
def _table(lines):
    """Renders the whole table as a FULL BOX (top/middle/bottom borders + corners), so it looks
    like one clean block instead of a stack of loose columns. Widths are measured on the ALREADY
    rendered content (bold/colours/links cannot break the alignment). If the table is wider than
    the terminal, the widest columns are narrowed PROPORTIONALLY and their cells are wrapped over
    several lines - no row is ever cut by the terminal itself. If there is spare room the columns
    grow a little (up to their natural width + a small air allowance) so the box looks balanced."""
    raw=[_tbl_cells(l) for l in lines]
    ncol=max(len(r) for r in raw)
    rows=[r+[""]*(ncol-len(r)) for r in raw]
    has_hdr=len(lines)>=2 and _is_sep(lines[1]) and not _is_sep(lines[0])
    al=_tbl_align(raw[1]) if has_hdr else ["l"]*ncol
    natural=[0]*ncol
    for i,r in enumerate(rows):
        if has_hdr and i==1: continue
        for k,c in enumerate(r): natural[k]=max(natural[k],_vislen(_in(c)))
    # natural width of the column, but never more than the header of the sorted block
    w=[max(3,n) for n in natural]
    # --- fit the terminal: "  " + ncol cells + (ncol-1) separators + 2 border pipes ---
    fixed=2+(ncol-1)*3+2+2   # +2 safety margin: the box never touches the last terminal column
    room=max(8,CS()-fixed)
    if sum(w)>room:
        # narrow PROPORTIONALLY to the real content, with a floor, then shave the widest column
        tot=sum(w) or 1; floor=4
        tgt=[max(floor,min(w[k],int(room*w[k]/tot))) for k in range(ncol)]
        while sum(tgt)>room:
            k=tgt.index(max(tgt))
            if tgt[k]<=floor: break
            tgt[k]-=1
        if sum(tgt)<=room: w=tgt
    # --- spare room: give every column a little air (ceil-based, so cells do not hug the pipes) ---
    once=True
    while once:
        once=False
        left=room-sum(w)
        if left>0:
            for k in range(ncol):
                if left<=0: break
                w[k]+=1; left-=1; once=True
    top =D["tblh"]+"  \u250c"+"\u252c".join("\u2500"*(x+2) for x in w)+"\u2510"+D["off"]
    mid =D["tblh"]+"  \u251c"+"\u253c".join("\u2500"*(x+2) for x in w)+"\u2524"+D["off"]
    bot =D["tblh"]+"  \u2514"+"\u2534".join("\u2500"*(x+2) for x in w)+"\u2518"+D["off"]
    out=[]
    out=[]
    for i,r in enumerate(rows):
        if has_hdr and i==1:
            out.append(mid); continue
        celllines=[_wrap(_in(c),w[k]) if _vislen(_in(c))>w[k] else [_in(c)] for k,c in enumerate(r)]
        h=max(len(x) for x in celllines)
        for ln in range(h):   # a tall cell may become several physical lines; columns stay aligned
            part=[(celllines[k][ln] if ln<len(celllines[k]) else "") for k in range(ncol)]
            out.append((D["tblh"] if i==0 else D["tbl"])+"  \u2502 "+_tbl_row(part,w,al)+" \u2502"+D["off"])
    return "\n".join([top]+out+[bot])

def _f(m):
    t=m.group(); head=re.match(r"^[ \t]*(?:(#{1,6}) |([-+*]) (\[[ xX]\] )?|(\d+)\. |(> ?))",t)
    if not head:
        if re.match(r"^[ \t]*[-*_=]{3,}[ \t]*$",t): return D["hr"]+"-"*48+D["off"]
        return _sp(m)
    if head.group(1):
        n=len(head.group(1)); return D["h%d"%n]+"\u2502 "+_in(t.lstrip("# ").strip())+D["off"]
    if head.group(2):
        if head.group(3): return (D["done"]+" ✔" if head.group(3)[1] in"xX" else D["todo"]+" ☐")+D["txt"]+" "+_in(t[t.index("]")+1:].strip())+D["off"]
        d=len(t)-len(t.lstrip()); return " "*d+D["bul"]+("\u25b8","\u2023","\u2022")[d%3]+" "+D["txt"]+_in(t.lstrip()[2:])+D["off"]
    if head.group(4): return D["num"]+head.group(4).rjust(3)+". "+D["txt"]+_in(t[t.index(".")+1:].strip())+D["off"]
    return D["quote"]+" ▌ "+_in(t.lstrip()[1:].strip())+" "+D["off"]
def _chunk(p):
    """A text segment without code: groups the table lines into whole blocks
    (so we can compute the widths over the whole table), the rest goes through RUL."""
    lines=p.split("\n"); out=[]; buf=[]; i=0
    def flush():
        if buf: out.append(RUL.sub(_f,"\n".join(buf))); buf.clear()
    while i<len(lines):
        if lines[i].strip().startswith("|"):
            j=i
            while j<len(lines) and lines[j].strip().startswith("|"): j+=1
            flush(); out.append(_table(lines[i:j])); i=j
        else:
            buf.append(lines[i]); i+=1
    flush()
    return "\n".join(out)
def _mdtable_to_list(block):
    """Converteste un bloc de tabel Markdown (linii cu '|') in LISTA simpla - pe ecranul mic
    al telefonului tabelele se vad prost. Fiecare rand devine un bullet."""
    lines=[l for l in block.split("\n") if l.strip()]
    if sum(1 for l in lines if l.count("|")>=2) < 2: return block   # nu e tabel
    has_sep = any(re.match(r"^\s*\|?[\s:-]*(\|[\s:-]*)+\|?\s*$", l) for l in lines)
    head=None; out=[]
    for l in lines:
        if re.match(r"^\s*\|?[\s:-]*(\|[\s:-]*)+\|?\s*$", l): continue   # separator |---|
        if l.count("|")>=2 or l.strip().startswith("|"):
            cells=[c.strip() for c in l.strip().strip("|").split("|")]
            if has_sep and head is None:      # primul rand = header, il retinem pentru etichete
                head=cells; continue
            if head and len(cells)>1:
                first=cells[0]
                rest=", ".join(f"{head[i]}: {cells[i]}" for i in range(1,len(cells)) if i<len(head) and cells[i])
                out.append("- "+first+(": "+rest if rest else ""))
            else:
                out.append("- "+", ".join(x for x in cells if x))
        else:
            out.append(l.strip())
    return "\n".join(out) if out else block


def render(t):
    out=[]
    for p in BLK.split(t):
        if p.startswith("```"):
            L=p.strip("\n").split("\n"); body=[x for x in L[1:] if not x.strip().startswith("```")]
            out.append(_box(L[0].strip("` ").strip() or "code",body))
        else:
            out.append(_chunk(_compact(_mdtable_to_list(p))))
    return re.sub(r"^\n+","",re.sub(r"\n(?:\n)+$","\n","".join(out)))
_SANDBOX=os.path.dirname(os.path.abspath(__file__))
_DEFHOME=os.path.join(_SANDBOX,"..")          # fallback: langa scriptul agentului (in sandbox)
_DEFHOME=os.path.abspath(_DEFHOME)
# Structura ceruta de operator (folder standard, deja indexat de file manager):
#   HOME/            -> memory.md + context.json
#   HOME/workspace/  -> TOT ce genereaza agentul (proiecte, fisiere, logs, archive)
# ★ HOME_DIR = sandbox-ul PRIVAT al app-ului (files/), NU sdcard-ul. Decizie operator:
# memory.md + context.json + bg_jobs.json + logs/ traiesc in stocarea privata => zero FUSE,
# zero zgomot MediaProvider (nici quota, nici revoke_uri_permission), scriere rapida.
# AGENT_HOME se IGNORA acum pentru HOME (ramane doar ptr compat); il folosim DOAR ca sa
# localizam WORKSPACE-ul, care trebuie sa ramana VIZIBIL pe sdcard pentru operator.
HOME_DIR=_DEFHOME
def _writable(d):
    try:
        os.makedirs(d,exist_ok=True)
        _t=os.path.join(d,".wtest"); open(_t,"w").write("x"); os.remove(_t); return True
    except Exception: return False
if not _writable(HOME_DIR):
    HOME_DIR=_DEFHOME; _writable(HOME_DIR)
# WORKSPACE: VIZIBIL, pe sdcard (unde operatorul vede fisierele generate de agent).
_AGH=os.environ.get("AGENT_HOME","").strip()
WORK=(os.path.join(_AGH,"workspace") if _AGH else os.path.join(HOME_DIR,"workspace"))
# registrul job-urilor de fundal (persistent, langa context.json/memory.md)
BG_REG=os.path.join(HOME_DIR,"bg_jobs.json")   # lista job-urilor cunoscute (id, pid, log, stare)
BG_LOG="/data/local/tmp/bg_logs"                # fundal: shell (uid 2000) NU poate scrie in sandbox-ul app-ului -> scriem unde poate shell, citim prin adbsh
os.makedirs(WORK,exist_ok=True)
# Folderul de lucru poate fi mutat intr-un loc VIZIBIL (ex. /sdcard/agent), ca operatorul
CTXNAME="context.json"       # conversation history: lives permanently in HOME_DIR (next to memory.md)
# NU se sterge workspace-ul la startup: proiectele trebuie sa supravietuiasca sesiunilor.
# Se curata doar gunoiul evident (fisiere temporare recunoscute), niciodata folderele de proiect.
for f in os.listdir(WORK):
    if f in (CTXNAME,CTXNAME+".tmp","logs","archive"): continue
    # sterge doar fisiere temporare clar recunoscute (nu foldere, nu surse)
    if os.path.isfile(os.path.join(WORK,f)) and (
        f.endswith(".tmp") or f.endswith(".log.tmp") or f.startswith(".tmp_")):
        try: os.remove(os.path.join(WORK,f))
        except Exception: pass
# My Files / MTP nu indexeaza un folder nou care nu contine NICIUN fisier media, deci
# "agent" nu aparea in lista de foldere. Scriem o iconita PNG minuscula: MediaScanner
# indexeaza directorul si folderul devine vizibil in orice file manager (Samsung/Sony/etc).
try:
    _mk=os.path.join(WORK,".agent_folder.png")
    if not os.path.exists(_mk):
        import base64 as _b64
        open(_mk,"wb").write(_b64.b64decode(
          "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="))
except Exception: pass
os.chdir(WORK)              # everything the agent does (files, projects) lives here, persistently
def _load_key():
    """Cheia DeepSeek: din variabila de mediu DEEPSEEK_API_KEY (pasa de UI),
    altfel din key.txt (langa agent.py SAU in HOME). NU crapa daca lipseste."""
    for v in ("DEEPSEEK_API_KEY","DS_KEY","API_KEY"):
        if os.environ.get(v,"").strip(): return os.environ[v].strip()
    for p in (os.path.join(os.path.dirname(os.path.abspath(__file__)),"key.txt"),
              os.path.join(HOME_DIR,"key.txt")):
        try:
            t=open(p,encoding="utf-8").read().strip()
            if t: return t
        except Exception: pass
    return ""
K=_load_key()
MEM=os.path.join(HOME_DIR,"memory.md")   # memoria sta in radacina (langa context.json)
if not os.path.exists(MEM) and os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)),"memory.md")):
    try: open(MEM,"w",encoding="utf-8").write(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),"memory.md"),encoding="utf-8").read())
    except Exception: pass
def mem(txt=None):
    if txt is None:
        try: return open(MEM,encoding="utf-8").read().strip()
        except FileNotFoundError: return ""
    open(MEM,"a",encoding="utf-8").write(txt.rstrip()+"\n\n"); return txt


def _mem_norm(s):
    """Normalise a memory bullet for duplicate detection: lowercase, collapse spaces,
    strip trailing punctuation. Two bullets with the same norm are the same fact."""
    import re as _re
    return _re.sub(r"\s+"," ", s.strip().lower()).strip(" .;,:-")

def mem_dups(before, after):
    """Compare the memory BEFORE and AFTER a /learn write and return (new, dup) where:
    new = genuinely new lines ADDED by this update, dup = added lines that repeat a fact
    already present before (same normalised text OR same first 6 significant words).
    Only ADDITIONS are judged - lines that were already there are neither new nor dup.
    A duplicate means /learn added no real lesson: nothing new was learned."""
    def to_bullets(txt):
        return [l.strip() for l in txt.split("\n") if l.strip() and not l.strip().startswith("#")]
    def sig6(l):
        return " ".join(_mem_norm(l).split()[:6])
    b = to_bullets(before)
    b_norm = {_mem_norm(x) for x in b}
    b_sig = {sig6(x) for x in b}
    b_lines = [l.strip() for l in before.split("\n") if l.strip()]
    a = to_bullets(after)
    a_lines = [l.strip() for l in after.split("\n") if l.strip()]
    # ce se afla in after dar NU in before = adaugirile acestui update (multiset)
    import collections as _c
    cnt_before = _c.Counter(_mem_norm(x) for x in b_lines)
    cnt_after = _c.Counter(_mem_norm(x) for x in a_lines)
    added_norm = {x: cnt_after[x]-cnt_before.get(x,0) for x in cnt_after if cnt_after[x]-cnt_before.get(x,0) > 0}
    added = []
    seen = _c.Counter()
    for l in a_lines:
        n = _mem_norm(l)
        if n in added_norm and seen[n] < added_norm[n]:
            added.append(l); seen[n]+=1
    new, dup = [], []
    for l in added:
        n = _mem_norm(l)
        if n in b_norm or sig6(l) in b_sig:
            dup.append(l)
        else:
            new.append(l)
    return new, dup


def _lesson_value(line):
    """Scor de VALOARE 0-10 pentru o lectie de memorie. Ideea: memoria sa creasca doar cu
    lectii care (a) spun o cauza si o consecinta (->), (b) contin detalii specifice
    (numere, Exception/errno, Api.metoda), (c) sunt destul de lungi ca sa fie informative.
    Resping banalitatile ('telefonul are 4 camere') si observatiile fara consecinta.
    Utilizat DOAR cand e strict: < 2 => lectia nu se scrie."""
    import re as _r
    s = 0
    if "->" in line: s += 3                       # are lant cauza -> efect
    if _r.search(r"\d", line): s += 2             # contine valori/numerot concrete
    if _r.search(r"[a-z]+\.[A-Z]\w+", line): s += 2  # nume Api.metoda
    if _r.search(r"\b(ERROR|DENY|DENIED|Exception|errno|ENOENT|EACCES|Permission|SELinux|null|refuses?)\b", line, _r.I): s += 2
    if len(line) < 60: s -= 3                     # prea scurta = probabil banala
    if line.upper().startswith(("OK:", "P:")) and "->" not in line: s -= 2
    if line.upper().startswith(("RULE:", "RULE (")): s += 3   # regula de ordine/decizie = mereu valoroasa
    return s


def mem_lint(txt):
    """Checks EVERY /learn write LINE BY LINE (the prompt's rules, enforced in code):
    - one lesson = ONE line, <=300 chars (the prompt says 150, density warns only on the AVERAGE)
    - no forbidden content: narration, tool calls, dialogue, praise, generic advice, code dumps
    - section heading present and well formed.
    Read-only: it NEVER edits or truncates the file. Returns (warnings, lessons)."""
    import re as _re
    # ★ FIX (bug real 24 sept: /learn a STERS o lectie TRAP de 584 chars de pe disc):
    # MAXLINE era 500 si blocul de ENFORCE de mai jos ELIMINA fizic liniile prea lungi,
    # cu un open(MEM,"w") care rescria tot fisierul. Rezultat: cea mai valoroasa lectie
    # (lant cauza->eroare->fix cu multe detalii) devenea exact cea mai fragila, pentru
    # ca e lunga prin natura ei. Memoria e declarata UNLIMITED, deci lungimea NU e un
    # motiv de stergere. Acum limita urca mult si e DOAR un avertisment de densitate.
    MAXLINE = 2000
    FORBID = [
        (r"\b(am citit|am rulat|am apelat|am folosit tool|tool call)\b", "narration/tool-call"),
        (r"\b(operatorul|utilizatorul a spus|buna seara)\b", "operator dialogue"),
        (r"\b(bravo|excelent|grozav|perfect)\b", "praise"),
        (r"\b(ar trebui|e bine sa|pe viitor incearca)\b", "generic advice"),
        (r"^```|^def |^import ", "code/output dump"),
        # (non-Android topics are now ALLOWED: the agent learns in every domain)
    ]
    out = []
    lines = [l.rstrip() for l in txt.split("\n") if l.strip()]
    heads = [l for l in lines if l.startswith("##")]
    body  = [l for l in lines if not l.startswith(("#", "<!--"))]
    for l in body:
        if len(l) > MAXLINE:
            out.append((len(l), l))
    lessons = [l for l in body if l.startswith(("TRAP:","OK:","DEAD:","P:","PREVENT:","RULE:","RULE (","- ","* "))]
    if len(lessons) > 16:
        out.append((0, "too many lesson lines (" + str(len(lessons)) + ") - possible padding"))
    if not heads:
        out.append((0, "missing heading '## date - area (session: ...)'"))
    else:
        for h in heads:
            if not _re.match(r"^##\s+\d{4}-\d{2}-\d{2}\s+-\s+\S+", h):
                out.append((0, "suspicious heading format: " + h[:60]))
    for l in body:
        for rx, why in FORBID:
            if _re.search(rx, l, _re.I):
                out.append((0, "forbidden [" + why + "]: " + l[:60]))
        # filtru de VALOARE: o linie de lectie prea slaba (banala, fara consecinta) nu intra
        if l.startswith(("TRAP:","OK:","DEAD:","P:","PREVENT:","RULE:","RULE (")) and _lesson_value(l) < 2:
            out.append((0, "low value [" + str(_lesson_value(l)) + "]: " + l[:60]))
    return out, lessons


# MEMORY PHILOSOPHY: the memory file is UNLIMITED in size - there is NO cap, no target, no hard
# limit. Size is never a reason to delete a lesson. It grows ONLY when a genuinely new, reusable
# lesson appears and NEVER to hold duplicates or noise. Quality per line is the only rule that
# matters: one line = one fact that changes future behaviour. A memory with 400 dense lines is
# still cheap (loaded once per session); 400 padded lines is a bug, not a size problem.
MEMSOFT=0            # 0 = disabled: no size target triggers a rewrite any more
MEMHARD=0            # 0 = disabled: no alarm on size; density is enforced per-line, not by a cap
def _real_cols():
    """Terminals sometimes LIE about their width: Alacritty launched from another terminal inherits
    COLUMNS/LINES from its parent and keeps reporting that stale value after a resize (seen live: 57
    columns on a 1920px window, while qterminal reported 210). We then read the X11 window geometry.
    $WINDOWID alone is NOT proof: every child process inherits it, so a shell running inside a small
    window would still see the big window of its grandparent. We therefore accept it ONLY when the
    window has no children of its own that are also terminals, AND an explicit AGENT_COLS always wins."""
    forced=os.environ.get("AGENT_COLS","").strip()   # escape hatch: a known-good width, always wins
    if forced.isdigit(): return int(forced)
    wid=os.environ.get("WINDOWID","").strip()
    if not wid.isdigit(): return 0
    try:
        import subprocess as _sp
        # the window must really be OUR window: the process the terminal started has ppid == the
        # shell's pid, and xdotool reports the pid that owns the window. A mismatch means WINDOWID
        # came from a parent, and the geometry would be the parent's - so we refuse it.
        own=_sp.run(["xdotool","getwindowpid",wid],capture_output=True,text=True,timeout=2).stdout.strip()
        mine=str(os.getppid())
        if own and mine and own!=mine:
            sib=_sp.run(["pgrep","-P",own],capture_output=True,text=True,timeout=2).stdout.split()
            if str(os.getpid()) not in sib: return 0   # the window does not host this process
        t=float(os.environ.get("AGENT_CELLPX","8.4"))   # average cell width in px at a normal font
        g=_sp.run(["xdotool","getwindowgeometry",wid],capture_output=True,text=True,timeout=2).stdout
        m=re.search(r"Geometry:\s*(\d+)x(\d+)",g)
        if not m: return 0
        return max(20,int(int(m.group(1))/t))
    except Exception:
        return 0
        told=int(shutil.get_terminal_size((80,24)).columns)
        return est if est>told else 0     # only useful when it is BIGGER; never shrink a correct report
    except Exception:
        return 0
def CS():
    """Terminal width in columns, read per line so a resize is picked up at once. If the terminal
    reports a width that contradicts the real window geometry (the Alacritty/COLUMNS bug), we
    trust the geometry: better a slightly approximate table than a table crushed into 57 columns."""
    try: w=int(shutil.get_terminal_size((80,24)).columns)
    except Exception: w=80
    r=_real_cols()
    # a honest terminal is within ~30% of the geometry we compute; anything beyond that is not our
    # window (a WINDOWID inherited from a parent, another workspace, a stale value). 4x is the hard
    # ceiling: it can still rescue the Alacritty bug (57 -> 210) without ever exploding the layout.
    if r and w < r-15 and r <= w*4:
        return r
    return w
LBLW=lambda: max(18,min(24,CS()-40))   # label box: tighter, so the timers/log/status sit close to the text
DURW=7   # widest _dur() value: "1:00:00" (7 chars)
REFW=10  # widest log file name in the step line (longer names end with …)
SZW=8    # width of the output-size box (and of the phase box in the live line)
TOOLMAX=int(os.environ.get("AGENT_TOOLMAX","8000"))   # how much of a tool output stays IN THE WINDOW (head+tail); the rest goes to disk, with a pointer
# CHUNK: the budget per tool call, in characters. It raises the window limit above TOOLMAX so a
# deliberate long read is not decapitated in the middle. AGENT_CHUNK=0 keeps the old TOOLMAX behaviour.
CHUNK=int(os.environ.get("AGENT_CHUNK","60000"))
BUDGETWARN=float(os.environ.get("AGENT_BUDGETWARN","0.9"))   # warn once per task above this share of CHUNK
BUDGETWARNED=[False]   # re-armed at the start of every task, so it cannot repeat in the same task
# The model's REAL context window. VERIFIED against the API, not guessed:
#   GET https://api.deepseek.com/models -> deepseek-flash: context_window=1048576 (1M)
#   A hardcoded 128000 here caused a FALSE "125% of the window" warning at ~15% real usage.
CTXWINDOW=int(os.environ.get("AGENT_CTXWINDOW","1048576"))   # 1M tokens, confirmed by the API
CTXWARN=int(os.environ.get("AGENT_CTXWARN","90"))            # warn (RED, loud) at this % of the window
CTXBUDGET=0   # COMPRESSION IS DISABLED, by the operator's explicit decision: no automatic
#   compaction and none via /compact. The context grows until **the operator** gives /reset, so the
#   MEMORY block inserted at startup stays present, byte for byte, for the ENTIRE session.
CTXKEEP=24         # how many recent messages are never compressed
LOGDIR=os.path.join(WORK,"logs")      # complete tool outputs (not deleted between sessions)
ARCH=os.path.join(WORK,"archive")     # COMPLETE snapshots of the history, before every compression
VERBOSE=[os.environ.get("AGENT_VERBOSE")=="1"]   # /verbose: re-prints code + output in the terminal
NOSPIN=[os.environ.get("AGENT_NOSPIN")=="1"]     # /nospin: NO live/redrawn line at all (clean scrollback on a phone)
THINKMIN=float(os.environ.get("AGENT_THINKMIN","0"))   # MINIMUM time "Thinking..." stays on screen (0 = the printed time is exactly the measured one). It never delays a tool step.
def _budget():
    """How much of a tool output fits IN THE WINDOW for this call. CHUNK raises it above TOOLMAX so a
    deliberate long read is not decapitated; AGENT_CHUNK=0 falls back to the old TOOLMAX behaviour."""
    return CHUNK if CHUNK and CHUNK>TOOLMAX else TOOLMAX
def _cut(o,ref=None,complete=False):
    """What goes INTO THE WINDOW: the first 3/4 of the budget + the last 1/4 (the tail is where the
    tracebacks and the conclusion show up), plus a POINTER to the complete text on disk.
    `complete` says whether the pointer REALLY holds the whole text (see _store): if it does not,
    the marker says so instead of promising a file that is itself cut."""
    b=_budget()
    if len(o)<=b: return o
    h,t=b*3//4,b//4
    _hidden=str(len(o)-b)
    if ref and complete:
        mid=("[... "+_hidden+" chars omitted here (NOT LOST). Read them with: "
             +"read path="+ref+" offset="+str(h)+" limit="+str(b)+" ...]")
    elif ref:
        mid=("[... "+_hidden+" chars omitted here, LOST (the log "+ref+" is itself truncated) - "
             +"RE-RUN the step in smaller parts ...]")
    else:
        mid=("[... "+_hidden+" chars omitted here, LOST (no log was written) - RE-RUN the step in smaller parts ...]")
    return o[:h]+"\n"+mid+"\n"+o[-t:]
def _store(o):
    """Writes the COMPLETE output into a log on disk and returns (what enters the window, path|None).
    The file is written in full and then VERIFIED by size; the marker only says NOT LOST when the file
    on disk really holds every byte."""
    b=_budget()
    if len(o)<=b:
        # Preventive warning, ONCE PER TASK: the output still fits, but one step like this bigger and the
        # middle is gone. Said now, while it can still be acted on (chunk it / use the `read` tool).
        if len(o)>b*BUDGETWARN and not BUDGETWARNED[0]:
            BUDGETWARNED[0]=True
            print(OF+"   [budget] this step returned "+str(len(o))+" chars, close to the "+str(b)+
                  "-char limit - one step bigger loses its middle. Split it or use the `read` tool."+N)
        return o,None
    os.makedirs(LOGDIR,exist_ok=True)
    p=os.path.join(LOGDIR,"tool_"+datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")+".log")
    complete=False
    try:
        with open(p,"w",encoding="utf-8") as f: f.write(o)
        complete=(os.path.getsize(p)==len(o.encode("utf-8")))
    except Exception:
        return _cut(o,None,False),None
    return _cut(o,os.path.relpath(p,WORK),complete),p
def _tokm(m):
    s=str(m.get("content") or "")
    for tc in (m.get("tool_calls") or []): s+=str((tc.get("function") or {}).get("arguments") or "")
    return len(s)//4
def ctx_tokens(): return sum(_tokm(m) for m in M)
CTXWINDOW_VERIFIED=[False]
def ctx_check_window():
    """Asks the API what the model's context window REALLY is and corrects CTXWINDOW if the local
    constant is wrong. A hardcoded window produced a false '125% of the window' warning at ~15% real
    usage. One cheap call at startup, cached for the session; if the network fails the local constant
    stays - it never blocks the startup."""
    global CTXWINDOW
    if CTXWINDOW_VERIFIED[0]: return
    CTXWINDOW_VERIFIED[0]=True
    try:
        r=urllib.request.Request("https://api.deepseek.com/models",headers={"Authorization":"Bearer "+K})
        d=json.loads(urllib.request.urlopen(r,timeout=20).read())
        mid=os.environ.get("DS_MODEL","deepseek-flash")
        for m in (d.get("data") or []):
            if m.get("id")==mid:
                w=int(m.get("context_window") or 0)
                if w and w!=CTXWINDOW:
                    print(OF+"   [ctx] the API reports a "+_K(w)+" window for "+mid+" (local was "+_K(CTXWINDOW)+") - corrected."+N)
                    CTXWINDOW=w
                break
    except Exception:
        pass
CTXWARNED=[False]
def ctx_warn():
    """LOUD RED warning when the context approaches the model window. It does NOT compress, does NOT
    touch the history and does NOT stop anything - it only tells the operator it is time for /reset.
    Fires once per crossing, so it cannot spam every round."""
    pct=100.0*ctx_tokens()/CTXWINDOW if CTXWINDOW else 0.0
    if pct>=CTXWARN:
        if not CTXWARNED[0]:
            CTXWARNED[0]=True
            bar="\u2588"*40
            print("\n"+R+"   "+bar+N)
            print(R+"   \u26a0 CONTEXT AT "+("%.0f"%pct)+"% OF THE WINDOW ("+_K(ctx_tokens())+"/"+_K(CTXWINDOW)+" tok)"+N)
            print(R+"   \u26a0 Time to /reset: the next requests may be rejected by the API."+N)
            print(R+"   \u26a0 I did NOT compress or delete anything - the memory stays intact."+N)
            print(R+"   "+bar+N+"\n")
    elif pct<CTXWARN-10:
        CTXWARNED[0]=False
# Compactarea automata e OPIRTA (decizie operator). Istoricul ramane complet viu.
CTXAUTO=0   # 0 = niciodata compactare automata
def compact_history(force=False):
    """COMPACTAREA AUTOMATA E OPRIATA (decizie operator: nu vrea sa vada notificari
    [ctx] fereastra ... referinte ... archive, si istoricul complet sa ramana viu).
    Nu arhiveaza, nu inlocuieste nimic, nu afiseaza nimic. Ramane doar ca sa nu
    fie nevoie sa schimbam cele ~4 locuri care o cheama (no-op instant)."""
    return 0
def _compact_history_DISABLED(force=False):
    """The old lossless compression, kept for reference only - never called."""
    """LOSSLESS COMPRESSION. When the live window goes over CTXBUDGET tokens:
    1) the COMPLETE history is archived (untouched) in archive/ctx_<date>.json;
    2) the window keeps stubs with a POINTER to the archive (message index, size, start/end),
       so the original text can be read at any time with a tool call.
    No message is removed from the list (the API requires every tool_call to have its answer)."""
    lim=len(M)-CTXKEEP
    if lim<=0: return 0
    if not force and (CTXBUDGET<=0 or ctx_tokens()<=CTXBUDGET): return 0   # threshold 0 = automatic compression disabled; /compact works at any time
    before=ctx_tokens()
    os.makedirs(ARCH,exist_ok=True)
    p=os.path.join(ARCH,"ctx_"+datetime.datetime.now().strftime("%Y%m%d-%H%M%S")+".json")
    try:
        json.dump(M[1:],open(p,"w",encoding="utf-8"),ensure_ascii=False,indent=1)
        ref=os.path.relpath(p,WORK)
    except Exception as e:
        print(R+"   [ctx] could not archive the history ("+str(e)+") - I do NOT compress, so I do not lose context."+N); return 0
    n=0
    for i,m in enumerate(M[:lim],1):
        c=str(m.get("content") or "")
        if m.get("role")=="tool" and len(c)>TOOLMAX//8:
            L=[x for x in c.strip().split("\n") if x.strip()] or [""]
            m["content"]=("[complete output, untouched: "+ref+" #"+str(i-1)+" ("+str(len(c))+" chars)]\n"+L[0][:70]+"\n...\n"+L[-1][-60:])
            n+=1
        for tc in (m.get("tool_calls") or []):
            f=tc.get("function") or {}; arg=str(f.get("arguments") or "")
            if len(arg)>300:
                f["arguments"]=json.dumps({"code":"[complete code, untouched: "+ref+" #"+str(i-1)+" ("+str(len(arg))+" chars)]"}); n+=1
    after=ctx_tokens()
    print(G+"   [ctx] window "+_K(before)+"tok -> "+_K(after)+"tok | "+str(n)+" references | complete original: "+ref+N)
    return after<before
SPIN=("⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏")
# ---------------- task UI: one timer for the WHOLE task + labelled steps ----------------
TASK={"t0":None,"n":0,"steps":0,"think":0.0,"tool":0.0,"chars":0,"tok_in":0,"tok_out":0,"cache":0,"err":False}   # one "task" = one operator request
LIVE={"phase":"idle","desc":"","col":None,"n":0,"t":0.0,"dt":0.0}              # what the live line is printing right now
def _clk(t):
    """Seconds -> mm:ss (or h:mm:ss above an hour); used for the timings in the UI."""
    t=max(0.0,float(t)); h,rest=divmod(int(t),3600); m,s=divmod(rest,60)
    return ("%d:%02d:%02d"%(h,m,s)) if h else ("%02d:%02d"%(m,s))
def _dur(t):
    """Readable duration, ALWAYS the real measured one: only a truly instant operation (under 50ms,
    e.g. a tiny file read) is shown as "<0.05s", everything else shows its real time with one decimal
    (0.1s, 0.8s, 12.3s), mm:ss above a minute. No rounding up, no floor."""
    t=max(0.0,float(t))
    if t<0.05: return "<0.05s"
    return ("%.1fs"%t) if t<60 else _clk(t)
def _short(s,n=60):
    """A single line, no double spaces, cut with … at n characters."""
    s=re.sub(r"\s+"," ",str(s)).strip().rstrip(".");return s if len(s)<=n else s[:n-1].rstrip()+"…"

def _op_of(code):
    """Classifies what THIS step REALLY does, straight from the tool code, into short English
    families. Two texts are used: `tcode` (code without comments) and `tnostr` (code with the
    content of every string removed). A word like "grep" inside a message, a file name or a
    comment is NOT a command - so generic keywords are matched against `tnostr` only, and the
    label can never claim something the step does not do."""
    t=code or ""
    body=[l.strip() for l in t.split(chr(10)) if l.strip() and not l.strip().startswith("#")]
    tcode=chr(10).join(re.sub(r"#.*$","",l) for l in t.split(chr(10)))
    tnostr=re.sub(r"""[\x22\x27]{3}(?:.|\n)*?[\x22\x27]{3}""","\"\"",tcode)   # drop triple-quoted blocks first
    tnostr=re.sub(r"""[\x22\x27][^\x22\x27\n]*[\x22\x27]""","\"\"",tnostr)   # then every single/double quoted string
    tnostr=re.sub(r"\x27(?:[^\x27\\]|\\.)*\x27","\"\"",tnostr)   # single-quoted strings with escapes
    tnostr=re.sub(r"\x22(?:[^\x22\\]|\\.)*\x22","\"\"",tnostr)   # double-quoted strings with escapes
    paths=re.findall(r"""['"]([A-Za-z0-9_./~+ -]+[.][A-Za-z0-9]{1,6})['"]""",t)
    fn=os.path.basename(paths[0]) if paths else ""
    def hit(*pats): return any(re.search(pat,tcode) for pat in pats)
    def hitc(*pats): return any(re.search(pat,tcmd,re.M) for pat in pats)   # commands only: words inside strings/text do not count
    tcmd=chr(10).join(l for l in tnostr.split(chr(10)) if re.match(r"\s*(?:import\s+subprocess|from\s+subprocess|subprocess|os[.]system|print\s*\(\s*[\x22\x27]?\s*(?:ffmpeg|xwd|grep|ls|df|du|ps)\b)",l))
    # --- shell: a REAL call, and the binary is taken from the call itself when possible ---
    if hit(r"subprocess[.](?:run|call|check_output|check_call|Popen)\s*\(", r"os[.]system\s*\(") or hitc(r"(?:^|[\s;&|(])uname(?:[\s;&|)]|$)", r"(?:^|[\s;&|(])chmod(?:[\s;&|)]|$)", r"(?:^|[\s;&|(])apt-get\b", r"(?:^|[\s;&|(])pip3?\b", r"(?:^|[\s;&|(])curl\b", r"(?:^|[\s;&|(])wget\b", r"(?:^|[\s;&|(])grep\b", r"(?:^|[\s;&|(])ffmpeg\b", r"(?:^|[\s;&|(])xwd\b", r"(?:^|[\s;&|(])df\b", r"(?:^|[\s;&|(])du\b", r"(?:^|[\s;&|(])systemctl\b"):
        ex=re.search(r"subprocess[.](?:run|call|Popen|check_output|check_call)\s*\([^)]*?[\x22\x27]([\w./~+-]+)",t)
        if not ex: ex=re.search(r"os[.]system\s*\([\x22\x27]([\w./~+-]+)",t)
        return "runs "+((ex.group(1)+" command") if ex else "a shell command")
    if hitc(r"\bunittest\b", r"\bpytest\b", r"\bassert\b"): return "checks"+((" "+fn) if fn else "")
    # --- destructive / moving / creating ---
    if hit(r"rmtree", r"os[.]remove", r"os[.]unlink", r"os[.]rmdir"): return "deletes"+((" "+fn) if fn else " on disk")
    if hit(r"os[.]rename", r"os[.]replace", r"shutil[.]move", r"shutil[.]copy"): return "moves"+((" "+fn) if fn else " files")
    if hit(r"makedirs", r"os[.]mkdir"):
        mx=re.search(r"mkdirs?\s*\([\x22\x27]([^\x22\x27]+)",t)
        return "creates the folder"+((" "+os.path.basename(mx.group(1))) if mx and mx.group(1) else "")
    # --- writing WINS over reading: an explicit write mode or a real write call ---
    if hit(r"[.]write\s*\(", r"json[.]dump", r"[.]writelines\s*\(", r"csv[.]writer"):
        return "writes"+((" "+fn) if fn else " a file")
    wm=re.search(r"open\s*\([^)]*?[\x22\x27]([^\x22\x27]+)[\x22\x27]\s*,\s*[\x22\x27]([wartx+]{1,2})b?[\x22\x27]",t)
    if wm and any(c in wm.group(2) for c in "wax+"): return "writes "+os.path.basename(wm.group(1))
    # --- inspecting metadata / listing / reading / searching / API ---
    if hit(r"os[.]stat", r"os[.]path[.]getsize", r"st_mtime", r"st_size"): return "inspects"+((" "+fn) if fn else " the files")
    if hit(r"os[.]listdir", r"os[.]walk", r"glob[.]") and not hit(r"[.]read\s*\("): return "lists the folder"
    if hit(r"urllib", r"requests[.]", r"urlopen", r"socket[.]", r"http://", r"https://"): return "queries the API"
    if hit(r"open\s*\(", r"[.]read\s*\(", r"[.]readlines", r"[.]readline", r"json[.]load"): return "reads"+((" "+fn) if fn else " the files")
    if hit(r"re[.](?:search|findall|finditer|match|fullmatch)"): return "searches the text"+((" for "+fn) if fn else "")
    if paths: return "works on "+fn
    if body: return "computes in python"
    return "runs python"
def phrase_op(op=""):
    """Operation family -> short English phrase for the FINISHED step: 'read agent.py',
    'searched for config.json', 'ran a shell command' - same classification as the live line."""
    low=_short(op or "",60).lower(); tok=low.split(" ")
    verb=tok[0] if tok else ""
    tbl={"command":"ran a shell command","checks":"ran the checks","deletes":"deleted","moves":"moved",
         "directories":"created the folders","lists":"listed the folder","queries":"queried the API",
         "uses":"opened the data","inspects":"inspected","writes":"wrote","reads":"read",
         "searches":"searched for","works":"worked on","runs":"ran","computes":"computed in python"}
    ph=tbl.get(verb)
    if not ph: return low or "step"
    drop=("the","a","an","for","on","in","files","file","folder","disk","api","python","text","data","and","shell","command","lines")
    keep=[w.strip("(),.") for w in tok[1:] if re.match(r"^[\w./~+-]+$",w.strip("(),.")) and w.strip("(),.").lower() not in drop]
    if not keep: return ph
    if verb in ("runs","reads","writes","deletes","searches","uses","works"): return ph+" "+keep[0]
    return ph

def brief(code):
    """The EXACT short English description of a step, derived from its own code: the same function feeds
    the live line while the step runs and the final line when it is over, so they always agree."""
    return _op_of(code).rstrip(".").strip()   # FULL text: no truncation, the whole description is shown
def _task_head(q=""):
    """Opens a task: the timer starts HERE and does not stop until the final answer.
    Prints the operator line "You > <message>", one blank line, then the TASK box."""
    TASK.update(t0=time.time(),steps=0,think=0.0,tool=0.0,chars=0,tok_in=0,tok_out=0,cache=0,n=TASK["n"]+1,err=False)
    BUDGETWARNED[0]=False   # fresh task: the budget warning may fire once again
    LIVE.update(phase="think",desc="",col=None,n=0,t=time.time())
    t=" TASK #"+str(TASK["n"])+" "
    w=len(t)+6   # a little wider than the text (a few dashes of air), still compact
    pad=w-len(t)   # so the right border lines up with the top/bottom borders
    box=[BAR+"╭"+"─"*w+"╮"+N,
         BAR+"│"+N+ST+t+N+" "*pad+BAR+"│"+N,
         BAR+"╰"+"─"*w+"╯"+N]
    who = (U+" You > "+N+ST+q) if q else ""
    return who+"\n\n"+"\n".join(box)+"\n\n"+N   # message, blank line, box, then blank line
def media_rescan():
    """Reindexeaza folderul de lucru in MediaStore, ca fisierele create de agent sa apara
    IMEDIAT in My Files / file manager (altfel raman invizibile pana la urmatorul scan de sistem).
    Ruleaza in background, nu blocheaza si nu da eroare daca nu e disponibil."""
    def _run():
        try:
            import subprocess as _sp
            _sp.run(["content","call","--uri","content://media/","--method","scan_volume","--arg","external"],
                    stdout=_sp.DEVNULL,stderr=_sp.DEVNULL,timeout=5)
        except Exception: pass
    try:
        import threading as _th
        _th.Thread(target=_run,daemon=True).start()
    except Exception: pass
def _task_foot(stare="done"):
    media_rescan()   # fisierele noi devin vizibile in file manager
    """Closes the task: stops the timer and breaks down the total (thinking vs. tool) + the steps + the TOKENS
    consumed by this task, taken from the server usage accumulated in TASK since _task_head()."""
    tot=(time.time()-TASK["t0"]) if TASK["t0"] else 0.0
    LIVE.update(phase="idle",desc="",col=None,n=0)
    ph=TASK["think"]+TASK["tool"]
    other=max(0.0,tot-ph)   # time NOT covered by any _spin: HTTP request, parsing, compact_history/save_ctx, rounding
    # Footer MINIMAL: doar "TASK #N done" + steps + total. Tokenii se afiseaza
    # separat, in blocul de la flush_task_tokens (tok / session tok).
    b=G+"  ·  "+str(TASK["steps"])+(" step" if TASK["steps"]==1 else " steps")+"  ·  total "+C+_dur(tot)+N
    return BAR+"  +-"+N+ST+" TASK #"+str(TASK["n"])+" "+stare+N+b

# ==================== MONITOR DE STATUS (0 tokeni, fara API) ====================
# DE CE EXISTA: operatorul a intrebat daca putem verifica statusul la fiecare minut.
# Daca asta s-ar face PRIN API (agentul cheama un tool), fiecare check ar retrimite TOT
# contextul: 30 de check-uri = ~255.000 tokeni INPUT. Inutil de scump.
# Solutia: un THREAD LOCAL care citeste registrul bg.json si scrie o linie pe ECRAN.
# 0 cereri API, 0 tokeni, 0 impact pe context. Se activeaza cu /watch on (sau AGENT_WATCH=1).
WATCH = {"on": os.environ.get("AGENT_WATCH") == "1", "sec": int(os.environ.get("AGENT_WATCH_SEC", "60") or 60)}

def _watch_snapshot():
    """One status line per RUNNING background job, read from bg.json - no API, no context.
    Returns [] when nothing runs (so the caller prints nothing and stays quiet)."""
    try:
        reg = _bg_load()
    except Exception:
        return []
    out = []
    for jid, j in (reg or {}).items():
        if j.get("status") != "running":
            continue
        pid = j.get("pid", 0)
        alive = "?"
        try:
            ok = run_adbsh_tool("test -d /proc/%d && echo A || echo D" % pid, 20).strip()
            alive = "RUNNING" if "A" in ok else "DONE"
        except Exception:
            pass
        dur = int(time.time() - j.get("ts", time.time()))
        sz = "?"
        try:
            sz = run_adbsh_tool("wc -c < %s 2>/dev/null || echo 0" % j["log"], 20).strip().split()[0]
        except Exception:
            pass
        out.append((jid, alive, pid, dur, sz))
    return out

def _watch_loop():
    """Writes one compact line every WATCH['sec'] seconds, ONLY while something runs.
    Prints to stdout (the app terminal), never to the model context."""
    last = ""
    while not WATCH.get("stop"):
        time.sleep(max(10, int(WATCH.get("sec", 60))))
        if not WATCH.get("on"):
            continue
        try:
            rows = _watch_snapshot()
        except Exception:
            continue
        if not rows:
            continue                      # nothing running: stay silent (no noise)
        line = "  ".join("%s %s %ds %sB" % (jid.split("_")[0], a, d, s) for jid, a, p, d, s in rows)
        if line != last:
            last = line
        try:
            print("\r\33[K" + SD + "\u23f1 watch " + N + G + line + N, flush=True)
        except Exception:
            pass

def _watch_start():
    if WATCH.get("thread"):
        return
    WATCH["stop"] = False
    th = threading.Thread(target=_watch_loop, daemon=True)
    WATCH["thread"] = th
    th.start()

def _live(i):
    """The live line, rewritten in place while the step runs. SIMPLE design:
    spinner + "Thinking..." (or "Running...") + the label of the work + the task clock.
    The phase is carried by the COLOUR and the word, never by a second column."""
    think=LIVE.get("phase")=="think"
    if think:
        # THINKING: NO seconds at all (they are meaningless while we wait for the model),
        # just the spinner + the word inside a violet box.
        box="[ "+SPIN[i%len(SPIN)]+" Thinking... ]"
        return "  "+MOV+box+N   # ONE line ONLY: _spin redraws it with \r, so no newline is allowed here
    cur=_dur(time.time()-LIVE["t"]) if LIVE.get("t") else "0.0s"   # REAL time of THIS step, measured from LIVE["t"] (set in _spin)
    st="  "+GY+SPIN[i%len(SPIN)]+N+" "+GY+"Running..."+N
    lbl=_lbl()
    if lbl and lbl.strip("- "): st+="  "+lbl+N
    st+="  "+SD+"\u23f1"+N+" "+GY+cur+N
    return _clamp(st)

def _clamp(s):
    """Android: a line longer than the terminal wraps onto a second row, and a LIVE
    line redrawn with \r then smears the scrollback when the operator scrolls up. So the live
    line is HARD-CLAMPED to (width-1) visible columns. Control sequences (\33[...m colours)
    are skipped while counting, so the colour codes never get cut in the middle."""
    try: w=os.get_terminal_size().columns
    except Exception: return s
    if w<=8: return s
    lim=w-1
    out=[]; vis=0; i=0; n=len(s)
    while i<n:
        if s[i]=="\33":
            j=i+1
            # copy the whole escape sequence untouched
            while j<n and not ("A"<=s[j]<="Z" or "a"<=s[j]<="z"):
                j+=1
            out.append(s[i:j+1]); i=j+1; continue
        if vis>=lim: break
        out.append(s[i]); vis+=1; i+=1
    return "".join(out)+("\33[0m" if "\33" in s else "")
def _lbl(col=False):
    """The exact label of the RUNNING step, with its own colour. Written once by _spin and reused by the
    final line, so the live line and the finished line can never show different words."""
    if LIVE.get("phase")=="think": return "" if not col else SD+"-"*6+N
    txt,colr=LIVE["desc"] or "working",LIVE["col"] or G
    return (colr+txt+N) if col else txt
def _spin(fn,*a,phase="tool",desc="",col=None):
    """Runs the operation with the live line instead of code/output: 'step NN - thinking' while we wait for
    the model answer, 'step NN - <what the step really does>' once the tool runs. One line, no flicker."""
    if phase: LIVE.update(phase=phase,desc=desc,col=col,n=TASK["steps"]+1,t=time.time())
    t0=time.time()
    if VERBOSE[0] or NOSPIN[0] or not sys.stdout.isatty():
        r=fn(*a); dt=time.time()-t0; LIVE["dt"]=dt
        if phase=="think": TASK["think"]+=dt
        elif phase=="tool": TASK["tool"]+=dt
        return r
    stop=threading.Event()
    drawn=[0]
    def loop():
        i=0
        while not stop.is_set():
            print("\r"+_live(i)+"\33[K",end="",flush=True); i+=1; drawn[0]+=1; stop.wait(0.1)
    th=threading.Thread(target=loop,daemon=True); th.start()
    try:
        r=fn(*a); dt=time.time()-t0; LIVE["dt"]=dt
        if phase=="think": TASK["think"]+=dt
        elif phase=="tool": TASK["tool"]+=dt
        return r
    finally:
        stop.set(); th.join(timeout=0.4); LIVE.update(phase="idle",n=0)
        if drawn[0]: print("\r\33[K",end="",flush=True)   # only if a frame was drawn: never eat an unused line
def run_tool(code):
    """Runs the step and returns what gets sent to the model (the CUT output). In the terminal, in compact mode:
    the live line while it runs, then ONE line: the status dot (GREEN = OK, RED = FAIL), the step number,
    what the step really did and, in RED, how long it took (plus a pointer to the log when it was written)."""
    n=TASK["steps"]+1; dsc=brief(code); col=HCLR[sum(map(ord,dsc))%len(HCLR)] if dsc else G
    o=_spin(py,code,os.getcwd(),phase="tool",desc=dsc,col=col); cut,ref=_store(o)
    TN[0]+=1; TASK.update(steps=n,chars=TASK["chars"]+len(o))
    _show_step(code,cut,n)   # ALWAYS: the first NLINES lines of the code and of the output
    if _looks_like_error(o): TASK["err"]=True
    return cut
NLINES=10   # how many lines of code and of output are shown for EVERY step (compact and verbose)
def _fisier(code):
    """The FILE or FOLDER the step works on, taken from its own code:
    open("x.py"), p="x.py" + open(p), os.makedirs("temp/x"). A folder ends with "/".
    Empty string when the step touches no file at all (a plain computation, a print...)."""
    if not code: return ""
    m=re.search(r"""os[.](?:makedirs|mkdir)\s*[(]\s*['"]([^'"]+)['"]""", code)
    if not m: m=re.search(r"""shutil[.]rmtree\s*[(]\s*['"]([^'"]+)['"]""", code)
    if not m: m=re.search(r"""os[.]rmdir\s*[(]\s*['"]([^'"]+)['"]""", code)
    if m: return m.group(1).rstrip("/").split("/")[-1]+"/"
    var={}
    for x in re.finditer(r"""([A-Za-z_]\w*)\s*=\s*['"]([A-Za-z0-9_./~+-]+[.][A-Za-z0-9]{1,6})['"]""", code):
        var[x.group(1)]=x.group(2)
    m=re.search(r"""open[(]\s*(?:['"]([A-Za-z0-9_./~+-]+[.][A-Za-z0-9]{1,6})['"]|([A-Za-z_]\w*))""", code)
    if m:
        n=m.group(1) or var.get(m.group(2),"")
        if n: return n.split("/")[-1]
    m=re.findall(r"""['"]([A-Za-z0-9_./~+-]+[.][A-Za-z0-9]{1,6})['"]""", code)
    if m: return m[0].split("/")[-1]
    return ""
def _operatie(code):
    """WHAT the step does to the file: reads / writes / appends / mkfld / deletes / moves.
    Taken from the code itself (the open() mode, os.makedirs, os.remove, shutil.move)."""
    if not code: return ""
    if re.search(r'os\.(makedirs|mkdir)\s*\(', code): return "mkfld"
    if re.search(r'os\.(remove|unlink|rmdir)\s*\(|shutil\.rmtree\s*\(', code): return "deletes"
    if re.search(r'shutil\.(move|copy|copy2|copyfile)\s*\(', code): return "moves"
    if "open(" not in code: return ""
    mod=re.search(r"""open\([^)]*?,\s*['"]([rwaxb+]{1,2})['"]""", code)
    m=mod.group(1) if mod else "r"
    if m.startswith("a"): return "appends"
    if m.startswith(("w","x","+")) or ".write(" in code: return "writes"
    return "reads"

def _step_line(code,n):
    """ONE line per step, compact: the step number in a calm slate tone, then - in the TOOL colour
    (amber, TC), clearly different from the grey/teal of the rest - the name of the tool that was
    called, wrapped in [brackets], and what the call did to which file."""
    op=_operatie(code) or "runs python"
    fis=_fisier(code)
    call=TC+"["+("python" if op else "tool")+"]"+N
    what=TCB+" "+op+(" "+fis+"" if fis else "")+" "+N
    return BAR+"   +-- "+N+SB+"step "+str(n).zfill(2)+N+" "+call+" "+what+"  "+SD+"\u23f1"+N+" "+G+_dur(LIVE["dt"])+N

def _show_step(code,cut,n):
    """COMPACT mode: ONE tool line per step - the highlighted tool call (tool name + action +
    file) and the duration; the code and the output are NOT printed (they stay in the log file).
    VERBOSE mode (/verbose): the whole code and the whole output, with the code in its own colour."""
    if not VERBOSE[0]:
        print(_step_line(code,n))
        return
    print(_step_line(code,n))
    for l in (code.split("\n") if code else []):
        print(BAR+"   | "+N+Y+l+N)
    print(BAR+"   +-- output "+N+BAR+"-"*32+N)
    for l in (cut.rstrip("\n").split("\n") if cut.strip() else []):
        print(BAR+"   | "+N+V+l[:200]+N)
    print(BAR+"   +"+N+BAR+"-"*46+N)
def mstats(s):
    """characters, ~tokens (chars/4), number of LESSON lines, characters per lesson - so you can see
    the memory density. A lesson line is any non-empty line that is not a section heading (## ...),
    not a comment, and not a bare label: it counts lines starting with TRAP:/OK:/DEAD:/P:/PREVENT:- or '- '."""
    lines=[l.strip() for l in s.split("\n") if l.strip()]
    nb=len([l for l in lines if not l.startswith(("#","<!--")) and (
        l.startswith(("TRAP:","OK:","DEAD:","P:","PREVENT:","RULE:","RULE (","- ","* ")) or (":" in l[:12] and not l.startswith("##")))])
    return len(s),len(s)//4,nb,(len(s)//nb if nb else 0)
LEARN_TAG="[[MEMORY-UPDATE]]"
# ★ CHECKPOINT /LEARN (24 sept: implementat la cererea operatorului).
# Problema rezolvata: la fiecare /learn se re-citea toata sesiunea => lectii deja invatate erau
# rescrise din alte unghiuri (near-duplicate), memoria se umfla inutil. Solutia: un fisier JSON
# care retine la ce INDEX din istoric s-a facut fiecare /learn. La /learn nou se invata DOAR
# mesajele de dupa ULTIMUL checkpoint (nu tot, nu de la 0) => zero re-procesare, zero duplicate.
# Checkpoint-urile vechi raman pentru audit: se vede exact ce interval a acoperit fiecare /learn.
LEARN_CKPT=os.path.join(HOME_DIR,".learn_checkpoints.json")   # in HOME_DIR (nu in _SANDBOX, care e folderul scriptului)

def _learn_ckpts():
    """Lista de checkpointuri (indici de mesaj) la care s-a rulat /learn, in ordine."""
    try:
        d=json.load(open(LEARN_CKPT,encoding="utf-8"))
        if isinstance(d,list): return [int(x) for x in d]
    except Exception: pass
    return []

def _learn_ckpt_save(idx):
    """Adauga un checkpoint nou (indexul curent) si scrie fisierul. Pastreaza doar istoricul."""
    ck=_learn_ckpts(); ck.append(int(idx))
    try:
        # scriere atomica (tmp+replace) ca sa nu se corupa la intrerupere
        tmp=LEARN_CKPT+".tmp"
        with open(tmp,"w",encoding="utf-8") as f: json.dump(ck,f)
        os.replace(tmp,LEARN_CKPT)
    except Exception as e: print(R+" [learn] nu am putut salva checkpointul: "+str(e)+N)
    return ck

def last_learn_idx():
    """De la ce index sa invete /learn acum: ULTIMUL checkpoint salvat (sau 0 daca nu exista).
    Asa fiecare /learn acopera DOAR mesajele noi de la ultimul checkpoint => fara re-procesare
    si fara near-duplicate. Daca istoricul a fost compactat (indici mai mici decat checkpointul),
    revenim la 0 ca sa nu pierdem lectii."""
    ck=_learn_ckpts()
    if not ck: return 0
    last=ck[-1]
    # istoric compactat/trunchiat intre timp => indexul nu mai e valid, reanalizam tot
    if last>len(M): return 0
    return last
# --- tech-flavour words for the step labels: random order per task, one colour per term ---
# --- SOFT PALETTE (eye-friendly): medium, desaturated 256-colour tones, NO bold.
# luma of every entry sits between ~145 and ~195 on a dark background: readable, but no glare.
HCLR=("\x1b[38;5;109m","\x1b[38;5;110m","\x1b[38;5;144m","\x1b[38;5;146m","\x1b[38;5;180m",
 "\x1b[38;5;181m","\x1b[38;5;216m","\x1b[38;5;215m","\x1b[38;5;139m","\x1b[38;5;175m",
 "\x1b[38;5;108m","\x1b[38;5;187m","\x1b[38;5;223m","\x1b[38;5;222m","\x1b[38;5;158m",
 "\x1b[38;5;145m","\x1b[38;5;152m","\x1b[38;5;116m","\x1b[38;5;114m","\x1b[38;5;150m",
 "\x1b[38;5;179m","\x1b[38;5;186m","\x1b[38;5;173m","\x1b[38;5;138m","\x1b[38;5;147m")
# --- step labels: generated LIVE from the task text, one colour per term ---
U=E+"[38;5;110m";IN=E+"[38;5;150m";G=E+"[38;5;146m";FR=E+"[38;5;108m";Y=E+"[38;5;223;48;5;238m"
UPROMPT="  "
V=E+"[38;5;245m";R=E+"[38;5;179m";N=E+"[0m";C=E+"[38;5;109m";OF=E+"[38;5;180m"
SB=E+"[38;5;180m";ST=E+"[38;5;114m";SD=E+"[38;5;243m";BAR=E+"[38;5;240m"
RY=E+"[38;5;139m";GY=E+"[38;5;109m";MOV=E+"[38;5;139m"
RED=E+"[38;5;203m"
TC=E+"[38;5;216m";TCB=E+"[38;5;180;48;5;236m"   # TC=calling a tool (warm amber), TCB=its banner on a dark strip: differs from the step line (grey/teal)   # SOFT: RY=sageata thinking, GY=tool (teal), MOV=cutia THINKING (violet moale), toate fara bold
T=[{"type":"function","function":{"name":"python","description":"Run Python 3 here (stdlib + requests, urllib3, certifi, beautifulsoup4, pyyaml, toml, dateutil). NO pip, NOTHING installable: numpy/pandas/cryptography do NOT exist. BEST for parsing (JSON/INI), logic, aggregation, HTTP (requests). Slow on multi-million-line streams -> use bash.","parameters":{"type":"object","properties":{"code":{"type":"string"}},"required":["code"]}}},
   {"type":"function","function":{"name":"bash","description":"Run a shell command (bash -lc), returns stdout+stderr. For TEXT STREAMS: grep/awk/sed/sort/uniq/wc/find/du/cut, line-by-line filtering, xargs -P. ~1.3-1.6x faster than python on big streams, far less memory. NOT for parsing/logic.","parameters":{"type":"object","properties":{"cmd":{"type":"string","description":"the full shell command line, e.g. grep -c ERROR app.log | sort | uniq -c"}},"required":["cmd"]}}},
   {"type":"function","function":{"name":"smart","description":"AUTO-ROUTER: give the shell cmd and/or the Python code; it picks the faster engine itself and reports which and why. Use when unsure.","parameters":{"type":"object","properties":{"cmd":{"type":"string","description":"the shell command you would run if bash is chosen"},"code":{"type":"string","description":"the Python code you would run if python is chosen"}},"required":["cmd"]}}},
   {"type":"function","function":{"name":"look","description":"Look at an IMAGE file (screenshot, chart, photo) with vision and answer what is really in it. Never guess image content - look.","parameters":{"type":"object","properties":{"path":{"type":"string","description":"image file path (png/jpg), absolute or relative to the cwd"},"prompt":{"type":"string","description":"what to look for / what to answer"}},"required":["path"]}}},{"type":"function","function":{"name":"android","description":"Native Android control (Android build only). The ui tool: SEE and CONTROL other apps. Actions: read (COMPACT text list, ~10x smaller than JSON; params max, depth, textonly), find (SEARCH a node by text - USE FIRST for a contact/button/field), settext, click, tap, swipe, scroll, back/home/recents, openapp, windows, wake, sleep, service. FULL SDK access via reflection: action=\"eval\" runs ANY class/method/field; also services (list all system services), info (methods of a class). Plus ready shortcuts: camera location battery clipboard notify vibrate tts volume wifi device apps intent settings system storage processes network display audio telephony nfc usb appinfo.","parameters":{"type":"object","properties":{"tool":{"type":"string","description":"sensors|camera|location|battery|clipboard|notify|vibrate|tts|volume|wifi|device|apps|intent|settings|tourl|system|storage|processes|network|display|audio|telephony|nfc|usb|appinfo|eval"},"action":{"type":"string","description":"the sub-action (e.g. sensors: list|read|stream; location: last|fresh|current|providers; camera: list|photo; battery: get|full; clipboard: get|set; tts: say; apps: list|launch; settings: get|set)"},"params":{"type":"object","description":"parameters; for eval must contain \"expr\" = the reflection request. Reflection ops: call, new, get, set, info, services, objs, free, proxy (make a real instance of any Java INTERFACE: {\"op\":\"proxy\",\"iface\":\"java.lang.Runnable\"}), await (block for the next callback: {\"op\":\"await\",\"id\":\"s0\",\"timeout_ms\":10000}), subclass (make a REAL concrete subclass of any class incl. abstract: {\"op\":\"subclass\",\"parent\":\"android.bluetooth.le.ScanCallback\"}), events, sinks. To PASS AN OBJECT as an argument use a 2-element array [\"ref\",<value>] where value is \"ctx\", \"app\", \"obj:<id>\" or \"svc:<name>\" (e.g. args:[[\"ref\",\"ctx\"],0,[\"ref\",\"obj:o5\"],0x04000000]); a bare string \"ctx\" is a literal and is NOT resolved."}},"required":["tool"]}}},
   {"type":"function","function":{"name":"adbsh","description":"SUPER POWERS: real ADB shell uid=2000(shell) on this phone, run FROM the app, no PC (Android build only). Raw shell as the privileged user, which app code cannot: pm grant/revoke, appops set, settings put, dumpsys (full), input tap/text/keyevent (UI automation WITHOUT accessibility), screencap, uiautomator dump, am start/force-stop, pm list/enable/disable, logcat, getprop, svc, wm size/density, ls/cat/cp on the whole sdcard and /data/local/tmp, run-as, ifconfig/ip, cat /proc/net/*. Bypasses every permission wall: USE IT whenever the android/ui tools hit a SecurityException or a runtime permission is missing.","parameters":{"type":"object","properties":{"cmd":{"type":"string","description":"the shell command to run as the shell user, e.g. \"pm grant net.sys32.agent android.permission.CAMERA\" or \"dumpsys battery\" or \"input keyevent 3\""},"timeout":{"type":"integer","description":"seconds to wait (default 20, max 60)"}},"required":["cmd"]}}},{"type":"function","function":{"name":"bg","description":"BACKGROUND JOBS: the ONLY correct way to launch and track long work (builds, downloads, servers, llama.cpp). NEVER raw nohup/& via adbsh - you WILL lose track, read a stale log, get mixed output. Keeps a persistent REGISTRY: unique id, own timestamped log, tracked PID. Actions: start (cmd=, name=); status (what is REALLY running now - checks /proc, with duration+log size); log (job=, lines=) last lines of THAT job; kill (job=); list; clean. RULE: anything over ~30s goes through bg.","parameters":{"type":"object","properties":{"action":{"type":"string","description":"start | status | list | log | kill | clean","enum":["start","status","list","log","kill","clean"]},"cmd":{"type":"string","description":"for start: the shell command to run in the background"},"name":{"type":"string","description":"for start: short label for the job (e.g. llamacpp_build)"},"job":{"type":"string","description":"for log/kill: the job id (or its prefix)"},"lines":{"type":"integer","description":"for log: how many last lines (default 40)"}},"required":["action"]}}},
   {"type":"function","function":{"name":"toolchain","description":"NATIVE COMPILE TOOLCHAIN, already bundled IN THE APK (no PC, no external packages, no bootstrap). clang 21 + lld + sysroot + libxml2/libxslt deps live in filesDir/toolchain and are used DIRECTLY BY THE APP. Actions: status (is the toolchain present + what it can do - run this first if unsure); selftest (COMPILE+LINK reality check: C, C++ with STL, Python.h extension, Fortran + what is missing - run this before promising an install); pip_install (package= : downloads from PyPI and COMPILES C/C++ extensions NATIVELY on the phone - use it for lxml, numpy, pillow, cryptography etc.; this is the normal way to add libraries); compile (source= path to a .c/.cpp, out= .so path - compile your own native code); env (show the full compile environment: CC/CXX/CFLAGS/LDFLAGS/PATH); preflight (10s sanity test: C, C++, math, SSL); profile (ready-made cmake/cflags/ldflags). THERE IS NO BOOTSTRAP STEP: the toolchain ships with the app, so just call pip_install/compile directly. Do NOT look for a prefix in /data/local/tmp - it is in filesDir/toolchain.","parameters":{"type":"object","properties":{"action":{"type":"string","description":"status | pip_install | compile | env | preflight | profile","enum":["status","selftest","pip_install","compile","env","preflight","profile","doctor","fix","env-file"]},"package":{"type":"string","description":"for pip_install: package name (e.g. lxml, numpy, pillow, cryptography)"},"source":{"type":"string","description":"for compile: path to a .c/.cpp source file"},"out":{"type":"string","description":"for compile: output .so path"},"flags":{"type":"string","description":"extra compiler flags (optional)"},"timeout":{"type":"integer","description":"seconds to wait (default 1200, max 3600)"}},"required":["action"]}}},
   {"type":"function","function":{"name":"read","description":"Read a FILE in chunks (paginate). Use this to read the parts of a large file or a truncated tool log that were not shown in the window. Returns a header with the exact byte range and, if not at EOF, the next command to continue with.","parameters":{"type":"object","properties":{"path":{"type":"string","description":"file path (absolute, or relative to the working directory)"},"offset":{"type":"integer","description":"byte offset to start at (default 0)"},"limit":{"type":"integer","description":"max bytes to return (default 4000, max 20000)"}},"required":["path"]}}},
   {"type":"function","function":{"name":"multi","description":"BATCH: 2-6 small, independent ops in ONE call, ONE consolidated answer. Biggest cost saver: each extra step re-sends the whole context. Keep entries small. Do NOT bundle heavy/crashable pipelines here (a failure must stay isolated).","parameters":{"type":"object","properties":{"ops":{"type":"array","description":"2-6 operations, each independent and small","items":{"type":"object","properties":{"kind":{"type":"string","description":"bash (a small shell command) or python (a few lines only)","enum":["bash","python"]},"body":{"type":"string","description":"the command / the code for this entry, kept SHORT"},"name":{"type":"string","description":"short label shown in the output"}},"required":["kind","body"]}}},"required":["ops"]}}},{"type":"function","function":{"name":"help","description":"Return the FULL guide for an advanced Android topic, on demand - the detailed reflection/objects reference is kept OUT of the fixed prompt to save tokens and delivered here instead. Topics: \"reflection\" (eval ops: services/info/call/new/get/set/objs, targets svc:/class:/obj:/ctx/app, how to pass object refs), \"objects\" (proxy vs subclass for callbacks, await/events, getSystemService, Executor), \"privileged\" (capture/vpn/guard detail), \"all\" (everything). Call it the moment the native shortcuts are not enough.","parameters":{"type":"object","properties":{"topic":{"type":"string","description":"reflection | objects | privileged | all"}},"required":["topic"]}}}]

TOOLGUIDE=("TOOL SELECTION (measured on THIS device, toybox on aarch64 - do not guess, the numbers below are real): you have 3 engines. "
  "1) `python`: THE DEFAULT AND THE FASTEST ENGINE HERE for any computation. Full stdlib PLUS pre-installed: requests, urllib3, certifi, charset-normalizer, idna, beautifulsoup4, soupsieve, python-dateutil, six, pyyaml, toml, packaging, typing-extensions. NO pip, no numpy/pandas/cryptography. Python WINS BIG on this toybox build at: sorting (sorted/set: 36-95x faster than `sort`), aggregation and counting (Counter/dict: 3-4x faster than `awk`), text transform (str.upper/replace: 23-27x faster than `base64`/`sed`), all structured parsing (json.loads/yaml/toml), logic, and HTTP (requests.Session: 2.4x faster than repeated curl via connection keep-alive). Default to python for anything that is not a pure stream. "
  "2) `bash`: ONLY for pure pass-through streaming over big files and for many-small-files work. It genuinely wins here at: grep -c / grep -m1 (early exit), wc, cat, head, tail, tr, sha256sum/md5sum (native C), find/du, and `ls glob | xargs -P8 ...` over thousands of small files. Cost: ~15ms process spawn. DO NOT use bash for sort/awk/sed/base64/cut|sort|uniq - on THIS toybox those are 3-95x SLOWER than the python equivalent. "
  "3) `smart`: the AUTO-ROUTER - give it the shell cmd and/or the Python code and it picks the faster engine by itself from the measured rules above, then runs it. Use `smart` when unsure; it prints the engine and why. "
  "RULE OF THUMB: data must be COMPUTED (sort/count/aggregate/transform/parse) -> python (king here); data only FLOWS through untouched or is read early-exited -> bash; thousands of small files in parallel -> bash with xargs -P. "
  "★ PYTHON FIRST (measured this session, hard rule): python is not just the fastest engine, it is the RELIABLE one. PREFER python for EVERYTHING that can be done in it - including shell work when possible - because (a) it avoids the two-implementation trap of toybox builtins, (b) a python step never depends on PATH or on the flaky adbsh socket layer, (c) `subprocess` from python is deterministic (explicit argv, no shell parsing, no quoting bugs), (d) it can also reach the shell when truly needed: `import adb_client; adb_client.shared().shell(cmd)` gives the SAME uid=2000 shell as the adbsh tool, without the tool-call machinery. Use the `adbsh`/`bash` TOOLS only when the task is genuinely a stream or a shell one-liner; if a shell-style task can be expressed as a python subprocess call, DO IT IN PYTHON. "
  "Never use toybox sort/awk/sed on a big file: python is up to 95x faster. Never parse JSON with grep/awk: it is also WRONG (leaks values from escaped strings) - always python json.loads. "
  "TOYBOX GREP TRAP (measured on this device): the `bash` tool runs with a minimal PATH (`/system/bin`) and there grep IS toybox, which SILENTLY FAILS on several GNU patterns. Worst case: the basic-regex ALTERNATION (a backslash-pipe between two words, GNU style) prints NOTHING and still exits 0, so it LOOKS like 'no match' even when matches exist. In the `adbsh` tool the PATH starts with the toolchain, so there grep IS GNU and that same command WORKS. => NEVER use a bare `grep` with backslash-pipe alternation: use `grep -E` with a plain pipe (works in BOTH), or `grep -F` for a literal string, or just do it in python. COROLLARY: the SAME grep can give DIFFERENT results in bash vs adbsh; if a check comes back empty but you expected a match, re-run it with -E before concluding the text is absent. "
  "SAME RULE for other toybox builtins: prefer POSIX-safe flags (-E, -F, -q, -r) and avoid GNU-only extensions (`grep -P`, `sed -i` with a bare expression, `awk --csv` ...). When unsure, run the check in `adbsh` (GNU coreutils) instead of `bash`. "
  "WARNING: do NOT build a hybrid that captures a huge awk output into Python memory (subprocess capture_output on megabytes) - 14x the memory of plain bash. If you must combine, STREAM it (iterate stdout line by line).")

# --- FORMATARE OUTPUT (Android: terminalul nu randeaza tabele corect) ---
FMT=("OUTPUT FORMAT - ABSOLUTE RULES for this small phone screen: "
  "(1) NEVER output a Markdown table. A line containing two or more `|` characters is FORBIDDEN. "
  "No header separator lines like `|---|---|`, no `| a | b |` rows, ever. "
  "(2) NEVER draw ASCII boxes, frames or column-aligned layouts (things made of +---+ or +===+ or box-drawing chars). "
  "(3) For any tabular data ALWAYS use a plain LIST, one field per line, like: "
  "`- camera 0: back, flash yes, max 4080x3060` then next line `- camera 1: front, ...`. "
  "Or a key/value block: `key: value`, one per line. "
  "(4) Bullets with `- `, numbered steps with `1. `, short prose paragraphs. Lines short (under ~70 chars). "
  "If you catch yourself typing `|`, STOP and rewrite as a list instead. A list is ALWAYS preferred over a table here.")

# --- GHID ACCES ANDROID COMPLET (reflection) ---

# --- HELP: ghidul AVANSAT de Android, scos din promptul fix (se cere cu tool-ul `help`) ---
HELP_TEXT={
 "reflection": ("Android SDK through reflection - no root needed. Call ANY public class, method or field. "
  "HOW: android(tool=\"eval\", params={\"expr\":{...}}) where expr is one of: "
  "{\"op\":\"services\"} lists ALL system services; "
  "{\"op\":\"info\",\"target\":\"class:android.hardware.SensorManager\",\"filter\":\"Sensor\"} lists methods+fields; "
  "{\"op\":\"call\",\"target\":\"svc:sensor\",\"method\":\"getSensorList\",\"args\":[-1]} calls on a system service; "
  "{\"op\":\"call\",\"target\":\"class:android.os.Environment\",\"static\":true,\"method\":\"getExternalStorageDirectory\"}; "
  "{\"op\":\"new\",\"target\":\"class:android.media.MediaRecorder\"}; "
  "{\"op\":\"get\",\"target\":\"svc:wifi\",\"field\":\"mService\"} or {\"op\":\"set\",...}; {\"op\":\"free\",\"id\":\"o0\"}. "
  "TARGETS: svc:NAME, class:FQCN, obj:ID, ctx (app context), app, str:X, int:N, bool:true, null. "
  "LIST KEPT OBJECTS with the OP {\"op\":\"objs\"} (NOT a tool) - it returns id+class of every held object. "),
 "objects": ("CRITICAL - OBJECTS:\n"
  " * Every call/get/new now AUTO-RETURNS an id; the object stays alive under obj:<id>. REUSE it, do not recreate the same thing in a loop.\n"
  " * If a call returns only {class,str} with no id, the object was a primitive/array/collection.\n"
  " * PROXY (INTERFACES): {\"op\":\"proxy\",\"iface\":\"java.lang.Runnable\"} -> obj:<id>, pass as [\"ref\",\"obj:<id>\"]; calls recorded. Read with {\"op\":\"await\",\"id\":\"<id>\",\"timeout_ms\":10000} (next callback) or {\"op\":\"events\",\"id\":\"<id>\"}; {\"op\":\"sinks\"} lists proxies. For an ABSTRACT CLASS (ScanCallback, BroadcastReceiver) use {\"op\":\"subclass\",\"parent\":\"<FQCN>\"} -> same await/events. So any Android callback is implementable.\n"
  " * PASSING OBJECTS: use [\"ref\",<value>] where <value> = \"ctx\"|\"app\"|\"obj:<id>\"|\"svc:<name>\". A bare string is a LITERAL and is NOT resolved - always wrap: {\"args\":[[\"ref\",\"ctx\"],0]} . Works for op=new too.\n"
  " * getSystemService lives on Context: use target ctx, e.g. {\"op\":\"call\",\"target\":\"ctx\",\"method\":\"getSystemService\",\"args\":[\"sensor\"]}. "
  "An Executor comes from ctx.getMainExecutor() (no-arg). Many classes (LocationManager, Executors, HandlerExecutor...) have NO public no-arg constructor - obtain them from a service/factory.\n"),
 "privileged": ("android tool=capture action=status => MediaProjection screen-capture state; action=grab [path=/path.png] saves the LATEST frame as PNG (no ~1/sec limit, unlike a11y shot); action=start (asks the one-time screen-capture consent on the phone), action=stop RELEASES the capture session.  android tool=vpn action=status => VpnService state; action=establish [name=agent0] creates the TUN (needs one-time user consent), action=close tears it down.  android tool=guard action=status => which privileged services are alive (foreground, a11y, notif_listener, ime); action=start restarts the guard; action=schedule re-arms the keep-alive alarm. NEVER force-stop/pm clear/pm disable net.sys32.agent - it kills accessibility permanently. Each service has a *_state: ime_state=installed_not_selected = installed but not the ACTIVE keyboard (NORMAL, not a fault; enable only if the task must read/write fields: adbsh ime set net.sys32.agent/.AgentIme); ime_state=not_installed = truly missing; notif_state=disabled_needs_allow_listener = run adbsh cmd notification allow_listener. "),
}

ANDROID_GUIDE=("BE EXHAUSTIVE: for any hardware/system question, do not stop at the first source. Squeeze EVERYTHING reachable - use the native shortcuts AND reflection AND shell, cross-check them, and report everything you found (including what is NOT available and why). It is fine to take many steps. Explore every relevant nook: services, build props, sensors (action=all), sysfs, settings, managers. ANDROID ACCESS: on this device you have the `android` tool with FULL generic access to the whole "
 "REFLECTION + OBJECTS (how: eval ops services/info/call/new/get/set/objs; TARGETS svc:/class:/obj:/ctx/app; [\"ref\",...] for args; proxy vs subclass + await/events; getSystemService; Executor): call help(topic=\"reflection\") or help(topic=\"objects\") for the FULL guide when the native shortcuts are not enough. "
 "NATIVE SHORTCUTS that DO real hardware reading (use these FIRST for sensors/location, they handle callbacks in Kotlin): "
 "sensors action=list | action=read (name,seconds) | action=stream (name or names[],seconds,max) for continuous multi-sample data; "
 "location action=last (cache) | action=fresh (REQUEST A BRAND-NEW GPS FIX: real requestLocationUpdates + waits for onLocationChanged; provider=gps default, seconds=30) | action=current (getCurrentLocation, may return a cached fused fix instantly) | action=providers; "
 "camera list/photo; battery get|full (full = ALL battery data incl health/technology/current/charge_counter/estimate); clipboard get/set; notify; vibrate; tts; volume; wifi; device; apps list|launch; intent; settings get|set; system (model/cpu/ram/heap/uptime/build props with action=full); storage (disk usage); processes; network (wifi+transport); display (resolution/density/refresh/brightness); audio (all streams+devices); telephony (operator/SIM); nfc; usb; appinfo (package details+perms). "
 "PRIVILEGED TOOLS (added - use them instead of dumpsys/adbsh for these things): "\
 "android tool=ui action=shot [path=/path.png] => SCREENSHOT via AccessibilityService.takeScreenshot (returns the PNG path; ~1 capture/sec rate limit - wait ~1.2s between shots). "\
 "android tool=ui action=read|find|click|set_text|swipe|global as before. "\
 "android tool=notif (EXACT name notif, NOT notify/notifications) action=list [limit=N] => READ ALL ACTIVE NOTIFICATIONS of ALL apps (pkg/title/text/ongoing) via NotificationListenerService - THIS is how you read other apps notifications, NOT dumpsys; action=cancel (key=<key> cancels one, or package=<pkg> cancels all of a package); action=snooze key=<key> ms=<ms>. If it says listener NOT enabled, fix with adbsh: cmd notification allow_listener net.sys32.agent/.AgentNotificationListener "\
 "android tool=ime action=read => READ the text of the CURRENTLY FOCUSED TEXT FIELD in ANY app (pkg + before/after/selected/full) via our InputMethodService; action=type text=<s> [delete=N] injects text globally; action=key code=<N> sends a key; action=keys [limit=N] shows recent input events. The IME must be the active keyboard (adbsh: ime set net.sys32.agent/.AgentIme); a normal app CANNOT do this. "\
 "android tool=capture/vpn/guard (screen-capture, VpnService, service guard): call help(topic=\"privileged\") for the full guide. "
  "BATTERY RULE: MediaProjection keeps a 1080x2340@60fps VirtualDisplay alive in SurfaceFlinger and burns CPU even unread - the most expensive service. Not started automatically; use it ONLY for a screenshot: capture action=start -> grab -> action=stop (auto-stops after 3 min idle). To READ the screen prefer `android tool=ui action=read` (a11y costs nothing idle). `ui wake`/`ui sleep` toggle the screen - always `ui sleep` after a UI task. "\
 "IMPORTANT: when the user asks for the CURRENT/real-time value, use location action=fresh (real new fix) - NOT action=last/current which can serve a cached fused fix - and sensors action=read/stream - do NOT keep re-reading cached values (getLastKnownLocation is cache). "
 "For complex APIs go step by step: info -> call/new -> reuse obj:<id> -> call further. "
 "Everything the Android SDK exposes to an app, you can reach."
 " MISSION RULES: (0) CAPABILITY QUESTIONS (\"can you install X?\", \"what can this phone build?\") -> run `toolchain` action=selftest FIRST: it compiles+links C, C++ (libc++), a Python.h extension and Fortran (FLANG) ON THIS DEVICE in ~5s and returns `ok`/`lipsa` + a `detalii` map with the EXACT implementations. When you report, use the real names from `detalii` (clang/libc++/FLANG/rustc 1.98.1/maturin/cmake 3.31.6/perl 5.42) - NEVER say libstdc++ or gfortran, they are not what is installed. If a Rust/cargo build or `rustc`/`cargo --version` dies with SIGSEGV / exit -11 / 139, the FIRST thing to check is free RAM (`selftest` returns `ram_liber_mb`): rustc maps librustc_driver (~90 MB) + libLLVM, and under ~900 MB free it dies silently - close background apps and retry; and NEVER REPLACE LD_LIBRARY_PATH, always PREPEND to it (dropping the APK nativeLibraryDir path is what makes rustc segfault). (1) a missing library is never a dead end - install it via `toolchain` (pip_install for PyPI incl. C/C++ extensions, compile for your own C/C++); prefer the already-installed pure-Python tools first. (2) LONG work (build/download/server, anything over ~30s) goes ONLY through `bg` - never raw nohup/& via adbsh (you will lose it and read a stale log). Before starting a new run of the same thing, check bg(action=status) and kill leftovers. (3a) WHERE THE BINARIES ARE (nu raporta nimic ca lipsa fara asta): fiecare unealta este un ELF in directorul lib al APK-ului (libclang_exec.so, libcmake_exec.so, libllvmar_exec.so, libninja_exec.so, libperl_exec.so, librustc_exec.so, libcargo_exec.so, libmaturin_exec.so, libccrust_exec.so...) cu symlink-uri in files/tmp/ SI in files/toolchain/bin/ (cmake, ninja, make, perl, ar, llvm-ar, ranlib, nm, strip, clang, rustc, cargo, maturin, patchelf...). Daca o unealta pare lipsa, ruleaza `toolchain action=env` si foloseste PATH-ul returnat; NU concluziona ca o capabilitate lipseste doar pe baza unui `ls`. (3b) RUNNING A COMPILED BINARY (dovedit pe device): procesul app NU poate executa un ELF proaspat compilat (SELinux data_file_type; Android 10+ interzice exec din datele aplicatiei). Caile care MERG: (a) /apex/com.android.runtime/bin/linker64 <binar> [args] - linkerul de sistem mapeaza binarul, ocolind restrictia; (b) prin adbsh (uid=2000). NU concluziona niciodata ca build-ul e rupt doar pentru ca binarul produs nu porneste direct. (3c) WHERE TO BUILD: compile in `files/tmp` (or the app workspace), NEVER on /sdcard - /storage is NOEXEC, the binary cannot even be mapped from there (couldn't map ... segment 3: Permission denied), so you would have to copy it again. `toolchain action=env` prints the exact CC/CXX/CFLAGS/LDFLAGS plus ready-to-copy examples (C, C++, Python extension, Fortran, Rust, cmake) - use it instead of guessing flags (guessing cost steps in real sessions: -latomic, --target, -resource-dir, -static-libstdc++). (3d) RUST: foloseste `toolchain`/cargo sau `$TC/bin/cargo build --release` - in `files/cargo/config.toml` linker-ul e deja setat (cc-rust) si build-ul merge (dovedit). NU te lupta cu `rustc` invocat direct: linkerul lui implicit `cc` nu se rezolva in mediul spawn-uit de rustc (pierzi zeci de pasi; cargo e calea corecta). (3e) EXEC: binarele ELF compilate de toolchain SUNT executabile direct din files/tmp (dovedit rc=0), iar varianta sigura e `/apex/com.android.runtime/bin/linker64 <binar>`. SCRIPTURILE shell din filesDir NU se executa (Permission denied) - pentru scripturi foloseste lansatoarele ELF (libshwrap_exec.so + <nume>.sh). (3f) CAPCANE DE RULARE (dovedite in testele din UI): linker64 cere o cale ABSOLUTA (`./x` da 'expected absolute path'). Un modul .so compilat NU poate fi importat din /sdcard (namespace de linker; /storage e noexec) - copiaza-l in files/libs sau files/tmp inainte de import. Fortran merge DOAR prin wrapperul files/tmp/flang; driverul brut toolchain/bin/flang EȘUEAZĂ cu 'gcc frontend command failed' - nu-l folosi. Daca adbsh raporteaza ca adbd asteapta autorizarea cheii, NU insista si NU repeta la infinit: foloseste uneltele native (android/ime/notif/capture) si spune operatorului sa apese Allow in dialogul de pe telefon. (3g) .so vs EXECUTABIL (a costat 20+ pasi): daca iesirea se termina in .so, compile face o LIBRARIE PARTEJATA (-shared) si NU se ruleaza (linker64 da SIGSEGV). Pentru un program care ruleaza, foloseste o iesire FARA .so (ex. t_bin): clang produce atunci un PIE executabil normal (are INTERP + entry) care ruleaza direct. (3h) cmake: are nevoie de export PREFIX=<toolchain> (CMakeDetermineSystem.cmake citeste $ENV{PREFIX}/include/android/api-level.h) si de CMAKE_ROOT=<toolchain>/cmake; altfel apare Could not find CMAKE_ROOT / file failed to open. Seteaza si CMAKE_SYSTEM_VERSION. (3i) rustc invocat DIRECT are nevoie de LD_LIBRARY_PATH cu <toolchain>/rust/lib, altfel da library librustc_driver not found; cargo merge fara asta (configul e deja pregatit). (3) To hand the operator something runnable from /data/local/tmp (a compiled binary, llama.cpp, a GGUF), tell them to use /run_su <script> [args] (SHELL rights uid=2000); /run has only APP rights and cannot see /data/local/tmp. Write the launcher as a .sh in the workspace exporting PATH/LD_LIBRARY_PATH.")


M=[{"role":"system","content":TOOLGUIDE+" "+FMT+" "+ANDROID_GUIDE+" You are a minimal autonomous agent. Use stdlib only. Your working directory is "+WORK+" - create every file, script and temporary test THERE, never elsewhere on the disk. Do the task end to end and verify it. "
  "WHILE WORKING (mandatory, never skip): BEFORE EVERY python tool call you MUST put a FULL, COMPLETE sentence in the `content` field, in the operator\u2019s language, telling what you are about to do and why. There is NO word limit and NO character limit: NEVER cut, shorten or abbreviate it with \u201c...\u201d or \u201c\u2026\u201d - the operator must always see the WHOLE sentence he needs to follow you. NEVER send a tool call with empty content. Markdown is NOT allowed in that sentence. "
  "VISION: you have a second tool, `look(path, prompt)` - it sends an IMAGE file to the same model with THINKING ENABLED and returns what is REALLY in it. Use it whenever the operator asks you to see/analyze a screen, a screenshot, a chart or a photo: first capture it (e.g. `xwd -root -out shot.xwd` then convert with ffmpeg to png), then call look on the png. Never guess what an image contains - look at it. "
  "STEP LABELS: the FIRST line of every python/bash tool call is a comment (lowercase) - the terminal prints it as that step’s label. Say WHAT the step does, in the language the operator is currently using (mirror them), never `# step 1` or `# test`. DENSITY RULE (this is billed, the label is part of the context sent on EVERY later request): one short line, the essential verb + object, no trailing explanation, no restating the task, no repeating the previous label. Aim for ~60-90 chars; a label that needs 200 is usually two steps. Completeness of INFORMATION, not of prose. "
  "The terminal UI shows a live task timer (from the operator's request to your final answer, split into thinking vs tool time) and one labelled line per finished step; no code and no output unless the operator toggles /verbose. "
  "BATCH SMALL STEPS (biggest cost saver): every request re-sends the WHOLE context, so each extra "
  "step costs the full history again. When you need 2-6 quick, INDEPENDENT things (a listing, a short cat, "
  "a status), do NOT spend 6 steps: use the `multi` tool ONCE with the list of ops. Rule of thumb: if step B "
  "would not read anything step A printed, they belong in the SAME `multi` call. DO NOT batch when the next "
  "step depends on the previous output, when an entry is heavy/long or can hang, or when the operator asked "
  "to see each step - a failure must stay isolated and visible. Small steps are GOOD for reliability; the "
  "only waste is running them one request at a time. "
  "STOPPING CRITERION (a real failure from the numpy build): before you call a task done, state to yourself WHAT the finish line is (e.g. `python -c \"import numpy\"` exits 0 and prints the version). The task is NOT done because a tool printed OK - it is done when the FINAL verification returns the result that was asked for. After EVERY step that reports success, check the EFFECT on disk (does the file exist? does the command run?), not the status message. If a tool says OK but the effect is missing, treat it as a FAILURE and investigate the tool. NEVER end a turn with \"I did X, next comes Y\" when the operator asked for Y: finish Y. A half-done task reported as progress is worse than an honest \"I am blocked on Z\". " +
  "UID 2000 (adbsh) - CE POATE SI CE NU: shell-ul are puteri privilegiate (pm grant/revoke, appops, settings, dumpsys, input, screencap, run-as, logcat) si poate scrie in /data/local/tmp, dar NU POATE CITI filesDir-ul aplicatiei (mod 700, alt proprietar): toolchain-ul din APK ramane EXCLUSIV al aplicatiei, nu-l cauta din adbsh. In /data/local/tmp pot exista wrapper-e VECHI (clang/cython) care arata spre cai de APK demultate - ignorale; compilarea se face cu tool-ul toolchain (in procesul aplicatiei), nu prin shell. " +
  "CODE DENSITY (the code you send is billed on EVERY later request): the `code`/`cmd` field of a tool call "
  "stays in the context forever and is re-sent each round. So write the SHORTEST code that does the job: no "
  "decorative comments (only the one required label line), no re-printing data you already printed, no "
  "boilerplate. This does NOT mean fewer steps or bigger pipelines: it means each step carries only the code "
  "it needs. "
  "CONTEXT ECONOMY: nothing is ever deleted - only heavy tool outputs and old steps are moved to disk when the window gets big. When you see a line like `[complete output, untouched: archive/ctx_....json #12 (4300 chars)]` or `[complete code, untouched: ...]`, the EXACT original text is on disk: read or grep it (raw tool outputs live in ./logs/*.log, full pre-compaction transcripts in ./archive/ctx_*.json) instead of guessing what the truncated middle contained. Do that whenever the exact bytes matter: error strings, stack traces, file contents, numbers. ""MEMORY RULE: the MEMORY block below is READ-ONLY for you - never write, append, modify or delete it on your own initiative, only when the operator explicitly asks. Use it to work faster, but only its owner updates it. "
  "IT IS A SNAPSHOT: memory.md was loaded into this system prompt ONCE, at session start; the file on disk may already be longer (the operator updates it, /learn appends to it). Lessons taught after this start are NOT here - if memory says nothing about X, that does not mean X was never learned. "
  "IT IS TELEGRAPHIC: one lesson per line - `TRAP: what failed -> exact error -> cause -> fix`, `OK: what verifiably works`, `DEAD: what does not work -> proof`, `P: absolute path -> artifact, `RULE (ordinea cailor): 1 -> 2 -> 3` = ordered decision rule (cheapest path first) / how to run`, sections `## date - topic`. Read it as dense facts, not prose; missing words are not missing meaning. "
  "FINAL MESSAGE: rendered as Markdown in a 256-colour terminal. You MAY use headings (# ## ###), **bold**, *italic*, `inline code`, ~~strikethrough~~, > blockquote, --- rules, numbered/bulleted lists and fenced code blocks. BUT on this small phone screen NEVER use tables (no | pipes | rows, no |---| separators) and never ASCII boxes - present ALL structured data as plain lists, one item or `key: value` per line. Write the final answer in the SAME LANGUAGE the operator used in their last message, complete and well structured - if they wrote in English, reply in English; if in Romanian, reply in Romanian."}]
# ★ FIX (24 sept: zgomot MediaProvider). context.json traia in DOUA locuri: copia privata
# (scrisa la fiecare pas) + o oglinda pe sdcard (FUSE) la fiecare 8 salvari. Fiecare scriere
# pe /storage/emulated/0 declansa in MediaProvider:
#   - "Failed to update quota type for .../context.json.tmp: No such file or directory"
#     (StorageManager incerca sa seteze project id pe .tmp DUPA ce os.replace il mutase deja)
#   - "Failed to revoke permissions for .../context.json from DownloadStorageProvider:
#      UnsupportedOperationException: Unsupported call: revoke_uri_permission"
#     (DownloadStorageProvider nu suporta revoke_uri_permission, dar MediaProvider il cheama oricum)
# Rezultat: ~66 erori in logcat + munca inutila pe FUSE la fiecare task, zero beneficiu real.
# Acum context.json (istoricul conversatiei) traieste EXCLUSIV in stocarea privata a app-ului,
# unde FUSE si MediaProvider nu intervin: zero erori, scriere mai rapida, istoric intact.
CTX=os.path.join(HOME_DIR,CTXNAME)   # in HOME_DIR (langa memory.md), NU in _SANDBOX (fisierul scriptului)
CTX_PUB=None  # pastrat doar pentru compat: nu mai exista oglinda pe sdcard
# --- migrare: muta context.json/memory.md din locatiile vechi (sandbox sau /sdcard/agent) ---
def _migrate():
    import glob as _g
    old_ws = [_SANDBOX, os.path.join(_SANDBOX,"workspace"),
              "/storage/emulated/0/agent", "/sdcard/agent"]
    for _w in old_ws:
        for _name,_dst in (("context.json",CTX),("memory.md",MEM)):
            _src=os.path.join(_w,_name)
            try:
                if os.path.exists(_src) and not os.path.exists(_dst):
                    import shutil as _sh; _sh.copy2(_src,_dst)
            except Exception: pass
_migrate()   # muta context.json/memory.md din locatiile vechi, o singura data
LEGACY=os.path.join(os.path.dirname(os.path.abspath(__file__)),"context.json")  # vechea locatie (langa script)
def _migrate_ctx():
    """If the history still exists next to the script (the old location) and we do not already have one
    in the working folder, move it there. Runs a single time, on the first startup
    after the location change, so that the conversation is not lost."""
    if os.path.abspath(LEGACY)==os.path.abspath(CTX) or not os.path.isfile(LEGACY): return
    empty=True
    if os.path.isfile(CTX):
        try: empty=(json.load(open(CTX,encoding="utf-8"))==[])
        except Exception: empty=True
    if not empty: return
    try: shutil.move(LEGACY,CTX)
    except Exception as e: print(R+" [context] could not move the old history into temp: "+str(e)+N)

def save_ctx(force_mirror=False):
    """Writes the conversation history (without the system message) to context.json, via a temporary
    file + os.replace, so it does not get corrupted on an interruption.
    Scrie EXCLUSIV in stocarea privata (CTX): fara oglinda pe FUSE, deci fara zgomotul
    MediaProvider (quota/revoke_uri_permission). Istericul nu mai e expus pe sdcard."""
    try:
        tmp=CTX+".tmp"
        with open(tmp,"w",encoding="utf-8") as f: json.dump(M[1:],f,ensure_ascii=False,indent=1)
        os.replace(tmp,CTX)
    except Exception as e: print(R+" [context] could not save "+CTX+": "+str(e)+N)

def ctx_mirror():
    """Nu mai exista copie pe sdcard de oglindit (context.json traieste doar in stocarea privata)."""
    return
def load_ctx():
    """Reloads the history at startup. Tool messages left without a corresponding
    tool_call (e.g. a brutal shutdown) are dropped, otherwise the API rejects
    the conversation."""
    _migrate_ctx()
    # migrare o singura data: daca exista o copie veche pe sdcard (dinainte de mutare),
    # o aducem in stocarea privata ca sa nu pierdem istoricul, apoi nu mai atingem sdcard-ul.
    if not os.path.exists(CTX) and CTX_PUB and os.path.exists(CTX_PUB):
        try: shutil.copyfile(CTX_PUB,CTX)
        except Exception: pass
    try: hist=json.load(open(CTX,encoding="utf-8"))
    except FileNotFoundError: return 0
    except Exception as e:
        print(R+" [context] "+CTX+" invalid ("+str(e)+") - starting with an empty history."+N); return 0
    if not isinstance(hist,list):
        print(R+" [context] context.json does not contain a list - starting with an empty history."+N); return 0
    ids={tc.get("id") for m in hist if isinstance(m,dict) and m.get("role")=="assistant" for tc in (m.get("tool_calls") or [])}
    hist=[m for m in hist if isinstance(m,dict) and m.get("role") in ("user","assistant","tool")
          and (m.get("role")!="tool" or m.get("tool_call_id") in ids)
          and (m.get("role")!="assistant" or (m.get("content") or "").strip() or m.get("tool_calls"))]
    # after a brutal stop the last assistant may still carry tool_calls with NO tool answer:
    # the API rejects the whole conversation (HTTP 400), so the broken tail is cut off
    while hist and hist[-1].get("role")=="assistant" and hist[-1].get("tool_calls"): hist.pop()
    M.extend(hist); return len(hist)
load_ctx()          # the history is loaded at startup (the return value was never used)
SESS={"in":0,"out":0,"cache_hit":0,"rounds":0}
TN=[0]   # the tool number in the current task (grows on every run, resets on a new task)
def _K(n):
    """Collapse a token count to a short human string (1.2k / 3.4M)."""
    if n>=1_000_000: return ("%.2f"%(n/1_000_000.0)).rstrip("0").rstrip(".")+"M"
    if n>=1_000: return ("%.1f"%(n/1000.0)).rstrip("0").rstrip(".")+"k"
    return str(int(n))
ROUND_LINES=[]      # the compact token line of the LAST round (printed by flush_task_tokens)
def print_usage_compact(usage):
    """Accumulates SESS (cumulative for the session) and stores the compact line of the
    last round; the printing happens only in flush_task_tokens(). The numbers come
    straight from the server usage (that is what gets billed)."""
    if not usage: return
    cd=usage.get("completion_tokens_details") or {}
    pt=usage.get("prompt_tokens") or 0
    ct=usage.get("completion_tokens") or 0
    h =usage.get("prompt_cache_hit_tokens") or 0
    rz=cd.get("reasoning_tokens") or 0
    SESS["in"]+=pt; SESS["out"]+=ct; SESS["rounds"]+=1
    TASK["tok_in"]+=pt; TASK["tok_out"]+=ct; TASK["cache"]+=h   # same server numbers, accumulated for THIS task
    if h: SESS["cache_hit"]+=h
    line="\u25aa tok \u2191%s \u2193%s"%(_K(pt),_K(ct))
    if pt and h: line+=" \u00b7 hit %d%%"%int(100.0*h/pt)
    if rz: line+=" \u00b7 rz %s"%_K(rz)
    ROUND_LINES[:]=[line]   # keep only the last round

def flush_task_tokens():
    """Prints (1) the token line of the last round and (2) the cumulative
    total for the session. No-op if no round has run."""
    lines=list(ROUND_LINES)
    del ROUND_LINES[:]
    if not SESS["rounds"] and not lines: return
    print()   # blank line: the token block is separate from the "TASK #N done" footer above it
    for ln in lines: print(G+"   "+ln+N)
    if TASK["tok_in"]: print(G+"   \u25aa this task cache HIT "+("%d%%"%int(100.0*TASK["cache"]/TASK["tok_in"]))+" (higher = cheaper)"+N)
    si,so=SESS["in"],SESS["out"]
    cum="   \u25aa session tok \u2191%s \u2193%s = %s"%(_K(si),_K(so),_K(si+so))
    if si: cum+=" \u00b7 hit %d%%"%int(100.0*SESS["cache_hit"]/si)
    cum+=" \u00b7 %d rds"%SESS["rounds"]
    print(G+cum+N)
    print("\n")   # 2 blank lines: separate the token block from the next "TU >" prompt (every caller of this returns to input())
def sanitize_msgs(msgs):
    """Repara istoricul ca sa fie ACCEPTAT de API-ul DeepSeek.

    Regula API: fiecare mesaj `assistant` cu `tool_calls` TREBUIE urmat imediat
    de cate un mesaj `tool` pentru FIECARE `tool_call_id`, inainte de orice alt
    mesaj (user/assistant).

    Cazul real care a produs eroarea HTTPError:
    operatorul scrie in chat in timp ce un task ruleaza -> mesajul `assistant`
    cu tool_calls ramane urmat de un mesaj `user` (nu de `tool`) -> API respinge
    TOT, iar agentul devine inutilizabil pana la /reset.

    Solutia: inseram raspunsuri `tool` lipsa (si, daca e nevoie, mutam/decuplam
    mesajele user care s-au strecurat intre). Idempotent.
    """
    if not msgs:
        return 0
    fixed = 0
    out = []
    i = 0
    n = len(msgs)
    while i < n:
        m = msgs[i]
        out.append(m)
        if m.get("role") == "assistant" and (m.get("tool_calls") or []):
            ids = [tc.get("id") for tc in m["tool_calls"] if tc.get("id")]
            # colectez raspunsurile tool care urmeaza IMEDIAT (pana la alt rol)
            j = i + 1
            got = {}
            while j < n:
                x = msgs[j]
                if x.get("role") == "tool" and x.get("tool_call_id") in ids:
                    got[x["tool_call_id"]] = x
                    out.append(x)
                    j += 1
                else:
                    break
            # adaug raspunsuri pentru cele lipsa
            for _id in ids:
                if _id not in got:
                    out.append({"role": "tool", "tool_call_id": _id,
                                "content": "[not executed - the run was interrupted before this "
                                           "tool call ran. Continue from the last completed step.]"})
                    fixed += 1
            i = j
            continue
        i += 1
    if fixed:
        msgs[:] = out
    return fixed


def complete_pending(msgs):
    """After Ctrl+C, the last assistant message may declare N tool_calls with answers
    for only some of them; the API requires an answer for EVERY declared call."""
    for i in range(len(msgs)-1,-1,-1):
        m=msgs[i]
        if m.get("role")!="assistant": continue
        tcs=m.get("tool_calls") or []
        if not tcs: return
        ids=[tc.get("id") for tc in tcs if tc.get("id")]
        got={x.get("tool_call_id") for x in msgs[i+1:] if x.get("role")=="tool"}
        for tc in tcs:
            if tc.get("id") and tc.get("id") not in got:
                msgs.append({"role":"tool","tool_call_id":tc["id"],
                    "content":"[not executed - operator interrupted the run (Ctrl+C) before this tool call ran; results of the tools that DID run are intact above. Continue from the last completed step.]"})
        return

def refresh():
    """Glues the memory into the system message. Called ONCE, at startup:
    from then on the system prefix stays IDENTICAL for the whole session (maximum prompt cache),
    and what /learn learns enters the context only at the next startup."""
    mm=mem()
    for m in M:
        if m["role"]=="system": m["content"]=m["content"].split("\n\n--- MEMORY ---")[0]+("\n\n--- MEMORY ---\n"+mm if mm else "")
def vision(path,prompt,max_tokens=None):
    """Sends ONE image to the same API in VISION mode, with THINKING ENABLED so the model
    really looks at the pixels (layout, alignment, what is broken) instead of guessing.
    Used by the `look` tool. Returns the model text, or an error string."""
    p=path if os.path.isabs(path) else os.path.join(os.getcwd(),path)
    if not os.path.isfile(p): return "[look] file not found: "+p
    try: b=base64.b64encode(open(p,"rb").read()).decode()
    except Exception as e: return "[look] cannot read "+p+": "+e.__class__.__name__+": "+str(e)
    mime={"png":"image/png","jpg":"image/jpeg","jpeg":"image/jpeg","gif":"image/gif","webp":"image/webp","xwd":"image/x-xwindowdump"}.get(p.rsplit(".",1)[-1].lower(),"image/png")
    mt=int(max_tokens or os.environ.get("DS_VISION_MAXTOK","4000"))
    msg=[{"role":"user","content":[{"type":"text","text":prompt or "Describe exactly what this image shows."},
          {"type":"image_url","image_url":{"url":"data:"+mime+";base64,"+b}}]}]
    body={"model":os.environ.get("DS_MODEL","deepseek-flash"),"messages":msg,"max_tokens":mt,
          "thinking":{"type":os.environ.get("DS_VISION_THINKING","disabled")}}
    r=urllib.request.Request("https://api.deepseek.com/chat/completions",data=json.dumps(body).encode(),
      headers={"Authorization":"Bearer "+K,"Content-Type":"application/json"})
    try:
        d=json.loads(urllib.request.urlopen(r,timeout=600).read())
        m=d["choices"][0]["message"]; u=d.get("usage") or {}
        out=(m.get("content") or "").strip()
        if not out: out="(the model returned no text; try a bigger DS_VISION_MAXTOK)"
        return out+"\n[look] "+str(os.path.getsize(p)//1024)+" KB | tok in "+str(u.get("prompt_tokens","?"))+" out "+str(u.get("completion_tokens","?"))+(" (reasoning "+str(u["completion_tokens_details"]["reasoning_tokens"])+")" if u.get("completion_tokens_details") else "")
    except Exception as e:
        return "[look] "+e.__class__.__name__+": "+str(getattr(e,"read",lambda:b"")())[:300]
def adbsu_capture(argv, timeout=3600):
    """Ruleaza un script PRIN ADB SHELL (uid=2000) si afiseaza output-ul
    linie cu linie, in timp real. Fata de py_capture (uid=app), acesta are
    SUPER-PUTERI: vede /data/local/tmp, poate executa binare din toolchain
    (compilate nativ), llama.cpp, modele GGUF etc.

    argv = [script, args...] ; scriptul poate fi .py, .sh sau orice executabil.
    """
    import shlex as _sh
    # construim linia de comanda: mediul complet + scriptul + argumente
    parts = [". /data/data/net.sys32.agent/files/toolchain_env.sh >/dev/null 2>&1; "]
    script = argv[0]
    args = " ".join(_sh.quote(a) for a in argv[1:])
    if script.endswith(".py"):
        # script Python: il rulam cu python3-ul din toolchain
        parts.append("cd %s; exec python3 %s %s" % (_sh.quote(WORK), _sh.quote(script), args))
    elif script.endswith(".sh"):
        parts.append("cd %s; exec sh %s %s" % (_sh.quote(WORK), _sh.quote(script), args))
    else:
        parts.append("cd %s; exec %s %s" % (_sh.quote(WORK), _sh.quote(script), args))
    cmd = "".join(parts)
    try:
        out = run_adbsh_tool(cmd, timeout)
    except KeyboardInterrupt:
        raise
    except Exception as e:
        out = "[run_su error: %s]" % str(e)
    sys.stdout.write(out if out.endswith("\n") else out + "\n")
    sys.stdout.flush()
    return out or "(no output)"


def _clean_ld(value):
    """LD_LIBRARY_PATH de RULARE: scoate directoarele de LINK (stub-urile NDK din
    sysroot) si duplicatele.

    ★ BUG REPARAT (28 sept, dovedit pe device): toolchain-ul isi punea
    `toolchain/sysroot/usr/lib/aarch64-linux-android/35` PRIMUL in LD_LIBRARY_PATH.
    Acolo libc.so/libm.so/libdl.so sunt STUB-uri de linkare (fara cod). Procesul
    AGENT nu patea nimic (bionic citeste LD_LIBRARY_PATH la INIT, nu la dlopen),
    dar ORICE PROCES COPIL pornea cu libc STUB -> SIGSEGV in constructorii
    libpython3.14.so. Simptomul vizibil: `pip install` murea cu
    "Preparing metadata (pyproject.toml): exit code: -11".
    """
    out=[]
    for p in str(value or "").split(":"):
        p=p.strip()
        if p and p not in out and "sysroot" not in p:
            out.append(p)
    return ":".join(out)


def _harvest_wheels(pkg, cachedir):
    """★ FAZA 0C: copiaza in wheelhouse (files/wheels) wheel-urile construite/descarcate
    pentru `pkg`, ca un reinstall sa NU mai compileze (si ca sa mearga si offline)."""
    try:
        wd = HOME_DIR + "/wheels"
        os.makedirs(wd, exist_ok=True)
        name = str(pkg).split("[")[0].split("==")[0].strip().replace("_", "-").lower()
        n = 0
        for dp, dn, fn in os.walk(cachedir or ""):
            for f in fn:
                if f.endswith(".whl") and name in f.lower():
                    dst = os.path.join(wd, f)
                    if not os.path.exists(dst):
                        shutil.copy2(os.path.join(dp, f), dst)
                        n += 1
        return n
    except Exception:
        return 0


def _classify_build_fail(txt):
    """★ FAZA 0B: taxonomie de esec -> (cod, ce lipseste, urmatorul pas).

    Scop: agentul sa spuna OPERATORULUI ce lipseste si ce alternativa are, in loc sa
    verse un traceback. Codurile acopera limitele cunoscute din PLAN_AUTONOMIE.md.
    """
    t = str(txt or "")
    low = t.lower()
    if "maturin" in low or ("cargo" in low and "rust" in low):
        return ("rust_lipsa",
                "backend-ul de build e scris in Rust (maturin) si nu exista rustc/cargo pentru aarch64-linux-android",
                "nu exista wheel binar pentru acest pachet; FAZA 2 din PLAN_AUTONOMIE.md deblocheaza Rust")
    if "cmake" in low and ("not found" in low or "no such file" in low or "executable" in low):
        return ("cmake_lipsa", "build-ul cere cmake (>= 3.29), care nu e in toolchain",
                "FAZA 1 din PLAN_AUTONOMIE.md; alternativ cauta o versiune a pachetului cu wheel binar")
    if "perl" in low and ("not found" in low or "no such file" in low):
        return ("perl_lipsa", "build-ul cere perl (autoconf/asm BoringSSL)", "FAZA 3 din PLAN_AUTONOMIE.md; vezi si GRPC_BUILD_WITH_BORING_SSL_ASM=0")
    if "no space left" in low or "enospc" in low:
        return ("spatiu_insuficient", "spatiu liber insuficient pe device", "elibereaza files/tmp si wheelhouse-ul vechi")
    if "cannot allocate memory" in low or "memoryerror" in low or "out of memory" in low:
        return ("ram_insuficient", "RAM insuficient pentru acest build", "reia build-ul prin `bg` cu MAKEFLAGS=-j1 si scoate alte procese")
    if "no matching distribution" in low or "could not find a version" in low:
        return ("wheel_inexistent", "nu exista distributie compatibila (wheel sau sdist) pentru android/arm64",
                "verifica numele/versiunea; unele pachete nu publica sdist")
    if "missing setup required dependencies" in low:
        return ("cerinte_build", "lipsesc cerintele de build din pyproject.toml", "se repara automat (prefetch) - vezi linia `pasi:`")
    if "python.h" in low or "stddef.h" in low or "stdint.h" in low:
        return ("headers_lipsa", "headerele de compilare nu sunt gasite", "ruleaza toolchain action=fix (rescrit sysconfig/INCLUDEPY)")
    if "undefined symbol" in low or "cannot locate symbol" in low:
        return ("link_runtime", "simbol nerezolvat la link/rulare (libc++/libm)", "ruleaza toolchain action=fix")
    return ("eroare_build", "build-ul a esuat (cauza in liniile de mai sus)",
            "ruleaza toolchain action=selftest ca sa vezi ce capabilitati are telefonul ACUM")


def py_capture(argv, timeout=600):
    """Ruleaza un script Python (argv=[script, args...]) si afiseaza output-ul LINIE cu LINIE,
    in timp real (streaming). Returneaza intregul output (pentru context), dar il si printeaza
    pe masura ce apare, ca sa vezi progresul unui script care dureaza."""
    buf=[]
    p=subprocess.Popen([sys.executable]+list(argv),stdin=subprocess.DEVNULL,cwd=WORK,stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT,start_new_session=True,text=True,bufsize=1)
    t0=time.time()
    try:
        for line in p.stdout:             # streaming: fiecare linie apare imediat
            buf.append(line)
            sys.stdout.write(line); sys.stdout.flush()
            if time.time()-t0 > timeout:
                try: os.killpg(p.pid,signal.SIGKILL)
                except Exception: pass
                print(R+"\n[timeout after "+str(timeout)+"s]"+N); break
        p.wait(timeout=5)
    except KeyboardInterrupt:
        try: os.killpg(p.pid,signal.SIGKILL); p.wait(timeout=3)
        except Exception: pass
        raise
    except Exception as e:
        buf.append("[run error: "+str(e)+"]\n")
    out="".join(buf)
    return out or "(no output)"

def _raise_fd_limit():
    """Ridica plafonul de descriptori (soft -> hard) o singura data.

    ★ Dupa ore de rulare, aplicatia atinge limita implicita (Android: ~1024 fd-uri) si
    tempfile/subprocess incep sa cada cu EMFILE ("Too many open files") - un astfel de esec a
    produs crash-ul raportat de operator (linia _mkstemp_inner din traceback).
    """
    try:
        import resource as _res
        soft, hard = _res.getrlimit(_res.RLIMIT_NOFILE)
        if soft < hard:
            _res.setrlimit(_res.RLIMIT_NOFILE, (hard, hard))
        return soft, hard
    except Exception:
        return None


def py(c,cwd):
    """Runs the code in its own process group. Ctrl+C kills ONLY this
    tool (SIGKILL on the group), then re-raises the signal to the task loop."""
    # ★ FAZA 4o (crash raportat de operator: traceback la tempfile.TemporaryFile(dir=WORK)):
    # pe /sdcard (FUSE) + proces de lunga durata, _mkstemp_inner poate cadea (fd-uri epuizate,
    # hiccup FUSE). Inainte, orice eroare aici OMORA agentul. Acum: fallback in lant si, in cel
    # mai rau caz, continuam fara buffer-ul LIVE (executia codului nu depinde de el).
    try:
        _raise_fd_limit()
    except Exception:
        pass
    o = None
    _F = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # .../files (agent.py e in files/python)
    for _td in (WORK, _F + "/tmp", None):
        try:
            o = tempfile.TemporaryFile(dir=_td) if _td else tempfile.TemporaryFile()
            break
        except Exception:
            o = None
    if o is None:
        o = io.BytesIO()
    # ★ FIX CRASH -11: `libpyexec.so -c <cod>` RE-INCARCA agent.py (sys.executable
    # e libpyexec.so, care la import ruleaza bucla principala) -> SIGSEGV instant.
    # Solutie: scriu codul intr-un fisier si il rulez ca SCRIPT (fara -c).
    try:
        _rf=tempfile.NamedTemporaryFile(mode="w",suffix=".py",dir=F+"/tmp",delete=False)
        _rf.write(c); _rf.close(); _rpath=_rf.name
    except Exception:
        _rpath=None
    if _rpath:
        p=subprocess.Popen([sys.executable,_rpath],cwd=cwd,stdout=o,stderr=subprocess.STDOUT,start_new_session=True,stdin=subprocess.DEVNULL)
    else:
        p=subprocess.Popen([sys.executable,"-c",c],cwd=cwd,stdout=o,stderr=subprocess.STDOUT,start_new_session=True,stdin=subprocess.DEVNULL)
    try:
        p.wait(timeout=600)
    except KeyboardInterrupt:
        try: os.killpg(p.pid,signal.SIGKILL); p.wait(timeout=3)
        except Exception: pass
        raise
    o.seek(0); return (o.read().decode("utf-8","replace") or "(no output)")

# ==================== TOOL ROUTER: alege AUTOMAT python vs bash ====================
# Euristici bazate pe masuratori reale (teste 1-3): bash castiga pe fluxuri/volum/paralelism,
# python castiga pe parsare structurata + logica. Routerul decide inainte de a executa.
PY_STRUCT = (r"\bjson\b", r"\bimport\s+json", r"json\.loads", r"json\.load\b", r"\.ini\b",
             r"configparser", r"def\s+\w+\(", r"class\s+\w+", r"\bCounter\b", r"collections",
             r"re\.(findall|search|match|sub)", r"dict\(|defaultdict", r"\.get\(", r"\blambda\b",
             r"os\.walk", r"glob\.", r"shutil\.", r"struct\.", r"\bdataclass\b", r"yield\b",
             r"\btry:", r"\bexcept\b", r"\.items\(\)", r"\.keys\(\)", r"\.values\(\)")
# BASH_STREAM: ONLY the tools where toybox genuinely WINS on this device (measured):
# pure pass-through streaming (cat/wc/head/tail/tr), early-exit search (grep -m1), native-C hashing,
# filesystem walks (find/du/df), and parallel small-file work (xargs -P). NOT sort/awk/sed/cut/uniq/base64:
# on this toybox build those are 3-95x SLOWER than the python equivalent, so they route to python.
BASH_STREAM = (r"\bgrep\b", r"\bwc\b", r"\bcat\b", r"\bhead\b", r"\btail\b", r"\btr\b",
               r"\bcut\b", r"\bxargs\b", r"\bfind\b", r"\bdu\b", r"\bdf\b", r"\brsync\b",
               r"\bzgrep\b", r"\bsha256sum\b", r"\bmd5sum\b", r"\bpaste\b", r"\bparallel\b",
               r"-P\s*\d", r"\bgrep\s+-[a-z]*c\b", r"\bgrep\s+-[a-z]*m\s*\d")
# BASH_SLOW: toybox commands that LOOK like stream tools but are pathologically slow here -> force python.
BASH_SLOW = (r"\bsort\b", r"\bawk\b", r"\bsed\b", r"\buniq\b", r"\bbase64\b", r"\bjoin\b")
BASH_HEAVY = (r"\.log\b", r"/var/log", r">\s*\d{6,}", r"\bfor\s+\w+\s+in\b", r"\bseq\b")

def route(cmd="", code=""):
    """Decide engine = 'bash' or 'python' from what is about to happen, using the numbers measured
    on THIS device (see BASH_STREAM / BASH_SLOW above). Priority: python-structure > toybox-slow >
    pure-bash-stream > parallel-small-files > default python."""
    c = (cmd or "").strip()
    k = (code or "").strip()
    t = (c + "\n" + k).lower()
    # 0) an explicit python tool block always stays python
    py_hits = sum(1 for pat in PY_STRUCT if re.search(pat, k))
    if py_hits >= 2:
        return "python", f"structured logic detected ({py_hits} python-structure signals): parsing/logic is where python wins"
    # 1) toybox tools that are pathologically slow here (sort/awk/sed/uniq/base64/join):
    #    if the command ONLY uses those (plus trivial plumbing) python is the faster engine.
    if c and re.search(r"\b(sort|awk|sed|uniq|base64|join)\b", c):
        # unless the SAME command also leans on a true bash win (grep -m1 early exit / xargs -P)
        if not (re.search(r"\bgrep\b", c) and re.search(r"-[a-z]*m\s*\d", c)) and not re.search(r"xargs[^|]*-P\s*\d", c) and not re.search(r"\bsha256sum\b|\bmd5sum\b", c):
            _slow = [w for w in ("sort", "awk", "sed", "uniq", "base64", "join") if re.search(r"\b" + w + r"\b", c)]
            return "python", f"toybox {','.join(_slow)} is 3-95x slower here than python -> overflow to python"
    # 2) pure bash stream / early-exit / native-C hashing -> bash
    sh_hits = sum(1 for pat in BASH_STREAM if re.search(pat, c or k))
    heavy = any(re.search(pat, t) for pat in BASH_HEAVY)
    if c and sh_hits >= 1:
        why = f"pure stream/early-exit detected ({sh_hits} bash-win signals)"
        if heavy: why += "; large streamed data -> bash (less memory, native C)"
        return "bash", why
    # 3) many small files in parallel -> bash (xargs -P uses all cores)
    if c and re.search(r"xargs", c) and re.search(r"-P\s*\d", c):
        return "bash", "many small files in parallel -> bash xargs -P (all cores)"
    # 4) mostly python-shaped (a single structure signal) -> python
    if py_hits == 1:
        return "python", "mostly python-shaped task (single structure signal)"
    # 5) default: python (the fastest engine on this device for anything not a pure stream)
    return "python", "default: python (fastest here except pure streams; explicit `bash` for those)"

def bash(cmd, cwd):
    """Ruleaza o comanda shell (bash -lc) in propriul grup de procese; Ctrl+C omoara doar acest
    tool. Intoarce stdout+stderr combinat, trunchiat la 8000 de caractere (ca la python)."""
    o=tempfile.TemporaryFile(dir=WORK)
    p=subprocess.Popen(SHELL[0]+(cmd,),cwd=cwd,stdout=o,stderr=subprocess.STDOUT,start_new_session=True,stdin=subprocess.DEVNULL)
    try:
        p.wait(timeout=600)
    except KeyboardInterrupt:
        try: os.killpg(p.pid,signal.SIGKILL); p.wait(timeout=3)
        except Exception: pass
        raise
    o.seek(0); return (o.read().decode("utf-8","replace") or "(no output)")

def run_bash_tool(cmd):
    """Wrapper cu acelasi contor de pasi si aceeasi linie de afisare ca run_tool."""
    n=TASK["steps"]+1; dsc="bash: "+_short(cmd,58); col=HCLR[sum(map(ord,dsc))%len(HCLR)] if dsc else G
    o=_spin(bash,cmd,os.getcwd(),phase="tool",desc=dsc,col=col); cut,ref=_store(o)
    TN[0]+=1; TASK.update(steps=n,chars=TASK["chars"]+len(o))
    _show_step(cmd,cut,n)
    if _looks_like_error(o): TASK["err"]=True
    return cut

def run_read_tool(path, offset=0, limit=4000):
    """Citeste un FISIER (ex. un log de tool trunchiat) de la un offset, cu o limita.
    Nu incarca tot in context: agentul poate pagina prin fisiere mari citind bucati.
    Intoarce textul cerut + un header care arata intervalul si cate caractere mai sunt."""
    import os as _os
    try:
        offset=int(offset); limit=int(limit)
    except Exception:
        offset, limit = 0, 4000
    if limit <= 0 or limit > 20000: limit = 20000 if limit > 20000 else 4000
    if offset < 0: offset = 0
    try:
        p = path if _os.path.isabs(path) else _os.path.join(WORK, path)
        tot = _os.path.getsize(p)
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            f.seek(offset)
            chunk = f.read(limit)
        n = len(chunk)
        end = offset + n
        hdr = "[read "+ _os.path.basename(p) +" | bytes "+str(offset)+"-"+str(end)+" of "+str(tot)
        if end < tot:
            hdr += " | MORE: call read path="+path+" offset="+str(end)+" limit="+str(limit)
        else:
            hdr += " | EOF"
        hdr += "]\n"
        o = hdr + chunk
    except Exception as e:
        o = "(read failed: "+str(e)+")"
    _step_show = "read "+str(path)+(" @"+str(offset) if offset else "")
    n=TASK["steps"]+1
    dsc="read: "+_short(str(path),58); col=HCLR[sum(map(ord,dsc))%len(HCLR)]
    TN[0]+=1; TASK.update(steps=n,chars=TASK["chars"]+len(o))
    _show_step(_step_show, o, n)
    return o

def _looks_like_error(o):
    """Cheap heuristic: does this tool output contain a FAILURE (traceback, a Python
    Error/Exception, a shell failure, a denied/missing path)? Sets TASK['err'] so the
    footer can show that a step failed. False positives are harmless."""
    if not o: return False
    lo = o.lower()
    if "traceback (most recent call last)" in lo: return True
    # Python exceptions: SyntaxError, ValueError, KeyError, OSError, ... (one token, no space)
    if re.search(r"\b\w*(error|exception)\b", lo): return True
    # shell / OS failures common on this device
    if re.search(r"\b(failed|failure|denied|refused|unreachable|timeout|timed out|"
                 r"non-zero exit status|exit status [1-9]|command not found|not found|"
                 r"no such file|inaccessible|permission denied|operation not permitted|"
                 r"errno|eacces|enoent|enospc|read-only file system|segmentation fault|"
                 r"cannot (access|open|create|execute|stat)|unable to)\b", lo):
        return True
    return False

def _bg_load():
    try:
        with open(BG_REG, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _bg_save(d):
    try:
        os.makedirs(os.path.dirname(BG_REG), exist_ok=True)
        with open(BG_REG, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=1)
    except Exception:
        pass


MAX_JOBS = 20          # ★ P4: cate joburi terminate pastram
MAX_JOB_AGE = 24*3600  # ★ P4: cat timp pastram un job terminat (secunde)


def _bg_autoclean(reg):
    """★ P4: colector de stare acumulata. Sterge joburile terminate mai vechi de
    MAX_JOB_AGE si, daca tot sunt > MAX_JOBS, pe cele mai vechi. Fara efecte pe
    joburile inca in lucru. Salveaza registrul doar daca a modificat ceva."""
    now = time.time()
    gone = []
    for k, j in list(reg.items()):
        if j.get("status") not in ("done", "killed"):
            continue
        age = now - j.get("ts", now)
        if age > MAX_JOB_AGE:
            gone.append(k)
    rest = [(k, j) for k, j in reg.items() if k not in gone
            and j.get("status") in ("done", "killed")]
    rest.sort(key=lambda kv: kv[1].get("ts", 0))
    while len(rest) > MAX_JOBS:
        gone.append(rest.pop(0)[0])
    for k in gone:
        try: run_adbsh_tool("rm -f %s" % reg[k]["log"], 30)
        except Exception: pass
        reg.pop(k, None)
    if gone:
        _bg_save(reg)
    return gone


def bg_tool(a):
    """Gestionar de procese in fundal. Actiuni:
       start <cmd> [name]  - lanseaza in fundal cu log unic + registru
       status             - ce ruleaza acum (PID viu?), cu durata si marimea log-ului
       log <job> [n]      - ultimele n linii din log-ul ACELUI job (nu ghicit)
       kill <job>         - opreste job-ul (proces + copii)
       clean              - sterge job-urile terminate si log-urile lor
       list               - toate job-urile (inclusiv terminate)
    """
    act = (a.get("action") or "status").strip()
    reg = _bg_load()
    # ★ P4: auto-curatare (stare care se acumula fara colector) - ruleaza la fiecare apel
    try:
        _bg_autoclean(reg)
    except Exception:
        pass

    if act == "start":
        cmd = (a.get("cmd") or "").strip()
        if not cmd:
            return "lipseste 'cmd'"
        name = (a.get("name") or "job").strip().replace(" ", "_")[:24]
        ts = time.strftime("%Y%m%d-%H%M%S")
        jid = "%s_%s" % (name, ts)
        log = "%s/%s.log" % (BG_LOG, jid)
        # rulam prin adbsh: script cu nohup, PID inregistrat, log unic
        sh = ("mkdir -p %s; cd /data/local/tmp; "
              "nohup /system/bin/sh -c %s > %s 2>&1 & echo $!") % (
                  BG_LOG, _shell_q(cmd), _shell_q(log))
        try:
            out = run_adbsh_tool(sh, 60)
        except Exception as e:
            return "start error: %s" % e
        import re as _re
        m = _re.search(r"(\d{4,})", out or "")
        pid = int(m.group(1)) if m else 0
        reg[jid] = {"pid": pid, "name": name, "cmd": cmd, "log": log,
                    "started": time.strftime("%Y-%m-%d %H:%M:%S"), "ts": time.time(),
                    "status": "running"}
        _bg_save(reg)
        return ("job pornit: %s\n  pid=%d\n  log=%s\n"
                "  (verifica progresul cu bg action=status, apoi bg action=log job=%s)"
                % (jid, pid, log, jid))

    if act in ("status", "list"):
        rows = []
        for jid, j in reg.items():
            pid = j.get("pid", 0)
            # liveness REAL (nu presupus): /proc/<pid> exista si nu e zombie
            alive = "?"
            try:
                st = run_adbsh_tool(
                    "test -d /proc/%d && (cat /proc/%d/stat 2>/dev/null | cut -d' ' -f3) || echo DEAD"
                    % (pid, pid), 30).strip()
                alive = "RUNNING" if st and st not in ("DEAD", "Z") else "DONE"
            except Exception:
                pass
            try:
                sz = run_adbsh_tool("wc -c < %s 2>/dev/null || echo 0" % j["log"], 30).strip().split()[0]
            except Exception:
                sz = "0"
            dur = int(time.time() - j.get("ts", time.time()))
            rows.append("%-28s %-8s pid=%-6d %4ds  log=%s bytes  | %s"
                        % (jid, alive, pid, dur, sz, j.get("cmd", "")[:40]))
            if alive == "DONE" and j.get("status") == "running":
                j["status"] = "done"; j["ended"] = time.strftime("%Y-%m-%d %H:%M:%S")
        _bg_save(reg)
        if not rows:
            return "niciun job inregistrat (bg action=start pentru a lansa unul)"
        if act == "status":
            rows = [r for r in rows if "RUNNING" in r] or ["(niciun job activ; vezi bg action=list)"]
        return "JOBURI:\n" + "\n".join(rows)

    if act == "log":
        jid = (a.get("job") or "").strip()
        n = int(a.get("lines") or 40)
        if not jid:
            return "lipseste 'job' (vezi bg action=list)"
        j = None
        for k in reg:
            if k == jid or k.startswith(jid):
                j = reg[k]; jid = k; break
        if not j:
            return "job necunoscut: %s" % jid
        out = run_adbsh_tool("tail -n %d %s 2>/dev/null" % (n, j["log"]), 60)
        hdr = ("=== %s (pornit %s, pid %d) ===\n" % (jid, j.get("started"), j.get("pid", 0)))
        return hdr + (out or "(log gol)")

    if act == "kill":
        jid = (a.get("job") or "").strip()
        j = None
        for k in reg:
            if k == jid or k.startswith(jid):
                j = reg[k]; jid = k; break
        if not j:
            return "job necunoscut: %s" % jid
        pid = j.get("pid", 0)
        run_adbsh_tool("kill -9 %d 2>/dev/null; pkill -9 -P %d 2>/dev/null; echo killed" % (pid, pid), 60)
        j["status"] = "killed"; j["ended"] = time.strftime("%Y-%m-%d %H:%M:%S")
        _bg_save(reg)
        return "job oprit: %s (pid %d)" % (jid, pid)

    if act == "clean":
        gone = [k for k, j in reg.items() if j.get("status") in ("done", "killed")]
        for k in gone:
            try: run_adbsh_tool("rm -f %s" % reg[k]["log"], 30)
            except Exception: pass
            reg.pop(k, None)
        _bg_save(reg)
        return "curatate %d job-uri terminate" % len(gone)

    return "actiuni: start | status | list | log | kill | clean"


def _shell_q(s):
    """Quoting sigur pentru shell (single quotes)."""
    return "'" + str(s).replace("'", "'\\''") + "'"


def run_adbsh_tool(cmd, timeout=20):
    """SHELL ca user 'shell' (uid=2000) prin clientul ADB pur-Python (adb_client).

    ★ REWRITE PYTHON-FIRST (decizie operator, dupa blocajele repetate ale vechiului tool):
    Vechea implementare tinea o conexiune persistenta globala (_ADBCONN) + un liveness
    check manual (MSG_PEEK) + reintegrare manuala pe socket: o singura comanda care agata
    (ex. un binar din toolchain care nu-si gaseste libs) lasa SESIUNEA ZOMBI deschisa si
    bloca TOT adbsh-ul de acolo inainte - exact simptomul raportat (echo merge, apoi dupa
    un 'git' nu mai merge nimic).
    Acum: fiecare comanda trece prin adb_client.shared().shell(), care are deja
      - _SOCK_LOCK (serializare pe socket, fara suprapuneri intre threaduri)
      - deadline la drenare (nu mai exista bucla fara limita)
      - auto-heal (_poisoned => reconectare curata)
    Nu mai exista conexiune persistenta proprie si nici verificari manuale de liveness:
    starea o gestioneaza adb_client, intr-un singur loc.
    """
    import importlib.util as _iu
    global _ADBCLI
    try:
        _ADBCLI
    except NameError:
        _ADBCLI = None
    if _ADBCLI is None:
        here = os.path.dirname(os.path.abspath(__file__))
        try:
            sp = _iu.spec_from_file_location("adb_client", os.path.join(here, "adb_client.py"))
            _ADBCLI = _iu.module_from_spec(sp); sp.loader.exec_module(_ADBCLI)
        except Exception as e:
            _ADBCLI = False
            _err = "adbsh unavailable: " + str(e)
    if not _ADBCLI:
        o = _err if isinstance(_err, str) else "adbsh unavailable"
        _show_step("adbsh", o, TASK["steps"]); return o

    dsc = "adbsh: " + cmd[:60]
    to = max(5, min(int(timeout), 3600))

    # ★ FIX (raportat de agent: "adbsh nu executa nimic, intoarce mereu \x03\x01\x00\x00\x00\x01"):
    # NU mai sursam toolchain_env.sh aici. Acel fisier e in filesDir (APP-PRIVATE): shell-ul
    # uid=2000 NU il poate citi -> "Permission denied" + protocol desync (răspuns binar rezidual).
    # Orice output binar rezidual facea ca TOATE comenzile adbsh sa intoarca blob-ul acela.
    # Toolchain-ul e al aplicatiei (binarele sunt in nativeLibraryDir, neexecutabile de shell),
    # deci prefixarea nu aducea oricum nimic util in shell-ul adbd.
    _wrapped = cmd

    def _run():
        # bucla de retry: daca raspunsul e gol/neconfirmat, o singura reincercare dupa
        # o reconectare curata (auto-heal). Marker unic = dovada ca raspunsul e al nostru.
        import time as _t
        last = ""
        for attempt in (1, 2):
            try:
                conn = _ADBCLI.shared()
                mk = "__MK" + str(int(_t.time() * 1000) % 10**9) + "__"
                out = conn.shell("echo " + mk + "; " + _wrapped, timeout=to)
            except Exception as e:
                _m = str(e)[:200]
                if ("timed out" in _m.lower()) or ("auth" in _m.lower()) or ("connection" in _m.lower()):
                    return ("adbsh: conexiunea ADB cere AUTORIZARE (adbd a afisat dialogul "
                            "Allow USB debugging si nimeni nu a raspuns).\n"
                            "REMEDIU (o singura data, pe telefon): Settings -> Developer options "
                            "-> dezactiveaza si reactiveaza USB debugging, apoi la urmatorul "
                            "dialog apasa Allow CU bifa Always allow from this computer.\n"
                            "Detaliu: " + _m)
                return "adbsh error: " + _m
            if mk in out:
                out = out.replace(mk + "\n", "", 1).replace(mk, "", 1)
                # ★ FAZA 4k: desync de protocol. Cand răspunsul conține doar bytes de control
                # (ex. "\x03\x01\x00\x00\x00\x01" - rezultatul desincronizarii pe un fisier
                # app-private), NU-l returna ca output real: reconecteaza si reincearca o data.
                if out and not any((c.isprintable() or c in "\n\r\t") for c in out):
                    last = out
                    if attempt == 1:
                        try:
                            _ADBCLI.force_reconnect()
                            _t.sleep(0.2)
                        except Exception:
                            pass
                        continue
                    return ("[adb] desync de protocol (raspuns binar): comanda NU a fost confirmata: "
                            + cmd[:60])
                return out
            last = out
            # marker lipsa = raspuns strain sau gol: reconectam o data si reincercam
            if attempt == 1:
                try:
                    _ADBCLI.force_reconnect()
                    _t.sleep(0.2)
                except Exception:
                    pass
        return ("[adb] protocol desync - marker-ul nu a revenit de 2 ori; comanda NU e "
                "confirmata: " + cmd[:80] + ("\n(ultim raspuns: " + last[:120] + ")" if last else ""))

    try:
        o = _spin(_run, phase="tool", desc=dsc, col=HCLR[sum(map(ord, dsc)) % len(HCLR)])
    except Exception as e:
        o = "adbsh error: " + str(e)
    TN[0] += 1; TASK.update(steps=TASK["steps"] + 1, chars=TASK["chars"] + len(o))
    _show_step(dsc, o, TASK["steps"])
    return o

def run_android_tool(tool, action, params):
    """Ruleaza un tool nativ Android prin bridge-ul Kotlin (socket local).
    Intoarce textul (JSON compact) trimis modelului, cu acelasi contor de pasi."""
    import importlib.util as _iu
    global _ABRIDGE
    try:
        _ABRIDGE
    except NameError:
        _ABRIDGE=None
    if _ABRIDGE is None:
        try:
            sp=_iu.spec_from_file_location("android_bridge", os.path.join(os.path.dirname(os.path.abspath(__file__)),"android_bridge.py"))
            _ABRIDGE=_iu.module_from_spec(sp); sp.loader.exec_module(_ABRIDGE)
        except Exception as e:
            _ABRIDGE=False
    if not _ABRIDGE:
        o="android tool unavailable: bridge module not loaded"
        _show_step("android "+tool+(" "+action if action else ""), o, TASK["steps"])
        return o
    dsc="android: "+tool+("."+action if action else "")
    try:
        o=_spin(lambda: json.dumps(_ABRIDGE.call(tool, action, **params), ensure_ascii=False, indent=1),
                phase="tool", desc=dsc, col=HCLR[sum(map(ord,dsc))%len(HCLR)])
    except Exception as e:
        o="android error: "+str(e)
    TN[0]+=1; TASK.update(steps=TASK["steps"]+1,chars=TASK["chars"]+len(o))
    _show_step(dsc+"  <- "+json.dumps(params, ensure_ascii=False)[:60], o, TASK["steps"])
    # Trunchiere INTELIGENTA: ui read compact (text lizibil) e dens, deci primeste mai mult
    # spatiu; JSON-ul umflat (tree) ramine la 8000. Marcam clar ca s-a taiat, ca modelul sa
    # stie sa ceara mai putin (max/depth) sau sa foloseasca action="find".
    _lim = 12000 if (tool=="ui" and action in ("read","screen","tree","find","search") and ("\"text\"" in o or "\"matches\"" in o)) else 8000
    if len(o) > _lim:
        _taie = o[:_lim] + "\n... [TRUNCHIAT la %d chars din %d. Pentru mai putin zgomot: ui read cu max/depth mici, SAU ui find <text> ca sa cauti direct un nod.]" % (_lim, len(o))
        return _taie
    return o



def run_multi_tool(ops):
    """BATCH runner: several SMALL independent operations in ONE tool call, ONE consolidated answer.
    Why: every request re-sends the whole context, so 6 little steps cost 6x the context; run as one
    call they cost once. Design rules that keep it SAFE on the phone:
      - each entry is independent (no entry depends on a previous one's output),
      - each entry is small and short-lived (a listing, a short cat, a status),
      - one entry failing NEVER aborts the others (its error is shown in place),
      - the total output is budgeted, so the answer cannot grow past the window limit."""
    if not isinstance(ops, list) or not ops:
        o = "[multi] give a list of 1-6 ops"
        n=TASK["steps"]+1; TN[0]+=1; TASK.update(steps=n,chars=TASK["chars"]+len(o))
        _show_step("multi (no ops)", o, n); return o
    ops = ops[:6]                     # hard cap: 6 entries max
    out = ["[multi] " + str(len(ops)) + " operations, ONE call (cost: 1 request instead of " + str(len(ops)) + ")"]
    for k, op in enumerate(ops, 1):
        kind = (op.get("kind") or "bash").strip()
        body = str(op.get("body") or "")
        nm = (op.get("name") or "").strip() or (kind + " " + str(k))
        head = "--- [" + str(k) + "] " + nm + " (" + kind + ") ---"
        if not body.strip():
            out.append(head + "\n(empty body - skipped)"); continue
        if kind not in ("python", "bash"):
            out.append(head + "\n(kind necunoscut %r - pune codul in body cu kind=python, sau "
                       "kind=bash pentru shell; uneltele native (toolchain/android) se cheama "
                       "din COD python)" % kind)
            continue
        try:
            r = run_tool(body) if kind == "python" else run_bash_tool(body)
            r = (r or "").rstrip()
        except Exception as e:
            r = "!! FAILED (isolated, the others still ran): " + e.__class__.__name__ + ": " + str(e)
        # per-entry cap so one huge entry cannot blow the whole answer (scaled to CHUNK)
        _cap = max(4000, _budget() // max(1, len(ops)))
        if len(r) > _cap:
            _keep = _cap - 600
            r = r[:_keep] + "\n[... " + str(len(r)-_keep-400) + " chars omitted - use the `read` tool if you need them ...]\n" + r[-400:]
        out.append(head + "\n" + (r if r else "(no output)"))
    o = "\n".join(out)
    if len(o) > _budget():
        o = o[:_budget()-400] + "\n[... total capped; run fewer/smaller ops ...]"
    n=TASK["steps"]+1
    dsc="multi: "+str(len(ops))+" ops"; col=HCLR[sum(map(ord,dsc))%len(HCLR)]
    TN[0]+=1; TASK.update(steps=n,chars=TASK["chars"]+len(o))
    _show_step("multi "+str(len(ops))+" ops", o, n)
    return o

def run_help_tool(a):
    """Return the FULL guide for an advanced Android topic ON DEMAND. Why: the detailed
    reflection/objects/privileged reference is ~2300 chars (~580 tok) and would be re-sent
    on EVERY request if kept in the fixed prompt. Here it costs only when actually needed."""
    t=(a.get("topic") or "all").strip().lower()
    if t=="all":
        o="\n\n".join("[help] "+k.upper()+"\n"+v for k,v in HELP_TEXT.items())
    elif t in HELP_TEXT:
        o="[help: "+t+"]\n"+HELP_TEXT[t]
    else:
        o="[help] unknown topic "+repr(t)+". Available: "+", ".join(HELP_TEXT)+", all"
    n=TASK["steps"]+1; TN[0]+=1
    TASK.update(steps=n,chars=TASK["chars"]+len(o))
    _show_step("help "+t, o, n)
    return o

def call_tool(c):
    """Dispatches ONE tool_call: `python` runs code, `look` sends an image to the VISION
    endpoint (thinking ON). Both increment the SAME step counter and print the SAME column
    layout, so the operator sees every step the same way. Returns what goes to the model."""
    fn=c["function"]["name"]; a=json.loads(c["function"]["arguments"] or "{}")
    if fn=="look":
        dsc="looks at "+(os.path.basename(a.get("path","")) or "the image")
        o=_spin(vision,a.get("path",""),a.get("prompt",""),phase="tool",desc=dsc,col=HCLR[sum(map(ord,dsc))%len(HCLR)])
        TN[0]+=1; TASK.update(steps=TASK["steps"]+1,chars=TASK["chars"]+len(o)); _show_step("look "+a.get("path","")+"  <- "+(a.get("prompt","") or "").strip(),o,TASK["steps"])   # FULL prompt
        return o
    if fn=="bash":
        return run_bash_tool(a.get("cmd",""))
    if fn=="read":
        return run_read_tool(a.get("path",""), a.get("offset",0), a.get("limit",4000))
    if fn=="multi":
        return run_multi_tool(a.get("ops") or [])
    if fn=="smart":
        cmd=a.get("cmd","") or ""; code=a.get("code","") or ""
        eng,why=route(cmd,code)
        print(BAR+"   "+TC+"[smart]"+N+" "+TCB+" engine = "+eng+N+"  "+SD+why+N)
        if eng=="bash" and cmd.strip():
            return run_bash_tool(cmd)
        if eng=="python" and code.strip():
            return run_tool(code)
        # fallback: ce a dat modelul, indiferent de engine
        return run_tool(code) if code.strip() else run_bash_tool(cmd)
    if fn=="android":
        return run_android_tool(a.get("tool",""), a.get("action",""), a.get("params",{}) or {})
    if fn=="bg":
        return bg_tool(a)
    if fn=="adbsh":
        return run_adbsh_tool(a.get("cmd",""), int(a.get("timeout",20) or 20))
    if fn=="toolchain":
        return run_toolchain_tool(a)
    if fn=="help":
        return run_help_tool(a)
    return run_tool(a.get("code",""))

def _uses_python_h(path):
    """True daca sursa include Python.h (pentru a adauga automat -lpython3.14)."""
    try:
        return "Python.h" in open(path, encoding="utf-8", errors="ignore").read()
    except Exception:
        return False


def run_toolchain_tool(a):
    """Toolchain nativ de compilare pe telefon (clang, pip, meson...)."""
    import subprocess as _sp
    action = (a.get("action") or "status").strip()
    here = os.path.dirname(os.path.abspath(__file__))
    tc = os.path.join(here, "toolchain.py")

    # ★ FIX: pyhome traieste in filesDir (stocarea privata), NU in AGENT_HOME (sdcard).
    # Vechiul cod lua AGENT_HOME -> pip_install cauta zip-urile in /storage/... si esua.
    F = "/data/data/net.sys32.agent/files"
    ROOT = "/data/data/net.sys32.agent/files/toolchain"
    BIN = ROOT + "/bin"

    def _toolchain_exports():
        """Export-uri shell cu mediul COMPLET de compilare (toolchain din APK)."""
        e = {}
        try:
            import importlib.util as _ilu
            spec = _ilu.spec_from_file_location("_tc_env", tc)
            mod = _ilu.module_from_spec(spec)
            spec.loader.exec_module(mod)
            e = mod.env_vars()
        except Exception:
            pass
        if not e:
            e = {"PATH": ROOT + "/deps/bin:" + ROOT + "/bin:/system/bin"}
        # ★ FIX (raportat de agent): cheile cu cratime (CC_aarch64-linux-android) nu sunt
        # identificatori shell valizi -> "export: ...: is not an identifier" la sursare.
        e = {k: v for k, v in e.items() if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", str(k))}
        parts = []
        for k, v in e.items():
            if v is None: continue
            parts.append("export %s='%s'" % (k, str(v).replace("'", "'\\''")) )
        return "; ".join(parts) + "; "
    def _env():
        """Mediul COMPLET pentru toolchain-ul din APK.

        ★ SURSĂ UNICĂ DE ADEVĂR: toolchain.env_vars(). Vechiul cod hardcoda
        BIN+"/clang-21" (neexecutabil ca untrusted_app) -> TOATE build-urile C
        esuau cu "Permission denied", desi toolchain-ul exista.
        env_vars() stie de nativeLibraryDir (singurul loc executabil).
        """
        e = dict(os.environ)
        try:
            import importlib.util as _ilu
            _sp2 = _ilu.spec_from_file_location("_tc_vars", tc)
            _m2 = _ilu.module_from_spec(_sp2); _sp2.loader.exec_module(_m2)
            e.update({k: v for k, v in _m2.env_vars().items() if v})
        except Exception:
            pass
        if not e.get("CC"):
            e["CC"] = BIN + "/clang-21"
        e["PYTHONHOME"] = F + "/pyhome"
        # ★ ORDINEA CONTEAZA (bug raportat de agent): stdlib_extra.zip PRIMUL - are zipfile._path
        # de care depinde importlib.metadata (pip); altfel: KeyError('prefix'), exit 1 in 0s.
        e["PYTHONPATH"] = (F + "/pyhome/lib/stdlib_extra.zip:" + F +
                           "/pyhome/lib/pysitepkg.zip:" + here)
        e["LD_LIBRARY_PATH"] = _clean_ld(e.get("LD_LIBRARY_PATH", ""))
        e["TMPDIR"] = F + "/tmp"
        try:
            os.makedirs(e["TMPDIR"], exist_ok=True)
        except Exception:
            pass
        return e
    def _run(cmd, timeout=300):
        """Ruleaza toolchain.py. ★ INLINE cand se poate (acelasi proces), ca sa
        refolosim conexiunea ADB partajata: altfel fiecare subproces face
        connect() NOU si adbd cere aprobarea 'Allow USB debugging' iar si iar
        (simptomul raportat de operator)."""
        # daca comanda e [python, toolchain.py, actiune, ...] o rulam inline
        try:
            _act0 = cmd[2] if len(cmd) > 2 else ""
            _NOINLINE = ("install",)
            if (len(cmd) >= 2 and str(cmd[0]).endswith(("python3", "python", "libpyexec.so"))
                    and os.path.basename(str(cmd[1])) == "toolchain.py"
                    and _act0 not in _NOINLINE):
                import importlib.util as _ilu2
                _spec = _ilu2.spec_from_file_location("_tc_inline", tc)
                _mod = _ilu2.module_from_spec(_spec)
                _spec.loader.exec_module(_mod)
                _act = cmd[2] if len(cmd) > 2 else "check"
                _extra = cmd[3] if len(cmd) > 3 else None
                import io as _io, contextlib as _cl
                _buf = _io.StringIO()
                with _cl.redirect_stdout(_buf), _cl.redirect_stderr(_buf):
                    if _act == "check":
                        print(json.dumps(_mod.check(), indent=2))
                    elif _act == "doctor":
                        print(json.dumps(_mod.doctor(), indent=2))
                    elif _act == "selftest":
                        # ★ FAZA 0A: ce POATE compila/linka agentul ACUM, pe acest device
                        print(json.dumps(_mod.selftest(), indent=2))
                    elif _act == "preflight":
                        print(json.dumps(_mod.preflight(), indent=2))
                    elif _act == "profile":
                        print(_mod.profile(_extra or "cmake"))
                    elif _act == "env":
                        # ★ OPTIMIZARE (analiza conversatiei): dump-ul complet de exports era
                        # ~7.4 KB (cel mai mare mesaj din context) si se re-trimitea la fiecare
                        # pas. Acum: pe scurt + EXEMPLE gata de copiat (agentul pierdea pasi
                        # ghicind flag-uri: -latomic, --target, -resource-dir) + build-dir corect.
                        # ★ FIX (raportat de agent): fisierul la care trimiteam NU era scris
                        # ("toolchain_env.sh: No such file or directory") - il scriem ACUM.
                        try:
                            _mod._write_env_file()
                        except Exception:
                            pass
                        _e = _mod.env_vars()
                        _P = _mod.ROOT
                        print("[toolchain env] prefix=%s  (exports complete: %s/toolchain_env.sh)" % (_P, _mod.F))
                        for _k in ("PATH", "CC", "CXX", "AR", "CFLAGS", "LDFLAGS", "PKG_CONFIG_PATH"):
                            if _e.get(_k):
                                print("%s=%s" % (_k, _e[_k]))
                        print("EXEMPLE GATA DE COPIAT (fara ghicit de flag-uri):")
                        print("  C:       $CC s.c -o s_bin $LDFLAGS")
                        print("  C++:     $CXX -std=c++17 s.cpp -o s_bin $LDFLAGS")
                        print("  pyext:   $CC -shared -fPIC m.c -o m.so $LDFLAGS -lpython3.14")
                        print("  Fortran: %s/bin/flang t.f90 -o t_bin" % _P)
                        print("  Rust:    %s/bin/cargo build --release" % _P)
                        print("  cmake:   export PREFIX=%s && %s/bin/cmake -G Ninja -S . -B b && %s/bin/ninja -C b"
                              "   (fara PREFIX, CMakeDetermineSystem.cmake esueaza)" % (_P, _P, _P))
                        print("  RULARE:  /apex/com.android.runtime/bin/linker64 <binar>  (exec direct din filesDir e INTERZIS)")
                        print("  BUILD DIR: files/tmp sau workspace-ul app-ului; /sdcard e NOEXEC.")
                    elif _act == "env-file":
                        _mod._write_env_file(); print("fisier: %s/env.sh" % _mod.ROOT)



                        _mod.install()
                    elif _act == "fix":
                        for _fn in ("_prepare_dirs", "_patch_runpath", "_fix_ninja",
                                    "_fix_cc_wrappers", "_fix_symlinks", "_fix_wrappers_shebang",
                                    "_fix_sysconfig", "_fix_ca_bundle", "_fix_libcxx_needed",
                                    "_write_env_file"):
                            try: getattr(_mod, _fn)()
                            except Exception: pass
                        print(json.dumps(_mod.preflight(), indent=2))
                    else:
                        print("[inline] actiune necunoscuta: %s" % _act)
                return _buf.getvalue().strip()
        except Exception as _ie:
            pass   # fallback la subproces
        try:
            r = _sp.run(cmd, capture_output=True, text=True, timeout=timeout, env=_env(),
                        cwd="/data/local/tmp")
            return (r.stdout + r.stderr).strip()
        except _sp.TimeoutExpired:
            return "[timeout dupa %ss]" % timeout
        except Exception as ex:
            return "EROARE: " + str(ex)

    if action == "status":
        return _run([sys.executable, tc, "check"], 60)
    if action == "selftest":
        # ★ FAZA 0A (PLAN_AUTONOMIE.md): self-test de capabilitati - compileaza+linkeaza
        # REAL (C, C++ cu STL, extensie Python.h, Fortran) si raporteaza ce lipseste.
        # Ruleaza-l INAINTE sa promiti ca poti instala ceva.
        return _run([sys.executable, tc, "selftest"], 900)
    if action == "doctor":
        # ★ raportul numpy A6: sanatatea toolchain-ului din PERSPECTIVA FIECARUI uid.
        # Raspunde la "poate CINE CERE sa-l foloseasca?" - nu doar "exista pe disc?".
        return _run([sys.executable, tc, "doctor"], 300)
    if action == "preflight":
        # R2/R4 (raport llama.cpp): test minim (C, C++, math, SSL, make) INAINTE
        # de un build mare - prinde toate problemele de linkare in ~10 secunde
        return _run([sys.executable, tc, "preflight"], 300)
    if action == "profile":
        # R3/R4b: flaguri gata facute (cmake/cflags/ldflags) - nu le descoperi iar
        return _run([sys.executable, tc, "profile", (a.get("package") or "cmake")], 60)
    if action == "fix":
        # re-aplica fixurile de mediu (launchers, python3.pc, CA, env.sh)
        return _run([sys.executable, tc, "fix"], 1800)
    if action == "env-file":
        return _run([sys.executable, tc, "env-file"], 120)































































    if action == "env":
        return _run([sys.executable, tc, "env"], 30)
    if action == "pip_install":
        pkg = (a.get("package") or "").strip()
        if not pkg: return "lipseste 'package'"
        # ★ REWRITE (toolchain din APK): rulam pip CA APP (uid 10318), nu prin adbsh:
        # prefixul traieste in filesDir, shell-ul (uid 2000) nu-l poate scrie.
        # Env-ul complet (CC/LDSHARED/CFLAGS/sysroot/libxml2) vine din _env().
        try:
            _e = _env()
            _e["PYTHONPATH"] = (F + "/pyhome/lib/stdlib_extra.zip:" + F +
                                "/pyhome/lib/pysitepkg.zip:" + here)
            # ★ -S + sitecustomize: garanteaza ca zip-urile (pip!) sunt in sys.path
            # chiar daca PYTHONPATH nu ajunge la subproces.
            _t0 = time.time()
            # ★ CRUCIAL: `-m pip` NU vede PYTHONPATH cand PYTHONHOME e setat (libpyexec
            # ignora env-ul la modulele -m). Injectam zip-urile DIRECT in sys.path prin -c.
            _zp = F + "/pyhome/lib/pysitepkg.zip"
            _ze = F + "/pyhome/lib/stdlib_extra.zip"
            _noiso = "--no-build-isolation " if "--no-build-isolation" not in pkg else ""
            _code = ("import sys;"
                     "sys.path[:0]=[r'%s',r'%s'];"
                     "from pip._internal.cli.main import main as _m;"
                     "sys.exit(_m(['install','--no-cache-dir','--disable-pip-version-check',%s%r]))"
                     % (_ze, _zp, _noiso and "'--no-build-isolation'," or "", pkg))
            # ★ FIX CRASH -11 (28 sept): pe Android `sys.executable` = libpyexec.so, iar un
            # subproces `libpyexec.so <script>` murea instant (SIGSEGV) pentru ca
            # LD_LIBRARY_PATH continea directorul de STUB-uri NDK (sysroot) -> libc stubbed.
            # Reparat la sursa in toolchain._rt_ld_path()/_clean_ld(). Acum subprocesele
            # pip (build backend / metadata) RULEAZA normal, deci pip poate folosi
            # backend-ul in mediul lui.
            # ★ AUTO-RETRY: prima incercare cu --no-build-isolation (rapid, deps preinstalate
            # in pysitepkg.zip); daca build-backend-ul cere un modul care lipseste
            # (ModuleNotFoundError), reincercam CU izolare (pip descarca backend-ul).
            _zp0 = F + "/pyhome/lib/pysitepkg.zip"
            _ze0 = F + "/pyhome/lib/stdlib_extra.zip"
            _wh = F + "/wheels"          # ★ FAZA 0C: wheelhouse local
            try:
                os.makedirs(_wh, exist_ok=True)
            except Exception:
                pass

            def _pip_main(args):
                """Ruleaza pip INTR-UN SUBPROCES (nu in-process!).

                ★ FIX (raportat de agent, testul "fa test complet toolchain"): varianta in-process
                (from pip._internal.cli.main import main) crapa cu KeyError('prefix') pentru ca
                pip isi citeste configuratia schemei din propriul proces, iar procesul agentului nu
                are mediul pip corect (sysconfig/purelib). Subprocesul are env-ul complet
                (env_vars + PYTHONPATH cu stdlib_extra.zip PRIMUL) - exact calea care merge
                dovedit (pip install lxml a functionat prin subproces).
                """
                _bp2 = io.StringIO()
                _code = ("import sys;"
                         "sys.path[:0]=[r'%s',r'%s',r'%s'];"
                         "from pip._internal.cli.main import main as _m;"
                         "sys.exit(_m(%r))" % (_ze0, _zp0, _wh, list(args)))
                _pe_env = dict(_env())
                _pe_env["PYTHONHOME"] = F + "/pyhome"
                _pe_env["PYTHONPATH"] = "%s/stdlib_extra.zip:%s/pysitepkg.zip:%s" % (
                    F + "/pyhome/lib", F + "/pyhome/lib", F + "/python")
                _pe_env["TMPDIR"] = F + "/tmp"
                _pe_env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
                try:
                    _p = subprocess.run([sys.executable, "-c", _code], capture_output=True,
                                        text=True, timeout=3600, env=_pe_env, cwd=F + "/tmp",
                                        stdin=subprocess.DEVNULL)
                    return int(_p.returncode), ((_p.stdout or "") + (_p.stderr or ""))
                except Exception as _pe:
                    import traceback as _tb
                    _bp2.write("\n[pip subprocess exception] %r\n%s" % (_pe, _tb.format_exc()))
                    return 1, _bp2.getvalue()

            def _pip_run(extra, targets=None):
                # ★ FAZA 0C: FARA --no-cache-dir (cache-ul pip din files/home supravietuieste
                # update-ului) + wheelhouse local ca sursa suplimentara (offline / reinstall).
                return _pip_main(["install", "--disable-pip-version-check", "-v",
                                  "--find-links", _wh] + list(extra)
                                 + (list(targets) if targets else [pkg]))

            def _pip_fresh(args):
                """★ Ruleaza pip intr-un PROCES NOU.

                Dovedit pe device: dupa `pip wheel` in-line, urmatorul `pip install
                --no-index --find-links` in ACELASI proces nu mai vede wheelhouse-ul
                ("Could not find a version ... from versions: none"), desi acelasi
                comando intr-un proces nou merge. pip nu suporta doua subcomenzi in
                acelasi proces fara scurgeri de stare -> izolam procesul.
                """
                _sf = F + "/tmp/_pipx.py"
                try:
                    open(_sf, "w").write(
                        "import sys\n"
                        "sys.path[:0]=[r'%s',r'%s']\n"
                        "from pip._internal.cli.main import main\n"
                        "sys.exit(main(sys.argv[1:]))\n" % (_zp0, _ze0))
                except Exception as ex:
                    return 1, "[nu pot scrie _pipx.py] %r" % (ex,)
                try:
                    _rp = _sp.run([sys.executable, _sf] + list(args), capture_output=True,
                                  text=True, timeout=3600, env=_e, stdin=_sp.DEVNULL)
                    return _rp.returncode, (getattr(_rp, "stdout", "") or "") + (getattr(_rp, "stderr", "") or "")
                except Exception as ex:
                    return 1, "[pip subproces: %r]" % (ex,)

            def _wh_has(name):
                """★ FAZA 0C: exista deja un wheel pentru pachet in wheelhouse?"""
                try:
                    n = str(name).split("[")[0].split("==")[0].strip().replace("_", "-").lower()
                    for f in os.listdir(_wh):
                        if f.endswith(".whl") and n in f.lower():
                            return f
                except Exception:
                    pass
                return ""

            _steps = []

            def _missing_deps(txt):
                """Cerintele de BUILD lipsa, asa cum le raporteaza setuptools/pip.
                ★ Caz real (kiwisolver, prins de testul din UI): cu --no-build-isolation pip
                NU instaleaza cerintele din pyproject.toml -> setuptools.build_meta ridica
                "Missing setup required dependencies: cppy" (raportat de pip ca
                BackendUnavailable: Cannot import 'setuptools.build_meta')."""
                _o = set()
                for _m in re.finditer(r"Missing setup required dependencies:\s*([^\n.]+)", txt):
                    for _d in re.split(r"[,\s]+", _m.group(1).strip()):
                        _d = _d.strip(" .;'\"")
                        if _d and _d[0].isalnum():
                            _o.add(_d)
                for _m in re.finditer(r"No module named ['\"]([A-Za-z0-9_.]+)['\"]", txt):
                    _o.add(_m.group(1).split(".")[0])
                for _x in ("setuptools", "wheel", "pip", "sys", "os"):
                    _o.discard(_x)
                return sorted(_o)

            try:
                # ★ CRUCIAL: mediul COMPLET (PATH cu files/tmp PRIMUL, LD_LIBRARY_PATH fara
                # stub-uri, CC/LDSHARED...) trebuie sa ajunga in os.environ, pentru ca pip
                # lanseaza build-backend-ul ca SUBPROCES care mosteneaza env-ul procesului.
                # Fara asta: "clang: error: unable to execute command" (nu gaseste ld.lld,
                # care sta in files/tmp) desi compilarea in sine merge.
                _saved = {}
                for _k, _v in _e.items():
                    if isinstance(_v, str):
                        _saved[_k] = os.environ.get(_k)
                        os.environ[_k] = _v
                try:
                    _hit = _wh_has(pkg)
                    if _hit:
                        # ★ FAZA 0C: wheel deja construit o data -> instalare OFFLINE, instant
                        _steps.append("wheelhouse:%s" % _hit)
                        _rc, _out = _pip_fresh(["install", "--disable-pip-version-check",
                                               "--no-index", "--find-links", _wh, pkg])
                        if _rc == 0:
                            _out = "instalat din wheelhouse local (fara retea, fara compilare)\n" + _out
                    else:
                        # ★ Drumul PRINCIPAL ramane `pip install --no-build-isolation -v`:
                        # `pip wheel` ascunde cauza reala a cerintelor de build lipsa
                        # (setuptools raporteaza "Missing setup required dependencies: cppy"
                        # doar pe calea de metadata, nu la build_wheel) - dovedit pe device
                        # cu kiwisolver: cu `pip wheel` esua ca BackendUnavailable, fara sa
                        # putem extrage cerintele lipsa.
                        _rc, _out = _pip_run(["--no-build-isolation", "-v"])
                    # ★ PAS 1: cerinte de build lipsa -> le instalam (pip le aduce din PyPI)
                    # si reluam install-ul cu --no-build-isolation.
                    if _rc != 0:
                        _deps = _missing_deps(_out)
                        if _deps:
                            _t1 = time.time()
                            _rcd, _outd = _pip_run([], targets=_deps)
                            _steps.append("deps(%s)=%s" % (" ".join(_deps), _rcd))
                            _out += ("\n--- [build deps preinstalate: %s (exit %s, %.0fs)] ---\n"
                                     % (" ".join(_deps), _rcd, time.time() - _t1)) + _outd[-1500:]
                            if _rcd == 0:
                                _rc, _out2 = _pip_run(["--no-build-isolation"])
                                _steps.append("retry_dupa_deps=%s" % _rc)
                                _out += "\n--- [retry dupa deps: %s] ---\n" % _rc + _out2
                                _out += "(retry dupa deps)"
                    # ★ PAS 2: backend tot indisponibil -> reincercam CU izolare (pip isi
                    # aduce singur backend-ul + cerintele in mediu izolat).
                    _missm = _rc != 0 and any(
                        s in _out for s in ("ModuleNotFoundError", "BackendUnavailable",
                                            "Cannot import", "backend is not available"))
                    if _missm and "--no-build-isolation" not in pkg:
                        _bp0 = _out
                        _t1 = time.time()
                        _rc, _out2 = _pip_run([])
                        _steps.append("retry_izolat=%s" % _rc)
                        _out = (_bp0 + "\n--- [retry cu build isolation: %s] ---\n" % _rc) + _out2
                        _out += "(retry in %.0fs)" % (time.time() - _t1)
                finally:
                    for _k, _v in _saved.items():
                        if _v is None:
                            os.environ.pop(_k, None)
                        else:
                            os.environ[_k] = _v
            except Exception as _ex:
                return "pip_install error: %s" % str(_ex)[:300]
            if _rc == 0:
                try:
                    _wheels_now = len([x for x in os.listdir(_wh) if x.endswith(".whl")])
                    # ★ FAZA 0C: daca NU s-a construit local (pachetul a venit ca wheel de pe
                    # PyPI), il copiem in wheelhouse: reinstallul devine instant + offline.
                    # Daca s-a construit (apare "Building wheel for"), NU rulam `pip wheel`
                    # iar - ar insemna o a doua compilare degeaba.
                    if ("Building wheel for" not in _out) and not _wh_has(pkg):
                        _rw, _ow = _pip_main(["wheel", "--no-deps", "--disable-pip-version-check",
                                              "-w", _wh, pkg])
                        if _rw == 0:
                            _wheels_now = len([x for x in os.listdir(_wh) if x.endswith(".whl")])
                            _steps.append("salvat_in_wheelhouse=%s" % _wh_has(pkg))
                    _steps.append("wheels=%s" % _wheels_now)
                except Exception:
                    pass
            # ★ FAZA 0B: la esec, spune CE LIPSESTE si ce urmeaza (nu traceback brut)
            _dij = None
            if _rc != 0:
                _dij = _classify_build_fail(_out)
                _steps.append("cod=%s" % _dij[0])
            _tail = "\n".join([l for l in _out.splitlines() if l.strip()][-11:])
            # ★ pasii incercati, PE SCURT, in prima linie (altfel tail-ul de 11 linii
            # ascunde exact informatia de care e nevoie: ce s-a incercat si cu ce rezultat).
            _sdep = (" pasi: " + "; ".join(_steps)) if _steps else ""
            _diag = ""
            if _dij:
                _diag = "\n[diagnostic] cod=%s | lipseste: %s | urmatorul pas: %s" % _dij
            return "pip install %s (exit %s, %.0fs)%s%s\n%s" % (
                pkg, _rc, time.time()-_t0, _sdep, _diag, _tail)
        except Exception as _ex:
            return "pip_install error: %s" % str(_ex)[:300]
    if action == "pip_install_adbsh":
        pkg = (a.get("package") or "").strip()
        if not pkg: return "lipseste 'package'"
        # ★ BUILD DEPS FIRST (raportul numpy, secțiunea 5): numpy>=2 se construieste cu meson-python,
        # nu cu setuptools. Fara meson/Cython/ninja in prefix, build-ul esueaza sau pip le descarca
        # degeaba intr-un mediu izolat. Le instalam o data, apoi buildim cu --no-build-isolation.
        deps = a.get("build_deps") if isinstance(a.get("build_deps"), str) else "meson meson-python Cython ninja pyproject-metadata packaging setuptools wheel"
        # ★ --no-build-isolation DOAR daca deps sunt deja in prefix: altfel pip nu mai vede
        # nimic si esueaza. Verificam intai, apoi decidem (nu presupunem).
        has_deps = "yes" in run_adbsh_tool(
            "for m in meson Cython ninja; do python3 -c \"import $m\" 2>/dev/null && echo -n yes; done",
            120).lower()
        iso = " --no-build-isolation" if has_deps else ""
        if deps and not has_deps:
            run_adbsh_tool(_toolchain_exports()
                           + "(python3 -m pip || pip3) install --no-cache-dir -q %s 2>&1 | tail -3" % deps,
                           1200)
        # ★ TIMP PE FAZE (raportul A5): pip scrie fazele in log, dar le si numaram ca sa stim
        # unde se duce timpul (metadata = meson configure = secțiunea lenta pentru numpy)
        _t0 = time.time()
        full = (_toolchain_exports()
                + "(python3 -m pip || pip3 || pip) install --no-cache-dir%s '%s' 2>&1 | tail -25"
                % (iso, pkg))
        res = run_adbsh_tool(full, int(a.get("timeout", 2400) or 2400))
        res += "\n[phases] total %.0fs%s" % (time.time()-_t0, iso)
        # extensiile C++ au nevoie de NEEDED libc++_shared (altfel "cannot locate symbol")
        try:
            fix = ("import importlib.util as iu;"
                   "sp=iu.spec_from_file_location('tc','%s');"
                   "m=iu.module_from_spec(sp);sp.loader.exec_module(m);"
                   "m._fix_libcxx_needed()" % tc)
            # ★ acelasi fix: fara -c (libpyexec re-incarca agent.py -> SIGSEGV)
            _fx = F + "/tmp/_fixlibcxx.py"
            try:
                os.makedirs(F + "/tmp", exist_ok=True)
                open(_fx, "w").write(fix)
                r2 = _run([sys.executable, _fx], 900)
            except Exception:
                r2 = _run([sys.executable, "-c", fix], 900)
            if "LIBCXX_ADDED" in r2:
                res += "\n" + r2.strip().split("\n")[-1]
        except Exception:
            pass
        return res
    if action == "compile":
        srcf = (a.get("source") or "").strip()
        # ★ FAZA 4l: compilam IN PROCESUL APLICATIEI, nu prin adbsh (uid 2000).
        # Shell-ul uid=2000 NU poate citi filesDir (toolchain-ul e al aplicatiei) -> vechea
        # varianta murea cu "clang: inaccessible or not found" si agentul pierdea ~20 de pasi
        # incercand manual (raportat in testul din UI "testeaza uid 2000 si acces complet tool chain").
        out = (a.get("out") or (F + "/tmp/out.bin")).strip()
        if out.startswith("/sdcard") or out.startswith("/storage"):
            out = F + "/tmp/" + os.path.basename(out)   # /sdcard e NOEXEC
        if not srcf: return "lipseste 'source'"
        if not os.path.isabs(srcf):
            srcf = F + "/tmp/" + srcf
        # ★ FAZA 4p: verificare CLARA inainte de orice (inainte dadea FileNotFoundError(2) cu
        # traceback, raportat in testul din laborator: "COMPILE error: FileNotFoundError")
        if not os.path.exists(srcf):
            _d = os.path.dirname(srcf)
            _near = sorted(os.listdir(_d))[:8] if os.path.isdir(_d) else []
            return ("sursa nu exista: %s\n(scrie fisierul intai; in %s: %s)" % (srcf, _d, _near))
        cpp = srcf.endswith((".cpp", ".cc", ".cxx"))
        shared = out.endswith(".so")
        try:
            e = _env()
            cc = ((e.get("CXX") if cpp else e.get("CC")) or "").split()[0]
            if not cc:
                cc = F + "/tmp/clang++" if cpp else F + "/tmp/clang"
            cargs = ([cc]
                     + (e.get("CXXFLAGS") if cpp else e.get("CFLAGS") or e.get("CFLAGS") or "").split()
                     + (["-shared", "-fPIC"] if shared else [])
                     + [srcf, "-o", out]
                     + (a.get("flags") or "").split()
                     + (e.get("LDFLAGS") or "").split()
                     # ★ extensie Python: daca sursa include Python.h, linkam automat libpython
                     # (raportat in testul din UI: "unable to find library -lpython3.14" /
                     # "undefined symbol: PyModule_Create2" - agentul trebuia sa ghiceasca flag-ul)
                     + (["-lpython3.14"] if (shared and _uses_python_h(srcf)) else []))
            p = subprocess.run(cargs, capture_output=True, text=True, env=e, cwd=F + "/tmp",
                               timeout=int(a.get("timeout", 600) or 600), stdin=subprocess.DEVNULL)
            res = (p.stdout or "") + (p.stderr or "")
            if p.returncode != 0 or not os.path.exists(out):
                return "COMPILE FAIL (rc=%s)\n%s" % (p.returncode, res.strip()[-1500:])
            msg = "COMPILE_OK\n%s\n%s (%s bytes)" % (res.strip()[-400:], out, os.path.getsize(out))
            if not shared:
                try:
                    q = subprocess.run([out], capture_output=True, text=True, env=e, timeout=120,
                                       stdin=subprocess.DEVNULL)
                    run = (q.stdout or "") + (q.stderr or "")
                except Exception:
                    q = subprocess.run(["/apex/com.android.runtime/bin/linker64", out],
                                       capture_output=True, text=True, env=e, timeout=120,
                                       stdin=subprocess.DEVNULL)
                    run = (q.stdout or "") + (q.stderr or "")
                msg += "\n--- RUN (rc=%s) ---\n%s" % (q.returncode, run.strip()[-800:])
            return msg
        except Exception as ex:
            import traceback as _tb
            return "COMPILE error: %r\n%s" % (ex, _tb.format_exc()[-600:])
    if action == "run":
        exe = (a.get("source") or a.get("package") or "").strip()
        if not exe: return "lipseste 'source' (calea binarului)"
        try:
            e = _env()
            try:
                p = subprocess.run([exe], capture_output=True, text=True, env=e, timeout=300,
                                   stdin=subprocess.DEVNULL)
            except Exception:
                p = subprocess.run(["/apex/com.android.runtime/bin/linker64", exe],
                                   capture_output=True, text=True, env=e, timeout=300,
                                   stdin=subprocess.DEVNULL)
            return "rc=%s\n%s" % (p.returncode, ((p.stdout or "") + (p.stderr or "")).strip()[-1500:])
        except Exception as ex:
            return "run error: %r" % (ex,)
    return "actiune necunoscuta: " + action


def ask(messages=None, tools=None, _timeout=600):
    _msgs = M if messages is None else messages
    _tools = T if tools is None else tools
    # ★ FIX: repara contextul invalid (assistant cu tool_calls fara raspuns tool).
    # Se intampla cand operatorul scrie in chat in timpul unui task -> API da
    # HTTPError "insufficient tool messages following tool_calls message".
    try:
        _n = sanitize_msgs(_msgs)
        if _n:
            print(OF + "   [ctx] " + str(_n) + " tool_call(uri) orfane reparate automat" + N)
    except Exception:
        pass
    _body={"model":os.environ.get("DS_MODEL","deepseek-flash"),"messages":_msgs,"tools":_tools,
           "max_tokens":int(os.environ.get("DS_MAXTOK","131072")),
           "thinking":{"type":os.environ.get("DS_THINKING","disabled")}}
    r=urllib.request.Request("https://api.deepseek.com/chat/completions",data=json.dumps(_body).encode(),headers={"Authorization":"Bearer "+K,"Content-Type":"application/json"})
    try:
        d=json.loads(urllib.request.urlopen(r,timeout=_timeout).read()); return d["choices"][0]["message"], d.get("usage")
    except Exception as e:
        print(R+" [API] "+e.__class__.__name__+": "+str(getattr(e,"read",lambda:b"")())[:300]+N);return None,None
def do_learn(trigger="/learn"):
    """The /learn routine: updates memory.md manually, on operator command.
    `trigger` is only a label shown in the task footer (e.g. '/learn')."""
    prev=mem(); nprev=len(prev); lea=last_learn_idx(); li=len(M)
    _c,_t,_nb,_den=mstats(prev)
    M.append({"role":"user","content":LEARN_TAG+" The operator EXPLICITLY asks you to update your memory NOW.\n"
      "File: "+MEM+" ("+str(_c)+" chars ~ "+str(_t)+" tok, "+str(_nb)+" bullets, "+str(_den)+" chars/bullet). It is loaded ONCE, at session start; the MEMORY block above IS that snapshot. Nothing you write now is visible before the next start, so do not re-read it expecting a refresh.\n"
      "Checkpoint system active: analyse ONLY the messages from index "+str(lea)+" to "+str(len(M))+" ("+str(len(M)-lea)+" msgs). Index < "+str(lea)+" was ALREADY learned by a previous /learn (checkpoint saved in .learn_checkpoints.json) - do NOT re-read it and do NOT re-add lessons from it: that would only create near-duplicates and inflate memory.\n"
      "★ HOWEVER: before adding a lesson from the current window, still check it is not ALREADY in memory.md (same cause/fix/path, even in different words). If it is, SKIP it. A duplicate is worse than a missed line, because memory is re-sent on every request.\n"
      "GOAL OF MEMORY: it exists ONLY so that next session you are FASTER and do NOT repeat this session's mistakes. It is NOT a diary, NOT a summary, NOT a task log. Every line must be a REUSABLE lesson. If a line would not change your behaviour next time, it does not belong in memory.\n"
      "SIZE POLICY: the file is UNLIMITED - there is no cap and size is NEVER a reason to delete a true lesson. The only quality rule is EFFICIENCY PER LINE: maximum signal, zero filler. A line that restates something already there, or that no future session would ever consult, is a defect no matter how small the file is.\n"
      "MANDATORY 4-STEP PROCEDURE - one single python tool call does all of it, no other call, no prose. Inside it:\n"
      "  1) READ the CURRENT memory.md FIRST (read "+MEM+"). You MUST know every existing bullet before writing anything.\n"
      "  2) EXTRACT from the session ONLY the hard lessons, in this order of value: (a) a mistake I made and the FIX that worked -> becomes a TRAP line; (b) something that verifiably works and is worth reusing -> OK/P line; (c) something proven NOT to work -> DEAD line. Skip everything else.\n"
      "  3) TEST EACH CANDIDATE AGAINST THE MEMORY YOU JUST READ - a new fact is written ONLY if BOTH hold:\n"
      "     - it is NOT already covered by an existing bullet (same cause, same fix, same path, even in different words). If the idea is already there, DO NOT WRITE IT: it means you learned nothing new. Merge/refresh the old bullet IN PLACE instead of adding a duplicate.\n"
      "     - it was NOT already applied: if the session's mistake is exactly a mistake the memory already warned about, the real lesson is 'A TRAP I ignored, reinforce it', not a new line. Tighten that existing bullet.\n"
      "  4) WRITE every genuinely new lesson from the CURRENT window (usually 0-8 lines; a short window may add nothing). Zero flakes, zero repetition, no narration: only REUSABLE lessons. If the window has no genuinely new lesson, add NOTHING and say so - an honest empty update is CORRECT and expected when the checkpoint already covered everything.\n"
      "- EDIT BY CODE, NOT BY RETYPING: delete/merge/replace old lines with regex or `in` filters. Never print the file content (code and output stay in the history and are re-sent on every round). Print ONLY stats: chars before/after, bullets before/after, exact NEW lines added (short), lines merged/removed.\n"
      "- Deterministic cleanup EVERY time: drop exact duplicate lines (normalised: lowercase, collapse spaces) AND near-duplicates (same first 6 significant words), strip trailing spaces, collapse blank lines, one bullet = one fact.\n"
      "- SIZE IS UNLIMITED: the memory has NO cap - never delete a still-true, reusable lesson because the file feels big. A large dense file is FINE. What is NOT fine is a padded line.\n"
      "- WRITE DISCIPLINE (the only rule, applied whatever the current size): append with mode 'a', NEVER truncate the whole file, and add at most the few genuinely-new bullets you found in step 3. When several existing bullets clearly overlap on the same subject, merge them in place into one denser line (this SHRINKS only redundancy, never information). Keep every exact path/command/error string.\n"
      "- SELF-CLEANING: you MAY rewrite a section by code to merge/dedupe it, but only to remove redundancy - the result must still contain every distinct fact present before. If in doubt, keep the old line.\n"
      "FORMAT - one lesson = ONE line, <=300 chars, telegraphic, no sentences:\n"
      "  `TRAP: what I did -> exact error -> cause -> fix that worked` (exact command/flag/path/error string - this is the MOST valuable line type)\n"
      "  `OK: command/path/flag that verifiably works`   `DEAD: what does NOT work -> proof`   `P: absolute path -> artifact / how to run it`\n"
      "  `PREVENT: rule to apply next time so <trap> never happens again` (only when it is a real, reusable rule)\n  `RULE (ordinea cailor): ...` - ordered decision rule (1 -> 2 -> 3), pick the cheapest/fastest path FIRST (only for a real, reusable decision order)\n"
      "  section heading (date only here, grouped by area: env / web / io / python / agent): ## "+datetime.date.today().isoformat()+" - <topic> (session: "+os.getcwd()+")"
      "\nDENSIFY: arrows instead of phrases, no articles/filler, same-subject facts merged into one bullet, `code` spans instead of descriptions, numbers/sizes instead of adjectives.\n"
      "NEVER write: dialogue summaries, what the operator said, which tools were called, task narration, plans/intentions, generic advice, code/output dumps, praise, self-critique, a paraphrase of an existing bullet, or anything derivable from what is already there."})
    save_ctx(); print(_task_head("consolidate memory /learn"))
    tries=0; rl=0
    while 1:
        m,u=_spin(ask,phase="think");print_usage_compact(u)
        if m is None: M.pop();break
        if _empty(m):
            tries+=1
            if tries<=EMPTY_RETRY:
                print(OF+"   \u26a0 EMPTY answer from the model - retrying ("+str(tries)+"/"+str(EMPTY_RETRY)+")"+N)
                continue
            print(R+"   [empty] the model answered empty "+str(tries)+" times in a row; stopping /learn."+N)
            break
        tries=0; rl+=1
        M.append(m);save_ctx()
        for c in m.get("tool_calls") or []: 
            o=call_tool(c)          # respecta modul curent: NU fortam VERBOSE, altfel linia de step s-ar dubla
            M.append({"role":"tool","tool_call_id":c["id"],"content":o});save_ctx()
        if not m.get("tool_calls"): break
        if rl>=4:
            print(R+"   [/learn] stopping after 4 rounds without a final answer (otherwise it burns tokens for nothing)."+N);break
    # ★ CHECKPOINT: marcăm până unde a acoperit ACEST /learn, ca urmatorul sa inceapa de aici
    # (nu re-procesa lectiile deja invatate => fara near-duplicate, fara memorie umflata).
    _ck_before=last_learn_idx()
    _ck_new=_learn_ckpt_save(len(M))
    if li<len(M) and M[li].get("role")=="user" and str(M[li].get("content") or "").startswith(LEARN_TAG):
        M[li]["content"]=LEARN_TAG+(" Memory update done. Checkpoint: analysed msgs "+str(_ck_before)+"-"+str(len(M))+
          " (saved in .learn_checkpoints.json). The NEXT /learn will analyse ONLY the messages AFTER this checkpoint,"+
          " so lessons already learned here must NOT be re-written - no near-duplicates.")
    now=mem(); c2,t2,nb2,den2=mstats(now); d=c2-nprev
    _new, _dup = mem_dups(prev, now)
    if _dup: print(R+"   [mem] DEDUP: "+str(len(_dup))+" line(s) repeat a fact already in memory - nothing new learned from them:"+N)
    if _dup: 
        for _l in _dup[:4]: print(R+"        ~ "+_l[:110]+N)
    if _new: print(G+"   [mem] +"+str(len(_new))+" genuinely NEW lesson(s):"+N)
    if _new:
        for _l in _new[:6]: print(G+"        + "+_l[:110]+N)
    if (not prev) or d==0: print(OF+"   [mem] memory.md unchanged ("+str(c2)+" chars) - nothing was learned."+N)
    elif d<0 and _new: print(G+"   [mem] memory SHRANK by "+str(-d)+" chars (removed redundancy) while adding "+str(len(_new))+" new - good consolidation."+N)
    elif d<0 and not _new: print(R+"   [mem] WARNING: memory.md SHRANK by "+str(-d)+" chars and added no new lesson - check it was not truncated: "+MEM+N)
    else:
        print(G+"   [mem] "+str(c2)+" chars ~ "+str(t2)+" tok | "+str(nb2)+" bullets | "+str(den2)+" chars/bullet | "+("+" if d>0 else "")+str(d)+" chars | unlimited size (density is the rule)"+N)
        print(G+"   [mem] ~"+str(t2)+" tok platiti o data la pornire (prefix cache-abil), 0 in restul sesiunii."+N)
    # size never alarms (unlimited). DENSITY does: chars/bullet above ~220 means the lines are padded/filler.
    if nb2 and den2>220: print(R+"   [mem] DENSITY WARNING: "+str(den2)+" chars/bullet (target <=220) - some lines are padded or merged facts; tighten them (density, not size, is the rule)."+N)
    if nb2 and den2<=180: print(G+"   [mem] density OK: "+str(den2)+" chars/bullet - tight and reusable."+N)
    _lint, _nless = mem_lint(now)
    if _lint:
        # ENFORCE the rules: drop the offending lesson lines from the proposed memory
        # BEFORE writing, so bad lessons never reach the file (not just a warning).
        _bad = set()
        _long = 0
        for _w in _lint:
            _txt = _w[1]
            if _w[0]:  # (length, line) -> too long: DOAR avertizare, NU stergere (memoria e unlimited)
                _long += 1
            elif _txt.startswith("forbidden"):
                _bad.add(_txt.split("]: ", 1)[-1].strip())
        _kept = [l for l in now.split("\n")
                 if not (l.strip().startswith(("TRAP:","OK:","DEAD:","P:","PREVENT:","RULE:","RULE (")) and l.strip() in _bad)]
        _dropped = len(now.split("\n")) - len(_kept)
        if _dropped > 0:
            now = "\n".join(_kept)
            try: open(MEM, "w", encoding="utf-8").write(now)
            except Exception as _e: print(R+"   [mem] could not rewrite memory: "+str(_e)+N)
        print(R+"   [mem] LINT: "+str(len(_lint))+" issue(s); dropped "+str(_dropped)+" line(s) with FORBIDDEN content; kept "+str(_long)+" long line(s)."+N)
        for _w in _lint[:6]:
            _msg = ("line "+str(_w[0])+" chars (long, kept - only a density note): "+_w[1][:90]) if _w[0] else _w[1]
            print(R+"        ! "+_msg+N)
        if len(_lint)>6: print(R+"        ... +"+str(len(_lint)-6)+" more"+N)
    elif _nless:
        print(G+"   [mem] lint OK: "+str(len(_nless))+" lesson line(s), no forbidden content, none over "+str(2000)+" chars."+N)
    save_ctx()
    if m and m.get("content"): print("\n"+RED+"AGENT"+C+" >"+N+"\n\n"+render(m["content"].strip()))
    print(G+"   [/learn] the new memory loads into the system prompt at the NEXT startup."+N)
    print(_task_foot("/learn")); flush_task_tokens(); return


# ======== ANTI-POISON v1 (patch 2026-09-24) ========
# Context: pe 23 sept 2026 invatarea automata (de atunci eliminata) a scris 4 lectii
# FALSE din 10, pentru ca a rulat DUPA FIECARE task si a salvat IPOTEZE INTERMEDIARE ca
# si concluzii. Memoria
# a ajuns sa se AUTO-CONTRAZICA ("dispatchGesture both fail" langa "dispatchGesture works").
#
# Acest bloc pune DOUA porti inainte de scrierea in memory.md:
#   (1) HEDGE  - lectia contine markeri de ipoteza (suspect/probably/Looper issue) -> carantina
#   (2) CONTRADICTIE - lectia contrazice o lectie existenta pe acelasi subiect -> carantina
# Lectiile blocate merg in memory_quarantine.md, NICIODATA in memory.md. Curatarea e
# determinista (0 tokeni, 0 apeluri API).
QUAR = os.path.join(os.path.dirname(MEM), "memory_quarantine.md")
HEDGE_RX = [r"\bsuspect", r"\bprobably\b", r"\bposibil", r"\bse pare\b", r"\bmaybe\b",
            r"\blikely\b", r"\bpoate fi\b", r"\bipotez", r"\bpresupun\b",
            r"\bneverificat\b", r"\bmight\b", r"\bcould be\b"]
# Generalizari absolute: DOAR cele care trag o concluzie despre propriul
# comportament (nu descrieri de fapte masurate). Tiparul care a otravit memoria
# era "X si Y ambele esueaza -> deci e read-only", nu "toate returneaza false".
ABSOLUTE_RX = [r"\bboth fail\b", r"\bambele\b.{0,20}?\b(esu|e[ss]u|fail)\w*",
               r"\ball (of them )?fail\b", r"\btoate\b.{0,40}?\b(esu|e[ss]u|fail)\w*",
               r"\bnici ?unul\b", r"\bfara exceptie\b",
               r"\bnu (mai )?merge (niciodata|nici)\b", r"\b(esu|e[ss]u)\w* (mereu|intotdeauna)\b",
               r"\bnu are permisiune\b", r"\bnu are (voie|drept)\b"]
PROOF_RX = [r"\bproven\b", r"\bdovedit\b", r"\bverified\b", r"\bconfirmat\b",
            r"\blogcat\b", r"\btested?\b", r"\bmeasured\b", r"\bmasurat\b"]
# Doar formulari care AFIRMA cauza ca verdict ("serviciul ESTE read-only",
# "e in mod read-only"), nu orice mentiune a cuvantului.
CAUSE_CLAIM_RX = [r"\b(e|este|e in mod) read[- ]only\b", r"\bconsider[oă]-[ol] read[- ]only\b",
                  r"\bmissing capability\b", r"\bcapabilities lack\b",
                  r"\bproblem[aă] de (thread|looper)\b"]
CAUSE_PROOF_RX = [r"\blogcat\b", r"\bproven\b", r"\bdovedit\b", r"\bverified\b",
                  r"\bconfirmat\b", r"\bPendingIntent\b", r"\bSystemActionPerformer\b"]
HEDGE_OK_RX = [r"\bdovedit\b", r"\bverified\b", r"\bconfirmat\b", r"\bproven\b"]
TOPIC_RX = [r"accessibility", r"performGlobalAction", r"dispatchGesture", r"capabilities",
            r"screencap", r"screenshot", r"canTakeScreenshot", r"read-only", r"keyevent",
            r"pendingintent", r"looper", r"threading", r"toolchain", r"numpy",
            r"reflection", r"subclass", r"adbsh", r"selinux", r"libpyexec", r"aapt2",
            r"enabled_accessibility_services", r"settings put secure",
            r"rss", r"\bhttps?\b", r"endpoint", r"\bjson\b", r"\bhtml\b",
            r"scraping", r"duckduckgo", r"blog\.google", r"github", r"cloud\.google",
            r"ai\.google\.dev", r"huggingface", r"algolia", r"\bcors\b",
            r"\bssl\b", r"\btls\b", r"certificat", r"timeout", r"rate.?limit", r"proxy",
            r"beautifulsoup", r"elementtree", r"\bregex\b", r"parsare", r"parsez",
            r"\bcsv\b", r"\bxml\b",
            r"gemini", r"deepseek", r"\bgpt\b", r"claude", r"\bllm\b", r"token",
            r"benchmark", r"deepswe", r"pricing", r"pret(ul|uri)?", r"\bcost\b",
            r"\bbash\b", r"\bpython\b", r"\bawk\b", r"\bgrep\b", r"\bsed\b",
            r"\bcurl\b", r"\brequests\b", r"\bwget\b", r"\bjq\b", r"\bgit\b"]
OPPOSITE_RX = [
    # --- WEB / HTTP: disponibilitate si raspuns ---
    (r"\b(merge|functioneaza|intoarce 200|raspunde|e disponibil|accesibil|se parseaza|e parsabil)\b",
     r"\b(nu merge|nu functioneaza|nu raspunde|esueaza|eroare|blocat|interzis|403|404|500|timeout|nu se poate parsa)\b"),
    (r"\b(da 200|intoarce 200|raspunde cu 200)\b",
     r"\b(da 4\d\d|da 5\d\d|404|403|500|eroare)\b"),
    # --- AUTH: necesita cheie vs anonim ---
    (r"\b(necesita|are nevoie de|cere)\b.{0,25}\b(api.?key|token|auth|autentificare)\b",
     r"\b(fara (api.?key|token|auth)|anonim|merge anonim|nu necesita cheie)\b"),
    # --- SCRAPING: HTML static vs necesita JS ---
    (r"\b(html static|merge fara js|fara javascript)\b",
     r"\b(necesita js|e un spa|javascript|html gol|content gol)\b"),
    # --- EXISTENTA unei resurse ---
    (r"\b(exista|e valabil|e activ)\b",
     r"\b(nu exista|inexistent|a fost retras|retired|e sters)\b"),
    # --- PRET (doar opus explicit) ---
    (r"\b(ieftin|cost redus|low cost)\b",
     r"\b(scump|cost ridicat|expensive)\b"),
    # --- PERFORMANTA ---
    (r"\b(mai bun|depaseste|bate |outperforms|cel mai bun|superior)\b",
     r"\b(mai slab|in urma|pierde|inferior|nu atinge)\b"),
    # --- SUPORT functionalitate ---
    (r"\b(suporta|are suport|accepta)\b",
     r"\b(nu suporta|nu accepta|nu permite|incompatibil|unsupported)\b"),
    # --- VITEZA uneltelor ---
    (r"\b(mai rapid|e rapid|performant|speedup)\b",
     r"\b(mai lent|e lent|slow|incet)\b"),
]

COND_RX = [r"\bfara\s+(LD_LIBRARY|PATH|variabil|env|root|permisiun|cheie|api|token|flag|optiun)",
           r"\bcu\s+(LD_LIBRARY|PATH=|env|variabil|flag|optiun)",
           r"\bdaca\s+", r"\bif\s+", r"\bcand\s+", r"\bwhen\s+",
           r"\bwith(out)?\s+(LD_|PATH|env|root)", r"\bonly\s+(if|when)",
           r"\bdoar\s+daca", r"\bnumai\s+daca"]

def _q_topics(line):
    return set(rx for rx in TOPIC_RX if re.search(rx, line, re.I))

def _q_absolute(line):
    """True daca lectia face o generalizare absoluta FARA dovada citata."""
    if any(re.search(rx, line, re.I) for rx in PROOF_RX):
        return False
    if any(re.search(rx, line, re.I) for rx in HEDGE_OK_RX):
        return False
    return any(re.search(rx, line, re.I) for rx in ABSOLUTE_RX)

def _q_hedged(line):
    """True daca lectia e o IPOTEZA sau un diagnostic nedovedit, nu o concluzie."""
    if any(re.search(rx, line, re.I) for rx in HEDGE_OK_RX):
        return False
    if _q_absolute(line):
        return True
    if any(re.search(rx, line, re.I) for rx in HEDGE_RX):
        return True
    if any(re.search(rx, line, re.I) for rx in CAUSE_CLAIM_RX) and \
       not any(re.search(rx, line, re.I) for rx in CAUSE_PROOF_RX):
        return True
    return False

# O lectie META (despre /learn, despre memorie, despre o eroare proprie) NU e
# o contradictie, chiar daca numeste subiecte si verdicturi. Fara exceptia asta,
# lectiile despre anti-poison se blocheaza singure (observat 2026-09-24).
META_RX = [r"\bauto-learn\b", r"\bmemory\.md\b", r"\bmemoria\b", r"\bmemorie\b",
           r"\bpoarta anti", r"\blegitii false\b", r"\blectii false\b", r"\bauto-contrazic",
           r"\bscrie lectii\b", r"\bgeneralizeaz", r"\bconcluzia gresita\b",
           r"\bacumuleaz", r"\bcontradictorii\b", r"\bverifica daca contrazice\b"]

def _q_meta(line):
    """True daca lectia vorbeste DESPRE procesul de invatare, nu despre telefon."""
    return any(re.search(rx, line, re.I) for rx in META_RX)

def _q_contradicts(new_line, mem_text):
    """Intoarce linia veche contrazisa, sau None. Doar daca verdictul e despre
    ACELASI mecanism (subiect comun) si semnalele sunt explicit opuse."""
    if _q_meta(new_line):
        return None
    nt = _q_topics(new_line)
    if not nt:
        return None
    for old in mem_text.split("\n"):
        if not old.startswith(("TRAP:", "OK:", "DEAD:", "P:", "PREVENT:", "RULE:", "RULE (")):
            continue
        # o lectie META (despre procesul de invatare) NU e un fapt despre telefon,
        # deci nu poate contrazice o lectie tehnica (simetrie cu _q_meta mai sus)
        if _q_meta(old):
            continue
        if not (_q_topics(old) & nt):
            continue
        # GUARD anti-conditional: "merge CU X" vs "esueaza FARA X" sunt complementare DOAR
        # cand conditionalul e prezent in AMBELE linii (acelasi subiect, aceeasi conditie).
        # Daca doar una e conditionata, conditiile difera -> poate fi contradictie reala.
        if any(re.search(rx, new_line, re.I) for rx in COND_RX) and any(re.search(rx, old, re.I) for rx in COND_RX):
            continue
        for a, b in OPPOSITE_RX:
            if (re.search(a, old, re.I) and re.search(b, new_line, re.I)) or (re.search(b, old, re.I) and re.search(a, new_line, re.I)):
                return old.strip()
    return None

def quarantine(reason, lines):
    """Scrie lectiile blocate in memory_quarantine.md - NICIODATA in memory.md."""
    try:
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        fresh = not os.path.exists(QUAR)
        with open(QUAR, "a", encoding="utf-8") as f:
            if fresh:
                f.write("# memory_quarantine.md - lectii BLOCATE de anti-poison\n\n")
                f.write("Nu au intrat in memory.md fiindca fie contrazic o lectie existenta, fie\n")
                f.write("contin markeri de incertitudine. Verifica-le; daca sunt corecte, muta-le\n")
                f.write("manual in memory.md si sterge-le de aici.\n")
            f.write("\n## " + stamp + " - " + reason + "\n")
            for l in lines:
                f.write("- " + l + "\n")
        return True
    except Exception:
        return False
# ======== END ANTI-POISON v1 ========




if __name__ == "__main__":
    # ★ PAS 2: aplica in PROCESUL CURENT PATH/LD/PYTHONPATH din toolchain.env_vars(),
    # altfel scripturile rulate prin /run si subprocess-urile NU gasesc make/ninja/cython
    # (Kotlin porneste procesul cu PATH=/system/bin:/vendor/bin).
    try:
        import importlib.util as _iluS
        _tcS_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "toolchain.py")
        _spS = _iluS.spec_from_file_location("_tcS", _tcS_path)
        _mS = _iluS.module_from_spec(_spS); _spS.loader.exec_module(_mS)
        for _kS, _vS in _mS.env_vars().items():
            if _vS:
                os.environ[_kS] = str(_vS)
        # ★ numpy/meson: sys.executable trebuie sa fie o cale CURATA si executabila
        # (files/tmp/python3), nu libpyexec.so din /data/app/~~...==/ (meson o pune intre
        # ghilimele simple si `env` nu le interpreteaza -> "env: exec -m: No such file").
        try:
            _mS._patch_sys_executable()
        except Exception:
            pass
        _FdS = os.path.dirname(os.path.abspath(__file__))
        _FdS = os.path.dirname(_FdS)
        _partsS = []
        for _pS in (_FdS + "/tmp", _FdS + "/libs",
                    os.environ.get("LD_LIBRARY_PATH", "")):
            if _pS and _pS not in _partsS:
                _partsS.append(_pS)
        # ★ FIX CRITIC: fara stub-urile NDK (sysroot) in LD_LIBRARY_PATH - altfel
        # orice proces copil (pip/build backend/setuptools) moare cu SIGSEGV (-11).
        os.environ["LD_LIBRARY_PATH"] = _clean_ld(":".join(_partsS))
        print("[pas2] PATH aplicat: " + os.environ.get("PATH","")[:80])
    except Exception as _eS:
        print("[pas2] EROARE: %r" % (_eS,))
    # ★ P3/P10: colectori de stare acumulata (backup-uri + loguri), la fiecare pornire
    try: _cleanup_backups()
    except Exception: pass
    try: _cleanup_logs()
    except Exception: pass
    if WATCH.get("on"):
        _watch_start()
    # cheia poate fi scrisa de UI in key.txt DUPA pornirea procesului: reincarcam.
    K=_load_key()
    if not K:
        print(N+"\n"+OF+"[key] lipsea cheia DeepSeek la pornire - o reincarc la prima cerere."+N)
    refresh()   # the memory enters the system prompt ONCE, here; from now on the prefix never changes again
    if K:
        ctx_check_window()   # cheap API call: corrects CTXWINDOW if the local constant is wrong
    # --- banner de start: titlu centrat + o linie de ajutor (cerut de operator) ---
    def _ctr(txt, visible):
        return txt   # aliniat la stanga (cerut de operator)
    _title = "\u26a1 AGENT DeepSeek"
    _tvis = len(_title) - 1   # emoji-ul ⚡ ocupa 2 celule, scadem 1
    print("")
    print(RED + _ctr(_title, _tvis) + N)
    print(G + _ctr("Type /help for all commands", 26) + N + "\n")
    while 1:
        try: q=input(U+UPROMPT+IN).strip()
        except (EOFError,KeyboardInterrupt): print(N);break
        if q=="": continue          # blank line (extra newline from the UI) = no-op, do NOT quit the agent
        if not K:
            K=_load_key()
            if not K:
                print(N+OF+"[key] nu am cheia DeepSeek. Scrie-o in key.txt si reincearca."+N); continue
        if q in ("/exit","/quit"): break
        if q in ("/help","/?"):
            print(G+"   COMMANDS"+N)
            print(G+"     /learn              update memory now (manual learning)"+N)
            print(G+"     /mem                show memory stats (size, bullets, density, lint)"+N)
            print(G+"     /ctx                context window + archives/logs on disk"+N)
            print(G+"     /where             show where everything lives (workspace, memory, context, logs)"+N)
            print(G+"     /run <script.py>   run a script from the workspace, with the APP's rights (uid=app)"+N)
            print(G+"     /run_su <script>   run a script with SHELL rights (uid=2000): /data/local/tmp,"+N)
            print(G+"                        toolchain nativ, llama.cpp, modele GGUF, binare compilate"+N)
            print(G+"     /compact            compress the context now"+N)
            print(G+"     /verbose            toggle full code/output of each step"+N)
            print(G+"     /nospin             NO live line at all: clean scrollback (best on a phone)"+N)
            print(G+"     /reset              erase the conversation history"+N)
            print(G+"     /help, /?           this list"+N)
            print(G+"     /exit, /quit        leave (empty line too)"+N)
            continue
        if q=="/ctx":
            _a=[f for f in (os.listdir(ARCH) if os.path.isdir(ARCH) else []) ]
            _l=[f for f in (os.listdir(LOGDIR) if os.path.isdir(LOGDIR) else []) ]
            print(G+"   [ctx] window: "+str(len(M))+" messages ~ "+_K(ctx_tokens())+"tok = "+("%.0f"%(100.0*ctx_tokens()/CTXWINDOW))+"% of "+_K(CTXWINDOW)+" ("+str(CTXWARN)+"% = red warning) | compression OFF (context grows until /reset)"+N)
            _hit="n/a"
            if SESS["in"]: _hit=("%d%%"%int(100.0*SESS["cache_hit"]/SESS["in"]))
            print(G+"   [cost] requests: "+str(SESS["rounds"])+" | tok in "+_K(SESS["in"])+" / out "+_K(SESS["out"])+" | cache HIT "+_hit+" (higher = cheaper)"+N)
            print(G+"   [ctx] archives: "+str(len(_a))+" in archive/ | tool logs: "+str(len(_l))+" in logs/ | nothing is ever deleted, only moved to disk"+N); continue
        if q=="/compact":
            print(G+"   [compact] DISABLED by the operator: the context is never compressed (not automatically, not on request), so the memory inserted at startup stays intact until you give /reset. Nothing was changed."+N); continue
        if q in ("/nospin","/spin"):
            NOSPIN[0]=(q=="/nospin"); print(G+"   [ui] "+("NOSPIN: no live line at all - the terminal scrollback stays clean (recommended on a phone)" if NOSPIN[0] else "live line back on (spinner + timer rewritten in place)")+N); continue
        if q.startswith("/watch"):
            _a = q.split()
            if len(_a) > 1 and _a[1].isdigit(): WATCH["sec"] = max(10, int(_a[1]))
            WATCH["on"] = not WATCH["on"]
            if WATCH["on"]:
                _watch_start()
                print(G+"   [watch] ON - o linie de status la fiecare "+str(WATCH["sec"])+"s, DOAR cat ruleaza un job."+N)
                print(G+"   [watch] cost: 0 tokeni (scrie pe ECRAN, nu intra in contextul modelului)."+N)
            else:
                print(G+"   [watch] OFF."+N)
            continue
        if q=="/verbose":
            VERBOSE[0]=not VERBOSE[0]; print(G+"   [ui] "+("VERBOSE: printing the code and the output of every step" if VERBOSE[0] else "COMPACT: live line with what it does now + timer over the WHOLE task (thinking vs. tool) and one line \u25cf <nr> \u00b7 <what the step does> \u00b7 time \u00b7 chars for every finished step")+N); continue
        if q=="/where":
            print(G+"   LOCATIONS"+N)
            print(G+"     home       "+N+HOME_DIR+N)
            print(G+"     workspace  "+N+WORK+N+"   (everything I create goes here)"+N)
            print(G+"     memory     "+N+MEM+N)
            print(G+"     context    "+N+CTX+N)
            print(G+"     logs       "+N+LOGDIR+N)
            print(G+"     archive    "+N+ARCH+N)
            try:
                _n=len([f for f in os.listdir(WORK)])
                print(G+"     files in workspace: "+N+str(_n)+N)
            except Exception: pass
            if HOME_DIR==_DEFHOME:
                print(OF+"     note: running from the app sandbox (external storage not writable) -"+N)
                print(OF+"           files are NOT visible in a file manager here."+N)
            continue

        if q.startswith("/run "):
            # /run <script.py> [args...] - ruleaza un script Python din workspace, cu argumente.
            argv=shlex.split(q[5:].strip())
            if not argv:
                print(R+"   usage: /run <script.py> [args...]   (scriptul trebuie sa fie in workspace)"+N); continue
            script=argv[0]
            if not os.path.isabs(script): script=os.path.join(WORK,script)
            if not os.path.exists(script):
                print(R+"   no such file: "+script+N); continue
            _a=argv[1:]
            print(G+"   [run] "+os.path.basename(script)+(" "+" ".join(_a) if _a else "")+N)
            _o=py_capture([script]+_a)   # afiseaza live (streaming), linie cu linie
            if len(_o)>4000:             # output lung: il salvam, ca sa nu-ti scape nimic
                try:
                    _lf=os.path.join(LOGDIR,"run_"+os.path.basename(script)+"_"+time.strftime("%Y%m%d-%H%M%S")+".log")
                    os.makedirs(LOGDIR,exist_ok=True)
                    with open(_lf,"w",encoding="utf-8") as f: f.write(_o)
                    print(SD+"   (full output: "+_lf+")"+N)
                except Exception: pass
            continue

        if q.startswith("/run_su ") or q == "/run_su":
            # /run_su <script> [args...] - ca /run, dar cu DREPTURI DE SHELL (uid=2000):
            # vede /data/local/tmp, toolchain-ul nativ, llama.cpp, modelele GGUF.
            try:
                argv = shlex.split(q[8:].strip())
            except Exception as _e:
                print(R + "   parse error: " + str(_e) + N); continue
            if not argv:
                print(R + "   usage: /run_su <script.py|script.sh|binar> [args...]" + N)
                print(SD + "   (ruleaza cu uid=2000: /data/local/tmp, toolchain, llama.cpp)" + N)
                continue
            script = argv[0]
            if not os.path.isabs(script):
                script = os.path.join(WORK, script)
            if not os.path.exists(script):
                print(R + "   no such file: " + script + N); continue
            _a = argv[1:]
            print(G + "   [run_su] " + os.path.basename(script) + (" " + " ".join(_a) if _a else "")
                  + "  (uid=2000)" + N)
            try:
                _o = adbsu_capture([script] + _a)
            except KeyboardInterrupt:
                print(R + "\n   [run_su] intrerupt (SIGINT)" + N); continue
            if len(_o) > 4000:
                try:
                    os.makedirs(LOGDIR, exist_ok=True)
                    _lf = os.path.join(LOGDIR, "runsu_" + os.path.basename(script) + "_"
                                       + time.strftime("%Y%m%d-%H%M%S") + ".log")
                    with open(_lf, "w", encoding="utf-8") as f: f.write(_o)
                    print(SD + "   (full output: " + _lf + ")" + N)
                except Exception:
                    pass
            continue

        if q=="/mem":
            _c,_t,_nb,_den=mstats(mem()); _dens="density OK (tight)" if (_nb and _den<=180) else ("DENSITY WARNING ("+str(_den)+" chars/bullet > 220)" if (_nb and _den>220) else "n/a"); print(G+"   memory: "+MEM+" | "+str(_c)+" chars ~ "+str(_t)+" tok | "+str(_nb)+" bullets | "+str(_den)+" chars/bullet | unlimited size | "+_dens+N); continue
        if q=="/reset":
            M[:]=M[:1]; save_ctx()
            # FIX: /reset goleste si checkpointurile /learn (altfel fisierul acumula indici
            # stale din sesiuni vechi; logica ii ignora, dar fisierul crestea inutil).
            try:
                if os.path.exists(LEARN_CKPT): os.remove(LEARN_CKPT)
            except Exception: pass
            print(G+"   [reset] history erased ("+os.path.basename(CTX)+") and /learn checkpoints cleared."+N); continue
        if q.startswith("/auto-learn") or q.startswith("/autolearn"):
            print(OF+"   [auto-learn] ELIMINAT - agentul nu mai invata singur dupa task."+N)
            print(G+"   [auto-learn] memoria se actualizeaza DOAR manual, cu /learn."+N); continue
        if q=="/learn":
            do_learn("/learn"); continue
        # ★ FIX: daca task-ul anterior s-a oprit cu tool_calls fara raspuns (ex. operatorul
        # a scris in chat in timpul unui task, sau API error), contextul devine INVALID si
        # API-ul respinge TOT. Reparam INAINTE de a adauga noul mesaj.
        try:
            _n = sanitize_msgs(M)
            if _n:
                print(OF + "   [ctx] " + str(_n) + " tool_call(uri) orfane reparate (context valid)" + N)
        except Exception:
            pass
        M.append({"role":"user","content":q});compact_history();save_ctx(); mark=len(M); TN[0]=0
        print(_task_head(q))
        try:
         tries=0
         while 1:
            m,u=_spin(ask,phase="think");print_usage_compact(u)
            if m is None: M.pop();print(_task_foot("interrupted: API error"));break
            if _empty(m):
                tries+=1
                if tries<=EMPTY_RETRY:
                    print(OF+"   \u26a0 EMPTY answer from the model - retrying ("+str(tries)+"/"+str(EMPTY_RETRY)+")"+N)
                    continue
                print(R+"   [empty] the model answered empty "+str(tries)+" times in a row; stopping the step (I do not save the empty message in the history)."+N)
                print(_task_foot("stopped: empty answer"));break
            tries=0
            M.append(m);save_ctx();ctx_warn()
            if m.get("tool_calls"):
                _a=json.loads(m["tool_calls"][0]["function"]["arguments"] or "{}"); _nm=m["tool_calls"][0]["function"]["name"]
                _fb=brief(_a.get("code","")) if _nm=="python" else ("looks at "+os.path.basename(_a.get("path","")) )
                _txt=str(m.get("content") or "").strip() or _fb
                # the descriptive text appears ABOVE the step line, clean: no arrow, no leading "#"
                if _txt:
                    _clean=re.sub(r"^#+\s*","",_txt.strip()).strip()   # drop the leading "#": the comment is a label, not code
                    if _clean: print(OF+"   "+N+C+_clean+N)
                for c in m["tool_calls"]:
                    code=json.loads(c["function"]["arguments"] or "{}").get("code","")
                    # ★ FAZA 4o (crash raportat de operator): orice exceptie aici (ex. tempfile pe
                    # /sdcard cand fd-urile sunt epuizate) OMORA procesul agentului. Acum eroarea
                    # devine un rezultat de tool, agentul o vede si continua.
                    try:
                        o=call_tool(c)
                    except Exception as _ex:
                        import traceback as _tb
                        o=("[tool error] %s: %s\n%s" % (type(_ex).__name__, str(_ex)[:300],
                                                         _tb.format_exc()[-800:]))
                        try:
                            print(R+"   [tool error] "+type(_ex).__name__+": "+str(_ex)[:140]+N)
                        except Exception:
                            pass
                    M.append({"role":"tool","tool_call_id":c["id"],"content":o});compact_history();save_ctx();ctx_warn()
            else:
                print("\n"+RED+"AGENT"+C+" >"+N+"\n\n"+render((m.get("content") or "").strip())+"\n")
                print(_task_foot())
                flush_task_tokens()
                break
        except KeyboardInterrupt:
            LIVE.update(phase="idle",desc="",col=None,n=0)   # kill the live line first: no "step 00" left stuck on screen
            print("\r\33[K",end="",flush=True)
            print(G+"   [Ctrl+C] stopped ONLY the current step. The tools run so far stay in the context (the agent knows where it stopped). /reset to make it forget the whole task."+N)
            while len(M)>mark and M[-1].get("role")=="assistant" and not M[-1].get("tool_calls"): M.pop()
            complete_pending(M);save_ctx(); print(_task_foot("interrupted by the operator")); flush_task_tokens(); continue
    save_ctx(force_mirror=True)   # on /exit or Ctrl+D: also refresh the visible sdcard copy

    # ---- FIX: AAPT2 ignora folderele care incep cu "_" (ex: compression/_common) ----
    # Il recreem la runtime din compression/_streams_data.py (livrat ca fisier simplu).
    def _fix_compression_common():
        import os, sys
        try:
            import sysconfig
            purelib = sysconfig.get_paths().get("purelib", "")
            base = os.path.dirname(os.path.abspath(__file__))
            # locul REAL vazut de Python: pyhome/lib/python3.14/compression
            # compression poate fi in pyhome/lib/pythonX.Y/ (stdlib) SAU in
            # site-packages SAU in assets Lib/. Cautam in toate.
            cands = []
            if purelib: cands.append(os.path.join(os.path.dirname(purelib), "compression"))
            if purelib: cands.append(os.path.join(purelib, "compression"))
            cands.append(os.path.join(base, "Lib", "compression"))
            for d in list(sys.path):
                if d: cands.append(os.path.join(d, "compression"))
            comp = ""
            for c in cands:
                if os.path.isdir(c) and os.path.exists(os.path.join(c, "_streams_data.py")):
                    comp = c; break
            if not comp:
                for c in cands:
                    if os.path.isdir(c): comp = c; break
            if not comp: return
            common = os.path.join(comp, "_common")
            src_data = os.path.join(comp, "_streams_data.py")
            if not os.path.exists(src_data):
                return
            bad = os.path.join(comp, "_common.py")
            if os.path.isfile(bad):
                try: os.remove(bad)
                except Exception: pass
            if os.path.isfile(common):
                try: os.remove(common)
                except Exception: pass
            if not (os.path.isdir(common) and os.path.exists(os.path.join(common, "_streams.py"))):
                os.makedirs(common, exist_ok=True)
                open(os.path.join(common, "__init__.py"), "w").close()
                import shutil
                shutil.copyfile(src_data, os.path.join(common, "_streams.py"))
                import shutil as _sh2
                _sh2.rmtree(os.path.join(common, "__pycache__"), ignore_errors=True)
                _sh2.rmtree(os.path.join(comp, "__pycache__"), ignore_errors=True)
        except Exception:
            pass

    _fix_compression_common()

MAX_BACKUPS = 3        # ★ P3: cate backup-uri .bak* pastram per fisier sursa


def _cleanup_backups(d=None):
    """★ P3: colector de backup-uri acumulate. Pastreaza ultimele MAX_BACKUPS
    per fisier sursa (dupa mtime) si sterge restul. Ruleaza la start, in try."""
    import glob as _g
    d = d or os.path.dirname(os.path.abspath(__file__))
    groups = {}
    for f in _g.glob(os.path.join(d, "*.bak*")):
        base = os.path.basename(f)
        src = base.split(".bak")[0]
        groups.setdefault(src, []).append(f)
    removed = 0
    for src, files in groups.items():
        files.sort(key=lambda f: os.path.getmtime(f), reverse=True)
        for old in files[MAX_BACKUPS:]:
            try:
                os.remove(old); removed += 1
            except Exception:
                pass
    return removed

MAX_LOGS = 5           # ★ P10: cate loguri pastram in workspace/logs


def _cleanup_logs(d=None):
    """★ P10: rotatie loguri (pastreaza ultimele MAX_LOGS dupa mtime)."""
    import glob as _g
    d = d or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logs")
    try:
        files = [f for f in _g.glob(os.path.join(d, "*")) if os.path.isfile(f)]
    except Exception:
        return 0
    files.sort(key=lambda f: os.path.getmtime(f), reverse=True)
    removed = 0
    for old in files[MAX_LOGS:]:
        try:
            os.remove(old); removed += 1
        except Exception:
            pass
    return removed
