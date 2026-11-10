package dk.philip.laesop

import android.app.Activity
import android.app.AlertDialog
import android.app.StatusBarManager
import android.appwidget.AppWidgetManager
import android.content.ComponentName
import android.content.Intent
import android.content.res.Configuration
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.Drawable
import android.graphics.drawable.GradientDrawable
import android.graphics.drawable.Icon
import android.os.Build
import android.os.Bundle
import android.provider.Settings as AndroidSettings
import android.text.Editable
import android.text.InputType
import android.text.TextWatcher
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.view.ViewGroup.LayoutParams.MATCH_PARENT
import android.view.ViewGroup.LayoutParams.WRAP_CONTENT
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.Switch
import android.widget.TextView
import android.widget.Toast

class MainActivity : Activity() {

    private lateinit var s: Settings
    private lateinit var speaker: Speaker

    private lateinit var accRow: Row
    private lateinit var accValue: TextView
    private lateinit var visSwitch: Switch
    private lateinit var voiceRow: Row
    private lateinit var autoRow: Row
    private lateinit var autoSwitch: Switch
    private lateinit var enRow: Row
    private lateinit var speedText: TextView
    private lateinit var testText: TextView
    private lateinit var ocrRow: Row

    private val ocrNames = arrayOf("Automatisk", "Altid", "Aldrig")
    private val ocrHelp = arrayOf(
        "Bruges, når der næsten ingen tekst findes – fx en PDF i Google Drive",
        "Læser altid et billede af skærmen. Virker overalt, men kan tage lidt tekst fra menuer med",
        "Læser kun den tekst, appen selv viser"
    )

    private val speakerListener: (Speaker.State) -> Unit = { st ->
        if (::testText.isInitialized) {
            testText.text = if (st == Speaker.State.IDLE) "Test stemmen" else "Stop"
        }
    }

    // ---------- Farver (lyst og mørkt tema) ----------

    private var night = false
    private val cBg get() = if (night) 0xFF000000.toInt() else 0xFFF2F2F7.toInt()
    private val cCard get() = if (night) 0xFF1C1C1E.toInt() else Color.WHITE
    private val cText get() = if (night) Color.WHITE else 0xFF111111.toInt()
    private val cSub get() = if (night) 0xFF9A9AA0.toInt() else 0xFF6B6B70.toInt()
    private val cLine get() = if (night) 0xFF2C2C2E.toInt() else 0xFFE5E5EA.toInt()
    private val cAccent get() = if (night) 0xFF7AA7E8.toInt() else 0xFF2B5C9E.toInt()
    private val cStep get() = if (night) 0xFF2C2C2E.toInt() else 0xFFEDEDF2.toInt()

    private fun dp(v: Int): Int = (v * resources.displayMetrics.density).toInt()

    // ---------- Byggeklodser ----------

    class Row(val root: LinearLayout, val title: TextView, val sub: TextView) {
        fun setSub(t: String?) {
            sub.text = t ?: ""
            sub.visibility = if (t.isNullOrEmpty()) View.GONE else View.VISIBLE
        }
    }

    private fun ripple(): Drawable? {
        val tv = TypedValue()
        theme.resolveAttribute(android.R.attr.selectableItemBackground, tv, true)
        return if (tv.resourceId != 0) getDrawable(tv.resourceId) else null
    }

    private fun section(parent: LinearLayout, title: String?): LinearLayout {
        if (title != null) {
            parent.addView(TextView(this).apply {
                text = title.uppercase()
                textSize = 12f
                letterSpacing = 0.06f
                setTextColor(cSub)
                setPadding(dp(16), dp(24), dp(16), dp(8))
            })
        }
        val card = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            background = GradientDrawable().apply {
                setColor(cCard)
                cornerRadius = dp(16).toFloat()
            }
            clipToOutline = true
        }
        parent.addView(card, LinearLayout.LayoutParams(MATCH_PARENT, WRAP_CONTENT))
        return card
    }

    /** Laver en tynd streg over rækken, hvis det ikke er den første i kortet. */
    private fun wrapper(card: LinearLayout): LinearLayout {
        val wrap = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        if (card.childCount > 0) {
            wrap.addView(View(this).apply { setBackgroundColor(cLine) },
                LinearLayout.LayoutParams(MATCH_PARENT, 1).apply { marginStart = dp(16) })
        }
        card.addView(wrap, LinearLayout.LayoutParams(MATCH_PARENT, WRAP_CONTENT))
        return wrap
    }

    private fun row(
        card: LinearLayout, title: String, sub: String? = null,
        right: View? = null, onClick: (() -> Unit)? = null
    ): Row {
        val wrap = wrapper(card)
        val line = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            minimumHeight = dp(54)
            setPadding(dp(16), dp(10), dp(14), dp(10))
        }
        val texts = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        val t = TextView(this).apply {
            text = title
            textSize = 16f
            setTextColor(cText)
        }
        val st = TextView(this).apply {
            textSize = 13f
            setTextColor(cSub)
            setPadding(0, dp(2), 0, 0)
        }
        texts.addView(t)
        texts.addView(st)
        line.addView(texts, LinearLayout.LayoutParams(0, WRAP_CONTENT, 1f))
        if (right != null) line.addView(right)
        if (onClick != null) {
            line.isClickable = true
            line.foreground = ripple()
            line.setOnClickListener { onClick() }
        }
        wrap.addView(line, LinearLayout.LayoutParams(MATCH_PARENT, WRAP_CONTENT))
        val r = Row(wrap, t, st)
        r.setSub(sub)
        return r
    }

    private fun valueText(v: String) = TextView(this).apply {
        text = v
        textSize = 15f
        setTextColor(cSub)
        setPadding(dp(8), 0, 0, 0)
    }

    private fun chevron() = TextView(this).apply {
        text = "›"
        textSize = 22f
        setTextColor(cSub)
        setPadding(dp(10), 0, 0, dp(2))
    }

    private fun field(
        card: LinearLayout, label: String, value: String, hint: String,
        password: Boolean, onChange: (String) -> Unit
    ) {
        val wrap = wrapper(card)
        val box = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(16), dp(12), dp(16), dp(10))
        }
        box.addView(TextView(this).apply {
            text = label
            textSize = 13f
            setTextColor(cSub)
        })
        val edit = EditText(this).apply {
            setText(value)
            this.hint = hint
            textSize = 16f
            setTextColor(cText)
            setHintTextColor(cSub)
            background = null
            setPadding(0, dp(4), 0, dp(2))
            isSingleLine = true
            inputType = if (password)
                InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
            else
                InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS
            addTextChangedListener(object : TextWatcher {
                override fun beforeTextChanged(c: CharSequence?, a: Int, b: Int, d: Int) {}
                override fun onTextChanged(c: CharSequence?, a: Int, b: Int, d: Int) {}
                override fun afterTextChanged(e: Editable?) { onChange(e?.toString() ?: "") }
            })
        }
        box.addView(edit, LinearLayout.LayoutParams(MATCH_PARENT, WRAP_CONTENT))
        wrap.addView(box)
    }

    private fun stepButton(label: String, onClick: () -> Unit) = TextView(this).apply {
        text = label
        textSize = 20f
        gravity = Gravity.CENTER
        setTextColor(cText)
        background = GradientDrawable().apply {
            shape = GradientDrawable.OVAL
            setColor(cStep)
        }
        foreground = ripple()
        isClickable = true
        setOnClickListener { onClick() }
        layoutParams = LinearLayout.LayoutParams(dp(36), dp(36))
    }

    private fun paragraph(card: LinearLayout, text: String) {
        val wrap = wrapper(card)
        wrap.addView(TextView(this).apply {
            this.text = text
            textSize = 15f
            setTextColor(cText)
            setLineSpacing(0f, 1.25f)
            setPadding(dp(16), dp(12), dp(16), dp(12))
        })
    }

    private fun dialogTheme() =
        if (night) android.R.style.Theme_Material_Dialog_Alert
        else android.R.style.Theme_Material_Light_Dialog_Alert

    // ---------- Skærmen ----------

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        night = (resources.configuration.uiMode and Configuration.UI_MODE_NIGHT_MASK) ==
            Configuration.UI_MODE_NIGHT_YES
        s = Settings(this)
        // Rund hastigheden til hele 0,1
        s.rate = (Math.round(s.rate / 10f) * 10).coerceIn(-50, 100)
        speaker = Speaker.get(this)
        speaker.addListener(speakerListener)

        val col = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(16), dp(28), dp(16), dp(48))
        }

        // Overskrift
        col.addView(TextView(this).apply {
            text = "Læs op"
            textSize = 32f
            setTypeface(typeface, Typeface.BOLD)
            setTextColor(cText)
            setPadding(dp(4), 0, 0, dp(2))
        })
        col.addView(TextView(this).apply {
            text = "Læser din skærm højt med en Azure-stemme"
            textSize = 15f
            setTextColor(cSub)
            setPadding(dp(4), 0, 0, 0)
        })

        // --- Knappen ---
        val knap = section(col, "Knappen")
        accValue = valueText("")
        val accBox = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            addView(accValue)
            addView(chevron())
        }
        accRow = row(knap, "Tilgængelighed", null, accBox) {
            startActivity(Intent(AndroidSettings.ACTION_ACCESSIBILITY_SETTINGS))
        }
        visSwitch = Switch(this)
        row(knap, "Vis knappen på skærmen", "Du kan også trække knappen ned på krydset", visSwitch)

        ocrRow = row(knap, "Tekst i billeder", null, chevron()) { pickOcr() }

        // --- Azure ---
        val azure = section(col, "Azure")
        field(azure, "Nøgle (KEY 1)", s.key, "Indsæt nøglen her", true) { s.key = it }
        field(azure, "Region", s.region, "northeurope", false) { s.region = it }

        // --- Stemme ---
        val stemme = section(col, "Stemme")
        voiceRow = row(stemme, "Stemme", null, chevron()) {
            pickVoice("Stemme", Voices.main, s.voice) { id ->
                s.voice = id
                updateVoiceUi()
            }
        }
        autoSwitch = Switch(this).apply {
            isChecked = s.autoLang
            setOnCheckedChangeListener { _, on ->
                s.autoLang = on
                updateVoiceUi()
            }
        }
        autoRow = row(stemme, "Find selv sproget", null, autoSwitch)
        enRow = row(stemme, "Engelsk stemme", null, chevron()) {
            pickVoice("Engelsk stemme", Voices.english, s.voiceEn) { id ->
                s.voiceEn = id
                updateVoiceUi()
            }
        }

        speedText = TextView(this).apply {
            textSize = 16f
            setTextColor(cText)
            gravity = Gravity.CENTER
            minWidth = dp(60)
        }
        val speedBox = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            addView(stepButton("−") { changeSpeed(-10) })
            addView(speedText)
            addView(stepButton("+") { changeSpeed(10) })
        }
        row(stemme, "Hastighed", null, speedBox)

        testText = TextView(this).apply {
            text = "Test stemmen"
            textSize = 16f
            setTextColor(cAccent)
        }
        val testWrap = wrapper(stemme)
        val testLine = FrameLayout(this).apply {
            minimumHeight = dp(54)
            setPadding(dp(16), dp(14), dp(16), dp(14))
            isClickable = true
            foreground = ripple()
            addView(testText, FrameLayout.LayoutParams(WRAP_CONTENT, WRAP_CONTENT, Gravity.CENTER_VERTICAL))
            setOnClickListener { testVoice() }
        }
        testWrap.addView(testLine, LinearLayout.LayoutParams(MATCH_PARENT, WRAP_CONTENT))

        // --- Få knappen frem ---
        val frem = section(col, "Få knappen frem igen")
        if (Build.VERSION.SDK_INT >= 33) {
            row(frem, "Tilføj til hurtigindstillinger", "Træk ned fra toppen af skærmen", chevron()) {
                addTile()
            }
        } else {
            row(frem, "Hurtigindstillinger",
                "Træk ned fra toppen → tryk på blyanten → træk \"Læs op\" op blandt dine knapper")
        }
        row(frem, "Tilføj widget", "En lille knap på hjemmeskærmen", chevron()) { addWidget() }
        row(frem, "Genvej på app-ikonet", "Hold fingeren på Læs op-ikonet → Vis knap eller Skjul knap")
        row(frem, "Sidebar og Nova Launcher", "Vælg Genveje → Læs op. Tryk én gang for at vise knappen, igen for at skjule den")

        // --- Hjælp ---
        val hjaelp = section(col, "Sådan bruger du den")
        paragraph(hjaelp,
            "Tryk på afspil-knappen for at læse skærmen op. Tryk igen for at stoppe.\n\n" +
            "Træk i knappen for at flytte den. Træk den ned på krydset i bunden for at skjule den.\n\n" +
            "Virker knappen ikke i en app? Markér teksten, og vælg Læs op i menuen. " +
            "Du kan også dele tekst til Læs op.")

        col.addView(TextView(this).apply {
            text = "Teksten sendes til Microsoft Azure for at blive lavet om til tale."
            textSize = 13f
            setTextColor(cSub)
            setPadding(dp(16), dp(16), dp(16), 0)
        })

        val scroll = ScrollView(this).apply {
            setBackgroundColor(cBg)
            addView(col)
        }
        setContentView(scroll)

        updateVoiceUi()
        updateSpeed()
        updateOcr()
    }

    private fun updateOcr() {
        val m = s.ocrMode.coerceIn(0, 2)
        ocrRow.setSub(ocrNames[m] + " – " + ocrHelp[m])
    }

    private fun pickOcr() {
        AlertDialog.Builder(this, dialogTheme())
            .setTitle("Tekst i billeder")
            .setSingleChoiceItems(ocrNames, s.ocrMode.coerceIn(0, 2)) { d, which ->
                d.dismiss()
                s.ocrMode = which
                updateOcr()
            }
            .setNegativeButton("Annuller", null)
            .show()
    }

    override fun onResume() {
        super.onResume()
        updateStatus()
    }

    override fun onDestroy() {
        speaker.removeListener(speakerListener)
        super.onDestroy()
    }

    // ---------- Opdatering ----------

    private fun updateStatus() {
        val on = Controls.isOn()
        accValue.text = if (on) "Til" else "Fra"
        accRow.setSub(if (on) null else "Tryk her for at slå knappen til")
        visSwitch.setOnCheckedChangeListener(null)
        visSwitch.isEnabled = on
        visSwitch.isChecked = on && Controls.isShown()
        visSwitch.setOnCheckedChangeListener { _, checked ->
            Controls.setVisible(this, checked)
        }
    }

    private fun updateVoiceUi() {
        val multi = Voices.isMultilingual(s.voice)
        voiceRow.setSub(Voices.label(s.voice, Voices.main))
        autoRow.setSub(
            if (multi) "Hjælper stemmen med at kende forskel på dansk og engelsk"
            else "Skifter til en engelsk stemme, når teksten er på engelsk"
        )
        enRow.root.visibility = if (!multi && s.autoLang) View.VISIBLE else View.GONE
        enRow.setSub(Voices.label(s.voiceEn, Voices.english))
    }

    private fun changeSpeed(delta: Int) {
        s.rate = (s.rate + delta).coerceIn(-50, 100)
        updateSpeed()
    }

    private fun updateSpeed() {
        val m = 100 + s.rate
        speedText.text = "x${m / 100},${(m % 100) / 10}"
    }

    private fun testVoice() {
        if (speaker.isBusy) {
            speaker.stop()
            return
        }
        speaker.speak(
            "Hej. Sådan lyder stemmen, når jeg læser din skærm op.\n" +
            "And this is how English text sounds."
        ) { msg -> Toast.makeText(this, msg, Toast.LENGTH_LONG).show() }
    }

    // ---------- Stemmevalg ----------

    private fun pickVoice(
        title: String, list: List<Voices.Voice>, current: String, onPick: (String) -> Unit
    ) {
        val labels = list.map { it.label } + "Anden stemme …"
        val found = list.indexOfFirst { it.id == current }
        val idx = if (found < 0) labels.size - 1 else found
        AlertDialog.Builder(this, dialogTheme())
            .setTitle(title)
            .setSingleChoiceItems(labels.toTypedArray(), idx) { d, which ->
                d.dismiss()
                if (which < list.size) onPick(list[which].id)
                else askCustomVoice(if (found < 0) current else "", onPick)
            }
            .setNegativeButton("Annuller", null)
            .show()
    }

    private fun askCustomVoice(current: String, onPick: (String) -> Unit) {
        val input = EditText(this).apply {
            setText(current)
            hint = "fx da-DK-ChristelNeural"
            isSingleLine = true
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS
        }
        val box = FrameLayout(this).apply {
            setPadding(dp(20), dp(8), dp(20), 0)
            addView(input)
        }
        AlertDialog.Builder(this, dialogTheme())
            .setTitle("Navn på stemme")
            .setView(box)
            .setPositiveButton("OK") { _, _ ->
                val v = input.text.toString().trim()
                if (v.isNotEmpty()) onPick(v)
            }
            .setNegativeButton("Annuller", null)
            .show()
    }

    // ---------- Hurtigknap og widget ----------

    private fun addTile() {
        if (Build.VERSION.SDK_INT < 33) return
        try {
            val sbm = getSystemService(StatusBarManager::class.java) ?: return
            sbm.requestAddTileService(
                ComponentName(this, ButtonTile::class.java),
                "Læs op",
                Icon.createWithResource(this, R.drawable.ic_play),
                mainExecutor
            ) { }
        } catch (_: Exception) {
            Toast.makeText(this, "Det kunne ikke lade sig gøre. Tilføj den selv via blyanten.", Toast.LENGTH_LONG).show()
        }
    }

    private fun addWidget() {
        val mgr = AppWidgetManager.getInstance(this)
        if (mgr != null && mgr.isRequestPinAppWidgetSupported) {
            mgr.requestPinAppWidget(ComponentName(this, ButtonWidget::class.java), null, null)
        } else {
            Toast.makeText(
                this,
                "Hold fingeren på hjemmeskærmen → Widgets → find Læs op.",
                Toast.LENGTH_LONG
            ).show()
        }
    }
}
