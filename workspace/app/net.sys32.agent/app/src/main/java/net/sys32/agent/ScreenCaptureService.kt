package net.sys32.agent

import android.app.*
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.hardware.display.DisplayManager
import android.hardware.display.VirtualDisplay
import android.media.ImageReader
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.os.Build
import android.os.IBinder
import java.io.File
import java.io.FileOutputStream

// FIX 5: MediaProjection in foreground service => captura de ecran continua
// (nu doar cadre izolate), fara limita de ~5s/iteratie din activitate.
// Flux: MainActivity cere consimtamant (createScreenCaptureIntent) -> trimite
// resultCode+data aici -> serviciul porneste VirtualDisplay in fond.
class ScreenCaptureService : Service() {

    companion object {
        const val EXTRA_CODE = "code"
        const val EXTRA_DATA = "data"
        const val CH_ID = "agent_capture"
        const val NOTIF_ID = 1002
        const val ACTION_STOP = "net.sys32.agent.CAPTURE_STOP"
        /** BATERIE: inchide sesiunea dupa 3 min fara nicio captura. */
        const val IDLE_MS = 3 * 60 * 1000L

        @Volatile var instance: ScreenCaptureService? = null
        @Volatile var ready = false

        fun start(ctx: Context, code: Int, data: Intent) {
            val i = Intent(ctx, ScreenCaptureService::class.java)
                .putExtra(EXTRA_CODE, code)
                .putExtra(EXTRA_DATA, data)
            if (Build.VERSION.SDK_INT >= 26) ctx.startForegroundService(i) else ctx.startService(i)
        }
        fun stop(ctx: Context) {
            // stopService() nu trece prin onStartCommand -> onStop() ar afisa "de sistem".
            // Il marcam de aici ca oprire VOLUNTARA, apoi anuntam pe ecran.
            try { instance?.let { it.markSilent(); ctx.stopService(Intent(ctx, ScreenCaptureService::class.java)) } } catch (_: Exception) {}
            MainActivity.logLine("\n[capture] MediaProjection stopped (on request)\n")
        }
    }

    private var projection: MediaProjection? = null
    private var vd: VirtualDisplay? = null
    private var reader: ImageReader? = null
    private var w = 1080; private var h = 2340; private var dpi = 450
    // BATERIE: momentul ultimei capturi. Un VirtualDisplay randeaza 1080x2340@60fps
    // NON-STOP cit timp e viu; daca nimeni nu citeste din el, e consum pur pierdut.
    @Volatile private var lastUse = 0L
    // ca sa nu dublam mesajul pe ecran: cand cerem noi oprirea, onStop() nu mai anunta
    @Volatile private var silentStop = false
    private val idleThread = object : Thread() {
        override fun run() {
            while (true) {
                try { Thread.sleep(30_000) } catch (_: InterruptedException) { return }
                if (ready && lastUse > 0 && System.currentTimeMillis() - lastUse > IDLE_MS) {
                    silentStop = true
                    cleanup(); stopSelf()
                    MainActivity.logLine("\n[capture] MediaProjection STOPPED (3 min without captures) - battery saving\n")
                    return
                }
            }
        }
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        instance = this
        startFg()
        if (intent?.action == ACTION_STOP) {
            silentStop = true
            cleanup(); stopSelf()
            MainActivity.logLine("\n[capture] MediaProjection stopped (on request)\n")
            return START_NOT_STICKY
        }
        val code = intent?.getIntExtra(EXTRA_CODE, 0) ?: 0
        @Suppress("DEPRECATION")
        val data = intent?.getParcelableExtra<Intent>(EXTRA_DATA)
        if (code != 0 && data != null) begin(code, data)
        // BATERIE: NU START_STICKY - o repornire fara date recrea un VirtualDisplay
        // orfan (scurgere de 2 display-uri "agent-capture"). Fara consimtamant, nu pornim.
        return START_NOT_STICKY
    }

    private fun startFg() {
        try {
            if (Build.VERSION.SDK_INT >= 26) {
                val nm = getSystemService(NotificationManager::class.java)
                if (nm.getNotificationChannel(CH_ID) == null)
                    nm.createNotificationChannel(NotificationChannel(CH_ID, "Agent capture", NotificationManager.IMPORTANCE_LOW))
                val n = Notification.Builder(this, CH_ID)
                    .setContentTitle("Agent capture")
                    .setContentText("Captura ecran activa")
                    .setSmallIcon(android.R.drawable.ic_menu_camera)
                    .setOngoing(true).build()
                startForeground(NOTIF_ID, n)
            }
        } catch (_: Exception) {}
    }

    private fun begin(code: Int, data: Intent) {
        try {
            // BATERIE/FIX scurgere: daca exista deja o sesiune, o inchidem COMPLET
            // inainte de a crea una noua (altfel raman display-uri orfane in SurfaceFlinger).
            if (projection != null || vd != null) { try { cleanup() } catch (_: Exception) {} }
            val mpm = getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
            projection = mpm.getMediaProjection(code, data)
            // Android 14+: obligatoriu registerCallback inainte de createVirtualDisplay,
            // altfel createVirtualDisplay arunca IllegalStateException.
            projection!!.registerCallback(object : MediaProjection.Callback() {
                override fun onStop() {
                    ready = false
                    if (!silentStop) MainActivity.logLine("\n[capture] MediaProjection stopped (session closed by the system)\n")
                }
            }, android.os.Handler(android.os.Looper.getMainLooper()))
            val dm = resources.displayMetrics
            w = dm.widthPixels; h = dm.heightPixels; dpi = dm.densityDpi
            reader = ImageReader.newInstance(w, h, android.graphics.PixelFormat.RGBA_8888, 2)
            vd = projection!!.createVirtualDisplay(
                "agent-capture", w, h, dpi,
                DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR, reader!!.surface, null, null
            )
            ready = true
            silentStop = false
            lastUse = System.currentTimeMillis()
            // BATERIE: daca nimeni nu cere o captura 3 minute, inchidem sesiunea singuri.
            if (!idleThread.isAlive) { idleThread.isDaemon = true; idleThread.start() }
        } catch (_: Exception) { ready = false }
    }

    // Grabs the most recent frame into a PNG file. Returns the path or error.
    fun grab(path: String): String {
        lastUse = System.currentTimeMillis()
        return try {
            val r = reader ?: return "error: no reader"
            var img = r.acquireLatestImage()
            var tries = 0
            while (img == null && tries < 30) { Thread.sleep(30); img = r.acquireLatestImage(); tries++ }
            if (img == null) return "error: no frame"
            val plane = img.planes[0]
            val rowStride = plane.rowStride
            val pixStride = plane.pixelStride
            val rowPadding = rowStride - pixStride * w
            val bmp = Bitmap.createBitmap(w + rowPadding / pixStride, h, Bitmap.Config.ARGB_8888)
            bmp.copyPixelsFromBuffer(plane.buffer)
            val cropped = Bitmap.createBitmap(bmp, 0, 0, w, h)
            img.close()
            val f = File(path); f.parentFile?.mkdirs()
            FileOutputStream(f).use { cropped.compress(Bitmap.CompressFormat.PNG, 100, it) }
            "$path:${f.length()}"
        } catch (e: Exception) { "error: $e" }
    }

    /** Marcheaza oprirea ca voluntara (nu anunta "de sistem"). */
    fun markSilent() { silentStop = true }

    fun status(): String = if (ready) "ready ${w}x${h}" else "not ready"

    private fun cleanup() {
        try { vd?.release() } catch (_: Exception) {}
        try { reader?.close() } catch (_: Exception) {}
        try { projection?.stop() } catch (_: Exception) {}
        vd = null; reader = null; projection = null; ready = false
    }

    override fun onDestroy() { cleanup(); instance = null; super.onDestroy() }
}
