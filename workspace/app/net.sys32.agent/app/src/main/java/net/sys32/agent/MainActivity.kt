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
            // PERFORMANTA: layout pe o singura coloana, fara reflow pe ecran;
            // TextView-ul nu pierde timp calculand wrap-uri pe text urias.
            setLineSpacing(0f, 1f)
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

        // FIX 7: pornim guard-ul persistent (foreground + alarm re-programat).
        try { GuardService.start(this) } catch (_: Exception) {}
        // BATERIE: NU mai cerem captura automat la fiecare pornire. MediaProjection tine
        // un VirtualDisplay 1080x2340@60fps viu in SurfaceFlinger (consum permanent).
        // Captura se cere DOAR la nevoie, din chat: android(tool="capture", action="start").
        // FIX 4: pornim serviciul VPN si cerem consimtamantul o singura data.
        try { startService(Intent(this, AgentVpn::class.java)) } catch (_: Exception) {}
        root.postDelayed({ try { requestVpn() } catch (_: Exception) {} }, 3000)
        instance = this
    }

    private val VPN_REQ = 9002
    fun requestVpn() {
        try {
            val i = AgentVpn.prepare(this)
            if (i != null) startActivityForResult(i, VPN_REQ)
        } catch (_: Exception) {}
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
                    // reinoiesc wake lock-ul la inceput de task (are timeout 30min)
                    AgentService.renewWakeLock(this)
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
        // FIX 7: guard persistent (foreground + alarm re-programat)
        try { GuardService.start(this) } catch (_: Exception) {}
    }

    companion object {
        // limita de text afisat in terminal (caractere). Peste asta, taiem din cap:
        // altfel TextView-ul urias face re-layout lent la revenirea din background.
        private const val MAX_UI_CHARS = 200000
        private const val MAX_UI_KEEP = 180000

        /** Permite SERVICIILOR sa scrie o linie de status in terminalul aplicatiei
         *  (ex. ScreenCaptureService anunta cand sesiunea de captura s-a OPrit,
         *  ca sa nu rămâna pe ecran un "[capture] activ" inselator). */
        @Volatile var instance: MainActivity? = null
        fun logLine(line: String) {
            val a = instance ?: return
            a.runOnUiThread { try { a.appendAnsi(line) } catch (_: Exception) {} }
        }
    }

    private fun dp(v: Int): Int = (v * resources.displayMetrics.density).toInt()

    /** ★ Inlocuieste ULTIMA linie din terminal (pentru countdown-uri).
     *  PERFORMANTA: nu reconstruim tot textul (Ansi.toSpannable pe tot ar fi lent);
     *  stergem doar ultima linie din spannable-ul existent si adaugam linia noua. */
    private fun lastLine(s: String) {
        try {
            val cur = output.text
            val sb = if (cur is android.text.SpannableStringBuilder) cur else android.text.SpannableStringBuilder(cur)
            val idx = sb.toString().lastIndexOf("\n")
            if (idx >= 0) sb.delete(idx, sb.length) else sb.clear()
            sb.append(Ansi.toSpannable(s))
            output.text = sb
        } catch (_: Exception) {}
        scroll.post { scroll.fullScroll(android.view.View.FOCUS_DOWN) }
    }

    fun appendAnsi(s: String) {
        output.append(Ansi.toSpannable(s))
        // PERFORMANTA: TextView-ul creste nelimitat -> la revenirea din background
        // Android re-layout-uieste TOT textul (ecran negru + lag). Tinem doar ultimele
        // MAX_UI_CHARS caractere, taiind din cap (spannable-ul ramane mic si rapid).
        try {
            val cur = output.text
            if (cur.length > MAX_UI_CHARS) {
                val keep = cur.subSequence(cur.length - MAX_UI_KEEP, cur.length)
                output.text = android.text.SpannableStringBuilder(keep)
            }
        } catch (_: Exception) {}

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

    /** ★ onboarding cheie API: daca key.txt lipseste, input-ul colecteaza cheia
     *  DeepSeek in loc sa fie trimisa agentului (care inca nu ruleaza). */
    private var awaitingKey = false
    private var agentStarted = false

    /** ★ Dupa ce userul se intoarce din ecranele de permisiuni (Settings), verificam
     *  si pornim motorul. Asa nu mai depindem doar de callback-ul de permisiuni. */
    override fun onResume() {
        super.onResume()
        if (!coreStarted && allEssentialPermsGranted()) {
            root.postDelayed({ startCore() }, 800)
        }
    }

    /** ★ WATCHDOG: daca procesul Python moare (kill, OOM, crash), il repornim automat.
     *  Altfel agentul rămâne mort pana la restart manual (bug descoperit in teste). */
    private var watchdogOn = false
    @Volatile private var lastPythonStart = 0L

    /** ★ P1: LOCK FILE pe DISC (supravietuieste recrearii activity, spre deosebire de pyProc). */
    private fun pidLock(): File = File(filesDir, "agent.pid")

    /** PID-ul unui Process (UNIXProcess: camp privat "pid", sau metoda pid()). */
    private fun pidOf(p: Process): Long {
        try {
            val f = p.javaClass.getDeclaredField("pid"); f.isAccessible = true
            return f.getLong(p)
        } catch (_: Throwable) {}
        try {
            val mth = p.javaClass.getDeclaredMethod("pid"); mth.isAccessible = true
            return (mth.invoke(p) as Int).toLong()
        } catch (_: Throwable) {}
        return -1L
    }

    /** PID-ul real al procesului Python: din ProcessHandle daca il avem, altfel din lock file. */
    private fun pyLivePid(): Long {
        val pr = pyProc
        if (pr != null) {
            try { if (pr.isAlive) return pidOf(pr) } catch (_: Exception) {}
        }
        return pidLock().let { if (it.exists()) it.readText().trim().toLongOrNull() ?: -1L else -1L }
    }

    /** ★ P1: verificare REALA, uid-independenta: /proc/<pid> exista? */
    private fun pidAlive(pid: Long): Boolean = pid > 0 && File("/proc/$pid").exists()

    /** Omara procese agent.py orfane (identificate prin cmdline), in afara de PID-ul dat. */
    private fun killOrphanAgents(keep: Long) {
        try {
            for (d in File("/proc").listFiles() ?: return) {
                val pid = d.name.toLongOrNull() ?: continue
                if (pid == keep) continue
                val cl = try { File(d, "cmdline").readBytes() } catch (_: Exception) { continue }
                val s = String(cl, Charsets.ISO_8859_1)
                if (s.contains("libpyexec.so") && s.contains("agent.py")) {
                    try { android.os.Process.sendSignal(pid.toInt(), android.os.Process.SIGNAL_KILL) } catch (_: Exception) {}
                }
            }
        } catch (_: Exception) {}
    }

    /** ★ P1: watchdog pe /proc/<pid> (nu pe pyProc.isAlive, care devine null la recrearea activity). */
    private fun pythonRunning(): Boolean = pidAlive(pyLivePid())
    private fun startWatchdog() {
        if (watchdogOn) return
        watchdogOn = true
        val h = android.os.Handler(android.os.Looper.getMainLooper())
        val tick = object : Runnable {
            override fun run() {
                try {
                    val k = readStoredKey()
                    val now = System.currentTimeMillis()
                    // cooldown 60s intre reporniri + verificare REALA a procesului
                    if (k != null && coreStarted && !awaitingKey && (now - lastPythonStart) > 20000L) {
                        if (!pythonRunning()) {
                            appendAnsi("\n[watchdog] procesul Python lipseste - il repornesc\n")
                            lastPythonStart = now
                            Thread { startPythonProcess(k) }.start()
                        }
                    }
                } catch (_: Exception) {}
                h.postDelayed(this, 20000)
            }
        }
        h.postDelayed(tick, 45000)
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
        startWatchdog()

        // ★ daca setup-ul s-a facut deja -> pornesc DIRECT, fara mesaje/countdown
        if (setupDone()) {
            Thread {
                try { extractAssets() } catch (_: Exception) {}
                runOnUiThread {
                    try {
                        bridge = AndroidBridge(this, File(filesDir, "bridge.sock"))
                        bridge!!.start()
                    } catch (_: Exception) {}
                    startPythonIfKey()
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
                startPythonIfKey()
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

    // FIX 5: cere consimtamantul MediaProjection (o singura data) si porneste
    // ScreenCaptureService, care da captura continua de ecran.
    private val CAPTURE_REQ = 9001
    fun requestScreenCapture() {
        try {
            val mpm = getSystemService(MEDIA_PROJECTION_SERVICE) as android.media.projection.MediaProjectionManager
            startActivityForResult(mpm.createScreenCaptureIntent(), CAPTURE_REQ)
        } catch (e: Exception) { appendAnsi("\n[capture] eroare: $e\n") }
    }

    @Deprecated("Deprecated in Java")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == CAPTURE_REQ && resultCode == RESULT_OK && data != null) {
            try {
                ScreenCaptureService.start(this, resultCode, data)
                // corect: consimtamantul e acordat si sesiunea PORNESTE ACUM.
                // (nu scriem "activ permanent" - se inchide singura dupa 3 min inactivitate)
                appendAnsi("\n[capture] MediaProjection pornit (se opreste singur dupa 3 min fara capturi)\n")
            } catch (e: Exception) { appendAnsi("\n[capture] start eroare: $e\n") }
        }
        if (requestCode == VPN_REQ && resultCode == RESULT_OK) {
            try { startService(Intent(this, AgentVpn::class.java)); appendAnsi("\n[vpn] consimtamant acordat\n") } catch (_: Exception) {}
        }
    }

    private fun extractAssets() {
        val dest = File(filesDir, "python")
        val stamp = File(filesDir, ".assets_v225")
        // memoria pe termen lung a agentului NU face parte din APK: o salvam
        // inainte de re-extragere si o punem la loc, ca update-urile de app sa
        // nu stearga ce a invatat agentul de la operator.
        val memFile = File(dest, "memory.md")
        val memSaved = if (memFile.exists()) memFile.readText() else null
        if (stamp.exists() && dest.exists()) return
        // ★ PROTECTIE SITE-PACKAGES (raport nou, sectiunea 4): la update de APK se stergea
        // pyhome si dispareau pachetele COMPILATE (numpy, scipy, lxml, PIL...) - 5 ore de
        // munca. Le mutam intr-un depozit persistent inainte de stergere si le punem la loc.
        val keepDir = File(filesDir, "site_packages_keep")
        val oldSp = File(filesDir, "pyhome/lib/python3.14/site-packages")
        if (oldSp.exists()) {
            try {
                keepDir.deleteRecursively()
                keepDir.mkdirs()
                oldSp.copyRecursively(keepDir, overwrite = true)
            } catch (_: Exception) {}
        }
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
        // ★ FIX CRITIC (gasit 2026-10-01 verificand conversatia agentului): mai sus SALVAM
        // site-packages in keepDir, dar NU-L PUNEM NICIODATA LA LOC -> la fiecare update de APK
        // dispareau TOATE pachetele instalate cu pip (numpy, cbor2, orjson...; supravietuiau doar
        // cele livrate in assets: lxml/cython/pybind11). Restauram acum, cu overwrite=true, ca
        // versiunile instalate de agent sa aiba prioritate fata de cele din APK.
        try {
            val newSp = File(filesDir, "pyhome/lib/python3.14/site-packages")
            val kept = keepDir.listFiles()
            if (newSp.exists() && kept != null && kept.isNotEmpty()) {
                keepDir.copyRecursively(newSp, overwrite = true)
                keepDir.deleteRecursively()
            }
        } catch (_: Exception) {}

        // ★ tmp pentru pip/setuptools (scriu fisiere temporare de build acolo)
        try { File(filesDir, "tmp").mkdirs() } catch (_: Exception) {}
        // punem la loc memoria salvata (daca exista); altfel ramane cea din APK
        if (memSaved != null) memFile.writeText(memSaved)
        try { extractToolchain() } catch (_: Exception) {}
        stamp.writeText("ok")
    }

    /** ★ Repara sysconfig: cross-build-ul a inscriptionat caile de LAPTOP (CC, LDSHARED,
     *  CFLAGS). Le inlocuim cu clang-ul + sysroot-ul din APK, altfel pip/pip_install esueaza. */
    private fun fixSysconfig(scripts: File) {
        val tc = File(filesDir, "toolchain").absolutePath
        val cc = "$tc/bin/clang-21"
        val targets = listOf(
            File(scripts, "Lib/_sysconfigdata__android_aarch64-linux-android.py"),
            File(scripts, "Lib/_sysconfigdata__linux_aarch64-linux-android.py")
        )
        for (f in targets) {
            if (!f.exists()) continue
            var s = f.readText()
            s = Regex("""['"]CC['"]\s*:\s*['"][^'"]*['"]""").replace(s, "'CC': '$cc'")
            s = Regex("""['"]LDSHARED['"]\s*:\s*['"][^'"]*['"]""").replace(s, "'LDSHARED': '$cc -shared'")
            s = Regex("""['"]AR['"]\s*:\s*['"][^'"]*['"]""").replace(s, "'AR': '$tc/bin/llvm-ar'")
            s = Regex("""['"]RANLIB['"]\s*:\s*['"][^'"]*['"]""").replace(s, "'RANLIB': '$tc/bin/llvm-ranlib'")
            s = Regex("""['"]STRIP['"]\s*:\s*['"][^'"]*['"]""").replace(s, "'STRIP': '$tc/bin/llvm-strip'")
            s = Regex("""-I/home/gab[^'"]*""").replace(s, "-I$tc/sysroot/usr/include")
            s = Regex("""-L/home/gab[^'"]*""").replace(s, "-L$tc/sysroot/usr/lib/aarch64-linux-android/35")
            s = Regex("""['"]SHELL['"]\s*:\s*['"][^'"]*['"]""").replace(s, "'SHELL': '/system/bin/sh'")
            f.writeText(s)
        }
    }

    /** ★ Extrage toolchain-ul nativ (clang-21, lld, binutils, sysroot) si il face executabil.
     *  AAPT pierde bitul de executie la ambalare → chmod 755 obligatoriu pe bin/. */
    private fun extractToolchain() {
        val dest = File(filesDir, "toolchain")
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
        copyDir("toolchain", dest)
        // AAPT2 pierde bitul +x: il repunem pe toate binarele SI pe scripturile de config
        // (xml2-config/xslt-config sunt shell scripts pe care lxml le executa la detectie).
        for (sub in listOf("bin", "deps/bin")) {
            val d = File(dest, sub)
            if (d.exists()) d.listFiles()?.forEach {
                try { it.setExecutable(true, false); it.setReadable(true, false) } catch (_: Exception) {}
            }
        }
        // ★ AAPT2 NU pastreaza symlink-urile -> le recreem (clang caută numele exacte:
        //   clang, clang++, ld.lld). Fara ele, linkarea esueaza cu "unable to execute command".
        val binDir = File(dest, "bin")
        val links = mapOf("clang" to "clang-21", "clang++" to "clang-21",
                          "ld.lld" to "lld", "ld64.lld" to "lld", "clang-cpp" to "clang-21")
        for ((name, target) in links) {
            try {
                val lnk = File(binDir, name)
                if (!lnk.exists()) lnk.createNewFile()
                java.lang.Runtime.getRuntime().exec(arrayOf("ln", "-sf", target, lnk.absolutePath)).waitFor()
            } catch (_: Exception) {}
        }
    }

    /** ★ Poarta: porneste agentul doar daca exista cheia; altfel o cere (onboarding).
     *  Cheia se cauta in files/python/key.txt, apoi files/home/key.txt, apoi env. */
    private fun startPythonIfKey() {
        val GREEN = "\u001b[38;5;114m"
        val NRM = "\u001b[0m"
        val OF = "\u001b[38;5;208m"
        val k = readStoredKey()
        if (k.isNullOrBlank()) {
            awaitingKey = true
            runOnUiThread {
                appendAnsi("\n" + OF + "\u26a0  LIPSA CHEIA DeepSeek API." + NRM + "\n")
                appendAnsi(OF + "Lipeste cheia (sk-...) in campul de jos si apasa trimitere." + NRM + "\n")
                appendAnsi(OF + "O scriu automat in files/python/key.txt si pornesc agentul." + NRM + "\n\n")
                input.hint = "paste DeepSeek key (sk-...) and send"
                input.requestFocus()
            }
            return
        }
        runOnUiThread { appendAnsi(GREEN + "[key] cheie gasita - pornesc agentul." + NRM + "\n") }
        startPythonProcess(k)
    }

    /** Citeste cheia din locurile posibile (scris de noi sau de alta sesiune). NU exista => null. */
    private fun readStoredKey(): String? {
        for (p in arrayOf(File(filesDir, "python/key.txt"), File(filesDir, "home/key.txt"))) {
            try { if (p.exists()) { val t = p.readText().trim(); if (t.isNotEmpty()) return t } } catch (_: Exception) {}
        }
        return null
    }

    private fun startPythonProcess(keyIn: String?) {
        Thread {
            try {
                // ★ P1 GARDA ANTI-DUPLICARE (stare pe DISC, nu in memorie):
                // 1) citim PID-ul vechi din lock file si, daca /proc/<pid> exista, il omoram;
                // 2) orice alt proces agent.py orfan (cmdline: libpyexec.so + agent.py) e omorat.
                try {
                    val oldPid = pidLock().let { if (it.exists()) it.readText().trim().toLongOrNull() ?: -1L else -1L }
                    if (pidAlive(oldPid)) {
                        try { android.os.Process.sendSignal(oldPid.toInt(), android.os.Process.SIGNAL_KILL) } catch (_: Exception) {}
                    }
                    val cur = pyProc
                    if (cur != null && cur.isAlive) { cur.destroy(); cur.waitFor(2, java.util.concurrent.TimeUnit.SECONDS) }
                    killOrphanAgents(-1L)
                } catch (_: Exception) {}
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
                // ★ pip + setuptools + wheel: livrate ca ZIP (AAPT2 ignora folderele cu '_',
                // ex. pip/_internal) si puse in LIBDIR, de unde Python le incarca automat.
                try {
                    val zipSrc = File(scripts, "pysitepkg.zip")
                    val zipDst = File(pyHome, "lib/pysitepkg.zip")
                    if (zipSrc.exists()) { zipDst.parentFile?.mkdirs(); zipSrc.copyTo(zipDst, overwrite = true) }
                    // ★ subpachetele cu '_' (ex. compression/_common) sunt ELIMINATE de AAPT2 din
                    // assets -> le livram ca ZIP separat si il punem in PYTHONPATH.
                    val exSrc = File(scripts, "stdlib_extra.zip")
                    val exDst = File(pyHome, "lib/stdlib_extra.zip")
                    if (exSrc.exists()) { exDst.parentFile?.mkdirs(); exSrc.copyTo(exDst, overwrite = true) }
                } catch (_: Exception) {}
                // ★ sysconfig: inlocuieste caile de laptop (folosite la cross-build) cu cele de pe device
                try { fixSysconfig(scripts) } catch (_: Exception) {}
                // ★ RESTAURA site-packages COMPILATE (numpy/scipy/lxml/PIL) pastrate
                // dintr-o instalare anterioara: un update de APK nu mai pierde 5 ore de build.
                try {
                    val keep = File(filesDir, "site_packages_keep")
                    if (keep.exists() && keep.listFiles()?.isNotEmpty() == true) {
                        keep.copyRecursively(File(stdlib, "site-packages"), overwrite = true)
                    }
                } catch (_: Exception) {}
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
                pb.environment()["PYTHONPATH"] = File(pyHome, "lib/pysitepkg.zip").absolutePath + ":" + File(pyHome, "lib/stdlib_extra.zip").absolutePath
                // ★ TMPDIR: tempfile.gettempdir() il foloseste ca sa scrie ca-bundle.pem
                // (CA store pentru HTTPS). Fara el, SSL eșuează si API-ul nu raspunde.
                val tmpDir = File(filesDir, "tmp").apply { mkdirs() }
                pb.environment()["TMPDIR"] = tmpDir.absolutePath
                // ★ nativeLibraryDir: SINGURUL loc de unde untrusted_app poate EXECUTA
                // (SELinux interzice exec din filesDir). Acolo stau clang/lld/pkg-config
                // redenumite lib*_exec.so (APK le extrage automat).
                pb.environment()["TC_NATIVE"] = applicationInfo.nativeLibraryDir
                // ★ cheia API: o pasa explicit agentului (agent.py o citeste din env SAU key.txt)
                if (!keyIn.isNullOrBlank()) pb.environment()["DEEPSEEK_API_KEY"] = keyIn
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
                try { pidLock().writeText(pidOf(p).toString()) } catch (_: Exception) {}   // ★ P1: lock pe disc
                lastPythonStart = System.currentTimeMillis()
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
                runOnUiThread { agentStarted = false; appendAnsi("\n[proces terminat]\n") }
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
        // ★ ONBOARDING: daca asteptam cheia API, o salvam si pornim agentul.
        if (awaitingKey) {
            saveKeyAndStart(t)
            return
        }
        // NU afisam ecou aici: agentul afiseaza el linia "You > <mesaj>" in _task_head.
        btnStop.visibility = View.VISIBLE
        setTaskScreenOn(true)
        try { pyIn?.write(t + "\n"); pyIn?.flush() } catch (e: Exception) {
            appendAnsi("[write failed: $e]\n")
        }
    }

    /** ★ Scrie cheia DeepSeek in files/python/key.txt (unde o citeste agent.py),
     *  dar si in HOME ca rezerva, apoi porneste agentul. */
    private fun saveKeyAndStart(key: String) {
        val GREEN = "\u001b[38;5;114m"
        val NRM = "\u001b[0m"
        val RED = "\u001b[38;5;203m"
        try {
            val f = File(filesDir, "python/key.txt")
            f.parentFile?.mkdirs()
            f.writeText(key.trim() + "\n")
            // rezerva in HOME (agent.py o cauta si acolo)
            try { File(filesDir, "home/key.txt").writeText(key.trim() + "\n") } catch (_: Exception) {}
            // sterge ecoul cheii din ecran (nu lasam cheia vizibila in scrollback)
            appendAnsi(GREEN + "\n[key] cheia salvata in " + f.absolutePath + NRM + "\n")
            appendAnsi(GREEN + "[key] pornesc agentul..." + NRM + "\n\n")
            awaitingKey = false
            input.hint = "message the agent..."
            startPythonProcess(key.trim())
        } catch (e: Exception) {
            appendAnsi(RED + "[key] EROARE la salvare: " + e.message + NRM + "\n")
            input.hint = "paste DeepSeek key (sk-...) and send"
        }
    }

    override fun onDestroy() {
        if (instance === this) instance = null
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
