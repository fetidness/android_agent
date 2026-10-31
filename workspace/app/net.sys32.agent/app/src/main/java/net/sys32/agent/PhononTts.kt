package net.sys32.agent

import android.content.Context
import android.media.MediaPlayer
import java.io.File
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Voce offline in aplicatie: binarul nativ ptts-mini (Rust, livrat ca libptts_exec.so) ruleaza
 * intr-un proces separat, scrie un WAV, iar aplicatia il reda cu MediaPlayer.
 * Nu depinde de JNI: singurul lucru dovedit stabil pe acest device.
 */
object PhononTts {
    private const val TAG = "PhononTts"
    private const val LANG = "en"
    private const val MODEL = "phonon-31m-en"

    private val exec = Executors.newSingleThreadExecutor { r -> Thread(r, "phonon-tts").apply { priority = Thread.NORM_PRIORITY } }
    private val busy = AtomicBoolean(false)
    private val cancel = AtomicBoolean(false)
    @Volatile private var player: MediaPlayer? = null
    @Volatile private var track: android.media.AudioTrack? = null
    @Volatile private var proc: Process? = null
    @Volatile private var lastWav: File? = null
    @Volatile private var ctxRef: Context? = null

    fun isBusy() = busy.get()
    fun cancel() {
        cancel.set(true)
        queue.clear()                                  // nimic vechi nu mai pleacă
        runCatching { proc?.destroyForcibly() }; proc = null
        // oprirea redării trebuie să fie INSTANTANEE: stop() lasă în buffer până la ~4 s
        runCatching { track?.pause(); track?.flush(); track?.stop() }
        runCatching { player?.stop(); player?.release() }
        player = null
    }
    fun lastWavPath(): String? = lastWav?.path
    fun isReady(ctx: Context) = File(modelDir(ctx), "model.q8.gguf").exists()

    private fun modelDir(ctx: Context) = File(File(ctx.filesDir, "models"), MODEL)
    private fun binPath(ctx: Context) = File(ctx.applicationInfo.nativeLibraryDir, "libptts_exec.so")
    private fun libPath(ctx: Context) = File(ctx.applicationInfo.nativeLibraryDir, "libptts_ffi.so")
    private fun outDir(ctx: Context) = File(ctx.filesDir, "tts").apply { mkdirs() }

    /** Copiaza modelul (63 MB) din assets in filesDir daca nu e deja acolo. */
    fun ensureModel(ctx: Context) {
        val dir = modelDir(ctx)
        if (File(dir, "model.q8.gguf").exists()) return
        dir.mkdirs()
        copyAssetDir(ctx, "models/$MODEL", dir)
        File(dir, ".ok").writeText("1")
    }

    private fun copyAssetDir(ctx: Context, assetPath: String, dst: File) {
        val kids = ctx.assets.list(assetPath) ?: return
        if (kids.isEmpty()) {
            dst.parentFile?.mkdirs()
            ctx.assets.open(assetPath).use { i -> dst.outputStream().use { o -> i.copyTo(o, 1 shl 16) } }
            return
        }
        dst.mkdirs()
        for (k in kids) copyAssetDir(ctx, "$assetPath/$k", File(dst, k))
    }

    /**
     * Spune [text] in streaming: binarul scrie PCM pe stdout pe masura ce il genereaza,
     * iar noi il redam imediat in AudioTrack. Primul sunet apare dupa ~1-2 s, nu dupa
     * ce se termina tot textul.
     */
    /** Cerere de rostit, in ordine. A doua intra in coada si pleaca dupa prima. */
    private class Item(val text: String, val onState: (String) -> Unit)
    private val queue = java.util.concurrent.LinkedBlockingQueue<Item>()
    @Volatile private var workerRunning = false

    /** Adauga textul in coada de rostit. NU il pierde daca vorba e ocupata. */
    fun speak(ctx: Context, text: String, onState: (String) -> Unit) {
        val clean = cleanText(text)
        if (clean.isEmpty()) { onState("nothing to read"); return }
        ctxRef = ctx.applicationContext
        queue.offer(Item(clean, onState))
        onState("queued (" + queue.size + ")")
        startWorkerIfNeeded(ctx)
    }

    private fun startWorkerIfNeeded(ctx: Context) {
        synchronized(this) {
            if (workerRunning) return
            workerRunning = true
        }
        exec.execute {
            try {
                while (true) {
                    val item = queue.poll() ?: break
                    busy.set(true)
                    try { speakOne(ctx, item.text, item.onState) }
                    finally { busy.set(false) }
                }
            } finally {
                synchronized(this) { workerRunning = false }
                if (queue.isNotEmpty()) startWorkerIfNeeded(ctx)   // a intrat ceva intre timp
            }
        }
    }

    private fun speakOne(ctx: Context, clean: String, onState: (String) -> Unit) {
        cancel.set(false)
        runBlockingSpeech(ctx, clean, onState)
    }

    private fun runBlockingSpeech(ctx: Context, clean: String, onState: (String) -> Unit) {
        try {
            onState("preparing model...")
            ensureModel(ctx)
            val bin = binPath(ctx)
            if (!bin.exists()) { onState("missing binary: " + bin.path); return }

            // iesirea cere 48 kHz pe acest device: redau la 48k si dublez esantioanele (24k -> 48k)
            val srOut = 48000
            val tr0 = android.media.AudioTrack.Builder()
                .setAudioAttributes(android.media.AudioAttributes.Builder()
                    .setUsage(android.media.AudioAttributes.USAGE_MEDIA)
                    .setContentType(android.media.AudioAttributes.CONTENT_TYPE_SPEECH).build())
                .setAudioFormat(android.media.AudioFormat.Builder()
                    .setEncoding(android.media.AudioFormat.ENCODING_PCM_16BIT)
                    .setSampleRate(srOut)
                    .setChannelMask(android.media.AudioFormat.CHANNEL_OUT_MONO).build())
                .setBufferSizeInBytes(
                    (android.media.AudioTrack.getMinBufferSize(srOut,
                        android.media.AudioFormat.CHANNEL_OUT_MONO,
                        android.media.AudioFormat.ENCODING_PCM_16BIT) * 2).coerceAtLeast(4096))
                .setTransferMode(android.media.AudioTrack.MODE_STREAM).build()
            track = tr0
            requestFocus(ctx)

            val t0 = System.currentTimeMillis()
            val pb = ProcessBuilder(bin.absolutePath, modelDir(ctx).absolutePath, LANG, "-", clean, "-")
            pb.environment()["LD_LIBRARY_PATH"] = ctx.applicationInfo.nativeLibraryDir + ":" +
                    pb.environment()["LD_LIBRARY_PATH"].orEmpty()
            pb.redirectErrorStream(false)
            val p = pb.start()
            proc = p
            var firstAt = 0L
            var total = 0L
            var started = false
            val saved = java.io.ByteArrayOutputStream()

            p.inputStream.use { ins ->
                val chunk = ByteArray(4800)                 // 100 ms la 24 kHz s16
                val up = ByteArray(9600)                    // acelasi bloc, upsamplat la 48 kHz
                var n: Int
                while (ins.read(chunk).also { n = it } > 0) {
                    if (cancel.get()) break
                    saved.write(chunk, 0, n)
                    total += n
                    // 24k -> 48k: fiecare esantion s16 scris de doua ori
                    var a2 = 0
                    var u2 = 0
                    while (a2 + 1 < n) {
                        up[u2] = chunk[a2]; up[u2 + 1] = chunk[a2 + 1]
                        up[u2 + 2] = chunk[a2]; up[u2 + 3] = chunk[a2 + 1]
                        a2 += 2; u2 += 4
                    }
                    var off = 0
                    while (off < u2 && !cancel.get()) {
                        val w = tr0.write(up, off, u2 - off, android.media.AudioTrack.WRITE_NON_BLOCKING)
                        if (w > 0) {
                            off += w
                            if (!started) {
                                // pornim DOAR cand bufferul are date: play() pe gol = underrun instant
                                tr0.play()
                                started = true
                                firstAt = System.currentTimeMillis() - t0
                                onState("playing (first sound after %.0f ms)".format(firstAt.toDouble()))
                            }
                            continue
                        }
                        if (cancel.get()) break
                        Thread.sleep(5)
                    }
                }
            }

            val errText = p.errorStream.bufferedReader().readText().trim()
            if (errText.isNotEmpty()) android.util.Log.i(TAG, "binar: " + errText.take(200))
            // las bufferul sa se dreneze in timp real inainte de stop()
            val framesOut = (saved.size() / 2) * 2
            val deadline = System.currentTimeMillis() + (framesOut / 48.0).toLong() + 2000
            while (!cancel.get() && System.currentTimeMillis() < deadline) {
                val head = try { tr0.playbackHeadPosition } catch (_: Exception) { -1 }
                if (head >= framesOut - 960) break
                Thread.sleep(20)
            }
            android.util.Log.i(TAG, "playhead final=" +
                (try { tr0.playbackHeadPosition } catch (_: Exception) { -1 }) + "/" + framesOut)
            runCatching { tr0.stop() }; runCatching { tr0.release() }
            track = null
            abandonFocus(ctx)
            if (cancel.get()) { onState("cancelled"); return }
            writeWavFromPcm(saved.toByteArray())
            val audioSec = total / 2.0 / 24000.0
            onState("done: %.1fs audio, first sound in %.0f ms".format(
                audioSec, (if (firstAt == 0L) 0L else firstAt).toDouble()))
        } catch (t: Throwable) {
            android.util.Log.e(TAG, "eroare", t)
            onState("error: " + (t.message ?: t.javaClass.simpleName))
        } finally {
            runCatching { track?.release() }
            track = null
            proc?.let { if (!cancel.get()) runCatching { it.waitFor(3000, java.util.concurrent.TimeUnit.MILLISECONDS) } }
            proc = null
        }
    }

    /** Salveaza ultimul audio in filesDir/tts/tts_last.wav (pentru verificare). */
    private fun writeWavFromPcm(pcm: ByteArray) {
        runCatching {
            val f = File(outDir(ctxRef ?: return), "tts_last.wav")
            java.io.DataOutputStream(f.outputStream().buffered()).use { d ->
                fun le32(v: Int) = d.write(byteArrayOf((v and 0xFF).toByte(), ((v shr 8) and 0xFF).toByte(), ((v shr 16) and 0xFF).toByte(), ((v shr 24) and 0xFF).toByte()))
                fun le16(v: Int) = d.write(byteArrayOf((v and 0xFF).toByte(), ((v shr 8) and 0xFF).toByte()))
                d.writeBytes("RIFF"); le32(36 + pcm.size); d.writeBytes("WAVE"); d.writeBytes("fmt ")
                le32(16); le16(1); le16(1); le32(24000); le32(48000); le16(2); le16(16)
                d.writeBytes("data"); le32(pcm.size); d.write(pcm)
            }
            lastWav = f
        }
    }

    @Volatile private var focusRequest: android.media.AudioFocusRequest? = null

    /** Cere focus audio: fara el, un alt player (sau sistemul) poate reteza redarea. */
    private fun requestFocus(ctx: Context) {
        runCatching {
            val am = ctx.getSystemService(Context.AUDIO_SERVICE) as android.media.AudioManager
            val attrs = android.media.AudioAttributes.Builder()
                .setUsage(android.media.AudioAttributes.USAGE_MEDIA)
                .setContentType(android.media.AudioAttributes.CONTENT_TYPE_SPEECH).build()
            val req = android.media.AudioFocusRequest.Builder(android.media.AudioManager.AUDIOFOCUS_GAIN_TRANSIENT_MAY_DUCK)
                .setAudioAttributes(attrs)
                .setOnAudioFocusChangeListener { ch -> android.util.Log.i(TAG, "focus change: " + ch) }
                .build()
            focusRequest = req
            val ok = am.requestAudioFocus(req)
            android.util.Log.i(TAG, "audio focus -> " + ok)
        }
    }

    private fun abandonFocus(ctx: Context) {
        runCatching {
            val am = ctx.getSystemService(Context.AUDIO_SERVICE) as android.media.AudioManager
            focusRequest?.let { am.abandonAudioFocusRequest(it) }
            focusRequest = null
        }
    }

    private fun wavDurationMs(f: File): Long = runCatching {
        // 24 kHz mono s16: bytes duplicate / 48000 octeti pe secunda
        ((f.length() - 44) / 48000.0 * 1000).toLong().coerceAtLeast(0)
    }.getOrDefault(0)

    private fun playBlocking(ctx: Context, f: File) {
        val mp = MediaPlayer()
        player = mp
        // fara atribut de vorbire, sistemul il vede ca USAGE_UNKNOWN (dumpsys) si trateaza
        // sunetul ca zgomot de fundal
        mp.setAudioAttributes(android.media.AudioAttributes.Builder()
            .setUsage(android.media.AudioAttributes.USAGE_MEDIA)
            .setContentType(android.media.AudioAttributes.CONTENT_TYPE_SPEECH)
            .build())
        mp.setDataSource(f.absolutePath)
        mp.prepare()
        val done = java.util.concurrent.CountDownLatch(1)
        mp.setOnCompletionListener { done.countDown() }
        mp.setOnErrorListener { _, w, e -> android.util.Log.e(TAG, "MediaPlayer err $w/$e"); done.countDown(); true }
        mp.start()
        done.await(60, java.util.concurrent.TimeUnit.SECONDS)
        runCatching { mp.stop(); mp.release() }
        player = null
    }

    /** Imparte textul in bucati de propozitii, grupate pana la ~35 de cuvinte. */
    fun splitForSpeech(text: String, maxWords: Int = 35): List<String> {
        // normalizez intai: liniile noi si spatiile multiple devin un singur spatiu, altfel
        // regex-ul de propozitii trateaza un bloc intreg ca o singura "propozitie"
        val flat = text.replace(Regex("\\s+"), " ").trim()
        if (flat.isEmpty()) return emptyList()
        val sentences = Regex("[^.!?]+[.!?]*").findAll(flat).map { it.value.trim() }
            .filter { it.isNotEmpty() }.toList()
        val out = ArrayList<String>()
        val cur = ArrayList<String>()
        fun flush() { if (cur.isNotEmpty()) { out.add(cur.joinToString(" ")); cur.clear() } }
        for (sent in sentences) {
            val words = sent.split(" ").filter { it.isNotEmpty() }
            if (words.isEmpty()) continue
            if (words.size > maxWords) {
                // propozitie prea lunga: o rup in bucati de maxWords cuvinte
                flush()
                var k = 0
                while (k < words.size) {
                    val end = minOf(k + maxWords, words.size)
                    out.add(words.subList(k, end).joinToString(" "))
                    k = end
                }
                continue
            }
            if (cur.size + words.size > maxWords) flush()
            cur.addAll(words)
        }
        flush()
        return if (out.isEmpty()) listOf(flat) else out
    }

    /** Textul generat, curatat pentru citire: fara markdown, cod si linkuri. */
    fun cleanText(raw: String): String = raw
        .replace(Regex("```[\\s\\S]*?```"), " ")
        .replace(Regex("`[^`]*`"), " ")
        .replace(Regex("\\[([^\\]]*)]\\([^)]*\\)"), "$1")
        .replace(Regex("[#*_>|]+"), " ")
        .replace(Regex("\\s+"), " ")
        .trim()   // fara limita de caractere: se rosteste TOT textul primit
}
