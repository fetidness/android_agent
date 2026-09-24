package net.sys32.agent

import android.app.Notification
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.CopyOnWriteArrayList

// FIX 2: citire/istere/snooze notificari. Se activeaza cu:
//   cmd notification allow_listener net.sys32.agent/.AgentNotificationListener
class AgentNotificationListener : NotificationListenerService() {

    companion object {
        @Volatile var instance: AgentNotificationListener? = null
        // buffer circular cu ultimele evenimente, ca agentul sa poata citi si ce a pierdut
        private const val MAX = 300
        val recent = CopyOnWriteArrayList<JSONObject>()
    }

    override fun onListenerConnected() {
        instance = this
        try { sendBroadcast(android.content.Intent("net.sys32.agent.NOTIF_CONNECTED")) } catch (_: Exception) {}
    }

    override fun onListenerDisconnected() {
        if (instance === this) instance = null
    }

    private fun push(ev: String, sbn: StatusBarNotification?) {
        val o = JSONObject()
        o.put("event", ev)
        if (sbn != null) {
            o.put("pkg", sbn.packageName)
            o.put("key", sbn.key)
            o.put("postTime", sbn.postTime)
            o.put("ongoing", sbn.isOngoing)
            o.put("clearable", sbn.isClearable)
            val n = sbn.notification
            if (n != null) {
                val ex = n.extras
                o.put("title", ex?.getCharSequence(Notification.EXTRA_TITLE)?.toString() ?: "")
                o.put("text", ex?.getCharSequence(Notification.EXTRA_TEXT)?.toString() ?: "")
                o.put("bigText", ex?.getCharSequence(Notification.EXTRA_BIG_TEXT)?.toString() ?: "")
                o.put("channel", if (android.os.Build.VERSION.SDK_INT >= 26) n.channelId else "")
            }
        }
        recent.add(o)
        while (recent.size > MAX) recent.removeAt(0)
    }

    override fun onNotificationPosted(sbn: StatusBarNotification?) { push("posted", sbn) }
    override fun onNotificationRemoved(sbn: StatusBarNotification?) { push("removed", sbn) }

    // ---- API apelat din bridge prin ToolRegistry ----
    fun dump(limit: Int): JSONObject {
        val out = JSONObject()
        val arr = JSONArray()
        try {
            val active = activeNotifications ?: emptyArray()
            for (sbn in active) {
                val o = JSONObject()
                o.put("pkg", sbn.packageName); o.put("key", sbn.key)
                o.put("postTime", sbn.postTime); o.put("ongoing", sbn.isOngoing)
                val n = sbn.notification
                if (n != null) {
                    val ex = n.extras
                    o.put("title", ex?.getCharSequence(Notification.EXTRA_TITLE)?.toString() ?: "")
                    o.put("text", ex?.getCharSequence(Notification.EXTRA_TEXT)?.toString() ?: "")
                    o.put("bigText", ex?.getCharSequence(Notification.EXTRA_BIG_TEXT)?.toString() ?: "")
                }
                arr.put(o)
            }
            out.put("active", arr)
            out.put("count", arr.length())
        } catch (e: Exception) { out.put("error", e.toString()) }
        val rec = JSONArray()
        val start = maxOf(0, recent.size - limit)
        for (i in start until recent.size) rec.put(recent[i])
        out.put("recent", rec)
        return out
    }

    fun cancelKey(key: String): Boolean = try {
        if (key.isNotEmpty()) cancelNotification(key); true
    } catch (_: Exception) { false }

    fun cancelPkg(pkg: String): Int {
        var n = 0
        try {
            for (sbn in activeNotifications ?: emptyArray()) {
                if (sbn.packageName == pkg) { cancelNotification(sbn.key); n++ }
            }
        } catch (_: Exception) {}
        return n
    }

    fun snooze(key: String, ms: Long): Boolean = try {
        if (key.isNotEmpty()) snoozeNotification(key, ms); true
    } catch (_: Exception) { false }

    fun setInterruption(pkg: String, level: Int): Boolean = try {
        if (android.os.Build.VERSION.SDK_INT >= 26 && pkg.isNotEmpty()) {
            requestInterruptionFilter(level); true
        } else false
    } catch (_: Exception) { false }
}
