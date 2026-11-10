package dk.philip.laesop

import android.annotation.SuppressLint
import android.app.PendingIntent
import android.content.Intent
import android.os.Build
import android.provider.Settings as AndroidSettings
import android.service.quicksettings.Tile
import android.service.quicksettings.TileService
import android.widget.Toast

/** Knap i hurtigindstillinger: viser eller skjuler afspil-knappen. */
class ButtonTile : TileService() {

    override fun onStartListening() {
        super.onStartListening()
        update()
    }

    override fun onClick() {
        super.onClick()
        if (!Controls.isOn()) {
            Toast.makeText(this, "Slå \"Læs op – knap\" til under Tilgængelighed.", Toast.LENGTH_LONG).show()
            openAccessibility()
            return
        }
        Controls.toggle(this)
        update()
    }

    private fun update() {
        val tile = qsTile ?: return
        val on = Controls.isOn()
        val shown = Controls.isShown()
        tile.state = if (on && shown) Tile.STATE_ACTIVE else Tile.STATE_INACTIVE
        tile.label = "Læs op"
        if (Build.VERSION.SDK_INT >= 29) {
            tile.subtitle = when {
                !on -> "Slået fra"
                shown -> "Vises"
                else -> "Skjult"
            }
        }
        tile.updateTile()
    }

    @SuppressLint("StartActivityAndCollapseDeprecated")
    private fun openAccessibility() {
        val intent = Intent(AndroidSettings.ACTION_ACCESSIBILITY_SETTINGS)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        if (Build.VERSION.SDK_INT >= 34) {
            val pi = PendingIntent.getActivity(this, 0, intent, PendingIntent.FLAG_IMMUTABLE)
            startActivityAndCollapse(pi)
        } else {
            @Suppress("DEPRECATION")
            startActivityAndCollapse(intent)
        }
    }
}
