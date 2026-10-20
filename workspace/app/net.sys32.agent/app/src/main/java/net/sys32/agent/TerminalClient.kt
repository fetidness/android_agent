package net.sys32.agent

import android.os.FileObserver
import java.io.File

/**
 * Client de terminal pentru UI - prin FISIERE de comanda/raspuns, cu SESIUNI MULTIPLE.
 *
 * ★ De ce fisiere si nu socket: `untrusted_app` nu poate execve nimic din app_data_file
 * (SELinux W^X), iar /data/data e montat NOEXEC. Executia trebuie sa treaca prin
 * adb_client, care exista doar in procesul agentului. Fisierele sunt canalul cel
 * mai simplu (zero protocol duplicat in Kotlin).
 *
 * Canal (o pereche de fisiere PER SESIUNE):
 *   files/tmp/term_in.txt          <- "0|1" + 0x01 + comanda + 0x02 + <sid>   (UI scrie)
 *   files/tmp/term_out_<sid>.txt   ->  prompt + output                          (agent scrie)
 *
 * Butonul "+" creeaza un sid nou => un terminal nou, independent.
 */
class TerminalClient(private val listener: Listener) {

    interface Listener {
        fun onCreated(id: Int, pid: Int)
        fun onData(id: Int, bytes: ByteArray)
        fun onExit(id: Int, code: Int)
        fun onSessions(list: List<Triple<Int, String, Int>>)
        fun onError(msg: String)
        fun onDisconnected()
    }

    companion object {
        const val HOME = "/data/data/net.sys32.agent/files"
        const val SEP_CMD = "\u0001"     // separator flag/comanda
        const val SEP_SID = "\u0002"     // separator comanda/session-id
        val IN: File get() = File(HOME, "tmp/term_in.txt")
        fun outFile(sid: Int) = File(HOME, "tmp/term_out_$sid.txt")
    }

    @Volatile private var running = false
    private var watcher: FileObserver? = null
    private val offsets = HashMap<Int, Long>()      // sid -> bytes deja citite
    private var nextSid = 1

    fun connect() {
        running = true
        try {
            IN.parentFile?.mkdirs()
        } catch (_: Exception) {}
        // o singura "sesiune" implicita, apoi fiecare "+" adauga una
        newSession("bash", false, 80, 24)
        Thread({
            while (running) {
                try { Thread.sleep(350) } catch (_: InterruptedException) { break }
                pump()
            }
        }, "term-poll").apply { isDaemon = true }.start()
    }

    /** citeste noile bytes din TOATE fisierele de output si le trimite pe sid */
    private fun pump() {
        if (!running) return
        for (sid in offsets.keys.toList()) {
            try {
                val f = outFile(sid)
                if (!f.exists()) continue
                val len = f.length()
                val off = offsets[sid] ?: 0L
                if (len < off) { offsets[sid] = 0L; continue }   // trunchiat
                if (len == off) continue
                val all = f.readBytes()
                val fresh = all.copyOfRange(off.toInt(), all.size)
                offsets[sid] = len
                if (fresh.isNotEmpty()) listener.onData(sid, fresh)
            } catch (_: Exception) {}
        }
    }

    /** creeaza o sesiune noua (un terminal nou) si intoarce id-ul */
    fun newSession(name: String, uid2000: Boolean, cols: Int, rows: Int): Int {
        val sid = nextSid++
        try {
            val f = outFile(sid)
            f.parentFile?.mkdirs()
            f.writeText("Terminal $sid (" + (if (uid2000) "uid 2000" else "Debian root") +
                    ")\r\nScrie o comanda si apasa Enter.\r\n\r\n")
            offsets[sid] = f.length()
        } catch (e: Exception) {
            listener.onError(e.message ?: "cannot create session")
        }
        listener.onCreated(sid, -1)
        return sid
    }

    /** trimite o comanda catre sesiunea data */
    fun sendCommand(sid: Int, cmd: String, uid2000: Boolean) {
        try {
            IN.parentFile?.mkdirs()
            // ★ 3 linii separate (flag / sid / comanda): separatorii cu \x01 \x02 se
            // rupeau la .strip() si la citirea pe linii (bug: comenzile nu ajungeau).
            // Comanda e ULTIMA, deci poate contine orice (inclusiv spatii multiple).
            // nonce pe ultima linie: acelasi `ls` de doua ori => fisier DIFERIT,
            // deci worker-ul il executa de fiecare data (nu se blocheaza pe egalitate)
            val nonce = System.nanoTime()
            IN.writeText((if (uid2000) "1" else "0") + "\n" + sid + "\n" + cmd + "\n" + nonce + "\n")
        } catch (e: Exception) {
            listener.onError(e.message ?: "write failed")
        }
    }

    fun writeText(id: Int, text: String) {
        for (line in text.replace("\r", "\n").split("\n")) {
            val cmd = line.filter { it.code in 32..126 || it.code > 160 }.trim()
            if (cmd.isEmpty()) continue
            sendCommand(id, cmd, uid2000 = false)
        }
    }

    fun write(id: Int, data: ByteArray) = writeText(id, String(data, Charsets.UTF_8))
    fun resize(id: Int, cols: Int, rows: Int) {}

    fun close(id: Int) {
        offsets.remove(id)
        try { outFile(id).delete() } catch (_: Exception) {}
    }

    fun list() {}

    fun shutdown() {
        running = false
        try { watcher?.stopWatching() } catch (_: Exception) {}
    }
}
