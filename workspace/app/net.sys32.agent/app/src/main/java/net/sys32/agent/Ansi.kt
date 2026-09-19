package net.sys32.agent

import android.graphics.Color
import android.graphics.Typeface
import android.text.Spannable
import android.text.SpannableStringBuilder
import android.text.style.ForegroundColorSpan
import android.text.style.StyleSpan
import android.text.style.UnderlineSpan
import android.text.style.StrikethroughSpan
import android.text.style.BackgroundColorSpan

/**
 * Converteste textul cu secvente ANSI (SGR) intr-un Spannable colorat.
 * Suporta: 30-37, 90-97, 38;5;N / 48;5;N (256 culori), bold(1), italic(3),
 * underline(4), strike(9), reset(0) si normal-off (22,23,24).
 */
object Ansi {

    data class Style(
        val fg: Int? = null,
        val bg: Int? = null,
        val bold: Boolean = false,
        val italic: Boolean = false,
        val underline: Boolean = false,
        val strike: Boolean = false,
    )

    // paleta ANSI 16 culori (adaptata pentru fundal inchis, ca un terminal modern)
    private val base16 = intArrayOf(
        0x000000, 0xE06C75, 0x98C379, 0xE5C07B, 0x61AFEF, 0xC678DD, 0x56B6C2, 0xABB2BF,
        0x5C6370, 0xE06C75, 0x98C379, 0xE5C07B, 0x61AFEF, 0xC678DD, 0x56B6C2, 0xFFFFFF
    )

    private fun color256(n: Int): Int = when {
        n < 16 -> base16[n]
        n < 232 -> {
            // cub 6x6x6
            val i = n - 16
            val r = (i / 36) % 6; val g = (i / 6) % 6; val b = i % 6
            val f = { v: Int -> if (v == 0) 0 else 55 + v * 40 }
            Color.rgb(f(r), f(g), f(b))
        }
        n < 256 -> {
            val v = 8 + (n - 232) * 10
            Color.rgb(v, v, v)
        }
        else -> Color.WHITE
    }

    /** Aplica parametrii SGR peste stilul curent. */
    private fun apply(params: List<Int>, st: Style): Pair<Style, Boolean> {
        var s = st
        var resetPending = false
        var i = 0
        while (i < params.size) {
            when (val p = params[i]) {
                0 -> s = Style()
                1 -> s = s.copy(bold = true)
                3 -> s = s.copy(italic = true)
                4 -> s = s.copy(underline = true)
                9 -> s = s.copy(strike = true)
                22 -> s = s.copy(bold = false)
                23 -> s = s.copy(italic = false)
                24 -> s = s.copy(underline = false)
                29 -> s = s.copy(strike = false)
                39 -> s = s.copy(fg = null)
                49 -> s = s.copy(bg = null)
                in 30..37 -> s = s.copy(fg = base16[p - 30])
                in 90..97 -> s = s.copy(fg = base16[p - 90 + 8])
                in 40..47 -> s = s.copy(bg = base16[p - 40])
                in 100..107 -> s = s.copy(bg = base16[p - 100 + 8])
                38, 48 -> {
                    val isFg = p == 38
                    if (i + 2 < params.size && params[i + 1] == 5) {
                        val c = color256(params[i + 2])
                        s = if (isFg) s.copy(fg = c) else s.copy(bg = c)
                        i += 2
                    } else if (i + 4 < params.size && params[i + 1] == 2) {
                        val c = Color.rgb(params[i + 2].coerceIn(0, 255), params[i + 3].coerceIn(0, 255), params[i + 4].coerceIn(0, 255))
                        s = if (isFg) s.copy(fg = c) else s.copy(bg = c)
                        i += 4
                    }
                }
            }
            i++
        }
        return s to resetPending
    }

    private fun span(st: Style, sb: SpannableStringBuilder, start: Int, end: Int) {
        if (end <= start) return
        st.fg?.let { sb.setSpan(ForegroundColorSpan(it), start, end, Spannable.SPAN_EXCLUSIVE_EXCLUSIVE) }
        st.bg?.let { sb.setSpan(BackgroundColorSpan(it), start, end, Spannable.SPAN_EXCLUSIVE_EXCLUSIVE) }
        val style = when {
            st.bold && st.italic -> Typeface.BOLD_ITALIC
            st.bold -> Typeface.BOLD
            st.italic -> Typeface.ITALIC
            else -> -1
        }
        if (style != -1) sb.setSpan(StyleSpan(style), start, end, Spannable.SPAN_EXCLUSIVE_EXCLUSIVE)
        if (st.underline) sb.setSpan(UnderlineSpan(), start, end, Spannable.SPAN_EXCLUSIVE_EXCLUSIVE)
        if (st.strike) sb.setSpan(StrikethroughSpan(), start, end, Spannable.SPAN_EXCLUSIVE_EXCLUSIVE)
    }

    /** Converteste un sir cu ANSI intr-un Spannable colorat. */
    fun toSpannable(input: String): CharSequence {
        val sb = SpannableStringBuilder()
        var st = Style()
        var i = 0
        val n = input.length
        while (i < n) {
            val c = input[i]
            if (c == '\u001B' && i + 1 < n && input[i + 1] == '[') {
                // gaseste terminatorul 'm' sau alt final
                var j = i + 2
                while (j < n && input[j] !in 'a'..'z' && input[j] !in 'A'..'Z') j++
                if (j < n) {
                    val final = input[j]
                    val body = input.substring(i + 2, j)
                    if (final == 'm') {
                        val params = body.split(';').mapNotNull { it.trim().ifEmpty { "0" }.toIntOrNull() }
                        val (ns, _) = apply(params.ifEmpty { listOf(0) }, st)
                        st = ns
                    }
                    // alte finale (H, J, K, A...) le ignoram
                    i = j + 1
                    continue
                } else {
                    i = n
                    break
                }
            } else if (c == '\r') {
                // CR: ignora (nu avem cursor in TextView)
                i++
                continue
            } else {
                val start = sb.length
                sb.append(c)
                span(st, sb, start, sb.length)
                i++
            }
        }
        return sb
    }
}
