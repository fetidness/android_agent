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

    private fun ensureModel(name: String, say: (String) -> Unit): File? {
        val f = modelFile(name)
        if (f.exists() && f.length() > 100_000_000L) return f
        f.parentFile?.mkdirs()
        if (f.exists()) f.delete()
        val tmp = File(f.parentFile, f.name + ".part")
        try {
            ctx.assets.open("whisper/models/ggml-$name.bin").use { inp ->
                val bos = java.io.BufferedOutputStream(FileOutputStream(tmp), 1 shl 20)
                val buf = ByteArray(1 shl 20)
                var lastPct = -10
                var done = 0L
                val total = inp.available().toLong().coerceAtLeast(1L)
                while (true) {
                    val n = inp.read(buf); if (n <= 0) break
                    bos.write(buf, 0, n); done += n
                    val pct = (done * 100 / total).toInt()
                    if (pct >= lastPct + 10) { lastPct = pct; say("unpacking whisper $name: $pct%") }
                }
                bos.flush(); bos.close()
            }
            if (!tmp.renameTo(f)) { tmp.copyTo(f, overwrite = true); tmp.delete() }
            return f
        } catch (e: Exception) {
            Log.w("PTT", "model asset missing for $name: $e")
            tmp.delete()
            return null
        }
    }

    // ---------------------------------------------------------------- UI
    fun build(frame: FrameLayout) {
        container = LinearLayout(ctx).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setBackgroundColor(Color.parseColor("#0D1117"))
            visibility = View.GONE
            setPadding(dp(20), dp(20), dp(20), dp(20))
        }
        val title = TextView(ctx).apply {
            text = "PUSH TO TALK"
            textSize = 20f
            typeface = Typeface.DEFAULT_BOLD
            setTextColor(Color.parseColor("#98C379"))
            gravity = Gravity.CENTER
        }
        status = TextView(ctx).apply {
            text = "Ready - hold the button and speak."
            textSize = 15f
            setTextColor(Color.parseColor("#61AFEF"))
            gravity = Gravity.CENTER
            setPadding(0, dp(14), 0, dp(14))
            setMinLines(2)
        }
        // doc 5.1: use a Button for anything that must be reliably readable (styled
        // TextView did not rasterise its glyphs on this device).
        btn = Button(ctx).apply {
            text = "HOLD\nTO TALK"
            textSize = 22f
            isAllCaps = false
            setTextColor(Color.WHITE)
            setBackgroundColor(Color.parseColor("#2E7D32"))
            minWidth = 0; minimumWidth = 0
            setOnTouchListener { _, ev ->
                when (ev.actionMasked) {
                    android.view.MotionEvent.ACTION_DOWN -> {
                        // barge-in: vocea agentului se opreste INAINTE de a deschide microfonul,
                        // altfel inregistrarea prinde propria voce a agentului
                        onPress()
                        PhononTts.cancel()
                        startRecording(); true
                    }
                    android.view.MotionEvent.ACTION_UP, android.view.MotionEvent.ACTION_CANCEL -> {
                        onRelease()
                        stopRecordingAndTranscribe(); true
                    }
                    else -> true
                }
            }
        }
        langBtn = Button(ctx).apply {
            text = "language: ro  (tap to change)"
            textSize = 13f
            typeface = Typeface.MONOSPACE
            isAllCaps = false
            setTextColor(Color.parseColor("#ABB2BF"))
            setBackgroundColor(Color.TRANSPARENT)
            minWidth = 0; minimumWidth = 0
            setOnClickListener {
                if (recording) return@setOnClickListener
                lang = langs[(langs.indexOf(lang) + 1) % langs.size]
                text = "language: $lang  (tap to change)"
            }
        }
        val hint = TextView(ctx).apply {
            text = "Release to transcribe. Type /audio off for text mode."
            textSize = 12f
            setTextColor(Color.parseColor("#5C6370"))
            gravity = Gravity.CENTER
            setPadding(0, dp(10), 0, 0)
        }
        container.addView(title)
        container.addView(status)
        container.addView(btn, LinearLayout.LayoutParams(dp(220), dp(220)))
        container.addView(langBtn)
        container.addView(hint)
        frame.addView(container, FrameLayout.LayoutParams(-1, -1))
        container.elevation = dp(20).toFloat()
        container.bringToFront()
    }

    fun show() {
        container.visibility = View.VISIBLE
        Thread {
            val binOk = native("libwhispercli_exec.so").exists()
            val mOk = modelFile(modelName).exists()
            act.runOnUiThread {
                if (!binOk) status.text = "ERROR: whisper binary missing from the APK"
                else if (!mOk) status.text = "unpacking whisper $modelName on first use (one time)..."
            }
        }.apply { isDaemon = true; start() }
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
