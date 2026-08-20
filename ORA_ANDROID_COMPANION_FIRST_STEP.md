# ORA Android Companion: First Step

## What happens next

Because you have Android, the correct next step is not to paste the ORA API token into a phone app. We must first add a secure device-pairing and event-ingestion layer to ORA, then build a small Android companion that receives a device-scoped token after pairing.

The companion will eventually handle push notifications, selected Android notification access, device state, on-demand location, and opt-in background routines. The Vercel website remains the dashboard and approval surface. The backend remains the policy, context, notification, and action layer.

## Current prerequisite state

The current repository has the Phase 7/8 voice and reliability code, but the live Render service was previously observed running an older build. Before phone work, Render should deploy commit `8bf2f71` or a newer backend build containing `/api/ready`, `/api/voice/config`, `/api/voice/command`, and `/api/voice/speak`.

The existing `/api/location/event` and `/api/location/current` endpoints are prototype hooks. They store one location string and timestamp in `kv_store` and use the general ORA API authentication model. They are not yet suitable for a phone companion because they lack device identity, pairing, consent IDs, event IDs, replay protection, expiry, retention, and per-device revocation.

## User setup after the companion is implemented

1. Open ORA on the web and choose **Settings → Devices → Pair Android phone**.
2. ORA displays a short-lived pairing code or QR code. The code expires quickly and can be used only once.
3. Install the signed ORA Companion APK or internal-test build. Do not install an unknown APK from an untrusted source.
4. Enter or scan the pairing code in the companion.
5. Confirm the device name, timezone, and permissions on both the web dashboard and phone.
6. Enable push notifications so ORA can send reminders and approval requests.
7. Enable notification access only for selected apps. Start with Calendar and Gmail metadata; add other apps deliberately.
8. Start with **on-demand or approximate location**, test it, and only then enable a named routine such as Home, Work, or Commute.
9. Confirm the first harmless event, such as a charging or arrival event, appears in ORA’s device timeline.
10. Use the privacy dashboard to verify last sync, active permissions, retention deadlines, pause, revoke, and delete controls.

## Backend work required before installation

Add these authenticated or signature-verified endpoints:

```text
POST /api/devices/pair
GET  /api/devices
POST /api/devices/{id}/revoke
POST /api/ingest/device
GET  /api/location/current
POST /api/location/pause
DELETE /api/location/history
GET  /api/privacy/audit
```

The pairing endpoint should create a short-lived pairing record. After the user confirms the code, issue a device-scoped rotating token. Never ship `ORA_API_TOKEN` inside the APK. The device token must be revocable without changing the main ORA token.

Every event sent by the companion should contain:

```json
{
  "event_id": "device:pixel:notification:abc123",
  "device_id": "device_01",
  "event_type": "notification_posted|location_transition|charging_started|device_checkin",
  "observed_at": "2026-08-20T11:00:00+03:00",
  "payload": {},
  "consent_id": 7,
  "retention_until": "2026-08-21T11:00:00+03:00",
  "signature": "sha256=..."
}
```

The backend must verify the token, signature, event ID, timestamp skew, consent scope, payload size, and replay status before storing anything. It should acknowledge quickly and process summaries or alerts asynchronously.

## Android MVP permissions

Start with the smallest useful permission set:

| Capability | Android permission or service | First-release policy |
|---|---|---|
| Push alerts | Notification permission plus Firebase Cloud Messaging | Enable by default during pairing, with a visible toggle |
| Location answer | Foreground coarse location | Start on demand |
| Routine location | Background location plus a visible foreground service | Add only after the user enables a named routine |
| Other app notifications | `NotificationListenerService` | Use an app allowlist and redact content |
| Charging/device state | Battery and connectivity APIs | Metadata only |
| Microphone | Record audio | Keep push-to-talk in the existing web app first; do not add always-listening |

Android supports approximate or precise location and separates foreground from background access; background location requires explicit permission on Android 10 and later. A background routine should show a persistent foreground-service notification so the user knows it is active.

## What ORA should know

Do not send every raw event directly into the LLM. Project the events into a compact awareness snapshot:

```json
{
  "presence": {
    "zone": "home",
    "state": "stationary",
    "observed_at": "2026-08-20T10:55:00+03:00",
    "expires_at": "2026-08-20T11:10:00+03:00",
    "confidence": 0.87
  },
  "attention": {
    "quiet_hours": false,
    "user_busy": true,
    "last_interaction_at": "2026-08-20T10:59:00+03:00"
  },
  "signals": [
    {
      "type": "important_email|meeting_soon|notification|location_transition",
      "urgency": "reminder",
      "reason": "A selected app reported a delivery update.",
      "source_ids": ["device:pixel:notification:abc123"]
    }
  ]
}
```

If the phone has not checked in before `expires_at`, ORA must say **last seen at** rather than claiming your current location.

## Recommended implementation order

First implement device pairing, signed ingestion, consent records, retention, pause, revoke, and audit. Then add FCM push and a minimal Android companion. Next add Calendar/Gmail metadata, on-demand location, and a notification allowlist. Only after those controls work should we add Home/Work/Commute geofences and background approximate location.

The first real-world test should be harmless: pair the device, enable push, enable on-demand approximate location, and send a device check-in. Do not begin by granting notification access to every app or precise background location.

## Architecture choices

| Choice | Best use | Tradeoff |
|---|---|---|
| Current Vercel + Render | Daily summaries and low-frequency checks | Lowest setup, but not dependable for real-time phone events if the backend sleeps |
| Always-on event gateway | Gmail/Telegram webhooks and timely device events | More reliable, with recurring hosting and monitoring |
| Event gateway plus Android companion | Full phone awareness, push, notifications, and location routines | Most work, but the correct long-term design for Android-wide awareness |

## Immediate decision

The only user decision needed before implementation is whether to begin with an **internal-test Android build** or a **local development build installed by USB/Android Studio**. The internal-test path is easier for normal use; the local path is faster for development but requires a computer and developer setup.

## References

[1]: https://developer.android.com/develop/sensors-and-location/location/permissions "Android location permissions and accuracy"

[2]: https://developer.android.com/reference/android/app/Service.html "Android Service lifecycle and foreground behavior"

[3]: https://github.com/elishaoigara/ORA/blob/main/backend/api.py "ORA current API and location endpoints"

[4]: https://github.com/elishaoigara/ORA/commit/8bf2f7107df487803fa566f8fcb2cdfb993abfaf "ORA Phase 7/8 backend release"
