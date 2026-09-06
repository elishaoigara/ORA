package expo.modules.oranotificationlistener

import android.app.DatePickerDialog
import android.app.TimePickerDialog
import java.util.Calendar
import expo.modules.kotlin.Promise
import android.content.ComponentName
import android.content.Intent
import android.provider.Settings
import expo.modules.kotlin.modules.Module
import expo.modules.kotlin.modules.ModuleDefinition

class OraNotificationListenerModule : Module() {
  override fun definition() = ModuleDefinition {
    Name("OraNotificationListener")
    AsyncFunction("pickDateTime") { initial: Double, promise: Promise ->
      val activity = appContext.currentActivity
      if (activity == null) { promise.resolve(null) } else activity.runOnUiThread {
        val date = Calendar.getInstance().apply { timeInMillis = initial.toLong() }
        val picker = DatePickerDialog(activity, { _, year, month, day ->
          date.set(year, month, day)
          val time = TimePickerDialog(activity, { _, hour, minute ->
            date.set(Calendar.HOUR_OF_DAY, hour); date.set(Calendar.MINUTE, minute)
            date.set(Calendar.SECOND, 0); date.set(Calendar.MILLISECOND, 0)
            promise.resolve(date.timeInMillis.toDouble())
          }, date.get(Calendar.HOUR_OF_DAY), date.get(Calendar.MINUTE), android.text.format.DateFormat.is24HourFormat(activity))
          time.setOnCancelListener { promise.resolve(null) }; time.show()
        }, date.get(Calendar.YEAR), date.get(Calendar.MONTH), date.get(Calendar.DAY_OF_MONTH))
        picker.setOnCancelListener { promise.resolve(null) }; picker.show()
      }
    }


    Function("canScheduleExactAlarms") {
      val context = appContext.reactContext
      if (context == null) false else if (android.os.Build.VERSION.SDK_INT >= 31) {
        (context.getSystemService(android.content.Context.ALARM_SERVICE) as android.app.AlarmManager).canScheduleExactAlarms()
      } else true
    }
    Function("openExactAlarmSettings") {
      val context = appContext.reactContext
      if (context != null && android.os.Build.VERSION.SDK_INT >= 31) {
        context.startActivity(Intent(Settings.ACTION_REQUEST_SCHEDULE_EXACT_ALARM, android.net.Uri.parse("package:" + context.packageName)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
      }
    }
    Function("getListenerStatus") {
      val context = appContext.reactContext
      if (context == null) {
        return@Function mapOf("available" to false, "accessGranted" to false, "configured" to false, "queuedEventCount" to 0)
      }
      val component = ComponentName(context, OraNotificationListenerService::class.java)
      mapOf(
        "available" to true,
        "accessGranted" to OraNotificationListenerService.isAccessGranted(context, component),
        "configured" to OraNotificationListenerStore.preferences(context).getBoolean(OraNotificationListenerStore.KEY_ENABLED, false),
        "queuedEventCount" to OraNotificationListenerStore.readEvents(context).length(),
      )
    }

    Function("openNotificationListenerSettings") {
      val context = appContext.reactContext ?: return@Function false
      context.startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
      true
    }

    Function("configure") { enabled: Boolean, sources: List<Map<String, Any?>> ->
      val context = appContext.reactContext ?: return@Function
      OraNotificationListenerStore.configure(context, enabled, sources)
    }

    Function("getPendingEvents") {
      val context = appContext.reactContext ?: return@Function emptyList<Map<String, Any>>()
      OraNotificationListenerStore.eventsAsMaps(context)
    }

    Function("acknowledgeEvents") { ids: List<String> ->
      val context = appContext.reactContext ?: return@Function
      OraNotificationListenerStore.acknowledgeEvents(context, ids.toSet())
    }

    Function("clearPendingEvents") {
      val context = appContext.reactContext ?: return@Function
      OraNotificationListenerStore.clearEvents(context)
    }
  }
}

