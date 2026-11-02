# ORA WhatsApp sidecar

A small, authenticated HTTP bridge that lets ORA read and send WhatsApp messages.

ORA's backend never embeds WhatsApp: `backend/connectors/whatsapp.py` talks to this
service over HTTP using the shared `WA_API_SECRET`, and `backend/mini/whatsapp.py`
mirrors companion alerts to the owner. The full setup guide is
[`docs/WHATSAPP_SETUP.md`](../docs/WHATSAPP_SETUP.md).

```bash
npm install
npm test                 # 19 tests, no WhatsApp connection required
WA_API_SECRET=at-least-12-chars npm start
```

Then open `http://localhost:8080/qr?secret=<WA_API_SECRET>` and scan the code with
WhatsApp → Settings → Linked devices → Link a device.

## HTTP contract

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | Liveness for platform health checks (unauthenticated) |
| GET | `/status` | `{ ok, state, me, pairedAt }` — `state` is `open` when linked |
| GET | `/qr` | Pairing page (HTML, auto-refreshing) |
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
| `ORA_BACKEND_URL` | no | When set with `ORA_INTERNAL_TOKEN`, inbound messages are POSTed to `/api/whatsapp/incoming`. |
| `ORA_INTERNAL_TOKEN` | with backend URL | Header `X-ORA-Token` for that webhook. |
| `WA_SESSION_B64` | no | Restores a linked session after a redeploy (see `/session/export`). |
| `WA_PAIR_NUMBER` | no | If set, logs a pairing code instead of relying on the QR page. |
| `WA_MAX_MESSAGES` | no | Ring-buffer size for the in-memory message cache (default `500`). |
| `WA_LOG_LEVEL` | no | pino level, default `warn`. |

## Privacy and safety

- Message bodies and read state live in memory only; they are never written to disk.
- Logs contain lifecycle events and exception class names, never message content,
  phone numbers, tokens, or the sidecar URL.
- Every mutating route is authenticated; the only anonymous route is `/health`.
- The service only sends text to an explicit recipient and reads what the linked
  device already received — it does not bulk-export chats or upload media.
