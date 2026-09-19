package net.sys32.agent

import android.Manifest
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
    private var bridge: AndroidBridge? = null
    private var pyProc: Process? = null
    private var pyIn: OutputStreamWriter? = null
    private val pending = StringBuilder()
    private var autoScroll = true
    private var programmaticScroll = false

    private val extraTop: Int get() = (16 * resources.displayMetrics.density).toInt()

    private val mono: Typeface by lazy {
        try { TF.createFromAsset(assets, "fonts/DejaVuSansMono.ttf") }
        catch (e: Exception) { Typeface.MONOSPACE }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        WindowCompat.setDecorFitsSystemWindows(window, false)
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
            setTextIsSelectable(true)
            setPadding(24, 16, 24, 24)
            textSize = 11f
            typeface = mono
            setTextColor(Color.parseColor("#ABB2BF"))
            setBackgroundColor(Color.parseColor("#0D1117"))
        }
        scroll.addView(output, ViewGroup.LayoutParams(-1, -2))
        root.addView(scroll, LinearLayout.LayoutParams(-1, 0, 1f))

        scroll.viewTreeObserver.addOnScrollChangedListener {
            if (programmaticScroll) return@addOnScrollChangedListener
            val child = scroll.getChildAt(0) ?: return@addOnScrollChangedListener
            val dist = child.bottom - scroll.height - scroll.scrollY
            autoScroll = dist <= 24
            btnDown.visibility = if (autoScroll) View.GONE else View.VISIBLE
        }

        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setBackgroundColor(Color.parseColor("#11151C"))
            setPadding(16, 12, 12, 12)
        }
        input = EditText(this).apply {
            hint = "scrie agentului..."
            setHintTextColor(Color.parseColor("#5C6370"))
            setTextColor(Color.parseColor("#E6E6E6"))
            textSize = 13f
            typeface = mono
            setBackgroundColor(Color.TRANSPARENT)
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_MULTI_LINE
            maxLines = 5
            setPadding(12, 12, 12, 12)
        }
        val send = Button(this).apply {
            text = "→"
            textSize = 18f
            setTextColor(Color.parseColor("#61AFEF"))
            setBackgroundColor(Color.TRANSPARENT)
        }
        row.addView(input, LinearLayout.LayoutParams(0, -2, 1f))
        row.addView(send, LinearLayout.LayoutParams(-2, -2))
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
                autoScroll = true
                btnDown.visibility = View.GONE
                programmaticScroll = true
                scroll.post {
                    scroll.fullScroll(ScrollView.FOCUS_DOWN)
                    scroll.postDelayed({ programmaticScroll = false }, 120)
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
            val bottom = maxOf(bars.bottom, ime.bottom)
            v.updatePadding(top = topPad, bottom = bottom)
            insets
        }

        send.setOnClickListener { sendLine() }
        requestAllPermissions()
        try { extractAssets() } catch (e: Exception) { appendAnsi("\n[extract eroare] $e\n") }
        try {
            bridge = AndroidBridge(this, File(filesDir, "bridge.sock"))
            bridge!!.start()
        } catch (e: Exception) { appendAnsi("\n[bridge eroare] $e\n") }
        startPython()
    }

    private fun appendAnsi(s: String) {
        output.append(Ansi.toSpannable(s))
        if (autoScroll) {
            programmaticScroll = true
            scroll.post {
                scroll.fullScroll(ScrollView.FOCUS_DOWN)
                scroll.postDelayed({ programmaticScroll = false }, 120)
            }
        }
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
            Manifest.permission.ACCESS_BACKGROUND_LOCATION,
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
        if (need.isNotEmpty()) ActivityCompat.requestPermissions(this, need.toTypedArray(), 1)

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

    private fun extractAssets() {
        val dest = File(filesDir, "python")
        val stamp = File(filesDir, ".assets_v16")
        if (stamp.exists() && dest.exists()) return
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
        appendAnsi("\u001B[38;5;245m" + t + "\u001B[0m\n")
        try { pyIn?.write(t + "\n"); pyIn?.flush() } catch (e: Exception) {
            appendAnsi("[scriere esuata: $e]\n")
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        try { pyProc?.destroy() } catch (_: Exception) {}
        try { bridge?.stop() } catch (_: Exception) {}
    }
}
