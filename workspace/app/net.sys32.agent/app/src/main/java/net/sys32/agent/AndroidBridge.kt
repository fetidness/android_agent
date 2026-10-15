package net.sys32.agent

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.hardware.camera2.CameraCharacteristics
import android.hardware.camera2.CameraManager
import android.location.Location
import android.location.LocationManager
import android.location.LocationListener
import android.os.Bundle
import android.os.CancellationSignal
import java.util.function.Consumer
import android.media.AudioManager
import android.media.MediaPlayer
import android.net.Uri
import android.net.wifi.WifiManager
import android.os.BatteryManager
import android.os.Build
import android.os.Environment
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import android.provider.Settings
import android.util.Base64
import android.util.Log
import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedReader
import java.io.File
import java.io.InputStreamReader
import java.io.OutputStreamWriter
import java.net.ServerSocket
import java.net.Socket
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

/**
 * Server de tool-uri native pentru agentul Python.
 * Asculta pe un Unix domain socket local si expune hardware-ul Android.
 * Protocol: o linie JSON per cerere -> o linie JSON per raspuns.
 *   cerere:  {"tool":"sensors","action":"read","name":"accelerometer","seconds":2}
 *   raspuns: {"ok":true,"data":{...}} sau {"ok":false,"error":"..."}
 */
class AndroidBridge(
    private val ctx: Context,
    private val socketFile: File,
) {
    companion object { const val TAG = "AgentBridge" }

    private val refl by lazy { Reflection(ctx) }

    /** Aplicatia e exclusa de la optimizarea bateriei (Doze)? Numai asa nu moare in background. */
    private fun isIgnoringBatteryOpt(): Boolean = try {
        if (android.os.Build.VERSION.SDK_INT < 23) true
        else (ctx.getSystemService(Context.POWER_SERVICE) as android.os.PowerManager)
            .isIgnoringBatteryOptimizations(ctx.packageName)
    } catch (_: Exception) { false }

    @Volatile private var running = false
    private var server: ServerSocket? = null
    private val sensorHandler = android.os.Handler(android.os.Looper.getMainLooper())
    private var thread: Thread? = null

    fun start() {
        if (running) return
        running = true
        thread = Thread {
            try {
                // TCP pe loopback: simplu si fiabil, accesibil doar local
                val srv = ServerSocket(0, 8, java.net.InetAddress.getByName("127.0.0.1"))
                server = srv
                tcpPort = srv.localPort
                // anuntam python-ul unde sa se conecteze
                File(socketFile.parentFile, "bridge.port").writeText(srv.localPort.toString())
                // scriem si in HOME (files/home) pentru ca python il cauta acolo
                try {
                    val home = File(ctx.filesDir, "home"); home.mkdirs()
                    File(home, "bridge.port").writeText(srv.localPort.toString())
                } catch (_: Exception) {}
                Log.i(TAG, "bridge pe 127.0.0.1:${srv.localPort}")
                while (running) {
                    val cli = try { srv.accept() } catch (e: Exception) {
                        if (running) Log.w(TAG, "accept: ${e.message}")
                        null
                    } ?: continue
                    Thread { serve(cli) }.start()
                }
            } catch (e: Exception) {
                Log.e(TAG, "bridge fatal: ${e.message}")
            }
        }.apply { isDaemon = true }
        thread!!.start()
    }

    @Volatile var tcpPort: Int = 0

    fun stop() {
        running = false
        try { server?.close() } catch (_: Exception) {}
        // sterge toate fisierele de port ca python sa nu citeasca un port mort
        try { socketFile.delete() } catch (_: Exception) {}
        try { File(socketFile.parentFile, "bridge.port").delete() } catch (_: Exception) {}
        try { File(ctx.filesDir, "home/bridge.port").delete() } catch (_: Exception) {}
        tcpPort = 0
    }

    private fun serve(sock: Socket) {
        try {
            val br = BufferedReader(InputStreamReader(sock.inputStream))
            val out = OutputStreamWriter(sock.outputStream)
            while (true) {
                val line = br.readLine() ?: break
                if (line.isBlank()) continue
                val resp = try { handle(JSONObject(line)) }
                catch (e: Exception) { JSONObject().put("ok", false).put("error", e.toString()) }
                out.write(resp.toString()); out.write("\n"); out.flush()
            }
        } catch (_: Exception) {
        } finally { try { sock.close() } catch (_: Exception) {} }
    }

    // ---------------- dispatcher ----------------
    private fun handle(req: JSONObject): JSONObject {
        val tool = req.optString("tool")
        val action = req.optString("action")
        val p = req.optJSONObject("params") ?: JSONObject()
        return when (tool) {
            "sensors" -> sensors(action, p)
            "camera" -> camera(action, p)
            "location" -> location(action, p)
            "battery" -> battery(action)
            "clipboard" -> clipboard(action, p)
            "notify" -> notify(p)
            "vibrate" -> vibrate(p)
            "tts" -> tts(action, p)
            "volume" -> volume(action, p)
            "wifi" -> wifi()
            "device" -> device()
            "apps" -> apps(action, p)
            "intent" -> intent(p)
            "settings" -> settings(action, p)
            "tourl" -> toUri(action, p)
            "system" -> systemInfo(action, p)
            "storage" -> storageInfo()
            "processes" -> processes()
            "network" -> networkInfo()
            "display" -> displayInfo()
            "audio" -> audioInfo()
            "telephony" -> telephonyInfo()
            "nfc" -> nfcInfo()
            "usb" -> usbInfo()
            "appinfo" -> appInfo(p)
            "install" -> installApk(action, p)
            "eval" -> refl.execute(p.optJSONObject("expr") ?: JSONObject())
            "services" -> refl.execute(JSONObject().put("op", "services"))
            "info" -> refl.execute(JSONObject().put("op", "info").put("target", p.optString("target")).put("filter", p.optString("filter")))
            "ui" -> ui(action, p)
            "notif" -> notif(action, p)
            "ime" -> ime(action, p)
            "vpn" -> vpn(action, p)
            "capture" -> capture(action, p)
            "guard" -> guard(action, p)
            else -> JSONObject().put("ok", false).put("error", "unknown tool: $tool")
        }
    }

    // ---------------- FIX 2: NotificationListener ----------------
    private fun notif(action: String, p: JSONObject): JSONObject {
        val svc = AgentNotificationListener.instance
            ?: return JSONObject().put("ok", false).put("error",
                "notification listener NOT enabled. Enable it with: cmd notification allow_listener net.sys32.agent/.AgentNotificationListener")
        return when (action) {
            "list", "read", "dump" -> svc.dump(p.optInt("limit", 100)).put("ok", true)
            "cancel" -> {
                val key = p.optString("key")
                if (key.isNotEmpty()) JSONObject().put("ok", svc.cancelKey(key))
                else JSONObject().put("ok", true).put("cancelled", svc.cancelPkg(p.optString("package", p.optString("pkg"))))
            }
            "snooze" -> JSONObject().put("ok", svc.snooze(p.optString("key"), p.optLong("ms", 60000)))
            else -> JSONObject().put("ok", false).put("error", "notif action? use list|cancel|snooze")
        }
    }

    // ---------------- FIX 3: IME ----------------
    /** Mesaj de ajutor in functie de starea IME: neselectat vs neinstalat. */
    private fun imeNotActiveHelp(): String {
        val pkg = ctx.packageName
        val installed = try {
            val imm = ctx.getSystemService(android.content.Context.INPUT_METHOD_SERVICE) as android.view.inputmethod.InputMethodManager
            imm.enabledInputMethodList.any { it.packageName == pkg }
        } catch (_: Exception) { false }
        return if (installed)
            "IME is INSTALLED but NOT the active keyboard (this is normal - not a fault). " +
            "To use it: adbsh 'ime set $pkg/.AgentIme'. It stays available in the keyboard list."
        else
            "IME not enabled at all. Add it: adbsh 'settings put secure enabled_input_methods <current>:$pkg/.AgentIme' then adbsh 'ime set $pkg/.AgentIme'"
    }

    private fun ime(action: String, p: JSONObject): JSONObject {
        val svc = AgentIme.instance
            ?: return JSONObject().put("ok", false).put("error", imeNotActiveHelp())
        return when (action) {
            "read", "field" -> svc.readField().put("ok", true)
            "type", "inject" -> JSONObject().put("ok", svc.inject(p.optString("text"), p.optInt("delete", 0)))
            "key" -> JSONObject().put("ok", svc.keyEvent(p.optInt("code")))
            "keys", "events" -> JSONObject().put("ok", true).put("keys", svc.dumpKeys(p.optInt("limit", 100)))
            else -> JSONObject().put("ok", false).put("error", "ime action? use read|type|key|keys")
        }
    }

    // ---------------- FIX 4: VpnService ----------------
    private fun vpn(action: String, p: JSONObject): JSONObject {
        if (AgentVpn.instance == null) {
            try { ctx.startService(android.content.Intent(ctx, AgentVpn::class.java)) } catch (_: Exception) {}
        }
        val svc = AgentVpn.instance
            ?: return JSONObject().put("ok", false).put("error",
                "vpn service started but instance is null (wait a second and retry)")
        return when (action) {
            "status" -> JSONObject().put("ok", true).put("status", svc.status())
            "establish", "up" -> JSONObject().put("ok", true).put("result", svc.establish(p.optString("name", "agent0")))
            "close", "down" -> { svc.closeTun(); JSONObject().put("ok", true).put("status", "down") }
            else -> JSONObject().put("ok", false).put("error", "vpn action? use status|establish|close")
        }
    }

    // ---------------- FIX 5: MediaProjection capture ----------------
    private fun capture(action: String, p: JSONObject): JSONObject {
        // BATERIE: la cerere pornim consimtamantul + serviciul, altfel NU mai ruleaza permanent.
        if (action == "start" || action == "request") {
            return try {
                val act = ctx as? net.sys32.agent.MainActivity
                if (act != null) {
                    act.runOnUiThread { act.requestScreenCapture() }
                    JSONObject().put("ok", true).put("capture", "consent requested - confirm on screen")
                } else JSONObject().put("ok", false).put("error", "no activity - open the app once")
            } catch (e: Exception) { JSONObject().put("ok", false).put("error", "$e") }
        }
        val svc = ScreenCaptureService.instance
            ?: return JSONObject().put("ok", false).put("error",
                "capture NOT running (by design: it no longer starts at boot to save battery). Start it on demand with capture action=start")
        return when (action) {
            "status" -> JSONObject().put("ok", true).put("status", svc.status())
            "grab", "shot" -> JSONObject().put("ok", true)
                .put("result", svc.grab(p.optString("path", ctx.filesDir.absolutePath + "/capture.png")))
            // BATERIE: inchide sesiunea MediaProjection (elibereaza display-ul virtual).
            "stop", "release" -> {
                ScreenCaptureService.stop(ctx)
                JSONObject().put("ok", true).put("capture", "stopped")
            }
            else -> JSONObject().put("ok", false).put("error", "capture action? use status|grab|stop")
        }
    }

    // ---------------- FIX 7: persistence guard ----------------
    private fun guard(action: String, p: JSONObject): JSONObject = when (action) {
        "start" -> { GuardService.start(ctx); JSONObject().put("ok", true).put("guard", "started") }
        "schedule" -> { GuardService.schedule(ctx); JSONObject().put("ok", true).put("alarm", "scheduled") }
        "status" -> {
            val r = JSONObject().put("ok", true)
            r.put("foreground", AgentService.running)
            r.put("accessibility", AgentAccessibilityService.instance != null)
            r.put("notif_listener", AgentNotificationListener.instance != null)
            // IME: distingem ACTIV vs INSTALAT-dar-neselectat vs LIPSA (altfel modelul
            // crede ca e o defectiune cand e doar neselectat - bug de diagnoza).
            val pkg = ctx.packageName
            val imeOn = AgentIme.instance != null
            val installed = try {
                android.view.inputmethod.InputMethodManager::class.java.let {
                    val imm = ctx.getSystemService(android.content.Context.INPUT_METHOD_SERVICE) as android.view.inputmethod.InputMethodManager
                    imm.enabledInputMethodList.any { it.packageName == pkg }
                }
            } catch (_: Exception) { false }
            val selected = try {
                android.provider.Settings.Secure.getString(ctx.contentResolver, android.provider.Settings.Secure.DEFAULT_INPUT_METHOD) ?: ""
            } catch (_: Exception) { "" }
            val isDefault = selected.startsWith(pkg)
            r.put("ime", imeOn)
            r.put("ime_state", when {
                imeOn -> "active"
                installed && isDefault -> "selected_but_not_bound"
                installed -> "installed_not_selected"
                else -> "not_installed"
            })
            r.put("ime_selected", isDefault)
            // celelalte servicii: stare detaliata
            r.put("accessibility_state", if (AgentAccessibilityService.instance != null) "active" else accessibilityEnabledHint())
            r.put("notif_state", if (AgentNotificationListener.instance != null) "active" else "disabled_needs_allow_listener")
            r
        }
        else -> JSONObject().put("ok", false).put("error", "guard action? use start|schedule|status")
    }

    /** Spune daca a11y e pornit in settings dar serviciul nu e bound, sau oprit complet. */
    private fun accessibilityEnabledHint(): String {
        return try {
            val cur = android.provider.Settings.Secure.getString(ctx.contentResolver,
                android.provider.Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES) ?: ""
            if (cur.contains(ctx.packageName)) "enabled_but_not_bound_yet" else "disabled"
        } catch (_: Exception) { "unknown" }
    }

    // ---------------- UI (AccessibilityService) ----------------
    /** Vedere + control asupra altor aplicatii, prin AgentAccessibilityService. */
    private fun ui(action: String, p: JSONObject): JSONObject {
        // wake/sleep NU depind de accessibility: tin ecranul aprins/treaz cind agentul lucreaza.
        if (action == "wake" || action == "screenon") {
            AgentService.wakeScreen(ctx)
            return JSONObject().put("ok", true).put("screen", "on")
                .put("hint", "the screen turns on; remember to call ui sleep at the end of the task")
        }
        if (action == "sleep" || action == "screenoff") {
            AgentService.sleepScreen(ctx)
            return JSONObject().put("ok", true).put("screen", "auto-off")
        }
        if (action == "service") {
            return JSONObject()
                .put("ok", true)
                .put("foreground", AgentService.running)
                .put("accessibility", AgentAccessibilityService.instance != null)
                .put("ignore_battery_opt", isIgnoringBatteryOpt())
        }
        val svc = AgentAccessibilityService.instance
            ?: return err("accessibility service NOT enabled. Activeaza: Settings > Accessibility > Agent (control ecran). "
                    + "Without it, Android forbids typing/tapping in other apps (INJECT_EVENTS is a system permission).")
        return try {
            when (action) {
                "shot", "screenshot", "capture" -> svc.captureScreen(
                    p.optString("path", ctx.filesDir.absolutePath + "/a11y_shot.png")
                )
                "read", "screen", "tree" -> svc.readScreen(
                    p.optInt("depth", p.optInt("max_depth", 20)),
                    p.optInt("max", p.optInt("max_nodes", 250)),
                    p.optBoolean("compact", true),       // text lizibil (default), nu JSON umflat
                    p.optBoolean("textonly", p.optBoolean("text_only", false)),
                    p.optString("package", p.optString("pkg", ""))
                )
                "find", "search", "query" -> svc.findNodes(
                    p.optString("find", p.optString("text", p.optString("query", ""))),
                    p.optBoolean("exact", false),
                    p.optBoolean("clickable", p.optBoolean("clickable_only", false)),
                    p.optInt("max", 20)
                )
                "settext", "type", "text" -> {
                    val find = p.optString("find", p.optString("field", ""))
                    val text = p.optString("text", "")
                    val exact = p.optBoolean("exact", false)
                    val replace = p.optBoolean("replace", true)
                    svc.setText(find, text, exact, replace)
                }
                "click" -> svc.click(
                    p.optString("find", p.optString("text", "")),
                    p.optInt("x", -1), p.optInt("y", -1),
                    p.optBoolean("exact", false)
                )
                "tap" -> svc.tap(p.optInt("x", -1), p.optInt("y", -1))
                "swipe" -> svc.swipe(
                    p.optInt("x1", -1), p.optInt("y1", -1),
                    p.optInt("x2", -1), p.optInt("y2", -1),
                    p.optLong("ms", 300)
                )
                "scroll" -> svc.scroll(p.optString("dir", "down"), p.optString("find", ""))
                "back" -> svc.global("back")
                "home" -> svc.global("home")
                "recents" -> svc.global("recents")
                "notifications" -> svc.global("notifications")
                "quicksettings" -> svc.global("quicksettings")
                "screenshot" -> svc.global("screenshot")
                "lockscreen" -> svc.global("lockscreen")
                "global" -> svc.global(p.optString("what", "back"))
                "openapp", "open" -> svc.openApp(p.optString("package", p.optString("pkg", "")))
                "windows" -> svc.windowsList()
                "status", "info" -> JSONObject()
                    .put("ok", true)
                    .put("enabled", true)
                    .put("service", "AgentAccessibilityService")
                else -> err("unknown ui action: $action (read|settext|click|tap|swipe|scroll|back|home|recents|notifications|quicksettings|screenshot|lockscreen|openapp|windows|status|wake|sleep|service)")
            }
        } catch (e: Exception) {
            err("ui error: ${e.message}")
        }
    }

    private fun ok(data: Any?): JSONObject =
        JSONObject().put("ok", true).put("data", data ?: JSONObject.NULL)

    private fun err(msg: String): JSONObject = JSONObject().put("ok", false).put("error", msg)

    // ---------------- SENSORS ----------------
    private val sensorTypes = mapOf(
        "accelerometer" to Sensor.TYPE_ACCELEROMETER,
        "gyroscope" to Sensor.TYPE_GYROSCOPE,
        "magnetic" to Sensor.TYPE_MAGNETIC_FIELD,
        "orientation" to Sensor.TYPE_ORIENTATION,
        "light" to Sensor.TYPE_LIGHT,
        "pressure" to Sensor.TYPE_PRESSURE,
        "proximity" to Sensor.TYPE_PROXIMITY,
        "temperature" to Sensor.TYPE_AMBIENT_TEMPERATURE,
        "humidity" to Sensor.TYPE_RELATIVE_HUMIDITY,
        "gravity" to Sensor.TYPE_GRAVITY,
        "linear_acceleration" to Sensor.TYPE_LINEAR_ACCELERATION,
        "rotation_vector" to Sensor.TYPE_ROTATION_VECTOR,
        "step_counter" to Sensor.TYPE_STEP_COUNTER,
        "significant_motion" to Sensor.TYPE_SIGNIFICANT_MOTION,
    )

    private fun sensors(action: String, p: JSONObject): JSONObject {
        val sm = ctx.getSystemService(Context.SENSOR_SERVICE) as SensorManager
        return when (action) {
            "list" -> {
                val arr = JSONArray()
                for (s in sm.getSensorList(Sensor.TYPE_ALL)) {
                    arr.put(JSONObject()
                        .put("name", s.name)
                        .put("type", s.type)
                        .put("stringType", s.stringType)
                        .put("vendor", s.vendor)
                        .put("version", s.version)
                        .put("maxRange", s.maximumRange.toDouble())
                        .put("resolution", s.resolution.toDouble())
                        .put("power", s.power.toDouble()))
                }
                ok(arr)
            }
            "read" -> {
                val name = p.optString("name", "accelerometer")
                val type = sensorTypes[name] ?: return err("unknown sensor: $name (try: ${sensorTypes.keys.joinToString(", ")})")
                val secs = p.optDouble("seconds", 2.0)
                val s = sm.getDefaultSensor(type) ?: return err("sensor not present: $name")
                val latch = CountDownLatch(1)
                var last: FloatArray? = null
                val lis = object : SensorEventListener {
                    override fun onSensorChanged(e: SensorEvent) { last = e.values.copyOf() }
                    override fun onAccuracyChanged(s: Sensor?, a: Int) {}
                }
                sm.registerListener(lis, s, SensorManager.SENSOR_DELAY_GAME, sensorHandler)
                Thread { try { latch.await((secs * 1000).toLong(), TimeUnit.MILLISECONDS) } catch (_: Exception) {} }.start()
                Thread.sleep((secs * 1000).toLong())
                sm.unregisterListener(lis)
                val v = last ?: return err("no data from $name")
                val vals = JSONArray(); v.forEach { vals.put(it.toDouble()) }
                ok(JSONObject().put("sensor", name).put("values", vals)
                    .put("unit", sensorUnit(name)).put("seconds", secs))
            }
            "stream" -> {
                // Stream continuu: colecteaza N esantioane de la unul/mai multi senzori intr-o fereastra de timp.
                val names = if (p.has("name")) listOf(p.optString("name"))
                            else p.optJSONArray("names")?.let { a -> (0 until a.length()).map { a.getString(it) } }
                            ?: listOf("accelerometer")
                val secs = p.optDouble("seconds", 3.0)
                val maxSamples = p.optInt("max", 100)
                val data = JSONObject()
                val listeners = ArrayList<SensorEventListener>()
                for (nm in names) {
                    val type = sensorTypes[nm] ?: return err("unknown sensor: $nm (try: ${sensorTypes.keys.joinToString(", ")})")
                    val s = sm.getDefaultSensor(type) ?: continue
                    val samples = JSONArray()
                    val lis = object : SensorEventListener {
                        override fun onSensorChanged(e: SensorEvent) {
                            if (samples.length() >= maxSamples) return
                            val row = JSONArray()
                            row.put(e.timestamp)
                            e.values.forEach { row.put(it.toDouble()) }
                            samples.put(row)
                        }
                        override fun onAccuracyChanged(s: Sensor?, a: Int) {}
                    }
                    sm.registerListener(lis, s, SensorManager.SENSOR_DELAY_GAME, sensorHandler)
                    listeners.add(lis)
                    data.put(nm, JSONObject().put("unit", sensorUnit(nm)).put("samples", samples))
                }
                if (listeners.isEmpty()) return err("none of the requested sensors are present: ${names.joinToString(", ")}")
                Thread.sleep((secs * 1000).toLong())
                for ((i, lis) in listeners.withIndex()) {
                    try { sm.unregisterListener(lis) } catch (_: Exception) {}
                }
                ok(JSONObject().put("seconds", secs).put("kind", "stream").put("data", data)
                    .put("counts", JSONObject().apply { for (nm in names) data.optJSONObject(nm)?.let { put(nm, it.optJSONArray("samples")?.length() ?: 0) } }))
            }
            "all" -> {
                // Citeste TOATE senzorii disponibili intr-un singur apel (o valoare fiecare).
                val secs = p.optDouble("seconds", 3.0)
                val all = sm.getSensorList(Sensor.TYPE_ALL)
                val data = JSONObject()
                val listeners = ArrayList<Pair<Sensor, SensorEventListener>>()
                val lastVals = HashMap<Int, FloatArray>()
                for (s in all) {
                    try {
                        val lis = object : SensorEventListener {
                            override fun onSensorChanged(e: SensorEvent) { lastVals[e.sensor.type] = e.values.copyOf() }
                            override fun onAccuracyChanged(s: Sensor?, a: Int) {}
                        }
                        sm.registerListener(lis, s, SensorManager.SENSOR_DELAY_FASTEST, sensorHandler)
                        listeners.add(s to lis)
                    } catch (_: Exception) {}
                }
                Thread.sleep((secs * 1000).toLong())
                for ((s, lis) in listeners) { try { sm.unregisterListener(lis) } catch (_: Exception) {} }
                for (s in all) {
                    val v = lastVals[s.type]
                    val o = JSONObject().put("name", s.name).put("type", s.type).put("stringType", s.stringType)
                        .put("vendor", s.vendor).put("power", s.power.toDouble()).put("maxRange", s.maximumRange.toDouble())
                    if (v != null) {
                        val vals = JSONArray(); v.forEach { vals.put(it.toDouble()) }
                        o.put("values", vals)
                    } else o.put("values", JSONArray())
                    data.put(s.stringType, o)
                }
                ok(JSONObject().put("seconds", secs).put("count", all.size).put("sensors", data))
            }
            else -> err("sensors: action must be list|read|stream|all")
        }
    }

    private fun sensorUnit(n: String) = when (n) {
        "accelerometer", "gravity", "linear_acceleration" -> "m/s^2"
        "gyroscope" -> "rad/s"
        "magnetic" -> "uT"
        "light" -> "lx"
        "pressure" -> "hPa"
        "proximity" -> "cm"
        "temperature" -> "C"
        "humidity" -> "%"
        "orientation" -> "degrees"
        else -> ""
    }

    // ---------------- CAMERA ----------------
    private fun camera(action: String, p: JSONObject): JSONObject {
        val cm = ctx.getSystemService(Context.CAMERA_SERVICE) as CameraManager
        return when (action) {
            "list" -> {
                val arr = JSONArray()
                for (id in cm.cameraIdList) {
                    val ch = cm.getCameraCharacteristics(id)
                    val facing = ch.get(CameraCharacteristics.LENS_FACING)
                    arr.put(JSONObject().put("id", id)
                        .put("facing", if (facing == CameraCharacteristics.LENS_FACING_FRONT) "front" else "back"))
                }
                ok(arr)
            }
            "photo" -> {
                // Delegam catre CameraActivity (are nevoie de UI/permisiune)
                val path = p.optString("path", File(ctx.getExternalFilesDir(null), "photo_${System.currentTimeMillis()}.jpg").absolutePath)
                val lens = p.optString("lens", "back")
                CameraCapture.request(ctx, path, lens)
                ok(JSONObject().put("requested", true).put("path", path)
                    .put("note", "the photo is taken in the background; it appears in a few seconds at the given path"))
            }
            else -> err("camera: action must be list|photo")
        }
    }

    // ---------------- LOCATION ----------------
    private fun location(action: String, p: JSONObject): JSONObject {
        val lm = ctx.getSystemService(Context.LOCATION_SERVICE) as LocationManager
        return when (action) {
            "last" -> {
                var loc: Location? = null
                for (prov in lm.getProviders(true)) {
                    try { lm.getLastKnownLocation(prov)?.let { if (loc == null || it.time > loc!!.time) loc = it } }
                    catch (_: SecurityException) {}
                }
                val l = loc ?: return err("no last known location (GPS off or no fix yet)")
                ok(JSONObject().put("lat", l.latitude).put("lon", l.longitude)
                    .put("accuracy", l.accuracy.toDouble()).put("provider", l.provider)
                    .put("time", l.time).put("altitude", l.altitude))
            }
            "fresh" -> {
                // Fix CU ADEVARAT NOU: cere update-uri de la provider si asteapta primul onLocationChanged.
                // getCurrentLocation/fused pot returna instant un fix din cache; asta NU face asta.
                val prov = p.optString("provider", "gps")
                val secs = p.optDouble("seconds", 30.0)
                val latch = CountDownLatch(1)
                var got: Location? = null
                val lis = object : LocationListener {
                    override fun onLocationChanged(l: Location) { if (got == null) { got = l; latch.countDown() } }
                    override fun onProviderEnabled(p: String) {}
                    override fun onProviderDisabled(p: String) {}
                    override fun onStatusChanged(p: String?, status: Int, extras: Bundle?) {}
                }
                try {
                    lm.requestLocationUpdates(prov, 0L, 0f, lis, android.os.Looper.getMainLooper())
                } catch (e: SecurityException) {
                    return err("permission denied for location: $e")
                } catch (e: Exception) {
                    return err("requestLocationUpdates failed: $e")
                }
                latch.await((secs * 1000).toLong(), TimeUnit.MILLISECONDS)
                try { lm.removeUpdates(lis) } catch (_: Exception) {}
                val l = got ?: return err("no NEW fix from $prov within ${secs}s (move to open sky; provider may be disabled)")
                val ageMs = System.currentTimeMillis() - l.time
                ok(JSONObject().put("lat", l.latitude).put("lon", l.longitude)
                    .put("accuracy", l.accuracy.toDouble()).put("provider", l.provider)
                    .put("time", l.time).put("age_ms", ageMs).put("age_s", ageMs / 1000.0)
                    .put("altitude", l.altitude).put("fresh", true).put("forced", true))
            }
            "providers" -> {
                val arr = JSONArray()
                for (prov in lm.getProviders(true)) arr.put(prov)
                ok(arr)
            }
            "current" -> {
                // Forteaza un fix PROASPAT (nu cache). Alege providerul si asteapta un callback real.
                val prov = p.optString("provider", "fused")
                val secs = p.optDouble("seconds", 15.0)
                val cs = CancellationSignal()
                val latch = CountDownLatch(1)
                var got: Location? = null
                val consumer = Consumer<Location> { loc -> got = loc; latch.countDown() }
                try {
                    lm.getCurrentLocation(prov, cs, ctx.mainExecutor, consumer)
                } catch (e: SecurityException) {
                    return err("permission denied for location: $e")
                } catch (e: Exception) {
                    return err("getCurrentLocation failed: $e")
                }
                latch.await((secs * 1000).toLong(), TimeUnit.MILLISECONDS)
                try { cs.cancel() } catch (_: Exception) {}
                val l = got ?: return err("no fresh fix within ${secs}s (provider=$prov; move to open sky, GPS may be off or indoor)")
                val ageMs = System.currentTimeMillis() - l.time
                ok(JSONObject().put("lat", l.latitude).put("lon", l.longitude)
                    .put("accuracy", l.accuracy.toDouble()).put("provider", l.provider)
                    .put("time", l.time).put("age_ms", ageMs).put("age_s", ageMs / 1000.0)
                    .put("altitude", l.altitude).put("fresh", true))
            }
            else -> err("location: action must be last|fresh|current|providers")
        }
    }

    // ---------------- BATTERY ----------------
    private fun battery(action: String = "get"): JSONObject {
        val bm = ctx.getSystemService(Context.BATTERY_SERVICE) as BatteryManager
        // sticky broadcast ACTION_BATTERY_CHANGED = sursa COMPLETA pe care o poate citi un app normal
        val i = ctx.registerReceiver(null, android.content.IntentFilter(Intent.ACTION_BATTERY_CHANGED))
        val level = bm.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY)
        val status = i?.getIntExtra(BatteryManager.EXTRA_STATUS, -1) ?: -1
        val plugged = i?.getIntExtra(BatteryManager.EXTRA_PLUGGED, -1) ?: -1
        val temp = (i?.getIntExtra(BatteryManager.EXTRA_TEMPERATURE, 0) ?: 0) / 10.0
        val volt = i?.getIntExtra(BatteryManager.EXTRA_VOLTAGE, 0) ?: 0
        val health = i?.getIntExtra(BatteryManager.EXTRA_HEALTH, -1) ?: -1
        val tech = i?.getStringExtra(BatteryManager.EXTRA_TECHNOLOGY)
        val present = i?.getBooleanExtra(BatteryManager.EXTRA_PRESENT, false) ?: false
        val scale = i?.getIntExtra(BatteryManager.EXTRA_SCALE, -1) ?: -1
        val statusName = when (status) {
            1 -> "UNKNOWN"; 2 -> "CHARGING"; 3 -> "DISCHARGING"; 4 -> "NOT_CHARGING"; 5 -> "FULL"; else -> "?" }
        val healthName = when (health) {
            1 -> "UNKNOWN"; 2 -> "GOOD"; 3 -> "OVERHEAT"; 4 -> "DEAD"; 5 -> "OVER_VOLTAGE";
            6 -> "UNSPECIFIED_FAILURE"; 7 -> "COLD"; else -> "?" }
        val plugName = when (plugged) {
            0 -> "none"; 1 -> "AC"; 2 -> "USB"; 4 -> "WIRELESS"; 8 -> "DOCK"; else -> "?" }
        val base = JSONObject()
            .put("level", level).put("charging", status == BatteryManager.BATTERY_STATUS_CHARGING || status == BatteryManager.BATTERY_STATUS_FULL)
            .put("status", status).put("status_name", statusName)
            .put("plugged", plugged != 0).put("plug_type", plugName)
            .put("temperature_c", temp).put("voltage_mv", volt)
            .put("health", health).put("health_name", healthName)
            .put("technology", tech ?: "").put("present", present).put("scale", scale)
        if (action != "full") return ok(base)
        // varianta COMPLETA: adauga toate proprietatile BatteryManager + campurile extras din sticky
        val curNow = try { bm.getIntProperty(BatteryManager.BATTERY_PROPERTY_CURRENT_NOW) } catch (_: Exception) { Int.MIN_VALUE }
        val curAvg = try { bm.getIntProperty(BatteryManager.BATTERY_PROPERTY_CURRENT_AVERAGE) } catch (_: Exception) { Int.MIN_VALUE }
        val chgCounter = try { bm.getLongProperty(BatteryManager.BATTERY_PROPERTY_CHARGE_COUNTER) } catch (_: Exception) { Long.MIN_VALUE }
        val energy = try { bm.getIntProperty(BatteryManager.BATTERY_PROPERTY_ENERGY_COUNTER) } catch (_: Exception) { Int.MIN_VALUE }
        val timeToFull = try { bm.computeChargeTimeRemaining() } catch (_: Exception) { -1L }
        val pm = ctx.getSystemService(Context.POWER_SERVICE) as android.os.PowerManager
        val capacityPctOfRaw = if (chgCounter > 0 && level > 0) (chgCounter.toDouble() * 100.0 / level) else -1.0
        return ok(base
            .put("current_now_uA", curNow).put("current_average_uA", curAvg)
            .put("charge_counter_uAh", chgCounter).put("energy_counter_nWh", energy)
            .put("time_to_full_ms", timeToFull)
            .put("battery_full_estimate_mAh", if (capacityPctOfRaw > 0) (capacityPctOfRaw / 1000.0) else -1.0)
            .put("power_save_mode", pm.isPowerSaveMode)
            .put("thermal_status", pm.currentThermalStatus)
            .put("is_charging", bm.isCharging)
            .put("note", "health/technology/present/scale come from the ACTION_BATTERY_CHANGED sticky broadcast - readable by any normal app; Samsung SEM_* properties and BATTERY_STATS need root/system perms"))
    }

    // ---------------- CLIPBOARD ----------------
    private fun clipboard(action: String, p: JSONObject): JSONObject {
        val cm = ctx.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        return when (action) {
            "get" -> ok(JSONObject().put("text", cm.primaryClip?.getItemAt(0)?.text?.toString() ?: ""))
            "set" -> {
                val t = p.optString("text", "")
                cm.setPrimaryClip(ClipData.newPlainText("agent", t))
                ok(JSONObject().put("set", t.length))
            }
            else -> err("clipboard: action must be get|set")
        }
    }

    // ---------------- NOTIFY ----------------
    private fun notify(p: JSONObject): JSONObject {
        val title = p.optString("title", "Agent")
        val text = p.optString("text", "")
        Notifier.show(ctx, title, text)
        return ok(JSONObject().put("shown", true))
    }

    // ---------------- VIBRATE ----------------
    private fun vibrate(p: JSONObject): JSONObject {
        val ms = p.optLong("ms", 300)
        val vib = if (Build.VERSION.SDK_INT >= 31) {
            (ctx.getSystemService(Context.VIBRATOR_MANAGER_SERVICE) as VibratorManager).defaultVibrator
        } else {
            @Suppress("DEPRECATION") ctx.getSystemService(Context.VIBRATOR_SERVICE) as Vibrator
        }
        if (Build.VERSION.SDK_INT >= 26) vib.vibrate(VibrationEffect.createOneShot(ms, VibrationEffect.DEFAULT_AMPLITUDE))
        else @Suppress("DEPRECATION") vib.vibrate(ms)
        return ok(JSONObject().put("vibrated_ms", ms))
    }

    // ---------------- TTS ----------------
    private fun tts(action: String, p: JSONObject): JSONObject {
        return when (action) {
            "say" -> { Speaker.say(ctx, p.optString("text", "")); ok(JSONObject().put("spoken", true)) }
            "stop" -> { Speaker.stop(); ok(JSONObject().put("stopped", true)) }
            else -> err("tts: action must be say|stop")
        }
    }

    // ---------------- VOLUME ----------------
    private fun volume(action: String, p: JSONObject): JSONObject {
        val am = ctx.getSystemService(Context.AUDIO_SERVICE) as AudioManager
        return when (action) {
            "get" -> ok(JSONObject().put("music", am.getStreamVolume(AudioManager.STREAM_MUSIC))
                .put("music_max", am.getStreamMaxVolume(AudioManager.STREAM_MUSIC))
                .put("ring", am.getStreamVolume(AudioManager.STREAM_RING)))
            "set" -> {
                val lvl = p.optInt("level", 5)
                am.setStreamVolume(AudioManager.STREAM_MUSIC, lvl, 0)
                ok(JSONObject().put("music", lvl))
            }
            "mute" -> { am.adjustStreamVolume(AudioManager.STREAM_MUSIC, AudioManager.ADJUST_MUTE, 0); ok(JSONObject().put("muted", true)) }
            else -> err("volume: action must be get|set|mute")
        }
    }

    // ---------------- WIFI ----------------
    private fun wifi(): JSONObject {
        @Suppress("DEPRECATION")
        val wm = ctx.applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
        @Suppress("DEPRECATION")
        val info = wm.connectionInfo
        return ok(JSONObject().put("enabled", wm.isWifiEnabled)
            .put("ssid", info?.ssid?.replace("\"", "") ?: "")
            .put("ip", intToIp(info?.ipAddress ?: 0))
            .put("rssi", info?.rssi ?: 0))
    }

    private fun intToIp(i: Int) = "${i and 0xff}.${(i shr 8) and 0xff}.${(i shr 16) and 0xff}.${(i shr 24) and 0xff}"

    // ---------------- DEVICE ----------------
    private fun device(): JSONObject {
        val dm = ctx.resources.displayMetrics
        return ok(JSONObject()
            .put("model", Build.MODEL).put("manufacturer", Build.MANUFACTURER)
            .put("brand", Build.BRAND).put("device", Build.DEVICE)
            .put("android", Build.VERSION.RELEASE).put("sdk", Build.VERSION.SDK_INT)
            .put("abis", JSONArray(Build.SUPPORTED_ABIS.toList()))
            .put("screen", "${dm.widthPixels}x${dm.heightPixels}")
            .put("density", dm.density)
            .put("locales", JSONArray(java.util.Locale.getAvailableLocales().map { it.toString() }.distinct().take(30)))
            .put("timezone", java.util.TimeZone.getDefault().id))
    }

    // ---------------- APPS ----------------
    private fun apps(action: String, p: JSONObject): JSONObject {
        val pm = ctx.packageManager
        return when (action) {
            "list" -> {
                val arr = JSONArray()
                val pkgs = if (Build.VERSION.SDK_INT >= 33)
                    pm.getInstalledPackages(android.content.pm.PackageManager.PackageInfoFlags.of(0L))
                else @Suppress("DEPRECATION") pm.getInstalledPackages(0)
                for (pi in pkgs) {
                    arr.put(JSONObject().put("package", pi.packageName)
                        .put("label", pi.applicationInfo?.loadLabel(pm)?.toString() ?: ""))
                }
                ok(arr)
            }
            "launch" -> {
                val pkg = p.optString("package", "")
                val i = ctx.packageManager.getLaunchIntentForPackage(pkg) ?: return err("no launch intent for $pkg")
                i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                ctx.startActivity(i)
                ok(JSONObject().put("launched", pkg))
            }
            else -> err("apps: action must be list|launch")
        }
    }

    // ---------------- INTENT ----------------
    private fun intent(p: JSONObject): JSONObject {
        val action = p.optString("action", "")
        val data = p.optString("data", "")
        val i = Intent(action)
        if (data.isNotEmpty()) i.data = Uri.parse(data)
        i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        return try { ctx.startActivity(i); ok(JSONObject().put("sent", action)) }
        catch (e: Exception) { err("intent failed: ${e.message}") }
    }

    // ---------------- SETTINGS ----------------
    private fun settings(action: String, p: JSONObject): JSONObject {
        return when (action) {
            "get" -> {
                val ns = p.optString("ns", "system")
                val key = p.optString("key", "")
                val v = when (ns) {
                    "global" -> Settings.Global.getString(ctx.contentResolver, key)
                    "secure" -> Settings.Secure.getString(ctx.contentResolver, key)
                    else -> Settings.System.getString(ctx.contentResolver, key)
                }
                ok(JSONObject().put("key", key).put("value", v ?: ""))
            }
            "open" -> {
                val label = p.optString("which", "settings")
                val act = when (label) {
                    "wifi" -> Settings.ACTION_WIFI_SETTINGS
                    "bluetooth" -> Settings.ACTION_BLUETOOTH_SETTINGS
                    "location" -> Settings.ACTION_LOCATION_SOURCE_SETTINGS
                    "display" -> Settings.ACTION_DISPLAY_SETTINGS
                    "sound" -> Settings.ACTION_SOUND_SETTINGS
                    "apps" -> Settings.ACTION_APPLICATION_SETTINGS
                    "battery" -> Settings.ACTION_BATTERY_SAVER_SETTINGS
                    else -> Settings.ACTION_SETTINGS
                }
                ctx.startActivity(Intent(act).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                ok(JSONObject().put("opened", label))
            }
            else -> err("settings: action must be get|open")
        }
    }

    // ---------------- TO URI (share/open) ----------------

    // ---------------- SYSTEM / INFRA ----------------
    private fun systemInfo(action: String, p: JSONObject): JSONObject {
        val rt = Runtime.getRuntime()
        val am = ctx.getSystemService(Context.ACTIVITY_SERVICE) as android.app.ActivityManager
        val mi = android.app.ActivityManager.MemoryInfo(); am.getMemoryInfo(mi)
        val pm = ctx.getSystemService(Context.POWER_SERVICE) as android.os.PowerManager
        val o = JSONObject()
        o.put("model", Build.MODEL).put("manufacturer", Build.MANUFACTURER).put("brand", Build.BRAND)
        o.put("device", Build.DEVICE).put("product", Build.PRODUCT).put("hardware", Build.HARDWARE)
        o.put("board", Build.BOARD).put("bootloader", Build.BOOTLOADER).put("fingerprint", Build.FINGERPRINT)
        o.put("android", Build.VERSION.RELEASE).put("sdk", Build.VERSION.SDK_INT)
        o.put("security_patch", Build.VERSION.SECURITY_PATCH)
        o.put("supported_abis", Build.SUPPORTED_ABIS.toList())
        o.put("cpu_abi", Build.CPU_ABI)
        o.put("cpu_cores", rt.availableProcessors())
        o.put("uptime_ms", android.os.SystemClock.elapsedRealtime())
        o.put("uptime_h", android.os.SystemClock.elapsedRealtime() / 3600000.0)
        o.put("heap_max_mb", rt.maxMemory() / 1048576)
        o.put("heap_used_mb", (rt.totalMemory() - rt.freeMemory()) / 1048576)
        o.put("ram_total_mb", mi.totalMem / 1048576)
        o.put("ram_avail_mb", mi.availMem / 1048576)
        o.put("ram_low", mi.lowMemory)
        o.put("is_rooted", (try { java.io.File("/system/xbin/su").exists() || java.io.File("/system/bin/su").exists() } catch (_: Exception) { false }))
        o.put("thermal_status", pm.currentThermalStatus)
        o.put("power_save", pm.isPowerSaveMode)
        o.put("device_idle", pm.isDeviceIdleMode)
        o.put("interactive", pm.isInteractive)
        if (action == "full") {
            // adauga toate build props utile
            val props = JSONObject()
            for (k in listOf("ro.build.version.release","ro.build.version.sdk","ro.build.display.id","ro.build.date",
                    "ro.product.model","ro.product.brand","ro.product.name","ro.product.device","ro.hardware",
                    "ro.serialno","ro.boot.serialno","ro.chipname","ro.board.platform","ro.build.characteristics",
                    "ro.boot.hardware","ro.revision","ro.build.host","ro.build.user","dalvik.vm.heapsize",
                    "ro.product.cpu.abilist","ro.crypto.state","ro.debuggable","ro.secure","ro.build.type","ro.build.tags")) {
                try {
                    val c = Class.forName("android.os.SystemProperties")
                    val m = c.getMethod("get", String::class.java)
                    props.put(k, m.invoke(null, k) as String)
                } catch (_: Exception) {}
            }
            o.put("build_props", props)
        }
        return ok(o)
    }

    // ---------------- STORAGE ----------------
    private fun storageInfo(): JSONObject {
        val o = JSONObject()
        try {
            val stat = android.os.StatFs(Environment.getDataDirectory().path)
            o.put("data_total_mb", stat.blockCountLong * stat.blockSizeLong / 1048576)
            o.put("data_free_mb", stat.availableBlocksLong * stat.blockSizeLong / 1048576)
            o.put("data_used_mb", (stat.blockCountLong - stat.availableBlocksLong) * stat.blockSizeLong / 1048576)
        } catch (_: Exception) {}
        try {
            val ext = Environment.getExternalStorageDirectory()
            if (ext != null) {
                val st = android.os.StatFs(ext.path)
                o.put("external_total_mb", st.blockCountLong * st.blockSizeLong / 1048576)
                o.put("external_free_mb", st.availableBlocksLong * st.blockSizeLong / 1048576)
            }
        } catch (_: Exception) {}
        val dirs = JSONObject()
        for ((k, f) in listOf("files" to ctx.filesDir, "cache" to ctx.cacheDir,
                              "external_files" to ctx.getExternalFilesDir(null),
                              "code_cache" to ctx.codeCacheDir, "no_backup" to ctx.noBackupFilesDir)) {
            if (f != null) dirs.put(k, f.absolutePath)
        }
        o.put("paths", dirs)
        return ok(o)
    }

    // ---------------- PROCESSES ----------------
    private fun processes(): JSONObject {
        val am = ctx.getSystemService(Context.ACTIVITY_SERVICE) as android.app.ActivityManager
        val arr = JSONArray()
        try {
            for (pi in am.runningAppProcesses ?: emptyList()) {
                arr.put(JSONObject().put("process", pi.processName).put("pid", pi.pid)
                    .put("uid", pi.uid).put("importance", pi.importance).put("pkg", pi.pkgList?.toList() ?: emptyList<String>()))
            }
        } catch (_: Exception) {}
        return ok(JSONObject().put("processes", arr))
    }

    // ---------------- NETWORK ----------------
    private fun networkInfo(): JSONObject {
        val o = JSONObject()
        val cm = ctx.getSystemService(Context.CONNECTIVITY_SERVICE) as android.net.ConnectivityManager
        try {
            val n = cm.activeNetwork
            val caps = if (n != null) cm.getNetworkCapabilities(n) else null
            o.put("active_network", n?.toString() ?: "none")
            if (caps != null) {
                o.put("wifi", caps.hasTransport(android.net.NetworkCapabilities.TRANSPORT_WIFI))
                o.put("cellular", caps.hasTransport(android.net.NetworkCapabilities.TRANSPORT_CELLULAR))
                o.put("ethernet", caps.hasTransport(android.net.NetworkCapabilities.TRANSPORT_ETHERNET))
                o.put("vpn", caps.hasTransport(android.net.NetworkCapabilities.TRANSPORT_VPN))
                o.put("bluetooth", caps.hasTransport(android.net.NetworkCapabilities.TRANSPORT_BLUETOOTH))
                o.put("down_kbps", caps.linkDownstreamBandwidthKbps)
                o.put("up_kbps", caps.linkUpstreamBandwidthKbps)
                o.put("metered", !caps.hasCapability(android.net.NetworkCapabilities.NET_CAPABILITY_NOT_METERED))
                o.put("internet", caps.hasCapability(android.net.NetworkCapabilities.NET_CAPABILITY_INTERNET))
            }
        } catch (_: Exception) {}
        val wm = ctx.getSystemService(Context.WIFI_SERVICE) as WifiManager
        try {
            val info = wm.connectionInfo
            o.put("wifi_ssid", info?.ssid).put("wifi_bssid", info?.bssid)
            o.put("wifi_link_speed", info?.linkSpeed).put("wifi_rssi", info?.rssi)
            o.put("wifi_frequency", info?.frequency).put("wifi_ip", info?.ipAddress)
            o.put("wifi_enabled", wm.isWifiEnabled)
        } catch (_: Exception) {}
        return ok(o)
    }

    // ---------------- DISPLAY ----------------
    private fun displayInfo(): JSONObject {
        val o = JSONObject()
        val dm = ctx.getSystemService(Context.DISPLAY_SERVICE) as android.hardware.display.DisplayManager
        try {
            val disp = dm.getDisplay(android.view.Display.DEFAULT_DISPLAY)
            if (disp != null) {
                val m = android.util.DisplayMetrics()
                disp.getMetrics(m)
                o.put("width_px", m.widthPixels).put("height_px", m.heightPixels)
                o.put("density", m.density.toDouble()).put("density_dpi", m.densityDpi)
                o.put("refresh_rate", disp.refreshRate.toDouble())
                o.put("rotation", disp.rotation)
                o.put("state", disp.state)
                o.put("name", disp.name)
                try {
                    val modes = disp.supportedModes
                    val arr = JSONArray()
                    for (mode in modes) arr.put(JSONObject().put("w", mode.physicalWidth).put("h", mode.physicalHeight).put("rate", mode.refreshRate.toDouble()))
                    o.put("modes", arr)
                } catch (_: Exception) {}
            }
        } catch (_: Exception) {}
        val wm = ctx.getSystemService(Context.WINDOW_SERVICE) as android.view.WindowManager
        o.put("brightness", android.provider.Settings.System.getInt(ctx.contentResolver, android.provider.Settings.System.SCREEN_BRIGHTNESS, -1))
        o.put("brightness_mode", android.provider.Settings.System.getInt(ctx.contentResolver, android.provider.Settings.System.SCREEN_BRIGHTNESS_MODE, -1))
        o.put("screen_timeout_ms", android.provider.Settings.System.getInt(ctx.contentResolver, android.provider.Settings.System.SCREEN_OFF_TIMEOUT, -1))
        return ok(o)
    }

    // ---------------- AUDIO ----------------
    private fun audioInfo(): JSONObject {
        val am = ctx.getSystemService(Context.AUDIO_SERVICE) as AudioManager
        val o = JSONObject()
        for ((name, stream) in listOf("music" to AudioManager.STREAM_MUSIC, "ring" to AudioManager.STREAM_RING,
                "alarm" to AudioManager.STREAM_ALARM, "notification" to AudioManager.STREAM_NOTIFICATION,
                "voice_call" to AudioManager.STREAM_VOICE_CALL, "system" to AudioManager.STREAM_SYSTEM)) {
            o.put(name, JSONObject().put("vol", am.getStreamVolume(stream)).put("max", am.getStreamMaxVolume(stream)).put("min", am.getStreamMinVolume(stream)))
        }
        o.put("ringer_mode", am.ringerMode).put("is_music_active", am.isMusicActive)
        o.put("mode", am.mode).put("speakerphone", am.isSpeakerphoneOn).put("bluetooth_sco", am.isBluetoothScoOn)
        try {
            val devs = am.getDevices(AudioManager.GET_DEVICES_ALL)
            val arr = JSONArray()
            for (d in devs) arr.put(JSONObject().put("type", d.type).put("name", d.productName?.toString() ?: "").put("is_sink", d.isSink))
            o.put("devices", arr)
        } catch (_: Exception) {}
        return ok(o)
    }

    // ---------------- TELEPHONY ----------------
    private fun telephonyInfo(): JSONObject {
        val o = JSONObject()
        try {
            val tm = ctx.getSystemService(Context.TELEPHONY_SERVICE) as android.telephony.TelephonyManager
            o.put("network_operator", tm.networkOperatorName).put("network_country", tm.networkCountryIso)
            o.put("sim_operator", tm.simOperatorName).put("sim_country", tm.simCountryIso)
            o.put("phone_type", tm.phoneType).put("sim_state", tm.simState)
            o.put("network_type", tm.networkType).put("is_roaming", tm.isNetworkRoaming)
        } catch (_: Exception) {}
        return ok(o)
    }

    // ---------------- NFC ----------------
    private fun nfcInfo(): JSONObject {
        val o = JSONObject()
        try {
            val nm = ctx.getSystemService(Context.NFC_SERVICE) as android.nfc.NfcManager
            val a = nm.defaultAdapter
            o.put("enabled", a?.isEnabled)
            o.put("adapter", a?.toString() ?: "")
        } catch (_: Exception) {}
        return ok(o)
    }

    // ---------------- USB ----------------
    private fun usbInfo(): JSONObject {
        val o = JSONObject()
        try {
            val um = ctx.getSystemService(Context.USB_SERVICE) as android.hardware.usb.UsbManager
            val arr = JSONArray()
            for ((name, dev) in um.deviceList) {
                arr.put(JSONObject().put("name", name).put("vendor", dev.vendorId).put("product", dev.productId))
            }
            o.put("devices", arr)
        } catch (_: Exception) {}
        return ok(o)
    }

    // ---------------- APPINFO ----------------
    private fun appInfo(p: JSONObject): JSONObject {
        val pkg = p.optString("package", ctx.packageName)
        val o = JSONObject()
        try {
            val pm = ctx.packageManager
            val pi = pm.getPackageInfo(pkg, android.content.pm.PackageManager.GET_PERMISSIONS or android.content.pm.PackageManager.GET_META_DATA)
            val ai = pi.applicationInfo
            o.put("package", pkg).put("version_name", pi.versionName).put("version_code", if (Build.VERSION.SDK_INT >= 28) pi.longVersionCode else pi.versionCode.toLong())
            o.put("installed", pi.firstInstallTime).put("updated", pi.lastUpdateTime)
            o.put("label", pm.getApplicationLabel(ai!!).toString())
            o.put("target_sdk", ai.targetSdkVersion).put("min_sdk", ai.minSdkVersion)
            o.put("source_dir", ai.sourceDir)
            o.put("data_dir", ai.dataDir)
            o.put("system_app", (ai.flags and android.content.pm.ApplicationInfo.FLAG_SYSTEM) != 0)
            o.put("enabled", ai.enabled).put("debuggable", (ai.flags and android.content.pm.ApplicationInfo.FLAG_DEBUGGABLE) != 0)
            val requested = pi.requestedPermissions ?: emptyArray<String>()
            val granted = JSONArray(); val denied = JSONArray()
            for (perm in requested) {
                if (pm.checkPermission(perm, pkg) == android.content.pm.PackageManager.PERMISSION_GRANTED) granted.put(perm) else denied.put(perm)
            }
            o.put("permissions_granted", granted).put("permissions_denied", denied)
            val sigs = JSONArray()
            for (si in pi.signatures ?: emptyArray<android.content.pm.Signature>()) sigs.put(si.toCharsString().take(64))
            o.put("signatures", sigs)
        } catch (e: Exception) { o.put("error", e.toString()) }
        return ok(o)
    }

    private fun toUri(action: String, p: JSONObject): JSONObject {
        val path = p.optString("path", "")
        val f = File(path)
        if (!f.exists()) return err("not found: $path")
        val mime = p.optString("mime", "image/*")
        // FileProvider ar fi ideal; folosim content uri simplu pentru fisiere din app
        val u = Uri.fromFile(f)
        val i = Intent(Intent.ACTION_VIEW).setDataAndType(u, mime).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        return try { ctx.startActivity(i); ok(JSONObject().put("opened", path)) }
        catch (e: Exception) { err("open failed: ${e.message}") }
    }

    // ---------------- instalare APK FARA adb (instalator de sistem) ----------------
    /**
     * ★ DE CE EXISTA: canalul adb al aplicatiei (uid=2000) poate fi blocat de adbd - pe acest
     * device adbd a respins chiar si o semnatura VALIDA si nu a mai afisat dialogul de aprobare,
     * deci `pm install` prin shell nu era disponibil deloc. Aici instalarea trece prin
     * instalatorul DE SISTEM: aplicatia ii da un content:// (FileProvider) si operatorul
     * confirma cu un tap pe 'Install'. Nu depinde de adb, shell sau root.
     * params: path = calea APK-ului (ex. /storage/emulated/0/Download/Agent/workspace/x.apk)
     */
    private fun installApk(action: String, p: JSONObject): JSONObject {
        val path = p.optString("path", "")
        if (path.isBlank()) return err("lipseste params.path (calea APK-ului)")
        val f = File(path)
        if (!f.exists()) return err("APK inexistent: $path")
        if (action == "status") {
            return ok(JSONObject().put("path", path).put("size", f.length()))
        }
        return try {
            val uri = androidx.core.content.FileProvider.getUriForFile(
                ctx, ctx.packageName + ".fileprovider", f)
            val i = Intent(Intent.ACTION_VIEW)
                .setDataAndType(uri, "application/vnd.android.package-archive")
                .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            ctx.startActivity(i)
            ok(JSONObject().put("opened", path).put("uri", uri.toString())
                .put("nota", "confirma instalarea pe ecran: un tap pe Install"))
        } catch (e: Exception) {
            err("install intent failed: ${e.message}")
        }
    }
}
