# BINDER IN-PROCESS (din aplicatie) — 2026-10-21

Agentul din aplicatie are acum acces Binder **nativ**, la fel ca Debian-ul,
dar **fara adb, fara bridge, fara proot**: deschide `/dev/binder` direct in
procesul aplicatiei.

===============================================================================
## CE FUNCTIONEAZA (verificat in aplicatie, u:r:untrusted_app)
===============================================================================
```
list            -> 468 servicii
check package   -> found
check nu_exista -> not found
iface display   -> android.hardware.display.IDisplayManager
handle power    -> handle=2
call display 1  -> status=0, 1736 bytes (date reale: QCM, DisplayAddress...)
call input 1    -> status=0, 8 bytes
call power 5    -> status=-1 (raspuns real de la serviciu)
```

Deci: `untrusted_app` POATE vorbi cu servicemanager si POATE apela servicii.

===============================================================================
## TOOL NOU: `binder`
===============================================================================
```json
{"action":"list"}
{"action":"check","params":{"name":"package"}}
{"action":"handle","params":{"name":"display"}}
{"action":"iface","params":{"name":"display"}}
{"action":"call","params":{"name":"display","code":1}}
{"action":"call","params":{"name":"power","code":5,"args":[]}}
{"action":"raw","params":{"name":"display","code":1,"descriptor":""}}
```

In `run_code` e disponibil ca `binder({...})`.

===============================================================================
## MODUL: android_binder.py
===============================================================================
```python
import sys; sys.path.insert(0,"/data/data/net.sys32.agent/files/python")
from android_binder import Binder, strings
b = Binder()                       # deschide /dev/binder (o singura data)
b.list()                           # 468 servicii
b.handle("display")                # handle local
b.iface("display")                 # descriptor AIDL
st, data = b.call("display", 1)    # apel AIDL real
strings(data)                      # extrage stringurile UTF-16
```

===============================================================================
## DE CE MERGE DIN untrusted_app
===============================================================================
- `/dev/binder` se deschide (SELinux permite binder_device pentru untrusted_app)
- `mmap` pana la **1 MB** cu PROT_READ (nu doar 4096)
- servicemanager (pid 1000) raspunde la getService/checkService/listServices
- apelurile pe servicii functioneaza daca descriptorul e corect

Diferenta fata de Debian: acolo trebuia `setuid(2000)` ca sa treaca SELinux.
Aici aplicatia are deja contextul ei si merge direct.

===============================================================================
## CAPCANE (dovedite)
===============================================================================
TRAP: errno=11 (EAGAIN) la BINDER_WRITE_READ NU e eroare - inseamna "nimic de
      citit inca". Trebuie tratat ca (0,0) si reincercat, altfel pica tot.
TRAP: buffer-urile trimise trebuie PASTRATE vii (lista _keep) pana la sfarsitul
      tranzactiei; daca sunt colectate de GC, kernelul citeste gunoi.
TRAP: `checkService` intoarce status=0 si pentru servicii INEXISTENTE.
      Diferenta: `offsets_size == 0` (niciun obiect binder) => nu exista.
TRAP: `getService` nu elibereaza bufferul; eliberarea se face in _prepare()
      DUPA ACQUIRE/INCREFS (ordinea libbinder).
TRAP: descriptorul AIDL e obligatoriu in parcel pentru apelurile AIDL,
      altfel "Binder invocation to an incorrect interface" (status -1).

Offseturile protocolului: vezi DEBIAN_BINDER.md (identice).

===============================================================================
## FISIERE
===============================================================================
P: /data/data/net.sys32.agent/files/python/android_binder.py   modulul (live)
P: /data/data/net.sys32.agent/files/python/agent.py            tool-ul integrat
P: /storage/emulated/0/Download/Agent/workspace/android_binder.py
P: workspace/app/.../assets/python/android_binder.py            (in repo)

===============================================================================
## LECTII DUROASE (2026-10-21, dupa testul in-productie)
===============================================================================

TRAP: NICIODATA sa nu inchizi fd-uri binder care nu iti apartin. Procesul
      aplicatiei are propriul binder (fd ~8, folosit de runtime-ul Android).
      Daca il inchizi, ORICE ioctl binder din proces da errno=13 (EACCES) si
      aplicatia ramane instabila PANA LA RESTART.
      Simptom: `binder error: send esuat (errno=13)` / `errno=9 (EBADF)`.
      Fix: restart aplicatie. In cod: un singur os.close, pe self.fd.

TRAP: NU pastra mai multi clienti Binder simultan in acelasi proces. Al doilea
      client (fd nou) primeste "reply prea mic" pentru ca primul are tranzactii
      in curs. Un singur client viu, refolosit (`_binder_client()` din agent.py).

TRAP: dupa un esec de comunicatie, clientul poate ramane cu buffere in coada.
      Tool-ul face UN reset (close + instanta noua) si reincearca o data.
      Daca tot esueaza, e semn de stare compromisa -> restart.

OK:  secventa dovedita in productie (10/10 apeluri consecutive):
       list(468) -> handle -> iface -> call, fara crestere de fd-uri.

OK:  apelul pe `power` code 5 intoarce mesajul REAL de permisiuni:
       "Neither user 10408 nor current process has
        android.permission.DEVICE_POWER."
     Deci binder-ul spune exact ce lipseste - foloseste-l ca diagnostic.
