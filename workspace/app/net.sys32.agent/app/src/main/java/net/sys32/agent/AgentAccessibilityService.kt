package net.sys32.agent

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.graphics.Path
import android.graphics.Rect
import android.os.Build
import android.os.Bundle
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import android.view.accessibility.AccessibilityWindowInfo
import org.json.JSONArray
import org.json.JSONObject

/**
 * AgentAccessibilityService - da agentului VEDERE si CONTROL asupra altor aplicatii.
 *
 * Fara root, Android interzice injectarea de input (INJECT_EVENTS = signature).
 * AccessibilityService e calea OFICIALA: utilizatorul il activeaza o data din
 * Settings -> Accessibility, iar de atunci putem:
 *   - citi ecranul oricarei aplicatii (arborele de noduri: text, bounds, id, clasa)
 *   - scrie text intr-un camp (ACTION_SET_TEXT)  <- TASTARE reala
 *   - apasa butoane / noduri (ACTION_CLICK)
 *   - face gesturi (tap/swipe) pe ecran (dispatchGesture)
 *   - naviga: back / home / recents, deschide notificari / quick settings
 *
 * Nu e un tool in sine: e un "motor" static. AndroidBridge il cheama prin
 * obiectul singleton `instance`. Daca serviciul nu e activat in Settings,
 * instance e null si bridge-ul raspunde cu instructiuni clare.
 */
class AgentAccessibilityService : AccessibilityService() {

    companion object {
        @Volatile var instance: AgentAccessibilityService? = null
    }

    override fun onServiceConnected() {
        super.onServiceConnected()
        instance = this
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) { /* nu ascultam evenimente */ }

    override fun onInterrupt() { /* nimic */ }

    override fun onDestroy() {
        if (instance === this) instance = null
        super.onDestroy()
    }

    // ---------------- AJUTOARE ----------------

    /** Nodul radacina al ferestrei active (sau a primei ferestre daca nu exista activa). */
    private fun activeRoot(): AccessibilityNodeInfo? {
        var r = rootInActiveWindow
        if (r != null) return r
        for (w in windows) {
            if (w.type == AccessibilityWindowInfo.TYPE_APPLICATION) {
                r = w.root
                if (r != null) return r
            }
        }
        return null
    }

    private fun boundsOf(n: AccessibilityNodeInfo): Rect = Rect().also { n.getBoundsInScreen(it) }

    /** Serializeaza un nod (si, opțional, copiii recursiv) in JSON. */
    private fun nodeToJson(n: AccessibilityNodeInfo, depth: Int, maxDepth: Int, maxNodes: Int, counter: IntArray): JSONObject? {
        if (counter[0] >= maxNodes) return null
        counter[0]++
        val o = JSONObject()
        val txt = n.text?.toString()
        val desc = n.contentDescription?.toString()
        o.put("id", n.viewIdResourceName ?: JSONObject.NULL)
        o.put("cls", n.className?.toString() ?: "")
        if (!txt.isNullOrEmpty()) o.put("text", txt)
        if (!desc.isNullOrEmpty()) o.put("desc", desc)
        if (n.isClickable) o.put("clickable", true)
        if (n.isEditable) o.put("editable", true)
        if (n.isScrollable) o.put("scrollable", true)
        if (n.isCheckable) o.put("checked", n.isChecked)
        if (n.isEnabled) o.put("enabled", true)
        val b = boundsOf(n)
        if (!b.isEmpty) o.put("bounds", JSONArray(listOf(b.left, b.top, b.right, b.bottom)))
        val pkg = n.packageName?.toString()
        if (!pkg.isNullOrEmpty()) o.put("pkg", pkg)
        if (depth < maxDepth && n.childCount > 0) {
            val kids = JSONArray()
            for (i in 0 until n.childCount) {
                val c = n.getChild(i) ?: continue
                val cj = nodeToJson(c, depth + 1, maxDepth, maxNodes, counter) ?: continue
                kids.put(cj)
            }
            if (kids.length() > 0) o.put("children", kids)
        }
        return o
    }

    /** Gaseste toate nodurile care contin un text / id / descriere (cauta recursiv). */
    private fun findByText(root: AccessibilityNodeInfo, needle: String, exact: Boolean): List<AccessibilityNodeInfo> {
        val out = ArrayList<AccessibilityNodeInfo>()
        val lo = needle.lowercase()
        fun walk(n: AccessibilityNodeInfo) {
            val hay = listOfNotNull(
                n.text?.toString(), n.contentDescription?.toString(), n.viewIdResourceName
            ).joinToString(" ").lowercase()
            val hit = if (exact) hay == lo else hay.contains(lo)
            if (hit) out.add(n)
            for (i in 0 until n.childCount) n.getChild(i)?.let { walk(it) }
        }
        walk(root)
        return out
    }

    // ---------------- ACTIUNI (apelate din bridge) ----------------

    /** Numeste scurt tipul de nod, ca sa fie lizibil (TextView -> TextView). */
    private fun shortCls(n: AccessibilityNodeInfo): String {
        val c = n.className?.toString() ?: return "View"
        return c.substringAfterLast('.')
    }

    /** Nodurile care CONTEAZA (au text, descriere, id relevant sau sunt interactive). */
    private fun isRelevant(n: AccessibilityNodeInfo): Boolean {
        val txt = n.text?.toString()?.trim()
        val desc = n.contentDescription?.toString()?.trim()
        val id = n.viewIdResourceName ?: ""
        if (!txt.isNullOrEmpty()) return true
        if (!desc.isNullOrEmpty()) return true
        if (n.isEditable) return true
        if (n.isClickable && (id.isNotEmpty() || n.isCheckable)) return true
        return false
    }

    /**
     * Cea mai IMPORTANTA functie pentru agent: transforma arborele de noduri intr-o
     * LISTA TEXT compacta, nu JSON umflat cu metadate. Rezulta de ~10x mai putine
     * caractere si informatia utila (numele contactelor, butoanele) e direct vizibila.
     *
     * Format:  [n] <Cls> id=<id> "text" @[x,y] <flags>
     *   flags: E=editable  C=clickable  K=checkable(+checked)  S=scrollable  D=descriere
     */
    private fun readCompact(maxDepth: Int, maxNodes: Int, textOnly: Boolean, packageFilter: String): JSONObject {
        val root = activeRoot() ?: return JSONObject().put("ok", false)
                .put("error", "no active window (ecranul nu e disponibil)")
        val lines = ArrayList<String>()
        var count = 0
        fun walk(n: AccessibilityNodeInfo, depth: Int) {
            if (count >= maxNodes) return
            val relevant = isRelevant(n)
            if (relevant) {
                count++
                val sb = StringBuilder()
                sb.append("[").append(count).append("] ").append(shortCls(n))
                val id = n.viewIdResourceName
                if (!id.isNullOrEmpty()) sb.append(" id=").append(id.substringAfterLast('/'))
                val txt = n.text?.toString()?.trim()
                if (!txt.isNullOrEmpty()) sb.append(" \"").append(txt.replace("\n", " ")).append("\"")
                val desc = n.contentDescription?.toString()?.trim()
                if (!desc.isNullOrEmpty()) sb.append(" desc=\"").append(desc.replace("\n", " ")).append("\"")
                val b = boundsOf(n)
                if (!b.isEmpty) sb.append(" @[").append((b.left + b.right) / 2).append(",").append((b.top + b.bottom) / 2).append("]")
                val flags = StringBuilder()
                if (n.isEditable) flags.append("E")
                if (n.isClickable) flags.append("C")
                if (n.isCheckable) flags.append(if (n.isChecked) "K+" else "K-")
                if (n.isScrollable) flags.append("S")
                if (n.isEnabled == false) flags.append("!")
                if (flags.isNotEmpty()) sb.append(" <").append(flags).append(">")
                if (textOnly && txt.isNullOrEmpty() && desc.isNullOrEmpty()) {
                    // mod text-only: sarim peste nodurile fara text (dar pastram copiii)
                } else {
                    lines.add(sb.toString())
                }
            }
            if (count < maxNodes && depth < maxDepth) {
                for (i in 0 until n.childCount) n.getChild(i)?.let { walk(it, depth + 1) }
            }
        }
        walk(root, 0)
        val pkg = root.packageName?.toString() ?: ""
        if (packageFilter.isNotEmpty() && pkg != packageFilter) {
            return JSONObject().put("ok", false).put("error", "fereastra activa e $pkg, nu $packageFilter")
        }
        return JSONObject()
            .put("ok", true)
            .put("package", pkg)
            .put("nodes", count)
            .put("text", lines.joinToString("\n"))
    }

    /**
     * Caută noduri dupa text/descriere/id si le returneaza ca lista compacta.
     * E calea EFICIENTA: agentul nu citeste tot ecranul, cere direct ce il intereseaza.
     */
    fun findNodes(needle: String, exact: Boolean, clickableOnly: Boolean, max: Int): JSONObject {
        val root = activeRoot() ?: return JSONObject().put("ok", false).put("error", "no active window")
        val hits = findByText(root, needle, exact)
            .filter { !clickableOnly || it.isClickable }
            .take(max)
        val arr = JSONArray()
        for (n in hits) {
            val b = boundsOf(n)
            val o = JSONObject()
            o.put("cls", shortCls(n))
            val id = n.viewIdResourceName
            if (!id.isNullOrEmpty()) o.put("id", id)
            val t = n.text?.toString(); if (!t.isNullOrEmpty()) o.put("text", t)
            val d = n.contentDescription?.toString(); if (!d.isNullOrEmpty()) o.put("desc", d)
            if (!b.isEmpty) {
                o.put("bounds", JSONArray(listOf(b.left, b.top, b.right, b.bottom)))
                o.put("center", JSONArray(listOf((b.left + b.right) / 2, (b.top + b.bottom) / 2)))
            }
            o.put("clickable", n.isClickable)
            o.put("editable", n.isEditable)
            arr.put(o)
        }
        return JSONObject()
            .put("ok", true)
            .put("package", root.packageName?.toString() ?: "")
            .put("count", hits.size)
            .put("matches", arr)
    }

    /** Citește ecranul curent. `compact=true` (default) returneaza text lizibil, nu JSON umflat. */
    fun readScreen(maxDepth: Int, maxNodes: Int, compact: Boolean = true, textOnly: Boolean = false, packageFilter: String = ""): JSONObject {
        return if (compact) readCompact(maxDepth, maxNodes, textOnly, packageFilter)
        else {
            val root = activeRoot() ?: return JSONObject().put("ok", false).put("error", "no active window")
            val counter = intArrayOf(0)
            val tree = nodeToJson(root, 0, maxDepth, maxNodes, counter) ?: JSONObject()
            JSONObject()
                .put("ok", true)
                .put("package", root.packageName?.toString() ?: "")
                .put("nodes", counter[0])
                .put("tree", tree)
        }
    }

    /** Scrie text intr-un camp: fie dupa textul/id-ul curent al campului, fie in campul FOCUSAT, fie in primul editabil. */
    fun setText(find: String, text: String, exact: Boolean, replace: Boolean): JSONObject {
        val root = activeRoot() ?: return JSONObject().put("ok", false).put("error", "no active window")
        var target: AccessibilityNodeInfo? = null
        if (find.isNotEmpty()) {
            target = findByText(root, find, exact).firstOrNull { it.isEditable } ?: findByText(root, find, exact).firstOrNull()
        }
        if (target == null) target = root.findFocus(AccessibilityNodeInfo.FOCUS_INPUT)
        if (target == null) {
            // primul camp editabil din arbore
            fun firstEditable(n: AccessibilityNodeInfo): AccessibilityNodeInfo? {
                if (n.isEditable && n.isEnabled) return n
                for (i in 0 until n.childCount) firstEditable(n.getChild(i) ?: continue)?.let { return it }
                return null
            }
            target = firstEditable(root)
        }
        if (target == null) return JSONObject().put("ok", false).put("error", "no editable field found")
        // daca nodul nu e editabil direct, caut un parinte editabil
        var node = target
        while (!node!!.isEditable && node.parent != null) node = node.parent
        val args = Bundle()
        args.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, if (replace) text else ((node.text?.toString() ?: "") + text))
        val okc = node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args)
        return JSONObject().put("ok", okc)
            .put("action", "setText")
            .put("field", node.viewIdResourceName ?: node.className?.toString() ?: "")
            .put("value", if (replace) text else ((node.text?.toString() ?: "") + text))
            .let { if (okc) it else it.put("error", "ACTION_SET_TEXT rejected (camp read-only? sau nu e editabil)") }
    }

    /** Apasa un nod gasit dupa text/id/descriere, SAU un punct (x,y) prin gest. */
    fun click(find: String, x: Int, y: Int, exact: Boolean): JSONObject {
        if (find.isNotEmpty()) {
            val root = activeRoot() ?: return JSONObject().put("ok", false).put("error", "no active window")
            val nodes = findByText(root, find, exact)
            if (nodes.isEmpty()) return JSONObject().put("ok", false).put("error", "node not found: $find")
            // preferam un nod clickabil (sau parintele lui clickabil)
            for (n in nodes) {
                var t: AccessibilityNodeInfo? = n
                while (t != null && !t.isClickable) t = t.parent
                val tgt = t ?: n
                if (tgt.performAction(AccessibilityNodeInfo.ACTION_CLICK)) {
                    return JSONObject().put("ok", true).put("action", "click").put("on", tgt.text?.toString() ?: tgt.viewIdResourceName ?: "")
                }
            }
            // nu s-a putut click prin nod: incercam gest pe centrul primului nod
            val b = boundsOf(nodes[0])
            if (!b.isEmpty) return tap(b.centerX(), b.centerY())
            return JSONObject().put("ok", false).put("error", "node found but not clickable and no bounds")
        }
        return tap(x, y)
    }

    /** Tap la coordonate prin gest (merge chiar daca nodul nu e clickabil). */
    fun tap(x: Int, y: Int): JSONObject {
        if (Build.VERSION.SDK_INT < 24) return JSONObject().put("ok", false).put("error", "gestures need API 24+")
        val path = Path().apply { moveTo(x.toFloat(), y.toFloat()) }
        val stroke = GestureDescription.StrokeDescription(path, 0, 50)
        val gd = GestureDescription.Builder().addStroke(stroke).build()
        val done = dispatchGesture(gd, null, null)
        return JSONObject().put("ok", done).put("action", "tap").put("x", x).put("y", y)
    }

    /** Swipe/scroll intre doua puncte. */
    fun swipe(x1: Int, y1: Int, x2: Int, y2: Int, ms: Long): JSONObject {
        if (Build.VERSION.SDK_INT < 24) return JSONObject().put("ok", false).put("error", "gestures need API 24+")
        val path = Path().apply { moveTo(x1.toFloat(), y1.toFloat()); lineTo(x2.toFloat(), y2.toFloat()) }
        val stroke = GestureDescription.StrokeDescription(path, 0, ms.coerceAtLeast(1))
        val gd = GestureDescription.Builder().addStroke(stroke).build()
        val done = dispatchGesture(gd, null, null)
        return JSONObject().put("ok", done).put("action", "swipe")
    }

    /** Scroll intr-o directie pe nodul scrollabil gasit (sau pe ecran prin swipe). */
    fun scroll(dir: String, find: String): JSONObject {
        val root = activeRoot() ?: return JSONObject().put("ok", false).put("error", "no active window")
        val forward = dir.lowercase() in listOf("down", "forward", "jos")
        var node: AccessibilityNodeInfo? = null
        if (find.isNotEmpty()) node = findByText(root, find, false).firstOrNull { it.isScrollable }
        if (node == null) {
            fun firstScrollable(n: AccessibilityNodeInfo): AccessibilityNodeInfo? {
                if (n.isScrollable) return n
                for (i in 0 until n.childCount) firstScrollable(n.getChild(i) ?: continue)?.let { return it }
                return null
            }
            node = firstScrollable(root)
        }
        if (node != null && node.performAction(if (forward) AccessibilityNodeInfo.ACTION_SCROLL_FORWARD else AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD)) {
            return JSONObject().put("ok", true).put("action", "scroll").put("dir", dir).put("via", "node")
        }
        // fallback: swipe pe ecran (mijloc)
        val dm = resources.displayMetrics
        val cx = dm.widthPixels / 2
        val y1 = if (forward) (dm.heightPixels * 0.7).toInt() else (dm.heightPixels * 0.3).toInt()
        val y2 = if (forward) (dm.heightPixels * 0.3).toInt() else (dm.heightPixels * 0.7).toInt()
        return swipe(cx, y1, cx, y2, 300)
    }

    /** Navigare globala: back / home / recents / notifications / quicksettings. */
    fun global(action: String): JSONObject {
        val a = when (action.lowercase()) {
            "back" -> GLOBAL_ACTION_BACK
            "home" -> GLOBAL_ACTION_HOME
            "recents" -> GLOBAL_ACTION_RECENTS
            "notifications" -> GLOBAL_ACTION_NOTIFICATIONS
            "quicksettings", "quick" -> GLOBAL_ACTION_QUICK_SETTINGS
            "lockscreen", "lock" -> if (Build.VERSION.SDK_INT >= 28) GLOBAL_ACTION_LOCK_SCREEN else -1
            "screenshot" -> if (Build.VERSION.SDK_INT >= 30) GLOBAL_ACTION_TAKE_SCREENSHOT else -1
            "power" -> if (Build.VERSION.SDK_INT >= 30) GLOBAL_ACTION_POWER_DIALOG else -1
            else -> -1
        }
        if (a < 0) return JSONObject().put("ok", false).put("error", "unknown/unsupported global action: $action")
        val ok = performGlobalAction(a)
        return JSONObject().put("ok", ok).put("action", "global").put("what", action)
    }

    /** Deschide aplicatia dupa pachet (prin serviciu, fara sa fim in app). */
    fun openApp(pkg: String): JSONObject {
        return try {
            val i = packageManager.getLaunchIntentForPackage(pkg)
                ?: return JSONObject().put("ok", false).put("error", "no launch intent for $pkg")
            i.addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK)
            startActivity(i)
            JSONObject().put("ok", true).put("opened", pkg)
        } catch (e: Exception) {
            JSONObject().put("ok", false).put("error", "open failed: ${e.message}")
        }
    }

    /** Lista ferestrelor vizibile (pachete + tip). */
    fun windowsList(): JSONObject {
        val arr = JSONArray()
        for (w in windows) {
            val o = JSONObject()
                .put("type", w.type)
                .put("active", w.isActive)
                .put("focused", w.isFocused)
            w.root?.packageName?.toString()?.let { o.put("pkg", it) }
            val b = Rect().also { w.getBoundsInScreen(it) }
            o.put("bounds", JSONArray(listOf(b.left, b.top, b.right, b.bottom)))
            arr.put(o)
        }
        return JSONObject().put("ok", true).put("windows", arr)
    }
}
