package dk.philip.laesop

import android.app.Activity
import android.content.Intent
import android.content.pm.ShortcutInfo
import android.content.pm.ShortcutManager
import android.graphics.drawable.Icon
import android.os.Bundle

/**
 * Vises i listen "Genveje" i sidebars og i Nova Launchers gestures.
 * Giver en genvej, der viser/skjuler den svævende knap.
 */
class ShortcutCreatorActivity : Activity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val target = Intent(this, ToggleActivity::class.java)
            .setAction(ToggleActivity.ACTION_TOGGLE)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        val label = getString(R.string.sc_toggle)

        // Ny måde (Android 8+)
        var result: Intent? = null
        try {
            val sm = getSystemService(ShortcutManager::class.java)
            if (sm != null) {
                val info = ShortcutInfo.Builder(this, "toggle_pinned")
                    .setShortLabel(label)
                    .setIcon(Icon.createWithResource(this, R.drawable.ic_sc_show))
                    .setIntent(target)
                    .build()
                result = sm.createShortcutResultIntent(info)
            }
        } catch (_: Exception) {}

        // Gammel måde – mange sidebars og Nova bruger stadig den
        val data = result ?: Intent()
        addLegacyExtras(data, target, label)

        setResult(RESULT_OK, data)
        finish()
    }

    @Suppress("DEPRECATION")
    private fun addLegacyExtras(data: Intent, target: Intent, label: String) {
        data.putExtra(Intent.EXTRA_SHORTCUT_INTENT, target)
        data.putExtra(Intent.EXTRA_SHORTCUT_NAME, label)
        data.putExtra(
            Intent.EXTRA_SHORTCUT_ICON_RESOURCE,
            Intent.ShortcutIconResource.fromContext(this, R.drawable.ic_sc_show)
        )
    }
}
