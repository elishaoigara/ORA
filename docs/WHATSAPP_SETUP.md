# WhatsApp for ORA — sidecar setup

ORA talks to WhatsApp through a small self-hosted bridge (`whatsapp-sidecar/`) instead of
embedding a WhatsApp client in the backend. The bridge holds the linked-device session;
ORA reaches it over HTTP with a shared secret.

```
             cron (external)                      HTTPS + x-api-secret
Render  ──►  /api/companion/tick  ──►  dispatch()  ────────────────►  ora-whatsapp sidecar  ──►  WhatsApp
   │                                    │                                   ▲
   │                                    └── Telegram (primary)              │
   └── POST /api/whatsapp/incoming  ◄──── inbound webhook (X-ORA-Token) ────┘
```

Outbound is a **mirror**: every companion alert that goes to Telegram is also sent to
WhatsApp when the channel is configured. Inbound messages only become an alert when they
read as time-sensitive, so routine chatter never becomes notification noise.

## 1. Deploy the sidecar

`render.yaml` already declares the service (`ora-whatsapp`, root `whatsapp-sidecar/`).
If you deploy manually instead:

| Setting | Value |
| --- | --- |
| Runtime | Node 22 |
| Root directory | `whatsapp-sidecar` |
| Build command | `npm ci --omit=dev` |
| Start command | `node src/server.js` |
| Health check path | `/health` |

Or with Docker:

```bash
docker build -t ora-whatsapp ./whatsapp-sidecar
docker run -p 8080:8080 -v ora-wa:/data \
  -e WA_API_SECRET='<same secret as the backend>' \
  -e ORA_BACKEND_URL='https://ora-oovf.onrender.com' \
  -e ORA_INTERNAL_TOKEN='<ORA_INTERNAL_TOKEN>' \
  ora-whatsapp
```

## 2. Configure both services

**Sidecar (`ora-whatsapp`)**

| Variable | Required | Notes |
| --- | --- | --- |
| `WA_API_SECRET` | yes | Same value as the backend's `WA_API_SECRET`. Must be ≥ 12 chars; the service refuses to boot on the public default. |
| `ORA_BACKEND_URL` | recommended | e.g. `https://ora-oovf.onrender.com` — enables the inbound webhook. |
| `ORA_INTERNAL_TOKEN` | with the above | Sent as `X-ORA-Token`; the backend rejects short or missing tokens. |
| `WA_AUTH_DIR` | no | Session directory. Use a persistent disk (`/data`) or `WA_SESSION_B64`. |
| `WA_SESSION_B64` | no | Restores a pairing after a redeploy — see §4. |
| `WA_MAX_MESSAGES` | no | In-memory message cache size, default `500`. |

**Backend (`ora-backend`)**

| Variable | Required | Notes |
| --- | --- | --- |
| `WA_SIDECAR_URL` | yes | Public URL of the sidecar, e.g. `https://ora-whatsapp.onrender.com`. |
| `WA_API_SECRET` | yes | Same secret as the sidecar. |
| `ORA_WA_NOTIFY_NUMBER` | yes | Your own number with country code (`2547XXXXXXXX`) or an exact WhatsApp contact name. |
| `ORA_INTERNAL_TOKEN` | for inbound | Must match the sidecar's value (≥ 16 chars). |

Nothing happens until **both** `ORA_WA_NOTIFY_NUMBER` and `WA_SIDECAR_URL` are set: the
mirror performs no network I/O when unconfigured, so a missing or deleted sidecar can never
delay Telegram delivery. Once configured, ORA sends a concise personal status update to
that WhatsApp destination every six hours. The first scheduled update runs six hours after
the backend scheduler starts.

## 3. Pair the device

1. Open `https://<sidecar-host>/qr?secret=<WA_API_SECRET>`.
2. On your phone: WhatsApp → Settings → Linked devices → Link a device, and scan.
3. `GET /status` (with the `x-api-secret` header) should report `"state": "open"`.

```bash
curl -s -H "x-api-secret: $WA_API_SECRET" https://ora-whatsapp.onrender.com/status
# {"ok":true,"state":"open","me":"2547…","pairedAt":"…"}
```

## 4. Keep the pairing alive

Render's free plan has an ephemeral disk, so a redeploy or restart loses the linked-device
session. Two options:

- **Persistent disk** (paid plans): mount a disk at `/data` and set `WA_AUTH_DIR=/data`.
- **Session backup** (free): while linked, call `GET /session/export` with the secret, then
  store the returned `b64` value as the `WA_SESSION_B64` environment variable. On boot the
  sidecar restores it and reconnects without a new QR scan.

Treat `WA_SESSION_B64` like a password: it is a live WhatsApp web session.

## 5. Verify end to end

```bash
# 1. Backend sees the channel configured (dashboard also shows delivery.whatsapp.enabled)
curl -s -H "Authorization: Bearer $ORA_API_TOKEN" https://ora-oovf.onrender.com/api/v2/sync \
  | python3 -c 'import json,sys;print(json.load(sys.stdin)["delivery"])'

# 2. Send a message through the sidecar directly
curl -s -X POST -H "x-api-secret: $WA_API_SECRET" -H 'Content-Type: application/json' \
  -d '{"to":"2547XXXXXXXX","message":"ORA sidecar test"}' \
  https://ora-whatsapp.onrender.com/send
```

Then queue a real alert (any companion notification) and confirm it arrives on both
Telegram and WhatsApp. Backend logs show `[WHATSAPP] send failed: …` on failure and stay
silent on success; alert rows carry an internal `whatsapp_done` marker that guarantees at
most one WhatsApp copy per alert even when Telegram retries.

## 6. Behaviour and limits

- **At-most-once mirror.** The `whatsapp_done` flag is stamped when an alert is claimed,
  before any network call. Alerts dispatched before you configure the channel are never
  replayed to WhatsApp.
- **Same privacy text.** Private mode sends "ORA · New update — open ORA to read your
  update", identical to Telegram. Detailed mode sends the full alert (≤ 4000 chars).
- **Inbound gating.** `/api/whatsapp/incoming` only queues an alert for messages containing
  words like `urgent`, `asap`, `help`, `call me`, `haraka`, `saidia`, `piga simu`. The
  queued text names the sender but never repeats the message body.
- **Memory only.** The sidecar keeps message bodies in RAM for the life of the process;
  nothing is written to disk except the linked-device credentials.
- **Free-tier sleep.** An idle Render web service spins down; the first request after that
  wakes it and the socket reconnects (allow ~30 s). The durable alert queue retries, so
  nothing is lost.
- **Security.** Every route except `/health` requires the shared secret; secrets are
  compared in constant time; `/qr` requires the secret as a header or `?secret=`. Rotate
  `WA_API_SECRET` on both services at the same time.

## 7. Troubleshooting

| Symptom | Check |
| --- | --- |
| `[WHATSAPP] send failed: sidecar rejected the message` | `WA_SIDECAR_URL` / secret mismatch, or `/status` is not `open`. |
| Alerts stop after a redeploy | Session lost — re-pair or set `WA_SESSION_B64`. |
| No inbound alerts | `ORA_BACKEND_URL` + `ORA_INTERNAL_TOKEN` set on the sidecar, message contains an urgency keyword. |
| `refusing to start: WA_API_SECRET …` | Secret missing, under 12 chars, or still the public default. |
| Messages duplicate on WhatsApp | Should not happen; `whatsapp_done` is stamped at claim. File a bug with the alert row's `delivery`/`attempts`. |
