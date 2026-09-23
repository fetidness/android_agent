#!/usr/bin/env python3
import base64,datetime,json,os,random,re,shlex,shutil,signal,subprocess,sys,tempfile,threading,time,urllib.request

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
# HOME vine din aplicatie (AGENT_HOME) - ex. /storage/emulated/0/Download/Agent.
# Daca nu e setat sau nu e scriibil, rămâne in sandbox (fallback sigur, nu se strica niciodata).
HOME_DIR=os.environ.get("AGENT_HOME","").strip() or _DEFHOME
def _writable(d):
    try:
        os.makedirs(d,exist_ok=True)
        _t=os.path.join(d,".wtest"); open(_t,"w").write("x"); os.remove(_t); return True
    except Exception: return False
if not _writable(HOME_DIR):
    HOME_DIR=_DEFHOME; _writable(HOME_DIR)
WORK=os.path.join(HOME_DIR,"workspace")
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
K=open(os.path.join(os.path.dirname(os.path.abspath(__file__)),"key.txt")).read().strip()
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
    if line.upper().startswith(("OK:", "P:")) and "->" not in line: s -= 2   # observatie fara consecinta
    return s


def mem_lint(txt):
    """Checks EVERY /learn write LINE BY LINE (the prompt's rules, enforced in code):
    - one lesson = ONE line, <=300 chars (the prompt says 150, density warns only on the AVERAGE)
    - no forbidden content: narration, tool calls, dialogue, praise, generic advice, code dumps
    - section heading present and well formed.
    Read-only: it NEVER edits or truncates the file. Returns (warnings, lessons)."""
    import re as _re
    MAXLINE = 500
    FORBID = [
        (r"\b(am citit|am rulat|am apelat|am folosit tool|tool call)\b", "narration/tool-call"),
        (r"\b(operatorul|utilizatorul a spus|buna seara)\b", "operator dialogue"),
        (r"\b(bravo|excelent|grozav|perfect)\b", "praise"),
        (r"\b(ar trebui|e bine sa|pe viitor incearca)\b", "generic advice"),
        (r"^```|^def |^import ", "code/output dump"),
        # NOT about this Android phone = not a memory lesson (desktop/CI/dev-environment knowledge)
        (r"\b(openrouter|hermes|claude cli|auto-learn hook|gradle|systemd|tmux|git-bash|busybox|coreutils|"
         r"debian|ubuntu|windows|win32|powershell|nvcc|cuda|docker|nginx|apt-get|pip install|npm|node_modules|"
         r"/dev/video|wsl|macos|homebrew|kernel-header|dkms|sshpass|ansible|venv|site-packages|"
         r"sudo|bash -lc|profile sourcing|login shell|non-login shell|/usr/bin/time)\b",
         "not about this Android device (dev/desktop topic)"),
    ]
    out = []
    lines = [l.rstrip() for l in txt.split("\n") if l.strip()]
    heads = [l for l in lines if l.startswith("##")]
    body  = [l for l in lines if not l.startswith(("#", "<!--"))]
    for l in body:
        if len(l) > MAXLINE:
            out.append((len(l), l))
    lessons = [l for l in body if l.startswith(("TRAP:","OK:","DEAD:","P:","PREVENT:","- ","* "))]
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
        if l.startswith(("TRAP:","OK:","DEAD:","P:","PREVENT:")) and _lesson_value(l) < 2:
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
TOOLMAX=int(os.environ.get("AGENT_TOOLMAX","6000"))   # how much of a tool output stays IN THE WINDOW (head+tail); the rest goes to disk, with a pointer
CTXBUDGET=int(os.environ.get("AGENT_CTXBUDGET","1000000"))   # ~tokens: above this it is compressed WITHOUT LOSS (0 = never)
CTXKEEP=24         # how many recent messages are never compressed
LOGDIR=os.path.join(WORK,"logs")      # complete tool outputs (not deleted between sessions)
ARCH=os.path.join(WORK,"archive")     # COMPLETE snapshots of the history, before every compression
VERBOSE=[os.environ.get("AGENT_VERBOSE")=="1"]   # /verbose: re-prints code + output in the terminal
NOSPIN=[os.environ.get("AGENT_NOSPIN")=="1"]     # /nospin: NO live/redrawn line at all (clean scrollback on a phone)
THINKMIN=float(os.environ.get("AGENT_THINKMIN","0"))   # MINIMUM time "Thinking..." stays on screen (0 = the printed time is exactly the measured one). It never delays a tool step.
def _cut(o,ref=None):
    """What goes INTO THE WINDOW: the first TOOLMAX*3/4 chars + the last TOOLMAX/4 chars (the tail is where
    the tracebacks and the conclusion show up), plus a POINTER to the complete text on disk.
    Nothing is lost: the original is at `ref` and can be read at any time with a tool call."""
    if len(o)<=TOOLMAX: return o
    h,t=TOOLMAX*3//4,TOOLMAX//4
    _tot=len(o)
    mid=("[... "+str(_tot-TOOLMAX)+" chars omitted here (NOT LOST). Read them with: "
         +"read path="+(ref if ref else "<file>")+" offset="+str(h)+" limit="+str(TOOLMAX)+" (then increase offset to continue) ...]")
    return o[:h]+"\n"+mid+"\n"+o[-t:]
def _store(o):
    """Writes the COMPLETE output into a log on disk and returns (what enters the window, path|None)."""
    if len(o)<=TOOLMAX: return o,None
    os.makedirs(LOGDIR,exist_ok=True)
    p=os.path.join(LOGDIR,"tool_"+datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")+".log")
    try: open(p,"w",encoding="utf-8").write(o)
    except Exception: return o[:TOOLMAX],None
    return _cut(o,os.path.relpath(p,WORK)),p
def _tokm(m):
    s=str(m.get("content") or "")
    for tc in (m.get("tool_calls") or []): s+=str((tc.get("function") or {}).get("arguments") or "")
    return len(s)//4
def ctx_tokens(): return sum(_tokm(m) for m in M)
def compact_history(force=False):
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
TASK={"t0":None,"n":0,"steps":0,"think":0.0,"tool":0.0,"chars":0,"tok_in":0,"tok_out":0,"err":False}   # one "task" = one operator request
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
    TASK.update(t0=time.time(),steps=0,think=0.0,tool=0.0,chars=0,tok_in=0,tok_out=0,n=TASK["n"]+1,err=False)
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
    """Termux/Android: a line longer than the terminal wraps onto a second row, and a LIVE
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
        l.startswith(("TRAP:","OK:","DEAD:","P:","PREVENT:","- ","* ")) or (":" in l[:12] and not l.startswith("##")))])
    return len(s),len(s)//4,nb,(len(s)//nb if nb else 0)
AUTOLEARN={"on":True,"min_steps":5}   # auto-learn after a finished task: ON by default, disable via /auto-learn off
AUTO_LEARN_PROMPT=("AUTO-LEARN CHECK. You are an autonomous agent running INSIDE an Android app on a real phone (Samsung SM-A366B, Android 16, no root). You talk to the device through the android tool (reflection + native shortcuts, socket bridge to Kotlin) and through a POSIX shell (sh -c). Look at the task that just finished above and decide whether it taught you a REUSABLE fact about THIS PHONE. A lesson qualifies ONLY if it is BOTH (1) about the Android device itself - its services, APIs, permissions, reflection quirks, sensors, storage layout, SELinux limits, shell behaviour on this phone - AND (2) likely to change how you act on a FUTURE task here, not just describe what happened. Typical valid lessons: an API call that needs [\"ref\",\"ctx\"] or fails with a specific exception; an abstract class that must be subclassed via op=subclass; a service that returns null / a value that is misleading without root; an exact working chain of reflection calls; a feature PROVEN impossible for a normal app; a permission/SELinux boundary. NEVER save: generic software/desktop knowledge (bash vs bash -lc, BusyBox, OpenRouter, claude CLI, Gradle, systemd, Windows, other tools), paraphrases of the task, trivia about one specific device you scanned, or anything already in your memory snapshot. If the lesson would be equally true on a Linux desktop, or is not about interacting with THIS phone, it does NOT qualify. REPLY FORMAT: one lesson per line and NOTHING else (no preamble, no numbering, no markdown). Write as many lines as there are GENUINELY valuable independent lessons (usually 1, sometimes 2-3, often 0). Do NOT pad - a weak or obvious line is worse than none.    - Each lesson line: do NOT start with YES/NO; write it as a dense bullet, syntax `KEY: what -> cause -> fix/verify`, where KEY is one of TRAP:/OK:/DEAD:/P:/PREVENT:, max 500 chars, no quotes, no markdown. Only write a line if it has a CONSEQUENCE (the '->'): what to DO differently next time; skip obvious facts and one-off task artefacts.   - If there is genuinely NOTHING reusable or it is not Android-specific: reply with the single word: NO.")
HINT_LINE="tip: /help shows every command"
LEARN_TAG="[[MEMORY-UPDATE]]"
def last_learn_idx():
    """The index of the last /learn request left in the history: everything before it has
    already been learned, so it is not re-analysed and not rewritten again (wasted tokens)."""
    for i in range(len(M)-1,-1,-1):
        if M[i].get("role")=="user" and str(M[i].get("content") or "").startswith(LEARN_TAG): return i
    return 0
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
T=[{"type":"function","function":{"name":"python","description":"Run Python 3 code on this Linux machine, returns stdout/stderr. Available: the FULL Python 3.14 stdlib PLUS these pre-installed third-party packages (pure-Python): requests, urllib3, certifi, charset-normalizer, idna, beautifulsoup4, soupsieve, python-dateutil, six, pyyaml, toml, packaging, typing-extensions. There is NO pip and you CANNOT install anything else - if a package is not in that list it does not exist: never try pip install, never import numpy/pandas/cryptography (not available). Prefer requests for HTTP. BEST for: structured parsing (JSON/INI/KeyValues), logic, aggregations in memory, complex data structures, anything needing decisions. SLOW for multi-million-line streams; for those use `bash` or the `smart` router.","parameters":{"type":"object","properties":{"code":{"type":"string"}},"required":["code"]}}},
   {"type":"function","function":{"name":"bash","description":"Run a BASH shell command (bash -lc) on this Linux machine, returns combined stdout/stderr. Use it when the task is a TEXT STREAM / SHELL PIPELINE: grep/awk/sed/sort/uniq/wc/find/du/cut, processing a large file that flows line by line, filtering logs, parallel work with xargs -P. Measured: on big streams bash is ~1.3-1.6x faster than Python and uses far less memory. NOT for structured parsing or logic - use `python` for that.","parameters":{"type":"object","properties":{"cmd":{"type":"string","description":"the full shell command line, e.g. grep -c ERROR app.log | sort | uniq -c"}},"required":["cmd"]}}},
   {"type":"function","function":{"name":"smart","description":"AUTO-ROUTER: give it ONE command and it decides BY ITSELF which engine runs it faster (python vs bash) using the measured heuristics, then runs it. It answers in one field: engine (\"bash\" or \"python\"), cmd (a shell command if bash) and code (Python code if python). Prefer this tool when you are unsure; it removes the guesswork. It also reports which engine it picked and why.","parameters":{"type":"object","properties":{"cmd":{"type":"string","description":"the shell command you would run if bash is chosen"},"code":{"type":"string","description":"the Python code you would run if python is chosen"}},"required":["cmd"]}}},
   {"type":"function","function":{"name":"look","description":"Look at an IMAGE file (screenshot, chart, photo) with vision and answer a question about what is really in it. Use it when the operator asks to analyze/see a screen or an image.","parameters":{"type":"object","properties":{"path":{"type":"string","description":"image file path (png/jpg), absolute or relative to the cwd"},"prompt":{"type":"string","description":"what to look for / what to answer"}},"required":["path"]}}},{"type":"function","function":{"name":"android","description":"Native Android control. Only on the Android build. Includes the 'ui' tool: SEE and CONTROL other apps. Actions: read (returns a COMPACT text list, ~10x smaller than JSON; params: max, depth, textonly), find (SEARCH a node by text WITHOUT reading the whole screen - USE THIS FIRST when looking for a contact/button/field; returns matches with center coordinates), settext (type into a field), click, tap, swipe, scroll, back/home/recents, openapp, windows, wake (keep screen on for UI work), sleep (release), service (status). Also FULL generic SDK access via reflection: action=\"eval\" runs ANY class/method/field. Also: services (list all 300+ system services), info (list methods of a class), plus ready shortcuts. camera (list/photo), location (last/providers), battery, clipboard (get/set), notifications, vibration, text-to-speech, volume, wifi status, device info, installed apps (list/launch), sending intents, reading system settings. Pass the action and its parameters directly.","parameters":{"type":"object","properties":{"tool":{"type":"string","description":"sensors|camera|location|battery|clipboard|notify|vibrate|tts|volume|wifi|device|apps|intent|settings|tourl|system|storage|processes|network|display|audio|telephony|nfc|usb|appinfo|eval"},"action":{"type":"string","description":"the sub-action (e.g. sensors: list|read|stream; location: last|fresh|current|providers; camera: list|photo; battery: get|full; clipboard: get|set; tts: say; apps: list|launch; settings: get|set)"},"params":{"type":"object","description":"parameters; for eval must contain \"expr\" = the reflection request. Reflection ops: call, new, get, set, info, services, objs, free, proxy (make a real instance of any Java INTERFACE: {\"op\":\"proxy\",\"iface\":\"java.lang.Runnable\"}), await (block for the next callback: {\"op\":\"await\",\"id\":\"s0\",\"timeout_ms\":10000}), subclass (make a REAL concrete subclass of any class incl. abstract: {\"op\":\"subclass\",\"parent\":\"android.bluetooth.le.ScanCallback\"}), events, sinks. To PASS AN OBJECT as an argument use a 2-element array [\"ref\",<value>] where value is \"ctx\", \"app\", \"obj:<id>\" or \"svc:<name>\" (e.g. args:[[\"ref\",\"ctx\"],0,[\"ref\",\"obj:o5\"],0x04000000]); a bare string \"ctx\" is a literal and is NOT resolved."}},"required":["tool"]}}},
   {"type":"function","function":{"name":"adbsh","description":"SUPER POWERS: real ADB shell with uid=2000(shell) on this very phone, run FROM the app with no PC. Only on the Android build. Runs a raw shell command as the privileged shell user, which app code cannot: pm grant/revoke runtime permissions, appops set, settings put secure/global, dumpsys (full), input tap/text/keyevent (UI automation WITHOUT accessibility), screencap, uiautomator dump, am start/force-stop, pm list/enable/disable, logcat, getprop/setprop (read), svc, wm size/density, ls/cat/cp on the whole sdcard and /data/local/tmp, run-as on debuggable apps, ifconfig/ip, cat /proc/net/*. This bypasses every permission wall: USE IT whenever the android/ui tools hit a SecurityException or a runtime permission is missing. Runs the command and returns stdout+stderr. Prefer ONE command per call; combine with && if needed.","parameters":{"type":"object","properties":{"cmd":{"type":"string","description":"the shell command to run as the shell user, e.g. \"pm grant net.sys32.agent android.permission.CAMERA\" or \"dumpsys battery\" or \"input keyevent 3\""},"timeout":{"type":"integer","description":"seconds to wait (default 20, max 60)"}},"required":["cmd"]}}},
   {"type":"function","function":{"name":"toolchain","description":"COMPILE TOOLCHAIN: install and use a complete native build stack ON the phone (clang 21, make, cmake, ninja/samu, python, pip, git, rust, libc++, openssl...) WITHOUT PC and WITHOUT Termux. Use action=status to see what is installed; action=bootstrap to download+install everything (through the Termux package repo, ~500MB, done once); action=pip_install to pip-install a PyPI package INCLUDING C/C++ extensions (the toolchain compiles them natively); action=compile to build a C/C++ file into a shared library; action=env to get the environment variables (PATH, CC, CXX, CFLAGS, LDFLAGS...). ALWAYS run action=preflight BEFORE any big build (10-second test of C, C++, math linking, SSL, make, cmake) - it catches every linking problem upfront instead of after minutes of compiling. Use action=profile to get ready-made flags for cmake/cflags/ldflags (libc++, bionic libm, target API, rpath already correct) instead of discovering them by trial. Use action=fix after anything reinstalls Termux packages (re-applies all environment repairs). action=env-file writes the persistent environment. This makes the phone a self-sufficient build machine: numpy, scipy-level packages, llama.cpp, any compiler-requiring pip package can be built here.","parameters":{"type":"object","properties":{"action":{"type":"string","description":"status | bootstrap | pip_install | compile | env | tpm","enum":["status","bootstrap","pip_install","compile","env","tpm","preflight","profile","fix","env-file"]},"package":{"type":"string","description":"for pip_install: package name (e.g. numpy, pandas, pillow). For tpm: termux package (e.g. nano)"},"source":{"type":"string","description":"for compile: path to a .c/.cpp source file"},"out":{"type":"string","description":"for compile: output .so path"},"flags":{"type":"string","description":"extra compiler flags (optional)"},"timeout":{"type":"integer","description":"seconds to wait (default 300 for compile, max 3600)"}},"required":["action"]}}},
   {"type":"function","function":{"name":"read","description":"Read a FILE in chunks (paginate). Use this to read the parts of a large file or a truncated tool log that were not shown in the window. Returns a header with the exact byte range and, if not at EOF, the next command to continue with.","parameters":{"type":"object","properties":{"path":{"type":"string","description":"file path (absolute, or relative to the working directory)"},"offset":{"type":"integer","description":"byte offset to start at (default 0)"},"limit":{"type":"integer","description":"max bytes to return (default 4000, max 20000)"}},"required":["path"]}}}]

TOOLGUIDE=("TOOL SELECTION (you choose the engine yourself, do not waste steps): you have 3 engines. "
  "1) `python`: run Python 3 code. Has the full stdlib PLUS pre-installed: requests, urllib3, certifi, charset-normalizer, idna, beautifulsoup4, soupsieve, python-dateutil, six, pyyaml, toml, packaging, typing-extensions. NO pip, you CANNOT install more (numpy/pandas/cryptography are NOT available - do not try). BEST for structured parsing (JSON/INI/KeyValues), logic, aggregations kept in memory, complex data structures, anything needing decisions. This is the default brain. "
  "2) `bash`: run a shell command (grep/awk/sed/sort/uniq/wc/find/du/cut/xargs). BEST when the work is a TEXT STREAM or a SHELL PIPELINE over a big file: bash is measured ~1.3-1.6x faster than Python there and uses far less memory. "
  "3) `smart`: the AUTO-ROUTER - give it both the shell cmd and the Python code and it picks the faster engine BY ITSELF using measured heuristics, then runs it. Use `smart` whenever you are unsure which is better; it prints which engine it chose and why. "
  "RULE OF THUMB: data that FLOWS and simple logic -> bash; data that must be PARSED or REASONED about -> python; unsure -> smart. "
  "Never pipe a huge file through python line by line if a single awk/grep does it; never parse JSON with grep when python json.loads is right there. "
  "WARNING: do NOT build a hybrid that captures a huge awk output into Python memory (subprocess capture_output on megabytes) - that was measured at 14x the memory of plain bash. If you must combine, STREAM it (iterate stdout line by line).")

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
ANDROID_GUIDE=("BE EXHAUSTIVE: for any hardware/system question, do not stop at the first source. Squeeze EVERYTHING reachable - use the native shortcuts AND reflection AND shell, cross-check them, and report everything you found (including what is NOT available and why). It is fine to take many steps. Explore every relevant nook: services, build props, sensors (action=all), sysfs, settings, managers. ANDROID ACCESS: on this device you have the `android` tool with FULL generic access to the whole "
 "Android SDK through reflection - no root needed. Call ANY public class, method or field. "
 "HOW: android(tool=\"eval\", params={\"expr\":{...}}) where expr is one of: "
 "{\"op\":\"services\"} lists ALL system services; "
 "{\"op\":\"info\",\"target\":\"class:android.hardware.SensorManager\",\"filter\":\"Sensor\"} lists methods+fields; "
 "{\"op\":\"call\",\"target\":\"svc:sensor\",\"method\":\"getSensorList\",\"args\":[-1]} calls on a system service; "
 "{\"op\":\"call\",\"target\":\"class:android.os.Environment\",\"static\":true,\"method\":\"getExternalStorageDirectory\"}; "
 "{\"op\":\"new\",\"target\":\"class:android.media.MediaRecorder\"}; "
 "{\"op\":\"get\",\"target\":\"svc:wifi\",\"field\":\"mService\"} or {\"op\":\"set\",...}; {\"op\":\"free\",\"id\":\"o0\"}. "
 "TARGETS: svc:NAME, class:FQCN, obj:ID, ctx (app context), app, str:X, int:N, bool:true, null. "
 "LIST KEPT OBJECTS with the OP {\"op\":\"objs\"} (NOT a tool) - it returns id+class of every held object. "
 "CRITICAL - OBJECTS:\n"
 " * Every call/get/new now AUTO-RETURNS an id; the object stays alive under obj:<id>. REUSE it, do not recreate the same thing in a loop.\n"
 " * If a call returns only {class,str} with no id, the object was a primitive/array/collection.\n"
 " * PROXY: you CAN now create a real instance of ANY Java INTERFACE via {\"op\":\"proxy\",\"iface\":\"java.lang.Runnable\"} -> returns an id (obj:<id>). Pass it as an argument like any object; every call of the interface is recorded. Read the recorded calls with {\"op\":\"await\",\"id\":\"<id>\",\"timeout_ms\":10000} (blocks until the next callback fires) or {\"op\":\"events\",\"id\":\"<id>\"} (all so far); {\"op\":\"sinks\"} lists active proxies. (op=proxy works only for INTERFACES. For an ABSTRACT CLASS like ScanCallback or BroadcastReceiver use {\"op\":\"subclass\",\"parent\":\"<FQCN>\"} -> returns an id (obj:<id>) of a REAL concrete subclass whose overridden methods are recorded as events exactly like a proxy; read them with await/events. So you CAN implement any Android callback: create the subclass, pass it as [\"ref\",\"obj:<id>\"] to the API that needs it, then await the events.)\n"
 " * PASSING OBJECTS AS ARGUMENTS is done with a 2-element array [\"ref\",<value>] where <value> is \"ctx\" (the app Context), \"app\" (application context), \"obj:<id>\" (a held object), or \"svc:<name>\". Example that works: {\"op\":\"call\",\"target\":\"class:android.app.PendingIntent\",\"static\":true,\"method\":\"getBroadcast\",\"args\":[[\"ref\",\"ctx\"],0,[\"ref\",\"obj:o5\"],0x04000000]}. A plain string \"ctx\"/\"obj:o5\"/\"$ref\" is treated as a literal STRING and will NOT be resolved - you MUST wrap it as [\"ref\",...]. This also works for op=new (constructors).\n"
 " * getSystemService lives on Context: use target ctx, e.g. {\"op\":\"call\",\"target\":\"ctx\",\"method\":\"getSystemService\",\"args\":[\"sensor\"]}. "
 "An Executor comes from ctx.getMainExecutor() (no-arg). Many classes (LocationManager, Executors, HandlerExecutor...) have NO public no-arg constructor - obtain them from a service/factory.\n"
 "NATIVE SHORTCUTS that DO real hardware reading (use these FIRST for sensors/location, they handle callbacks in Kotlin): "
 "sensors action=list | action=read (name,seconds) | action=stream (name or names[],seconds,max) for continuous multi-sample data; "
 "location action=last (cache) | action=fresh (REQUEST A BRAND-NEW GPS FIX: real requestLocationUpdates + waits for onLocationChanged; provider=gps default, seconds=30) | action=current (getCurrentLocation, may return a cached fused fix instantly) | action=providers; "
 "camera list/photo; battery get|full (full = ALL battery data incl health/technology/current/charge_counter/estimate); clipboard get/set; notify; vibrate; tts; volume; wifi; device; apps list|launch; intent; settings get|set; system (model/cpu/ram/heap/uptime/build props with action=full); storage (disk usage); processes; network (wifi+transport); display (resolution/density/refresh/brightness); audio (all streams+devices); telephony (operator/SIM); nfc; usb; appinfo (package details+perms). "
 "IMPORTANT: when the user asks for the CURRENT/real-time value, use location action=fresh (real new fix) - NOT action=last/current which can serve a cached fused fix - and sensors action=read/stream - do NOT keep re-reading cached values (getLastKnownLocation is cache). "
 "For complex APIs go step by step: info -> call/new -> reuse obj:<id> -> call further. "
 "Everything the Android SDK exposes to an app, you can reach."
 " COMPILE STACK: this phone is a SELF-SUFFICIENT BUILD MACHINE. The 'toolchain' tool installs (once, via the Termux repo) a full native compiler stack: clang 21, make, cmake, ninja/samu, git, python+pip, rust, libc++, openssl, zlib. Use toolchain action=status to see what is present; action=bootstrap to install the whole stack (~500MB, one time, no PC, no Termux app needed); action=pip_install package=<name> to pip-install ANY PyPI package INCLUDING ones with C/C++/Fortran extensions (they get compiled natively here); action=compile source=<file.c> out=<file.so> to build C/C++ into a shared library; action=env to print PATH/CC/CXX/CFLAGS/LDFLAGS; action=tpm package=<name> to install any Termux binary (nano, htop, jq...). RULE: when a task needs a library that is not installed, do NOT give up - install it: pip_install for Python packages (compiles extensions), tpm for CLI tools, compile for your own C/C++ code. Prefer the already-installed pure-Python tools first; reach for the toolchain when something must be compiled or installed. "
 "RUNNING SCRIPTS FOR THE OPERATOR: when a build was done and the operator needs to RUN something "
 "(a compiled binary, llama.cpp, a GGUF model, a chat script, anything under /data/local/tmp), "
 "tell them to use /run_su <script> [args] - it runs with SHELL rights (uid=2000), so it can see "
 "/data/local/tmp, the native toolchain and compiled binaries. /run only has the APP's rights "
 "(uid=app) and CANNOT access /data/local/tmp. Always write the launcher as a .sh script in the "
 "workspace (exporting PATH/LD_LIBRARY_PATH) so /run_su can execute it.")


M=[{"role":"system","content":TOOLGUIDE+" "+FMT+" "+ANDROID_GUIDE+" You are a minimal autonomous agent. Use stdlib only. Your working directory is "+WORK+" - create every file, script and temporary test THERE, never elsewhere on the disk. Do the task end to end and verify it. "
  "WHILE WORKING (mandatory, never skip): BEFORE EVERY python tool call you MUST put a FULL, COMPLETE sentence in the `content` field, in the operator\u2019s language, telling what you are about to do and why. There is NO word limit and NO character limit: NEVER cut, shorten or abbreviate it with \u201c...\u201d or \u201c\u2026\u201d - the operator must always see the WHOLE sentence he needs to follow you. NEVER send a tool call with empty content. Markdown is NOT allowed in that sentence. "
  "VISION: you have a second tool, `look(path, prompt)` - it sends an IMAGE file to the same model with THINKING ENABLED and returns what is REALLY in it. Use it whenever the operator asks you to see/analyze a screen, a screenshot, a chart or a photo: first capture it (e.g. `xwd -root -out shot.xwd` then convert with ffmpeg to png), then call look on the png. Never guess what an image contains - look at it. "
  "STEP LABELS: the FIRST line of every python tool call is a comment (lowercase) - the terminal prints it as the label of that step, so write WHAT the step does, clearly and COMPLETELY, in the language the operator is currently using (mirror their language: if they write English, use English; if Romanian, use Romanian), never `# step 1` or `# test`. There is NO word limit: write the full label, do not cut it. "
  "The terminal UI shows a live task timer (from the operator's request to your final answer, split into thinking vs tool time) and one labelled line per finished step; no code and no output unless the operator toggles /verbose. "
  "CONTEXT ECONOMY: nothing is ever deleted - only heavy tool outputs and old steps are moved to disk when the window gets big. When you see a line like `[complete output, untouched: archive/ctx_....json #12 (4300 chars)]` or `[complete code, untouched: ...]`, the EXACT original text is on disk: read or grep it (raw tool outputs live in ./logs/*.log, full pre-compaction transcripts in ./archive/ctx_*.json) instead of guessing what the truncated middle contained. Do that whenever the exact bytes matter: error strings, stack traces, file contents, numbers. ""MEMORY RULE: the MEMORY block below is READ-ONLY for you - never write, append, modify or delete it on your own initiative, only when the operator explicitly asks. Use it to work faster, but only its owner updates it. "
  "IT IS A SNAPSHOT: memory.md was loaded into this system prompt ONCE, at session start; the file on disk may already be longer (the operator updates it, /learn appends to it). Lessons taught after this start are NOT here - if memory says nothing about X, that does not mean X was never learned. "
  "IT IS TELEGRAPHIC: one lesson per line - `TRAP: what failed -> exact error -> cause -> fix`, `OK: what verifiably works`, `DEAD: what does not work -> proof`, `P: absolute path -> artifact / how to run`, sections `## date - topic`. Read it as dense facts, not prose; missing words are not missing meaning. "
  "FINAL MESSAGE: rendered as Markdown in a 256-colour terminal. You MAY use headings (# ## ###), **bold**, *italic*, `inline code`, ~~strikethrough~~, > blockquote, --- rules, numbered/bulleted lists and fenced code blocks. BUT on this small phone screen NEVER use tables (no | pipes | rows, no |---| separators) and never ASCII boxes - present ALL structured data as plain lists, one item or `key: value` per line. Write the final answer in the SAME LANGUAGE the operator used in their last message, complete and well structured - if they wrote in English, reply in English; if in Romanian, reply in Romanian."}]
CTX=os.path.join(HOME_DIR,CTXNAME)
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

def save_ctx():
    """Writes the conversation history (without the system message) to context.json,
    via a temporary file + os.replace, so it does not get corrupted on an interruption."""
    try:
        tmp=CTX+".tmp"
        with open(tmp,"w",encoding="utf-8") as f: json.dump(M[1:],f,ensure_ascii=False,indent=1)
        os.replace(tmp,CTX)
    except Exception as e: print(R+" [context] could not save "+CTX+": "+str(e)+N)
def load_ctx():
    """Reloads the history at startup. Tool messages left without a corresponding
    tool_call (e.g. a brutal shutdown) are dropped, otherwise the API rejects
    the conversation."""
    _migrate_ctx()
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
    TASK["tok_in"]+=pt; TASK["tok_out"]+=ct   # same server numbers, accumulated for THIS task
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
    parts = [". /data/local/tmp/tpm/env.sh >/dev/null 2>&1; "]
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


def py_capture(argv, timeout=600):
    """Ruleaza un script Python (argv=[script, args...]) si afiseaza output-ul LINIE cu LINIE,
    in timp real (streaming). Returneaza intregul output (pentru context), dar il si printeaza
    pe masura ce apare, ca sa vezi progresul unui script care dureaza."""
    buf=[]
    p=subprocess.Popen([sys.executable]+list(argv),cwd=WORK,stdout=subprocess.PIPE,
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

def py(c,cwd):
    """Runs the code in its own process group. Ctrl+C kills ONLY this
    tool (SIGKILL on the group), then re-raises the signal to the task loop."""
    o=tempfile.TemporaryFile(dir=WORK)
    p=subprocess.Popen([sys.executable,"-c",c],cwd=cwd,stdout=o,stderr=subprocess.STDOUT,start_new_session=True)
    try:
        p.wait(timeout=600)
    except KeyboardInterrupt:
        try: os.killpg(p.pid,signal.SIGKILL); p.wait(timeout=3)
        except Exception: pass
        raise
    o.seek(0); return (o.read().decode("utf-8","replace") or "(no output)")[:8000]

# ==================== TOOL ROUTER: alege AUTOMAT python vs bash ====================
# Euristici bazate pe masuratori reale (teste 1-3): bash castiga pe fluxuri/volum/paralelism,
# python castiga pe parsare structurata + logica. Routerul decide inainte de a executa.
PY_STRUCT = (r"\bjson\b", r"\bimport\s+json", r"json\.loads", r"json\.load\b", r"\.ini\b",
             r"configparser", r"def\s+\w+\(", r"class\s+\w+", r"\bCounter\b", r"collections",
             r"re\.(findall|search|match|sub)", r"dict\(|defaultdict", r"\.get\(", r"\blambda\b",
             r"os\.walk", r"glob\.", r"shutil\.", r"struct\.", r"\bdataclass\b", r"yield\b",
             r"\btry:", r"\bexcept\b", r"\.items\(\)", r"\.keys\(\)", r"\.values\(\)")
BASH_STREAM = (r"\bgrep\b", r"\bawk\b", r"\bsed\b", r"\bsort\b", r"\buniq\b", r"\bwc\b",
               r"\bcut\b", r"\btail\b", r"\bhead\b", r"\bxargs\b", r"\bfind\b", r"\bdu\b",
               r"\bdf\b", r"\brsync\b", r"\bzgrep\b", r"\btr\b", r"\bpaste\b", r"\bcomm\b",
               r"\bjoin\b", r"\bflock\b", r"\bcomm\b", r"\bparallel\b", r"-P\s*\d", r"\|\s*\w+")
BASH_HEAVY = (r"\.log\b", r"/var/log", r">\s*\d{6,}", r"\bfor\s+\w+\s+in\b", r"\bseq\b")

def route(cmd="", code=""):
    """Decide engine = 'bash' sau 'python' pentru un task, pe baza a ce urmeaza sa se intample.
    Intoarce (engine, why). Prioritatea: structura > stream > volum > implicit."""
    c = (cmd or "").strip()
    k = (code or "").strip()
    t = (c + "\n" + k).lower()
    # 1) cod Python clar structurat -> python
    py_hits = sum(1 for pat in PY_STRUCT if re.search(pat, k))
    if py_hits >= 2:
        return "python", f"structured logic detected ({py_hits} python-structure signals): parsing/logic is where python wins (test 2: ~130x faster than bash)"
    # 2) comanda shell de tip stream -> bash
    sh_hits = sum(1 for pat in BASH_STREAM if re.search(pat, c or k))
    heavy = any(re.search(pat, t) for pat in BASH_HEAVY)
    if c and sh_hits >= 1:
        why = f"shell pipeline detected ({sh_hits} stream signals)"
        if heavy: why += "; large/streamed data -> bash (test 3: 1.3-1.6x faster, far less memory)"
        return "bash", why
    # 3) cod python pur dar cu semnale de stream (subprocess grep/awk in el) -> las python
    if py_hits == 1:
        return "python", "mostly python-shaped task (single structure signal)"
    # 4) implicit: python (logic-safe)
    return "python", "default: python (safe for logic; explicit `bash` for pure streams)"

def bash(cmd, cwd):
    """Ruleaza o comanda shell (bash -lc) in propriul grup de procese; Ctrl+C omoara doar acest
    tool. Intoarce stdout+stderr combinat, trunchiat la 8000 de caractere (ca la python)."""
    o=tempfile.TemporaryFile(dir=WORK)
    p=subprocess.Popen(SHELL[0]+(cmd,),cwd=cwd,stdout=o,stderr=subprocess.STDOUT,start_new_session=True)
    try:
        p.wait(timeout=600)
    except KeyboardInterrupt:
        try: os.killpg(p.pid,signal.SIGKILL); p.wait(timeout=3)
        except Exception: pass
        raise
    o.seek(0); return (o.read().decode("utf-8","replace") or "(no output)")[:8000]

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
    """Cheap heuristic: does this tool output contain a FAILURE (traceback, non-zero exit, an
    ERROR/EXCEPTION line)? Used ONLY by auto-learn to decide whether a task is worth learning from.
    False positives are harmless (auto-learn then just asks the model, which may say NO)."""
    if not o: return False
    lo=o.lower()
    if "traceback (most recent call last)" in lo: return True
    if re.search(r"\b(error|exception|failed|non-zero exit status|command not found|no such file)\b", lo): return True
    return False

_ADBCLI=None
def run_adbsh_tool(cmd, timeout=20):
    """SUPER PUTERI: ruleaza o comanda shell ca user 'shell' (uid=2000) folosind
    clientul ADB scris in Python (adb_client.py), conectat la adbd pe 127.0.0.1:5555.
    Fara PC, fara root. Da acces la: pm grant, dumpsys, settings put, input, screencap, etc."""
    import importlib.util as _iu
    global _ADBCLI
    try:
        _ADBCLI
    except NameError:
        _ADBCLI=None
    if _ADBCLI is None:
        here=os.path.dirname(os.path.abspath(__file__))
        try:
            sp=_iu.spec_from_file_location("adb_client", os.path.join(here,"adb_client.py"))
            _ADBCLI=_iu.module_from_spec(sp); sp.loader.exec_module(_ADBCLI)
        except Exception as e:
            _ADBCLI=False
            _err="adbsh unavailable: "+str(e)
    if not _ADBCLI:
        o=_err if isinstance(_err,str) else "adbsh unavailable"
        _show_step("adbsh", o, TASK["steps"]); return o
    dsc="adbsh: "+cmd[:60]
    def _run():
        try:
            import signal as _sig
            def _to(s,f): raise TimeoutError("adbsh timeout")
            old=_sig.signal(_sig.SIGALRM,_to); _sig.alarm(max(min(int(timeout),3600),1))
            try:
                # ★ CONEXIUNE PERSISTENTA: refolosim ACELASI obiect Adb intre comenzi.
                # adbd cere confirmare (fereastra "Allow USB debugging") doar la conexiuni NOI;
                # daca tinem socket-ul deschis nu mai apare niciun prompt.
                global _ADBCONN
                try:
                    _ADBCONN
                except NameError:
                    _ADBCONN=None
                if _ADBCONN is None:
                    _ADBCONN=_ADBCLI.Adb(); _ADBCONN.connect()
                else:
                    # verificam daca socket-ul e inca viu; reconectam DOAR daca a murit
                    doomed=False
                    try:
                        _s=_ADBCONN.s
                        if _s is None:
                            doomed=True
                        else:
                            import select as _sel
                            r,_,_=_sel.select([_s],[],[],0)
                            if r:
                                peek=_s.recv(1, 0x02)  # MSG_PEEK
                                if peek==b"":
                                    doomed=True
                    except Exception:
                        doomed=True
                    if doomed:
                        try: _ADBCONN.close()
                        except Exception: pass
                        _ADBCONN=_ADBCLI.Adb(); _ADBCONN.connect()
                # ★ R1/R5 (raport llama.cpp): sursez AUTOMAT mediul toolchain
                # daca exista, ca agentul sa nu mai scrie export-uri manual
                # (PREFIX, SSL_CERT_FILE, PATH, LD_LIBRARY_PATH erau uitate
                #  si fiecare lipsa costa minute de diagnostic)
                _wrapped = cmd
                try:
                    if os.path.exists("/data/local/tmp/tpm/env.sh"):
                        _wrapped = (". /data/local/tmp/tpm/env.sh >/dev/null 2>&1; "
                                    "export PATH=/data/local/tmp/wrap:$PATH; ") + cmd
                except Exception:
                    pass
                return _ADBCONN.shell(_wrapped, timeout=min(int(timeout),60))
            finally:
                _sig.alarm(0); _sig.signal(_sig.SIGALRM,old)
        except Exception as e:
            # la eroare de conexiune: aruncam obiectul ca sa reconecteze curat la urmatorul apel
            try:
                globals()["_ADBCONN"]=None
            except Exception:
                pass
            return "adbsh error: "+str(e)
    try:
        o=_spin(_run, phase="tool", desc=dsc, col=HCLR[sum(map(ord,dsc))%len(HCLR)])
    except Exception as e:
        o="adbsh error: "+str(e)
    TN[0]+=1; TASK.update(steps=TASK["steps"]+1,chars=TASK["chars"]+len(o))
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
    if fn=="adbsh":
        return run_adbsh_tool(a.get("cmd",""), int(a.get("timeout",20) or 20))
    if fn=="toolchain":
        return run_toolchain_tool(a)
    return run_tool(a.get("code",""))

def run_toolchain_tool(a):
    """Toolchain nativ de compilare pe telefon (clang, pip, meson...)."""
    import subprocess as _sp
    action = (a.get("action") or "status").strip()
    here = os.path.dirname(os.path.abspath(__file__))
    tc = os.path.join(here, "toolchain.py")
    tpm = os.path.join(here, "tpm.py")
    F = os.environ.get("AGENT_HOME") or "/data/data/net.sys32.agent/files"
    ROOT = "/data/local/tmp/tpm"
    BIN = ROOT + "/usr/bin"

    def _toolchain_exports():
        """Export-uri shell cu mediul COMPLET de compilare, luat din toolchain.py.
        Sursele Termux au RUNPATH gresit + clang are target android24 implicit ->
        fara aceste variabile (CFLAGS cu --target, LD_PRELOAD libc++, PATH cu
        /system/bin) pachetele cu extensii C/C++ (numpy!) NU se compileaza."""
        e = {}
        try:
            import importlib.util as _ilu
            spec = _ilu.spec_from_file_location("_tc_env", tc)
            mod = _ilu.module_from_spec(spec)
            spec.loader.exec_module(mod)
            e = mod.env_vars()
        except Exception:
            pass
        # fallback daca toolchain.py nu poate fi incarcat
        e.setdefault("PATH", BIN + ":/system/bin:/system/xbin:" + os.environ.get("PATH", ""))
        e.setdefault("LD_LIBRARY_PATH", ROOT + "/usr/lib")
        e.setdefault("PREFIX", ROOT + "/usr")
        e.setdefault("LD_PRELOAD", ROOT + "/usr/lib/libc++_shared.so")
        parts = []
        for k, v in e.items():
            parts.append("export %s='%s'" % (k, str(v).replace("'", "'\\''")) )
        return "; ".join(parts) + "; "

    def _env():
        e = dict(os.environ)
        e["PATH"] = BIN + ":" + F + "/python:" + e.get("PATH","")
        e["PREFIX"] = e["TERMUX_PREFIX"] = ROOT + "/usr"
        e["CC"] = BIN + "/clang"; e["CXX"] = BIN + "/clang++"
        e["AR"] = BIN + "/ar"; e["RANLIB"] = BIN + "/ranlib"
        e["CFLAGS"] = "-I" + ROOT + "/usr/include"
        e["LDFLAGS"] = "-L" + ROOT + "/usr/lib -Wl,-rpath," + ROOT + "/usr/lib"
        e["PKG_CONFIG_PATH"] = ROOT + "/usr/lib/pkgconfig:" + ROOT + "/usr/share/pkgconfig"
        e["LD_LIBRARY_PATH"] = ROOT + "/usr/lib:" + F + "/libs:" + e.get("LD_LIBRARY_PATH","")
        return e

    def _run(cmd, timeout=300):
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
    if action == "preflight":
        # R2/R4 (raport llama.cpp): test minim (C, C++, math, SSL, make) INAINTE
        # de un build mare - prinde toate problemele de linkare in ~10 secunde
        return _run([sys.executable, tc, "preflight"], 300)
    if action == "profile":
        # R3/R4b: flaguri gata facute (cmake/cflags/ldflags) - nu le descoperi iar
        return _run([sys.executable, tc, "profile", (a.get("package") or "cmake")], 60)
    if action == "fix":
        # re-aplica toate fixurile (dupa ce s-au reinstalat pachete Termux)
        return _run([sys.executable, tc, "fix"], 1800)
    if action == "env-file":
        return _run([sys.executable, tc, "env-file"], 120)
    if action == "bootstrap":
        return _run([sys.executable, tc, "bootstrap_direct"], int(a.get("timeout", 3600) or 3600))
    if action == "bootstrap_tpm":
        return _run([sys.executable, tc, "install"], int(a.get("timeout", 3600) or 3600))
    if action == "env":
        return _run([sys.executable, tc, "env"], 30)
    if action == "tpm":
        pkg = (a.get("package") or "").strip()
        if not pkg: return "lipseste 'package'"
        return _run([sys.executable, tpm, "install", pkg], int(a.get("timeout", 600) or 600))
    if action == "pip_install":
        pkg = (a.get("package") or "").strip()
        if not pkg: return "lipseste 'package'"
        # mediul COMPLET (target API, LD_PRELOAD, SSL_CERT_FILE, PATH cu /system/bin)
        # luat din toolchain.env_vars() - fara el pachetele C/C++ nu se compileaza
        full = (_toolchain_exports()
                + "(python3 -m pip || pip3 || pip) install --no-cache-dir '%s' 2>&1 | tail -25"
                % pkg)
        res = run_adbsh_tool(full, int(a.get("timeout", 2400) or 2400))
        # extensiile C++ au nevoie de NEEDED libc++_shared (altfel "cannot locate symbol")
        try:
            fix = ("import importlib.util as iu;"
                   "sp=iu.spec_from_file_location('tc','%s');"
                   "m=iu.module_from_spec(sp);sp.loader.exec_module(m);"
                   "m._fix_libcxx_needed()" % tc)
            r2 = _run([sys.executable, "-c", fix], 900)
            if "LIBCXX_ADDED" in r2:
                res += "\n" + r2.strip().split("\n")[-1]
        except Exception:
            pass
        return res
    if action == "compile":
        srcf = (a.get("source") or "").strip()
        out = (a.get("out") or "/data/local/tmp/out.bin").strip()
        # /sdcard e montat noexec: mut binarul in /data/local/tmp daca e acolo
        if out.startswith("/sdcard") or out.startswith("/storage"):
            out = "/data/local/tmp/" + os.path.basename(out)
        if not srcf: return "lipseste 'source'"
        cpp = srcf.endswith((".cpp", ".cc", ".cxx"))
        # aleg compilatorul prin SHELL (app-ul nu vede /data/local/tmp)
        cc = "clang++" if cpp else "clang"
        flags = (a.get("flags") or "").strip()
        # .so => shared library; altfel executabil
        shared = out.endswith(".so")
        mode = "-shared -fPIC" if shared else ""
        # RULARE PRIN SHELL (uid=2000): app-ul NU poate executa din /data/local/tmp
        full = (_toolchain_exports()
                + "cd /data/local/tmp && %s %s -O2 '%s' -o '%s' %s && echo COMPILE_OK"
                % (cc, mode, srcf, out, flags))
        r = run_adbsh_tool(full, int(a.get("timeout", 600) or 600))
        if "COMPILE_OK" in r and not shared:
            rr = run_adbsh_tool("export LD_LIBRARY_PATH=%s:$LD_LIBRARY_PATH; '%s'" % (ROOT + "/usr/lib", out), 120)
            return r + "\n--- OUTPUT BINAR ---\n" + rr
        return r
    if action == "run":
        exe = (a.get("source") or a.get("package") or "").strip()
        if not exe: return "lipseste 'source' (calea binarului)"
        return run_adbsh_tool("export LD_LIBRARY_PATH=%s:$LD_LIBRARY_PATH; '%s'" % (ROOT + "/usr/lib", exe), 120)
    return "actiune necunoscuta: " + action


def ask(messages=None, tools=None):
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
    r=urllib.request.Request("https://api.deepseek.com/chat/completions",data=json.dumps({"model":os.environ.get("DS_MODEL","deepseek-flash"),"messages":_msgs,"tools":_tools,"max_tokens":131072,"thinking":{"type":os.environ.get("DS_THINKING","disabled")}}).encode(),headers={"Authorization":"Bearer "+K,"Content-Type":"application/json"})
    try:
        d=json.loads(urllib.request.urlopen(r,timeout=600).read()); return d["choices"][0]["message"], d.get("usage")
    except Exception as e:
        print(R+" [API] "+e.__class__.__name__+": "+str(getattr(e,"read",lambda:b"")())[:300]+N);return None,None
def do_learn(trigger="/learn"):
    """Shared /learn routine: used by the manual /learn command AND by auto-learn.
    `trigger` is only a label shown in the task footer (e.g. '/learn' or 'auto-learn')."""
    prev=mem(); nprev=len(prev); lea=last_learn_idx(); li=len(M)
    _c,_t,_nb,_den=mstats(prev)
    M.append({"role":"user","content":LEARN_TAG+" The operator EXPLICITLY asks you to update your memory NOW.\n"
      "File: "+MEM+" ("+str(_c)+" chars ~ "+str(_t)+" tok, "+str(_nb)+" bullets, "+str(_den)+" chars/bullet). It is loaded ONCE, at session start; the MEMORY block above IS that snapshot. Nothing you write now is visible before the next start, so do not re-read it expecting a refresh.\n"
      "Learn ONLY the messages after index "+str(lea)+" ("+str(len(M)-lea)+" msgs). Index < "+str(lea)+" is already covered by memory: do not re-read, re-append or summarise it.\n"
      "GOAL OF MEMORY: it exists ONLY so that next session you are FASTER and do NOT repeat this session's mistakes. It is NOT a diary, NOT a summary, NOT a task log. Every line must be a REUSABLE lesson. If a line would not change your behaviour next time, it does not belong in memory.\n"
      "SIZE POLICY: the file is UNLIMITED - there is no cap and size is NEVER a reason to delete a true lesson. The only quality rule is EFFICIENCY PER LINE: maximum signal, zero filler. A line that restates something already there, or that no future session would ever consult, is a defect no matter how small the file is.\n"
      "MANDATORY 4-STEP PROCEDURE - one single python tool call does all of it, no other call, no prose. Inside it:\n"
      "  1) READ the CURRENT memory.md FIRST (read "+MEM+"). You MUST know every existing bullet before writing anything.\n"
      "  2) EXTRACT from the session ONLY the hard lessons, in this order of value: (a) a mistake I made and the FIX that worked -> becomes a TRAP line; (b) something that verifiably works and is worth reusing -> OK/P line; (c) something proven NOT to work -> DEAD line. Skip everything else.\n"
      "  3) TEST EACH CANDIDATE AGAINST THE MEMORY YOU JUST READ - a new fact is written ONLY if BOTH hold:\n"
      "     - it is NOT already covered by an existing bullet (same cause, same fix, same path, even in different words). If the idea is already there, DO NOT WRITE IT: it means you learned nothing new. Merge/refresh the old bullet IN PLACE instead of adding a duplicate.\n"
      "     - it was NOT already applied: if the session's mistake is exactly a mistake the memory already warned about, the real lesson is 'A TRAP I ignored, reinforce it', not a new line. Tighten that existing bullet.\n"
      "  4) WRITE the minimum. Zero flakes, zero repetition. A good /learn adds 2-6 lines, rarely more. If nothing genuinely new was learned, add NOTHING and say so - an honest empty update beats 20 useless lines.\n"
      "- EDIT BY CODE, NOT BY RETYPING: delete/merge/replace old lines with regex or `in` filters. Never print the file content (code and output stay in the history and are re-sent on every round). Print ONLY stats: chars before/after, bullets before/after, exact NEW lines added (short), lines merged/removed.\n"
      "- Deterministic cleanup EVERY time: drop exact duplicate lines (normalised: lowercase, collapse spaces) AND near-duplicates (same first 6 significant words), strip trailing spaces, collapse blank lines, one bullet = one fact.\n"
      "- SIZE IS UNLIMITED: the memory has NO cap - never delete a still-true, reusable lesson because the file feels big. A large dense file is FINE. What is NOT fine is a padded line.\n"
      "- WRITE DISCIPLINE (the only rule, applied whatever the current size): append with mode 'a', NEVER truncate the whole file, and add at most the few genuinely-new bullets you found in step 3. When several existing bullets clearly overlap on the same subject, merge them in place into one denser line (this SHRINKS only redundancy, never information). Keep every exact path/command/error string.\n"
      "- SELF-CLEANING: you MAY rewrite a section by code to merge/dedupe it, but only to remove redundancy - the result must still contain every distinct fact present before. If in doubt, keep the old line.\n"
      "FORMAT - one lesson = ONE line, <=300 chars, telegraphic, no sentences:\n"
      "  `TRAP: what I did -> exact error -> cause -> fix that worked` (exact command/flag/path/error string - this is the MOST valuable line type)\n"
      "  `OK: command/path/flag that verifiably works`   `DEAD: what does NOT work -> proof`   `P: absolute path -> artifact / how to run it`\n"
      "  `PREVENT: rule to apply next time so <trap> never happens again` (only when it is a real, reusable rule)\n"
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
    if li<len(M) and M[li].get("role")=="user" and str(M[li].get("content") or "").startswith(LEARN_TAG):
        M[li]["content"]=LEARN_TAG+" a memory update already happened here and is already on disk; it becomes visible in the system prompt only at the next session start. Everything BEFORE this line is covered by memory: do not re-learn it."
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
        for _w in _lint:
            _txt = _w[1]
            if _w[0]:  # (length, line) -> too long
                _bad.add(_w[1].strip())
            elif _txt.startswith("forbidden"):
                _bad.add(_txt.split("]: ", 1)[-1].strip())
        _kept = [l for l in now.split("\n")
                 if not (l.strip().startswith(("TRAP:","OK:","DEAD:","P:","PREVENT:")) and l.strip() in _bad)]
        _dropped = len(now.split("\n")) - len(_kept)
        if _dropped > 0:
            now = "\n".join(_kept)
            try: open(MEM, "w", encoding="utf-8").write(now)
            except Exception as _e: print(R+"   [mem] could not rewrite memory: "+str(_e)+N)
        print(R+"   [mem] LINT: "+str(len(_lint))+" issue(s); dropped "+str(_dropped)+" bad lesson line(s) (not saved to memory)."+N)
        for _w in _lint[:6]:
            _msg = ("line "+str(_w[0])+" chars (>300): "+_w[1][:90]) if _w[0] else _w[1]
            print(R+"        ! "+_msg+N)
        if len(_lint)>6: print(R+"        ... +"+str(len(_lint)-6)+" more"+N)
    elif _nless:
        print(G+"   [mem] lint OK: "+str(len(_nless))+" lesson line(s), all <=300 chars, no forbidden content."+N)
    save_ctx()
    if m and m.get("content"): print("\n"+RED+"AGENT"+C+" >"+N+"\n\n"+render(m["content"].strip()))
    print(G+"   [/learn] the new memory loads into the system prompt at the NEXT startup."+N)
    print(_task_foot("/learn")); flush_task_tokens(); return


def auto_learn_check(task_steps, had_error, task_msgs=None):
    """V4 hybrid auto-learn, run right AFTER a task finishes (only if AUTOLEARN['on']).
    Filter (cheap): only bother on a non-trivial task - enough steps OR an error occurred.
    Decision (model): ONE short call, no tools. The model replies EITHER "NO" (nothing reusable)
    OR one dense lesson line (TRAP:/OK:/DEAD:/P:/PREVENT: ...). A valid, non-duplicate line is
    APPENDED STRAIGHT TO MEMORY (no full re-analysis), so subtle lessons (a misleading command
    without root, a working path, a proven dead end) are not lost. Anything unexpected falls
    back to the old do_learn() path. Returns nothing; prints what it did. /auto-learn toggles."""
    if not AUTOLEARN["on"]:
        return
    if task_steps < AUTOLEARN["min_steps"] and not had_error:
        return   # task prea mic: iesim silentios (fara mesaj in output)
    # DECIZIE: un singur mesaj, FARA tools, dar CU istoricul taskului (altfel modelul nu vede
    # la ce se refera "the task that just finished above" si raspunde NO orbește).
    try:
        _msgs = list(task_msgs) if task_msgs is not None else list(M)
        _probe = ask(_msgs+[{"role":"user","content":AUTO_LEARN_PROMPT}], tools=[])
    except Exception as e:
        print(OF+"   [auto-learn] decision call failed ("+e.__class__.__name__+") - skipped."+N)
        return
    _raw = ""
    try:
        _raw = (((_probe[0] if _probe else None) or {}).get("content") or "").strip()
    except Exception:
        pass
    if not _raw:
        print(G+"   [auto-learn] decision call returned empty - skipped."+N)
        return
    # Noul format: fie "NO", fie UNA SAU MAI MULTE linii de lectie (TRAP:/OK:/DEAD:/P:/PREVENT:),
    # cate una pe linie. Fiecare linie trece INDIVIDUAL prin mem_lint (valoare + format + Android).
    _KEYS = ("TRAP:","OK:","DEAD:","P:","PREVENT:")
    _cand = []
    for _ln in _raw.split("\n"):
        _ln = _ln.strip().strip("`").strip().strip('"').strip("'").strip()
        _ln = " ".join(_ln.split())                      # colapseaza spatiile din interior
        if not _ln: continue
        if _ln.upper() == "NO": continue
        # Limita 500: o lectie utila (TRAP cu cauza+fix) nu incape in 300. NU o mutila la
        # mijloc de cuvant - taie doar la granita de propozitie, altfel pastreaza tot.
        if len(_ln) > 500:
            _cut = _ln[:500]
            for _sep in (" -> ", ". ", "; ", ", "):
                _p = _cut.rfind(_sep)
                if _p > 200: _cut = _cut[:_p+len(_sep)]; break
            _ln = _cut.rstrip(" ,;-")
            while _ln.endswith("->"): _ln = _ln[:-2].rstrip(" ,;-")
        if _ln.upper().startswith(tuple(k.upper() for k in _KEYS)):
            _cand.append(_ln)
    if not _cand:
        # nimic valid: fie NO explicit, fie altceva
        _flat = " ".join(_raw.split())
        if _flat.upper() == "NO" or _flat.upper().startswith("NO "):
            print(G+"   [auto-learn] decision: NO - nothing reusable was learned, memory untouched."+N)
        elif _flat.upper().startswith("YES"):
            print(G+"   [auto-learn] decision: YES (no explicit line) - running full do_learn()."+N)
            do_learn("auto-learn")
        else:
            print(G+"   [auto-learn] decision: unrecognised reply - skipped. Got: "+_flat[:80]+N)
        return
    # memorie existenta (pentru dedup)
    try:
        _mem = open(MEM, "r", encoding="utf-8").read() if 'MEM' in globals() else ""
    except Exception:
        _mem = ""
    def _norm(x):
        return "".join(x.lower().split())
    _memnorm = _norm(_mem)
    _tgt = MEM if 'MEM' in globals() else None
    if not _tgt:
        print(OF+"   [auto-learn] memory path unknown - falling back to do_learn()."+N)
        do_learn("auto-learn"); return
    _saved, _skipped = [], []
    for _ln in _cand:
        # duplicat?
        if _norm(_ln) in _memnorm:
            _skipped.append(("duplicate", _ln)); continue
        # validare stricta (format + Android + VALOARE)
        try:
            _issues, _ = mem_lint(_ln)
        except Exception:
            _issues = []
        _why = None
        for _w in _issues:
            _txt = _w[1]
            if _w[0] and _txt.strip() == _ln: _why = "too long"
            elif _txt.startswith("forbidden"): _why = _txt.split("]:",1)[0].replace("forbidden [","")
            elif _txt.startswith("low value"): _why = "low value"
        if _why:
            _skipped.append((_why, _ln)); continue
        _saved.append(_ln)
        _memnorm += _norm(_ln)
    if _saved:
        try:
            with open(_tgt, "a", encoding="utf-8") as _f:
                for _ln in _saved: _f.write("\n" + _ln + "\n")
            print(G+"   [auto-learn] decision: YES - saved "+str(len(_saved))+" lesson(s):"+N)
            for _ln in _saved: print(G+"        + "+_ln[:120]+N)
        except Exception as e:
            print(OF+"   [auto-learn] write failed ("+e.__class__.__name__+") - falling back to do_learn()."+N)
            do_learn("auto-learn"); return
    for _why, _ln in _skipped:
        print(OF+"   [auto-learn] skipped ("+_why+"): "+_ln[:90]+N)
    if not _saved and not _skipped:
        print(G+"   [auto-learn] decision: NO - nothing reusable was learned, memory untouched."+N)


refresh()   # the memory enters the system prompt ONCE, here; from now on the prefix never changes again
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
    if q in ("/exit","/quit"): break
    if q in ("/help","/?"):
        _al="ON" if AUTOLEARN["on"] else "OFF"
        print(G+"   COMMANDS"+N)
        print(G+"     /learn              update memory now (manual learning)"+N)
        print(G+"     /auto-learn on|off  learn BY ITSELF after each finished task (now: "+_al+", min "+str(AUTOLEARN["min_steps"])+" steps)"+N)
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
        print(G+"   "+(HINT_LINE)+N)
        continue
    if q=="/ctx":
        _a=[f for f in (os.listdir(ARCH) if os.path.isdir(ARCH) else []) ]
        _l=[f for f in (os.listdir(LOGDIR) if os.path.isdir(LOGDIR) else []) ]
        print(G+"   [ctx] window: "+str(len(M))+" messages ~ "+_K(ctx_tokens())+"tok | compress threshold "+_K(CTXBUDGET)+"tok (0=off) | steps kept intact: last "+str(CTXKEEP)+N)
        print(G+"   [ctx] archives: "+str(len(_a))+" in archive/ | tool logs: "+str(len(_l))+" in logs/ | nothing is ever deleted, only moved to disk"+N); continue
    if q=="/compact":
        ok=compact_history(force=True); save_ctx()
        print(G+"   [compact] "+("done, context compressed WITHOUT loss (the original is in archive/)" if ok else "nothing to compress / archiving failed - I touched nothing")+N); continue
    if q in ("/nospin","/spin"):
        NOSPIN[0]=(q=="/nospin"); print(G+"   [ui] "+("NOSPIN: no live line at all - the terminal scrollback stays clean (recommended on a phone)" if NOSPIN[0] else "live line back on (spinner + timer rewritten in place)")+N); continue
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
        print(G+"   [reset] the conversation history was erased ("+os.path.basename(CTX)+")"+N); continue
    if q.startswith("/auto-learn"):
        arg=q.split(None,1)[1].strip().lower() if len(q.split(None,1))>1 else ""
        if arg in ("on","1","yes"):
            AUTOLEARN["on"]=True;  print(G+"   [auto-learn] ON - after each finished task I decide myself whether to update memory."+N)
        elif arg in ("off","0","no"):
            AUTOLEARN["on"]=False; print(G+"   [auto-learn] OFF - learning only via the manual /learn command."+N)
        else:
            print(G+"   [auto-learn] currently "+(("ON" if AUTOLEARN["on"] else "OFF"))+" - use /auto-learn on|off"+N)
        continue
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
        M.append(m);save_ctx()
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
                o=call_tool(c)          # compact: only the summary; the CUT output is what gets sent to the model
                M.append({"role":"tool","tool_call_id":c["id"],"content":o});compact_history();save_ctx()
        else:
            print("\n"+RED+"AGENT"+C+" >"+N+"\n\n"+render((m.get("content") or "").strip())+"\n")
            print(_task_foot())
            auto_learn_check(TASK["steps"], TASK["err"], M[mark:])
            flush_task_tokens()
            break
    except KeyboardInterrupt:
        LIVE.update(phase="idle",desc="",col=None,n=0)   # kill the live line first: no "step 00" left stuck on screen
        print("\r\33[K",end="",flush=True)
        print(G+"   [Ctrl+C] stopped ONLY the current step. The tools run so far stay in the context (the agent knows where it stopped). /reset to make it forget the whole task."+N)
        while len(M)>mark and M[-1].get("role")=="assistant" and not M[-1].get("tool_calls"): M.pop()
        complete_pending(M);save_ctx(); print(_task_foot("interrupted by the operator")); flush_task_tokens(); continue
save_ctx()   # on /exit or Ctrl+D the history is already on disk

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
