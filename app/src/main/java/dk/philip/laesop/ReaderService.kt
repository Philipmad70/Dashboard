package dk.philip.laesop

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.AccessibilityService.ScreenshotResult
import android.accessibilityservice.AccessibilityService.TakeScreenshotCallback
import android.annotation.SuppressLint
import android.content.Intent
import android.content.res.ColorStateList
import android.graphics.Bitmap
import android.graphics.Color
import android.os.Build
import android.view.Display
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import android.graphics.PixelFormat
import android.graphics.drawable.GradientDrawable
import android.os.Handler
import android.os.Looper
import android.view.Gravity
import android.view.HapticFeedbackConstants
import android.view.MotionEvent
import android.view.View
import android.view.ViewConfiguration
import android.view.ViewGroup
import android.view.WindowManager
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import android.view.accessibility.AccessibilityWindowInfo
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.ProgressBar
import android.widget.Toast
import kotlin.math.abs
import kotlin.math.hypot

/**
 * Tilgængelighedstjeneste: viser en svævende afspil-knap.
 * Tryk = læs skærmen op. Tryk igen = stop.
 * Træk = flyt knappen. Træk ned på krydset i bunden = skjul knappen.
 */
class ReaderService : AccessibilityService() {

    companion object {
        /** Den kørende tjeneste (null, hvis den er slået fra). */
        @Volatile var instance: ReaderService? = null
            private set
    }

    private val main = Handler(Looper.getMainLooper())
    private var wm: WindowManager? = null

    private var button: FrameLayout? = null
    private var icon: ImageView? = null
    private var spinner: ProgressBar? = null

    private var target: FrameLayout? = null
    private var targetCircle: FrameLayout? = null

    private var speaker: Speaker? = null
    private val stateListener: (Speaker.State) -> Unit = { updateButton(it) }

    val isButtonShown: Boolean get() = button != null

    private fun dp(v: Float): Int = (v * resources.displayMetrics.density).toInt()

    override fun onServiceConnected() {
        super.onServiceConnected()
        instance = this
        wm = getSystemService(WINDOW_SERVICE) as WindowManager
        val sp = Speaker.get(this)
        sp.addListener(stateListener)
        speaker = sp
        applyVisibility()
        Controls.refresh(this)
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {}
    override fun onInterrupt() { speaker?.stop() }

    override fun onUnbind(intent: Intent?): Boolean {
        cleanup()
        return super.onUnbind(intent)
    }

    override fun onDestroy() {
        cleanup()
        worker.shutdownNow()
        super.onDestroy()
    }

    private fun cleanup() {
        if (instance === this) instance = null
        speaker?.let {
            it.removeListener(stateListener)
            it.stop()
        }
        speaker = null
        collectGen++
        collecting = false
        removeTarget()
        removeButton()
        Controls.refresh(this)
    }

    // ---------- Vis / skjul ----------

    /** Viser eller skjuler knappen ud fra indstillingen. */
    fun applyVisibility() {
        if (Settings(this).buttonVisible) {
            if (button == null) showButton()
        } else {
            speaker?.stop()
            removeTarget()
            removeButton()
        }
    }

    private fun removeButton() {
        button?.let { try { wm?.removeView(it) } catch (_: Exception) {} }
        button = null
        icon = null
        spinner = null
    }

    // ---------- Knappen ----------

    @SuppressLint("ClickableViewAccessibility")
    private fun showButton() {
        val windowManager = wm ?: return
        val settings = Settings(this)
        val size = dp(52f)

        val frame = FrameLayout(this).apply {
            background = GradientDrawable().apply {
                shape = GradientDrawable.OVAL
                setColor(0xEE1F2937.toInt())
                setStroke(dp(1f), 0x40FFFFFF)
            }
            contentDescription = "Læs skærmen op"
        }
        val pb = ProgressBar(this).apply {
            isIndeterminate = true
            indeterminateTintList = ColorStateList.valueOf(Color.WHITE)
            visibility = View.GONE
        }
        frame.addView(pb, FrameLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT
        ))
        val iv = ImageView(this).apply { setImageResource(R.drawable.ic_play) }
        frame.addView(iv, FrameLayout.LayoutParams(dp(22f), dp(22f), Gravity.CENTER))

        val params = WindowManager.LayoutParams(
            size, size,
            WindowManager.LayoutParams.TYPE_ACCESSIBILITY_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
            PixelFormat.TRANSLUCENT
        ).apply {
            gravity = Gravity.TOP or Gravity.START
            x = settings.buttonX
            y = settings.buttonY
        }

        var downX = 0f
        var downY = 0f
        var startX = 0
        var startY = 0
        var dragging = false
        var overTarget = false
        val slop = ViewConfiguration.get(this).scaledTouchSlop.toFloat()

        frame.setOnTouchListener { v, e ->
            when (e.actionMasked) {
                MotionEvent.ACTION_DOWN -> {
                    downX = e.rawX; downY = e.rawY
                    startX = params.x; startY = params.y
                    dragging = false
                    overTarget = false
                    v.alpha = 0.8f
                }
                MotionEvent.ACTION_MOVE -> {
                    val dx = e.rawX - downX
                    val dy = e.rawY - downY
                    if (!dragging && (abs(dx) > slop || abs(dy) > slop)) {
                        dragging = true
                        showTarget()
                    }
                    if (dragging) {
                        params.x = startX + dx.toInt()
                        params.y = startY + dy.toInt()
                        try { windowManager.updateViewLayout(v, params) } catch (_: Exception) {}
                        val now = isOverTarget(e.rawX, e.rawY)
                        if (now != overTarget) {
                            overTarget = now
                            highlightTarget(now)
                            if (now) v.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
                        }
                    }
                }
                MotionEvent.ACTION_UP -> {
                    v.alpha = 1f
                    if (dragging) {
                        removeTarget()
                        if (overTarget) {
                            // Skjul – men husk den gamle plads
                            main.post {
                                Controls.setVisible(this, false)
                                Toast.makeText(
                                    applicationContext,
                                    "Knappen er skjult. Få den frem igen fra hurtigindstillinger, widget eller app-ikonet.",
                                    Toast.LENGTH_LONG
                                ).show()
                            }
                        } else {
                            settings.buttonX = params.x
                            settings.buttonY = params.y
                        }
                    } else {
                        onButtonTap()
                    }
                }
                MotionEvent.ACTION_CANCEL -> {
                    v.alpha = 1f
                    if (dragging) removeTarget()
                }
            }
            true
        }

        windowManager.addView(frame, params)
        button = frame
        icon = iv
        spinner = pb
        updateButton(speaker?.state ?: Speaker.State.IDLE)
    }

    private fun updateButton(state: Speaker.State) {
        val b = button ?: return
        val i = icon ?: return
        val p = spinner ?: return
        when (state) {
            Speaker.State.IDLE -> {
                i.setImageResource(R.drawable.ic_play)
                p.visibility = View.GONE
                b.contentDescription = "Læs skærmen op"
            }
            Speaker.State.LOADING -> {
                i.setImageResource(R.drawable.ic_stop)
                p.visibility = View.VISIBLE
                b.contentDescription = "Henter oplæsning. Tryk for at stoppe"
            }
            Speaker.State.PLAYING -> {
                i.setImageResource(R.drawable.ic_stop)
                p.visibility = View.GONE
                b.contentDescription = "Stop oplæsning"
            }
        }
    }

    // ---------- Tryk på knappen ----------

    private val worker: ExecutorService = Executors.newSingleThreadExecutor()
    private var collectGen = 0
    private var collecting = false

    /** Læser skærmen op efter en kort pause (bruges ikke længere, men skader ikke). */
    fun readFromShortcut(delayMs: Long) {
        main.postDelayed({ onButtonTap() }, delayMs)
    }

    private fun onButtonTap() {
        val sp = speaker ?: return
        if (sp.isBusy || collecting) {
            // Stop alt
            collectGen++
            collecting = false
            sp.stop()
            updateButton(Speaker.State.IDLE)
            return
        }
        collecting = true
        val myGen = ++collectGen
        updateButton(Speaker.State.LOADING)
        val mode = Settings(this).ocrMode

        if (mode == 1) {
            startOcr(myGen, "")
            return
        }
        // Læs skærmen i baggrunden, så knappen aldrig fryser
        worker.execute {
            val text = try { readScreen() } catch (e: Exception) { "" }
            main.post {
                if (myGen != collectGen) return@post
                if (mode == 0 && wordCount(text) < 30) startOcr(myGen, text)
                else startSpeaking(myGen, text)
            }
        }
    }

    private fun wordCount(t: String): Int = t.split(Regex("\\s+")).count { it.length > 1 }

    private fun startSpeaking(gen: Int, text: String) {
        if (gen != collectGen) return
        collecting = false
        if (text.isBlank()) {
            updateButton(Speaker.State.IDLE)
            Toast.makeText(applicationContext, "Der blev ikke fundet noget tekst på skærmen.", Toast.LENGTH_LONG).show()
            return
        }
        speaker?.speak(text) { msg ->
            Toast.makeText(applicationContext, msg, Toast.LENGTH_LONG).show()
        }
    }

    // ---------- Tekstgenkendelse (billede af skærmen) ----------

    private fun startOcr(gen: Int, fallback: String) {
        if (Build.VERSION.SDK_INT < 30) {
            startSpeaking(gen, fallback)
            return
        }
        try {
            takeScreenshot(Display.DEFAULT_DISPLAY, mainExecutor, object : TakeScreenshotCallback {
                override fun onSuccess(result: ScreenshotResult) {
                    val hb = result.hardwareBuffer
                    val bmp = try {
                        Bitmap.wrapHardwareBuffer(hb, result.colorSpace)
                            ?.copy(Bitmap.Config.ARGB_8888, false)
                    } catch (e: Exception) {
                        null
                    }
                    try { hb.close() } catch (_: Exception) {}
                    if (bmp == null) {
                        startSpeaking(gen, fallback)
                        return
                    }
                    Ocr.read(bmp, statusBarHeight()) { found ->
                        bmp.recycle()
                        startSpeaking(gen, if (wordCount(found) > wordCount(fallback)) found else fallback)
                    }
                }

                override fun onFailure(errorCode: Int) {
                    startSpeaking(gen, fallback)
                }
            })
        } catch (e: Exception) {
            startSpeaking(gen, fallback)
        }
    }

    private fun statusBarHeight(): Int {
        val id = resources.getIdentifier("status_bar_height", "dimen", "android")
        return if (id > 0) resources.getDimensionPixelSize(id) else dp(24f)
    }

    // ---------- Krydset i bunden ----------

    private fun showTarget() {
        if (target != null) return
        val windowManager = wm ?: return
        val circleSize = dp(60f)
        val winSize = dp(84f)

        val container = FrameLayout(this)
        val circle = FrameLayout(this).apply {
            background = GradientDrawable().apply {
                shape = GradientDrawable.OVAL
                setColor(0xDD111827.toInt())
                setStroke(dp(1.5f), 0x66FFFFFF)
            }
        }
        val x = ImageView(this).apply { setImageResource(R.drawable.ic_close) }
        circle.addView(x, FrameLayout.LayoutParams(dp(24f), dp(24f), Gravity.CENTER))
        container.addView(circle, FrameLayout.LayoutParams(circleSize, circleSize, Gravity.CENTER))

        val params = WindowManager.LayoutParams(
            winSize, winSize,
            WindowManager.LayoutParams.TYPE_ACCESSIBILITY_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE or
                WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
            PixelFormat.TRANSLUCENT
        ).apply {
            gravity = Gravity.BOTTOM or Gravity.CENTER_HORIZONTAL
            y = dp(64f)
        }

        container.alpha = 0f
        try {
            windowManager.addView(container, params)
        } catch (_: Exception) {
            return
        }
        container.animate().alpha(1f).setDuration(150).start()
        target = container
        targetCircle = circle
    }

    private fun isOverTarget(x: Float, y: Float): Boolean {
        val c = targetCircle ?: return false
        if (c.width == 0) return false
        val loc = IntArray(2)
        c.getLocationOnScreen(loc)
        val cx = loc[0] + c.width / 2f
        val cy = loc[1] + c.height / 2f
        return hypot(x - cx, y - cy) < c.width * 0.9f
    }

    private fun highlightTarget(on: Boolean) {
        val c = targetCircle ?: return
        val s = if (on) 1.25f else 1f
        c.animate().scaleX(s).scaleY(s).setDuration(120).start()
    }

    private fun removeTarget() {
        target?.let { try { wm?.removeView(it) } catch (_: Exception) {} }
        target = null
        targetCircle = null
    }

    // ---------- Læs teksten på skærmen ----------

    private val numberOnly = Regex("^[\\d.,\\s]+[kKmM]?$")

    private var nodeCount = 0

    private fun readScreen(): String {
        val out = mutableListOf<String>()
        val seen = HashSet<String>()
        nodeCount = 0
        val roots = mutableListOf<AccessibilityNodeInfo>()

        try {
            for (w in windows) {
                if (w.type != AccessibilityWindowInfo.TYPE_APPLICATION) continue
                val r = w.root ?: continue
                if (r.packageName?.toString() == packageName) continue
                roots.add(r)
            }
        } catch (_: Exception) {}
        if (roots.isEmpty()) rootInActiveWindow?.let { roots.add(it) }

        for (r in roots) collect(r, out, seen, 0)
        return out.joinToString("\n")
    }

    /**
     * Går gennem alt på skærmen.
     * - Har noget tekst, bruges teksten (og vi går ikke længere ned, så intet læses to gange).
     * - Ellers kigges der i det, der ligger indeni.
     * - Gav det ingenting, bruges beskrivelsen (fx et opslag på Reddit, der kun har en beskrivelse).
     * Små knapper som "Del", "Svar" og tal som "1,2k" springes over.
     */
    private fun collect(
        node: AccessibilityNodeInfo?, out: MutableList<String>, seen: HashSet<String>, depth: Int
    ) {
        if (node == null || depth > 250 || nodeCount > 6000) return
        nodeCount++
        if (!node.isVisibleToUser) return
        val cls = node.className?.toString().orEmpty()

        val text = node.text?.toString()?.trim().orEmpty()
        if (text.isNotEmpty()) {
            val isSmallButton = cls.endsWith("Button") && text.length <= 20
            if (!numberOnly.matches(text) && !isSmallButton && seen.add(text)) out.add(text)
            return
        }

        val before = out.size
        for (i in 0 until node.childCount) {
            collect(node.getChild(i), out, seen, depth + 1)
        }

        if (out.size == before) {
            val desc = node.contentDescription?.toString()?.trim().orEmpty()
            if (desc.isEmpty() || numberOnly.matches(desc)) return
            val looksLikeIcon = desc.length < 25 &&
                (node.isClickable || cls.contains("Image") || cls.endsWith("Button"))
            if (!looksLikeIcon && seen.add(desc)) out.add(desc)
        }
    }
}
