package dk.philip.laesop

import android.graphics.Bitmap
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.text.Text
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.latin.TextRecognizerOptions

/** Tekstgenkendelse: finder teksten i et billede af skærmen. Kører på telefonen. */
object Ocr {

    private val recognizer by lazy { TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS) }
    private val onlyNumbers = Regex("^[\\d.,:/%\\s]+$")

    /** skipTop = alt over denne højde (statuslinjen) springes over. Svaret kommer på hovedtråden. */
    fun read(bmp: Bitmap, skipTop: Int, done: (String) -> Unit) {
        try {
            val img = InputImage.fromBitmap(bmp, 0)
            recognizer.process(img)
                .addOnSuccessListener { result -> done(format(result, skipTop)) }
                .addOnFailureListener { done("") }
        } catch (e: Exception) {
            done("")
        }
    }

    private fun format(r: Text, skipTop: Int): String {
        val sb = StringBuilder()
        for (b in r.textBlocks) {
            val box = b.boundingBox
            if (box != null && box.bottom <= skipTop) continue

            // Linjerne i en blok samles til én tekst. Orddeling med "-" bliver sat sammen igen.
            val joined = StringBuilder()
            for (line in b.lines) {
                val l = line.text.trim()
                if (l.isEmpty()) continue
                if (joined.isEmpty()) {
                    joined.append(l)
                } else if (joined.endsWith("-") && l[0].isLowerCase()) {
                    joined.setLength(joined.length - 1)
                    joined.append(l)
                } else {
                    joined.append(' ').append(l)
                }
            }
            val t = joined.toString()
            if (t.isEmpty() || onlyNumbers.matches(t)) continue
            if (sb.isNotEmpty()) sb.append('\n')
            sb.append(t)
        }
        return sb.toString()
    }
}
