# Staying inside Render Free

ORA Mini is designed for one owner on a Render Free web service. The free plan is
generous but it is metered in a way that punishes "just keep it warm" habits, so
this page records the budget, the decisions that protect it, and the rules for
future changes.

## What Render Free actually gives you

| Resource | Free allowance | What it means for ORA |
| --- | --- | --- |
| Instance hours | **750 per workspace per month**, shared by *all* free services | One service running non-stop already uses ~730 h |
| Sleep | Spins down after **15 minutes without inbound traffic** | Any polling client keeps it awake indefinitely |
| Cold start | ~1 minute after sleep | Clients must tolerate a slow first request |
| CPU / RAM | ~0.1 CPU and 512 MB | Keep one worker, cap concurrency, avoid heavy startup work |
| Outbound traffic | Small monthly allowance on a Hobby workspace | Compress JSON, do not re-download unchanged snapshots |
| Postgres | 1 GB, **expires 30 days after creation** | Use an external durable database (Supabase) instead |
| Cron / workers | Not available on Free | Scheduling happens through an external tick, not a Render cron |

When the workspace runs out of hours, **every free service is suspended until the
next calendar month**. Unused hours do not roll over.

> **The tick interval is a product decision, not just a cost knob.**
> `.github/workflows/companion-tick.yml` currently schedules
> `cron: '17,47 * * * *'`. Every tick wakes the service, so it is also the
> WhatsApp catch-up interval: 30 minutes means WhatsApp is reachable (and catches
> up) twice an hour, for ~360 h/month; `cron: '47 4,10,16 * * *'` costs ~22 h but
> only catches up three times a day. Both fit the budget — pick the one you want.
> The workflow file can only be edited with a token that has the `workflow` scope.

## The budget before this cleanup

| Behaviour | Monthly cost |
| --- | --- |
| GitHub Actions tick every 30 minutes (48 wakes/day) | 48 × 15 min ≈ **360 h** |
| Second free web service (WhatsApp sidecar) held connected | ≈ **730 h** |
| User traffic | whatever is left |
| **Total before a single user request** | **≈ 1,090 h vs a 750 h budget** |

Two habits caused almost all of it:

1. **A 30-minute cron.** Render sleeps 15 minutes after the last request, so a
   tick every 30 minutes keeps the service awake half the time. A cron does not
   cost "one request"; it costs a *wake window*.
2. **A second free service.** The WhatsApp sidecar must hold a connection to
   WhatsApp to be useful, which means it never gets to sleep. Two free services
   cannot both fit in 750 hours, no matter how efficient the code is.

## The budget after this cleanup

The second service is gone: the WhatsApp bridge now runs inside the backend's
container (`backend/mini/wa_bridge.py`, built by the root `Dockerfile`), so the
workspace pays for one service no matter how many processes it hosts.

| Behaviour | Monthly cost |
| --- | --- |
| One free web service (API + embedded WhatsApp bridge) | no background cost while asleep |
| Tick every 30 min — WhatsApp catch-up twice an hour | 48 × 15 min ≈ **360 h** |
| …or tick three times a day — WhatsApp catches up 3×/day | ≈ **22 h** |
| Typical owner usage (a few sessions a day) | ~20–60 h |
| **Expected total** | **~420 h at the 30-minute cadence, ~80 h otherwise, of 750** |

Both columns fit. The 30-minute option buys WhatsApp responsiveness; the 3×/day
option buys headroom. What does *not* fit is a second always-on service — that was
the 730 h line in the table above, and no amount of tuning removes it.

## What changed in the code

- **One container** (`Dockerfile`, `render.yaml`): the Python API and the Node
  WhatsApp bridge are built into a single image and deployed as one Docker web
  service. `backend/mini/wa_bridge.py` supervises the bridge, restarts it if it
  dies, and shuts it down cleanly. A separate sidecar is still possible
  (`whatsapp-sidecar/render.yaml`, `plan: starter`) for a paid plan, but it is no
  longer the default and no longer needed on Free.
- **WhatsApp that survives sleep** (`backend/next_api.py`,
  `whatsapp-sidecar/src/session.js`): the linked-device credentials are saved to
  the `ora_mini_kv` table (debounced, ≤ 512 KB, never in a snapshot or export) and
  restored on boot, so a wake-up costs a reconnect instead of a QR pairing. The
  bridge is loopback-only; `/api/whatsapp/pairing?token=…` proxies the QR (and the
  pairing code) to the owner without exposing the sidecar secret.
- **Tick schedule** (`.github/workflows/companion-tick.yml`): deliberately left at
  30 minutes because that is now the WhatsApp catch-up cadence. Change it to
  `cron: '47 4,10,16 * * *'` if you would rather have the ~340 h back than
  twice-hourly WhatsApp catch-up (07:47, 13:47, 19:47 in Africa/Nairobi).
- **Compression** (`backend/next_api.py`): gzip for JSON responses above 500 bytes.
  Workspace snapshots are highly repetitive JSON and shrink by roughly 80%.
  Downloads are skipped because they are already compressed.
- **Conditional sync** (`/api/v2/sync`): the snapshot now carries an `ETag`. A
  client that already has the current workspace receives an empty `304`, not the
  whole payload. The tag changes on every mutation, per device scope, and at
  least every five minutes so clock-derived suggestions still refresh.
- **Client polling** (`frontend/src/App.jsx`, `ToolsPage.jsx`): one self-scheduling
  loop instead of fixed intervals. It polls every 60 s while the tab is active,
  every 3 min after two idle minutes, and **stops entirely** when the tab is
  hidden or after ten minutes without input. Any click, key press, scroll or tab
  focus resumes it immediately. A hidden tab therefore lets Render sleep.
- **Store** (`backend/mini/store.py`): pooled Postgres connections (no TLS
  handshake per request) and a five-second read cache that every mutation
  refreshes. One request used to parse the whole workspace three or four times.
- **Startup**: the Telegram webhook is re-registered at most once a week (or after
  a URL change or failure) instead of on every cold start.
- **Server flags**: `--workers 1 --limit-concurrency 32 --timeout-keep-alive 5`,
  which protects 512 MB of RAM without changing behaviour.

## Rules for future changes

1. **Do not add a keep-alive.** No uptime pinger, no cron-job.org warm-up, no
   self-ping. They work by spending the whole monthly allowance.
2. **Do not add a second free service.** Upgrade to a paid instance or combine the
   work into this process — that is exactly what the WhatsApp bridge does now.
3. **Budget a wake pattern before adding it.** A schedule that fires every N
   minutes costs about `1440 × 15 / N` hours a month (the 15-minute idle window):

   | Interval | Approx. hours/month |
   | --- | --- |
   | 5 min | 4,320 (impossible on Free) |
   | 30 min | 720 |
   | 1 h | 360 |
   | 2 h | 180 |
   | 3× per day | 22 |

   Anything more frequent than a few times a day is a deliberate trade against
   user traffic.
4. **Clients poll only while visible and active.** New screens must reuse the
   visibility gate rather than adding a `setInterval`.
5. **Prefer a 304 over a payload.** Add an `ETag` to any endpoint a client polls.
6. **Keep one worker.** It bounds model concurrency and memory; the database
   transactions, not multiple workers, provide safety.

## Verifying usage

Open the Render Dashboard → **Billing** and read *Free instance hours* for the
workspace. A healthy month stays in the low tens of hours. If the number climbs,
the cause is almost always one of: a new polling client, a shortened cron, or a
second service.

`GET /api/health` reports `free_tier: true` when `ORA_FREE_TIER=1` is set (the
blueprint sets it), which is a quick way to confirm a deployment carries this
configuration.
