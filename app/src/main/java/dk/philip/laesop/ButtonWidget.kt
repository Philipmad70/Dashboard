package dk.philip.laesop

import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.widget.RemoteViews

/** Lille widget på hjemmeskærmen: tryk = vis/skjul knappen. */
class ButtonWidget : AppWidgetProvider() {

    override fun onUpdate(context: Context, appWidgetManager: AppWidgetManager, appWidgetIds: IntArray) {
        updateAll(context)
    }

    companion object {
        fun updateAll(context: Context) {
            val mgr = AppWidgetManager.getInstance(context) ?: return
            val ids = mgr.getAppWidgetIds(ComponentName(context, ButtonWidget::class.java))
            if (ids == null || ids.isEmpty()) return

            val on = Controls.isOn()
            val shown = Controls.isShown()

            val views = RemoteViews(context.packageName, R.layout.widget_button)
            views.setTextViewText(
                R.id.widget_label,
                when {
                    !on -> "Slå til"
                    shown -> "Skjul"
                    else -> "Vis"
                }
            )
            views.setInt(R.id.widget_icon, "setImageAlpha", if (shown) 255 else 110)

            val intent = Intent(context, ToggleActivity::class.java)
                .setAction(ToggleActivity.ACTION_TOGGLE)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            val pi = PendingIntent.getActivity(
                context, 1, intent,
                PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
            )
            views.setOnClickPendingIntent(R.id.widget_root, pi)
            mgr.updateAppWidget(ids, views)
        }
    }
}
