package net.sys32.agent

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import java.io.File

/**
 * Foreground service care mentine procesul Python (agentul) viu in BACKGROUND.
 *
 * Fara el, Android suspenda/omoara procesul cand MainActivity e minimizata
 * (si cu atat mai mult cand agentul trebuie sa lucreze in alte aplicatii).
 *
 * Face 3 lucruri:
 *  1) ruleaza in foreground cu o notificare persistenta (procesul nu e "candidat la kill")
 *  2) tine un PARTIAL_WAKE_LOCK (CPU-ul nu adoarme in timpul unui task)
 *  3) START_STICKY + onTaskRemoved -> revine daca sistemul il omoara
 *
 * Procesul Python INSUSI e pornit de PythonRunner (obiect partajat in proces),
 * ca sa nu avem doua instante. Serviciul e "gazda" care garanteaza prioritatea.
 */
class AgentService : Service() {

    companion object {
        /** Reinnoieste wake lock-ul - apelat la inceputul unui task. */
        fun renewWakeLock(ctx: Context) {
            try { instance?.acquireWakeLock() } catch (_: Exception) {}
        }

        const val CHANNEL_ID = "agent_bg"
        const val NOTIF_ID = 4711
        const val ACTION_START = "net.sys32.agent.START"
        const val ACTION_STOP = "net.sys32.agent.STOP"
        const val ACTION_WAKE = "net.sys32.agent.WAKE"
        const val ACTION_SLEEP = "net.sys32.agent.SLEEP"

        @Volatile var running = false
        @Volatile var instance: AgentService? = null

        /** Aprinde ecranul + il tine treaz (pentru task-uri care ating UI-ul altor aplicatii). */
        fun wakeScreen(ctx: Context) {
            try {
                val i = Intent(ctx, AgentService::class.java).setAction(ACTION_WAKE)
                if (Build.VERSION.SDK_INT >= 26) ctx.startForegroundService(i) else ctx.startService(i)
            } catch (_: Exception) {}
        }

        /** Lasa ecranul sa se stinga singur (dupa terminarea taskului). */
        fun sleepScreen(ctx: Context) {
            try {
                val i = Intent(ctx, AgentService::class.java).setAction(ACTION_SLEEP)
                if (Build.VERSION.SDK_INT >= 26) ctx.startForegroundService(i) else ctx.startService(i)
            } catch (_: Exception) {}
        }
    }

    private var wakeLock: PowerManager.WakeLock? = null
    private var wakeLockFull: PowerManager.WakeLock? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        instance = this
        createChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            stopForegroundCompat()
            stopSelf()
            return START_NOT_STICKY
        }
        if (intent?.action == ACTION_WAKE) {
            // task cu UI: ecranul trebuie APRINS si telefonul DEBLOCAT
            acquireWakeLock()
            wakeLockFull?.let { if (!it.isHeld) it.acquire(10 * 60 * 1000L) }
            startForegroundCompat()
            running = true
            return START_STICKY
        }
        if (intent?.action == ACTION_SLEEP) {
            try { if (wakeLockFull?.isHeld == true) wakeLockFull?.release() } catch (_: Exception) {}
            // nu oprim serviciul: procesul trebuie sa ramina viu (headless)
            return START_STICKY
        }
        startForegroundCompat()
        acquireWakeLock()
        running = true
        // agentul Python e deja pornit de MainActivity/PythonRunner; serviciul doar
        // garanteaza ca procesul ramane in viata si prioritar in background.
        return START_STICKY
    }

    private fun startForegroundCompat() {
        val pi = PendingIntent.getActivity(
            this, 0,
            Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val notif: Notification = Notification.Builder(this, CHANNEL_ID)
            .setContentTitle("Agent ruleaza")
            .setContentText("Lucreaza in background - atinge pentru a deschide")
            .setSmallIcon(android.R.drawable.stat_sys_download_done)
            .setOngoing(true)
            .setContentIntent(pi)
            .setCategory(Notification.CATEGORY_SERVICE)
            .build()

        if (Build.VERSION.SDK_INT >= 34) {
            startForeground(NOTIF_ID, notif, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE)
        } else if (Build.VERSION.SDK_INT >= 29) {
            startForeground(NOTIF_ID, notif, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
        } else {
            startForeground(NOTIF_ID, notif)
        }
    }

    private fun stopForegroundCompat() {
        try {
            if (Build.VERSION.SDK_INT >= 24) stopForeground(STOP_FOREGROUND_REMOVE)
            else @Suppress("DEPRECATION") stopForeground(true)
        } catch (_: Exception) {}
        running = false
    }

    private fun acquireWakeLock() {
        if (wakeLock?.isHeld == true) return
        try {
            val pm = getSystemService(Context.POWER_SERVICE) as PowerManager
            wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "net.sys32.agent::agent")
            wakeLock?.setReferenceCounted(false)
            // OPTIMIZARE BATERIE: timeout de 30 min, nu la infinit. Daca nimic nu-l
            // reinoieste (task activ), CPU-ul poate adormi -> consum mult mai mic in idle.
            wakeLock?.acquire(30 * 60 * 1000L)
            // wake lock suplimentar care APRINDE ecranul (folosit doar pentru task-uri cu UI)
            wakeLockFull = pm.newWakeLock(
                PowerManager.PARTIAL_WAKE_LOCK or PowerManager.ACQUIRE_CAUSES_WAKEUP,
                "net.sys32.agent::screen"
            )
            wakeLockFull?.setReferenceCounted(false)
        } catch (_: Exception) {}
    }

    private fun releaseWakeLock() {
        try { if (wakeLock?.isHeld == true) wakeLock?.release() } catch (_: Exception) {}
        try { if (wakeLockFull?.isHeld == true) wakeLockFull?.release() } catch (_: Exception) {}
        wakeLock = null
        wakeLockFull = null
    }

    private fun createChannel() {
        if (Build.VERSION.SDK_INT >= 26) {
            val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            if (nm.getNotificationChannel(CHANNEL_ID) == null) {
                val ch = NotificationChannel(CHANNEL_ID, "Agent background", NotificationManager.IMPORTANCE_LOW)
                ch.description = "Tine agentul viu cand aplicatia e minimizata"
                ch.setShowBadge(false)
                nm.createNotificationChannel(ch)
            }
        }
    }

    override fun onTaskRemoved(rootIntent: Intent?) {
        // utilizatorul a dat "swipe" din recents: repornim serviciul (agentul isi continua munca)
        try {
            val restart = Intent(applicationContext, AgentService::class.java).setAction(ACTION_START)
            if (Build.VERSION.SDK_INT >= 26) startForegroundService(restart)
            else startService(restart)
        } catch (_: Exception) {}
        super.onTaskRemoved(rootIntent)
    }

    override fun onDestroy() {
        if (instance === this) instance = null
        releaseWakeLock()
        running = false
        super.onDestroy()
    }
}
