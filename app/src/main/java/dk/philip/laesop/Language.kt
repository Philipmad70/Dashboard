package dk.philip.laesop

/** Gætter om en linje er dansk eller engelsk ud fra almindelige småord. */
object Language {
    enum class Lang { DA, EN }

    private val da = setOf(
        "og", "det", "er", "jeg", "ikke", "en", "et", "til", "på", "med", "har",
        "som", "af", "de", "den", "vi", "du", "kan", "skal", "var", "men", "om",
        "så", "fra", "der", "hvor", "hvad", "også", "eller", "efter", "når", "nu",
        "ved", "mig", "dig", "han", "hun", "blev", "være", "bliver", "meget",
        "alle", "her", "hvis", "deres", "sin", "sit", "sig", "jo", "lige", "noget",
        "kun", "mere", "godt", "får", "fik", "være", "dette", "disse", "hvordan"
    )
    private val en = setOf(
        "the", "and", "is", "of", "to", "you", "that", "it", "with", "this",
        "are", "was", "on", "be", "have", "not", "from", "they", "we", "what",
        "which", "will", "can't", "your", "an", "by", "or", "but", "all", "has",
        "more", "about", "there", "their", "would", "been", "if", "when", "who",
        "do", "does", "how", "my", "our", "just", "get", "like", "should", "could",
        "these", "those", "into", "than", "then", "were", "it's", "i'm", "don't"
    )

    /** Returnerer null, hvis linjen er for kort eller uklar. */
    fun detect(line: String): Lang? {
        val lower = line.lowercase()
        val words = lower.split(Regex("[^\\p{L}']+")).filter { it.isNotEmpty() }
        var daScore = words.count { it in da }
        val enScore = words.count { it in en }
        if (lower.any { it == 'æ' || it == 'ø' || it == 'å' }) daScore += 2
        if (daScore == 0 && enScore == 0) return null
        return when {
            daScore > enScore -> Lang.DA
            enScore > daScore -> Lang.EN
            else -> null
        }
    }
}
