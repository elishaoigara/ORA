# ORA Phone Awareness Rollout

## Executive answer

To make ORA aware of your phone, use two components:

1. **The ORA cloud backend** receives normalized, signed events and applies context, notification, and approval policies.
2. **A mobile companion app** runs on the phone and, with explicit OS permissions, sends selected notification events, device state, push-token updates, and location transitions.

The Vercel website alone cannot read other apps’ notifications or maintain background GPS collection when it is closed. Gmail and Telegram can connect directly through their official APIs; phone-wide notification access and dependable background location require a mobile companion.

The goal should be **continuous readiness with bounded collection**, not an unrestricted raw stream of every message and coordinate. Every source needs a visible consent scope, purpose, freshness timestamp, retention period, pause switch, and revoke/delete action.

## What ORA can read

| Source | Recommended connection | What ORA should ingest | Important limitation |
|---|---|---|---|
| Gmail | Existing Google OAuth plus Gmail API push/reconciliation | Message/thread IDs, sender, subject, labels, timestamps, selected body text when needed | Gmail push needs a stable backend, Pub/Sub, watch renewal, and history reconciliation |
| Google Calendar | Existing OAuth plus watch/incremental sync | Events, participants, times, locations, preparation needs | Shared changes and invitations remain approval-gated |
| Telegram | Bot webhook or current polling during transition | Private messages sent to the ORA bot, commands, callback approvals | It cannot read unrelated private chats outside the bot’s authorized access |
| Other Android notifications | Android companion with notification access and app allowlist | App, title, timestamp, category, redacted preview | Requires user-enabled notification access; do not capture every app by default |
| SMS/calls/WhatsApp | Dedicated provider or mobile OS integration where legally and technically supported | Only explicitly enabled event types | Do not scrape or bypass app security; start with metadata or user-forwarded messages |
| Location | Android companion, permission tiers, geofences, adaptive sampling | Named zone, coarse geohash, movement/arrival/departure events | Background precise access needs explicit OS permission and visible controls |
| Device state | Mobile companion | Charging, battery band, connectivity, last check-in | Use for routines, not surveillance |

## Recommended architecture

```text
Gmail Pub/Sub ----\
Telegram webhook --\
Android companion ---> HTTPS Event Gateway ---> Event Store ---> Context Projector
                                                         |              |
                                                         v              v
                                                   Dedupe/audit   Ask/Plan/Act/Watch
                                                                        |
                                                        Chat / Telegram / Push / Voice
```

The event gateway must accept only validated JSON events. It should check a signature, device or provider identity, timestamp skew, event ID, consent scope, payload size, and replay status. It should acknowledge webhooks quickly and process expensive summarization asynchronously.

The event store should contain normalized metadata and short-lived content references. The LLM should receive a compact awareness projection, not every raw message, notification, or location sample.

## Phone companion requirements

The companion should provide a first-run privacy setup with separate switches for notifications, location, device state, and message sources. It should show what is enabled, when it last sent data, how long data is retained, and a global **Pause ORA awareness** button.

The companion should implement:

| Component | Responsibility |
|---|---|
| Pairing | Display a short code in the app and require confirmation in the ORA web dashboard |
| Device credential | Use a rotating device-scoped token; support immediate revocation |
| Event queue | Buffer encrypted events offline and retry later with exponential backoff |
| Notification listener | Capture only user-selected apps and redact sensitive content |
| Location worker | Use on-demand, routine, or geofence-based collection rather than constant GPS uploads |
| Push receiver | Receive ORA alerts and open the relevant approval or explanation screen |
| Privacy dashboard | Show permissions, last sync, retention, pause, revoke, export, and delete controls |

For full system-level access, **Android is the practical first target**. Android provides background and foreground location permissions and a notification-listener service model. On iPhone, background location and notification access are more restricted; a web app cannot provide the same device-wide awareness.

## Data flow for an incoming message or notification

```text
1. Provider or phone produces an event.
2. Gateway verifies provider/device signature and consent.
3. Event ID is deduplicated.
4. Metadata is stored with retention deadline.
5. Normalizer classifies it as email, message, notification, commitment, or device event.
6. Policy engine checks urgency, quiet hours, source preference, and duplicate state.
7. Context projector updates only the useful summary.
8. ORA decides: suppress, group into digest, notify, ask, or propose an action.
9. Delivery receipt is stored.
10. User can acknowledge, snooze, edit, revoke, or delete.
```

## Gmail implementation

ORA already has Google OAuth. Add a Pub/Sub topic and a verified HTTPS push subscription. Register Gmail `watch` on the selected mailbox labels, save the returned history ID and expiration, and renew the watch daily. When a notification arrives, use Gmail `history.list` from the last cursor to fetch only deltas. Gmail documentation states that watches must be renewed at least every seven days and that notifications can be delayed or dropped, so reconciliation is mandatory [1].

Store message and thread IDs, sender, labels, classification, timestamps, and extracted commitments. Fetch and retain body text only for a user-requested summary, draft, search, or commitment workflow. Never store all message bodies permanently by default.

## Telegram implementation

Move ORA from long polling to an HTTPS webhook when the backend has a stable endpoint. Configure Telegram’s secret token, verify the `X-Telegram-Bot-Api-Secret-Token` header, restrict allowed update types, and persist update IDs. Telegram retries failed webhook deliveries, so the event ID must be idempotent [2].

Use Telegram for timely reminders, concise summaries, and approval links. Do not put full email bodies, precise location, or sensitive personal data in notifications. Use the Vercel app for complex approval details.

## Android notification implementation

Create a notification access screen that lists selected apps. Default to an allowlist such as Calendar, Gmail, delivery, banking, and messaging only if the user explicitly chooses them. A safer default is Calendar and Gmail metadata first.

Normalize a notification like this:

```json
{
  "event_id": "device:pixel:notification:abc123",
  "source": "android_notification",
  "type": "notification_posted",
  "observed_at": "2026-08-20T11:00:00+03:00",
  "device_id": "device_01",
  "app_id": "com.example.app",
  "title": "Delivery update",
  "redacted_text": "Your delivery is arriving today",
  "sensitivity": "normal",
  "consent_scope": "notifications:allowlist",
  "retention_until": "2026-08-21T11:00:00+03:00"
}
```

Redact OTPs, passwords, API keys, private keys, bank verification codes, and any notification category the user has not approved. Store previews for a short period only.

## Location implementation

Do not stream raw GPS continuously. Use tiers:

| Tier | Behavior |
|---|---|
| Off | No location collected |
| On demand | One location after a visible user action |
| Routine | Coarse updates during selected schedules, such as commute or work hours |
| Background approximate | Geofence and meaningful-movement events |
| Background precise | Temporary navigation or explicitly enabled routine |

Android supports approximate and precise location and distinguishes foreground from background access; background access requires explicit permission on Android 10 and later [3]. If a background routine is active, use a visible foreground service notification so the user knows it is running [4].

Use named zones such as `home`, `work`, `Juja`, or `Nairobi CBD` rather than sending raw coordinates to ORA. Upload an event when entering/leaving a zone, moving beyond a configured distance, starting a routine, or requesting a location-based answer. Keep raw coordinates on-device or delete them after deriving a coarse zone.

Every location record must contain:

```json
{
  "device_id": "device_01",
  "zone": "home",
  "observed_at": "2026-08-20T11:00:00+03:00",
  "expires_at": "2026-08-20T11:20:00+03:00",
  "accuracy": "coarse",
  "purpose": "commute_reminder",
  "consent_id": 7,
  "confidence": 0.87
}
```

If the device has not checked in before `expires_at`, ORA must say **last seen at** rather than claiming your current location.

## ORA awareness API

Add these endpoints to the backend:

| Endpoint | Function |
|---|---|
| `POST /api/devices/pair` | Pair a phone through a visible confirmation code |
| `GET /api/devices` | List devices, scopes, last seen, and consent |
| `POST /api/devices/{id}/revoke` | Revoke access immediately |
| `POST /api/ingest/device` | Receive signed notification, location, and device events |
| `POST /api/ingest/gmail` | Receive verified Pub/Sub events |
| `POST /api/ingest/telegram` | Receive verified Telegram updates |
| `GET /api/location/current` | Return only non-expired consented presence |
| `POST /api/location/pause` | Pause every location routine |
| `DELETE /api/location/history` | Delete by time range or source |
| `GET /api/privacy/audit` | Show permissions, access, retention, and delivery history |

ORA currently has `/api/location/event` and `/api/location/current`, but the existing implementation stores a single location string and timestamp in `kv_store`. It is a useful prototype hook, not yet a complete location-awareness system. It should be upgraded to consent records, event IDs, expiry, retention, device identity, and audit history before enabling continuous routines.

## Alert policy

Use five urgency levels:

| Level | Delivery |
|---|---|
| Silent | Store in context only |
| Digest | Include in next morning/evening or user-requested digest |
| Reminder | Telegram or web notification during permitted hours |
| Important | Immediate Telegram/push with explanation |
| Urgent | Interrupt only for a user-defined category and only when explicitly enabled |

Every alert should say:

```text
WHAT: The event.
WHY: Why it matters to you.
NEXT: One recommended action.
SOURCE: Where it came from and when it was observed.
CONTROL: Acknowledge, snooze, mute this category, or open details.
```

## Build sequence

1. **Secure base:** implement device pairing, event IDs, signed ingestion, consent records, privacy audit, retention jobs, and global pause/revoke.
2. **Communication foundation:** implement the shared response envelope, notification policy, quiet hours, semantic deduplication, and notification history.
3. **Email and Telegram:** add Gmail Pub/Sub/reconciliation and Telegram webhook/replay handling.
4. **Android companion MVP:** implement push notifications, device pairing, Calendar/Gmail metadata, on-demand location, and an allowlisted notification listener.
5. **Routines:** add home/work/commute geofences, charging routines, and background approximate location only after privacy controls are tested.
6. **Intelligence:** add commitment extraction, daily priority, meeting preparation, delivery/finance alerts, and follow-up scheduling.
7. **Hardening:** test offline buffering, revoked consent, stale location, duplicate webhook delivery, provider outage, sensitive-notification redaction, and cross-channel deduplication.

## Hosting choices

| Choice | Best for | Limitation |
|---|---|---|
| Current Vercel + Render | Daily summaries and low-frequency sync | Not dependable for real-time webhooks if the backend sleeps |
| Always-on event gateway | Gmail Pub/Sub, Telegram webhooks, timely device events | Requires persistent hosting and operational monitoring |
| Event gateway plus Android companion | Device notifications, background location, push, offline buffering | Highest implementation effort, but required for full phone awareness |

Do not use keep-alive traffic to defeat free-tier suspension. If real-time awareness becomes essential, use an always-on service for the event gateway and keep the Vercel UI separate.

## References

[1]: https://developers.google.com/workspace/gmail/api/guides/push "Gmail API push notifications"

[2]: https://core.telegram.org/bots/api "Telegram Bot API webhooks"

[3]: https://developer.android.com/develop/sensors-and-location/location/permissions "Android location permissions"

[4]: https://developer.android.com/reference/android/app/Service.html "Android Service lifecycle and foreground behavior"
