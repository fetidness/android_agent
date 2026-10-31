package net.sys32.agent

import android.Manifest
import android.content.pm.PackageManager
import android.media.*
import android.graphics.Color
import android.graphics.Typeface
import android.util.Log
import android.view.Gravity
import android.view.View
import android.widget.Button
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextView
import java.io.File
import java.io.FileOutputStream
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Push-to-talk for the /audio on mode: hold, speak, release -> Whisper (offline, native)
 * -> text injected into the chat exactly as if it had been typed.
 *
 * Design follows WHISPER_AUDIO_MODE_INTEGRATION.md section 9 "Model A": the binaries ship in
 * jniLibs, so the app EXECUTES them from nativeLibraryDir (label apk_data_file) with
 * ProcessBuilder - no /data/local/tmp, no shell bridge, no adb authorization.
 */
class PushToTalk(
    private val act: MainActivity,
    private val onExit: () -> Unit,        // iese din modul audio (inapoi la chat)
    private val onStopVoice: () -> Unit,   // opreste vocea agentului, ramane in modul audio
    private val onPress: () -> Unit,       // degetul a atins butonul: opreste vocea ACUM
    private val onRelease: () -> Unit,     // degetul s-a ridicat: microfonul nu mai asculta
    private val onText: (String) -> Unit
) {
    private val ctx = act.applicationContext
    private val SR = 16000
    private val MIN_SAMPLES = SR / 2                 // 0.5 s: stray taps are ignored
    private val MAX_MS = 60_000

    private val busy = AtomicBoolean(false)
    private lateinit var container: LinearLayout
    private lateinit var btn: Button
    private lateinit var status: TextView
    private lateinit var langBtn: Button

    private var rec: AudioRecord? = null
    private var recThread: Thread? = null
    private val pcm = java.io.ByteArrayOutputStream()
    @Volatile private var recording = false

    // singurul model livrat: medium (doc: REPARA cuvinte romanesti pe care small le strica)
    private val modelName = "medium"
    // limba trebuie sa se potriveasca cu vocea: fortat 'ro' pe engleza da text romanizat
    private var lang = "ro"
    private val langs = listOf("ro", "en", "auto")

    private fun dp(v: Int) = (v * ctx.resources.displayMetrics.density).toInt()

    /** Starea PTT, afisata si in panoul principal al modului audio. */
    private fun say(msg: String, color: String = "#61AFEF") {
        act.runOnUiThread { status.setTextColor(Color.parseColor(color)); status.text = msg }
        act.audioPanelStatus(msg)
    }
    private fun native(name: String) = File(ctx.applicationInfo.nativeLibraryDir, name)

    /** filesDir/models/whisper/ggml-<name>.bin; copied from assets once when missing (streamed). */
    private fun modelFile(name: String): File = File(File(File(ctx.filesDir, "models"), "whisper"), "ggml-$name.bin")

    /** Cate octeti are asset-ul (available() nu da dimensiunea unui asset comprimat/streamat). */
    private fun assetSize(path: String): Long = try {
        ctx.assets.openFd(path).use { it.length }
    } catch (_: Exception) { 0L }

    private fun ensureModel(name: String, say: (String) -> Unit): File? {
        val f = modelFile(name)
        val path = "whisper/models/ggml-$name.bin"
        val expected = assetSize(path)
        if (f.exists() && (expected == 0L || f.length() == expected)) return f
        f.parentFile?.mkdirs()
        if (f.exists()) f.delete()
        val tmp = File(f.parentFile, f.name + ".part")
        try {
            ctx.assets.open(path).use { inp ->
                val bos = java.io.BufferedOutputStream(FileOutputStream(tmp), 1 shl 20)
                val buf = ByteArray(1 shl 20)
                var done = 0L
                var lastShown = -1L
                val t0 = System.currentTimeMillis()
                while (true) {
                    val n = inp.read(buf); if (n <= 0) break
                    bos.write(buf, 0, n); done += n
                    // progres la fiecare 2% SAU la fiecare 50 MB: 1.5 GB nu trebuie sa para blocat
                    val pct = if (expected > 0) (done * 100 / expected) else -1
                    val step = if (expected > 0) (expected / 50).coerceAtLeast(1L) else (50L shl 20)
                    val duePct = pct >= 0 && pct % 2L == 0L && pct != lastShown
                    val dueBytes = done - lastShown * step > step
                    if (duePct || dueBytes) {
                        lastShown = pct.toLong()
                        val mb = done / (1L shl 20)
                        val tot = expected / (1L shl 20)
                        val secs = ((System.currentTimeMillis() - t0) / 1000).coerceAtLeast(1)
                        say(if (tot > 0) "Preparing voice input: $mb / $tot MB  ($pct%)  -  one time only"
                            else "Preparing voice input: $mb MB  -  one time only")
                        Log.i("PTT", "unpack $name: $mb/$tot MB in ${secs}s")
                    }
                }
                bos.flush(); bos.close()
            }
            if (!tmp.renameTo(f)) { tmp.copyTo(f, overwrite = true); tmp.delete() }
            if (expected > 0 && f.length() != expected) {
                Log.w("PTT", "size mismatch after unpack: ${f.length()} != $expected")
                f.delete(); return null
            }
            say("Voice input ready (${f.length() / (1L shl 20)} MB).", "#98C379")
            return f
        } catch (e: Exception) {
            Log.w("PTT", "model asset could not be unpacked for $name: $e")
            tmp.delete()
            say("ERROR: cannot prepare the voice model: ${e.message}", "#E06C75")
            return null
        }
    }

    // ---------------------------------------------------------------- UI
    private lateinit var step: TextView
    private lateinit var dotLabel: TextView
    private lateinit var ring1: android.widget.FrameLayout
    private lateinit var ring2: android.widget.FrameLayout

    /** Fundal circular cu inel, desenat (nu imagine) - arata bine la orice densitate. */
    private fun circleBg(fill: String, ringColor: String, ringDp: Int) =
        android.graphics.drawable.GradientDrawable().apply {
            shape = android.graphics.drawable.GradientDrawable.OVAL
            setColor(Color.parseColor(fill))
            setStroke(dp(ringDp), Color.parseColor(ringColor))
        }

    fun build(frame: FrameLayout) {
        container = LinearLayout(ctx).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setBackgroundColor(Color.parseColor("#0B0E14"))
            visibility = View.GONE
            setPadding(dp(24), dp(24), dp(24), dp(24))
        }
        val title = TextView(ctx).apply {
            text = ""
            textSize = 13f
            letterSpacing = 0.35f
            typeface = Typeface.create(Typeface.DEFAULT, Typeface.BOLD)
            setTextColor(Color.parseColor("#5C6370"))
            gravity = Gravity.CENTER
        }
        status = TextView(ctx).apply {
            text = "Ready - hold the button and speak."
            textSize = 19f
            typeface = Typeface.create(Typeface.DEFAULT, Typeface.BOLD)
            setTextColor(Color.parseColor("#E5E9F0"))
            gravity = Gravity.CENTER
            setPadding(dp(8), dp(10), dp(8), dp(6))
            setMinLines(2)
        }
        // ce face agentul ACUM (pasul real, din linia lui "+-- step NN [tool] ...")
        step = TextView(ctx).apply {
            text = ""
            textSize = 13f
            typeface = Typeface.MONOSPACE
            setTextColor(Color.parseColor("#61AFEF"))
            gravity = Gravity.CENTER
            setPadding(dp(6), 0, dp(6), dp(8))
            setMinLines(2)
        }

        // ---- butonul: cerc mare cu doua inele in jur (aspect "hardware", nu dreptunghi) ----
        ring2 = android.widget.FrameLayout(ctx).apply { setBackground(circleBg("#131A24", "#1F6F43", 1)) }
        ring1 = android.widget.FrameLayout(ctx).apply { setBackground(circleBg("#16202B", "#2E7D32", 2)) }
        btn = Button(ctx).apply {
            text = "HOLD\nTO TALK"
            textSize = 23f
            isAllCaps = false
            typeface = Typeface.create(Typeface.DEFAULT, Typeface.BOLD)
            setTextColor(Color.WHITE)
            letterSpacing = 0.12f
            background = circleBg("#2E7D32", "#43A047", 2)
            stateListAnimator = null
            minWidth = 0; minimumWidth = 0
            minimumHeight = 0; minHeight = 0
            setPadding(0, 0, 0, 0)
            setOnTouchListener { _, ev ->
                when (ev.actionMasked) {
                    android.view.MotionEvent.ACTION_DOWN -> {
                        // barge-in: vocea agentului se opreste INAINTE de a deschide microfonul,
                        // altfel inregistrarea prinde propria voce a agentului
                        onPress()
                        PhononTts.cancel()
                        pressing(true)
                        startRecording(); true
                    }
                    android.view.MotionEvent.ACTION_UP, android.view.MotionEvent.ACTION_CANCEL -> {
                        onRelease()
                        pressing(false)
                        stopRecordingAndTranscribe(); true
                    }
                    else -> true
                }
            }
        }
        ring1.addView(btn, android.widget.FrameLayout.LayoutParams(dp(190), dp(190), Gravity.CENTER))
        ring2.addView(ring1, android.widget.FrameLayout.LayoutParams(dp(224), dp(224), Gravity.CENTER))

        // controalele de iesire stau IN acest ecran: in modul audio nu se poate tasta nimic
        val exitBtn = Button(ctx).apply {
            text = "EXIT TO TEXT"
            textSize = 15f
            isAllCaps = false
            typeface = Typeface.create(Typeface.DEFAULT, Typeface.BOLD)
            setTextColor(Color.parseColor("#E5E9F0"))
            background = android.graphics.drawable.GradientDrawable().apply {
                cornerRadius = dp(14).toFloat(); setColor(Color.parseColor("#1B2028"))
                setStroke(dp(1), Color.parseColor("#2C3440"))
            }
            stateListAnimator = null
            minWidth = 0; minimumWidth = 0
            setOnClickListener { onExit() }
        }
        val stopBtn = Button(ctx).apply {
            text = "STOP VOICE"
            textSize = 13f
            isAllCaps = false
            setTextColor(Color.parseColor("#8B93A1"))
            setBackgroundColor(Color.TRANSPARENT)
            stateListAnimator = null
            minWidth = 0; minimumWidth = 0
            setOnClickListener { onStopVoice() }
        }
        container.addView(exitBtn, LinearLayout.LayoutParams(dp(190), dp(50)).apply { topMargin = dp(16) })
        container.addView(stopBtn, LinearLayout.LayoutParams(dp(190), dp(40)).apply { topMargin = dp(4) })
        dotLabel = TextView(ctx).apply {
            text = "release to send"
            textSize = 12f
            setTextColor(Color.parseColor("#7F8C8D"))
            gravity = Gravity.CENTER
            setPadding(0, dp(14), 0, 0)
        }
        langBtn = Button(ctx).apply {
            text = "\u25C9  ro"
            textSize = 13f
            typeface = Typeface.MONOSPACE
            isAllCaps = false
            setTextColor(Color.parseColor("#ABB2BF"))
            setBackgroundColor(Color.parseColor("#0B0E14"))
            stateListAnimator = null
            minWidth = 0; minimumWidth = 0
            setOnClickListener {
                if (recording) return@setOnClickListener
                lang = langs[(langs.indexOf(lang) + 1) % langs.size]
                text = "\u25C9  $lang"
            }
        }
        title.visibility = View.GONE
        container.addView(status)
        container.addView(step)
        container.addView(ring2, LinearLayout.LayoutParams(dp(224), dp(224)).apply { topMargin = dp(18) })
        container.addView(dotLabel)
        container.addView(langBtn, LinearLayout.LayoutParams(-2, -2).apply { topMargin = dp(6) })
        val lp = FrameLayout.LayoutParams(-1, -2, Gravity.BOTTOM or Gravity.CENTER_HORIZONTAL)
        lp.bottomMargin = dp(4)
        frame.addView(container, lp)
        container.bringToFront()
    }

    /** Aspectul butonului: apasat = rosu (asculta), liber = verde. */
    private fun pressing(on: Boolean) {
        act.runOnUiThread {
            btn.background = if (on) circleBg("#C0392B", "#E06C75", 3) else circleBg("#2E7D32", "#43A047", 2)
            btn.text = if (on) "LISTENING" else "HOLD\nTO TALK"
            ring1.setBackground(circleBg("#16202B", if (on) "#C0392B" else "#2E7D32", 2))
            dotLabel.text = if (on) "release to send" else "hold to speak"
        }
    }

    /** Linia de progres: ce face agentul chiar acum (apelata din MainActivity). */
    fun progress(msg: String) {
        act.runOnUiThread { if (container.visibility == View.VISIBLE) step.text = msg.take(150) }
    }

    @Volatile private var preparing = false

    fun show() {
        container.visibility = View.VISIBLE
        Thread {
            val binOk = native("libwhispercli_exec.so").exists()
            val expected = assetSize("whisper/models/ggml-$modelName.bin")
            val have = modelFile(modelName)
            val ready = have.exists() && (expected == 0L || have.length() == expected)
            if (!binOk) { act.runOnUiThread { status.text = "ERROR: whisper binary missing from the APK" }; return@Thread }
            if (ready) { act.runOnUiThread { status.text = "Ready - hold the button and speak." }; return@Thread }
            // prima folosire: extrag modelul ACUM, cu progres vizibil (nu la prima apasare)
            if (preparing) return@Thread
            preparing = true
            try { ensureModel(modelName) { m -> act.runOnUiThread { status.text = m; act.audioPanelStatus(m) } } }
            finally { preparing = false; act.runOnUiThread { if (container.visibility == View.VISIBLE) status.text = "Ready - hold the button and speak." } }
        }.start()
    }
    fun hide() {
        if (recording) stopRecordingAndTranscribe()
        container.visibility = View.GONE
    }

    // ---------------------------------------------------------- recording
    private fun startRecording() {
        if (busy.get() || recording) return
        if (ctx.checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            act.requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), 771)
            status.text = "Microphone permission is required - allow it, then hold again."
            return
        }
        val minBuf = AudioRecord.getMinBufferSize(SR, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
        if (minBuf <= 0) { status.text = "AudioRecord not available on this device."; return }
        val r = AudioRecord(MediaRecorder.AudioSource.VOICE_RECOGNITION, SR,
                AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT, minBuf * 2)
        if (r.state != AudioRecord.STATE_INITIALIZED) { status.text = "Cannot open the microphone."; r.release(); return }
        pcm.reset()
        rec = r; recording = true
        say("Listening... speak now (release to stop).", "#E06C75")
        recThread = Thread {
            val buf = ByteArray(minBuf)
            try { r.startRecording() } catch (e: Exception) { Log.w("PTT", "start: $e") }
            val t0 = System.currentTimeMillis()
            while (recording) {
                val n = try { r.read(buf, 0, buf.size) } catch (e: Exception) { -1 }
                if (n > 0) pcm.write(buf, 0, n)
                if (System.currentTimeMillis() - t0 > MAX_MS) break
            }
            try { r.stop() } catch (_: Exception) {}
            r.release()
        }.apply { isDaemon = true; start() }
    }

    private fun wavFile(samples: ByteArray): File {
        val f = File(File(ctx.cacheDir, "ptt").apply { mkdirs() }, "rec_${System.currentTimeMillis()}.wav")
        FileOutputStream(f).use { o ->
            fun le32(v: Int) = o.write(byteArrayOf((v and 0xFF).toByte(), ((v shr 8) and 0xFF).toByte(),
                    ((v shr 16) and 0xFF).toByte(), ((v shr 24) and 0xFF).toByte()))
            fun le16(v: Int) = o.write(byteArrayOf((v and 0xFF).toByte(), ((v shr 8) and 0xFF).toByte()))
            o.write("RIFF".toByteArray()); le32(36 + samples.size); o.write("WAVE".toByteArray())
            o.write("fmt ".toByteArray()); le32(16); le16(1); le16(1)
            le32(SR); le32(SR * 2); le16(2); le16(16)
            o.write("data".toByteArray()); le32(samples.size); o.write(samples)
        }
        return f
    }

    private fun stopRecordingAndTranscribe() {
        if (!recording) return
        recording = false
        try { recThread?.join(600) } catch (_: Exception) {}
        recThread = null; rec = null
        val samples = pcm.toByteArray()
        val secs = samples.size / (SR * 2.0)
        if (samples.size < MIN_SAMPLES * 2) {
            status.setTextColor(Color.parseColor("#E5C07B"))
            status.text = "Too short (%.1f s) - hold the button longer.".format(secs)
            return
        }
        say("Transcribing %.1f s with whisper %s ...".format(secs, modelName))
        busy.set(true)
        val wav = wavFile(samples)
        Thread {
            val t0 = System.currentTimeMillis()
            val text = transcribe(wav)
            val ms = System.currentTimeMillis() - t0
            act.runOnUiThread {
                busy.set(false)
                val clean = text.lines().map { it.trim() }
                        .filter { it.isNotEmpty() && !it.startsWith("[") && !it.startsWith("(") }
                        .joinToString(" ").trim()
                when {
                    clean.isEmpty() -> {
                        status.setTextColor(Color.parseColor("#E5C07B"))
                        status.text = "(no speech recognised in %.1f s - whisper %s, %d ms)".format(secs, modelName, ms)
                    }
                    else -> {
                        status.setTextColor(Color.parseColor("#98C379"))
                        status.text = clean
                        onText(clean)
                    }
                }
            }
        }.apply { isDaemon = true; start() }
    }

    // ------------------------------------------------------- transcription
    private fun transcribe(wav: File): String {
        val bin = native("libwhispercli_exec.so")
        if (!bin.exists()) return "ERROR: whisper binary missing (${bin.name})"
        val model = ensureModel(modelName) { s -> act.runOnUiThread { status.text = s } }
                ?: return "ERROR: model ggml-$modelName.bin is not bundled in this build"
        val cmd = listOf(bin.absolutePath, "-m", model.absolutePath, "-f", wav.absolutePath,
                "-t", "6", "-np", "-nt") + if (lang == "auto") emptyList() else listOf("-l", lang)
        return try {
            val pb = ProcessBuilder(cmd)
            pb.directory(ctx.cacheDir)
            pb.environment()["LD_LIBRARY_PATH"] = ctx.applicationInfo.nativeLibraryDir
            pb.redirectErrorStream(false)
            val p = pb.start()
            val out = StringBuilder()
            val err = StringBuilder()
            val to = Thread { p.inputStream.bufferedReader().forEachLine { out.append(it).append('\n') } }.apply { isDaemon = true; start() }
            val te = Thread { p.errorStream.bufferedReader().forEachLine { err.append(it) } }.apply { isDaemon = true; start() }
            val finished = p.waitFor(180, java.util.concurrent.TimeUnit.SECONDS)
            if (!finished) { p.destroyForcibly(); return "ERROR: whisper timed out (180 s)" }
            to.join(2000); te.join(2000)
            wav.delete()
            val txt = out.toString().trim()
            if (txt.isEmpty()) {
                Log.w("PTT", "empty; stderr=${err.take(400)}")
                ""
            } else txt
        } catch (e: Exception) {
            "ERROR: ${e.message}"
        }
    }
}
