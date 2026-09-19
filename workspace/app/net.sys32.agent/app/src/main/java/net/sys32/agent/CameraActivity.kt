package net.sys32.agent

import android.app.Activity
import android.content.Context
import android.content.pm.PackageManager
import android.graphics.ImageFormat
import android.hardware.camera2.*
import android.media.ImageReader
import android.os.Bundle
import android.os.Handler
import android.os.HandlerThread
import android.util.Log
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import java.io.File
import java.io.FileOutputStream

/**
 * Activitate transparenta care face o singura poza cu Camera2 si se inchide.
 * Lansata din bridge cu: path + lens (back|front).
 */
class CameraActivity : Activity() {
    companion object { const val TAG = "AgentCam" }

    private var thread: HandlerThread? = null
    private var handler: Handler? = null
    private var device: CameraDevice? = null
    private var session: CameraCaptureSession? = null
    private var reader: ImageReader? = null
    private var outPath: String = ""
    private var lens: String = "back"

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        outPath = intent.getStringExtra("path") ?: ""
        lens = intent.getStringExtra("lens") ?: "back"

        if (ContextCompat.checkSelfPermission(this, android.Manifest.permission.CAMERA)
            != PackageManager.PERMISSION_GRANTED) {
            ActivityCompat.requestPermissions(this, arrayOf(android.Manifest.permission.CAMERA), 77)
            return
        }
        shoot()
    }

    override fun onRequestPermissionsResult(req: Int, perms: Array<out String>, res: IntArray) {
        super.onRequestPermissionsResult(req, perms, res)
        if (req == 77 && res.isNotEmpty() && res[0] == PackageManager.PERMISSION_GRANTED) shoot()
        else { Log.w(TAG, "permisiune camera refuzata"); finish() }
    }

    private fun shoot() {
        try {
            thread = HandlerThread("cam").also { it.start() }
            handler = Handler(thread!!.looper)
            val cm = getSystemService(Context.CAMERA_SERVICE) as CameraManager
            var camId: String? = null
            for (id in cm.cameraIdList) {
                val f = cm.getCameraCharacteristics(id).get(CameraCharacteristics.LENS_FACING)
                val want = if (lens == "front") CameraCharacteristics.LENS_FACING_FRONT else CameraCharacteristics.LENS_FACING_BACK
                if (f == want) { camId = id; break }
            }
            if (camId == null) camId = cm.cameraIdList.firstOrNull()
            if (camId == null) { finish(); return }

            val ch = cm.getCameraCharacteristics(camId)
            val size = ch.get(CameraCharacteristics.SENSOR_INFO_PIXEL_ARRAY_SIZE)!!
            val w = minOf(size.width, 1920); val h = minOf(size.height, 1080)
            reader = ImageReader.newInstance(w, h, ImageFormat.JPEG, 1)
            reader!!.setOnImageAvailableListener({ r ->
                val img = r.acquireLatestImage() ?: return@setOnImageAvailableListener
                try {
                    val buf = img.planes[0].buffer
                    val bytes = ByteArray(buf.remaining()); buf.get(bytes)
                    val f = File(outPath); f.parentFile?.mkdirs()
                    FileOutputStream(f).use { it.write(bytes) }
                    Log.i(TAG, "foto salvata: $outPath (${bytes.size} bytes)")
                    File(filesDir, "last_photo.path").writeText(outPath)
                } catch (e: Exception) { Log.e(TAG, "save: ${e.message}") }
                finally { img.close(); runOnUiThread { cleanup(); finish() } }
            }, handler)

            cm.openCamera(camId, object : CameraDevice.StateCallback() {
                override fun onOpened(d: CameraDevice) {
                    device = d
                    try {
                        val req = d.createCaptureRequest(CameraDevice.TEMPLATE_STILL_CAPTURE)
                        req.addTarget(reader!!.surface)
                        req.set(CaptureRequest.CONTROL_MODE, CameraMetadata.CONTROL_MODE_AUTO)
                        d.createCaptureSession(listOf(reader!!.surface), object : CameraCaptureSession.StateCallback() {
                            override fun onConfigured(s: CameraCaptureSession) {
                                session = s
                                try { s.capture(req.build(), null, handler) } catch (e: Exception) { Log.e(TAG,"capture: ${e.message}"); finish() }
                            }
                            override fun onConfigureFailed(s: CameraCaptureSession) { Log.e(TAG,"configure failed"); finish() }
                        }, handler)
                    } catch (e: Exception) { Log.e(TAG, "req: ${e.message}"); finish() }
                }
                override fun onDisconnected(d: CameraDevice) { d.close(); finish() }
                override fun onError(d: CameraDevice, e: Int) { Log.e(TAG,"camera error $e"); d.close(); finish() }
            }, handler)
        } catch (e: Exception) {
            Log.e(TAG, "shoot: ${e.message}")
            finish()
        }
    }

    private fun cleanup() {
        try { session?.close() } catch (_: Exception) {}
        try { device?.close() } catch (_: Exception) {}
        try { reader?.close() } catch (_: Exception) {}
        try { thread?.quitSafely() } catch (_: Exception) {}
    }

    override fun onDestroy() { super.onDestroy(); cleanup() }
}
