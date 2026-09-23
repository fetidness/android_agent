package net.sys32.agent

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.Typeface as TF
import android.os.Build
import android.os.Bundle
import android.os.Environment
import android.text.InputType
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.view.WindowManager
import android.widget.Button
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import androidx.core.view.ViewCompat
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.updatePadding
import java.io.BufferedReader
import java.io.File
import java.io.InputStreamReader
import java.io.OutputStreamWriter

class MainActivity : AppCompatActivity() {

    private lateinit var output: TextView
    private lateinit var input: EditText
    private lateinit var scroll: ScrollView
    private lateinit var root: LinearLayout
    private lateinit var btnDown: Button
    private lateinit var btnStop: Button
    @Volatile private var generating = false
    private var bridge: AndroidBridge? = null
    private var pyProc: Process? = null
    private var pyIn: OutputStreamWriter? = null
    private val pending = StringBuilder()
    private var autoScroll = true
    private var permRequested = false   // anti-bucla: cerem o singura data automat din onResume
    @Volatile private var followTail = true
    private var programmaticScroll = false

    private val extraTop: Int get() = (16 * resources.displayMetrics.density).toInt()

    private val mono: Typeface by lazy {
        try { TF.createFromAsset(assets, "fonts/DejaVuSansMono.ttf") }
        catch (e: Exception) { Typeface.MONOSPACE }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        WindowCompat.setDecorFitsSystemWindows(window, false)

        // ===== BACKGROUND / LOCK SCREEN =====
        // Permite activitatii sa se afiseze PESTE lock screen si sa aprinda ecranul
        // cand agentul are nevoie de UI (task care atinge alte aplicatii).
        if (android.os.Build.VERSION.SDK_INT >= 27) {
            setShowWhenLocked(true)
            setTurnScreenOn(true)
        } else {
            @Suppress("DEPRECATION")
            window.addFlags(
                android.view.WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED or
                android.view.WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON
            )
        }
        // ecranul nu se stinge CAT TIMP agentul lucreaza (flag adaugat dinamic in setTaskScreenOn)

        window.statusBarColor = Color.parseColor("#0D1117")
        window.navigationBarColor = Color.parseColor("#0D1117")

        root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.parseColor("#0D1117"))
        }

        scroll = ScrollView(this).apply {
            isFillViewport = true
            setBackgroundColor(Color.parseColor("#0D1117"))
        }

        output = TextView(this).apply {
            setPadding(24, 16, 24, 24)
            textSize = 11f
            typeface = mono
            setTextColor(Color.parseColor("#ABB2BF"))
            setBackgroundColor(Color.parseColor("#0D1117"))
        }
        scroll.addView(output, ViewGroup.LayoutParams(-1, -2))
        root.addView(scroll, LinearLayout.LayoutParams(-1, 0, 1f))

        // ===== SCROLL =====
        // Nu mai tin niciun flag de "user a derulat". Sistemul e pur reactiv:
        // in appendAnsi verific DACA suntem acum la fund; daca da -> urmaresc generarea,
        // daca nu -> nu misc nimic. Astfel:
        //   - esti jos la fund        -> auto-scroll (urmareste generarea)
        //   - ai derulat sus          -> nu esti la fund -> rămâi unde esti
        //   - revii jos la fund       -> iar la fund -> auto-scroll reia singur
        scroll.setOnScrollChangeListener { _, _, scrollY, _, oldScrollY ->
            val child = scroll.getChildAt(0)
            val dist = if (child != null) child.bottom - scroll.height - scrollY else Int.MAX_VALUE
            // miscarea reala a userului (nu cea programatica): daca s-a urcat, nu mai urmarim;
            // daca s-a coborat pana EFECTIV la fund (<=2), reluam urmarirea.
            if (!programmaticScroll) {
                if (scrollY < oldScrollY) {
                    // userul a derulat SUS -> oprim urmarirea
                    followTail = false
                } else if (scrollY > oldScrollY && dist <= 24) {
                    // userul a derulat JOS si a ajuns (aproape) la fund -> reluam
                    followTail = true
                }
            }
            // daca userul a ajuns la fund (prin orice mijloc), urmarirea reia
            if (!programmaticScroll && dist <= 8) followTail = true
            btnDown.visibility = if (dist <= 24) View.GONE else View.VISIBLE
        }

        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setBackgroundColor(Color.parseColor("#11151C"))
            setPadding(16, 12, 12, 12)
        }
        input = EditText(this).apply {
            hint = "message the agent..."
            setHintTextColor(Color.parseColor("#5C6370"))
            setTextColor(Color.parseColor("#E6E6E6"))
            textSize = 13f
            typeface = mono
            setBackgroundColor(Color.TRANSPARENT)
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_MULTI_LINE
            maxLines = 6
            minLines = 1
            setSingleLine(false)
            // padding vertical generos: altfel ultima linie de text e taiata pe marginea de jos
            setPadding(dp(14), dp(16), dp(14), dp(16))
            // textul se aseaza pe inaltimea lui, caseta creste pana la maxLines
            includeFontPadding = true
            // ENTER trimite taskul; SHIFT+ENTER (sau Enter cu Alt) baga linie noua.
            setOnKeyListener { _, keyCode, event ->
                if (keyCode == android.view.KeyEvent.KEYCODE_ENTER && event.action == android.view.KeyEvent.ACTION_DOWN) {
                    val shift = event.isShiftPressed || event.isAltPressed
                    if (shift) false            // linie noua
                    else { sendLine(); true }   // trimite
                } else false
            }
            // fallback pentru tastaturi soft care trimit actiunea IME
            setOnEditorActionListener { _, actionId, _ ->
                val isEnter = actionId == android.view.inputmethod.EditorInfo.IME_ACTION_SEND ||
                              actionId == android.view.inputmethod.EditorInfo.IME_ACTION_DONE
                if (isEnter) { sendLine(); true } else false
            }
            // Gboard (si alte IME-uri) NU trimit KEYCODE_ENTER: tasta Enter adauga
            // direct "\n" in text. Deci detectam newline-ul in TextWatcher si trimitem.
            addTextChangedListener(object : android.text.TextWatcher {
                override fun afterTextChanged(ed: android.text.Editable) {
                    if (ed.toString().contains("\n")) {
                        val cleaned = ed.toString().replace("\n", "")
                        ed.clear()
                        ed.append(cleaned)
                        sendLine()
                    }
                }
                override fun beforeTextChanged(s: CharSequence?, a: Int, b: Int, c: Int) {}
                override fun onTextChanged(s: CharSequence?, a: Int, b: Int, c: Int) {}
            })
        }
        val send = Button(this).apply {
            text = "→"
            textSize = 18f
            setTextColor(Color.parseColor("#61AFEF"))
            setBackgroundColor(Color.TRANSPARENT)
            minWidth = 0; minimumWidth = 0
            setPadding(0, 0, 0, 0)
        }
        // butonul STOP sta LANGĂ trimitere, in randul de input, deci e mereu vizibil
        // (nu mai poate ajunge sub tastatura). apare doar cat timp agentul genereaza.
        btnStop = Button(this).apply {
            text = "■"
            textSize = 16f
            setTextColor(Color.parseColor("#E06C75"))
            setBackgroundColor(Color.TRANSPARENT)
            visibility = View.GONE
            minWidth = 0; minimumWidth = 0     // Button are minWidth implicit ~88dp -> il anulam
            setPadding(dp(14), 0, dp(14), 0)
            setOnClickListener { stopGenerating() }
        }
        row.addView(input, LinearLayout.LayoutParams(0, -2, 1f))
        // ■ = latime fixa mica, lipit de →
        row.addView(btnStop, LinearLayout.LayoutParams(dp(56), -2))
        row.addView(send, LinearLayout.LayoutParams(dp(56), -2))
        root.addView(row, LinearLayout.LayoutParams(-1, -2))

        val frame = FrameLayout(this)
        frame.addView(root, ViewGroup.LayoutParams(-1, -1))
        btnDown = Button(this).apply {
            text = "⇩"
            textSize = 18f
            setTextColor(Color.parseColor("#0D1117"))
            setBackgroundColor(Color.parseColor("#61AFEF"))
            visibility = View.GONE
            setOnClickListener {
                followTail = true
                autoScroll = true
                btnDown.visibility = View.GONE
                scroll.post {
                    programmaticScroll = true
                    scroll.fullScroll(ScrollView.FOCUS_DOWN)
                    scroll.postDelayed({ programmaticScroll = false }, 60)
                }
            }
        }
        val lp = FrameLayout.LayoutParams(-2, -2)
        lp.gravity = Gravity.END or Gravity.BOTTOM
        lp.setMargins(0, 0, 28, 180)
        frame.addView(btnDown, lp)

        setContentView(frame)

        ViewCompat.setOnApplyWindowInsetsListener(root) { v, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars())
            val cutout = insets.getInsets(WindowInsetsCompat.Type.displayCutout())
            val ime = insets.getInsets(WindowInsetsCompat.Type.ime())
            val topPad = maxOf(bars.top, cutout.top) + extraTop
            // cand tastatura e deschisa, lasam o marja in plus ca ultimul rand al casetei de
            // scris sa NU fie lipit/acoperit de tastatura (mai ales la text pe mai multe randuri)
            val imeLift = if (ime.bottom > 0) ime.bottom + dp(6) else 0
            val bottom = maxOf(bars.bottom, imeLift)
            v.updatePadding(top = topPad, bottom = bottom)
            insets
        }

        send.setOnClickListener { sendLine() }
        // cerem permisiunile DUPĂ ce ecranul All-Files (deschis tot din
        // requestAllPermissions) s-a închis si activitatea e iar in fata.
        // Altfel dialogul de runtime e acoperit de Settings si se pierde.
        requestAllPermissions()
        // ★ STARTUP-ul mutat in onRequestPermissionsResult (dupa ce permisiunile sunt acordate)
        // altfel extractAssets/startPython ruleaza cu permisiunile inca needate -> eroare
        if (allEssentialPermsGranted()) startCore()
        else requestAllPermissions()
        // Cere o singura data excluderea de la optimizarea bateriei (ca sa nu moara in Doze).
        requestIgnoreBatteryOptimizations()
    }

    /** Porneste AgentService (foreground) ca procesul sa supravietuiasca in background. */
    private fun startAgentService() {
        try {
            val i = Intent(this, AgentService::class.java).setAction(AgentService.ACTION_START)
            if (android.os.Build.VERSION.SDK_INT >= 26) startForegroundService(i) else startService(i)
        } catch (e: Exception) { appendAnsi("\n[service error] $e\n") }
    }

    /**
     * Aprinde ecranul si il tine treaz cit timp agentul lucreaza (FLAG_KEEP_SCREEN_ON),
     * apoi il lasa sa se stinga singur. Se apeleaza la inceputul/sfirsitul unui task.
     */
    private fun setTaskScreenOn(on: Boolean) {
        runOnUiThread {
            try {
                if (on) {
                    window.addFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
                } else {
                    window.clearFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
                }
            } catch (_: Exception) {}
        }
    }

    /**
     * Cere sistemului sa NU limiteze aplicatia in background (Doze/battery optimization).
     * Fara asta, Samsung suspenda agresiv procesul si tunelurile de retea.
     * Dialogul se arata o singura data (daca nu e deja acordat).
     */
    private fun requestIgnoreBatteryOptimizations() {
        try {
            if (android.os.Build.VERSION.SDK_INT < 23) return
            val pm = getSystemService(android.os.PowerManager::class.java) ?: return
            if (pm.isIgnoringBatteryOptimizations(packageName)) return
            val i = android.content.Intent(
                android.provider.Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS
            ).setData(android.net.Uri.parse("package:" + packageName))
            startActivity(i)
        } catch (e: Exception) {
            appendAnsi("\n[battery-opt] nu am putut cere excluderea: " + e.message + "\n")
        }
    }

    override fun onStop() {
        super.onStop()
        // daca utilizatorul a iesit din aplicatie, ne asiguram ca serviciul foreground ruleaza
        // (agentul continua sa lucreze prin alte aplicatii)
        startAgentService()
    }

    private fun dp(v: Int): Int = (v * resources.displayMetrics.density).toInt()

    /** ★ Inlocuieste ULTIMA linie din terminal (pentru countdown-uri). */
    private fun lastLine(s: String) {
        val cur = output.text.toString()
        val idx = cur.lastIndexOf("\n")
        val head = if (idx >= 0) cur.substring(0, idx + 1) else ""
        output.text = Ansi.toSpannable(head + s)
        scroll.post { scroll.fullScroll(android.view.View.FOCUS_DOWN) }
    }

    fun appendAnsi(s: String) {
        output.append(Ansi.toSpannable(s))

        // butonul STOP: il ascund cand taskul s-a terminat
        if (btnStop.visibility == View.VISIBLE && (s.contains("TASK #") && (s.contains("done") || s.contains("interrupted")))) {
            btnStop.visibility = View.GONE
            setTaskScreenOn(false)
        }

        // urmarim coada DOAR daca userul nu a derulat manual in sus (followTail).
        // Daca a derulat sus, textul nou creste SUB pozitia lui, fara sa-l miste.
        if (followTail) {
            scroll.post {
                if (!followTail) return@post
                programmaticScroll = true
                scroll.fullScroll(ScrollView.FOCUS_DOWN)
                scroll.postDelayed({ programmaticScroll = false }, 60)
            }
        }
    }

    // Opreste generarea curenta: trimite SIGINT procesului Python. Agentul prinde
    // KeyboardInterrupt, abandoneaza taskul elegant (pastreaza istoricul) si reia bucla.
    private fun stopGenerating() {
        val p = pyProc ?: return
        try {
            // Pe Android, java.lang.Process e UNIXProcess: nu are metoda pid(),
            // ci CAMPUL privat "pid". Incercam campul, apoi metoda (compatibilitate).
            var pid = -1
            run {
                try {
                    val f = p.javaClass.getDeclaredField("pid"); f.isAccessible = true
                    pid = f.getInt(p)
                } catch (_: Throwable) {
                    val mth = p.javaClass.getDeclaredMethod("pid"); mth.isAccessible = true
                    pid = mth.invoke(p) as Int
                }
            }
            // SIGINT = 2 (Python il prinde ca KeyboardInterrupt); destroy() ar da SIGTERM si ar omori procesul
            android.os.Process.sendSignal(pid, 2)
            appendAnsi("\u001B[38;5;208m[stop] intrerupere trimisa (SIGINT)...\u001B[0m\n")
        } catch (e: Throwable) {
            appendAnsi("[stop error: $e]\n")
        }
        btnStop.visibility = View.GONE
    }

    private fun requestAllPermissions() {
        // CEREM ABSOLUT TOT ce poate cere un app normal (in limita sandbox-ului).
        // cele cu "signature|privileged" in manifest nu se acorda unui app obisnuit, dar cererile
        // de runtime de mai jos acopera tot ce Android ofera unui app third-party.
        val perms = mutableListOf(
            Manifest.permission.CAMERA,
            Manifest.permission.RECORD_AUDIO,
            Manifest.permission.ACCESS_FINE_LOCATION,
            Manifest.permission.ACCESS_COARSE_LOCATION,
            // ACCESS_BACKGROUND_LOCATION NU se cere aici: pe Android 11+ cererea
            // ei impreuna cu permisiunile foreground face sistemul sa respinga
            // dialogul instant (se inchide in ~0.3s, fara sa apara). O cerem
            // separat, dupa ce FINE e acordata (vezi onRequestPermissionsResult).
            Manifest.permission.READ_CONTACTS,
            Manifest.permission.WRITE_CONTACTS,
            Manifest.permission.GET_ACCOUNTS,
            Manifest.permission.READ_SMS,
            Manifest.permission.SEND_SMS,
            Manifest.permission.RECEIVE_SMS,
            Manifest.permission.READ_CALL_LOG,
            Manifest.permission.WRITE_CALL_LOG,
            Manifest.permission.READ_PHONE_STATE,
            Manifest.permission.READ_PHONE_NUMBERS,
            Manifest.permission.ANSWER_PHONE_CALLS,
            Manifest.permission.CALL_PHONE,
            Manifest.permission.READ_CALENDAR,
            Manifest.permission.WRITE_CALENDAR,
            Manifest.permission.BODY_SENSORS,
            Manifest.permission.ACTIVITY_RECOGNITION
        )
        if (Build.VERSION.SDK_INT >= 31) {
            perms.add(Manifest.permission.BLUETOOTH_CONNECT)
            perms.add(Manifest.permission.BLUETOOTH_SCAN)
            perms.add(Manifest.permission.BLUETOOTH_ADVERTISE)
            perms.add(Manifest.permission.UWB_RANGING)
        }
        if (Build.VERSION.SDK_INT >= 33) {
            perms.add(Manifest.permission.POST_NOTIFICATIONS)
            perms.add(Manifest.permission.NEARBY_WIFI_DEVICES)
            perms.add(Manifest.permission.READ_MEDIA_IMAGES)
            perms.add(Manifest.permission.READ_MEDIA_VIDEO)
            perms.add(Manifest.permission.READ_MEDIA_AUDIO)
        }
        val need = perms.filter { ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED }
        if (need.isNotEmpty()) {
            // IMPORTANT: cerem intai permisiunile runtime (un dialog cu toate).
            // Ecranul All-Files (Settings) il deschidem abia dupa, in
            // onRequestPermissionsResult -> altfel Settings acopera dialogul
            // de permisiuni si acesta se pierde instantaneu.
            ActivityCompat.requestPermissions(this, need.toTypedArray(), 1)
            return
        }
        // ★ toate permisiunile esentiale deja acordate -> pornesc motorul direct
        root.postDelayed({ startCore() }, 200)
        requestAllFilesAccess()
    }

    /** Deschide ecranul "All files access" (doar daca nu e deja acordat). */
    private fun requestAllFilesAccess() {
        if (Build.VERSION.SDK_INT >= 30) {
            try {
                if (!Environment.isExternalStorageManager()) {
                    startActivity(android.content.Intent(
                        android.provider.Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION,
                        android.net.Uri.parse("package:$packageName")))
                }
            } catch (_: Exception) {}
        }
    }

    private var coreStarted = false

    /** ★ SETUP-ul se face DOAR LA PRIMA INSTALARE (flag persistent pe disc). */
    private fun setupDone(): Boolean = File(filesDir, ".setup_done").exists()
    private fun markSetupDone() {
        try { File(filesDir, ".setup_done").writeText("ok") } catch (_: Exception) {}
    }
    /** countdown-ul ruleaza doar la prima configurare. */
    private var firstConfig = false

    /** ★ Dupa ce userul se intoarce din ecranele de permisiuni (Settings), verificam
     *  si pornim motorul. Asa nu mai depindem doar de callback-ul de permisiuni. */
    override fun onResume() {
        super.onResume()
        if (!coreStarted && allEssentialPermsGranted()) {
            root.postDelayed({ startCore() }, 800)
        }
    }

    private fun allEssentialPermsGranted(): Boolean {
        val ess = arrayOf(
            Manifest.permission.CAMERA, Manifest.permission.RECORD_AUDIO,
            Manifest.permission.ACCESS_FINE_LOCATION, Manifest.permission.READ_CONTACTS,
            Manifest.permission.READ_MEDIA_IMAGES, Manifest.permission.POST_NOTIFICATIONS
        )
        return ess.all { ContextCompat.checkSelfPermission(this, it) == PackageManager.PERMISSION_GRANTED }
    }

    /** Porneste efectiv motorul: assets, bridge, python, serviciu. O SINGURA DATA. */
    private fun startCore() {
        if (coreStarted) return
        coreStarted = true

        // ★ daca setup-ul s-a facut deja -> pornesc DIRECT, fara mesaje/countdown
        if (setupDone()) {
            Thread {
                try { extractAssets() } catch (_: Exception) {}
                runOnUiThread {
                    try {
                        bridge = AndroidBridge(this, File(filesDir, "bridge.sock"))
                        bridge!!.start()
                    } catch (_: Exception) {}
                    startPython()
                    startAgentService()
                }
            }.start()
            return
        }
        firstConfig = true

        // ★ COOLDOWN 30s: countdown real prin Handler (nu Thread.sleep -> UI se blocheaza).
        val RED = "\u001b[38;5;203m"
        val NRM = "\u001b[0m"
        appendAnsi("\n" + RED + "AGENT CONFIGURATION IN PROGRESS..." + NRM + "\n"
            + RED + "Preparing keys, libraries and environment." + NRM + "\n"
            + RED + "Do not close the app." + NRM + "\n")
        // linia de countdown (o adaug o data, apoi o inlocuiesc)
        appendAnsi(RED + "Configuring... 30 seconds remaining" + NRM)

        var s = 30
        val handler = android.os.Handler(android.os.Looper.getMainLooper())
        val tick = object : Runnable {
            override fun run() {
                if (s > 1) {
                    s--
                    lastLine(RED + "Configuring... " + s + " seconds remaining" + NRM)
                    handler.postDelayed(this, 1000)
                } else {
                    lastLine(RED + "Configuring... DONE" + NRM)
                    handler.postDelayed({ runSetup() }, 1500)
                }
            }
        }
        handler.postDelayed(tick, 1000)
    }

    /** Configurarea reala (dupa countdown): extract + bridge + python + serviciu. */
    private fun runSetup() {
        val RED = "\u001b[38;5;203m"
        val NRM = "\u001b[0m"
        appendAnsi("\n" + RED + "Finalizing configuration..." + NRM + "\n")
        Thread {
            try { extractAssets() } catch (e: Exception) {
                runOnUiThread { appendAnsi(RED + "Extract error: $e" + NRM + "\n") }
            }
            runOnUiThread {
                try {
                    bridge = AndroidBridge(this, File(filesDir, "bridge.sock"))
                    bridge!!.start()
                } catch (e: Exception) { appendAnsi(RED + "Bridge error: $e" + NRM + "\n") }
                startPython()
                startAgentService()
                requestIgnoreBatteryOptimizations()
            }
        }.start()
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == 1) {
            // dupa ce userul a raspuns: cerem BACKGROUND location (doar daca FINE
            // a fost acordata si nu e deja) - separat, cum cere Android 11+
            val fineOk = ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED
            val bgOk = ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_BACKGROUND_LOCATION) == PackageManager.PERMISSION_GRANTED
            if (fineOk && !bgOk && Build.VERSION.SDK_INT >= 29) {
                root.postDelayed({
                    ActivityCompat.requestPermissions(this, arrayOf(Manifest.permission.ACCESS_BACKGROUND_LOCATION), 2)
                }, 400)
                return
            }
            root.postDelayed({ requestAllFilesAccess() }, 500)
        }
        if (requestCode == 2) {
            // dupa raspunsul la BACKGROUND, cerem All-Files
            root.postDelayed({ requestAllFilesAccess() }, 500)
        }
    }

    private fun extractAssets() {
        val dest = File(filesDir, "python")
        val stamp = File(filesDir, ".assets_v83")
        // memoria pe termen lung a agentului NU face parte din APK: o salvam
        // inainte de re-extragere si o punem la loc, ca update-urile de app sa
        // nu stearga ce a invatat agentul de la operator.
        val memFile = File(dest, "memory.md")
        val memSaved = if (memFile.exists()) memFile.readText() else null
        if (stamp.exists() && dest.exists()) return
        // la fiecare re-extragere, stergem si pyhome: altfel stdlib-ul copiat o singura data
        // (Lib/ + site-packages/) NU s-ar actualiza cand adaugam biblioteci noi in assets.
        File(filesDir, "pyhome").deleteRecursively()
        dest.deleteRecursively()
        fun copyDir(path: String, out: File) {
            val list = assets.list(path) ?: return
            if (list.isEmpty()) {
                out.parentFile?.mkdirs()
                assets.open(path).use { i -> out.outputStream().use { o -> i.copyTo(o) } }
            } else {
                out.mkdirs()
                for (child in list) copyDir(if (path.isEmpty()) child else "$path/$child", File(out, child))
            }
        }
        copyDir("python", dest)
        // punem la loc memoria salvata (daca exista); altfel ramane cea din APK
        if (memSaved != null) memFile.writeText(memSaved)
        stamp.writeText("ok")
    }

    private fun startPython() {
        Thread {
            try {
                val home = File(filesDir, "home").apply { mkdirs() }
                val py = File(applicationInfo.nativeLibraryDir, "libpyexec.so")
                val scripts = File(filesDir, "python")
                val pyHome = File(filesDir, "pyhome")
                val stdlib = File(pyHome, "lib/python3.14")
                if (!stdlib.exists()) {
                    File(pyHome, "lib").mkdirs()
                    val srcLib = File(scripts, "Lib")
                    if (srcLib.exists()) srcLib.copyRecursively(stdlib, overwrite = true)
                }
                val dynDst = File(stdlib, "lib-dynload")
                if (!dynDst.exists() || dynDst.list()?.isEmpty() != false) {
                    dynDst.mkdirs()
                    val abiTag = when (Build.SUPPORTED_ABIS.firstOrNull()) {
                        "arm64-v8a" -> "arm64"; else -> "x86_64"
                    }
                    val dynSrc = File(scripts, "libdynload/$abiTag")
                    if (dynSrc.exists()) dynSrc.copyRecursively(dynDst, overwrite = true)
                }

                // ★ SETUP ADB AUTOMAT: genereaza cheia + cert + libs la prima pornire
                try {
                    val setup = ProcessBuilder(py.absolutePath, "adb_setup.py")
                    setup.directory(scripts)
                    setup.environment()["LD_LIBRARY_PATH"] = applicationInfo.nativeLibraryDir + ":" + File(filesDir,"libs").absolutePath
                    setup.environment()["PYTHONHOME"] = pyHome.absolutePath
                    setup.environment()["HOME"] = home.absolutePath
                    setup.environment()["PATH"] = "/system/bin:/vendor/bin"
                    val sp = setup.start()
                    val sout = sp.inputStream.bufferedReader().readText()
                    sp.waitFor()
                    // ★ afisez TOATE liniile de setup, apoi mesajul final (in ordine!)
                    val wasFirst = !setupDone()
                    markSetupDone()   // ★ setup-ul s-a terminat -> nu se mai repeta
                    runOnUiThread {
                        // ★ afisez setup-ul + mesajul final DOAR la prima configurare
                        if (wasFirst) {
                            if (sout.isNotEmpty()) appendAnsi("\n[setup] " + sout.trim() + "\n")
                            appendAnsi("\n" + "\u001b[38;5;203m" + "AGENT FULLY CONFIGURED AND OPERATIONAL" + "\u001b[0m" + "\n\n")
                        }
                    }
                } catch (_: Exception) {}

                val pb = ProcessBuilder(py.absolutePath, "agent.py")
                pb.directory(scripts)
                pb.environment()["LD_LIBRARY_PATH"] = applicationInfo.nativeLibraryDir
                pb.environment()["PYTHONHOME"] = pyHome.absolutePath
                pb.environment()["HOME"] = home.absolutePath
                pb.environment()["PATH"] = "/system/bin:/vendor/bin"
                pb.environment()["PYTHONUNBUFFERED"] = "1"
                pb.environment()["TERM"] = "xterm-256color"
                pb.environment()["ANDROID_BRIDGE"] = File(filesDir, "bridge.sock").absolutePath
                pb.environment()["AGENT_BRIDGE_PORT_FILE"] = File(filesDir, "bridge.port").absolutePath
pb.environment()["AGENT_HOME"] = File(android.os.Environment.getExternalStoragePublicDirectory(android.os.Environment.DIRECTORY_DOWNLOADS), "Agent").absolutePath
                pb.environment()["AGENT_COLS"] = run {
                    val test = android.widget.TextView(this@MainActivity).apply {
                        textSize = 11f; typeface = mono
                    }
                    val w = test.paint.measureText("M")
                    val usable = resources.displayMetrics.widthPixels - 48f
                    if (w > 0f) (usable / w).toInt().coerceAtLeast(20) else 46
                }.toString()
                pb.redirectErrorStream(true)

                val p = pb.start()
                pyProc = p
                pyIn = OutputStreamWriter(p.outputStream)

                val raw = p.inputStream
                val buf = ByteArray(4096)
                while (true) {
                    val k = raw.read(buf)
                    if (k < 0) break
                    val chunk = String(buf, 0, k, Charsets.UTF_8)
                    synchronized(pending) {
                        pending.append(chunk.replace("\r", ""))
                        var idx: Int
                        while (pending.indexOf("\n").also { idx = it } >= 0) {
                            val line = pending.substring(0, idx + 1)
                            pending.delete(0, idx + 1)
                            runOnUiThread { appendAnsi(line) }
                        }
                        if (pending.isNotEmpty() && pending.length > 4096) {
                            val rest = pending.toString(); pending.setLength(0)
                            runOnUiThread { appendAnsi(rest) }
                        }
                    }
                }
                runOnUiThread { appendAnsi("\n[proces terminat]\n") }
            } catch (e: Exception) {
                val msg = e.toString()
                runOnUiThread { appendAnsi("\n[EROARE] $msg\n") }
            }
        }.start()
    }

    private fun sendLine() {
        // one line only: the text field may contain embedded newlines (IME / Enter),
        // and an extra blank line would be read by the agent's input() as a separate, empty line.
        val t = input.text.toString().replace("\r", "").replace("\n", " ").trim()
        if (t.isEmpty()) return
        input.setText("")
        // NU afisam ecou aici: agentul afiseaza el linia "You > <mesaj>" in _task_head.
        btnStop.visibility = View.VISIBLE
        setTaskScreenOn(true)
        try { pyIn?.write(t + "\n"); pyIn?.flush() } catch (e: Exception) {
            appendAnsi("[write failed: $e]\n")
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        // IMPORTANT: NU omoram procesul Python si bridge-ul daca AgentService ruleaza in
        // foreground. Altfel agentul moare la minimizare si nu mai poate lucra prin alte
        // aplicatii. Le oprim doar cand serviciul a fost oprit explicit (butonul /stop).
        if (!AgentService.running) {
            try { pyProc?.destroy() } catch (_: Exception) {}
            try { bridge?.stop() } catch (_: Exception) {}
        }
    }
}
