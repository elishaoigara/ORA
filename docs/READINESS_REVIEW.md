# ORA readiness review — 12 October 2026

This repair package includes the reviewed UI and reliability fixes plus the
Telegram migration. Runtime credentials and a real phone still need the
activation checks below. See TELEGRAM_SETUP.md for voice and phone calls.

Reviewed main branches:
- ORA: `811a28c6c40c509ae6edae31da678e9cacdbb00c`
- ora-android-companion: `01be1571a55eae38a70583d0c4c2025f7ff21f5c`

## What exists today

The deployed entry point is `backend/next_api.py`, with `backend/mini/*`.
Legacy backend modules and roadmap documents do not establish that a feature
is active in this runtime.

| Area | Implemented capability | Practical limit |
| --- | --- | --- |
| AI and workspace | DeepSeek chat, saved history, tasks, repeats, memories, reviewed proposals, shared web/phone state | A configured key does not prove provider balance or a live reply. History is capped at 300 messages, tasks at 500 and memories at 200. |
| Documents | PDF/text/Markdown ingestion; reviewed creation/editing and download of DOCX, PDF, PPTX, XLSX and text | Bounded excerpt-based input and structured output, not arbitrary full-fidelity Office editing. Spreadsheet text cannot execute formulas. |
| Projects | Project notes, attachments and separate conversations; reviewed desktop-agent commands | A paired local desktop worker is required to execute desktop commands. |
| Connected tools | GitHub repository/build reads and proposed changes; web research; Gmail/Calendar adapters; Telegram | Each needs its own server configuration and account access. ChatGPT's GitHub connection does not configure ORA's integration. Writes require the existing review flow. |
| Android | One-time pairing, SecureStore session, offline task/memory outbox, cached workspace, local reminders, biometric lock, voice notes and spoken replies | Cloud sync runs in the foreground/about every 60 seconds. Reminder changes made on the web reach the phone on its next sync. |
| Phone awareness | Opt-in notification listener, selected sources, redaction, short-lived context; manual battery, location, contacts and calendar snapshots | No continuous background cloud sync or continuous location tracking is active. Native notification access requires a standalone build, not Expo Go. |
| Proactivity | Weather checks, daily routines, alert inbox, Telegram alert dispatch; generic local daily nudge | Remote work depends on the external scheduler, Telegram pairing, permissions and quiet hours. The GitHub schedule is every 30 minutes, not exact-time delivery. |

## Evidence and fixes

1. **Scheduled automation was not running in the inspected successful job.**
   Job `114638169039` in ORA run `38195844836` logged empty `ORA_BACKEND_URL`
   and `ORA_CRON_TOKEN`, then exited 0. This change fails clearly when these
   secrets are missing, declares the Render cron token, exposes authenticated
   configuration diagnostics and records the last completed dispatch.
2. **Android main does not build an APK.** Its `build` script only runs
   `expo export --platform android`. This change adds a separate native Gradle
   APK build with Java 17, an artifact and checksum, plus the explicit Kotlin
   return used in the successful older native-build branch. It preserves the
   lightweight export check. The native workflow runs on pushes to main.
3. **Notification retries replay already uploaded items.** This change acknowledges
   each successful item, removes expired/invalid timestamps and preserves
   unsent items after failure and new events outside the snapshot. The existing
   server idempotency remains in place. Expo/FCM token registration has been removed; opt-in Telegram alerts replace it.
4. **Startup errors could escape the saved-session load.** This change catches
   that failure, moves session reads inside sync error handling and exports
   Expo Router's error boundary.
5. **Misleading or mixed state.** This change fixes reversed task priorities,
   filters project messages from general chat on both clients, scopes displayed
   phone events to their device, and returns 422 for an empty event timestamp.
6. **Probe failures in the supplied logs.** This change adds GET/HEAD at `/` and
   `/api/health`; health performs a small database check and returns 503 when
   storage is unavailable without exposing connection details.
7. **Design.** Both clients use navy `#10131d`, cards `#191e2c`, indigo
   `#a5b4fc`, mint `#5eead4`, text `#f5f7fc` and muted text `#a8b3c8`.
   Cards and chat bubbles have consistent rounded corners, clearer typography,
   larger controls, and visible connection diagnostics. The web mobile bar has
   five destinations; Tools and Projects remain available through Connections.
   Shared Android changes are mirrored in ORA's embedded mobile copy.

## What the Render logs mean

- The shutdown lines show graceful termination, not an application exception.
  The roughly 15-minute idle intervals are consistent with Render Free sleep.
  Render documents a roughly one-minute wake-up delay. A paid compute instance
  removes idle sleep; upgrading is an account decision, not a code fix.
- `/` returning 404 and `HEAD /api/health` returning 405 reflect missing routes/
  methods in the current source. They do not show a failed chat request.
- Chat, sync and event requests in the supplied excerpt returned 200.
- Repeated event POSTs can be a queued notification batch being drained. The
  access log does not show payload IDs, so it cannot establish an infinite loop.
- The live health check returned 200, `storage: postgres` and
  `ai_configured: true` during this review. Current health does not validate the
  AI key or prove database availability; this change improves the database probe.

## Activation after deployment

1. Both repositories use main for these changes. Check the ORA Mini checks
   workflow and Android checks and APK workflow. Deploy the backend, then install
   the newly compiled APK; a bundle export alone is not an installable app.
2. In Render, set a strong `ORA_CRON_TOKEN` of at least 32 characters. In ORA
   GitHub Actions secrets, set the SAME `ORA_CRON_TOKEN` and set
   `ORA_BACKEND_URL=https://ora-oovf.onrender.com`. Do not put secrets in code
   or send their values through chat. Run Companion weather and Telegram alerts
   manually once; verify a completed timestamp in Connections.
3. Verify `DATABASE_URL`, `ORA_API_TOKEN`, `DEEPSEEK_API_KEY`, the account's
   supported `DEEPSEEK_MODEL`, and the frontend origin in `CORS_ORIGINS`.
   Existing live health reports `deepseek-flash`; its actual provider access
   must be checked with an authenticated test message. Optional voice needs
   `GROQ_API_KEY`. The frontend API origin should point at the Render service.
4. Build/install the new APK and pair it using a fresh code from web Connections.
   Allow notifications and precise reminder timing. Create a reminder two
   minutes ahead, sync, close ORA and verify delivery. Check offline outbox
   recovery by creating a task offline, reconnecting and syncing.
5. Set `TELEGRAM_BOT_TOKEN` on Render and pair your private Telegram account
   through web Connections. `/alerts on` enables a daily Telegram check-in without
   Android. `/voice on` enables spoken previews; sending a voice note transcribes
   it with Groq. The Android notification center separately enables phone weather
   and routine alerts. No Firebase project, Google services file, FCM sending
   credentials or Expo push token is needed. Local reminders remain on Android.
6. Enable only the integrations you need: `GITHUB_TOKEN` plus `ORA_GITHUB_REPOS`;
   `TAVILY_API_KEY` for research; `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`,
   `GOOGLE_REFRESH_TOKEN` for the implemented Google adapters;
   `TELEGRAM_BOT_TOKEN` and a valid public backend URL for Telegram. Check each
   through its own connection/tool test.

## APK signing and installation

An older successful build is still available as of this review:
https://github.com/elishaoigara/ora-android-companion/actions/runs/37284349844/artifacts/11335752027

It was built on 5 October from `48a097b2ed746583bb2623f3ea5a00ff2da150ad`,
on `arena/01a10a0b-ora-android-companion`, and expires on 19 October.
It predates this draft. Its successful Gradle run is evidence for that build,
not proof that the new draft compiles natively. The new workflow uses the
generated Expo development signing identity for personal testing; stable release
signing is still needed for predictable updates. Do not discard an older
installation with unsynced data merely to bypass a signing mismatch.

## Local validation and remaining gates

- Backend: 89 unittest cases passed, including Telegram delivery, voice, call limits, and readiness regressions.
- Web: ESLint and Vite production build passed.
- Android: TypeScript check, 14 tests across five files, and Android bundle export passed.
- Browser: login → task creation → real local API → SQLite persistence → reload
  passed. General chat filtering and connection diagnostics were checked.
  The five main pages at 1440, 390 and 320 px had no horizontal overflow or
  browser page errors. Screenshots were inspected internally.
- The tests use local data and mocked external-provider responses where appropriate.
  No authenticated production AI/tool action or private workspace export was run.
- Not yet verified: the new native APK compile/install, real-device crash/ANR
  behavior, live Telegram/voice/call delivery, exact alarm delivery, microphone, biometrics, and
  live external-provider credentials. Capture the device model, Android version,
  failing steps and a redacted crash trace if an issue remains after installing.
- Continuous background sync, background location and unrestricted autonomous
  phone control are not introduced by these patches.

## Sources

- https://github.com/elishaoigara/ORA/tree/811a28c6c40c509ae6edae31da678e9cacdbb00c
- https://github.com/elishaoigara/ora-android-companion/tree/01be1571a55eae38a70583d0c4c2025f7ff21f5c
- https://github.com/elishaoigara/ORA/actions/runs/38195844836
- https://github.com/elishaoigara/ora-android-companion/actions/runs/37284349844
- https://render.com/docs/free
- Supplied Render log excerpt and local test results from this review.
