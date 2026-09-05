# ORA · Mini AI

A personal AI workspace for Elisha: a restrained cyberpunk web app and Android companion with shared conversations, tasks, memory, document context and reviewable actions.

**This branch is the ORA 2 rebuild. It is not a deployed upgrade yet.** Configure durable storage and validate a new Android build before switching production. The original `backend/api.py` and earlier modules remain as a rollback reference; the new entry point is **`next_api:app`**. Earlier roadmap documents describe the legacy implementation, not the active Mini runtime.

## What you can do

- Talk to ORA with persistent, synchronized conversation history.
- Record a voice note, review the transcript, then send it.
- Choose an installed browser/Android voice and preview it. Read replies aloud optionally.
- Ask for task/reminder proposals, personal memory or a message draft; review before applying.
- Add tasks and reminders directly; complete them from either device.
- Receive Android-local reminders for up to 50 synchronized future tasks, even when Render sleeps.
- Opt into a daily local planning nudge. It respects the configured quiet-hour window; explicit timed reminders are not suppressed.
- Keep confirmed memory and upload PDF, text or Markdown documents from web or phone.
- Share today's phone calendar, one selected contact, current approximate location or battery status explicitly.
- Enable a native Android notification listener for selected Gmail, Calendar, WhatsApp and Telegram notifications. Previews are redacted and synced when the app opens.
- Review message drafts and open the OS share sheet to choose a recipient and send yourself.
- Pause phone awareness, delete shared phone context, revoke a phone, or export the workspace from the web.

## Design

Charcoal surfaces, quiet cyan accents, restrained violet, generous spacing and a small abstract ORA orb. Both clients have Today, Talk, Plan, Memory and Settings. `shared/theme.json` records the palette; web CSS and Android StyleSheet tokens match it.

## Architecture

- **Vercel:** static React/Vite web client. No secrets are compiled into the client.
- **Render Free:** one FastAPI worker, demand-driven requests. No always-running inference, cron loop, keep-alive traffic or local production database.
- **External Postgres:** durable workspace, hashed session/device credentials and mutation receipts. A Supabase session pooler is one compatible option. Enable SSL. The API initializes its two private tables and enables row-level security with no public policies.
- **Android:** Expo SDK 56, native notification module, local notification scheduling, secure credential storage and a device-local cached workspace/outbox.
- **AI:** Groq Llama 3.3 70B by default, one bounded inference per chat request. A compact context and limited history control input size. `ORA_DAILY_AI_REQUESTS` provides a durable daily request cap (default 100). This is a request cap, not a guaranteed token or cost ceiling.
- **Voice:** Groq Whisper transcription; system text-to-speech playback. Playback availability, offline support and voice quality depend on the device/browser speech engine.

See [setup and migration](docs/ORA_MINI_SETUP.md), [feature boundaries](docs/ORA_MINI_CAPABILITIES.md), and [validation](docs/ORA_MINI_VALIDATION.md).

## Local development

Backend (Python 3.11+):

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements-mini.txt
cp .env.example .env
# Set ORA_API_TOKEN and GROQ_API_KEY in .env.
uvicorn next_api:app --reload --port 8000
```

SQLite is allowed only for development. Production refuses to start without `DATABASE_URL`.

Web:

```bash
cd frontend
npm ci
npm run dev
```

The default backend is `http://localhost:8000`. Set `VITE_API_URL` for deployed builds. Enter your owner key in the connection screen; it is exchanged for a seven-day revocable session held in browser session storage. Remove the old `VITE_ORA_API_TOKEN` variable from Vercel.

Android:

```bash
cd mobile/ora-android-companion
pnpm install --frozen-lockfile
pnpm android
```

A native development/standalone build is required for the custom notification listener. Expo Go cannot validate it. Minimum Android version is 8 (API 26). A build recipe for an installable APK is included in `eas.json`; it requires your Expo account/project and Android signing credentials.

## Checks

```bash
cd backend
pip install httpx
python -m unittest test_mini -v
```

```bash
cd frontend
npm run lint
npm run build
```

```bash
cd mobile/ora-android-companion
pnpm check
pnpm test
pnpm build
```

The workflow in `.github/workflows/mini.yml` runs these gates. Android export verifies JavaScript packaging; it is not a Kotlin compile, signed APK or physical-device test.
