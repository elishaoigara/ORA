package expo.modules.oranotificationlistener

import android.content.ComponentName
import android.content.Context
import android.os.Build
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import android.provider.Settings
import android.app.Notification
import org.json.JSONArray
import org.json.JSONObject
import java.time.Instant
import java.util.UUID

/**
 * An allowlist-only notification listener. It never invokes notification action
 * buttons, replies, dismisses, snoozes, or stores non-allowlisted content.
 */
class OraNotificationListenerService : NotificationListenerService() {
  override fun onNotificationPosted(sbn: StatusBarNotification) {
    val context = applicationContext
    if (!OraNotificationListenerStore.isEnabled(context) || sbn.isOngoing) return
    val notification = sbn.notification ?: return
    if ((notification.flags and Notification.FLAG_ONGOING_EVENT) != 0) return
    val source = OraNotificationListenerStore.sourceFor(context, sbn.packageName) ?: return
    if (!source.optBoolean("enabled", false)) return

    val mode = source.optString("contentMode", "metadata")
    val label = source.optString("appLabel", sbn.packageName)
    val extras = notification.extras
    var title = extras?.getCharSequence(Notification.EXTRA_TITLE)?.toString().orEmpty()
    var body = extras?.getCharSequence(Notification.EXTRA_TEXT)?.toString().orEmpty()
    if (mode == "metadata") {
      title = ""
      body = ""
    } else if (mode == "redacted") {
      title = OraNotificationListenerStore.redact(title)
      body = OraNotificationListenerStore.redact(body)
    }
    val event = JSONObject().apply {
      put("id", UUID.randomUUID().toString())
      put("packageName", sbn.packageName)
      put("appLabel", label)
      put("title", title.take(200))
      put("body", body.take(1000))
      put("contentMode", mode)
      put("occurredAt", if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) Instant.now().toString() else System.currentTimeMillis().toString())
    }
    OraNotificationListenerStore.enqueue(context, event)
  }

  companion object {
    fun isAccessGranted(context: Context, component: ComponentName): Boolean {
      val enabled = Settings.Secure.getString(context.contentResolver, "enabled_notification_listeners") ?: return false
      return enabled.split(":").any { component.flattenToString() == it }
    }
  }
}

object OraNotificationListenerStore {
  const val KEY_ENABLED = "enabled"
  private const val STORE = "ora_notification_listener"
  private const val KEY_SOURCES = "sources"
  private const val KEY_EVENTS = "events"
  private const val MAX_EVENTS = 30

  fun preferences(context: Context) = context.getSharedPreferences(STORE, Context.MODE_PRIVATE)

  fun isEnabled(context: Context) = preferences(context).getBoolean(KEY_ENABLED, false)

  fun configure(context: Context, enabled: Boolean, sources: List<Map<String, Any?>>) {
    val array = JSONArray()
    sources.take(12).forEach { source ->
      val packageName = source["packageName"]?.toString()?.trim().orEmpty()
      val appLabel = source["appLabel"]?.toString()?.trim().orEmpty()
      val contentMode = source["contentMode"]?.toString()?.trim().orEmpty()
      if (packageName.matches(Regex("^[A-Za-z][A-Za-z0-9_]*(\\.[A-Za-z][A-Za-z0-9_]*)+$")) && appLabel.isNotEmpty() && contentMode in setOf("metadata", "redacted", "full")) {
        array.put(JSONObject().apply {
          put("packageName", packageName)
          put("appLabel", appLabel.take(80))
          put("contentMode", contentMode)
          put("enabled", source["enabled"] as? Boolean ?: true)
        })
      }
    }
    preferences(context).edit().putBoolean(KEY_ENABLED, enabled).putString(KEY_SOURCES, array.toString()).apply()
    if (!enabled) clearEvents(context)
  }

  fun sourceFor(context: Context, packageName: String): JSONObject? {
    val sources = JSONArray(preferences(context).getString(KEY_SOURCES, "[]"))
    for (index in 0 until sources.length()) {
      val source = sources.optJSONObject(index)
      if (source?.optString("packageName") == packageName) return source
    }
    return null
  }

  fun readEvents(context: Context): JSONArray = JSONArray(preferences(context).getString(KEY_EVENTS, "[]"))

  fun eventsAsMaps(context: Context): List<Map<String, Any>> {
    val events = readEvents(context)
    return (0 until events.length()).mapNotNull { index ->
      events.optJSONObject(index)?.let { event ->
        mapOf(
          "id" to event.optString("id"),
          "packageName" to event.optString("packageName"),
          "appLabel" to event.optString("appLabel"),
          "title" to event.optString("title"),
          "body" to event.optString("body"),
          "contentMode" to event.optString("contentMode"),
          "occurredAt" to event.optString("occurredAt"),
        )
      }
    }
  }

  fun enqueue(context: Context, event: JSONObject) {
    val events = readEvents(context)
    events.put(event)
    while (events.length() > MAX_EVENTS) events.remove(0)
    preferences(context).edit().putString(KEY_EVENTS, events.toString()).apply()
  }

  fun clearEvents(context: Context) {
    preferences(context).edit().remove(KEY_EVENTS).apply()
  }

  fun redact(value: String): String {
    return value
      .replace(Regex("https?://\\S+"), "[link]")
      .replace(Regex("\\b\\d{4,10}\\b"), "[code]")
      .replace(Regex("\\b[\\w.+-]+@[\\w-]+(?:\\.[\\w-]+)+\\b"), "[email]")
  }
}
