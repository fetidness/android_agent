## 2026-09-24 - android build+install (session: /home/gab/Desktop/android_agent/temp)
P: /home/gab/Desktop/android_agent/workspace/app -> ./build_app.sh (build+install+start); build solo: net.sys32.agent/./gradlew assembleDebug
TRAP: checkout laptop incomplet pt build -> lipsesc gradlew+gradle-wrapper.jar, jniLibs/*.so, assets/python/Lib/* (toate in .gitignore) -> regenerez wrapper: /home/gab/android/gradle-8.11.1/bin/gradle wrapper --gradle-version 8.11.1 ; .so+Lib+libdynload le extrag DE PE DEVICE
OK: adb pull <codePath>/lib/arm64/. <proj>/app/src/main/jniLibs/arm64-v8a -> 6 .so (libpyexec/libpython3.14/libcrypto_python/libssl_python/libsqlite3_python)
OK: assets de pe device: adb shell "run-as net.sys32.agent sh -c 'cd /data/data/net.sys32.agent/files/python && tar cf - Lib libdynload'" > tar; untar in assets/python (Lib=17M, libdynload arm64+x86_64=42M)
TRAP: assets locale mai vechi decat device -> agent.py 178678B vs 189931B pe device -> sync din files/python DUPA extragere, altfel APK livreaza cod vechi
PREVENT: la orice rebuild incremental, compara size fiecarui .py assets vs device (files/python/) si incrementeaza .assets_vNN in MainActivity.kt (era v97->v99)
TRAP: editezi assets dar app-ul nu le re-extrage -> marker .assets_vNN+1 OBLIGATORIU; verificare: adb shell run-as net.sys32.agent ls -la /data/data/net.sys32.agent/files/ | grep assets_v (dotfiles: NEcesita -a)
TRAP: pm uninstall NU sterge /sdcard/Download/Agent (adbkey persistent) nici reziduurile /data/local/tmp (agent_*.py, tpm/, wrap/, apkx/) -> le sterg explicit
TRAP: adb install -r dezactiveaza accessibility -> re-activare: settings put secure enabled_accessibility_services net.sys32.agent/net.sys32.agent.AgentAccessibilityService ; settings put secure accessibility_enabled 1 ; verificare dumpsys accessibility
OK: date cheie device (necesita adb aut) DE PE PC: adb shell run-as net.sys32.agent ... ; cel mai important: dumpsys package net.sys32.agent | grep -E 'codePath|firstInstallTime'
OK: cheie API NU e in APK (key.txt in .gitignore) -> se pune manual in files/python/key.txt (sau home/key.txt)

## 2026-09-24 - env adb+shell fragil (session: /home/gab/Desktop/android_agent/temp)
TRAP: adb pm uninstall/rm masiv pe /sdcard -> adbd se agata, "no output" pe ORICE adb shell/ps (bash -lc returneaza gol) -> solutie: ruleaza adb prin tool python (subprocess.run), nu prin bash; python merge chiar cand bash e blocat
PREVENT: pe acest mediu NU pune adb in variabila $ADB urmata de comenzi multiple in bash -lc -> executa doar calea absoluta /home/gab/android/platform-tools/adb, o comanda per apel
TRAP: tel autorizare adb revocata -> start-server trebuie; adb devices gol pana reaproba dialogul "Allow USB debugging"

## 2026-09-24 - agent python key.txt (session: /home/gab/Desktop/android_agent/temp)
TRAP: agent.py linia ~292 citea key.txt modul-level -> fara key.txt = crash instant la pornire -> fix: def _load_key() cu fallback env DEEPSEEK_API_KEY -> key.txt(dir script) -> HOME/key.txt, returneaza "" fara crash
OK: onboarding cheie in MainActivity.kt: startPythonIfKey() verifica readStoredKey() (python/key.txt, home/key.txt); lipsa -> awaitingKey=true, sendLine() o scrie in files/python/key.txt + home/key.txt, apoi startPythonProcess(key) paseaza env DEEPSEEK_API_KEY
OK: input EditText hint e ceea ce trebuie setat pentru prompt ("paste DeepSeek key (sk-...) and send"); ecran 1080x2340@450, buton trimitere center=(989,2211)

## 2026-09-24 - auto-learn eliminat complet + git push (session: /home/gab/Desktop/android_agent/temp)
OK: auto-learn scos din AMBELE fisiere (agent-original.py Linux + agent.py Android): auto_learn_check, AUTOLEARN, AUTO_LEARN_PROMPT, tracing al_log/al_rotate/al_compact_msgs, comanda /auto-learn -> ramane DOAR /learn manual (do_learn)
OK: /auto-learn raspunde acum explicit "ELIMINAT - memoria se actualizeaza DOAR manual, cu /learn"
TRAP: git push esueaza cu "Permission denied (publickey)" cu cheia default -> foloseste GIT_SSH_COMMAND="ssh -i ~/.ssh/id_ed25519_github_new -o IdentitiesOnly=yes" git push origin master (cheia id_ed25519_android_agent e RESPINSA de GitHub)
TRAP: memory.md pe disc avea doar liniile noi (22), dar in git 1144 linii de istoric -> git add -A ar fi STERS istoricul; verifica intotdeauna git show HEAD:memory.md inainte de commit
