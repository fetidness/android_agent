---
name: android-agent-tool-integration
description: "Cum adaugi un tool NOU in agent.py (files/python) ca sa functioneze real, nu doar sa apara in prompt - toate punctele de inregistrare, inclusiv dispatcher-ul care conteaza."
---
# Adaugarea unui tool nou in agent.py

## When to Use
- Vrei sa expui o functionalitate noua ca tool al agentului (ex. `androidapi`).
- Ai adaugat un tool si "apare in lista" dar apelul intoarce GOL / nu se intampla nimic.
- Trebuie sa verifici ca o modificare in agent.py chiar ajunge in build-ul de APK.

## Method
1. BACKUP + garda de sintaxa inainte de orice editare:
```python
import shutil, time, py_compile
p = "/data/data/net.sys32.agent/files/python/agent.py"
shutil.copy(p, p + ".bak." + time.strftime("%Y%m%d_%H%M%S"))
py_compile.compile(p, doraise=True)
```

2. Scrie functia + un wrapper care respecta contractul de afisare:
   wrapper-ul trebuie sa apeleze `_show_step(...)` si sa actualizeze
   `TN[0] += 1` si `TASK.update(steps=..., chars=...)`, apoi sa RETURNEZE stringul.

3. Inregistreaza in TOATE punctele (agent.py are DOUA dispatchere, nu unul):
   - lista `T` (`{"type":"function","function":{"name":...}}`) = ce vede modelul
   - `TOOLGUIDE` (textul din system prompt: cand sa-l prefere)
   - ramura in `_call_tool_inner(c)` = `if fn=="<tool>": return ...`  <-- CEL CARE CONTEAZA
   - `sandbox={...}` din `run_code` (`"<tool>": _wrap("<tool>", lambda a: ...)`)

4. Verifica sintaxa dupa FIECARE pas:
```python
py_compile.compile(p, doraise=True)
```

5. Test real prin dispatcher-ul adevarat (nu prin modul):
```python
import importlib.util, json, io, contextlib
spec = importlib.util.spec_from_file_location("agentmod", p)
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
c = {"function": {"name": "<tool>", "arguments": json.dumps({"action": "battery"})}}
o = m._call_tool_inner(c)          # NU m.call_tool(c) - acela lanseaza subprocese
```

6. Restart aplicatie, apoi confirma cu tool-ul real ca raspunde cu date.

## Pitfalls
- TRAP: tool-ul apare in lista `T` si in `TOOLGUIDE` dar apelul intoarce GOL -> lipseste ramura din `_call_tool_inner(c)`; `sandbox` din `run_code` NU e folosit de apelurile reale ale modelului -> adauga `if fn=="<tool>":` in `_call_tool_inner`.
- TRAP: modifici agent.py si testul tau trece, dar tool-ul real tot nu merge -> procesul agentului are versiunea veche in memorie -> restart aplicatie; restartul facut INAINTE de ultima linie adaugata nu ajuta.
- TRAP: `m.call_tool(c)` in test da `KeyboardInterrupt` din `insight_tool`/subproces -> testeaza cu `_call_tool_inner(c)`.
- TRAP: editezi TOOLGUIDE pe linii si inchizi gresit tuplul -> `TypeError: can only concatenate tuple (not "str") to tuple` si `SyntaxError: '(' was never closed` -> nu edita pe linii; inlocuieste EXACT ultimul string al tuplului (`...")`) cu `... "\n "linie noua")` printr-un `t.replace(OLD, NEW, 1)`.
- TRAP: o singura eroare de sintaxa face importul sa cada si TOATE tool-urile dispar -> ruleaza `py_compile` dupa fiecare pas, nu la final.
- OK: textul de adaugat in lista `T` se insereaza cel mai sigur prin ancorarea pe intrarea existenta a unui tool vecin (`{"name":"toolchain"`).
