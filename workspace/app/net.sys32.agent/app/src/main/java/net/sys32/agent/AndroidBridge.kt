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

    @Volatile private var running = false
    private var server: ServerSocket? = null
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
            "eval" -> refl.execute(p.optJSONObject("expr") ?: JSONObject())
            "services" -> refl.execute(JSONObject().put("op", "services"))
            "info" -> refl.execute(JSONObject().put("op", "info").put("target", p.optString("target")).put("filter", p.optString("filter")))
            else -> JSONObject().put("ok", false).put("error", "unknown tool: $tool")
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
                sm.registerListener(lis, s, SensorManager.SENSOR_DELAY_GAME)
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
                    sm.registerListener(lis, s, SensorManager.SENSOR_DELAY_GAME)
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
            else -> err("sensors: action must be list|read|stream")
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
                    .put("note", "foto se face in fundal; apare in cateva secunde la calea data"))
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
}
