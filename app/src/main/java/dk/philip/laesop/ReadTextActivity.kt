package dk.philip.laesop

import android.app.Activity
import android.content.Intent
import android.os.Bundle
import android.widget.Toast

/**
 * Usynlig skærm, der læser tekst op:
 * - når man markerer tekst og vælger "Læs op" i menuen
 * - når man deler tekst til "Læs op"
 */
class ReadTextActivity : Activity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val app = applicationContext

        val text = when (intent?.action) {
            Intent.ACTION_PROCESS_TEXT ->
                intent.getCharSequenceExtra(Intent.EXTRA_PROCESS_TEXT)?.toString()
            Intent.ACTION_SEND ->
                intent.getStringExtra(Intent.EXTRA_TEXT)
            else -> null
        }
        val t: String = text?.trim() ?: ""

        when {
            t.isEmpty() ->
                Toast.makeText(app, "Der var ingen tekst at læse op.", Toast.LENGTH_SHORT).show()
            Regex("^https?://\\S+$").matches(t) ->
                Toast.makeText(app, "Der blev kun delt et link. Markér teksten i stedet, og vælg Læs op.", Toast.LENGTH_LONG).show()
            else ->
                Speaker.get(app).speak(t) { msg ->
                    Toast.makeText(app, msg, Toast.LENGTH_LONG).show()
                }
        }
        finish()
        overridePendingTransition(0, 0)
    }
}
