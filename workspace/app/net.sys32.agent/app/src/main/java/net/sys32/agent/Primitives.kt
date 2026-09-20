package net.sys32.agent

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.lang.reflect.InvocationHandler
import java.lang.reflect.Method
import java.lang.reflect.Proxy
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.CountDownLatch
import java.util.concurrent.LinkedBlockingQueue
import java.util.concurrent.TimeUnit

/**
 * Primitive GENERALE de acces:
 *
 *  1) PROXY de interfete / clase: agentul poate cere o instanta care implementeaza
 *     ORICE interfata Java cunoscuta (ex. android.bluetooth.le.ScanCallback are nevoie
 *     de o subclasa, dar majoritatea API-urilor cer INTERFETE: Runnable, Consumer,
 *     LocationListener, SensorEventListener, TextWatcher, OnClickListener, etc.)
 *     si primeste inapoi un obiect (obj:oN) pe care il poate pasa mai departe.
 *     Fiecare apel al interfetei este INREGISTRAT ca eveniment.
 *
 *  2) REFERINTE de obiecte ca argumente: rezolvarea "obj:oN", "ctx", "app", "svc:X"
 *     direct la obiectul Java real, ca proxy-ul sa poata fi transmis ca parametru.
 *
 *  3) EVENIMENTE asincrone: un buffer per proxy + op=await care blocheaza pina
 *     soseste un eveniment (sau expira). Asa agentul poate astepta rezultatul unui
 *     callback declansat de un apel asincron (scanare BLE, ascultare senzori, etc.)
 *
 * Nimic din astea nu e specific vreunui API: sunt primitive reutilizabile pentru tot.
 */
class Primitives(private val ctx: Context, private val objects: ConcurrentHashMap<String, Any?>) {

    /** evenimentele capturate de fiecare proxy, in ordine, cu coada blocanta pt await */
    private class Sink {
        val queue = LinkedBlockingQueue<JSONObject>()
        val seen = ArrayList<JSONObject>()
        var calls = 0
    }

    private val sinks = ConcurrentHashMap<String, Sink>()

    /** instantiaza un proxy pentru o interfata; intoarce id-ul (oN) */
    fun makeProxy(ifaceName: String, sinkId: String?): String {
        val iface = loadIface(ifaceName)
        val sink = Sink()
        // registrul de sink-uri e separat de obiecte; cheia o generam aici
        val id = nextId()
        sinks[id] = sink

        val handler = InvocationHandler { _, method, args ->
            try {
                val ev = JSONObject()
                ev.put("event", "call")
                ev.put("method", method.name)
                ev.put("iface", ifaceName)
                ev.put("args", serArgs(args))
                sink.calls++
                sink.seen.add(ev)
                sink.queue.offer(ev)
            } catch (_: Throwable) {}
            defaultReturn(method)
        }

        val proxy = Proxy.newProxyInstance(
            iface.classLoader ?: ctx.classLoader,
            arrayOf(iface),
            handler
        )
        objects[id] = proxy
        return id
    }

    /** asteapta urmatorul eveniment al unui proxy (sau orice, daca id null) */
    fun await(id: String?, timeoutMs: Long): JSONObject {
        // fara id: asteapta orice eveniment din orice sink, in ordine
        if (id.isNullOrBlank()) {
            val deadline = System.currentTimeMillis() + timeoutMs
            while (System.currentTimeMillis() < deadline) {
                for (s in sinks.values) {
                    val e = s.queue.poll()
                    if (e != null) return ok(e)
                }
                Thread.sleep(20)
            }
            return ok(JSONObject().put("event", "timeout").put("waited_ms", timeoutMs))
        }
        val s = sinks[id] ?: return err("unknown sink/proxy id: $id (create one with op=proxy)")
        val e = s.queue.poll(timeoutMs, TimeUnit.MILLISECONDS)
            ?: return ok(JSONObject().put("event", "timeout").put("waited_ms", timeoutMs))
        return ok(e)
    }

    /** toate evenimentele capturate pina acum de un proxy (fara sa consume coada) */
    fun events(id: String): JSONObject {
        val s = sinks[id] ?: return err("unknown sink/proxy id: $id")
        val a = JSONArray()
        synchronized(s.seen) { for (e in s.seen) a.put(e) }
        return ok(JSONObject().put("id", id).put("calls", s.calls).put("events", a))
    }

    /** goleste coada unui proxy */
    fun drain(id: String): JSONObject {
        val s = sinks[id] ?: return err("unknown sink/proxy id: $id")
        var n = 0
        while (s.queue.poll() != null) n++
        return ok(JSONObject().put("id", id).put("drained", n))
    }

    /** listeaza proxy-urile active cu interfata lor */
    fun listSinks(): JSONObject {
        val a = JSONArray()
        for ((k, s) in sinks) {
            a.put(JSONObject().put("id", k)
                .put("calls", s.calls)
                .put("pending", s.queue.size))
        }
        return ok(a)
    }

    // ---------- helpers ----------

    private fun loadIface(name: String): Class<*> {
        val c = Class.forName(name, false, ctx.classLoader)
        if (!c.isInterface) throw IllegalArgumentException("not an interface: $name (proxy works only for interfaces; abstract CLASSES like ScanCallback cannot be proxied - use a concrete subclass exposed as a shortcut, if one exists)")
        return c
    }

    private fun serArgs(args: Array<Any?>?): Any {
        if (args == null) return JSONArray()
        val a = JSONArray()
        for (x in args) {
            when (x) {
                null -> a.put(JSONObject.NULL)
                is String, is Number, is Boolean -> a.put(x)
                else -> {
                    // incercam o reprezentare bogata, apoi fallback pe toString
                    val o = JSONObject()
                    o.put("class", x.javaClass.name)
                    o.put("str", safeStr(x))
                    a.put(o)
                }
            }
        }
        return a
    }

    private fun safeStr(x: Any?): String = try { x.toString() } catch (_: Throwable) { "<toString failed>" }

    /** valoarea implicita de returnat dintr-un proxy (void/boolean false/0/null) */
    private fun defaultReturn(m: Method): Any? = when (m.returnType) {
        Void.TYPE, Void::class.java -> null
        java.lang.Boolean.TYPE, java.lang.Boolean::class.java -> false
        java.lang.Integer.TYPE, java.lang.Integer::class.java -> 0
        java.lang.Long.TYPE, java.lang.Long::class.java -> 0L
        java.lang.Double.TYPE, java.lang.Double::class.java -> 0.0
        java.lang.Float.TYPE, java.lang.Float::class.java -> 0f
        java.lang.Short.TYPE, java.lang.Short::class.java -> 0.toShort()
        java.lang.Byte.TYPE, java.lang.Byte::class.java -> 0.toByte()
        java.lang.Character.TYPE, java.lang.Character::class.java -> '\u0000'
        else -> null
    }

    private var counter = 0
    private fun nextId(): String = "s" + (counter++)

    private fun ok(d: Any?): JSONObject = JSONObject().put("ok", true).put("data", d ?: JSONObject.NULL)
    private fun err(m: String): JSONObject = JSONObject().put("ok", false).put("error", m)
}
