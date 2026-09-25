#!/usr/bin/env python3
import base64,datetime,json,os,random,re,shutil,signal,subprocess,sys,tempfile,threading,time,urllib.request
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
def render(t):
    out=[]
    for p in BLK.split(t):
        if p.startswith("```"):
            L=p.strip("\n").split("\n"); body=[x for x in L[1:] if not x.strip().startswith("```")]
            out.append(_box(L[0].strip("` ").strip() or "code",body))
        else:
            out.append(_chunk(_compact(p)))
    return re.sub(r"^\n+","",re.sub(r"\n(?:\n)+$","\n","".join(out)))
WORK=os.path.join(os.path.dirname(os.path.abspath(__file__)),"temp")
os.makedirs(WORK,exist_ok=True)
CTXNAME="context.json"       # conversation history: lives permanently in the working folder (temp)
for f in os.listdir(WORK):   # clean working folder on every startup
    if f in (CTXNAME,CTXNAME+".tmp","logs","archive"): continue   # the context, the logs and the archives are NOT deleted
    try: os.remove(os.path.join(WORK,f)) if os.path.isfile(os.path.join(WORK,f)) else shutil.rmtree(os.path.join(WORK,f))
    except Exception: pass
os.chdir(WORK)              # everything the agent does (files, tests, temp) lives here
K=open(os.path.expanduser("~/.deepseek_agent_key")).read().strip()
MEM=os.path.join(os.path.dirname(os.path.abspath(__file__)),"memory.md")
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
    """Scor de VALOARE 0-10 pentru o lectie de memorie. Memoria creste doar cu lectii care
    (a) spun o cauza si o consecinta (->), (b) contin detalii specifice (numere/erori/Api.metoda),
    (c) sunt destul de lungi sa fie informative. Respinge banalitatile si observatiile fara
    consecinta. Utilizat strict: < 2 => lectia NU se scrie."""
    import re as _r
    s = 0
    if "->" in line: s += 3
    if _r.search(r"\d", line): s += 2
    if _r.search(r"[a-z]+\.[A-Z]\w+", line): s += 2
    if _r.search(r"\b(ERROR|DENY|DENIED|Exception|errno|ENOENT|EACCES|Permission|SELinux|null|refuses?|not found)\b", line, _r.I): s += 2
    if len(line) < 60: s -= 3
    if line.upper().startswith(("OK:", "P:")) and "->" not in line: s -= 2
    if line.upper().startswith(("RULE:", "RULE (")): s += 3   # regula de ordine/decizie = mereu valoroasa
    return s


def mem_lint(txt):
    """Checks EVERY /learn write LINE BY LINE (the prompt's rules, enforced in code):
    - one lesson = ONE line, <=300 chars (density warns only on the AVERAGE)
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
        # ORICE linie de corp trebuie sa fie o lectie cu prefix valid.
        # Altfel text liber (observatii, paragrafe) intra in memorie fara nicio validare.
        if not l.startswith(("TRAP:","OK:","DEAD:","P:","PREVENT:","RULE:","RULE (","- ","* ")):
            out.append((0, "no valid prefix (TRAP:/OK:/DEAD:/P:/PREVENT:/RULE:): " + l[:60]))
            continue
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
# CHUNK: when the caller emits MORE than this many chars in one tool call, the output is NOT cut at
# TOOLMAX but at CHUNK - so a long, deliberate read (a big file split into parts) is not decapitated
# in the middle. Raise it with AGENT_CHUNK; set AGENT_CHUNK=0 to keep the old TOOLMAX behaviour.
CHUNK=int(os.environ.get("AGENT_CHUNK","60000"))     # budget per tool call, in chars (1M-token window: 60k chars = 1.4% of it)
BUDGETWARN=float(os.environ.get("AGENT_BUDGETWARN","0.9"))   # warn once per task above this share of CHUNK
BUDGETWARNED=[False]   # re-armed at the start of every task, so it cannot repeat in the same task
# The model's REAL context window. VERIFIED against the API, not guessed:
#   GET https://api.deepseek.com/models -> deepseek-flash: context_window=1048576 (1M)
#   (max_output_tokens=393216). A hardcoded 128000 here caused a FALSE "125% of the window"
#   warning when the session was really at ~15%. If the model ever changes, re-check the API.
CTXWINDOW=int(os.environ.get("AGENT_CTXWINDOW","1048576"))   # 1M tokens, confirmed by the API
CTXWARN=int(os.environ.get("AGENT_CTXWARN","90"))            # warn (RED, loud) at this % of the window
CTXBUDGET=0   # COMPRESSION IS DISABLED, by the operator's explicit decision: no automatic
#   compaction and none via /compact. The context grows until **the operator** gives /reset, so the
#   MEMORY block inserted at startup stays present, byte for byte, for the ENTIRE session.
#   Set AGENT_CTXBUDGET to a number only if you deliberately want the old behaviour back.
CTXKEEP=24         # how many recent messages are never compressed
LOGDIR=os.path.join(WORK,"logs")      # complete tool outputs (not deleted between sessions)
ARCH=os.path.join(WORK,"archive")     # COMPLETE snapshots of the history, before every compression
VERBOSE=[os.environ.get("AGENT_VERBOSE")=="1"]   # /verbose: re-prints code + output in the terminal
THINKMIN=float(os.environ.get("AGENT_THINKMIN","0"))   # MINIMUM time "Thinking..." stays on screen (0 = the printed time is exactly the measured one). It never delays a tool step.
def _budget():
    """How much of a tool output fits IN THE WINDOW for this call. CHUNK raises it so a
    deliberate long read is not decapitated; AGENT_CHUNK=0 falls back to TOOLMAX."""
    return CHUNK if CHUNK and CHUNK>TOOLMAX else TOOLMAX
def _cut(o,ref=None,complete=False):
    """What goes INTO THE WINDOW: the first 3/4 of the budget + the last 1/4 (the tail is where the
    tracebacks and the conclusion show up), plus a POINTER to the complete text on disk.
    `complete` says whether the pointer REALLY holds the whole text (see _store): if it does not,
    the marker says so instead of promising a file that is itself cut - that promise was wrong
    before and cost whole sessions of re-reading."""
    b=_budget()
    if len(o)<=b: return o
    h,t=b*3//4,b//4
    hidden=str(len(o)-b)
    if ref and complete:
        mid="[... "+hidden+" chars in the middle, NOT LOST: the complete text in "+ref+" (open it and read by offset) ...]"
    elif ref:
        mid="[... "+hidden+" chars in the middle, LOST (the log "+ref+" is itself truncated; nothing else holds it) - RE-RUN the step in smaller parts ...]"
    else:
        mid="[... "+hidden+" chars in the middle, LOST (no log was written) - RE-RUN the step in smaller parts ...]"
    return o[:h]+"\n"+mid+"\n"+o[-t:]
def _store(o):
    """Writes the COMPLETE output into a log on disk and returns (what enters the window, path|None).
    The file is written in full and then VERIFIED by size; the window marker is only allowed to say
    NOT LOST when the file on disk really contains every byte."""
    b=_budget()
    if len(o)<=b:
        # Preventive warning, ONCE PER TASK: the output still fits, but one step like this bigger and the
        # middle is gone. Said now, while it can still be acted on (chunk it / use the `read` tool).
        # Measured: it fires rarely (1 in 251 outputs in a long session), so it is signal, not noise.
        if len(o)>b*BUDGETWARN and not BUDGETWARNED[0]:
            BUDGETWARNED[0]=True
            print(OF+"   [budget] this step returned "+str(len(o))+" chars, close to the "+str(b)+
                  "-char window limit - one step bigger loses its middle. Split it (emit <"+str(int(b*BUDGETWARN))+
                  " chars per step) or read the rest with the `read` tool."+N)
        return o,None
    os.makedirs(LOGDIR,exist_ok=True)
    p=os.path.join(LOGDIR,"tool_"+datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")+".log")
    complete=False
    try:
        with open(p,"w",encoding="utf-8") as f: f.write(o)
        complete=(os.path.getsize(p)==len(o.encode("utf-8")))   # verified, not assumed
    except Exception:
        return _cut(o,None,False),None
    return _cut(o,os.path.relpath(p,WORK),complete),p
def _tokm(m):
    s=str(m.get("content") or "")
    for tc in (m.get("tool_calls") or []): s+=str((tc.get("function") or {}).get("arguments") or "")
    return len(s)//4
_CTXCACHE=[None,None,None]   # [len(M), suma_len_content, tokeni]
def _ctxsig():
    """Semnatura IEFTINA a ferestrei: numarul de mesaje + suma lungimilor de content.
    Prinde ORICE schimbare reala (append, pop, reset, M[i]['content']=... in-place),
    fara sa reconstruiasca stringurile. ~1 ms la 1000 de mesaje."""
    n=len(M); tot=0
    for m in M:
        c=m.get('content')
        tot+= len(c) if isinstance(c,str) else 0
        tc=m.get('tool_calls')
        if tc:
            for t in tc:
                tot+= len(str((t.get('function') or {}).get('arguments') or ''))
    return n,tot
def ctx_tokens():
    """Tokenii din fereastra, cu cache pe semnatura continutului.
    ctx_warn() o cheama dupa FIECARE tool call: fara cache, parcurgerea a 1000+
    de mesaje de fiecare data e munca irosita (masurat: 0.6 ms x ~10/pas = 6 ms/pas)."""
    sig=_ctxsig()
    if _CTXCACHE[0]==sig[0] and _CTXCACHE[1]==sig[1] and _CTXCACHE[2] is not None:
        return _CTXCACHE[2]
    t=sum(_tokm(m) for m in M)
    _CTXCACHE[0]=sig[0]; _CTXCACHE[1]=sig[1]; _CTXCACHE[2]=t
    return t
CTXWARNED=[False]   # warns ONCE per crossing (re-arms if the context shrinks, i.e. after /reset)
CTXWINDOW_VERIFIED=[False]
def ctx_check_window():
    """Asks the API what the model's context window REALLY is and corrects CTXWINDOW if the local
    constant is wrong. Why it exists: a hardcoded window (128000) produced a false '125% of the
    window' warning when the session was really at 15%. One cheap call at startup, cached for the
    session; if the network fails, the local constant stays - never a crash."""
    global CTXWINDOW
    if CTXWINDOW_VERIFIED[0]: return
    CTXWINDOW_VERIFIED[0]=True
    try:
        r=urllib.request.Request("https://api.deepseek.com/models",headers={"Authorization":"Bearer "+K})
        d=json.loads(urllib.request.urlopen(r, timeout=_timeout).read())
        mid=os.environ.get("DS_MODEL","deepseek-flash")
        for m in (d.get("data") or []):
            if m.get("id")==mid:
                w=int(m.get("context_window") or 0)
                if w and w!=CTXWINDOW:
                    print(OF+"   [ctx] the API reports a "+_K(w)+" window for "+mid+" (local constant was "+_K(CTXWINDOW)+") - corrected."+N)
                    CTXWINDOW=w
                break
    except Exception:
        pass    # keep the local constant: never block the startup on this
def ctx_warn():
    """LOUD RED warning when the context approaches the model window. It does NOT compress, does NOT
    touch the history and does NOT stop anything - it only tells the operator it is time for /reset.
    Fires once per crossing, so it cannot spam every round."""
    _ct=ctx_tokens()                       # UN singur calcul (inainte: 3 apeluri per warn)
    pct=100.0*_ct/CTXWINDOW if CTXWINDOW else 0.0
    if pct>=CTXWARN:
        if not CTXWARNED[0]:
            CTXWARNED[0]=True
            bar="\u2588"*40
            print("\n"+R+"   "+bar+N)
            print(R+"   \u26a0 CONTEXT AT "+("%.0f"%pct)+"% OF THE WINDOW ("+_K(_ct)+"/"+_K(CTXWINDOW)+" tok)"+N)
            print(R+"   \u26a0 Time to /reset: the next requests may be rejected by the API."+N)
            print(R+"   \u26a0 I did NOT compress or delete anything - the memory stays intact."+N)
            print(R+"   "+bar+N+"\n")
    elif pct<CTXWARN-10:
        CTXWARNED[0]=False      # re-arm once we drop well below (e.g. after /reset)
def compact_history(force=False):
    """DISABLED on purpose (operator decision). It used to move heavy tool outputs and old steps to
    disk and replace them with pointers, so the window stayed small. The operator wants the memory -
    inserted ONCE at startup - to stay present, untouched, until THEY say /reset, so this now does
    nothing at all: neither automatically nor via /compact. Kept as a function because the call sites
    exist; returning 0 = 'nothing was compressed'."""
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
    No labels are prepared here: each one is produced from the code of that very step (see brief)."""
    TASK.update(t0=time.time(),steps=0,think=0.0,tool=0.0,chars=0,tok_in=0,tok_out=0,cache=0,n=TASK["n"]+1,err=False)
    BUDGETWARNED[0]=False   # fresh task: the budget warning may fire once again
    LIVE.update(phase="think",desc="",col=None,n=0,t=time.time())
    t=" TASK #"+str(TASK["n"])+" "
    w=len(t)+6   # a little wider than the text (a few dashes of air), still compact
    pad=w-len(t)   # so the right border lines up with the top/bottom borders
    box=[BAR+"╭"+"─"*w+"╮"+N,
         BAR+"│"+N+ST+t+N+" "*pad+BAR+"│"+N,
         BAR+"╰"+"─"*w+"╯"+N]
    return "\n"+"\n".join(box)+"\n\n"+N   # box, then exactly 2 blank lines before the first step
def _task_foot(stare="done"):
    """Closes the task: stops the timer and breaks down the total (thinking vs. tool) + the steps + the TOKENS
    consumed by this task, taken from the server usage accumulated in TASK since _task_head()."""
    tot=(time.time()-TASK["t0"]) if TASK["t0"] else 0.0
    LIVE.update(phase="idle",desc="",col=None,n=0)
    ph=TASK["think"]+TASK["tool"]
    other=max(0.0,tot-ph)   # time NOT covered by any _spin: HTTP request, parsing, compact_history/save_ctx, rounding
    b=G+"  ·  "+str(TASK["steps"])+(" step" if TASK["steps"]==1 else " steps")+"  ·  total "+C+_dur(tot)+N+G+" = thinking "+_dur(TASK["think"])+" + tool "+_dur(TASK["tool"])+" + other "+_dur(other)+N
    b+=G+"  ·  tok \u2191"+_K(TASK["tok_in"])+" \u2193"+_K(TASK["tok_out"])+" = "+_K(TASK["tok_in"]+TASK["tok_out"])+" this task"
    if TASK["tok_in"]: b+=" \u00b7 cache HIT "+("%d%%"%int(100.0*TASK["cache"]/TASK["tok_in"]))
    b+=N
    return BAR+"  +-"+N+ST+" TASK #"+str(TASK["n"])+" "+stare+N+b

# ==================== MONITOR DE STATUS (0 tokeni, fara API) ====================
# DE CE: verificarea periodica PRIN API ar retrimite tot contextul la fiecare check
# (~7k tok x 30 check-uri = ~255k tokeni). Acest thread scrie pe ECRAN, nu in context:
# 0 cereri API, 0 tokeni. Se activeaza cu /watch [sec] sau AGENT_WATCH=1.
WATCH = {"on": os.environ.get("AGENT_WATCH") == "1",
         "sec": int(os.environ.get("AGENT_WATCH_SEC", "60") or 60)}

def _watch_snapshot():
    """Ce joburi de fundal ruleaza ACUM, verificat pe /proc (nu ghicit).
    Intoarce o lista de tuple (nume, stare, pid, secunde, log). Fara API, fara context."""
    out = []
    try:
        import glob as _g
        for d in _g.glob("/tmp/agent_bg/*"):
            n = os.path.basename(d)
            pid = 0
            try:
                pid = int(open(os.path.join(d, "pid")).read().strip())
            except Exception:
                pass
            alive = "?"
            if pid:
                try:
                    st = open("/proc/%d/stat" % pid).read().split(") ", 1)[1].split()[0]
                    alive = "RUNNING" if st not in ("Z", "X") else "DONE"
                except Exception:
                    alive = "DONE"
            out.append((n, alive, pid, 0, d))
    except Exception:
        pass
    return out

def _watch_loop():
    """Scrie o linie compacta la fiecare WATCH['sec'] secunde. Doar stdout, niciodata in context."""
    last = ""
    while not WATCH.get("stop"):
        time.sleep(max(10, int(WATCH.get("sec", 60))))
        if not WATCH.get("on"):
            continue
        try:
            rows = [r for r in _watch_snapshot() if r[1] == "RUNNING"]
        except Exception:
            continue
        if not rows:
            continue
        line = "  ".join("%s pid=%d" % (n, p) for n, a, p, d, l in rows)
        if line == last:
            continue                    # nimic nou: nu scrie (fara zgomot)
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
    return st
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
    if VERBOSE[0] or not sys.stdout.isatty():
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
    not a comment, and not a bare label: it counts lines starting with TRAP:/OK:/DEAD:/P:/PREVENT:/RULE:- or '- '."""
    lines=[l.strip() for l in s.split("\n") if l.strip()]
    nb=len([l for l in lines if not l.startswith(("#","<!--")) and (
        l.startswith(("TRAP:","OK:","DEAD:","P:","PREVENT:","RULE:","RULE (","- ","* ")) or (":" in l[:12] and not l.startswith("##")))])
    return len(s),len(s)//4,nb,(len(s)//nb if nb else 0)
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
V=E+"[38;5;245m";R=E+"[38;5;179m";N=E+"[0m";C=E+"[38;5;109m";OF=E+"[38;5;180m"
SB=E+"[38;5;180m";ST=E+"[38;5;114m";SD=E+"[38;5;243m";BAR=E+"[38;5;240m"
RY=E+"[38;5;139m";GY=E+"[38;5;109m";MOV=E+"[38;5;139m"
TC=E+"[38;5;216m";TCB=E+"[38;5;180;48;5;236m"   # TC=calling a tool (warm amber), TCB=its banner on a dark strip: differs from the step line (grey/teal)   # SOFT: RY=sageata thinking, GY=tool (teal), MOV=cutia THINKING (violet moale), toate fara bold
T=[{"type":"function","function":{"name":"python","description":"Run Python 3 code here (stdlib only), returns stdout/stderr. Default engine: parsing (JSON/INI), logic, aggregation, text transform, HTTP. Slow on multi-million-line streams.","parameters":{"type":"object","properties":{"code":{"type":"string"}},"required":["code"]}}},
   {"type":"function","function":{"name":"bash","description":"Run a BASH shell command (bash -lc), returns stdout+stderr. For pure pass-through streams and many-small-files work: grep/wc/head/tail/sort/uniq/find/du, xargs -P. Not for parsing or logic.","parameters":{"type":"object","properties":{"cmd":{"type":"string","description":"the full shell command line, e.g. grep -c ERROR app.log | sort | uniq -c"}},"required":["cmd"]}}},
   {"type":"function","function":{"name":"smart","description":"AUTO-ROUTER: give it the shell cmd and/or the Python code; it picks the faster engine by itself and reports which and why. Use when unsure.","parameters":{"type":"object","properties":{"cmd":{"type":"string","description":"the shell command you would run if bash is chosen"},"code":{"type":"string","description":"the Python code you would run if python is chosen"}},"required":["cmd"]}}},
   {"type":"function","function":{"name":"look","description":"Look at an IMAGE file (screenshot, chart, photo) with vision and answer a question about what is really in it. Never guess image content - look at it.","parameters":{"type":"object","properties":{"path":{"type":"string","description":"image file path (png/jpg), absolute or relative to the cwd"},"prompt":{"type":"string","description":"what to look for / what to answer"}},"required":["path"]}}},
   {"type":"function","function":{"name":"read","description":"Read a file by LINE RANGE with a guaranteed char budget (default 6000), never cut in the middle. ALWAYS use this instead of python print(open().read()). Raise budget (e.g. 20000) to take a whole medium file in ONE call - with the 1M window that is cheap, and one big read beats many small ones. Returns a footer with the EXACT next offset. Long file: first call with grep=regex for the map, then offset/limit.","parameters":{"type":"object","properties":{"path":{"type":"string","description":"file to read (absolute or relative to the cwd)"},"offset":{"type":"integer","description":"first line to read, 1-based (default 1)"},"limit":{"type":"integer","description":"how many lines to read at most (default: as many as fit the budget)"},"budget":{"type":"integer","description":"max characters to return, default 6000; raise to 20000+ for a whole medium file in ONE call"},"grep":{"type":"string","description":"optional regex: return only lines matching it (with their line numbers), then read around them"},"numbered":{"type":"boolean","description":"prefix every line with its number (default true - makes offsets reusable)"}},"required":["path"]}}},
   {"type":"function","function":{"name":"multi","description":"BATCH: 2-6 small, independent ops in ONE call, ONE consolidated answer. Biggest cost saver: each extra step re-sends the whole context. Keep entries small (a listing, a short cat, a status). Do NOT bundle heavy/crashable pipelines here.","parameters":{"type":"object","properties":{"ops":{"type":"array","description":"2-6 operations, each independent and small","items":{"type":"object","properties":{"kind":{"type":"string","description":"bash (a small shell command) or python (a few lines, stdlib only)","enum":["bash","python"]},"body":{"type":"string","description":"the command / the code for this entry, kept SHORT"},"name":{"type":"string","description":"short label shown in the output (e.g. env, ls, git status)"}},"required":["kind","body"]}}},"required":["ops"]}}}]

TOOLGUIDE=("TOOL SELECTION (measured on the Android toybox build; use the SAME rules when the target is GNU coreutils, where bash's sort/awk/sed are fast): you have 3 engines. "
  "1) `python`: THE DEFAULT AND THE FASTEST ENGINE for any computation. BEST for structured parsing (JSON/INI/KeyValues), logic, aggregation/counting, text transform, sorting, and HTTP (requests.Session beats repeated curl). Default to python for anything that is not a pure stream. "
  "2) `bash`: ONLY for pure pass-through streaming and for many-small-files work: grep -c / grep -m1 (early exit), wc, cat, head, tail, tr, sha256sum/md5sum (native C), find/du, and `ls glob | xargs -P8 ...`. "
  "3) `smart`: the AUTO-ROUTER - give it the shell cmd and/or the Python code and it picks the faster engine by itself from the measured rules above, then runs it. Use `smart` when unsure; it prints the engine and why. "
  "RULE OF THUMB: data must be COMPUTED (sort/count/aggregate/transform/parse) -> python; data only FLOWS through untouched or is read early-exited -> bash; thousands of small files in parallel -> bash with xargs -P. "
  "CAUTION: on the Android toybox build sort/awk/sed/base64/cut|sort|uniq are 3-95x SLOWER than python, so route those to python there. On GNU/Linux (this repo's usual host) bash is the right tool for sort/awk/sed and python for parsing/logic/HTTP. "
  "Never parse JSON with grep/awk: it is also WRONG (leaks values from escaped strings) - always python json.loads. "
  "WARNING: do NOT build a hybrid that captures a huge awk output into Python memory (subprocess capture_output on megabytes) - 14x the memory of plain bash. If you must combine, STREAM it (iterate stdout line by line).")

M=[{"role":"system","content":" You are a minimal autonomous agent. Use stdlib only. Your working directory is "+WORK+" - create every file, script and temporary test THERE, never elsewhere on the disk. Do the task end to end and verify it. " +
  "WHILE WORKING (mandatory, never skip): BEFORE EVERY python tool call you MUST put a FULL, COMPLETE sentence in the `content` field, in the operator\u2019s language, telling what you are about to do and why. There is NO word limit and NO character limit: NEVER cut, shorten or abbreviate it with \u201c...\u201d or \u201c\u2026\u201d - the operator must always see the WHOLE sentence he needs to follow you. NEVER send a tool call with empty content. Markdown is NOT allowed in that sentence. " +
  "VISION: you have a second tool, `look(path, prompt)` - it sends an IMAGE file to the same model with THINKING ENABLED and returns what is REALLY in it. Use it whenever the operator asks you to see/analyze a screen, a screenshot, a chart or a photo: first capture it (e.g. `xwd -root -out shot.xwd` then convert with ffmpeg to png), then call look on the png. Never guess what an image contains - look at it. " +
  "STEP LABELS: the FIRST line of every python/bash tool call is a comment (lowercase) - the terminal prints it as that step\u2019s label. Say WHAT the step does, in the operator\u2019s language (Romanian), never `# step 1` or `# test`. DENSITY RULE (this is billed, the label is part of the context sent on EVERY later request): one short line, the essential verb + object, no trailing explanation, no restating the task, no repeating the previous label. Aim for ~60-90 chars; a label that needs 200 is usually two steps or an explanation that belongs in the answer, not in the label. Completeness of INFORMATION, not of prose. " +
  
  "CODE DENSITY (the code you send is billed on EVERY later request): the `code`/`cmd` field of a tool call stays in the context forever and is re-sent each round - in a long session it is a third of the total input. So write the SHORTEST code that does the job: no decorative comments (only the one required label line), no re-printing data you already printed, no re-implementing something a stdlib call does in one line, no boilerplate headers. Prefer one clear line over five explained lines. This does NOT mean fewer steps or bigger pipelines: it means each step carries only the code it needs. " +"STOPPING CRITERION (a real failure from a build report): before you call a task done, state to yourself WHAT the finish line is (e.g. `python -c \"import numpy\"` exits 0 and prints the version). The task is NOT done because a tool printed OK - it is done when the FINAL verification returns the result that was asked for. After EVERY step that reports success, check the EFFECT on disk (does the file exist? does the command run?), not the status message. If a tool says OK but the effect is missing, treat it as a FAILURE and investigate the tool. NEVER end a turn with \"I did X, next comes Y\" when the operator asked for Y: finish Y. A half-done task reported as progress is worse than an honest \"I am blocked on Z\". " +
  "TIMING: tools that shell out return in milliseconds here, so a step that takes seconds means it is WAITING (a timeout, a lock, a network call) - investigate the cause instead of waiting it out. Do not sleep between steps: each step already waits exactly as long as its tool needs. " +
"BATCH SMALL STEPS (biggest cost saver): every request re-sends the WHOLE context, so each extra step costs the full history again. When you need 2-6 quick, INDEPENDENT things (a listing, a short cat, a status, a git branch, an env value), do NOT spend 6 steps: use the `multi` tool ONCE with the list of ops. Rule of thumb: if step B would not read anything step A printed, they belong in the SAME `multi` call. DO NOT batch when the next step depends on the previous output, when an entry is heavy/long or can hang, or when the operator asked to see each step individually - a failure must stay isolated and visible. Small steps are GOOD for reliability; the only waste is running them one request at a time. " +"CONTEXT ECONOMY (1M-token window): a tool output up to ~60000 chars (~15k tok) fits IN FULL - prefer ONE big read over many small ones, because every extra step re-sends the whole history. Only above ~60000 chars is the middle cut, and the complete text is always saved under ./logs/*.log (read it by offset instead of re-running the step). Use the `read` tool (path/offset/limit/budget) for a FILE: default budget 6000, raise it (e.g. 20000) for a whole medium file in one call, and the footer gives the EXACT next offset. For an unknown file: first `read` with grep=regex for the map, then offset/limit on the section you need. ""MEMORY RULE: the MEMORY block below is READ-ONLY for you - never write, append, modify or delete it on your own initiative, only when the operator explicitly asks. Use it to work faster, but only its owner updates it. " +
  "IT IS A SNAPSHOT: loaded ONCE at session start; the file on disk may be longer (operator /learn). Lessons taught after this start are NOT here - memory silence about X does not mean X was never learned. " +
  "IT IS TELEGRAPHIC: one lesson per line - `TRAP: what failed -> exact error -> cause -> fix`, `OK: what verifiably works`, `DEAD: what does not work -> proof`, `P: absolute path -> artifact / how to run`, `RULE (ordinea cailor): 1 -> 2 -> 3` = ordered decision rule (cheapest path first), sections `## date - topic`. Read it as dense facts, not prose; missing words are not missing meaning. " +
  "FINAL MESSAGE: rich Markdown in a 256-colour terminal (headings, bold, lists, code blocks, --- rules). Write it in Romanian, complete and well structured; no tables (this is a phone screen), no repetition of steps already shown in the UI. "}]
CTX=os.path.join(WORK,CTXNAME)   # the history lives in the working folder (temp), permanently
LEGACY=os.path.join(os.path.dirname(os.path.abspath(__file__)),"context.json")  # the old location (next to the script)
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
    si,so=SESS["in"],SESS["out"]
    cum="   \u25aa session tok \u2191%s \u2193%s = %s"%(_K(si),_K(so),_K(si+so))
    if si: cum+=" \u00b7 hit %d%%"%int(100.0*SESS["cache_hit"]/si)
    cum+=" \u00b7 %d rds"%SESS["rounds"]
    print(G+cum+N)
    print("\n")   # 2 blank lines: separate the token block from the next "TU >" prompt (every caller of this returns to input())
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
    """Glues TOOLGUIDE + the memory into the system message. Called ONCE, at startup:
    from then on the system prefix stays IDENTICAL for the whole session (maximum prompt cache),
    and what /learn learns enters the context only at the next startup.
    TOOLGUIDE lives HERE (not inline in the prompt) so it is written once and cached."""
    mm=mem()
    tail="\n\n--- MEMORY ---\n"+mm if mm else ""
    for m in M:
        if m["role"]=="system":
            m["content"]=m["content"].split("\n\n--- TOOL GUIDE ---")[0].split("\n\n--- MEMORY ---")[0]+"\n\n--- TOOL GUIDE ---\n"+TOOLGUIDE+tail
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
          "thinking":{"type":os.environ.get("DS_VISION_THINKING","enabled")}}
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
    o.seek(0); return (o.read().decode("utf-8","replace") or "(no output)")

# ==================== TOOL ROUTER: alege AUTOMAT python vs bash ====================
# Euristici bazate pe masuratori reale (teste 1-3): bash castiga pe fluxuri/volum/paralelism,
# python castiga pe parsare structurata + logica. Routerul decide inainte de a executa.
PY_STRUCT = (r"\bjson\b", r"\bimport\s+json", r"json\.loads", r"json\.load\b", r"\.ini\b",
             r"configparser", r"def\s+\w+\(", r"class\s+\w+", r"\bCounter\b", r"collections",
             r"re\.(findall|search|match|sub)", r"dict\(|defaultdict", r"\.get\(", r"\blambda\b",
             r"os\.walk", r"glob\.", r"shutil\.", r"struct\.", r"\bdataclass\b", r"yield\b",
             r"\btry:", r"\bexcept\b", r"\.items\(\)", r"\.keys\(\)", r"\.values\(\)")
# NOTE: on GNU coreutils (this repo's usual host) sort/awk/sed are FAST, so they stay in BASH_STREAM.
# On the Android toybox build they are 3-95x SLOWER than python - there the agent's own guide tells the
# model to route them to python instead. Keep this list as the GNU-target default.
BASH_STREAM = (r"\bgrep\b", r"\bawk\b", r"\bsed\b", r"\bsort\b", r"\buniq\b", r"\bwc\b",
               r"\bcut\b", r"\btail\b", r"\bhead\b", r"\bxargs\b", r"\bfind\b", r"\bdu\b",
               r"\bdf\b", r"\brsync\b", r"\bzgrep\b", r"\btr\b", r"\bpaste\b", r"\bcomm\b",
               r"\bjoin\b", r"\bflock\b", r"\bcomm\b", r"\bparallel\b", r"-P\s*\d", r"\|\s*\w+")
# BASH_SLOW: tools that look like stream tools but are pathologically slow on a TOYBOX target; the
# router overflows them to python ONLY when the command is clearly running against toybox semantics.
BASH_SLOW = (r"\bawk\b", r"\bsed\b", r"\bsort\b", r"\buniq\b", r"\bbase64\b", r"\bjoin\b")
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
        return "python", f"structured logic detected ({py_hits} python-structure signals): parsing/logic is where python wins"
    # 2) comanda shell de tip stream -> bash
    sh_hits = sum(1 for pat in BASH_STREAM if re.search(pat, c or k))
    heavy = any(re.search(pat, t) for pat in BASH_HEAVY)
    if c and sh_hits >= 1:
        why = f"shell pipeline detected ({sh_hits} stream signals)"
        if heavy: why += "; large/streamed data -> bash (native C, less memory)"
        return "bash", why
    # 3) many small files in parallel -> bash (xargs -P uses every core)
    if c and re.search(r"xargs", c) and re.search(r"-P\s*\d", c):
        return "bash", "many small files in parallel -> bash xargs -P (all cores)"
    # 4) cod python pur dar cu semnale de stream (subprocess grep/awk in el) -> las python
    if py_hits == 1:
        return "python", "mostly python-shaped task (single structure signal)"
    # 5) implicit: python (logic-safe)
    return "python", "default: python (safe for logic; explicit `bash` for pure streams)"

def bash(cmd, cwd):
    """Ruleaza o comanda shell (bash -lc) in propriul grup de procese; Ctrl+C omoara doar acest
    tool. Intoarce stdout+stderr combinat, trunchiat la 8000 de caractere (ca la python)."""
    o=tempfile.TemporaryFile(dir=WORK)
    p=subprocess.Popen(["bash","-lc",cmd],cwd=cwd,stdout=o,stderr=subprocess.STDOUT,start_new_session=True)
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

def _looks_like_error(o):
    """Cheap heuristic: does this tool output contain a FAILURE (traceback, a Python
    Error/Exception, a shell failure, a denied/missing path)? Sets TASK['err'] so the
    footer can show that a step failed. False positives are harmless."""
    if not o: return False
    lo = o.lower()
    if "traceback (most recent call last)" in lo: return True
    if re.search(r"\b\w*(error|exception)\b", lo): return True
    if re.search(r"\b(failed|failure|denied|refused|unreachable|timeout|timed out|"
                 r"non-zero exit status|exit status [1-9]|command not found|not found|"
                 r"no such file|inaccessible|permission denied|operation not permitted|"
                 r"errno|eacces|enoent|enospc|read-only file system|segmentation fault|"
                 r"cannot (access|open|create|execute|stat)|unable to)\b", lo):
        return True
    return False

def tool_read(a):
    """Reads a file by line range with a GUARANTEED character budget, so nothing is ever cut in the
    middle. Prints at most `budget` chars (default 6000, ceiling = CHUNK, i.e. 60000 under the 1M-token
    window) and then a footer with the EXACT line to continue from. With `grep` it returns only the
    matching lines (with line numbers) so a big file is searched once and read only around the hits."""
    path=a.get("path","") or ""
    off=max(1,int(a.get("offset") or 1)); lim=a.get("limit") or 0
    bud=int(a.get("budget") or 6000); bud=max(500,min(bud,CHUNK))   # ceiling = tool budget (1M window)dow limit
    num=bool(a.get("numbered",True)); g=a.get("grep") or ""
    try: raw=open(path,encoding="utf-8",errors="replace").read()
    except Exception as e: return "[read] "+e.__class__.__name__+": "+str(e)
    lines=raw.split("\n"); total=len(lines)
    if g:
        try: rx=re.compile(g)
        except re.error as e: return "[read] bad regex: "+str(e)
        sel=[(i+1,lines[i]) for i in range(total) if rx.search(lines[i])]
        head="[read] "+path+" | grep "+repr(g)+" -> "+str(len(sel))+" hits in "+str(total)+" lines"
        out=[head]; used=len(head)
        for n,l in sel:
            row=str(n).rjust(5)+"| "+l
            if used+len(row)+1>bud: out.append("  ... more hits; narrow the regex or use offset"); break
            out.append(row); used+=len(row)+1
        return "\n".join(out)
    if off>total: return "[read] "+path+" has only "+str(total)+" lines (offset "+str(off)+" is past the end)"
    out=[]; used=0; i=off-1; last=off-1
    while i<total:
        if lim and (i-(off-1))>=lim: break
        row=(str(i+1).rjust(5)+"| "+lines[i]) if num else lines[i]
        # +1 for the newline that joins it
        if used+len(row)+1>bud: break
        out.append(row); used+=len(row)+1; last=i; i+=1
    nxt=last+2                     # 1-based line AFTER the last one printed
    foot="[read] "+path+" | lines "+str(off)+"-"+str(last+1)+" of "+str(total)+" | "+str(used)+"/"+str(bud)+" chars"
    if nxt<=total: foot+=" | NEXT: offset="+str(nxt)+(" limit="+str(lim) if lim else "")
    else: foot+=" | END OF FILE"
    return foot+"\n"+"\n".join(out)

def tool_multi(a):
    """BATCH runner: several SMALL independent operations in ONE tool call, ONE consolidated answer.
    Why it exists: every request re-sends the whole context, so 6 little steps cost 6x the context;
    run as one call they cost once. Design rules that keep it SAFE:
      - each entry is independent (no entry can depend on a previous one's output),
      - each entry is small and short-lived (a listing, a short cat, a status),
      - one entry failing NEVER aborts the others (its error is shown in place),
      - the total output is budgeted, so the answer cannot grow past the window limit."""
    ops = a.get("ops") or []
    if not isinstance(ops, list) or not ops: return "[multi] give a list of 1-6 ops"
    ops = ops[:6]                                   # hard cap: 6 entries max
    out = ["[multi] " + str(len(ops)) + " operations, ONE call (cost: 1 request instead of " + str(len(ops)) + ")"]
    for n, op in enumerate(ops, 1):
        kind = (op.get("kind") or "bash").strip()
        body = str(op.get("body") or "")
        nm = (op.get("name") or "").strip() or (kind + " " + str(n))
        head = "--- [" + str(n) + "] " + nm + " (" + kind + ") ---"
        if not body.strip():
            out.append(head + "\n(empty body - skipped)"); continue
        try:
            if kind == "python":
                r = py(body, os.getcwd())
            else:
                r = bash(body, os.getcwd())
            r = (r or "").rstrip()
        except Exception as e:
            r = "!! FAILED (isolated, the others still ran): " + e.__class__.__name__ + ": " + str(e)
        # per-entry cap so one huge entry cannot blow the whole answer (scaled to the 1M window)
        _cap = max(2000, _budget() // max(1, len(ops)))
        if len(r) > _cap:
            _keep = _cap - 600
            r = r[:_keep] + "\n[... " + str(len(r)-_keep-400) + " chars omitted - read it with the `read` tool if you need it ...]\n" + r[-400:]
        out.append(head + "\n" + (r if r else "(no output)"))
    res = "\n".join(out)
    if len(res) > _budget():
        res = res[:_budget()-400] + "\n[... total capped; run fewer/smaller ops ...]"
    return res

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
    if fn=="multi":
        o=tool_multi(a)
        TN[0]+=1; TASK.update(steps=TASK["steps"]+1,chars=TASK["chars"]+len(o))
        _show_step("multi "+str(len(a.get("ops") or []))+" ops",o,TASK["steps"])
        return o
    if fn=="read":
        o=tool_read(a)
        TN[0]+=1; TASK.update(steps=TASK["steps"]+1,chars=TASK["chars"]+len(o))
        _show_step("read "+a.get("path","")+("  grep="+a.get("grep","") if a.get("grep") else "  @"+str(a.get("offset") or 1)),o,TASK["steps"])
        return o
    return run_tool(a.get("code",""))
def ask(messages=None, tools=None, _timeout=600):
    _msgs = M if messages is None else messages
    _tools = T if tools is None else tools
    body={"model":os.environ.get("DS_MODEL","deepseek-flash"),"messages":_msgs,"tools":_tools,
          "max_tokens":int(os.environ.get("DS_MAXTOK","131072")),
          "thinking":{"type":os.environ.get("DS_THINKING","disabled")}}
    r=urllib.request.Request("https://api.deepseek.com/chat/completions",data=json.dumps(body).encode(),headers={"Authorization":"Bearer "+K,"Content-Type":"application/json"})
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
      "FORMAT - one lesson = ONE line, <=150 chars, telegraphic, no sentences:\n"
      "  `TRAP: what I did -> exact error -> cause -> fix that worked` (exact command/flag/path/error string - this is the MOST valuable line type)\n"
      "  `OK: command/path/flag that verifiably works`   `DEAD: what does NOT work -> proof`   `P: absolute path -> artifact / how to run it`\n"
      "  `PREVENT: rule to apply next time so <trap> never happens again` (only when it is a real, reusable rule)\n"
      "  `RULE (ordinea cailor): ...` - ordered decision rule (1 -> 2 -> 3), pick the CHEAPEST/FASTEST path FIRST; only for a real, reusable decision order\n"
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
        print(R+"   [mem] LINT: "+str(len(_lint))+" line-level issue(s):"+N)
        for _w in _lint[:6]:
            _msg = ("line "+str(_w[0])+" chars (>150): "+_w[1][:90]) if _w[0] else _w[1]
            print(R+"        ! "+_msg+N)
        if len(_lint)>6: print(R+"        ... +"+str(len(_lint)-6)+" more"+N)
    elif _nless:
        print(G+"   [mem] lint OK: "+str(len(_nless))+" lesson line(s), all <=150 chars, no forbidden content."+N)
    save_ctx()
    if m and m.get("content"): print("\n"+C+"AGENT >"+N+"\n"+render(m["content"].strip()))
    print(G+"   [/learn] the new memory loads into the system prompt at the NEXT startup."+N)
    print(_task_foot("/learn")); flush_task_tokens(); return


# ======== ANTI-POISON v1 (patch 2026-09-24) ========
# Context: pe 23 sept 2026 invatarea automata (de atunci eliminata) a scris 4 lectii
# FALSE din 10, pentru ca a rulat DUPA FIECARE task si a salvat IPOTEZE INTERMEDIARE ca
# si concluzii. Memoria a ajuns sa se AUTO-CONTRAZICA ("dispatchGesture both fail" langa
# "dispatchGesture works"). Portile raman valabile si pentru /learn manual.
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
    # --- ACCESSIBILITY/Linux (pastrate) ---
    (r"\b(suspect|probably|se pare|maybe|likely|poate fi)\b.*\b(threading|Looper|issue|cause|cauza)\b",
     r"\b(NU threading|nu e threading|platform-side|PendingIntent cancellation)\b"),
    (r"\b(read-only|NU acorda permisiunea de actiune|missing capability|capabilities lack)\b",
     r"\b(NOT a capability problem|not read-only|NU (e|este) capabilit|nu modifica configul)\b"),
    (r"\b(read-only|nu acorda permisiunea)\b",
     r"\b(TAP MERGE|dispatchGesture.*MERGE|actioneaza|reactiveaza|se leaga serviciul|NU e read-only)\b"),
    (r"\bfix: add android:canTakeScreenshot\b",
     r"\bXML.*(compilat corect|e corect)\b"),
    # --- WEB / HTTP ---
    (r"\b(merge|functioneaza|intoarce 200|raspunde|e disponibil|accesibil|se parseaza|e parsabil)\b",
     r"\b(nu merge|nu functioneaza|nu raspunde|esueaza|eroare|blocat|interzis|403|404|500|timeout|nu se poate parsa)\b"),
    (r"\b(da 200|intoarce 200|raspunde cu 200)\b",
     r"\b(da 4\d\d|da 5\d\d|404|403|500|eroare)\b"),
    # --- AUTH ---
    (r"\b(necesita|are nevoie de|cere)\b.{0,25}\b(api.?key|token|auth|autentificare)\b",
     r"\b(fara (api.?key|token|auth)|anonim|merge anonim|nu necesita cheie)\b"),
    # --- SCRAPING JS ---
    (r"\b(html static|merge fara js|fara javascript)\b",
     r"\b(necesita js|e un spa|javascript|html gol|content gol)\b"),
    # --- EXISTENTA ---
    (r"\b(exista|e valabil|e activ)\b",
     r"\b(nu exista|inexistent|a fost retras|retired|e sters)\b"),
    # --- PRET ---
    (r"\b(ieftin|cost redus|low cost)\b",
     r"\b(scump|cost ridicat|expensive)\b"),
    # --- PERFORMANTA ---
    (r"\b(mai bun|depaseste|bate |outperforms|cel mai bun|superior)\b",
     r"\b(mai slab|in urma|pierde|inferior|nu atinge)\b"),
    # --- SUPORT ---
    (r"\b(suporta|are suport|accepta)\b",
     r"\b(nu suporta|nu accepta|nu permite|incompatibil|unsupported)\b"),
    # --- VITEZA ---
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
META_RX = [r"\bauto-learn\b", r"\b/learn\b", r"\bmemory\.md\b", r"\bmemoria\b", r"\bmemorie\b",
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
        # GUARD anti-conditional: complementar DOAR cand conditionalul e in AMBELE linii
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


HOME_DIR = os.path.dirname(os.path.abspath(__file__))

if __name__ == "__main__":
    if WATCH.get("on"):
        _watch_start()
    refresh()   # the memory enters the system prompt ONCE, here; from now on the prefix never changes again
    ctx_check_window()   # cheap API call: corrects CTXWINDOW if the local constant is wrong
    print(U+" ⚡ AGENT DeepSeek "+N+G+"| tools: python, bash, smart, look | "+os.getcwd()+N)
    print(G+"   "+HINT_LINE+"  ·  commands like /learn, /ctx, /compact, /verbose, /watch, /reset, /exit"+N+"\n")
    while 1:
        try: q=input(U+" TU > "+IN).strip()
        except (EOFError,KeyboardInterrupt): print(N);break
        if q in ("/exit","/quit",""): break
        if q in ("/help","/?"):
            print(G+"   COMMANDS"+N)
            print(G+"     /learn              update memory now (manual learning)"+N)
            print(G+"     /mem                show memory stats (size, bullets, density, lint)"+N)
            print(G+"     /ctx                context window + archives/logs on disk"+N)
            print(G+"     /compact            (disabled) context is never compressed - memory stays intact until /reset"+N)
            print(G+"     /verbose            toggle full code/output of each step"+N)
            print(G+"     /watch [sec]        status la fiecare N secunde (0 tokeni, doar cat ruleaza un job)"+N)
            print(G+"     /reset              erase the conversation history"+N)
            print(G+"     /help, /?           this list"+N)
            print(G+"     /exit, /quit        leave (empty line too)"+N)
            print(G+"   "+(HINT_LINE)+N)
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
            print(G+"   [compact] DISABLED by the operator: the context is never compressed (not automatically, "
                  "not on request), so the memory inserted at startup stays intact until you give /reset. "
                  "Nothing was changed."+N); continue
        if q.startswith("/watch"):
            _a = q.split()
            if len(_a) > 1 and _a[1].isdigit(): WATCH["sec"] = max(10, int(_a[1]))
            WATCH["on"] = not WATCH["on"]
            if WATCH["on"]:
                _watch_start()
                print(G+"   [watch] ON - status la fiecare "+str(WATCH["sec"])+"s, DOAR cat ruleaza ceva."+N)
                print(G+"   [watch] cost: 0 tokeni (scrie pe ECRAN, nu intra in contextul modelului)."+N)
            else:
                print(G+"   [watch] OFF."+N)
            continue
        if q=="/verbose":
            VERBOSE[0]=not VERBOSE[0]; print(G+"   [ui] "+("VERBOSE: printing the code and the output of every step" if VERBOSE[0] else "COMPACT: live line with what it does now + timer over the WHOLE task (thinking vs. tool) and one line \u25cf <nr> \u00b7 <what the step does> \u00b7 time \u00b7 chars for every finished step")+N); continue
        if q=="/mem":
            _c,_t,_nb,_den=mstats(mem()); _dens="density OK (tight)" if (_nb and _den<=180) else ("DENSITY WARNING ("+str(_den)+" chars/bullet > 220)" if (_nb and _den>220) else "n/a"); print(G+"   memory: "+MEM+" | "+str(_c)+" chars ~ "+str(_t)+" tok | "+str(_nb)+" bullets | "+str(_den)+" chars/bullet | unlimited size | "+_dens+N); continue
        if q=="/reset":
            M[:]=M[:1]; save_ctx()
            print(G+"   [reset] the conversation history was erased ("+os.path.basename(CTX)+")"+N); continue
        if q.startswith("/auto-learn") or q.startswith("/autolearn"):
            print(OF+"   [auto-learn] ELIMINAT - agentul nu mai invata singur dupa task."+N)
            print(G+"   [auto-learn] memoria se actualizeaza DOAR manual, cu /learn."+N); continue
        if q=="/learn":
            do_learn("/learn"); continue
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
                    o=call_tool(c)          # compact: only the summary; the CUT output is what gets sent to the model
                    M.append({"role":"tool","tool_call_id":c["id"],"content":o});compact_history();save_ctx();ctx_warn()
            else:
                print("\n"+C+"AGENT >"+N+"\n"+render((m.get("content") or "").strip())+"\n")
                print(_task_foot())
                flush_task_tokens()
                break
        except KeyboardInterrupt:
            LIVE.update(phase="idle",desc="",col=None,n=0)   # kill the live line first: no "step 00" left stuck on screen
            print("\r\33[K",end="",flush=True)
            print(G+"   [Ctrl+C] stopped ONLY the current step. The tools run so far stay in the context (the agent knows where it stopped). /reset to make it forget the whole task."+N)
            while len(M)>mark and M[-1].get("role")=="assistant" and not M[-1].get("tool_calls"): M.pop()
            complete_pending(M);save_ctx(); print(_task_foot("interrupted by the operator")); flush_task_tokens(); continue
    save_ctx()   # on /exit or Ctrl+D the history is already on disk