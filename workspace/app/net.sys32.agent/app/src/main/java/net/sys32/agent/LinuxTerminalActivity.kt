package net.sys32.agent

import android.content.Context
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.text.SpannableStringBuilder
import android.text.method.ScrollingMovementMethod
import android.view.Gravity
import android.view.KeyEvent
import android.view.View
import android.view.ViewGroup
import android.view.WindowInsets
import android.view.WindowInsetsController
import android.view.WindowManager
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputMethodManager
import android.widget.Button
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.HorizontalScrollView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity

/**
 * Terminal pentru Debian (proot) cu sesiuni multiple.
 *
 * LAYOUT (de sus in jos) - cerut de operator:
 *   [ tab-uri: BASH1  BASH2  + ]
 *   [ TERMINAL - lista comenzilor si a output-ului, ocupa tot spatiul liber ]
 *   [ CAMP DE SCRIS vizibil - deasupra tastelor, cu buton de trimitere ]
 *   [ bara de taste: ^C ^D TAB ESC | SH ]
 *
 * Canalul de executie: fisiere in files/tmp (UI scrie comanda, agent.py o ruleaza
 * prin adb_client -> adbd uid 2000 -> proot -> Debian, apoi scrie output-ul).
 * Motivul e documentat in RAPORT_LAPTOP.md: /data/data e NOEXEC si untrusted_app
 * nu poate execve, deci executia trebuie sa treaca prin procesul agentului.
 */
class LinuxTerminalActivity : AppCompatActivity(), TerminalClient.Listener {

    companion object {
        // paleta One Dark (aceeasi ca MainActivity)
        private const val BG = "#0D1117"
        private const val BG_BAR = "#11151C"
        private const val BG_FIELD = "#1C2128"
        private const val FG = "#ABB2BF"
        private const val FG_DIM = "#5C6370"
        private const val ACCENT = "#61AFEF"
        private const val GREEN = "#98C379"
        private const val YELLOW = "#E5C07B"
        private const val RED = "#E06C75"
    }

    private lateinit var client: TerminalClient
    private val ui = Handler(Looper.getMainLooper())

    private lateinit var root: FrameLayout
    private lateinit var tabsBar: LinearLayout
    private lateinit var tv: TextView
    private lateinit var scroll: ScrollView
    private lateinit var input: EditText

    private val buffers = LinkedHashMap<Int, SpannableStringBuilder>()
    private val names = HashMap<Int, String>()
    private var activeId = -1
    private var shellMode = true      // ★ uid 2000 PERMANENT (cerut de operator)
    private var created = false

    private val mono: Typeface by lazy {
        try { Typeface.createFromAsset(assets, "fonts/DejaVuSansMono.ttf") }
        catch (_: Exception) { Typeface.MONOSPACE }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

        root = FrameLayout(this).apply { setBackgroundColor(Color.parseColor(BG)) }
        val col = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }

        // ---------------- 1. TAB-URI ----------------
        val tabsRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setBackgroundColor(Color.parseColor(BG_BAR))
            // ★ padding sus pentru bara de status (FLAG_LAYOUT_NO_LIMITS scoate fereastra
            // de sub bara de sistem, deci tab-urile ajungeau sub ceas - raportat de operator)
            setPadding(dp(6), dp(4), dp(6), dp(4))
            gravity = Gravity.CENTER_VERTICAL
        }
        tabsBar = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        val tabsScroll = HorizontalScrollView(this).apply { isHorizontalScrollBarEnabled = false }
        tabsScroll.addView(tabsBar)
        tabsRow.addView(tabsScroll, LinearLayout.LayoutParams(0, -2, 1f))
        tabsRow.addView(chip("+", GREEN, bold = true) { newTab() })
        col.addView(tabsRow, LinearLayout.LayoutParams(-1, -2))

        // ---------------- 2. TERMINAL (lista de comenzi) ----------------
        tv = TextView(this).apply {
            typeface = mono
            textSize = 12f
            setTextColor(Color.parseColor(FG))
            setBackgroundColor(Color.parseColor(BG))
            setPadding(dp(10), dp(8), dp(10), dp(8))
            // ★ NU setTextIsSelectable(true): face TextView-ul focusabil si fura
            // inputul de la EditText (dovedit: mServedView=TextView in dumpsys input_method)
            isFocusable = false
            isFocusableInTouchMode = false
            movementMethod = ScrollingMovementMethod()
            letterSpacing = 0f
        }
        scroll = ScrollView(this).apply {
            setBackgroundColor(Color.parseColor(BG))
            isFillViewport = true
            addView(tv)
        }
        col.addView(scroll, LinearLayout.LayoutParams(-1, 0, 1f))

        // ---------------- 3. CAMP DE SCRIS (deasupra tastelor) ----------------
        val inputRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setBackgroundColor(Color.parseColor(BG_BAR))
            setPadding(dp(6), dp(6), dp(6), dp(6))
            gravity = Gravity.CENTER_VERTICAL
        }
        val prompt = TextView(this).apply {
            text = "$ "
            typeface = mono
            textSize = 14f
            setTextColor(Color.parseColor(GREEN))
            setPadding(dp(2), 0, dp(6), 0)
        }
        inputRow.addView(prompt, LinearLayout.LayoutParams(-2, -2))
        input = EditText(this).apply {
            hint = ""
            setHintTextColor(Color.parseColor(FG_DIM))
            setTextColor(Color.parseColor(FG))
            setBackgroundColor(Color.parseColor(BG_FIELD))
            typeface = mono
            textSize = 13f
            setPadding(dp(10), dp(8), dp(10), dp(8))
            isSingleLine = true
            isFocusable = true
            isFocusableInTouchMode = true
            inputType = android.text.InputType.TYPE_CLASS_TEXT or
                    android.text.InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS
            imeOptions = EditorInfo.IME_ACTION_SEND or
                    EditorInfo.IME_FLAG_NO_EXTRACT_UI or EditorInfo.IME_FLAG_NO_FULLSCREEN
            background = rounded(BG_FIELD, 8f)
            setOnClickListener { openKeyboard() }
            setOnFocusChangeListener { v, has -> if (has) openKeyboard() }
            setOnEditorActionListener { _, actionId, ev ->
                val enter = actionId == EditorInfo.IME_ACTION_SEND ||
                        (ev != null && ev.keyCode == KeyEvent.KEYCODE_ENTER &&
                                ev.action == KeyEvent.ACTION_DOWN)
                if (enter) { submit(); true } else false
            }
        }
        inputRow.addView(input, LinearLayout.LayoutParams(0, -2, 1f))
        inputRow.addView(chip("↵", ACCENT, bold = true) { submit() })
        col.addView(inputRow, LinearLayout.LayoutParams(-1, -2))

        // ---------------- 4. BARA DE TASTE (redusa) ----------------
        keyBar = buildKeyBar() as LinearLayout
        col.addView(keyBar, LinearLayout.LayoutParams(-1, -2))

        root.addView(col, FrameLayout.LayoutParams(-1, -1))
        setContentView(root)

        // tastatura sa nu acopere campul (FLAG_LAYOUT_NO_LIMITS anuleaza adjustResize)
        root.setOnApplyWindowInsetsListener { v, insets ->
            val ime = insets.getInsets(WindowInsets.Type.ime()).bottom
            val nav = insets.getInsets(WindowInsets.Type.navigationBars()).bottom
            // ★ padding SUS = bara de status (altfel tab-urile stau sub ceas)
            val top = insets.getInsets(WindowInsets.Type.statusBars()).top
            v.setPadding(0, top, 0, if (ime > 0) ime else nav)
            scroll.post { scroll.fullScroll(View.FOCUS_DOWN) }
            insets
        }

        client = TerminalClient(this)
        client.connect()
        // ★ focus explicit pe camp DUPA layout (altfel tastatura se leaga de TextView)
        root.post {
            input.isFocusableInTouchMode = true
            input.requestFocus()
            openKeyboard()
        }
        // ★ SETUP AUTOMAT LA DESCHIDEREA TERMINALULUI (cerut de operator):
        //   instalarea mediului Linux porneste imediat ce se apasa TERMINAL, FARA sa mai
        //   fie nevoie de o comanda care oricum esua ("proot_exec.so: inaccessible").
        //   Progresul apare in terminal pas cu pas: "done Linux filesystem",
        //   "done Linux runtime", "done Android service access", "done Compiler toolchain".
        //   Idempotent: agent.py sare peste tot daca files/.debian_ready exista.
        root.postDelayed({
            try {
                if (activeId >= 0) {
                    appendCmd("[setup] configuring the Linux environment, please wait\u2026")
                    client.sendCommand(activeId, "setup", uid2000 = false)
                    scroll.post { scroll.fullScroll(View.FOCUS_DOWN) }
                }
            } catch (_: Exception) {}
        }, 700)
    }

    // ---------------- UI helpers ----------------
    private fun dp(v: Int) = (v * resources.displayMetrics.density).toInt()

    private fun rounded(color: String, radiusDp: Float) = GradientDrawable().apply {
        setColor(Color.parseColor(color))
        cornerRadius = radiusDp * resources.displayMetrics.density
    }

    /** buton mic, stilizat */
    private fun chip(label: String, color: String, bold: Boolean = false,
                     onClick: () -> Unit) = Button(this).apply {
        text = label
        textSize = 13f
        typeface = mono
        setTextColor(Color.parseColor(color))
        setBackgroundColor(Color.TRANSPARENT)
        minWidth = 0; minimumWidth = 0
        setPadding(dp(10), dp(4), dp(10), dp(4))
        isAllCaps = false
        if (bold) setTypeface(mono, Typeface.BOLD)
        setOnClickListener { onClick() }
    }

    /** bara de taste: CTRL  TAB  ESC  |  UID 2000 (galben cand e activ) */
    private fun buildKeyBar(): View {
        val bar = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setBackgroundColor(Color.parseColor(BG_BAR))
            setPadding(dp(6), dp(2), dp(6), dp(4))
            gravity = Gravity.CENTER_VERTICAL
        }
        // CTRL: comuta mod "control" (urmatoarea tasta se prefixeaza cu ^)
        bar.addView(chip("CTRL", if (ctrlMode) YELLOW else FG) {
            ctrlMode = !ctrlMode
            rebuildKeyBar()
        })
        bar.addView(chip("TAB", FG) { insertKey("\t") })
        bar.addView(chip("ESC", FG) { insertKey("\u001b") })
        bar.addView(View(this), LinearLayout.LayoutParams(0, 1, 1f))
        // ★ UID 2000 e PERMANENT: butonul a fost scos (nu isi mai are rostul)
        return bar
    }

    private var keyBar: LinearLayout? = null
    private var ctrlMode = false

    private fun rebuildKeyBar() {
        val col = (keyBar?.parent as? LinearLayout) ?: return
        val idx = col.indexOfChild(keyBar)
        if (idx >= 0) {
            col.removeViewAt(idx)
            col.addView(buildKeyBar2(), idx, LinearLayout.LayoutParams(-1, -2))
        }
    }

    private fun buildKeyBar2(): View = buildKeyBar()

    private fun insertKey(bytes: String) {
        if (activeId < 0) return
        val cur = input.text.toString()
        input.setText(cur + bytes)
        input.setSelection(input.text.length)
        openKeyboard()
    }

    // ---------------- actiuni ----------------
    private fun openKeyboard() {
        try {
            val imm = getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager
            input.requestFocus()
            input.post { imm.showSoftInput(input, InputMethodManager.SHOW_IMPLICIT) }
        } catch (_: Exception) {}
    }

    private fun submit() {
        val cmd = input.text.toString().trim()
        if (cmd.isEmpty()) return
        // ★ /exit (sau exit): inchide sesiunea curenta; daca nu mai exista, iese din ecran
        if (cmd == "/exit" || cmd == "exit" || cmd == "/quit") {
            input.setText("")
            val id = activeId
            client.close(id); buffers.remove(id); names.remove(id)
            activeId = buffers.keys.lastOrNull() ?: -1
            if (activeId < 0) { finish(); return }
            renderTabs(); renderText()
            return
        }
        if (activeId < 0) return
        // feedback instant in terminal
        appendCmd("root@debian:~# " + cmd)
        client.sendCommand(activeId, cmd, uid2000 = shellMode)
        input.setText("")
        scroll.post { scroll.fullScroll(View.FOCUS_DOWN) }
    }

    private fun sendRaw(display: String, bytes: String) {
        appendCmd("root@debian:~# " + display)
        // trimitem ca o comanda speciala (agent.py o executa literal)
        client.sendCommand(activeId, "printf '" + bytes.replace("'", "") + "'", uid2000 = false)
    }

    private fun newTab() {
        client.newSession("bash", false, 80, 24)
    }

    private fun appendCmd(text: String) {
        val b = buffers.getOrPut(activeId) { SpannableStringBuilder() }
        // ★ intotdeauna pe linie NOUA: altfel output-ul se lipeste de comanda
        if (b.isNotEmpty() && !b.endsWith("\n")) b.append("\n")
        b.append(text).append("\n")
        renderText()
        scroll.post { scroll.fullScroll(View.FOCUS_DOWN) }
    }

    // ---------------- TerminalClient.Listener ----------------
    override fun onCreated(id: Int, pid: Int) {
        ui.post {
            buffers.putIfAbsent(id, SpannableStringBuilder())
            names[id] = "bash$id"
            if (activeId < 0) activeId = id
            renderTabs(); renderText()
        }
    }

    override fun onData(id: Int, bytes: ByteArray) {
        val text = String(bytes, Charsets.UTF_8)
        ui.post {
            val b = buffers.getOrPut(id) { SpannableStringBuilder() }
            // ★ output-ul incepe pe linie noua (nu continuat dupa comanda)
            if (b.isNotEmpty() && !b.endsWith("\n") && !text.startsWith("\n")) b.append("\n")
            b.append(text)
            if (b.length > 120_000) b.delete(0, b.length - 90_000)
            if (id == activeId) {
                renderText()
                scroll.post { scroll.fullScroll(View.FOCUS_DOWN) }
            }
        }
    }

    override fun onExit(id: Int, code: Int) {}
    override fun onSessions(list: List<Triple<Int, String, Int>>) {}
    override fun onError(msg: String) {
        ui.post { appendCmd("[eroare] " + msg) }
    }
    override fun onDisconnected() {}

    // ---------------- randare ----------------
    private fun renderTabs() {
        tabsBar.removeAllViews()
        for ((id, nm) in names) {
            val active = id == activeId
            val t = Button(this).apply {
                text = nm
                textSize = 12f
                typeface = mono
                isAllCaps = false
                setTextColor(Color.parseColor(if (active) ACCENT else FG_DIM))
                setBackgroundColor(Color.parseColor(if (active) BG_FIELD else BG_BAR))
                minWidth = 0; minimumWidth = 0
                setPadding(dp(12), dp(4), dp(12), dp(4))
                setOnClickListener { activeId = id; renderTabs(); renderText() }
                setOnLongClickListener {
                    client.close(id); buffers.remove(id); names.remove(id)
                    activeId = buffers.keys.lastOrNull() ?: -1
                    renderTabs(); renderText()
                    true
                }
            }
            tabsBar.addView(t)
        }
    }

    private fun renderText() {
        val b = buffers[activeId] ?: return
        tv.text = b
    }

    override fun onKeyDown(keyCode: Int, event: KeyEvent): Boolean {
        if (keyCode == KeyEvent.KEYCODE_ENTER && event.action == KeyEvent.ACTION_DOWN) {
            submit(); return true
        }
        return super.onKeyDown(keyCode, event)
    }

    override fun onDestroy() {
        try { client.shutdown() } catch (_: Exception) {}
        super.onDestroy()
    }
}
