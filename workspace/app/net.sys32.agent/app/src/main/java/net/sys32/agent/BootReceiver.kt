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
            // OPTIMIZARE BATERIE/RAM: NU mai pornim un AL DOILEA foreground service.
            // AgentService face deja tot (foreground + wakelock + START_STICKY + onTaskRemoved),
            // iar GuardService doar dubla notificarea si consuma un slot de FGS.
            // GuardService rămâne DOAR ca tinta a alarmei de siguranta (schedule).
            try { AgentService.ensureRunning(ctx) } catch (_: Exception) {}
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
                // BATERIE: 15 min -> 60 min si fara _WAKEUP (nu mai trezim CPU-ul din Doze
                // la fiecare sfert de ora). Guard-ul e oricum un foreground service + are
                // watchdog propriu; alarm-ul e doar o plasa de siguranta.
                am.setExactAndAllowWhileIdle(
                    AlarmManager.ELAPSED_REALTIME,
                    android.os.SystemClock.elapsedRealtime() + 60 * 60 * 1000L, pi
                )
            } catch (_: Exception) {}
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        // OPTIMIZARE BATERIE: NU mai rămâne un foreground service aici (a doua notificare
        // persistenta + al doilea FGS erau redundante cu AgentService). Acest serviciu se
        // foloseste DOAR ca tinta a alarmei: re-programeaza alarma si deleaga la AgentService.
        try { AgentService.ensureRunning(this) } catch (_: Exception) {}
        schedule(this)
        stopSelf()
        return START_NOT_STICKY
    }

    override fun onBind(intent: Intent?) = null
    override fun onTaskRemoved(rootIntent: Intent?) { schedule(this); super.onTaskRemoved(rootIntent) }
}
