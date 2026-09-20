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

    private val objects = java.util.concurrent.ConcurrentHashMap<String, Any?>()  // id -> obiect pastrat
    private var nextId = 0
    private val javaClasses = HashMap<String, Class<*>>()  // cache
    private val prim = Primitives(ctx, objects)            // primitive generale: proxy/await/events

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
        "battery" to "batterymanager",
        "vibrator" to "vibrator",
        "vibrator_manager" to "vibrator_manager",
        "telephony" to "phone",
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
        "job" to "jobscheduler",
        "download" to "download",
        "media_router" to "media_router",
        "network_stats" to "netstats",
        "print" to "print",
        "usage_stats" to "usagestats",
        "ui_mode" to "ui_mode",
        "wearable" to "wearable",
        "cast" to "cast",
        "ambient_context" to "ambient_context",
        "appops" to "appops",
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
        "restrictions" to "user",
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
        "virtual_device" to "virtualdevice",
        "accessibility" to "accessibility",
        "account" to "account",
        "activity_task" to "activity_task",
        "adb" to "adb",
        "adservices_manager" to "adservices_manager",
        "advanced_protection" to "advanced_protection",
        "app_binding" to "app_binding",
        "app_function" to "app_function",
        "app_hibernation" to "app_hibernation",
        "app_integrity" to "app_integrity",
        "app_prediction" to "app_prediction",
        "app_search" to "app_search",
        "application_policy" to "application_policy",
        "appwidget" to "appwidget",
        "artd" to "artd",
        "asks" to "asks",
        "attestation_verification" to "attestation_verification",
        "auth" to "auth",
        "background_install_control" to "background_install_control",
        "backup" to "backup",
        "batteryproperties" to "batteryproperties",
        "batterystats" to "batterystats",
        "binder_calls_stats" to "binder_calls_stats",
        "blob_store" to "blob_store",
        "blockchain" to "blockchain",
        "bluetooth_manager" to "bluetooth_manager",
        "bugreport" to "bugreport",
        "cacheinfo" to "cacheinfo",
        "carrier_config" to "carrier_config",
        "color_display" to "color_display",
        "companiondevice" to "companiondevice",
        "connectivity_native" to "connectivity_native",
        "connmetrics" to "connmetrics",
        "content" to "content",
        "content_capture" to "content_capture",
        "contextual_search" to "contextual_search",
        "cpuinfo" to "cpuinfo",
        "credential" to "credential",
        "dataloader_manager" to "dataloader_manager",
        "dbinfo" to "dbinfo",
        "device_config" to "device_config",
        "device_identifiers" to "device_identifiers",
        "device_state" to "device_state",
        "deviceidle" to "deviceidle",
        "devicestoragemonitor" to "devicestoragemonitor",
        "diskstats" to "diskstats",
        "display_aiqe" to "display_aiqe",
        "dnsresolver" to "dnsresolver",
        "dreams" to "dreams",
        "dual_app" to "dual_app",
        "dynamic_instrumentation" to "dynamic_instrumentation",
        "dynamic_system" to "dynamic_system",
        "ecm_enhanced_confirmation" to "ecm_enhanced_confirmation",
        "econtroller" to "econtroller",
        "edm_proxy" to "edm_proxy",
        "edmnativehelper" to "edmnativehelper",
        "emergency_affordance" to "emergency_affordance",
        "enterprise_license_policy" to "enterprise_license_policy",
        "enterprise_policy" to "enterprise_policy",
        "ethernet" to "ethernet",
        "euicc_card_controller" to "euicc_card_controller",
        "extendedethernetservice" to "extendedethernetservice",
        "external_vibrator_service" to "external_vibrator_service",
        "face" to "face",
        "feature_flags" to "feature_flags",
        "fingerprint" to "fingerprint",
        "font" to "font",
        "game" to "game",
        "gamemanager" to "gamemanager",
        "gfxinfo" to "gfxinfo",
        "gpu" to "gpu",
        "grammatical_inflection" to "grammatical_inflection",
        "graphicsstats" to "graphicsstats",
        "imms" to "imms",
        "incident" to "incident",
        "incidentcompanion" to "incidentcompanion",
        "incremental" to "incremental",
        "input_method" to "input_method",
        "inputflinger" to "inputflinger",
        "installd" to "installd",
        "intrusion_detection" to "intrusion_detection",
        "ions" to "ions",
        "iphonesubinfo" to "iphonesubinfo",
        "ipsec" to "ipsec",
        "isemphonesubinfo" to "isemphonesubinfo",
        "isemtelephony" to "isemtelephony",
        "isms" to "isms",
        "isub" to "isub",
        "jobscheduler" to "jobscheduler",
        "knox_ucsm_policy" to "knox_ucsm_policy",
        "knox_vpn_policy" to "knox_vpn_policy",
        "knoxcustom" to "knoxcustom",
        "knoxguard_service" to "knoxguard_service",
        "launcherapps" to "launcherapps",
        "lazy_service" to "lazy_service",
        "legacy_permission" to "legacy_permission",
        "lifeguard" to "lifeguard",
        "lights" to "lights",
        "location_time_zone_manager" to "location_time_zone_manager",
        "lock_settings" to "lock_settings",
        "logcat" to "logcat",
        "looper_stats" to "looper_stats",
        "manager" to "manager",
        "mdns" to "mdns",
        "media_communication" to "media_communication",
        "media_resource_monitor" to "media_resource_monitor",
        "meminfo" to "meminfo",
        "mobile_payment" to "mobile_payment",
        "mocca" to "mocca",
        "motion_recognition" to "motion_recognition",
        "mount" to "mount",
        "multicontrol" to "multicontrol",
        "mum_container_policy" to "mum_container_policy",
        "nearby" to "nearby",
        "netd" to "netd",
        "netd_listener" to "netd_listener",
        "netpolicy" to "netpolicy",
        "netstats" to "netstats",
        "network_management" to "network_management",
        "network_score" to "network_score",
        "network_stack" to "network_stack",
        "network_time_update_service" to "network_time_update_service",
        "network_watchlist" to "network_watchlist",
        "oem_lock" to "oem_lock",
        "on_device_intelligence" to "on_device_intelligence",
        "ondevicepersonalization_system_service" to "ondevicepersonalization_system_service",
        "otadexopt" to "otadexopt",
        "overlay" to "overlay",
        "pac_proxy" to "pac_proxy",
        "package" to "package",
        "package_native" to "package_native",
        "perfsdkservice" to "perfsdkservice",
        "permission" to "permission",
        "permission_checker" to "permission_checker",
        "permissionmgr" to "permissionmgr",
        "persistent_data_block" to "persistent_data_block",
        "persona" to "persona",
        "phone" to "phone",
        "pinner" to "pinner",
        "platform_compat" to "platform_compat",
        "platform_compat_native" to "platform_compat_native",
        "powerstats" to "powerstats",
        "processinfo" to "processinfo",
        "procstats" to "procstats",
        "profilepolicy" to "profilepolicy",
        "profiling_service" to "profiling_service",
        "ranging" to "ranging",
        "reboot_readiness" to "reboot_readiness",
        "recovery" to "recovery",
        "remote_provisioning" to "remote_provisioning",
        "remoteappmode" to "remoteappmode",
        "resources" to "resources",
        "restriction_policy" to "restriction_policy",
        "rollback" to "rollback",
        "runtime" to "runtime",
        "safety_center" to "safety_center",
        "samsung_telecom" to "samsung_telecom",
        "samsungnfc" to "samsungnfc",
        "scheduling_policy" to "scheduling_policy",
        "scontext" to "scontext",
        "sdhms" to "sdhms",
        "sdk_sandbox" to "sdk_sandbox",
        "sec_key_att_app_id_provider" to "sec_key_att_app_id_provider",
        "sec_location" to "sec_location",
        "secims" to "secims",
        "secure_element" to "secure_element",
        "security_state" to "security_state",
        "sem_ssdid" to "sem_ssdid",
        "sem_wifi" to "sem_wifi",
        "sem_wifi_aware" to "sem_wifi_aware",
        "sem_wifi_p2p" to "sem_wifi_p2p",
        "semclipboard" to "semclipboard",
        "semprivilege" to "semprivilege",
        "sensitive_content_protection_service" to "sensitive_content_protection_service",
        "sensorservice" to "sensorservice",
        "sepunion" to "sepunion",
        "serial" to "serial",
        "servicediscovery" to "servicediscovery",
        "settings" to "settings",
        "simphonebook" to "simphonebook",
        "slice" to "slice",
        "soundtrigger" to "soundtrigger",
        "soundtrigger_middleware" to "soundtrigger_middleware",
        "speech_recognition" to "speech_recognition",
        "spengestureservice" to "spengestureservice",
        "spqr_service" to "spqr_service",
        "stats" to "stats",
        "statsbootstrap" to "statsbootstrap",
        "statscompanion" to "statscompanion",
        "statsmanager" to "statsmanager",
        "stdp_service" to "stdp_service",
        "storaged" to "storaged",
        "storaged_pri" to "storaged_pri",
        "storagestats" to "storagestats",
        "supervision" to "supervision",
        "suspend_control" to "suspend_control",
        "suspend_control_internal" to "suspend_control_internal",
        "system_config" to "system_config",
        "system_server_dumper" to "system_server_dumper",
        "system_update" to "system_update",
        "telephony_ims" to "telephony_ims",
        "testharness" to "testharness",
        "tethering" to "tethering",
        "textclassification" to "textclassification",
        "textservices" to "textservices",
        "texttospeech" to "texttospeech",
        "thermalservice" to "thermalservice",
        "time_detector" to "time_detector",
        "time_zone_detector" to "time_zone_detector",
        "tradeinmode" to "tradeinmode",
        "transparency" to "transparency",
        "trust" to "trust",
        "updatelock" to "updatelock",
        "uri_grants" to "uri_grants",
        "urspservice" to "urspservice",
        "usagestats" to "usagestats",
        "user" to "user",
        "vcn_management" to "vcn_management",
        "virtualdevice" to "virtualdevice",
        "virtualdevice_native" to "virtualdevice_native",
        "voiceinteraction" to "voiceinteraction",
        "vold" to "vold",
        "vpn_management" to "vpn_management",
        "wearable_sensing" to "wearable_sensing",
        "webviewupdate" to "webviewupdate",
        "wifiaware" to "wifiaware",
        "wifinl80211" to "wifinl80211",
        "wifip2p" to "wifip2p",
        "wifiscanner" to "wifiscanner",
        "sem_wifi_p2p" to "sem_wifi_p2p",
        "wifinl80211" to "wifinl80211",
        "wifip2p" to "wifip2p",
    )

    // ---------------- helpers ----------------
    private fun svc(name: String): Any? {
        // 1) nume direct (daca exista deja un asemenea serviciu de sistem, il folosim)
        try { ctx.getSystemService(name)?.let { return it } } catch (_: Exception) {}
        // 2) numele mapat in tabelul nostru
        val c = services[name]
        if (c != null) { try { ctx.getSystemService(c)?.let { return it } } catch (_: Exception) {} }
        // 3) variante frecvente (Android foloseste nume "lipite" pentru unele servicii)
        for (alt in listOf(name, name.replace("_", ""), name + "manager", name + "service", name.replace("_", " ") )) {
            try { ctx.getSystemService(alt)?.let { return it } } catch (_: Exception) {}
        }
        return null
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
                // ---- primitive generale: proxy de interfete + evenimente async ----
                // op=proxy: creeaza o instanta care implementeaza ORICE interfata Java.
                //   {"op":"proxy","iface":"java.lang.Runnable"}  -> {"id":"s0",...}
                //   obiectul primit se foloseste ca orice alt obiect: target "obj:s0".
                "proxy" -> {
                    val iface = req.optString("iface")
                    if (iface.isBlank()) err("proxy: 'iface' required (fully qualified interface name, e.g. java.lang.Runnable)")
                    else ok(JSONObject().put("id", prim.makeProxy(iface, null))
                        .put("iface", iface)
                        .put("note", "proxy created; every interface call is recorded as an event - use op=await to receive them"))
                }
                "await" -> prim.await(req.optString("id").ifBlank { null }, req.optLong("timeout_ms", 10000))
                "events" -> prim.events(req.optString("id"))
                "drain" -> prim.drain(req.optString("id"))
                "sinks" -> prim.listSinks()
                "objs" -> {
                    val a = JSONArray()
                    for ((k, v) in objects) a.put(JSONObject().put("id", k).put("class", v?.javaClass?.name ?: "null"))
                    ok(a)
                }
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
        if (target.startsWith("obj:") && objects[target.removePrefix("obj:")] == null && objects[target] == null)
            return err("unknown obj target: $target (existing ids: ${objects.keys.joinToString(", ")}) -- objects returned by a previous call get an id automatically; use it as obj:<id>")
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
            if (v is JSONArray && v.length() == 2 && (v.get(0) as? String) in listOf("svc","obj","class","str","int","long","double","bool","new","ref","ctx","app")) {
                // argument cu tip: [tip, valoare]  ex ["svc","sensor"]
                resolveArg(v.getString(0), v.get(1))
            } else v
        }
        val m = findMethod(cls, method, args)
            ?: return err("method not found: ${cls.name}.$method/" + args.size +
                    " (hint: use op=info on ${cls.name} to list methods; methods like getSystemService/registerListener live on Context or a service -> use target ctx or svc:NAME)")
        m.isAccessible = true
        val out = m.invoke(receiver, *args)
        return ok(wrapReturn(out, req.optString("as"), req.optBoolean("keep", true)))
    }

    /** rezolva o referinta textuala ("obj:oN", "ctx", "app", "svc:X") la obiectul real */
    private fun resolveRef(r: String?): Any? = when {
        r == null -> null
        r == "ctx" -> ctx
        r == "app" -> ctx.applicationContext
        r.startsWith("obj:") -> objects[r.removePrefix("obj:")]
        r.startsWith("svc:") -> svc(r.removePrefix("svc:"))
        else -> objects[r]
    }

    private fun resolveArg(kind: String, value: Any?): Any? = when (kind) {
        "svc" -> svc(value as String)
        "class" -> resolveClass(value as String)
        "obj" -> objects[value as String] ?: (value as? String)?.removePrefix("obj:")?.let { objects[it] }
        "ref" -> resolveRef(value as? String)
        "ctx" -> ctx
        "app" -> ctx.applicationContext
        else -> {
            // Primitiva 2: orice string care arata ca o referinta ("obj:oN", "ctx", "app",
            // "svc:X") se rezolva la obiectul Java real - asa putem transmite proxy-uri,
            // Context, servicii etc. ca argumente la apeluri.
            val s = value as? String
            when {
                s == null -> value
                s == "ctx" -> ctx
                s == "app" -> ctx.applicationContext
                s.startsWith("obj:") -> objects[s.removePrefix("obj:")] ?: value
                s.startsWith("svc:") -> svc(s.removePrefix("svc:")) ?: value
                else -> value
            }
        }
    }

    private fun doNew(req: JSONObject): JSONObject {
        val name = req.optString("target").removePrefix("class:")
        val argsJson = req.optJSONArray("args") ?: JSONArray()
        val cls = resolveClass(name)
        val args = Array(argsJson.length()) { i ->
            val v = argsJson.get(i)
            if (v is JSONArray && v.length() == 2 && (v.get(0) as? String) in listOf("svc","obj","class","str","int","long","double","bool","new","ref","ctx","app")) {
                resolveArg(v.getString(0), v.get(1))
            } else {
                val sv = v as? String
                when {
                    sv == null -> v
                    sv == "ctx" -> ctx
                    sv == "app" -> ctx.applicationContext
                    sv.startsWith("obj:") || sv.startsWith("svc:") -> resolveRef(sv) ?: sv
                    else -> sv
                }
            }
        }
        val want = args.size
        val ctor = cls.constructors
            .filter { it.parameterCount == want }
            .sortedByDescending { c -> c.parameterTypes.indices.count { i -> args[i] == null || compatible(c.parameterTypes[i], args[i]!!.javaClass) } }
            .firstOrNull()
            ?: return err("no constructor with $want args for $name (hint: many Android classes have no public constructor; obtain them via ctx.getSystemService(\"name\"), a static factory, or a service target like svc:NAME)")
        ctor.isAccessible = true
        val o = ctor.newInstance(*args)
        val id = req.optString("id", "o${nextId++}")
        objects[id] = o
        return ok(JSONObject().put("id", id).put("class", o.javaClass.name))
    }

    private fun doGet(req: JSONObject): JSONObject {
        val targetObj = resolve(req.optString("target"))
        val field = req.optString("field")
        if (field.isBlank()) return err("field name required (set \"field\": \"<name>\")")
        val f = findField(targetObj, field) ?: return err("field not found: $field")
        f.isAccessible = true
        return ok(wrapReturn(f.get(targetObj), req.optString("as"), req.optBoolean("keep", true)))
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
        // 1) candidate cu exact numele si numarul de argumente, scor de compatibilitate
        val cands = cls.methods.filter { it.name == name && it.parameterCount == args.size }
        var best: Method? = null
        var bestScore = -1
        for (m in cands) {
            val p = m.parameterTypes
            var score = 0
            var fits = true
            for (i in args.indices) {
                val a = args[i]
                if (a == null) { score++; continue }   // null se potriveste oriunde (ambiguu, dar acceptabil)
                if (compatible(p[i], a.javaClass)) score++ else { fits = false; break }
            }
            if (fits && score > bestScore) { bestScore = score; best = m }
        }
        if (best != null) return best
        // 2) fallback: orice metoda cu numele dat (dar NU un overload incompatibil)
        return cands.firstOrNull()
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
