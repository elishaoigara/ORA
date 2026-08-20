# ORA Communication and Personal-Awareness Architecture

**Status:** Architecture blueprint for Phase 9 and subsequent implementation  
**Timezone:** Africa/Nairobi  
**Primary channels:** Vercel web app, Telegram, push-to-talk voice, optional Android companion

## 1. Core principle

ORA should become **continuously ready, not continuously invasive**. It can receive permitted events and maintain a current, useful projection of your situation, but it should not collect every message, notification, GPS coordinate, microphone signal, or screen state indefinitely. Every source needs an explicit purpose, consent scope, freshness value, retention deadline, pause switch, revocation path, and audit record.

The target loop is:

```text
Observe -> Normalize -> Project context -> Prioritize -> Communicate
                                          |
                                          v
                              Propose -> Approve -> Execute -> Verify -> Follow up
```

ORA’s current `personal_context.py` already provides the canonical read-only context containing profile, preferences, memory, confirmed learned facts, alerts, tasks, overdue work, goals, Google data, weather, spending, predictions, summaries, and source flags. Phase 9 should extend that snapshot with `DailyPlan`, `Commitments`, `Presence`, `Attention`, `NotificationPolicy`, and `Freshness`, rather than creating parallel context systems.

## 2. Ask, Plan, Act, Watch architecture

| Mode | Purpose | Default behavior | Side effects |
|---|---|---|---|
| **Ask** | Answer a question or retrieve context | Give a direct answer with sources and freshness when useful | None by default |
| **Plan** | Turn goals, commitments, and context into a proposed plan | Show priorities, time assumptions, dependencies, and one clarification if needed | Private draft tasks only if enabled; no shared changes |
| **Act** | Perform a typed operation | Preview exact parameters, enforce approval, execute once, verify, show receipt | Controlled by risk policy and action ledger |
| **Watch** | Monitor meaningful changes and follow up | Deduplicate, apply quiet hours, group related signals, explain why it matters | Notification delivery only; no hidden external writes |

### Shared response contract

Every channel should receive the same semantic envelope and render it differently:

```json
{
  "schema_version": "ora.response.v1",
  "response_id": "resp_01J...",
  "session_id": "session_...",
  "mode": "ask|plan|act|watch",
  "status": "answered|needs_clarification|action_proposed|executed|verified|failed|suppressed",
  "answer": "The direct answer.",
  "spoken_summary": "The short answer and next step for voice.",
  "intent": "calendar_read|task_create|email_send|...",
  "confidence": 0.0,
  "sources": [
    {
      "source_type": "calendar|gmail|task|memory|location|user_statement",
      "source_id": "provider-or-local-id",
      "observed_at": "2026-08-20T10:00:00+03:00",
      "fresh_until": "2026-08-20T10:10:00+03:00",
      "confidence": 0.95
    }
  ],
  "why": "Why the answer or notification matters.",
  "next_step": {
    "label": "Review this proposal",
    "tool_name": "gmail.reply",
    "action_id": 42,
    "due_at": null
  },
  "approval": {
    "required": true,
    "reason": "This sends an external email.",
    "expires_at": "2026-08-21T10:00:00+03:00",
    "parameters": {"to": "recipient@example.com", "subject": "Exact subject"}
  },
  "follow_up": {"commitment_id": null, "scheduled_for": null, "channel": null},
  "error": null,
  "trace": {"request_id": "...", "context_generated_at": "...", "tool_idempotency_key": null}
}
```

The web renderer should show the full action preview, source freshness, and approval controls. Telegram should show a short summary and link to the web approval queue for complex actions. Voice should speak only `spoken_summary`; exact recipient, date, amount, and resource parameters should remain visible on screen.

## 3. Exact mode state machines

### Ask

```text
received -> context_loaded -> answered
                         -> needs_clarification
                         -> failed
```

Ask must not create durable memory or actions unless the user explicitly requests a follow-up, task, reminder, or change.

### Plan

```text
received -> context_loaded -> plan_proposed
plan_proposed -> accepted -> action_proposed|executed
              -> edited -> plan_proposed
              -> rejected|expired
```

Plan should never silently move a shared calendar meeting, send a message, delete data, or spend money.

### Act

```text
received -> contract_validated -> action_proposed
action_proposed -> approved -> executing -> verified
                             -> failed -> retryable|terminal
              -> rejected|expired|cancelled
```

Use ORA’s existing `ToolSpec`, typed gateway, action ledger, idempotency key, approval policy, retry limit, expiry, and connector receipt. External communication, shared-calendar changes, deletion, irreversible operations, and financial actions remain approval-gated.

### Watch

```text
source_event -> normalized -> policy_evaluated
policy_evaluated -> suppressed
                 -> grouped -> digest_pending
                 -> delivered -> acknowledged|snoozed|expired
```

A Watch notification must include the event, why it matters, the source and freshness, the next step, and how to snooze or stop repeats.

## 4. Data schemas

Use SQLite-compatible migrations with ISO-8601 timezone-aware timestamps and JSON text for flexible structured fields.

```sql
CREATE TABLE communication_preferences (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  category TEXT NOT NULL,
  key TEXT NOT NULL,
  value_json TEXT NOT NULL,
  source TEXT NOT NULL DEFAULT 'user',
  confidence REAL NOT NULL DEFAULT 1.0,
  last_confirmed_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(category, key)
);

CREATE TABLE commitments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  description TEXT,
  status TEXT NOT NULL,
  owner TEXT NOT NULL DEFAULT 'user',
  source_type TEXT NOT NULL,
  source_id TEXT,
  confidence REAL NOT NULL DEFAULT 0.5,
  sensitivity TEXT NOT NULL DEFAULT 'normal',
  due_at TEXT,
  follow_up_at TEXT,
  waiting_for TEXT,
  linked_task_id INTEGER,
  linked_goal_id INTEGER,
  linked_action_id INTEGER,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  completed_at TEXT,
  expires_at TEXT
);

CREATE TABLE notification_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_key TEXT NOT NULL UNIQUE,
  category TEXT NOT NULL,
  urgency TEXT NOT NULL,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  reason TEXT,
  source_json TEXT NOT NULL,
  response_id TEXT,
  commitment_id INTEGER,
  action_id INTEGER,
  first_seen_at TEXT NOT NULL,
  deliver_after TEXT,
  expires_at TEXT,
  state TEXT NOT NULL DEFAULT 'pending',
  delivered_channels_json TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE channel_deliveries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  notification_id INTEGER NOT NULL,
  channel TEXT NOT NULL,
  provider_message_id TEXT,
  status TEXT NOT NULL,
  error TEXT,
  sent_at TEXT,
  acknowledged_at TEXT,
  UNIQUE(notification_id, channel)
);
```

For location and devices:

```sql
CREATE TABLE location_consents (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  device_id TEXT NOT NULL,
  tier TEXT NOT NULL,
  purposes_json TEXT NOT NULL,
  accuracy TEXT NOT NULL,
  active_from TEXT NOT NULL,
  active_until TEXT,
  consent_version TEXT NOT NULL,
  paused_at TEXT,
  revoked_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE location_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id TEXT NOT NULL UNIQUE,
  device_id TEXT NOT NULL,
  observed_at TEXT NOT NULL,
  received_at TEXT NOT NULL,
  zone TEXT,
  geohash TEXT,
  latitude_encrypted TEXT,
  longitude_encrypted TEXT,
  accuracy_meters REAL,
  source TEXT NOT NULL,
  purpose TEXT NOT NULL,
  consent_id INTEGER NOT NULL,
  retention_until TEXT NOT NULL,
  processed_at TEXT,
  deleted_at TEXT
);

CREATE TABLE presence_state (
  device_id TEXT PRIMARY KEY,
  zone TEXT,
  state TEXT NOT NULL,
  confidence REAL NOT NULL,
  observed_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  source_event_id TEXT
);
```

## 5. Connecting ORA to your app and accounts

### Web frontend

Keep the Vercel React app as the user interface. Add a Communication Settings page, a notification history page, a commitment queue, a privacy dashboard, and device management. The browser should call authenticated ORA endpoints using the existing `X-ORA-Token` mechanism. Do not expose Gmail, Telegram, Groq, or device secrets in Vercel client code.

### Backend and event gateway

The backend should expose an HTTPS ingestion gateway with these protected or signature-verified endpoints:

| Endpoint | Purpose |
|---|---|
| `POST /api/ingest/gmail` | Receive verified Pub/Sub notifications and fetch Gmail deltas |
| `POST /api/ingest/telegram` | Receive verified Telegram webhook updates |
| `POST /api/ingest/device` | Receive signed Android companion events |
| `POST /api/devices/pair` | Pair a device through a visible confirmation code |
| `GET /api/devices` | List devices, permissions, last seen, and consent |
| `POST /api/devices/{id}/revoke` | Revoke a device immediately |
| `GET /api/location/current` | Return only non-expired consented presence |
| `POST /api/location/pause` | Pause every location routine |
| `DELETE /api/location/history` | Delete location records by time range |
| `GET /api/privacy/audit` | Show data-source access and retention history |

The gateway should acknowledge webhooks quickly, store a deduplicated event, and process it asynchronously. Never perform a long LLM call inside a provider webhook request.

### Gmail and email

Use the existing Google OAuth connection. Gmail supports push notifications through Cloud Pub/Sub; the `watch` must be renewed at least every seven days, and the backend should use `history.list` to fetch deltas and repair missed notifications [1]. Store message IDs, thread IDs, labels, sender, subject classification, timestamps, and a short-lived body cache only when needed for a user-requested summary, commitment extraction, or approved draft.

### Telegram

Use Telegram webhooks when the backend has a stable HTTPS endpoint. Verify `X-Telegram-Bot-Api-Secret-Token`, restrict update types, persist update IDs for deduplication, and send complex approval flows to the web dashboard. Telegram supports HTTPS webhook delivery and retries unsuccessful webhook responses [2].

### Notifications from other phone apps

A Vercel browser page cannot read other apps’ notifications when closed. For Android-wide notification awareness, use a mobile companion with a user-enabled `NotificationListenerService`. Start with an app allowlist and metadata-only capture. Default-redact OTPs, banking codes, passwords, private keys, and sensitive app bodies. Store a short-lived preview only when a specific workflow needs it.

## 6. Location awareness

The safest useful design is **event-based and adaptive**, not a permanent raw GPS stream. Give the user these tiers:

| Tier | Data collection | Example |
|---|---|---|
| Off | None | Maximum privacy |
| On demand | One location after a visible action | “Where am I?” |
| Routine | Coarse location during selected schedules | Workday or commute routine |
| Background approximate | Geofence and movement-triggered updates | “Alert me when I leave home” |
| Background precise | Temporary, explicitly justified feature | Navigation session |

Android distinguishes foreground/background access and approximate/precise accuracy; background access requires explicit permission on Android 10 and later [3]. Use a visible foreground service for an enabled background routine, with a persistent notification so the user knows it is active [4].

Default location policy:

1. Keep raw coordinates on-device where possible.
2. Upload a coarse geohash or named zone by default.
3. Send an update only on meaningful movement, geofence transition, or routine boundary.
4. Keep raw samples for at most 24 hours unless the user explicitly changes retention.
5. Mark every presence record with `observed_at`, `expires_at`, precision, purpose, and consent ID.
6. Treat stale location as “last seen,” never as current.
7. Include a global pause button, per-routine pause, device revoke, export, and delete controls.

The Android companion should buffer encrypted events offline and upload them later with a device-scoped rotating token. The backend must verify the device ID, event ID, signature, timestamp skew, consent scope, payload size, and replay status before persistence.

## 7. Awareness projection

Do not send all raw events to the model. Project bounded, fresh signals into ORA context:

```json
{
  "generated_at": "2026-08-20T11:00:00+03:00",
  "freshness": {
    "calendar": "2026-08-20T10:59:00+03:00",
    "gmail": "2026-08-20T10:57:00+03:00",
    "device": "2026-08-20T10:58:00+03:00",
    "location": "2026-08-20T10:55:00+03:00"
  },
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
      "type": "meeting_soon|important_email|commitment_due|device_notification|location_transition",
      "importance": 0.8,
      "urgency": "reminder",
      "reason": "A meeting starts in 30 minutes and has no preparation note.",
      "source_ids": ["calendar:event-123"]
    }
  ]
}
```

Deterministic code should handle consent, deduplication, rate limits, retention, and safety. The LLM should summarize or classify bounded signals, not decide whether it is allowed to read or retain raw data.

## 8. Hosting recommendation

For the first step, keep the Vercel frontend and current backend, add the response envelope, notification policy, commitments, and explicit privacy settings, and use scheduled synchronization. This is the least expensive and simplest path, but it is not real-time.

When timely email/Telegram events or background device updates become essential, move the event gateway to an always-on HTTPS service. Keep the main API and database behind the same authenticated contract, add Pub/Sub/webhook ingestion, and use a mobile companion for notification and location events. Do not use keep-alive traffic to defeat Render suspension.

A native mobile companion is required for dependable background location and other-app notification access. A PWA can support foreground location and push notifications, but it cannot provide the same system-level coverage when closed.

## 9. Build order

1. Implement the shared response envelope, communication preferences, notification event tables, quiet hours, and deduplication.
2. Implement commitments, follow-ups, and the daily priority projection.
3. Add Gmail Pub/Sub and Telegram webhook ingestion with reconciliation and signature verification.
4. Add device pairing, notification allowlisting, on-demand location, and privacy audit screens.
5. Add routine/geofence location only after pause, revoke, retention, and delete flows are tested.
6. Add end-to-end tests for duplicate webhook events, stale location, revoked consent, offline device buffering, provider outages, and cross-channel deduplication.

## References

[1]: https://developers.google.com/workspace/gmail/api/guides/push "Gmail API push notifications"

[2]: https://core.telegram.org/bots/api "Telegram Bot API webhooks"

[3]: https://developer.android.com/develop/sensors-and-location/location/permissions "Android location permissions"

[4]: https://developer.android.com/reference/android/app/Service.html "Android Service lifecycle and foreground behavior"

[5]: https://github.com/elishaoigara/ORA/blob/main/backend/personal_context.py "ORA canonical personal context"

[6]: https://github.com/elishaoigara/ORA/blob/main/backend/tool_contracts.py "ORA typed tool contracts"
