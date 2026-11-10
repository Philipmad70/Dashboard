package dk.philip.laesop

import android.content.ComponentName
import android.content.Context
import android.service.quicksettings.TileService

/** Fælles styring af knappen – bruges af appen, hurtigknappen, widget og genveje. */
object Controls {

    /** Er tilgængelighedstjenesten slået til? */
    fun isOn(): Boolean = ReaderService.instance != null

    /** Vises knappen lige nu? */
    fun isShown(): Boolean = ReaderService.instance?.isButtonShown == true

    fun setVisible(context: Context, visible: Boolean) {
        Settings(context).buttonVisible = visible
        ReaderService.instance?.applyVisibility()
        refresh(context)
    }

    /** Returnerer false, hvis tjenesten ikke er slået til. */
    fun toggle(context: Context): Boolean {
        if (!isOn()) return false
        setVisible(context, !isShown())
        return true
    }

    /** Opdaterer hurtigknap og widget. */
    fun refresh(context: Context) {
        try {
            TileService.requestListeningState(context, ComponentName(context, ButtonTile::class.java))
        } catch (_: Exception) {}
        try {
            ButtonWidget.updateAll(context)
        } catch (_: Exception) {}
    }
}
