package net.sys32.agent

import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.ImageFormat
import android.hardware.camera2.CameraCaptureSession
import android.hardware.camera2.CameraDevice
import android.hardware.camera2.CameraManager
import android.hardware.camera2.CameraMetadata
import android.hardware.camera2.CaptureRequest
import android.hardware.camera2.CameraCharacteristics
import android.media.ImageReader
import android.os.Build
import android.os.Handler
import android.os.HandlerThread
import android.speech.tts.TextToSpeech
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import java.io.File
import java.io.FileOutputStream
import java.util.Locale

/** Notificari simple. */
object Notifier {
    private const val CH = "agent"
    fun show(ctx: Context, title: String, text: String) {
        val nm = ctx.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        if (Build.VERSION.SDK_INT >= 26) {
            nm.createNotificationChannel(NotificationChannel(CH, "Agent", NotificationManager.IMPORTANCE_DEFAULT))
        }
        val n = NotificationCompat.Builder(ctx, CH)
            .setSmallIcon(android.R.drawable.stat_notify_chat)
            .setContentTitle(title).setContentText(text)
            .setAutoCancel(true).build()
        try { nm.notify(System.currentTimeMillis().toInt(), n) } catch (e: SecurityException) { Log.w("AgentBridge","notify: ${e.message}") }
    }
}

/** Text-to-speech partajat. */
object Speaker {
    private var tts: TextToSpeech? = null
    private var ready = false

    fun init(ctx: Context) {
        if (tts != null) return
        tts = TextToSpeech(ctx.applicationContext) { st ->
            ready = st == TextToSpeech.SUCCESS
            if (ready) try { tts?.language = Locale.getDefault() } catch (_: Exception) {}
        }
    }
    fun say(ctx: Context, text: String) {
        init(ctx)
        if (text.isEmpty()) return
        try { tts?.speak(text, TextToSpeech.QUEUE_ADD, null, "agent_${System.currentTimeMillis()}") } catch (_: Exception) {}
    }
    fun stop() { try { tts?.stop() } catch (_: Exception) {} }
}

/** Captura foto in fundal catre o cale data. */
object CameraCapture {
    private const val TAG = "AgentCam"
    @Volatile private var pending: String? = null
    @Volatile private var wantLens = "back"

    fun request(ctx: Context, path: String, lens: String) {
        pending = path; wantLens = lens
        val i = Intent(ctx, CameraActivity::class.java)
            .putExtra("path", path).putExtra("lens", lens)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        ctx.startActivity(i)
    }
}
