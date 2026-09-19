# ACCES ANDROID COMPLET pentru agent - FINALIZAT

## FILOZOFIE: agentul gandeste, noi doar ii dam acces
NU liste predefinite de "ce poate face". In schimb:
- tool generic `android` cu REFLECTION -> acces la ORICE clasa/metoda/camp Android SDK
- tool-uri shortcut pentru cazurile uzuale (rapide, dar nu limitative)

## ARHITECTURA
AndroidBridge.kt (Kotlin, procesul app)
  - TCP pe 127.0.0.1:<port aleator> (scris in files/bridge.port + files/home/bridge.port)
  - protocol: o linie JSON cerere -> o linie JSON raspuns
  - Reflection.kt: evaluator generic (op: call/new/get/set/info/services/free/objs)
  - shortcut-uri: sensors camera location battery clipboard notify vibrate tts
                 volume wifi device apps intent settings tourl

android_bridge.py (Python, in agent)
  - gaseste portul (AGENT_BRIDGE_PORT_FILE, HOME, ANDROID_BRIDGE, cai absolute)
  - call(tool, action, **params) -> dict

agent.py
  - tool `android` in schema (5 tools: python bash smart look android)
  - run_android_tool() face dispatch
  - ANDROID_GUIDE in promptul de sistem: cum sa foloseasca reflection

## TARGETS in reflection
svc:NUME    serviciu de sistem (72 expuse: sensor camera location connectivity wifi audio
            clipboard notification power battery vibrator telephony usb bluetooth nfc display
            window input keyguard storage activity alarm job download biometric device_policy
            media_projection ...)
class:FQCN  orice clasa (android.*, java.*)
obj:ID      obiect pastrat (din op=new cu "keep":true sau "id":"x")
ctx / app   Application context
str:X int:N long:N double:N bool:true null

## OPERATII
{"op":"services"}                      -> toate serviciile + disponibilitate
{"op":"info","target":"class:X"}       -> metode + campuri (+ filter)
{"op":"call","target":"svc:sensor","method":"getSensorList","args":[-1]}
{"op":"call","target":"class:android.os.Build","static":true,"method":"getModel"}
{"op":"new","target":"class:android.media.MediaRecorder"}
{"op":"get","target":"class:android.os.Build","field":"MODEL"}
{"op":"set","target":"obj:o0","field":"x","value":1}
{"op":"free","id":"o0"} / {"op":"objs"}

## EXEMPLE CARE MERG (testate)
- getSensorList(-1)          -> 139 senzori cu detalii  (ATENTIE: TYPE_ALL = -1, nu 0)
- Build.MODEL (static)       -> "sdk_gphone64_x86_64"
- Runtime.getRuntime()       -> obiect Java
- Uri.parse("content://...") -> obiect
- svc:window getDefaultDisplay -> DisplayInfo complet
- svc:activity getRunningAppProcesses
- svc:power field mService   -> IPowerManager$Stub$Proxy

## LIMITA CUNOSCUTA (nu e bug)
Reflection NU poate crea obiecte care IMPLEMENTEAZA interfete Java la runtime
(ex: un SensorEventListener propriu). Deci pentru callback-uri (stream de senzori)
se folosesc shortcut-urile care au listeneri scrisi in Kotlin (sensors read).
Agentul poate totusi chema metode care PRIMESC listeneri deja existenti.

## BUILD
cd /home/gab/Desktop/agent/workspace/app/net.sys32.agent && ./gradlew assembleDebug
sau ./build_app.sh (din app/)

## LECTII
- json.dumps in agent -> params ajung in req["params"]; bridge citeste p.optJSONObject("expr")
- Context.X_SERVICE unele NU exista in SDK public -> folosim string-uri ("sensor","wifi"...)
- bridge.port trebuie scris si in HOME (files/home), nu doar in files/
- NU folosi open(p,"w").write(open(p).read()...) : trunchiaza fisierul la 0! (a distrus MainActivity.kt)
