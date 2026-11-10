package dk.philip.laesop

import android.app.Activity
import android.content.Intent
import android.os.Bundle
import android.provider.Settings as AndroidSettings
import android.widget.Toast

/** Usynlig skærm, der viser/skjuler knappen. Bruges af genveje og widget. */
class ToggleActivity : Activity() {

    companion object {
        const val ACTION_SHOW = "dk.philip.laesop.SHOW"
        const val ACTION_HIDE = "dk.philip.laesop.HIDE"
        const val ACTION_TOGGLE = "dk.philip.laesop.TOGGLE"
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val app = applicationContext

        if (!Controls.isOn()) {
            Toast.makeText(app, "Slå \"Læs op – knap\" til under Tilgængelighed.", Toast.LENGTH_LONG).show()
            try {
                startActivity(Intent(AndroidSettings.ACTION_ACCESSIBILITY_SETTINGS))
            } catch (_: Exception) {}
            finish()
            return
        }

        when (intent?.action) {
            ACTION_SHOW -> Controls.setVisible(app, true)
            ACTION_HIDE -> Controls.setVisible(app, false)
            else -> Controls.toggle(app)
        }
        finish()
        overridePendingTransition(0, 0)
    }
}
