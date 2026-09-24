package net.sys32.agent

import android.app.AlarmManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Build

// FIX 7: repornire agent la boot + re-programare periodica prin AlarmManager.
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val a = intent.action ?: return
        if (a == Intent.ACTION_BOOT_COMPLETED || a == "android.intent.action.QUICKBOOT_POWERON") {
            GuardService.start(context)
        }
        if (a == GuardService.ALARM_ACTION) {
            GuardService.start(context)
            GuardService.schedule(context)
        }
    }
}

// FIX 7: serviciu foreground persistent. NU se foloseste niciodata
// am force-stop / pm clear pe propriul pachet (distruge accessibility).
class GuardService : android.app.Service() {

    companion object {
        const val ALARM_ACTION = "net.sys32.agent.GUARD_TICK"
        const val NOTIF_ID = 1001
        const val CH_ID = "agent_guard"

        fun start(ctx: Context) {
            try {
                val i = Intent(ctx, GuardService::class.java)
                if (Build.VERSION.SDK_INT >= 26) ctx.startForegroundService(i) else ctx.startService(i)
            } catch (_: Exception) {}
            schedule(ctx)
        }

        // re-programare exacta, supravietuieste doze
        fun schedule(ctx: Context) {
            try {
                val am = ctx.getSystemService(Context.ALARM_SERVICE) as AlarmManager
                val pi = PendingIntent.getBroadcast(
                    ctx, 42, Intent(ctx, BootReceiver::class.java).setAction(ALARM_ACTION),
                    PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
                )
                am.cancel(pi)
                am.setExactAndAllowWhileIdle(
                    AlarmManager.ELAPSED_REALTIME_WAKEUP,
                    android.os.SystemClock.elapsedRealtime() + 15 * 60 * 1000L, pi
                )
            } catch (_: Exception) {}
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        try {
            if (Build.VERSION.SDK_INT >= 26) {
                val nm = getSystemService(android.app.NotificationManager::class.java)
                if (nm.getNotificationChannel(CH_ID) == null) {
                    nm.createNotificationChannel(
                        android.app.NotificationChannel(CH_ID, "Agent", android.app.NotificationManager.IMPORTANCE_LOW)
                    )
                }
                val n = android.app.Notification.Builder(this, CH_ID)
                    .setContentTitle("Agent activ")
                    .setContentText("Ruleaza in fundal")
                    .setSmallIcon(android.R.drawable.stat_notify_sync)
                    .setOngoing(true)
                    .build()
                startForeground(NOTIF_ID, n)
            }
        } catch (_: Exception) {}
        schedule(this)
        return START_STICKY
    }

    override fun onBind(intent: Intent?) = null
    override fun onTaskRemoved(rootIntent: Intent?) { schedule(this); super.onTaskRemoved(rootIntent) }
}
