package net.sys32.agent

import android.content.Context
import android.util.Log
import org.json.JSONArray
import org.json.JSONObject
import java.lang.reflect.Field
import java.lang.reflect.Method
import java.lang.reflect.Modifier

/**
 * Evaluator generic prin REFLECTION: da agentului acces la ORICE clasa/metoda Android.
 * Comenzile vin ca dict-uri JSON:
 *   {"op":"call",   "target":"svc:sensor",  "method":"getSensorList", "args":[0]}
 *   {"op":"call",   "target":"class:android.os.Environment", "static":true, "method":"getExternalStorageDirectory"}
 *   {"op":"new",    "target":"class:android.media.MediaRecorder"}
 *   {"op":"get",    "target":"svc:wifi", "field":"mService"}
 *   {"op":"set",    "target":"svc:audio", "field":"x", "value":1}
 *   {"op":"info",   "target":"class:android.hardware.SensorManager"}   -> lista metode
 *   {"op":"services"}  -> toate serviciile de sistem
 * Obiectele create se pastreaza intr-un registru si pot fi referite prin id.
 */
class Reflection(private val ctx: Context) {

    companion object { const val TAG = "AgentRefl" }

    private val objects = HashMap<String, Any?>()          // id -> obiect pastrat
    private var nextId = 0
    private val javaClasses = HashMap<String, Class<*>>()  // cache

    /** Servicii de sistem expuse sub nume simple. */
        private val services: Map<String, String> = mapOf(
        "sensor" to "sensor",
        "camera" to "camera",
        "location" to "location",
        "connectivity" to "connectivity",
        "wifi" to "wifi",
        "audio" to "audio",
        "clipboard" to "clipboard",
        "notification" to "notification",
        "power" to "power",
        "battery" to "battery",
        "vibrator" to "vibrator",
        "vibrator_manager" to "vibrator_manager",
        "telephony" to "telephony",
        "telephony_sub" to "telephony_subscription",
        "usb" to "usb",
        "bluetooth" to "bluetooth",
        "nfc" to "nfc",
        "display" to "display",
        "window" to "window",
        "input" to "input",
        "keyguard" to "keyguard",
        "search" to "search",
        "storage" to "storage",
        "activity" to "activity",
        "alarm" to "alarm",
        "job" to "job_scheduler",
        "download" to "download",
        "media_router" to "media_router",
        "network_stats" to "network_stats",
        "print" to "print",
        "usage_stats" to "usage_stats",
        "ui_mode" to "ui_mode",
        "wearable" to "wearable",
        "cast" to "cast",
        "ambient_context" to "ambient_context",
        "appops" to "app_ops",
        "autofill" to "autofill",
        "biometric" to "biometric",
        "country_detector" to "country_detector",
        "device_policy" to "device_policy",
        "dropbox" to "dropbox",
        "hardware_properties" to "hardware_properties",
        "healthconnect" to "healthconnect",
        "media_metrics" to "media_metrics",
        "media_projection" to "media_projection",
        "media_session" to "media_session",
        "midi" to "midi",
        "network_policy" to "netpolicy",
        "people" to "people",
        "performance_hint" to "performance_hint",
        "restrictions" to "restrictions",
        "role" to "role",
        "shortcut" to "shortcut",
        "statusbar" to "statusbar",
        "system_health" to "system_health",
        "telecom" to "telecom",
        "tv_input" to "tv_input",
        "tv_interactive_app" to "tv_interactive_app",
        "vpn" to "vpn_management",
        "wallpaper" to "wallpaper",
        "crossprofileapps" to "cross_profile_apps",
        "domain_verification" to "domain_verification",
        "euicc" to "euicc",
        "file_integrity" to "file_integrity",
        "grammatical" to "grammatical_inflection",
        "isp" to "isp",
        "locale" to "locale",
        "music_recognition" to "music_recognition",
        "sensor_privacy" to "sensor_privacy",
        "translation" to "translation",
        "uimode" to "ui_mode",
        "virtual_device" to "virtual_device",
    )

    // ---------------- helpers ----------------
    private fun svc(name: String): Any? {
        val const = services[name] ?: return null
        return ctx.getSystemService(const)
    }

    private fun resolveClass(name: String): Class<*> {
        javaClasses[name]?.let { return it }
        // incercari: nume complet, apoi aliasuri uzuale (java.util.List etc)
        val aliases = mapOf(
            "String" to String::class.java, "Object" to Any::class.java,
            "Integer" to Int::class.javaObjectType, "int" to Int::class.javaPrimitiveType,
            "Long" to Long::class.javaObjectType, "long" to Long::class.javaPrimitiveType,
            "Double" to Double::class.javaObjectType, "double" to Double::class.javaPrimitiveType,
            "Float" to Float::class.javaObjectType, "float" to Float::class.javaPrimitiveType,
            "Boolean" to Boolean::class.javaObjectType, "boolean" to Boolean::class.javaPrimitiveType,
            "Byte" to Byte::class.javaObjectType, "byte" to Byte::class.javaPrimitiveType,
            "Short" to Short::class.javaObjectType, "short" to Short::class.javaPrimitiveType,
            "Char" to Char::class.javaObjectType, "char" to Char::class.javaPrimitiveType,
            "List" to java.util.List::class.java, "ArrayList" to java.util.ArrayList::class.java,
            "Map" to java.util.Map::class.java, "HashMap" to java.util.HashMap::class.java,
            "JSONObject" to JSONObject::class.java, "JSONArray" to JSONArray::class.java,
            "File" to java.io.File::class.java, "Uri" to android.net.Uri::class.java,
            "Intent" to android.content.Intent::class.java, "ComponentName" to android.content.ComponentName::class.java,
            "Thread" to Thread::class.java, "System" to java.lang.System::class.java,
        )
        val cls = try {
            aliases[name] ?: Class.forName(name)
        } catch (e: Exception) {
            val fq = if (name.contains(".")) name else "java.lang.$name"
            Class.forName(fq)
        }
        javaClasses[name] = cls
        return cls
    }

    /** Rezolva un target: svc:NUME, class:NUME, obj:ID, ctx, app sau obiect existent. */
    private fun resolve(target: String): Any? = when {
        target == "ctx" || target == "context" -> ctx
        target == "app" -> ctx.applicationContext
        target.startsWith("svc:") -> svc(target.removePrefix("svc:"))
        target.startsWith("class:") -> resolveClass(target.removePrefix("class:"))
        target.startsWith("obj:") -> objects[target.removePrefix("obj:")]
        target.startsWith("str:") -> target.removePrefix("str:")
        target.startsWith("int:") -> target.removePrefix("int:").toIntOrNull()
        target.startsWith("long:") -> target.removePrefix("long:").toLongOrNull()
        target.startsWith("double:") -> target.removePrefix("double:").toDoubleOrNull()
        target.startsWith("bool:") -> target.removePrefix("bool:").toBoolean()
        target.startsWith("null") -> null
        else -> objects[target]
    }

    /** Converteste valorile JSON in tipuri Java potrivite. */
    private fun coerce(v: Any?): Any? = v

    // ---------------- operatii ----------------
    fun execute(req: JSONObject): JSONObject {
        return try {
            when (val op = req.optString("op", "call")) {
                "call" -> doCall(req)
                "new" -> doNew(req)
                "get" -> doGet(req)
                "set" -> doSet(req)
                "info" -> doInfo(req)
                "services" -> doServices()
                "free" -> { val id = req.optString("id"); objects.remove(id); ok(JSONObject().put("freed", id)) }
                "objs" -> ok(JSONArray(objects.keys.toList()))
                else -> err("unknown op: $op")
            }
        } catch (e: java.lang.reflect.InvocationTargetException) {
            err("invocation: " + (e.targetException?.toString() ?: e.toString()))
        } catch (e: Exception) {
            err(e.toString())
        }
    }

    private fun doCall(req: JSONObject): JSONObject {
        val target = req.optString("target")
        val method = req.optString("method")
        val argsJson = req.optJSONArray("args") ?: JSONArray()
        val isStatic = req.optBoolean("static", false)
        val targetObj: Any? = resolve(target)
        val cls: Class<*> = when {
            isStatic -> resolveClass(target.removePrefix("class:"))
            targetObj is Class<*> -> targetObj
            targetObj != null -> targetObj.javaClass
            else -> return err("cannot resolve target: $target (svc:/class:/obj:/ctx)")
        }
        val receiver = if (isStatic || targetObj is Class<*>) null else targetObj
        val args = Array(argsJson.length()) { i ->
            val v = argsJson.get(i)
            if (v is JSONArray && v.length() == 2 && (v.get(0) as? String) in listOf("svc","obj","class","str","int","long","double","bool","new")) {
                // argument cu tip: [tip, valoare]  ex ["svc","sensor"]
                resolveArg(v.getString(0), v.get(1))
            } else v
        }
        val m = findMethod(cls, method, args)
            ?: return err("method not found: ${cls.name}.$method/" + args.size +
                    " (call op=info on the class to list methods)")
        m.isAccessible = true
        val out = m.invoke(receiver, *args)
        return ok(wrapReturn(out, req.optString("as"), req.optBoolean("keep", false)))
    }

    private fun resolveArg(kind: String, value: Any?): Any? = when (kind) {
        "svc" -> svc(value as String)
        "class" -> resolveClass(value as String)
        "obj" -> objects[value as String]
        else -> value
    }

    private fun doNew(req: JSONObject): JSONObject {
        val name = req.optString("target").removePrefix("class:")
        val argsJson = req.optJSONArray("args") ?: JSONArray()
        val cls = resolveClass(name)
        val args = Array(argsJson.length()) { i -> argsJson.get(i) }
        val ctor = cls.constructors.firstOrNull { it.parameterCount == args.size }
            ?: return err("no constructor with ${args.size} args for $name")
        ctor.isAccessible = true
        val o = ctor.newInstance(*args)
        val id = req.optString("id", "o${nextId++}")
        objects[id] = o
        return ok(JSONObject().put("id", id).put("class", o.javaClass.name))
    }

    private fun doGet(req: JSONObject): JSONObject {
        val targetObj = resolve(req.optString("target"))
        val field = req.optString("field")
        val f = findField(targetObj, field) ?: return err("field not found: $field")
        f.isAccessible = true
        return ok(wrapReturn(f.get(targetObj), req.optString("as"), req.optBoolean("keep", false)))
    }

    private fun doSet(req: JSONObject): JSONObject {
        val targetObj = resolve(req.optString("target"))
        val field = req.optString("field")
        val value = if (req.has("value")) req.get("value") else null
        val f = findField(targetObj, field) ?: return err("field not found: $field")
        f.isAccessible = true
        f.set(targetObj, value)
        return ok(JSONObject().put("set", field))
    }

    private fun doInfo(req: JSONObject): JSONObject {
        val t = req.optString("target")
        val cls = try { resolveClass(t.removePrefix("class:")) } catch (e: Exception) { return err("class not found: $t") }
        val methods = JSONArray()
        val filter = req.optString("filter", "")
        for (m in cls.methods) {
            if (m.declaringClass == Any::class.java) continue
            val sig = m.name + "(" + m.parameterTypes.joinToString(",") { it.simpleName } + ")"
            if (filter.isEmpty() || sig.contains(filter, true)) {
                methods.put(sig + (if (Modifier.isStatic(m.modifiers)) " static" else ""))
            }
        }
        val fields = JSONArray()
        for (f in cls.fields) {
            if (filter.isEmpty() || f.name.contains(filter, true))
                fields.put(f.name + ": " + f.type.simpleName + (if (Modifier.isStatic(f.modifiers)) " static" else ""))
        }
        return ok(JSONObject().put("class", cls.name).put("methods", methods).put("fields", fields))
    }

    private fun doServices(): JSONObject {
        val arr = JSONArray()
        for ((k, v) in services) arr.put(JSONObject().put("name", k).put("const", v).put("available", svc(k) != null))
        return ok(arr)
    }

    // ---------------- reflection helpers ----------------
    private fun findMethod(cls: Class<*>, name: String, args: Array<Any?>): Method? {
        for (m in cls.methods) {
            if (m.name != name || m.parameterCount != args.size) continue
            val p = m.parameterTypes
            var fits = true
            for (i in args.indices) {
                if (args[i] == null) continue
                if (!compatible(p[i], args[i]!!.javaClass)) { fits = false; break }
            }
            if (fits) return m
        }
        // fallback: orice metoda cu numele dat
        return cls.methods.firstOrNull { it.name == name }
    }

    private fun compatible(param: Class<*>, given: Class<*>): Boolean {
        if (param.isAssignableFrom(given)) return true
        if (param.isPrimitive) {
            val box = mapOf(
                java.lang.Integer.TYPE to Int::class.javaObjectType,
                java.lang.Long.TYPE to Long::class.javaObjectType,
                java.lang.Double.TYPE to Double::class.javaObjectType,
                java.lang.Float.TYPE to Float::class.javaObjectType,
                java.lang.Boolean.TYPE to Boolean::class.javaObjectType,
                java.lang.Byte.TYPE to Byte::class.javaObjectType,
                java.lang.Short.TYPE to Short::class.javaObjectType,
                java.lang.Character.TYPE to Char::class.javaObjectType,
            )
            return box[param]?.isAssignableFrom(given) == true
        }
        // conversii numerice
        return Number::class.java.isAssignableFrom(param) && Number::class.java.isAssignableFrom(given)
    }

    private fun findField(obj: Any?, name: String): Field? {
        if (obj == null) return null
        var c: Class<*>? = if (obj is Class<*>) obj else obj.javaClass
        while (c != null) {
            try { return c.getDeclaredField(name) } catch (_: Exception) {}
            c = c.superclass
        }
        return null
    }

    /** Transforma valoarea de retur intr-un JSON serializabil. */
    private fun wrapReturn(v: Any?, asType: String, keep: Boolean): Any? {
        if (keep && v != null) {
            val id = "o${nextId++}"
            objects[id] = v
        }
        return ser(v, 0, keep)
    }

    private fun ser(v: Any?, depth: Int, keep: Boolean): Any? {
        if (depth > 4) return v.toString()
        return when (v) {
            null -> JSONObject.NULL
            is String, is Number, is Boolean -> v
            is JSONObject, is JSONArray -> v
            is Array<*> -> JSONArray(v.map { ser(it, depth + 1, keep) })
            is Iterable<*> -> {
                val a = JSONArray(); var n = 0
                for (x in v) { if (n++ > 200) { a.put("...(truncated)"); break }; a.put(ser(x, depth + 1, keep)) }
                a
            }
            is Map<*, *> -> {
                val o = JSONObject()
                for ((k, vv) in v) o.put(k.toString(), ser(vv, depth + 1, keep))
                o
            }
            else -> {
                // obiecte Android: incerc toString + cateva campuri publice uzuale
                val s = try { v.toString() } catch (_: Exception) { v.javaClass.name }
                if (keep) {
                    val id = "o${nextId++}"
                    objects[id] = v
                    JSONObject().put("id", id).put("class", v.javaClass.name).put("str", s)
                } else {
                    JSONObject().put("class", v.javaClass.name).put("str", s)
                }
            }
        }
    }

    private fun ok(data: Any?): JSONObject = JSONObject().put("ok", true).put("data", data ?: JSONObject.NULL)
    private fun err(msg: String): JSONObject = JSONObject().put("ok", false).put("error", msg)
}
