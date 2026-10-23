---
name: android-api-tool-integration
description: Cum se adauga un tool nou in agent.py astfel incat sa functioneze REAL (nu doar sa existe), cu toate cele 4 puncte de integrare si capcanele de sintaxa
---

# Integrarea unui tool nou in agent.py

## REGULA: un tool are NEVOIE de 4 puncte de integrare

Un tool care exista doar in unele locuri ruleaza in unele contexte si nu in altele.
Simptomul clasic: `run_code` il vede, dar apelul direct al modelului intoarce GOL.

1. **lista `T`** — descrierea pentru model (`{"type":"function",...}`)
   fara ea, modelul nu stie ca tool-ul exista
2. **`_call_tool_inner`** — dispatcher-ul REAL, lanțul `if fn=="nume": return ...`
   ★ ACESTA e cel care conteaza pentru apelurile modelului
3. **`sandbox`** (in `run_code_ptc`) — pentru `run_code`
   `"nume": _wrap("nume", lambda a: ...)`
4. **`TOOLGUIDE`** — instructiunea text care spune modelului CAND sa-l foloseasca

## TRAP: agentul are DOUA dispatchere

- `_call_tool_inner(c)` — apelurile reale ale modelului (linia ~2741)
- `sandbox={...}` in run_code_ptc (~3545) — doar pentru run_code

Daca adaugi doar in `sandbox`, tool-ul merge in scripturi dar NU la apel direct.
Verificare: `grep -n 'if fn=="NUME"' agent.py`

## TRAP: TOOLGUIDE e un TUPLU de stringuri

```python
TOOLGUIDE=("linia1 "
  "linia2 "
  "ultima linie")     # <- se inchide cu ) NU cu ,)
```
Daca adaugi o linie si lasi `,)` la final => `TypeError: can only concatenate tuple`
Fix: ultima linie se termina cu `",` si tuplul se inchide pe ULTIMA linie cu `")`.
Mai sigur: inlocuieste textul ULTIMEI linii printr-un `replace()` cu textul vechi + nou, nu edita pe linii.

## TRAP: editatul pe linii rupe parantezele

Editarea `lines[i] = ...` pe un fisier de 6000+ linii a produs de 3 ori
`SyntaxError: '(' was never closed`. Foloseste `str.replace(OLD_EXACT, NEW)` pe text,
unde OLD_EXACT e copiat verbatim din fisier.

## PROCEDURA verificata

```python
# 1. backup + sintaxa inainte
shutil.copy(p, p+".bak."+timestamp); py_compile.compile(p,doraise=True)

# 2. adauga functia (str.replace pe un anchor unic)
t = t.replace("def run_adbsh_tool(", FUNCTII_NOI + "def run_adbsh_tool(", 1)

# 3. cele 4 puncte, fiecare cu assert ca anchorul exista
assert old in t; t = t.replace(old, new, 1)

# 4. sintaxa DUPA fiecare pas
py_compile.compile(p,doraise=True)

# 5. verificare ca toate punctele sunt prezente
for k,v in checks.items(): print(("OK " if v else "LIPSA"), k)
```

## VERIFICARE FINALA (nu doar sintaxa)

Sintaxa valida NU inseamna ca tool-ul merge. Testeaza:

```python
spec=importlib.util.spec_from_file_location("agentmod",p)
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

# a) tool-ul e in lista
assert "NUME" in [x["function"]["name"] for x in m.T]
# b) apelul REAL prin dispatcher (nu prin sandbox)
o = m._call_tool_inner({"function":{"name":"NUME","arguments":json.dumps({...})}})
# c) call_tool() direct poate lansa subprocese (insight_tool) -> poate atarna/intrerupe
#    foloseste _call_tool_inner pentru test izolat
```

## TRAP: procesul vechi tine codul vechi in memorie

Dupa modificarea `agent.py`, procesul agentului ruleaza in continuare versiunea
incarcata la pornire. `py_compile` trece, modulul se incarca corect din fisier,
dar tool-ul apelat de model da GOL pana la RESTART.
Nu depana codul: cere restart si retesteaza.

## P: fisierele

- `/data/data/net.sys32.agent/files/python/agent.py` — agentul care ruleaza
- `workspace/app/net.sys32.agent/app/src/main/assets/python/agent.py` — sursa din repo
  (aceasta intra in APK la rebuild; cele doua trebuie SA FIE IDENTICE)
