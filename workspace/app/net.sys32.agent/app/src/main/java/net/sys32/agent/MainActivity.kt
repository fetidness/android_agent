package net.sys32.agent

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.Typeface as TF
import android.os.Build
import android.os.Bundle
import android.os.Environment
import android.text.InputType
import android.text.TextUtils
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.view.WindowManager
import android.widget.Button
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ProgressBar
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
    private lateinit var btnSpeak: Button
    private lateinit var audioPanel: LinearLayout
    private lateinit var ptt: PushToTalk
    private lateinit var inputRow: LinearLayout
    private lateinit var audioTitle: TextView
    private lateinit var audioSub: TextView
    private lateinit var audioState: TextView
    private lateinit var audioYou: TextView
    private lateinit var audioHint: TextView
    // acumulator: textul pe care il citim cu voce tare la 🔊 (ultimul raspuns al agentului)
    private val lastAnswer = StringBuilder()
    // true = urmatorul text adaugat incepe un mesaj NOU al agentului (golim acumulatorul)
    @Volatile private var newTurn = true
    // true = suntem in interiorul raspunsului unui task (intre "TASK #N" si footer)
    @Volatile private var inTask = false
    // true = am vazut "AGENT >" si urmeaza raspunsul propriu-zis
    @Volatile private var inAgent = false
    // true = ultimul mesaj trimis a fost /audio -> raspunsul se rosteste automat, fara sa se afiseze
    @Volatile private var audioNext = false
    // mod persistent: /audio on -> toate raspunsurile se rostesc pana la /audio off
    @Volatile private var audioMode = false
    // operatorul tine apasat HOLD TO TALK: nimic nu are voie sa inceapa sa vorbeasca
    @Volatile private var userTalking = false
    private val audioText = StringBuilder()

    /** Arata in panoul audio ce a scris operatorul si ca agentul lucreaza. */
    private fun showAudioYou(msg: String) {
        if (!audioMode) return
        runOnUiThread {
            audioYou.text = "You: " + msg.take(120)
            audioState.text = "Agent is working... please wait."
            audioState.setTextColor(Color.parseColor("#E5C07B"))
        }
    }

    /** Comuta interfata intre terminal si panoul curat de mod audio. */
    private fun setAudioUi(on: Boolean) {
        runOnUiThread {
            audioPanel.visibility = View.GONE          // un singur ecran: panoul de voce
            inputRow.visibility = if (on) View.GONE else View.VISIBLE
            scroll.visibility = if (on) View.GONE else View.VISIBLE
            if (on) audioState.text = "Ready - just type."
            if (on) ptt.show() else ptt.hide()
            hideKeyboard(on)
        }
    }

    /** In modul audio tastatura nu are ce cauta: nu se poate tasta nimic acolo. */
    private fun hideKeyboard(lock: Boolean) {
        try {
            val imm = getSystemService(Context.INPUT_METHOD_SERVICE) as android.view.inputmethod.InputMethodManager
            if (lock) {
                // scoate focusul din camp si blocheaza tastatura pana la EXIT
                input.clearFocus()
                scroll.requestFocus()
                imm.hideSoftInputFromWindow(input.windowToken, 0)
                input.showSoftInputOnFocus = false       // nici un tap pe camp nu mai deschide IME
                window.setSoftInputMode(
                    WindowManager.LayoutParams.SOFT_INPUT_STATE_ALWAYS_HIDDEN or
                    WindowManager.LayoutParams.SOFT_INPUT_ADJUST_NOTHING)
            } else {
                input.showSoftInputOnFocus = true
                window.setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE or
                        WindowManager.LayoutParams.SOFT_INPUT_STATE_UNSPECIFIED)
            }
        } catch (e: Exception) { android.util.Log.w("audio", "keyboard: $e") }
    }

    /** Ieșire din modul audio din UI (chat-ul e ascuns, deci comanda /audio off nu se poate tasta). */
    private fun exitAudioMode() {
        audioMode = false; audioNext = false; audioText.setLength(0)
        userTalking = false
        PhononTts.cancel()
        setAudioUi(false)
        appendAnsi("\u001b[38;5;114m[audio] OFF: replies are shown as text again.\u001b[0m\n")
        toast("audio mode OFF")
        followTail = true; scrollToBottom()
    }

    /** Push-to-talk (Whisper offline) in modul /audio on - vezi PushToTalk.kt. */
    private fun buildPushToTalk(frame: android.widget.FrameLayout) {
        ptt = PushToTalk(this,
            onExit = { exitAudioMode() },
            onStopVoice = { stopAgentVoice("Stopped."); toast("voice stopped") },
            onPress = {
            // barge-in imediat in UI: operatorul vrea sa vorbeasca peste agent
            userTalking = true
            stopAgentVoice("Listening...")
        }, onRelease = { userTalking = false }) { text ->
            userTalking = false
            // orice mesaj vocal nou intrerupe vocea veche, ca sa nu se suprapuna
            stopAgentVoice("Interrupted - listening...")
            // vocea intra in agent EXACT ca un mesaj tastat: se vede in caseta si costa la fel
            input.setText(text)
            newTurn = true; inTask = false; inAgent = false
            showAudioYou(text)
            sendLine()
        }
        ptt.build(frame)
    }

    /** Ce face agentul chiar acum: "Working - <pasul real>", in ambele ecrane. */
    fun audioWork(msg: String) {
        audioPanelStatus("Working - " + msg)
        ptt.progress("Working - " + msg)
    }

    /** Starea aratata in panoul principal al modului audio (apelata si de push-to-talk). */
    fun audioPanelStatus(msg: String) {
        if (!audioMode) return
        runOnUiThread { if (audioMode) audioState.text = msg }
    }

    /** Starea vocii, afisata pe panoul audio (nu in terminal). */
    private fun audioStatus(msg: String) {
        if (!audioMode) return
        runOnUiThread { audioState.text = msg }
    }

    /** Opreste vocea agentului (barge-in): operatorul vrea sa vorbeasca din nou. */
    fun stopAgentVoice(reason: String) {
        if (!PhononTts.isBusy()) return
        PhononTts.cancel()
        runOnUiThread { if (audioMode) audioState.text = reason }
    }

    /** /audio sau /audio <mesaj>: raspunsul se rosteste, nu se afiseaza. */
    private fun isAudioCommand(m: String): Boolean {
        val t = m.trim().lowercase()
        return t == "/audio" || t.startsWith("/audio ")
    }
    private fun clearAudioText() { audioText.setLength(0) }

    /** Linii de infrastructura care nu trebuie citite cu voce tare. */
    private fun isInfra(t: String): Boolean =
        t.startsWith("[") || t.startsWith("+-") || t.startsWith("tok ") || t.startsWith("sess ") ||
        t.startsWith("\u25B8") || t.startsWith("SAFE") || t.startsWith("$")

    private val ANSWER_CAP = 12000
    @Volatile private var generating = false
    private var bridge: AndroidBridge? = null
    private var pyProc: Process? = null
    private var pyIn: OutputStreamWriter? = null
    private val pending = StringBuilder()
    private var autoScroll = true
    private var permRequested = false   // anti-bucla: cerem o singura data automat din onResume
    @Volatile private var followTail = true
    private var programmaticScroll = false
    // ★ FIX 2026-10-07: ultima inaltime cunoscuta a ScrollView-ului. Folosita ca sa
    // distingem o derulare REALA a userului de o ajustare automata de scroll facuta de
    // ScrollView cand i se schimba inaltimea (IME show/hide).
    private var lastScrollHeight = 0
    // true DOAR cat timp degetul utilizatorului atinge efectiv ScrollView-ul.
    // Fara el, TextView-ul selectabil (setTextIsSelectable) emite scroll
    // "fals" (re-layout/focus) pe care listener-ul il lua drept derulare manuala.
    private var userTouching = false

    // ===== FONT (sp) =====
    // dimensiunea fontului terminalului (sp), persistata intre lansari
    private var fontSizeSp = 15f
    private lateinit var fontLabel: TextView

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

        // dimensiunea fontului: citita din preferinte (persistata), implicit 15sp
        fontSizeSp = getSharedPreferences(PREFS, MODE_PRIVATE)
            .getFloat("font_size", fontSizeSp).coerceIn(FONT_MIN, FONT_MAX)

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
            textSize = fontSizeSp
            typeface = mono
            // SELECTIE + COPIERE: long-press pe text -> bara cu Copy / Select all.
            // Copierea apare DOAR cand selectezi textul (fara buton dedicat).
            setTextIsSelectable(true)
            setTextColor(Color.parseColor("#ABB2BF"))
            setBackgroundColor(Color.parseColor("#0D1117"))
            // PERFORMANTA: layout pe o singura coloana, fara reflow pe ecran;
            // TextView-ul nu pierde timp calculand wrap-uri pe text urias.
            setLineSpacing(0f, 1f)
        }
        scroll.addView(output, ViewGroup.LayoutParams(-1, -2))

        // ===== PANOU MOD AUDIO (vizibil doar cu /audio on) =====
        // Ecran curat: spune doar ca modul e activ si arata starea vocii.
        audioPanel = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setBackgroundColor(Color.parseColor("#0D1117"))
            visibility = View.GONE
            setPadding(dp(28), dp(28), dp(28), dp(28))
        }
        audioTitle = TextView(this).apply {
            text = "\uD83D\uDD0A  AUDIO MODE"
            textSize = 26f
            typeface = Typeface.DEFAULT_BOLD
            setTextColor(Color.parseColor("#98C379"))
            gravity = Gravity.CENTER
        }
        audioSub = TextView(this).apply {
            text = "Every reply is spoken, nothing is shown."
            textSize = 15f
            setTextColor(Color.parseColor("#ABB2BF"))
            gravity = Gravity.CENTER
            setPadding(0, dp(14), 0, 0)
        }
        audioState = TextView(this).apply {
            text = ""
            textSize = 14f
            typeface = mono
            setTextColor(Color.parseColor("#61AFEF"))
            gravity = Gravity.CENTER
            setPadding(0, dp(26), 0, 0)
        }
        audioHint = TextView(this).apply {
            text = "Tap EXIT AUDIO MODE to go back to text (or type /audio off)."
            textSize = 13f
            setTextColor(Color.parseColor("#5C6370"))
            gravity = Gravity.CENTER
            setPadding(0, dp(30), 0, 0)
        }
        audioYou = TextView(this).apply {
            text = ""
            textSize = 15f
            typeface = Typeface.DEFAULT_BOLD
            setTextColor(Color.parseColor("#E5C07B"))
            gravity = Gravity.CENTER
            setPadding(dp(8), dp(22), dp(8), 0)
        }
        audioPanel.addView(audioTitle)
        audioPanel.addView(audioSub)
        audioPanel.addView(audioYou)
        audioPanel.addView(audioState)
        audioPanel.addView(audioHint)

        // ===== BARA DE CONTROL (sus, dreapta): dimensiune font =====
        val bar = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setBackgroundColor(Color.parseColor("#11151C"))
            setPadding(dp(8), dp(2), dp(8), dp(2))
            gravity = Gravity.CENTER_VERTICAL
        }
        fun miniBtn(label: String, color: String, onClick: () -> Unit) = Button(this).apply {
            text = label
            textSize = 13f
            typeface = mono
            setTextColor(Color.parseColor(color))
            setBackgroundColor(Color.TRANSPARENT)
            minWidth = 0; minimumWidth = 0
            setPadding(dp(12), dp(2), dp(12), dp(2))
            setOnClickListener { onClick() }
        }
        fontLabel = TextView(this).apply {
            text = fontSizeSp.toInt().toString()
            textSize = 13f
            typeface = mono
            setTextColor(Color.parseColor("#5C6370"))
            setPadding(dp(6), 0, dp(6), 0)
        }
        val btnFontMinus = miniBtn("A-", "#ABB2BF") { changeFontSize(-1f) }
        val btnFontPlus  = miniBtn("A+", "#ABB2BF") { changeFontSize(+1f) }
        // Desktop Debian (proot + Xtigervnc): GUI integrat, client RFB propriu
        val btnDesktop = miniBtn("TERMINAL", "#98C379") { openTerminal() }
        // bannerul mutat din terminal in bara: ⚡ AGENT DeepSeek + linia de ajutor
        val banner = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(0, 0, dp(8), 0)
        }
        val bannerTitle = TextView(this).apply {
            text = "\u26a1 AGENT DeepSeek"
            setTextColor(Color.parseColor("#FF5F87"))   // RED (38;5;203)
            textSize = 13f
            typeface = mono
            setSingleLine(true)
            ellipsize = TextUtils.TruncateAt.END
        }
        val bannerHelp = TextView(this).apply {
            text = "Type /help"
            setTextColor(Color.parseColor("#AFAFD7"))   // G (38;5;146)
            textSize = 11f
            typeface = mono
            setSingleLine(true)
            ellipsize = TextUtils.TruncateAt.END
        }
        banner.addView(bannerTitle)
        banner.addView(bannerHelp)
        bar.addView(banner, LinearLayout.LayoutParams(0, -2, 1f))
        bar.addView(btnFontMinus, LinearLayout.LayoutParams(-2, -2))
        bar.addView(fontLabel, LinearLayout.LayoutParams(-2, -2))
        bar.addView(btnFontPlus, LinearLayout.LayoutParams(-2, -2))
        bar.addView(btnDesktop, LinearLayout.LayoutParams(-2, -2))
        root.addView(bar, LinearLayout.LayoutParams(-1, -2))    // bara sta SUS

        root.addView(scroll, LinearLayout.LayoutParams(-1, 0, 1f))
        root.addView(audioPanel, LinearLayout.LayoutParams(-1, 0, 1f))

        // ===== SCROLL =====
        // Nu mai tin niciun flag de "user a derulat". Sistemul e pur reactiv:
        // in appendAnsi verific DACA suntem acum la fund; daca da -> urmaresc generarea,
        // daca nu -> nu misc nimic. Astfel:
        //   - esti jos la fund        -> auto-scroll (urmareste generarea)
        //   - ai derulat sus          -> nu esti la fund -> rămâi unde esti
        //   - revii jos la fund       -> iar la fund -> auto-scroll reia singur
        // Touch real pe zona de text: doar atunci miscarile de scroll pot opri urmarirea.
        // Astfel, scroll-ul "artificial" generat de TextView-ul selectabil (re-layout/focus)
        // NU mai e confundat cu o derulare manuala a utilizatorului.
        scroll.setOnTouchListener { _, ev ->
            when (ev.actionMasked) {
                android.view.MotionEvent.ACTION_DOWN -> userTouching = true
                android.view.MotionEvent.ACTION_UP,
                android.view.MotionEvent.ACTION_CANCEL -> userTouching = false
            }
            false   // nu consumam evenimentul: ScrollView-ul deruleaza normal
        }

        scroll.setOnScrollChangeListener { _, _, scrollY, _, oldScrollY ->
            val h = scroll.height
            // ★ FIX 2026-10-07: cand inaltimea viewport-ului se schimba (tastatura apare/
            // dispare), ScrollView-ul isi ajusteaza SINGUR scrollY ca sa-si pastreze
            // continutul. Acel eveniment NU e o derulare a userului. Daca il tratam ca
            // atare, un "sus" automat oprea urmarirea cozii pe vecie (auto-scroll mort).
            val heightChanged = h != lastScrollHeight
            lastScrollHeight = h
            val child = scroll.getChildAt(0)
            val dist = if (child != null) child.bottom - h - scrollY else Int.MAX_VALUE
            if (!programmaticScroll && !heightChanged) {
                // Reaccionam DOAR la derularea facuta de degetul utilizatorului (userTouching).
                // Orice alta schimbare de scroll (programatica, sau cauzata de TextView-ul
                // selectabil) este ignorata -> nu mai opreste urmarirea din greseala.
                if (userTouching) {
                    if (scrollY < oldScrollY) {
                        // userul a derulat SUS -> oprim urmarirea
                        followTail = false
                    } else if (scrollY > oldScrollY && dist <= 32) {
                        // userul a derulat JOS si a ajuns (aproape) la fund -> reluam
                        followTail = true
                    }
                }
                // daca suntem EFECTIV la fund (prin orice mijloc), urmarirea reia de la sine.
                // pragul e mai generos (32px): dupa trunchierea textului (MAX_UI_CHARS) si pe
                // ecrane mici, 'dist' poate rămâne 10-25px chiar cand esti vizual la fund,
                // iar pragul vechi de 8px facea auto-scroll-ul sa "moara" fara motiv.
                if (dist <= 32) followTail = true
            }
        }

        // ★ FIX 2026-10-07 (tastatura ascunsa -> conversatia "sare" mai sus):
        // La IME HIDE, inaltimea ScrollView-ului CREȘTE, layout-ul se reface DAR scrollY
        // rămâne numeric la fel -> continutul nu mai e lipit de marginea de jos (rămâne gol
        // sub el) si, fiindca pozitia nu s-a schimbat, NU vine niciun eveniment de scroll
        // care sa re-armeze urmarirea. Re-fixam coada explicit.
        // IMPORTANT: re-fixam DOAR la crestere (ascundere tastatura). La DESCHIDERE (viewport
        // scade) NU atingem scroll-ul: acolo EditText-ul isi castiga focusul, iar un
        // fullScroll in acel moment i-l fura (bug observat: nu se mai putea scrie in input).
        scroll.addOnLayoutChangeListener { _, _, top, _, bottom, _, oldTop, _, oldBottom ->
            val grew = (bottom - top) > (oldBottom - oldTop)
            if (grew && followTail) {
                scroll.post { scrollToBottom() }
            }
        }

        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setBackgroundColor(Color.parseColor("#11151C"))
            setPadding(16, 12, 12, 12)
        }
        inputRow = row
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
        // 🔊 citeste ultimul raspuns al agentului cu voce tare (Phonon 31m, offline)
        btnSpeak = Button(this).apply {
            text = "🔊"
            textSize = 16f
            setTextColor(Color.parseColor("#98C379"))
            setBackgroundColor(Color.TRANSPARENT)
            minWidth = 0; minimumWidth = 0
            setPadding(dp(10), 0, dp(10), 0)
            setOnClickListener { speakLastAnswer() }
        }
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
        buildSetupPanel(frame)
        buildPushToTalk(frame)
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

        send.setOnClickListener { newTurn = true; inTask = false; sendLine() }
        // self-test pentru voce (adb: am start ... --ez tts_selftest true) - verifica pe device
        if (intent?.getBooleanExtra("tts_selftest", false) == true) {
            var phrase = intent.getStringExtra("tts_text") ?: "Hello from Phonon, running offline inside the agent app."
            val inFile = File(filesDir, "tts_input.txt")
            if (inFile.exists()) {
                val fromFile = inFile.readText().trim()
                if (fromFile.isNotEmpty()) phrase = fromFile
            }
            android.util.Log.i("PhononTts", "self-test text[" + phrase.length + "]: " + phrase)
            appendAnsi("[tts] self-test: $phrase\n")
            PhononTts.speak(this, phrase) { st -> appendAnsi("[tts] $st\n") }
        }
        // cerem permisiunile DUPĂ ce ecranul All-Files (deschis tot din
        // requestAllPermissions) s-a închis si activitatea e iar in fata.
        // Altfel dialogul de runtime e acoperit de Settings si se pierde.
        // ★ la PRIMA configurare afisam panoul INAINTE de cererea de permisiuni, ca userul
        //   sa vada exact ce i se cere (lista cu bife) si sa revina dupa fiecare acordare.
        // ★ BUG reparat ("ecranul sta asa, nu porneste; a durat 2 minute"):
        //   startCore() se chema DOAR daca toate permisiunile esentiale erau deja date.
        //   La o instalare curata ele nu sunt -> nu se chema nimic -> ecranul ramanea gol
        //   (fara panou, fara setup) pana cand onResume nimerea intamplator o stare buna.
        //   Acum startCore() e chemat INTOTDEAUNA; el stie sa afiseze panoul de setup
        //   si sa astepte permisiunile (blocajul e in ticker, nu aici).
        startCore()
        requestAllPermissions()
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
        // ★ FIX 2026-10-07: pornim cu inaltimea curenta cunoscuta (altfel primul eveniment
        // de scroll ar fi tratat gresit ca "schimbare de inaltime").
        scroll.post { lastScrollHeight = scroll.height }
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
            appendAnsi("\n[battery-opt] could not request the exemption: " + e.message + "\n")
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
        // UI: dimensiunea fontului terminalului (sp) + limitele ei
        private const val FONT_MIN = 10f
        private const val FONT_MAX = 30f
        private const val PREFS = "agent_ui"

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

    /** Modifica dimensiunea fontului terminalului (sp) si o salveaza. */
    private fun changeFontSize(delta: Float) {
        fontSizeSp = (fontSizeSp + delta).coerceIn(FONT_MIN, FONT_MAX)
        applyFontSize()
    }

    /** Aplica dimensiunea fontului pe terminal si o persista in preferinte. */
    private fun applyFontSize() {
        try { output.textSize = fontSizeSp } catch (_: Exception) {}
        try { fontLabel.text = fontSizeSp.toInt().toString() } catch (_: Exception) {}
        try {
            getSharedPreferences(PREFS, MODE_PRIVATE).edit()
                .putFloat("font_size", fontSizeSp).apply()
        } catch (_: Exception) {}
    }


    /** ★ Inlocuieste ULTIMA linie din terminal (pentru countdown-uri).
     *  PERFORMANTA: nu reconstruim tot textul (Ansi.toSpannable pe tot ar fi lent);
     *  stergem doar ultima linie din spannable-ul existent si adaugam linia noua. */
    // ================== ECRAN DE CONFIGURARE (prima pornire) ==================
    // Design: panou propriu peste terminal, cu progres REAL si permisiuni bifate live.
    // Inlocuieste countdown-ul orb de 30s care scria in terminal cu lastLine() (liniile
    // se stergeau una dupa alta -> haos). Countdown-ul EXISTA in continuare ca fereastra
    // de timp pentru acordarea permisiunilor, dar se termina imediat ce toate sunt date.

    private var setupPanel: LinearLayout? = null
    private var setupProgress: ProgressBar? = null
    private var setupStatus: TextView? = null
    private var setupStepRows: LinkedHashMap<String, TextView> = LinkedHashMap()
    private var setupPermRows: LinkedHashMap<String, TextView> = LinkedHashMap()
    private var setupDeadline: Long = 0L
    private var setupWarning: TextView? = null
    private var btnGrantAll: Button? = null
    private var setupTickerDone = true
    private var setupFinished = false
    private var readyAnnounced = false

    private val COLOR_BG = "#0D1117"
    private val COLOR_CARD = "#11161D"
    private val COLOR_TEXT = "#C8CDD4"
    private val COLOR_DIM = "#5C6370"
    private val COLOR_ACCENT = "#61AFEF"
    private val COLOR_OK = "#98C379"
    private val COLOR_WARN = "#E5C07B"
    private val COLOR_ERR = "#E06C75"

    /** Permisiunile cerute la prima configurare: (eticheta afisata, permisiune manifest). */
    private fun essentialPermList(): List<Pair<String, String>> = listOf(
        "Camera" to Manifest.permission.CAMERA,
        "Microphone" to Manifest.permission.RECORD_AUDIO,
        "Location" to Manifest.permission.ACCESS_FINE_LOCATION,
        "Contacts" to Manifest.permission.READ_CONTACTS,
        "Photos & media" to Manifest.permission.READ_MEDIA_IMAGES,
        "Notifications" to Manifest.permission.POST_NOTIFICATIONS
    )

    private fun permGranted(perm: String): Boolean =
        ContextCompat.checkSelfPermission(this, perm) == PackageManager.PERMISSION_GRANTED

    private fun allFilesOk(): Boolean =
        if (Build.VERSION.SDK_INT >= 30) Environment.isExternalStorageManager() else true

    private fun buildSetupPanel(frame: FrameLayout) {
        val card = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.parseColor(COLOR_CARD))
            setPadding(dp(26), dp(34), dp(26), dp(26))
            visibility = View.GONE
        }
        val title = TextView(this).apply {
            text = "\u26A1  AGENT"
            textSize = 22f
            typeface = android.graphics.Typeface.DEFAULT_BOLD
            setTextColor(Color.parseColor(COLOR_ACCENT))
            letterSpacing = 0.08f
        }
        val subtitle = TextView(this).apply {
            text = "First-time setup"
            textSize = 14f
            setTextColor(Color.parseColor(COLOR_DIM))
            setPadding(0, dp(4), 0, dp(10))
        }
        // ★ cerut de operator: mesaj de calmare, rosu, sub subtitlu
        val relax = TextView(this).apply {
            text = "Please wait, take a coffee and relax\u2026"
            textSize = 13f
            typeface = mono
            setTextColor(Color.parseColor(COLOR_ERR))
            setPadding(0, 0, 0, dp(18))
        }
        setupProgress = ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal).apply {
            max = 100; progress = 0
            progressTintList = android.content.res.ColorStateList.valueOf(Color.parseColor(COLOR_ACCENT))
            progressBackgroundTintList = android.content.res.ColorStateList.valueOf(Color.parseColor("#1C2333"))
        }
        setupStatus = TextView(this).apply {
            text = "Waiting for permissions\u2026"
            textSize = 13f
            typeface = mono
            setTextColor(Color.parseColor(COLOR_TEXT))
            setPadding(0, dp(12), 0, dp(20))
        }
        card.addView(title)
        card.addView(subtitle)
        card.addView(relax)
        card.addView(setupProgress, LinearLayout.LayoutParams(-1, dp(6)))
        card.addView(setupStatus)

        // ---- secțiunea permisiuni ----
        card.addView(sectionLabel("PERMISSIONS"))
        for ((label, perm) in essentialPermList()) {
            addRow(card, setupPermRows, label) { permGranted(perm) }
        }
        addRow(card, setupPermRows, "All files access") { allFilesOk() }

        // ---- secțiunea etape de setup (se populează la pornire) ----
        card.addView(sectionLabel("STARTUP"))

        card.addView(LinearLayout(this))  // spacer flexibil in jos
        // ★ Avertisment: setup-ul NU porneste fara TOATE permisiunile (cerinta operator).
        setupWarning = TextView(this).apply {
            visibility = View.GONE
            textSize = 13f
            typeface = mono
            setTextColor(Color.parseColor(COLOR_ERR))
            setPadding(0, 0, 0, dp(10))
        }
        card.addView(setupWarning)
        // ★ Butonul GRANT ALL PERMISSIONS: apare dupa expirarea ferestrei de 30s.
        //   Reia cererea de permisiuni pana cand TOATE sunt acordate. Fara el, setup-ul
        //   nu porneste NICIODATA (obligatie, nu optiune).
        btnGrantAll = Button(this).apply {
            text = "GRANT ALL PERMISSIONS"
            textSize = 13f
            isAllCaps = false
            typeface = mono
            setTextColor(Color.parseColor("#0D1117"))
            setBackgroundColor(Color.parseColor(COLOR_ACCENT))
            setPadding(dp(18), dp(10), dp(18), dp(10))
            visibility = View.GONE
            setOnClickListener { grantAllPermissions() }
        }
        card.addView(btnGrantAll, LinearLayout.LayoutParams(-1, -2))
        setupPanel = card
        val lp = FrameLayout.LayoutParams(-1, -1)
        frame.addView(card, lp)
    }

    private fun sectionLabel(text: String): TextView = TextView(this).apply {
        this.text = text
        textSize = 11f
        typeface = mono
        setTextColor(Color.parseColor(COLOR_DIM))
        letterSpacing = 0.12f
        setPadding(0, dp(6), 0, dp(8))
    }

    /** Rând de stare: cerculet, eticheta, valoare. Se actualizează in loc. */
    private fun addRow(
        parent: LinearLayout,
        map: LinkedHashMap<String, TextView>,
        label: String,
        check: () -> Boolean
    ): TextView {
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setPadding(0, dp(5), 0, dp(5))
            gravity = Gravity.CENTER_VERTICAL
        }
        val dot = TextView(this).apply {
            text = "\u25CB"
            textSize = 15f
            setTextColor(Color.parseColor(COLOR_DIM))
            width = dp(26)
        }
        val name = TextView(this).apply {
            text = label
            textSize = 14f
            typeface = mono
            setTextColor(Color.parseColor(COLOR_TEXT))
        }
        row.addView(dot)
        row.addView(name)
        parent.addView(row)
        val holder = object : TextView(this) {}.apply { visibility = View.GONE }
        row.addView(holder)
        map[label] = dot
        return dot
    }

    /** Reîmprospătează bifele de permisiuni + textul de status. */
    private fun refreshSetupPanel() {
        if (setupFinished) return
        val missing = mutableListOf<String>()
        for ((label, perm) in essentialPermList()) {
            val ok = permGranted(perm)
            setupPermRows[label]?.let { setDot(it, ok) }
            if (!ok) missing.add(label)
        }
        val filesOk = allFilesOk()
        setupPermRows["All files access"]?.let { setDot(it, filesOk) }
        if (!filesOk) missing.add("All files access")

        val st = setupStatus ?: return
        val left = ((setupDeadline - System.currentTimeMillis()) / 1000L).coerceAtLeast(0L)
        // bara reflecta permisiunile acordate (7 = toate), apoi trece pe etapele de setup
        val total = essentialPermList().size + 1
        val done = total - missing.size
        setupProgress?.progress = (done * 100 / total)
        if (missing.isEmpty()) {
            st.text = "All permissions granted \u2014 starting\u2026"
            st.setTextColor(Color.parseColor(COLOR_OK))
        } else {
            st.text = "Waiting for " + missing.size + " permission(s) \u2014 " + left + "s"
            st.setTextColor(Color.parseColor(if (left < 10) COLOR_WARN else COLOR_TEXT))
        }
    }

    private fun setDot(v: TextView, ok: Boolean) {
        v.text = if (ok) "\u2713" else "\u25CB"
        v.setTextColor(Color.parseColor(if (ok) COLOR_OK else COLOR_DIM))
    }

    /** Afișează panoul și pornește fereastra de permisiuni. */
    private fun showSetupPanel() {
        setupFinished = false
        setupPanel?.visibility = View.VISIBLE
        startSetupTicker()
    }

    /** Porneste fereastra de 30s + reimprospatarea bifelelor (idempotent). */
    private fun startSetupTicker() {
        if (setupTickerDone == false) return   // deja ruleaza
        setupDeadline = System.currentTimeMillis() + 30_000L
        setupTickerDone = false
        refreshSetupPanel()
        val h = android.os.Handler(android.os.Looper.getMainLooper())
        val tick = object : Runnable {
            override fun run() {
                if (setupTickerDone || setupFinished) return
                refreshSetupPanel()
                val missing = essentialPermList().any { !permGranted(it.second) } || !allFilesOk()
                if (!missing) {
                    // toate date -> nu mai așteptăm cele 30s
                    finishSetupPanel()
                    return
                }
                if (System.currentTimeMillis() >= setupDeadline) {
                    // WINDOW EXPIRED WITHOUT ALL PERMISSIONS: setup does NOT start.
                    // Show WARNING + GRANT ALL PERMISSIONS; setup is OBLIGATORILY gated.
                    setupTickerDone = true
                    val miss = essentialPermList().filter { !permGranted(it.second) }
                        .map { it.first }.toMutableList()
                    if (!allFilesOk()) miss.add("All files access")
                    setupWarning?.let { w ->
                        w.visibility = View.VISIBLE
                        w.text = "\u26A0 WARNING: " + miss.size + " permission(s) not granted.\n" +
                                 "Setup CANNOT start until ALL are granted:\n" +
                                 miss.joinToString(", ")
                    }
                    setupStatus?.text = "Blocked \u2014 grant all permissions to continue"
                    setupStatus?.setTextColor(Color.parseColor(COLOR_ERR))
                    btnGrantAll?.visibility = View.VISIBLE
                    return
                }
                h.postDelayed(this, 700)
            }
        }
        h.postDelayed(tick, 700)
    }

    /** ★ Cerinta operator: butonul reia cererea de permisiuni PANA CAND toate sunt date.
     *  Setup-ul nu porneste fara ele - e obligatie, nu optiune. */
    private fun grantAllPermissions() {
        val need = essentialPermList().map { it.second }
            .filter { ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED }
        if (need.isNotEmpty()) {
            // Some were permanently denied ("Don't ask again") -> Android gives no dialog.
            // In that case open the app's settings page so the user can toggle them.
            // daca vreo permisiune e refuzata definitiv (USER_FIXED), Android nu mai arata
            // dialogul -> deschidem DIRECT ecranul de setari al aplicatiei
            val firstTime = getSharedPreferences(PREFS, MODE_PRIVATE)
                .getBoolean("grant_retry", false)
            if (firstTime) {
                try {
                    startActivity(android.content.Intent(
                        android.provider.Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
                        android.net.Uri.parse("package:$packageName")))
                } catch (_: Exception) {}
            } else {
                getSharedPreferences(PREFS, MODE_PRIVATE).edit().putBoolean("grant_retry", true).apply()
            }
            ActivityCompat.requestPermissions(this, need.toTypedArray(), 1)
            return
        }
        // runtime permissions done -> All files access is a system Settings screen
        if (!allFilesOk()) {
            requestAllFilesAccess()
            return
        }
        // everything granted -> restart the window and let the ticker start setup
        getSharedPreferences(PREFS, MODE_PRIVATE).edit().putBoolean("grant_retry", false).apply()
        setupWarning?.visibility = View.GONE
        btnGrantAll?.visibility = View.GONE
        setupTickerDone = true
        startSetupTicker()
    }

    private fun finishSetupPanel() {
        setupFinished = true
        setupTickerDone = true
        // ★ BUG reparat: inainte, runSetup() era chemat in withEndAction() al animatiei,
        //   care NU se executa daca view-ul nu are inca un parinte/layout valid (sau daca
        //   animatia e anulata) -> panoul disparea si setup-ul nu pornea NICIODATA
        //   ("dupa ce expira secundele nu functioneaza"). Acum setup-ul porneste
        //   necondiionat, iar ascunderea panoului e independenta.
        // ★ Panoul ramane VIZIBIL cat timp setup-ul ruleaza (arată etapele cu bife),
        //   si se ascunde abia cand ultima etapa s-a terminat. Inainte era ascuns
        //   dupa 200 ms -> operatorul nu vedea nimic, doar terminalul gol.
        runSetup()
    }

    /** Ascunde panoul de configurare (la finalul setup-ului sau la eroare). */
    private fun hideSetupPanel() {
        setupPanel?.let {
            it.animate().alpha(0f).setDuration(220).start()
            it.postDelayed({ it.visibility = View.GONE; it.alpha = 1f }, 260)
        }
    }

    /** O etapă de setup: apare o singura data, isi schimba doar starea. FARA stergeri. */
    private fun setupStep(label: String, state: String) {
        runOnUiThread {
            val card = setupPanel ?: return@runOnUiThread
            var dot = setupStepRows[label]
            if (dot == null) {
                dot = addRow(card, setupStepRows, label) { false }
            }
            when (state) {
                "run" -> { dot.text = "\u25CF"; dot.setTextColor(Color.parseColor(COLOR_ACCENT)) }
                "ok"  -> { dot.text = "\u2713"; dot.setTextColor(Color.parseColor(COLOR_OK)) }
                "err" -> { dot.text = "\u2717"; dot.setTextColor(Color.parseColor(COLOR_ERR)) }
            }
            val total = 6f
            val done = setupStepRows.values.count { it.text == "\u2713" }.toFloat()
            setupProgress?.progress = (10 + (done / total) * 90f).toInt()
        }
    }

    /** 🔊 citeste cu voce tare ultimul raspuns al agentului (Phonon 31m, offline, in app). */
    private fun speakLastAnswer() {
        if (PhononTts.isBusy()) { PhononTts.cancel(); toast("voice stopped"); return }
        val text = PhononTts.cleanText(lastAnswer.toString().trim())
        if (text.isEmpty()) { toast("nothing to read"); return }
        PhononTts.speak(this, text) { st -> runOnUiThread { if (!isFinishing) btnSpeak.text = if (st.startsWith("gata") || st.startsWith("eroare")) "🔊" else "…" } }
        toast("reading ${text.length} characters")
    }

    private fun toast(m: String) {
        runOnUiThread { android.widget.Toast.makeText(this, m, android.widget.Toast.LENGTH_SHORT).show() }
    }

    private fun lastLine(s: String) {
        try {
            val cur = output.text
            val sb = if (cur is android.text.SpannableStringBuilder) cur else android.text.SpannableStringBuilder(cur)
            val idx = sb.toString().lastIndexOf("\n")
            if (idx >= 0) sb.delete(idx, sb.length) else sb.clear()
            sb.append(Ansi.toSpannable(s))
            output.text = sb
        } catch (_: Exception) {}
        scrollToBottom()
    }

    fun appendAnsi(s: String) {
        // siguranta: apelat si din thread-uri de fundal (vocea) -> orice atingere de view
        // trebuie sa se faca pe thread-ul principal
        if (android.os.Looper.myLooper() != android.os.Looper.getMainLooper()) {
            runOnUiThread { appendAnsi(s) }
            return
        }
        // ★ FIX 2026-10-06: masuram DACA eram la fund INAINTE de a adauga textul.
        // Dupa append, contentH creste (cu o linie intreaga) -> un atBottom() facut DUPA
        // ar returna fals (dist = lineHeight > 32) si nu ar mai re-arma urmarirea.
        val wasAtBottom = atBottom()
        // /audio: cat timp modul audio e ARMAT, nimic din ce vine de la agent nu se afiseaza
        // in terminal, cu exceptia liniilor de infrastructura ([...]) pe care le lasam sa curga.
        val cleanForHide = s.replace(Regex("\\u001B\\[[0-9;?]*[a-zA-Z]"), "").trim()
        // In modul audio ascundem TOT ce vine de la agent (mai putin liniile de
        // infrastructura [xxx]), ca operatorul sa vada doar sunetul, nu tool-urile.
        val hideForAudio = audioNext && cleanForHide.isNotEmpty() && !cleanForHide.startsWith("[")
        if (!hideForAudio) output.append(Ansi.toSpannable(s))
        // 🔊: acumulez DOAR liniile care par raspunsul agentului (proza), nu zgomotul de
        // infrastructura (self-heal, adb, term, setup) care umplea citirea vocala.
        val plain = s.replace(Regex("\\u001B\\[[0-9;?]*[a-zA-Z]"), "")
            .replace(Regex("\\u001B\\][^\u0007]*\u0007"), "")
            .trim()
        // 🔊 Citim DOAR raspunsul din ULTIMUL task. Marcajele reale ale agentului:
        //   " You > ..."  (mesajul utilizatorului)
        //   "╭────╮ │ TASK #1 │ ╰────╯"  (inceput de task)
        //   "AGENT >"     (urmeaza raspunsul)
        //   "  +-  #1 done · 0 tools, 1 rnd"  (footer, termina raspunsul)
        // Tot ce nu e intre "AGENT >" si footer (self-heal, adb, term, setup) e ignorat.
        val t = plain.trim()
        if (audioNext && Regex("#\\d+\\s+(done|interrupted)").containsMatchIn(t)) {
            // task terminat in modul audio: rostim raspunsul, fara sa-l afisam
            val say = audioText.toString().trim()
            // mod persistent: audioNext rămâne true daca audioMode e pornit; altfel se consuma
            audioNext = audioMode
            inTask = false; inAgent = false
            android.util.Log.i("PhononTts", "audio finish: " + say.length + " car. -> speak")
            if (say.isNotEmpty()) {
                if (userTalking) { audioStatus("Ready - just type."); audioText.setLength(0); return }
                PhononTts.speak(this, say) { st ->
                    android.util.Log.i("PhononTts", st)
                    if (audioMode) {
                        // afisez doar mesaje scurte si utile, nu detalii tehnice
                        val show = when {
                            st.startsWith("preparing") -> "Loading voice..."
                            st.startsWith("playing")   -> "Speaking..."
                            st.startsWith("done")      -> "Ready - just type."
                            st.startsWith("error")     -> st
                            st.startsWith("nothing")   -> "Ready - just type."
                            else -> null
                        }
                        if (show != null) audioStatus(show)
                    }
                }
            } else {
                android.util.Log.w("PhononTts", "audio finish: empty text, nothing to speak")
            }
            audioText.setLength(0)   // urmatorul raspuns porneste curat
        }
        // ce face agentul ACUM: linia lui de pas "+-- step 02 [bash] lists files  ⏱3s"
        // (in modul audio nu vede terminalul, deci ii aratam pasul pe ecranul de voce)
        if (audioMode && audioNext) {
            val sm = Regex("""step\s+(\d+)\s+\[(\w+)]\s*(.*?)\s*(?:\u23f1.*)?$""").find(t)
            if (sm != null) {
                val what = sm.groupValues[3].trim().take(90)
                audioWork("step ${sm.groupValues[1]}  ${sm.groupValues[2]}" + if (what.isEmpty()) "" else " - $what")
            }
        }
        if (t.contains("TASK #") || (t.contains("\u256D") && !inTask)) {
            inTask = true; newTurn = false; inAgent = false; lastAnswer.setLength(0)
            if (audioNext) { audioText.setLength(0); audioWork("working - thinking about your request") }
        } else if (inTask && Regex("#\\d+\\s+(done|interrupted)").containsMatchIn(t)) {
            inTask = false; inAgent = false
        } else if (inTask && Regex("^\\s*AGENT\\s*>\\s*$").containsMatchIn(t)) {
            inAgent = true
            audioWork("reply ready - preparing the voice")
        } else if (inTask && inAgent && t.isNotEmpty()) {
            // modul audio: adunam DOAR textul raspunsului (dupa "AGENT >"), nu tool-urile
            if (audioNext) audioText.append(t).append(' ')
        }
        if (false) {
            if (!isInfra(t)) {
                lastAnswer.append(t).append('\n')
                if (lastAnswer.length > ANSWER_CAP) lastAnswer.delete(0, lastAnswer.length - ANSWER_CAP)
            }
        }
        // PERFORMANTA: TextView-ul creste nelimitat -> la revenirea din background
        // Android re-layout-uieste TOT textul (ecran negru + lag). Tinem doar ultimele
        // MAX_UI_CHARS caractere, taiind din cap (spannable-ul ramane mic si rapid).
        var truncated = false
        try {
            val cur = output.text
            if (cur.length > MAX_UI_CHARS) {
                val keep = cur.subSequence(cur.length - MAX_UI_KEEP, cur.length)
                output.text = android.text.SpannableStringBuilder(keep)
                truncated = true
            }
        } catch (_: Exception) {}

        // butonul STOP: il ascund cand taskul s-a terminat
        if (btnStop.visibility == View.VISIBLE && (s.contains("TASK #") && (s.contains("done") || s.contains("interrupted")))) {
            btnStop.visibility = View.GONE
            setTaskScreenOn(false)
        }

        // ★ FIX 2026-10-06: daca textul a fost TRUNCHIAT, pozitia de scroll se reseteaza
        // (output.text e inlocuit) -> daca urmaream coada, ne asezam imediat la fund ca sa
        // nu rămâne continutul sub marginea de jos dupa trunchiere.
        if (truncated) scrollToBottom(force = true)

        // ★ FIX 2026-10-06 (auto-scroll "moare" si nu se mai re-arma):
        // Re-armam urmarirea cozii daca suntem EFECTIV la fund. Inainte re-armarea se
        // facea DOAR in listener-ul de scroll - dar daca scroll-ul era blocat (nimic nu
        // se misca) nu mai venea niciun eveniment -> followTail rămânea false pe vecie
        // si textul curgea sub marginea de jos. Acum verificam activ la fiecare text nou.
        if (!followTail && !programmaticScroll && wasAtBottom) followTail = true

        // urmarim coada DOAR daca userul nu a derulat manual in sus (followTail).
        // Daca a derulat sus, textul nou creste SUB pozitia lui, fara sa-l miste.
        if (followTail) scrollToBottom()
    }

    /** ★ true daca suntem (aproape) la fundul listei (dist <= 32px). */
    private fun atBottom(threshold: Int = 32): Boolean {
        val child = scroll.getChildAt(0) ?: return true
        val dist = child.bottom - scroll.height - scroll.scrollY
        return dist <= threshold
    }

    /** ★ Deruleaza la fund DUPA ce TextView-ul si-a recalculat inaltimea.
     *  Inainte se facea un singur scroll.post { fullScroll } - dar la pasul acela
     *  TextView-ul putea sa NU fi terminat layout-ul, deci fullScroll ajungea la
     *  fundul VECHI -> textul nou ramanea sub marginea de jos (auto-scroll "rupt").
     *  Acum: (1) post imediat, (2) al doilea post dupa layout, (3) un retry scurt.
     *  programmaticScroll se elibereaza dupa ce layout-ul s-a linistit, nu dupa un
     *  timp fix care putea expira prea devreme pe text mare/ANSI. */
    private fun scrollToBottom(force: Boolean = false) {
        // force=true: ignoram guard-ul followTail (folosit dupa TRUNCHIERE, cand textul
        // e inlocuit si pozitia se reseteaza - altfel continutul rămânea sub margine).
        if (!followTail && !force) return
        programmaticScroll = true
        val doScroll = Runnable {
            if (!followTail && !force) return@Runnable
            pinToBottom()
        }
        scroll.post(doScroll)
        output.post(doScroll)               // dupa ce TextView-ul e re-layoutat
        scroll.postDelayed(doScroll, 32)    // a doua sansa (text greu/ANSI)
        scroll.postDelayed({
            // eliberam abia dupa ce layout-ul s-a asezat; thencorectam si deriva
            if (followTail || force) pinToBottom()
            scroll.postDelayed({ programmaticScroll = false }, 32)
        }, 96)
    }

    /** ★ FIX 2026-10-07 (focus): deruleaza la fund FARA sa atinga focusul.
     *  ScrollView.fullScroll(FOCUS_DOWN) foloseste intern scrollAndFocus() ->
     *  findFocusableViewInBounds() -> requestFocus() pe primul view focusabil de la
     *  interior. TextView-ul terminalului e focusabil (setTextIsSelectable(true)), asa ca
     *  acel requestFocus FURA focusul de pe EditText-ul de input; IME-ul rămâne atasat de
     *  TextView si userul NU MAI POATE SCRIE (simptom real raportat).
     *  scrollTo() nu atinge deloc focusul -> nu mai fura nimic. */
    private fun pinToBottom() {
        val child = scroll.getChildAt(0) ?: return
        val max = (child.height - scroll.height).coerceAtLeast(0)
        scroll.scrollTo(0, max)
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
            appendAnsi("\u001B[38;5;208m[stop] interrupt sent (SIGINT)...\u001B[0m\n")
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
        // ★ Revenirea in prim-plan (din dialoguri de permisiuni / Settings / All files access)
        //   e singurul moment in care putem sti ca userul a schimbat ceva. Verificam o
        //   singura data, centralizat, si pornim setup-ul daca totul e acordat.
        if (!setupDone()) {
            root.postDelayed({ onPermissionsMaybeComplete() }, 250)
        }
        // ★ La revenirea in prim-plan, Android re-layoutuieste tot TextView-ul (poate dura):
        // daca urmaream coada, ne asezam la fund DUPA layout, nu inainte.
        if (followTail) {
            scroll.postDelayed({ if (followTail) scrollToBottom() }, 120)
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
                    // ★ NU raporta "lipseste" cat timp prima configurare e IN CURS: extractia
                    //   stdlib-ului (1688 fisiere) + pornirea Python dureaza zeci de secunde,
                    //   iar mesajul de watchdog aparea INAINTE de "[extract]" si nelinistea
                    //   operatorul ("procesul python lipseste" chiar cand el se instala).
                    val stillSettingUp = !setupDone() || (pythonLaunching && (now - pythonStartRequestedAt) < 180000L)
                    if (k != null && coreStarted && !awaitingKey && !stillSettingUp &&
                        (now - lastPythonStart) > 20000L) {
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

    /** ★ AUTO-REACTIVARE ACCESIBILITATE (cerut de operator).
     *
     * De ce: la FIECARE reinstalare de APK, Android reseteaza permisiunile speciale ->
     * `enabled_accessibility_services` devine null, iar serviciul AgentAccessibilityService
     * nu se mai leaga. Efect: agentul pierde screenshot-ul si controlul UI. Pana acum se
     * reactiva MANUAL (de 3 ori intr-o sesiune).
     *
     * Cum: avem WRITE_SECURE_SETTINGS in manifest; cand e acordata (`pm grant` o singura data),
     * putem scrie cheile Secure direct. Scriem lista serviciilor + flagul enabled, apoi lasam
     * sistemul ~600 ms sa faca bind-ul.
     *
     * Fara permisiune: nu incercam (nu aruncam), scriem o linie cu instructiunea `pm grant`.
     * @return true daca serviciul e activ (bound) la sfarsit.
     */
    private fun ensureAccessibility(): Boolean {
        // deja activ? atunci nu atingem nimic (idempotent)
        if (net.sys32.agent.AgentAccessibilityService.instance != null) return true
        val me = net.sys32.agent.AgentAccessibilityService::class.java
        val want = packageName + "/" + me.name
        val cr = contentResolver
        // permisiunea speciala acordata?
        val canWrite = checkSelfPermission(
            "android.permission.WRITE_SECURE_SETTINGS") == PackageManager.PERMISSION_GRANTED
        if (!canWrite) {
            // ★ Daca avem cheia autorizata a operatorului (op_adbkey), Python-ul poate da
            // `pm grant` SINGUR prin adb local (uid 2000) -> NU mai alarmam operatorul cu un
            // mesaj de eroare care oricum dispare 20s mai tarziu. Asteptam in liniste si
            // lasam a11y_selfheal() din agent.py sa repare (ruleaza la pornirea python-ului).
            val hasOpKey = java.io.File(filesDir, "op_adbkey").exists()
            if (hasOpKey) return false
            return try {
                appendAnsi("\u001b[38;5;214m[a11y] accessibility is OFF and WRITE_SECURE_SETTINGS is not granted.\u001b[0m\n" +
                    "\u001b[38;5;243m      grant it once via adb:  pm grant " + packageName +
                    " android.permission.WRITE_SECURE_SETTINGS\u001b[0m\n" +
                    "\u001b[38;5;243m      (or copy the authorised key to files/op_adbkey for automatic repair)\u001b[0m\n")
                false
            } catch (_: Exception) { false }
        }
        return try {
            val cur = android.provider.Settings.Secure.getString(
                cr, android.provider.Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES) ?: ""
            // lista e separata prin ':' - adaugam al nostru doar daca lipseste
            val set = cur.split(":").filter { it.isNotBlank() }.toMutableSet()
            val changed = set.add(want)
            if (changed) {
                android.provider.Settings.Secure.putString(cr,
                    android.provider.Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES,
                    set.joinToString(":"))
            }
            android.provider.Settings.Secure.putInt(cr,
                android.provider.Settings.Secure.ACCESSIBILITY_ENABLED, 1)
            try {
                appendAnsi("\u001b[38;5;110m[a11y] accessibility re-enabled automatically (" +
                    (if (changed) "added to list" else "already listed") + ")\u001b[0m\n")
            } catch (_: Exception) {}
            true
        } catch (e: Exception) {
            try { appendAnsi("\u001b[38;5;203m[a11y] could not enable: " + e.message + "\u001b[0m\n") }
            catch (_: Exception) {}
            false
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
    /** Deschide terminalul LINUX real (bash in Debian prin pty). */
    fun openTerminal() {
        try {
            startActivity(Intent(this, LinuxTerminalActivity::class.java))
        } catch (e: Exception) {
            appendAnsi("\n[terminal] cannot open: ${e.message}\n")
        }
    }

    private fun startCore() {
        if (coreStarted) return
        coreStarted = true
        startWatchdog()
        ensureAccessibility()   // ★ reactivarea automata a serviciului (reinstalarea il reseta)

        // ★ cerut de operator: mesaj VIZIBIL IMEDIAT la deschiderea aplicatiei, INAINTE de orice
        // munca grea (extragerea assets + pornirea procesului python pot dura zeci de secunde -
        // abia acolo ruleaza self-heal-ul, deci fara linia asta operatorul nu vede nimic si nu
        // stie ca aplicatia isi verifica/vindeca mediul). Self-heal-ul ruleaza apoi SINGUR, in
        // fundal (la pornirea python-ului, in alt thread), iar rezultatul lui apare tot aici:
        // verde = a reparat, gri = nimic de reparat, rosu = a rămas rupt.
        try {
            val BLUE = "\u001b[38;5;110m"
            val GRY = "\u001b[38;5;243m"
            val NRM = "\u001b[0m"
            appendAnsi(BLUE + "[self-heal] in progress, please wait" + GRY +
                " - checking the environment (launchers, packages, toolchain)" + NRM + "\n")
            // ★ Provisioning-ul Debian + binder ruleaza la PRIMA DESCHIDERE A TERMINALULUI
            // si scrie EXCLUSIV in terminal (cerinta operator: fara zgomot in fereastra
            // principala, sub "AGENT DeepSeek").
        } catch (_: Exception) {}

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

        // ★ ECRAN DE CONFIGURARE dedicat (nu mai scriem countdown in terminal: lastLine()
        //   stergea ultima linie la fiecare secunda -> text care se zbate, fara ierarhie).
        //   Fereastra de 30s pentru permisiuni EXISTA in continuare (fara ea setup-ul crapa),
        //   dar se inchide IMEDIAT ce toate permisiunile sunt acordate. Etapele reale de
        //   setup se marcheaza pe rand, o singura data, fara stergeri.
        showSetupPanel()
    }

    /** Configurarea reala (dupa fereastra de permisiuni): extract + bridge + python + serviciu. */
    @Volatile private var runSetupStarted = false

    private fun runSetup() {
        // ★ idempotent: onResume + finishSetupPanel pot chema amandoua -> setup-ul rula de
        //   DOUA ori (de aici "Ready." de doua ori si doua procese Python).
        if (runSetupStarted) return
        runSetupStarted = true
        Thread {
            setupStep("Environment", "run")
            try {
                extractAssets(); setupStep("Environment", "ok")
            } catch (e: Exception) {
                setupStep("Environment", "err")
            }
            setupStep("Libraries", "run")
            try {
                verifyStdlibInstalled(); setupStep("Libraries", "ok")
            } catch (_: Exception) { setupStep("Libraries", "err") }
            setupStep("Bridge", "run")
            try {
                bridge = AndroidBridge(this, File(filesDir, "bridge.sock"))
                bridge!!.start(); setupStep("Bridge", "ok")
            } catch (e: Exception) { setupStep("Bridge", "err") }
            runOnUiThread {
                setupStep("Agent", "run")
                try { startPythonIfKey() } catch (e: Exception) {
                    appendAnsi("\u001b[38;5;203m[start] " + e + "\u001b[0m\n")
                }
                startAgentService()
                setupStep("Agent", "ok")
                requestIgnoreBatteryOptimizations()
                if (!readyAnnounced && setupStepRows.values.all { it.text == "\u2713" }) {
                    readyAnnounced = true
                    appendAnsi("\n\u001b[38;5;114mReady.\u001b[0m\n\n")
                    // setup complet -> ascundem panoul si lasam terminalul
                    android.os.Handler(android.os.Looper.getMainLooper())
                        .postDelayed({ hideSetupPanel() }, 900)
                }
            }
        }.start()
    }

    /** Confirma ca stdlib-ul Python e complet pe disc (nu doar ca s-a copiat). */
    private fun verifyStdlibInstalled() {
        val base = File(filesDir, "pyhome/lib/python3.14")
        val need = listOf("threading.py", "encodings/__init__.py", "os.py")
        val t0 = System.currentTimeMillis()
        while (System.currentTimeMillis() - t0 < 90_000L) {
            if (need.all { File(base, it).exists() }) return
            try { Thread.sleep(150) } catch (_: Exception) { return }
        }
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
            // ★ BUG reparat ("ecranul sta asa, nu porneste pasul urmator"): aici NU se chema
            //   nimic pentru pornirea setup-ului. Dupa ce userul acorda permisiunile, panoul
            //   ramanea pe loc si setup-ul nu pleca niciodata. Acum pornim explicit.
            root.postDelayed({ onPermissionsMaybeComplete() }, 900)
        }
        if (requestCode == 2) {
            // dupa raspunsul la BACKGROUND, cerem All-Files
            root.postDelayed({ requestAllFilesAccess() }, 500)
            root.postDelayed({ onPermissionsMaybeComplete() }, 1200)
        }
    }

    /** ★ Porneste setup-ul cand toate permisiunile esentiale sunt acordate (idempotent). */
    private fun onPermissionsMaybeComplete() {
        if (setupDone()) return
        val allOk = essentialPermList().all { permGranted(it.second) }
        if (!allOk) { refreshSetupPanel(); return }
        setupWarning?.visibility = View.GONE
        btnGrantAll?.visibility = View.GONE
        if (!coreStarted) {
            startCore()
        } else if (!runSetupStarted) {
            setupTickerDone = true
            finishSetupPanel()
        }
    }

    // FIX 5: cere consimtamantul MediaProjection (o singura data) si porneste
    // ScreenCaptureService, care da captura continua de ecran.
    private val CAPTURE_REQ = 9001
    fun requestScreenCapture() {
        try {
            val mpm = getSystemService(MEDIA_PROJECTION_SERVICE) as android.media.projection.MediaProjectionManager
            startActivityForResult(mpm.createScreenCaptureIntent(), CAPTURE_REQ)
        } catch (e: Exception) { appendAnsi("\n[capture] error: $e\n") }
    }

    @Deprecated("Deprecated in Java")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == CAPTURE_REQ && resultCode == RESULT_OK && data != null) {
            try {
                ScreenCaptureService.start(this, resultCode, data)
                // corect: consimtamantul e acordat si sesiunea PORNESTE ACUM.
                // (nu scriem "activ permanent" - se inchide singura dupa 3 min inactivitate)
                appendAnsi("\n[capture] MediaProjection started (auto-stops after 3 min without captures)\n")
            } catch (e: Exception) { appendAnsi("\n[capture] start error: $e\n") }
        }
        if (requestCode == VPN_REQ && resultCode == RESULT_OK) {
            try { startService(Intent(this, AgentVpn::class.java)); appendAnsi("\n[vpn] consimtamant acordat\n") } catch (_: Exception) {}
        }
    }

    private fun assetsStampValue(): String {
        return try {
            val pi = packageManager.getPackageInfo(packageName, 0)
            "${pi.longVersionCode}-${pi.lastUpdateTime}"
        } catch (_: Exception) { "unknown" }
    }

    private fun extractAssets() {
        val dest = File(filesDir, "python")
        // ★ FIX (bug raportat de agent: "fix-urile din sursa nu ajung pe device"): stampila de
        // assets NU mai e un nume HARDCODAT (era ".assets_v257", un numar pe care trebuia sa-l
        // bumpezi manual la fiecare modificare de cod python). Acum valoarea vine din APK-ul
        // insusi (versionCode + lastUpdateTime): orice update de APK re-extrage automat codul
        // python (agent.py, android_build.py...), iar daca APK-ul e neschimbat nu se re-extrage.
        val stamp = File(filesDir, ".assets_stamp")
        val want = assetsStampValue()
        val legacy = File(filesDir, ".assets_v257")
        // memoria pe termen lung a agentului NU face parte din APK: o salvam
        // inainte de re-extragere si o punem la loc, ca update-urile de app sa
        // nu stearga ce a invatat agentul de la operator.
        val memFile = File(dest, "memory.md")
        val memSaved = if (memFile.exists()) memFile.readText() else null
        val current = try { if (stamp.exists()) stamp.readText() else "" } catch (_: Exception) { "" }
        if (current == want && dest.exists() && !legacy.exists()) return
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
        // ★ BUG reparat ("agentul isi da restart singur"): aici se stergea pyhome LA FIECARE
        //   apel al extractAssets(). Dar extractAssets() e chemat din startCore() (prima
        //   configurare) SI din ramura setupDone() (fiecare pornire) -> dupa ce Python pornea
        //   cu stdlib-ul din pyhome, un al doilea extractAssets il stergea sub picioarele lui,
        //   procesul murea, watchdog-ul il repornea -> bucla infinita de restarturi.
        //   Acum pyhome se sterge DOAR cand se schimba efectiv continutul din assets
        //   (stampila diff), nu la fiecare rulare.
        val oldLib = File(filesDir, "pyhome/lib/python3.14/threading.py")
        val needLibRefresh = !oldLib.exists()
        if (needLibRefresh) File(filesDir, "pyhome").deleteRecursively()
        // ★ BUG reparat (crash "agent keeps stopping"): deleteRecursively() arunca
        //   AssertionError ("rootDir must be verified to be directory beforehand") daca
        //   directorul NU exista -> crash pe Thread-3 la prima configurare.
        runCatching { if (dest.isDirectory) dest.deleteRecursively() }.onFailure { dest.mkdirs() }
        dest.mkdirs()
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
        // ★ BUG reparat ("dupa cheie, ecranele sunt bifate dar nu se intampla nimic"):
        //   pyhome (stdlib-ul Python) se construia DOAR in startPythonProcess(), care la randul
        //   lui era gate-uit de pythonLaunching. Daca prima incercare esua, pyhome nu exista
        //   niciodata si setup-ul raporta etapele ca "ok" fara sa existe stdlib.
        //   Acum stdlib-ul se construieste AICI, sincron cu restul extragerii.
        try {
            val pyHomeX = File(filesDir, "pyhome")
            val stdlibX = File(pyHomeX, "lib/python3.14")
            val stdlibOkX = File(pyHomeX, ".stdlib_ok")
            fun stdlibFull(base: File): Boolean =
                File(base, "threading.py").exists() &&
                File(base, "encodings/__init__.py").exists() &&
                File(base, "os.py").exists()
            if (!stdlibOkX.exists() || !stdlibFull(stdlibX)) {
                try { stdlibOkX.delete() } catch (_: Exception) {}
                val tagX = "-" + android.os.Process.myPid() + "-" + System.nanoTime()
                val tmpX = File(pyHomeX, "lib/.py314.tmp" + tagX)
                try { tmpX.deleteRecursively() } catch (_: Exception) {}
                tmpX.mkdirs()
                var n = 0
                fun cpTree(src: File, dst: File) {
                    if (src.isDirectory) {
                        if (!dst.exists()) dst.mkdirs()
                        src.listFiles()?.forEach { cpTree(it, File(dst, it.name)) }
                    } else {
                        try {
                            dst.parentFile?.mkdirs()
                            src.inputStream().use { i -> dst.outputStream().use { o -> i.copyTo(o) } }
                            n++
                        } catch (_: Exception) {}
                    }
                }
                val srcLibX = File(dest, "Lib")
                if (srcLibX.isDirectory) cpTree(srcLibX, tmpX)
                if (stdlibFull(tmpX)) {
                    if (stdlibX.exists()) {
                        try { stdlibX.renameTo(File(pyHomeX, "lib/.old" + tagX)) } catch (_: Exception) {}
                    }
                    if (!tmpX.renameTo(stdlibX)) {
                        try { tmpX.copyRecursively(stdlibX, overwrite = true) } catch (_: Exception) {}
                    }
                    if (stdlibFull(stdlibX)) stdlibOkX.writeText("ok")
                }
                try { tmpX.deleteRecursively() } catch (_: Exception) {}
                try { File(pyHomeX, "lib").listFiles()?.filter {
                    it.name.startsWith(".old") || it.name.startsWith(".py314.tmp")
                }?.forEach { it.deleteRecursively() } } catch (_: Exception) {}
            }
            // lib-dynload (modulele .so) - separate de Lib/
            val dynX = File(stdlibX, "lib-dynload")
            if (!dynX.exists() || dynX.list()?.isEmpty() != false) {
                dynX.mkdirs()
                val abi = if (android.os.Build.SUPPORTED_ABIS.firstOrNull() == "arm64-v8a") "arm64" else "x86_64"
                val dynSrcX = File(dest, "libdynload/$abi")
                if (dynSrcX.isDirectory) dynSrcX.copyRecursively(dynX, overwrite = true)
            }
            // zip-urile pip/setuptools
            try {
                File(dest, "pysitepkg.zip").let {
                    if (it.exists()) it.copyTo(File(pyHomeX, "lib/pysitepkg.zip"), overwrite = true)
                }
                File(dest, "stdlib_extra.zip").let {
                    if (it.exists()) it.copyTo(File(pyHomeX, "lib/stdlib_extra.zip"), overwrite = true)
                }
            } catch (_: Exception) {}
        } catch (e: Exception) { runOnUiThread { appendAnsi("\u001b[38;5;203m[pyhome] " + e + "\u001b[0m\n") } }
        // ★ FIX 2026-10-21 (cauza pentru care lectiile despre binder nu ajungeau la o
        // instalare curata): assets continea DOUA memory.md - unul in radacina assets/
        // (cel bun) si unul vechi in assets/python/memory.md (copiat de copyDir("python")).
        // Agentul il lua pe cel vechi (690 B, doar antetul). Aici il fortam pe cel din
        // radacina assets/memory.md, care e sursa de adevar pentru lectiile livrate in APK.
        try {
            assets.open("memory.md").use { i ->
                File(filesDir, "memory.md").outputStream().use { o -> i.copyTo(o) }
            }
        } catch (_: Exception) {}
        // ★ FIX (2026-10-21, cauza reala a esecului binder la instalare curata):
        // aici se copia DOAR `assets/python`. `assets/binder` (clientul C + binarul bctl-android
        // + install_binder.sh) si `assets/skills` (procedurile agentului) NU ajungeau NICIODATA
        // pe device, deci la o instalare curata agentul nu avea: nici documentatia binder,
        // nici skill-ul de audit, nici sursa/installer-ul pentru clientul din Debian.
        // De aceea "repunea la punct" binder-ul de la zero, cu offseturi gresite.
        try {
            val bdir = File(filesDir, "binder")
            bdir.deleteRecursively(); bdir.mkdirs()
            copyDir("binder", bdir)
            // aapt pierde bitul de executie la ambalare -> chmod obligatoriu
            File(bdir, "bctl-android").let { if (it.exists()) it.setExecutable(true, false) }
            File(bdir, "install_binder.sh").let { if (it.exists()) it.setExecutable(true, false) }
        } catch (_: Exception) {}
        // skill-urile: cele livrate in APK se copiaza, dar cele scrise de agent pe device
        // (invatate) NU se sterg - acelasi principiu ca la memory.md.
        try {
            val sdir = File(filesDir, "skills")
            sdir.mkdirs()
            copyDir("skills", sdir)
        } catch (_: Exception) {}
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
            try { extractProotAssets() } catch (_: Exception) {}
        stamp.writeText(want)
        // curatam stampila veche (hardcodata), ca sa nu ramana pe disc
        try { legacy.delete() } catch (_: Exception) {}
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
    /**
     * Extrage desktopul Debian (proot): scriptul de start + rootfs-ul comprimat.
     * Rootfs-ul (~86 MB zstd) NU se dezarhiveaza aici: un tar zstd dureaza zeci de
     * secunde si ar bloca pornirea. Il lasam in files/proot si `proot_tool.py install`
     * il extrage o singura data, in background, cand operatorul cere desktopul.
     */
    private fun extractProotAssets() {
        val dest = File(filesDir, "proot")
        val stamp = File(dest, ".stamp")
        val want = assetsStampValue()
        try {
            if (stamp.exists() && stamp.readText() == want &&
                File(dest, "trixie-arm64.tar.zst").exists()) return
        } catch (_: Exception) {}
        runCatching { if (dest.isDirectory) dest.deleteRecursively() }
        dest.mkdirs()
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
        try {
            copyDir("proot", dest)
            File(dest, "debian_x.sh").setExecutable(true, false)
            stamp.writeText(want)
        } catch (_: Exception) {}
    }

    private fun extractToolchain() {
        val dest = File(filesDir, "toolchain")
        // ★ NU sterge ce a construit AGENTUL pe device: files/toolchain/git (git 2.47.1 + dropbear,
        // compilate nativ, ~20 MB, durabile) disparea la fiecare update de APK - exact motivul pentru
        // care operatorul a raportat "git a disparut si l-am rugat sa-l compileze de la 0".
        // Il mutam deoparte si il punem la loc dupa re-extragere (acelasi pattern ca site_packages_keep).
        val gitKeep = File(filesDir, "git_keep")
        val gitLive = File(dest, "git")
        var gitSaved = false
        if (gitLive.exists()) {
            try {
                gitKeep.deleteRecursively()
                gitLive.renameTo(gitKeep)
                gitSaved = true
            } catch (_: Exception) {
                try {
                    gitKeep.mkdirs(); gitLive.copyRecursively(gitKeep, overwrite = true); gitSaved = true
                } catch (_: Exception) {}
            }
        }
        runCatching { if (dest.isDirectory) dest.deleteRecursively() }
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
        // ★ punem la loc git-ul construit pe device (vezi mai sus)
        if (gitSaved) {
            try {
                val target = File(dest, "git")
                if (!target.exists()) gitKeep.renameTo(target)
                if (!File(target, "bin/git").exists() && gitKeep.exists()) {
                    gitKeep.copyRecursively(target, overwrite = true)
                }
                gitKeep.deleteRecursively()
            } catch (_: Exception) {}
        }
    }

    /** ★ Poarta: porneste agentul doar daca exista cheia; altfel o cere (onboarding).
     *  Cheia se cauta in files/python/key.txt, apoi files/home/key.txt, apoi env. */
    /** Asteapta ca stdlib-ul sa fie complet (marker .stdlib_ok + threading.py). */
    private fun waitStdlibReady(pyHome: File, timeoutMs: Long): Boolean {
        val marker = File(pyHome, ".stdlib_ok")
        val threading = File(pyHome, "lib/python3.14/threading.py")
        val t0 = System.currentTimeMillis()
        while (System.currentTimeMillis() - t0 < timeoutMs) {
            if (marker.exists() && threading.exists()) return true
            try { Thread.sleep(100) } catch (_: Exception) { return false }
        }
        // ultima sansa: daca stdlib-ul exista totusi complet, scriem markerul si pornim
        return threading.exists().also { if (it) try { marker.writeText("ok") } catch (_: Exception) {} }
    }

    private fun startPythonIfKey() {
        val GREEN = "\u001b[38;5;114m"
        val NRM = "\u001b[0m"
        val OF = "\u001b[38;5;208m"
        val k = readStoredKey()
        if (k.isNullOrBlank()) {
            awaitingKey = true
            runOnUiThread {
                appendAnsi("\n" + OF + "\u26a0  DeepSeek API KEY MISSING." + NRM + "\n")
                appendAnsi(OF + "Paste the key (sk-...) in the field below and press send." + NRM + "\n")
                appendAnsi(OF + "I write it automatically to files/python/key.txt and start the agent." + NRM + "\n\n")
                input.hint = "paste DeepSeek key (sk-...) and send"
                if (!audioMode) input.requestFocus()
            }
            return
        }
        // ★ (cerut de operator): fara linia de diagnostic "[key] cheie gasita" la pornire -
        // pe ecran raman doar ERORILE (ex. "LIPSA CHEIA DeepSeek API").
        startPythonProcess(k)
    }

    /** Citeste cheia din locurile posibile (scris de noi sau de alta sesiune). NU exista => null. */
    private fun readStoredKey(): String? {
        for (p in arrayOf(File(filesDir, "python/key.txt"), File(filesDir, "home/key.txt"))) {
            try { if (p.exists()) { val t = p.readText().trim(); if (t.isNotEmpty()) return t } } catch (_: Exception) {}
        }
        return null
    }

    @Volatile private var pythonLaunching = false
    @Volatile private var pythonStartRequestedAt = 0L

    private fun startPythonProcess(keyIn: String?) {
        // ★ GARDA ANTI-DUPLICARE in MEMORIE (nu doar pe disc): onResume + runSetup pot
        //   chema amandoua startPythonProcess -> 3 procese Python simultane (fiecare isi
        //   deschide propriul worker de terminal si propria conexiune adb).
        if (pythonLaunching) return
        pythonLaunching = true
        pythonStartRequestedAt = System.currentTimeMillis()
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
                // ★ FIX (bug "ModuleNotFoundError: No module named 'threading'" +
                //   "Fatal Python error: init_android_streams"): agent.py era pornit imediat ce
                //   aparea files/python/agent.py, in timp ce Lib/ se copia INCA in pyhome ->
                //   _android_support.py (rulat de CPython la bootstrap) facea
                //   `from threading import RLock` cu threading.py inca inexistent.
                //   Extragere ATOMICA + marker .stdlib_ok scris ULTIMUL; pornirea Python
                //   asteapta markerul (waitStdlibReady), deci nu mai vede stdlib incomplet.
                val stdlibOk = File(pyHome, ".stdlib_ok")
                // ★ o stdlib COMPLETA = threading.py + encodings + lib-dynload (altfel CPython
                //   moare in bootstrap cu "No module named 'threading'" / "Failed to import encodings")
                // ★ ATENTIE: lib-dynload NU face parte din Lib/ - modulele .so se copiaza
                //   SEPARAT, din assets/python/libdynload/<abi> in pyhome/.../lib-dynload.
                //   De aceea conditia se uita DOAR la ce trebuie sa fie in Lib/:
                //   threading.py (bootstrap CPython), encodings/ (obligatoriu la init) si os.py.
                fun stdlibComplete(base: File): Boolean =
                    File(base, "threading.py").exists() &&
                    File(base, "encodings/__init__.py").exists() &&
                    File(base, "os.py").exists()
                val needExtract = !stdlibOk.exists() || !stdlibComplete(stdlib)
                if (needExtract) {
                    try { stdlibOk.delete() } catch (_: Exception) {}
                    val tag = "-" + android.os.Process.myPid() + "-" + System.nanoTime()
                    val tmp = File(pyHome, "lib/.py314.tmp" + tag)
                    try { tmp.deleteRecursively() } catch (_: Exception) {}
                    tmp.mkdirs()
                    val srcLib = File(scripts, "Lib")
                    // ★ copyRecursively() crapa silentios pe arborele stdlib (1688 fisiere, 27 MB)
                    //   si lasa doar lib-dynload -> stdlib incomplet. Copiem manual, fiind foarte
                    //   explicit: mkdirs pentru directoare, stream pentru fisiere.
                    var _copied = 0
                    var _err = 0
                    fun copyTree(src: File, dst: File) {
                        if (src.isDirectory) {
                            if (!dst.exists()) dst.mkdirs()
                            src.listFiles()?.forEach { copyTree(it, File(dst, it.name)) }
                        } else {
                            try {
                                dst.parentFile?.mkdirs()
                                src.inputStream().use { i -> dst.outputStream().use { o -> i.copyTo(o) } }
                                _copied++
                            } catch (_: Exception) { _err++ }
                        }
                    }
                    if (srcLib.isDirectory) copyTree(srcLib, tmp)
                    // verificare: stdlib-ul temporar trebuie sa fie COMPLET inainte de a inlocui
                    val complete = stdlibComplete(tmp)
                    runOnUiThread {
                        appendAnsi("\u001b[38;5;243m[extract] stdlib: " + _copied + " fisiere, " +
                            _err + " erori, " + (if (complete) "COMPLET" else "INCOMPLET") + "\u001b[0m\n")
                    }
                    if (complete) {
                        if (stdlib.exists()) stdlib.renameTo(File(pyHome, "lib/.old" + tag))
                        if (!tmp.renameTo(stdlib)) { tmp.copyRecursively(stdlib, overwrite = true) }
                        stdlibOk.writeText("ok")
                    } else {
                        runOnUiThread {
                            appendAnsi("\u001b[38;5;203m[extract] stdlib incomplet - reincerc\u001b[0m\n")
                        }
                    }
                    try { tmp.deleteRecursively() } catch (_: Exception) {}
                    try { File(pyHome, "lib").listFiles()?.filter {
                        it.name.startsWith(".old") || it.name.startsWith(".py314.tmp")
                    }?.forEach { it.deleteRecursively() } } catch (_: Exception) {}
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
                // ★ lib-dynload face parte din conditia de "stdlib complet": daca lipseste,
                //   stdlibComplete() da false si re-extragem TOT (nu doar dynload) - altfel
                //   ramanea un stdlib fara encodings si CPython nu pornea deloc.
                val dynDst = File(stdlib, "lib-dynload")
                if (!dynDst.exists() || dynDst.list()?.isEmpty() != false) {
                    dynDst.mkdirs()
                    val abiTag = when (Build.SUPPORTED_ABIS.firstOrNull()) {
                        "arm64-v8a" -> "arm64"; else -> "x86_64"
                    }
                    val dynSrc = File(scripts, "libdynload/$abiTag")
                    if (dynSrc.exists()) dynSrc.copyRecursively(dynDst, overwrite = true)
                }

                // ★ folderul acestei aplicatii pe /sdcard (Download/<agent_home_dir>): workspace-ul
                //   si adbkey-ul sunt PER APLICATIE, ca cei doi agenti sa nu si le imparta.
                val agentHome = File(
                    android.os.Environment.getExternalStoragePublicDirectory(android.os.Environment.DIRECTORY_DOWNLOADS),
                    getString(R.string.agent_home_dir))

                // ★ SETUP ADB AUTOMAT: genereaza cheia + cert + libs la prima pornire
                try {
                    val setup = ProcessBuilder(py.absolutePath, "adb_setup.py")
                    setup.directory(scripts)
                    setup.environment()["LD_LIBRARY_PATH"] = applicationInfo.nativeLibraryDir + ":" + File(filesDir,"libs").absolutePath
                    setup.environment()["PYTHONHOME"] = pyHome.absolutePath
                    setup.environment()["HOME"] = home.absolutePath
                    setup.environment()["PATH"] = "/system/bin:/vendor/bin"
                    // ★ OBLIGATORIU: altfel adb_setup cade pe fallback (/sdcard/Download/Agent) si
                    //   cei doi agenti impart acelasi adbkey persistent
                    setup.environment()["AGENT_HOME"] = agentHome.absolutePath
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

                // ★ POARTA (acelasi bug ca mai sus): nu porni Python pana cand stdlib-ul nu e
                // COMPLET pe disc. Markerul .stdlib_ok se scrie dupa threading.py; fara el
                // CPython moare in bootstrap cu "No module named 'threading'".
                if (!waitStdlibReady(pyHome, 120_000L)) {
                    runOnUiThread {
                        appendAnsi("\u001b[38;5;203m[python] stdlib incomplet - pornire amanata\u001b[0m\n")
                    }
                }
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
                // ★ folderul de pe sdcard e per aplicatie (vezi agentHome mai sus)
                pb.environment()["AGENT_HOME"] = agentHome.absolutePath
                pb.environment()["AGENT_COLS"] = run {
                    val test = android.widget.TextView(this@MainActivity).apply {
                        textSize = fontSizeSp; typeface = mono
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
                runOnUiThread { agentStarted = false; appendAnsi("\n[process finished]\n") }
            } catch (e: Exception) {
                val msg = e.toString()
                runOnUiThread { appendAnsi("\n[ERROR] $msg\n") }
            } finally { pythonLaunching = false }
        }.start()
    }

    private fun sendLine() {
        // one line only: the text field may contain embedded newlines (IME / Enter),
        // and an extra blank line would be read by the agent's input() as a separate, empty line.
        var t = input.text.toString().replace("\r", "").replace("\n", " ").trim()
        if (t.isEmpty()) return
        input.setText("")
        // ★ /audio = MOD PERSISTENT.
        //   /audio on  (sau doar /audio) -> de acum TOATE raspunsurile se rostesc si nu se afiseaza
        //   /audio off                    -> revine la afisarea normala in terminal
        //   /audio <mesaj>                -> activeaza modul si trimite mesajul
        val low = t.lowercase()
        if (low == "/audio on" || low == "/audio" || low == "/audio arm") {
            audioMode = true; audioNext = true; audioText.setLength(0); inTask = false; inAgent = false
            appendAnsi("\u001b[38;5;114m[audio] ON: every reply is spoken, nothing is shown. " +
                       "Type /audio off to go back.\u001b[0m\n")
            setAudioUi(true)
            toast("audio mode ON (persistent)")
            return
        }
        if (low == "/audio off" || low == "/text") {
            exitAudioMode()
            return
        }
        if (low.startsWith("/audio ")) {
            // "/audio <mesaj>": activeaza modul persistent si trimite mesajul
            audioMode = true; audioNext = true; audioText.setLength(0); inTask = false; inAgent = false
            t = t.substring(6).trim()
            showAudioYou(t)
            appendAnsi("\u001b[38;5;114m[audio] ON: every reply is spoken, nothing is shown.\u001b[0m\n")
            setAudioUi(true)
            if (t.isEmpty()) { toast("audio mode ON (persistent)"); return }
        } else if (audioMode && !t.startsWith("/")) {
            // mod persistent: fiecare mesaj nou se duce ca "/audio <mesaj>", ca agentul sa
            // raspunda in engleza si proza curata, iar aplicatia sa ascunda textul
            audioNext = true; audioText.setLength(0); inTask = false; inAgent = false
            showAudioYou(t)
            if (PhononTts.isBusy()) {
                runOnUiThread { audioState.text = "Queued - the agent will answer after the audio finishes." }
            }
            t = "/audio " + t
        }
        // ★ ONBOARDING: daca asteptam cheia API, o salvam si pornim agentul.
        if (awaitingKey) {
            saveKeyAndStart(t)
            return
        }
        // NU afisam ecou aici: agentul afiseaza el linia "You > <mesaj>" in _task_head.
        btnStop.visibility = View.VISIBLE
        setTaskScreenOn(true)
        // ★ FIX 2026-10-06 (auto-scroll "sare mai sus" la un task nou):
        // urmarirea cozii se OPREA cand userul derula sus (followTail=false) si NU se mai
        // re-arma la taskul urmator -> textul curgea SUB marginea de jos, scroll blocat.
        // La fiecare mesaj trimis reluam urmarirea cozii (userul vrea sa vada raspunsul nou).
        followTail = true
        scrollToBottom()
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
            // (liniile de diagnostic "[key] cheia salvata/pornesc agentul" au fost scoase;
            //  feedbackul e schimbarea hint-ului de input)
            awaitingKey = false
            input.hint = "message the agent..."
            // ★ BUG reparat ("a durat 2 minute pana a aparut ready si abia apoi cere cheia"):
            //   saveKeyAndStart() chema DIRECT startPythonProcess(), sarind peste extractAssets()
            //   si peste ecranul de setup. Daca pyhome nu exista, Python nu pornea si setup-ul
            //   nu se mai facea niciodata. Acum, dupa salvare, pornim setup-ul COMPLET
            //   (extract -> verify -> bridge -> python) exact o data, prin runSetup().
            // ★ BUG reparat ("dupa ce am inserat cheia, ecranul arata toate etapele bifate
            //   dar nu se intampla nimic"): runSetup() e idempotent prin runSetupStarted,
            //   iar el RULASE deja o data (cand a aparut cererea de cheie) -> a doua chemare
            //   iesea imediat si Python nu pornea niciodata.
            //   Acum, dupa salvare, pornim DIRECT procesul Python (stdlib-ul e deja pe disc,
            //   verificat de prima rulare a setup-ului).
            appendAnsi("\n\u001b[38;5;114mKey saved.\u001b[0m Starting agent...\n")
            runSetupStarted = false
            startPythonProcess(key.trim())
        } catch (e: Exception) {
            appendAnsi(RED + "[key] ERROR while saving: " + e.message + NRM + "\n")
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
