package dk.philip.laesop

import android.content.Context

/** Gemmer Azure-nøgle, region, stemmer og hastighed på telefonen. */
class Settings(context: Context) {
    private val p = context.getSharedPreferences("laesop", Context.MODE_PRIVATE)

    var key: String
        get() = p.getString("key", "") ?: ""
        set(v) = p.edit().putString("key", v.trim()).apply()

    var region: String
        get() = p.getString("region", "northeurope") ?: "northeurope"
        set(v) = p.edit().putString("region", v.trim().lowercase()).apply()

    /** Hovedstemmen. */
    var voice: String
        get() = p.getString("voice", "da-DK-ChristelNeural") ?: "da-DK-ChristelNeural"
        set(v) = p.edit().putString("voice", v.trim()).apply()

    /** Engelsk stemme (bruges kun sammen med en dansk hovedstemme). */
    var voiceEn: String
        get() = p.getString("voiceEn", "en-GB-SoniaNeural") ?: "en-GB-SoniaNeural"
        set(v) = p.edit().putString("voiceEn", v.trim()).apply()

    /** Find selv ud af, om teksten er dansk eller engelsk. */
    var autoLang: Boolean
        get() = p.getBoolean("autoLang", true)
        set(v) = p.edit().putBoolean("autoLang", v).apply()

    /** Hastighed i procent: -50 (x0,5) til +100 (x2,0). 0 = x1,0. */
    var rate: Int
        get() = p.getInt("rate", 0)
        set(v) = p.edit().putInt("rate", v).apply()

    /** Tekstgenkendelse: 0 = automatisk, 1 = altid, 2 = aldrig. */
    var ocrMode: Int
        get() = p.getInt("ocr", 0)
        set(v) = p.edit().putInt("ocr", v).apply()

    var buttonX: Int
        get() = p.getInt("bx", 40)
        set(v) = p.edit().putInt("bx", v).apply()

    var buttonY: Int
        get() = p.getInt("by", 400)
        set(v) = p.edit().putInt("by", v).apply()

    var buttonVisible: Boolean
        get() = p.getBoolean("visible", true)
        set(v) = p.edit().putBoolean("visible", v).apply()

    val isReady: Boolean get() = key.isNotBlank() && region.isNotBlank()
}
