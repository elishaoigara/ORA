package expo.modules.oranotificationlistener

import android.content.ComponentName
import android.content.Intent
import android.provider.Settings
import expo.modules.kotlin.modules.Module
import expo.modules.kotlin.modules.ModuleDefinition

class OraNotificationListenerModule : Module() {
  override fun definition() = ModuleDefinition {
    Name("OraNotificationListener")

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

