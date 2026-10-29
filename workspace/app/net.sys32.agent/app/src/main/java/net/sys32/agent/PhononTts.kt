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
    @Volatile private var lastWav: File? = null
    @Volatile private var ctxRef: Context? = null

    fun isBusy() = busy.get()
    fun cancel() {
        cancel.set(true)
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
    fun speak(ctx: Context, text: String, onState: (String) -> Unit) {
        val clean = cleanText(text)
        if (clean.isEmpty()) { onState("nimic de citit"); return }
        if (!busy.compareAndSet(false, true)) { onState("deja vorbeste"); return }
        cancel.set(false)
        ctxRef = ctx.applicationContext
        exec.execute {
            var track: android.media.AudioTrack? = null
            try {
                onState("pregatesc modelul...")
                ensureModel(ctx)
                val bin = binPath(ctx)
                if (!bin.exists()) { onState("lipsește binarul: " + bin.path); return@execute }

                val sr = 24000
                track = android.media.AudioTrack.Builder()
                    .setAudioAttributes(android.media.AudioAttributes.Builder()
                        .setUsage(android.media.AudioAttributes.USAGE_MEDIA)
                        .setContentType(android.media.AudioAttributes.CONTENT_TYPE_SPEECH).build())
                    .setAudioFormat(android.media.AudioFormat.Builder()
                        .setEncoding(android.media.AudioFormat.ENCODING_PCM_16BIT)
                        .setSampleRate(sr)
                        .setChannelMask(android.media.AudioFormat.CHANNEL_OUT_MONO).build())
                    .setBufferSizeInBytes(sr * 2 * 4)   // ~4 s de buffer
                    .setTransferMode(android.media.AudioTrack.MODE_STREAM).build()
                    track.play()
                    requestFocus(ctx)

                val t0 = System.currentTimeMillis()
                // TOT textul dintr-o singura bucata: engine-ul citeste pana la ultimul cuvant
                val pb = ProcessBuilder(bin.absolutePath, modelDir(ctx).absolutePath, LANG, "-", clean, "-")
                pb.environment()["LD_LIBRARY_PATH"] = ctx.applicationInfo.nativeLibraryDir + ":" +
                        pb.environment()["LD_LIBRARY_PATH"].orEmpty()
                pb.redirectErrorStream(false)
                val p = pb.start()
                var firstAt = 0L
                var total = 0L
                val saved = java.io.ByteArrayOutputStream()
                p.inputStream.use { ins ->
                    val buf = ByteArray(4800)          // 100 ms la 24 kHz s16
                    var n: Int
                    while (ins.read(buf).also { n = it } > 0) {
                        if (cancel.get()) break
                        if (firstAt == 0L) {
                            firstAt = System.currentTimeMillis() - t0
                            onState("redau (primul sunet dupa %.0f ms)".format(firstAt.toDouble()))
                        }
                        // WRITE_BLOCKING scrie TOT sau cat incape; restul trebuie trimis in bucla,
                        // altfel esantioanele ramase se pierd si sunetul "se opreste" la mijloc.
                        var off = 0
                        while (off < n) {
                            val w = track.write(buf, off, n - off, android.media.AudioTrack.WRITE_BLOCKING)
                            if (w <= 0) break
                            off += w
                        }
                        saved.write(buf, 0, n)
                        total += n
                    }
                }
                val errText = p.errorStream.bufferedReader().readText().trim()
                p.waitFor()
                if (errText.isNotEmpty()) android.util.Log.i(TAG, "binar: " + errText.take(200))
                track.stop(); track.release(); track = null
                abandonFocus(ctx)
                writeWavFromPcm(saved.toByteArray())
                val audioSec = total / 2.0 / 24000.0
                onState("gata: %.1fs audio, primul sunet in %.0f ms".format(
                    audioSec, (if (firstAt == 0L) 0L else firstAt).toDouble()))
            } catch (t: Throwable) {
                android.util.Log.e(TAG, "eroare", t)
                onState("eroare: " + (t.message ?: t.javaClass.simpleName))
            } finally {
                runCatching { track?.stop(); track?.release() }
                busy.set(false)
            }
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
