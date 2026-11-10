package dk.philip.laesop

/** Stemmerne man kan vælge mellem. */
object Voices {

    data class Voice(val id: String, val label: String)

    val main = listOf(
        Voice("da-DK-ChristelNeural", "Christel – dansk, kvinde"),
        Voice("da-DK-JeppeNeural", "Jeppe – dansk, mand"),
        Voice("en-US-AvaMultilingualNeural", "Ava – flersproget, kvinde"),
        Voice("en-US-AndrewMultilingualNeural", "Andrew – flersproget, mand"),
        Voice("de-DE-SeraphinaMultilingualNeural", "Seraphina – flersproget, kvinde"),
        Voice("de-DE-FlorianMultilingualNeural", "Florian – flersproget, mand"),
        Voice("en-US-EmmaMultilingualNeural", "Emma – flersproget, kvinde"),
        Voice("en-US-BrianMultilingualNeural", "Brian – flersproget, mand")
    )

    val english = listOf(
        Voice("en-GB-SoniaNeural", "Sonia – britisk, kvinde"),
        Voice("en-GB-RyanNeural", "Ryan – britisk, mand"),
        Voice("en-US-AvaMultilingualNeural", "Ava – amerikansk, kvinde"),
        Voice("en-US-AndrewMultilingualNeural", "Andrew – amerikansk, mand")
    )

    fun label(id: String, list: List<Voice>): String =
        list.firstOrNull { it.id == id }?.label ?: id

    fun isMultilingual(id: String): Boolean = id.contains("Multilingual", ignoreCase = true)

    /** fx "da-DK" ud fra "da-DK-ChristelNeural". */
    fun locale(id: String): String {
        val parts = id.split("-")
        return if (parts.size >= 2) parts[0] + "-" + parts[1] else "da-DK"
    }
}
