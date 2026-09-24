package net.sys32.agent

import android.net.VpnService
import android.content.Intent
import android.os.ParcelFileDescriptor

// FIX 4: VpnService pentru interceptarea traficului.
// Necesita consimtamant O SINGURA data prin VpnService.prepare().
// Nu impune tunel implicit: expune doar capabilitatea + stabileste tunelul daca
// e cerut din bridge. Fara o configuratie de tunel reala, serviciul doar
// confirma disponibilitatea (nu blocheaza reteaua).
class AgentVpn : VpnService() {

    companion object {
        @Volatile var instance: AgentVpn? = null
        @Volatile var established = false
        fun prepare(ctx: android.content.Context): Intent? = VpnService.prepare(ctx)
    }

    private var tun: ParcelFileDescriptor? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        instance = this
        return START_STICKY
    }

    // creeaza tunelul (apelabil din bridge); MTU + adresa de test
    fun establish(name: String = "agent0"): String {
        return try {
            val b = Builder()
                .setSession("agent")
                .addAddress("10.8.0.2", 32)
                .addRoute("10.8.0.0", 24)
                .setMtu(1500)
            tun = b.establish()
            established = tun != null
            if (established) "ok: $name" else "establish() -> null"
        } catch (e: Exception) { "error: $e" }
    }

    fun closeTun() { try { tun?.close() } catch (_: Exception) {}; tun = null; established = false }

    fun status(): String = if (established) "up" else "down"

    override fun onRevoke() { closeTun(); super.onRevoke() }
    override fun onDestroy() { closeTun(); instance = null; super.onDestroy() }
}
