# ORA WhatsApp sidecar

A small, authenticated HTTP bridge that lets ORA read and send WhatsApp messages.

The backend talks to this service over HTTP using the shared `WA_API_SECRET`, and
`backend/mini/whatsapp.py` mirrors companion alerts to the owner. The full setup
guide is [`docs/WHATSAPP_SETUP.md`](../docs/WHATSAPP_SETUP.md).

On Render Free the bridge is **not** deployed as its own service: it is built into
the backend's Docker image and supervised by `backend/mini/wa_bridge.py`, so the
workspace pays for one service instead of two. Run it standalone only on a paid
plan (or locally); either way the HTTP contract below is identical.

```bash
npm install
npm test                 # 36 tests, no WhatsApp connection required
WA_API_SECRET=at-least-12-chars npm start
```

Then open `http://localhost:8080/qr?secret=<WA_API_SECRET>` and scan the code with
WhatsApp → Settings → Linked devices → Link a device.

## HTTP contract

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | Liveness for platform health checks (unauthenticated) |
| GET | `/status` | `{ ok, state, me, pairedAt }` — `state` is `open` when linked |
| GET | `/qr` | Pairing page (HTML, auto-refreshing, QR + pairing code) |
| GET | `/qr.json` | `{ state, linked, qr, code }` for the API's pairing proxy |
| POST | `/send` | `{ to, message }` — phone with country code, JID, or contact name |
| GET | `/messages` | `?limit&contact&unread&search&no_groups` |
| POST | `/mark-read` | `{ ids }` |
| GET | `/contacts` | `{ contacts: [{ name, phone }] }` |
| GET | `/groups` | `{ groups: [{ name, jid }] }` |
| POST | `/mute` | `{ jid, mute }` for a group |
| GET | `/unread-summary` | `{ total, summary: [...] }` |
| GET | `/session/export` | Base64 auth state for `WA_SESSION_B64` |

Every route except `/health` requires the `x-api-secret` header (the `/qr` page also
accepts `?secret=` so it can be opened in a browser).

## Environment

| Variable | Required | Notes |
| --- | --- | --- |
| `WA_API_SECRET` | yes | Shared secret with the backend. Refuses to boot on the public default or under 12 characters. |
| `PORT` | no | Defaults to `8080`. |
| `WA_AUTH_DIR` | no | Session directory, defaults to `./auth_state` (`/data` in Docker). |
| `ORA_BACKEND_URL` | no | With `ORA_INTERNAL_TOKEN`: inbound webhooks go to `/api/whatsapp/incoming`, and the session is mirrored to the backend's database. |
| `ORA_INTERNAL_TOKEN` | with backend URL | Header `X-ORA-Token` for those calls. |
| `WA_SESSION_SYNC` | no | `0` keeps credentials on disk only; on by default when the backend URL and token are set. |
| `WA_SESSION_B64` | no | Explicit session override, restored before anything else (see `/session/export`). |
| `WA_PAIR_NUMBER` | no | Phone number to request an 8-character pairing code (useful when the QR would have to be scanned by the screen showing it). |
| `WA_MAX_MESSAGES` | no | Ring-buffer size for the in-memory message cache (default `500`). |
| `WA_LOG_LEVEL` | no | pino level, default `warn`. |

## Surviving a restart

With `ORA_BACKEND_URL` + `ORA_INTERNAL_TOKEN` set, the bridge saves its credential
bundle to `PUT /api/whatsapp/session` (debounced, at most every ~15 s, plus once on
shutdown) and restores it from `GET /api/whatsapp/session` on boot. That is what lets
a sleeping free instance relink without a new QR scan. The bundle is never logged and
never leaves the authenticated channel.

## Privacy and safety

- Message bodies and read state live in memory only; they are never written to disk.
- Logs contain lifecycle events and exception class names, never message content,
  phone numbers, tokens, or the sidecar URL.
- Every mutating route is authenticated; the only anonymous route is `/health`.
- The service only sends text to an explicit recipient and reads what the linked
  device already received — it does not bulk-export chats or upload media.
