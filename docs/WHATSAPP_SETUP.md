# WhatsApp for ORA on Render Free

ORA talks to WhatsApp through a small self-hosted bridge (`whatsapp-sidecar/`) that
holds the linked-device session. On Render Free the bridge does **not** get its own
service: it runs as a supervised child process of the backend, inside the same
container. That is what makes WhatsApp affordable on the free plan.

```
                    ONE free web service (750 h/month for the whole workspace)
   ┌──────────────────────────────────────────────────────────────────────────┐
   │  uvicorn  next_api.py        ──►  /api/companion/tick, /api/v2/*          │
   │      │  supervises (mini/wa_bridge.py)                                    │
   │      ▼                                                                    │
   │  node  whatsapp-sidecar  ──►  connected WhatsApp device  (loopback :8080) │
   │      │                                                                    │
   │      ├── POST /api/whatsapp/incoming        inbound urgency alerts        │
   │      ├── PUT  /api/whatsapp/session         saves the linked device       │
   │      └── GET  /api/whatsapp/session         restores it after a sleep     │
   └──────────────────────────────────────────────────────────────────────────┘
                                    │
                          Telegram (primary channel)
```

The old design needed a second always-on service. A bridge that holds a socket uses
~730 instance hours a month on its own and the backend uses the rest, so the
workspace (750 h) ran out and **both** services were suspended. Sharing one process
removes that cost entirely: WhatsApp is available whenever ORA is awake, and costs
nothing extra.

## 1. Turn it on

Everything below belongs to the single `ora-backend` service (`render.yaml` already
declares it).

| Variable | Required | Notes |
| --- | --- | --- |
| `WA_EMBEDDED` | yes | `1` starts the bridge inside the service. Without it nothing new runs. |
| `WA_API_SECRET` | yes | Shared secret for the loopback bridge. 12+ characters, never the public default. |
| `ORA_INTERNAL_TOKEN` | yes | 16+ characters. Authenticates the bridge's webhooks **and** its session saves. |
| `ORA_WA_NOTIFY_NUMBER` | to mirror alerts | Your number with country code (`2547XXXXXXXX`) or an exact WhatsApp contact name. |
| `WA_PAIR_NUMBER` | for phone-only pairing | Your number with country code. Makes WhatsApp issues an 8-character pairing code instead of requiring a QR scan. |
| `WA_SIDECAR_PORT` | no | Default `8080`, loopback only. It is never exposed publicly. |
| `WA_MAX_MESSAGES` | no | In-memory message cache, default `200` here to fit beside the API in 512 MB. |
| `NODE_OPTIONS` | no | `--max-old-space-size=160` keeps the bridge from crowding the API. |
| `WA_SESSION_SYNC` | no | `0` disables credential backup to the database (default on). |
| `WA_SIDECAR_URL` | no | Leave empty for the embedded bridge. Set it only for a standalone sidecar (§6). |

The bridge only starts when `WA_EMBEDDED=1`, `WA_API_SECRET` (≥ 12 chars),
`ORA_INTERNAL_TOKEN` (≥ 16 chars) and a `node` binary are all present. Otherwise the
backend behaves exactly as it did before — no child process, no network I/O, no
errors.

## 2. Pair the phone

Open, once:

```
https://ora-oovf.onrender.com/api/whatsapp/pairing?token=<ORA_API_TOKEN>
```

- The page shows a QR: scan it from WhatsApp → **Settings → Linked devices → Link a device**.
- If `WA_PAIR_NUMBER` is set, it also shows an 8-character code. Use **Link with
  phone number** and type it — the only option when the page is open on the very
  phone that would have to scan the code.

The bridge is loopback-only, so the backend proxies the QR and no sidecar secret ever
reaches your browser. The owner key does appear in the URL of that one request (and
therefore in your Render access log, as with the old `/qr?secret=` page); rotate
`ORA_API_TOKEN` afterwards if that matters to you. Check the state from the app with
`GET /api/v2/whatsapp/status` (owner session), which returns booleans only:

```json
{"enabled": true, "linked": true, "state": "open"}
```

The linked phone number is deliberately never returned to a client.

## 3. Why the link survives sleep

Render Free stops an idle instance after 15 minutes and **destroys its filesystem**.
A linked-device session kept only on disk is gone after the first nap, which is why
the old setup asked you to re-pair (or paste `WA_SESSION_B64`) after every restart.

Now the credentials live in the database:

| Direction | Endpoint | Who calls it |
| --- | --- | --- |
| Save | `PUT /api/whatsapp/session` | the bridge, after WhatsApp rotates keys (debounced, ≥ 15 s apart) |
| Restore | `GET /api/whatsapp/session` | the bridge, on boot, before the socket starts |

They are stored in the `ora_mini_kv` table under `whatsapp.session`, capped at 512 KB,
and are **never** part of a sync snapshot, an export or the workspace read cache.

Boot order: `WA_SESSION_B64` (explicit override) → credentials already on disk (a
persistent-disk deployment) → the database copy → otherwise wait for a QR. So a wake
costs a reconnect, not a new pairing.

To unlink deliberately: unlink on the phone, then
`DELETE /api/whatsapp/session` with `X-ORA-Token: $ORA_INTERNAL_TOKEN` (or
`?token=<ORA_API_TOKEN>`). Treat a stored session like a password — it is a live
WhatsApp web session.

## 4. What "works on the free tier" actually means

The service sleeps when nothing talks to it, and the socket sleeps with it. That is
the one limitation that no amount of code can remove, so ORA is built around it:

| Situation | Behaviour |
| --- | --- |
| ORA is awake | Full WhatsApp: read chats, send messages, mirror alerts. A send that lands while the socket is still linking waits up to 15 s instead of failing. |
| ORA goes to sleep | The socket closes, exactly as if you had closed WhatsApp Web. WhatsApp keeps recent messages for the linked device. |
| ORA wakes up | The bridge restores the session from Postgres, relinks in a few seconds, and the messages WhatsApp held are delivered. Those that read as urgent become alerts. Messages older than WhatsApp's offline window may not be replayed. |
| You send while asleep | The request wakes the service (~1 min cold start); the message then goes out normally. |

**The wake-ups are the delivery cadence.** Every companion tick wakes the service,
so it is also the WhatsApp catch-up interval:

- **Tick every 30 minutes** (`cron: '17,47 * * * *'`, the current workflow): WhatsApp
  catches up twice an hour during the day. Costs ~360 of the 750 h, leaving ~390 h
  for your own sessions — comfortable.
- **Tick three times a day**: cheaper (~22 h) but messages that arrive while ORA
  sleeps wait until the next tick. Only choose this if you do not need WhatsApp
  promptly.

Do not add a keep-alive to get "instant" WhatsApp: a service that never sleeps uses
the entire monthly allowance and gets suspended, at which point nothing works. See
[the free-tier budget](RENDER_FREE_BUDGET.md).

## 5. Verify end to end

```bash
# 1. Bridge state, booleans only
curl -s -H "Authorization: Bearer $TOKEN" https://ora-oovf.onrender.com/api/v2/whatsapp/status
# {"enabled":true,"linked":true,"state":"open"}

# 2. Channel configured (the snapshot reports the mirror as enabled)
curl -s -H "Authorization: Bearer $TOKEN" https://ora-oovf.onrender.com/api/v2/sync \
  | python3 -c 'import json,sys;print(json.load(sys.stdin)["delivery"])'
```

Then queue a real companion alert and confirm it reaches both Telegram and WhatsApp.
Backend logs stay silent on success and print `[WHATSAPP] send failed: …` on failure.
An alert carries an internal `whatsapp_done` marker, so a Telegram retry never
duplicates the WhatsApp copy.

## 6. Standalone sidecar (optional, paid)

The separate service still works and is unchanged: deploy `whatsapp-sidecar/render.yaml`
(`plan: starter`), set `WA_SIDECAR_URL` on the backend, and leave `WA_EMBEDDED` unset.
Use it if you want WhatsApp live 24/7 regardless of whether ORA is awake — a free
workspace cannot afford two always-on services, so this path is for a paid plan. The
session endpoints work there too: set `ORA_BACKEND_URL` + `ORA_INTERNAL_TOKEN` and the
sidecar backs its credentials up to the same database instead of relying on
`WA_SESSION_B64`.

## 7. Migrating from the standalone sidecar

If you already run `ora-whatsapp`, move the linked device instead of scanning again:

```bash
# 1. Export the live session from the old service
curl -s -H "x-api-secret: $WA_API_SECRET" https://ora-whatsapp.onrender.com/session/export \
  | python3 -c 'import json,sys;print(json.load(sys.stdin)["b64"])' > session.b64

# 2a. Either store it in the database (preferred, no redeploy)
curl -s -X PUT https://ora-oovf.onrender.com/api/whatsapp/session \
  -H "X-ORA-Token: $ORA_INTERNAL_TOKEN" -H 'Content-Type: application/json' \
  -d "{\"b64\": \"$(cat session.b64)\"}"

# 2b. …or set it as WA_SESSION_B64 on the backend (restored before the DB copy)
```

Then, once `/api/v2/whatsapp/status` reports `linked: true`, **delete the
`ora-whatsapp` service** in Render. Two always-on services are what exhausted the
workspace hours in the first place. Treat the exported `b64` like a password and
delete it afterwards.

## 8. Behaviour and limits

- **At-most-once mirror.** `whatsapp_done` is stamped when an alert is claimed, before
  any network call. Alerts dispatched before the channel was configured are never
  replayed later.
- **Same privacy text.** Private mode sends "ORA · New update — open ORA to read your
  update", identical to Telegram. Detailed mode sends the full alert (≤ 4000 chars).
- **Inbound gating.** `/api/whatsapp/incoming` only queues an alert for messages that
  read as time-sensitive (`urgent`, `asap`, `help`, `call me`, `haraka`, `saidia`,
  `piga simu`, …). The queued text names the sender but never repeats the body.
- **Memory only.** Message bodies stay in RAM for the life of the process; the only
  thing written to storage is the credential bundle.
- **Share the 512 MB.** The API and the bridge run in one container. `WA_MAX_MESSAGES`
  and `NODE_OPTIONS` keep the bridge small; raise them only if Render reports OOM.
- **Loopback only.** The bridge listens on `127.0.0.1:8080`; the only public surface
  is the API, and pairing is proxied by an owner-authenticated page.
- **Security.** The bridge requires `x-api-secret` on every route except `/health`;
  secrets are compared with a constant-time digest; the API requires
  `X-ORA-Token` for session reads and writes. Rotate `WA_API_SECRET` and
  `ORA_INTERNAL_TOKEN` together and re-pair.

## 9. Troubleshooting

| Symptom | Check |
| --- | --- |
| `/api/v2/whatsapp/status` says `enabled: false` | `WA_EMBEDDED=1`, `WA_API_SECRET` ≥ 12 chars, `ORA_INTERNAL_TOKEN` ≥ 16 chars, and this image (the bridge only exists in the Docker build). |
| Status says `state: "closed"` for a while | The device was unlinked on the phone, or the session was wiped. Open the pairing page again. |
| Pairing page shows "Waiting for the bridge" | The service just woke up; the socket needs a few seconds. The page retries. |
| Alerts mirror to Telegram but not WhatsApp | `ORA_WA_NOTIFY_NUMBER` missing, or `state` is not `open`. |
| Alerts stop after a few days | The phone unlinked the device (WhatsApp → Linked devices). Re-pair. |
| `[startup] refusing to start: WA_API_SECRET …` | Secret missing, under 12 chars, or still the public default — the bridge fails closed. |
| Container restarts repeatedly / OOM | Lower `WA_MAX_MESSAGES` (100) and keep `NODE_OPTIONS=--max-old-space-size=160`. |
| Messages arrive in bursts | Expected: WhatsApp delivers what it held while ORA was asleep at the first wake-up. Shorten the tick interval to tighten the gap. |
