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
- Research public sources with links, create and revise reviewed documents, and download real DOCX/PDF, PowerPoint and XLSX files from either client.
- Share today's phone calendar, one selected contact, current approximate location or battery status explicitly.
- Enable a native Android notification listener for selected Gmail, Calendar, WhatsApp and Telegram notifications. Previews are redacted and synced when the app opens.
- Review message drafts and open the OS share sheet to choose a recipient and send yourself.
- Pause phone awareness, delete shared phone context, revoke a phone, or export the workspace from the web.

## Design

Charcoal surfaces, quiet cyan accents, restrained violet, generous spacing and a small abstract ORA orb. Both clients have Today, Talk, Plan, Memory and Settings. `shared/theme.json` records the palette; web CSS and Android StyleSheet tokens match it.

## Architecture

- **Vercel:** static React/Vite web client. No secrets are compiled into the client.
- **Render Free:** one FastAPI worker, demand-driven requests. No always-running inference, cron loop, keep-alive traffic or local production database. The workspace shares 750 instance hours a month, so compressed snapshots, `ETag`/`304` syncs, visible-tab-only polling and a three-times-a-day tick keep normal use in the low tens of hours. See [the free-tier budget](docs/RENDER_FREE_BUDGET.md).
- **External Postgres:** durable workspace, hashed session/device credentials and mutation receipts. A Supabase session pooler is one compatible option. Enable SSL. The API initializes its two private tables and enables row-level security with no public policies.
- **Android:** Expo SDK 56, native notification module, local notification scheduling, secure credential storage and a device-local cached workspace/outbox.
- **AI:** DeepSeek (`deepseek-flash` by default), up to three bounded inference calls per chat request. A compact context and limited history control input size. `ORA_DAILY_AI_REQUESTS` provides a durable daily request cap (default 100). This is a request cap, not a guaranteed token or cost ceiling.
- **Voice:** Groq Whisper transcription; system text-to-speech playback. Playback availability, offline support and voice quality depend on the device/browser speech engine.

See [setup and migration](docs/ORA_MINI_SETUP.md), [feature boundaries](docs/ORA_MINI_CAPABILITIES.md), and [validation](docs/ORA_MINI_VALIDATION.md).

The new file tools use the existing authenticated `/api/v2/tools` flow. Ask ORA to create a file or use Tools & activity, inspect the exact proposal, approve it, then download it from Saved files. File source is stored in the durable workspace and rendered on demand; no public links or filesystem persistence are required. Live research needs `TAVILY_API_KEY` on Render. See [tool setup and limits](docs/TOOLS.md).

## Local development

Backend (Python 3.11+):

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements-mini.txt
cp .env.example .env
# Set ORA_API_TOKEN and DEEPSEEK_API_KEY in .env.
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


See [DeepSeek migration](docs/DEEPSEEK_MIGRATION.md) for backend setup and companion behavior.
