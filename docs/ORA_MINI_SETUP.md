# Bring ORA Mini online

## Before switching the live app

Keep the existing production branch/deployment while configuring Mini. The new clients use `/api/v2`; the old API is not compatible. Do not switch only one half and expect it to work. Build a Vercel preview and a separate backend test deployment first if you want zero disruption.

Save a copy of the old SQLite database and any uploaded documents before restarting or redeploying the old free Render instance. If it has already lost its ephemeral files, the repository cannot recover those personal records.

## 1. Durable database

Render Free cannot attach a persistent disk. Its local SQLite/filesystem data is lost on restart, redeploy or spin-down. A sleeping service also cannot execute background jobs.

Use an external Postgres database, for example a Supabase project:

1. Open the project's **Connect** panel and copy its **Session pooler** connection string (port 5432). Use the database password, not a Supabase API key.
2. URL-encode special characters in the password when constructing a URL. Do not paste credentials into GitHub, source files or chat.
3. Set the complete connection string as Render's secret `DATABASE_URL`. Use `sslmode=require` or stronger. `verify-full` with the provider certificate is supported.
4. The database user needs permission to create and own the two `ora_mini_*` tables. The service enables RLS without anonymous/authenticated policies. Use the database connection only from the backend, never from either client.

The store uses a serialized single-owner workspace and transactional idempotency receipts. It is intentionally sized for a personal assistant, not a multi-user service. Provider free-tier quotas and availability still apply. Render's own free Postgres database is not a permanent storage plan because its free database expires.

## 2. Render backend

Keep Root Directory **backend**. Update:

- Build: `pip install -r requirements-mini.txt`
- Start: `uvicorn next_api:app --host 0.0.0.0 --port $PORT --workers 1`
- Health path: `/api/health`
- Instance: **Free**
- Remove the old persistent disk declaration. `render.yaml` already describes this setup.

Configure these environment variables:

| Variable | Value |
| --- | --- |
| `APP_ENV` | `production` |
| `DATABASE_URL` | Secret external Postgres URL |
| `ORA_API_TOKEN` | Long random owner key, generated in your password manager or locally |
| `GROQ_API_KEY` | Your Groq API key |
| `CORS_ORIGINS` | Exact Vercel origin; comma-separate any explicitly allowed preview origins |
| `GROQ_MODEL_PRIMARY` | `llama-3.3-70b-versatile` by default |
| `GROQ_STT_MODEL` | `whisper-large-v3-turbo` by default |
| `ORA_DAILY_AI_REQUESTS` | `100` default; adjust to your provider quota/budget |

Do not add wildcard browser origins. `ORA_API_TOKEN` is not a Google or Supabase token. Keep one worker: it bounds inference concurrency and avoids simultaneous model requests from multiple clients. Durable database transactions still protect task mutations.

Open `/api/health` and check `release: ora-mini-2`, `storage: postgres`, and `ai_configured: true`. A missing database makes production startup fail deliberately rather than silently losing your data.

A first request after sleep may take around a minute. The clients wait up to 115 seconds and preserve unsent drafts. They do not generate fake keep-alive traffic. Only visible/foreground clients synchronize every 60 seconds.

## 3. Migrate available old data

Run this from `backend` against a COPY of the old database. The source is opened read-only.

```bash
python migrate_legacy.py /absolute/path/to/old-ora.db
```

This prints import counts without changing either database. With the new destination configured in your local environment:

```bash
python migrate_legacy.py /absolute/path/to/old-ora.db --apply
```

The import refuses to overwrite a nonempty Mini task/message/memory workspace. It imports up to 500 tasks, the most recent 300 conversation turns and up to 200 confirmed/verified learned facts. Legacy naive timestamps are interpreted as Africa/Nairobi. Other data is NOT silently imported: re-upload documents and pair devices again. Keep the original database as your archive for goals, M-Pesa history, unconfirmed facts, integrations and older conversations. No external credentials are imported.

## 4. Vercel web

- Root Directory: **frontend**
- Build command: `npm run build`
- Output: **dist**
- Set `VITE_API_URL=https://YOUR_BACKEND.onrender.com`.
- **Delete `VITE_ORA_API_TOKEN`.** The new build never reads it.
- Redeploy the matching branch.

Open the web app and enter the owner key. That key is exchanged over HTTPS for a short-lived opaque session. The key itself is not retained. The temporary session, cached workspace and drafts use tab-scoped browser session storage; avoid public/shared browsers and disconnect when finished.

Add a task, refresh, and check that it survives. Ask ORA for a reminder; approve the proposal. The task must appear exactly once.

## 5. Android APK

The repository contains an Expo build profile, not a signed APK. Use your existing Expo project and signing credentials; do not create a second application package unnecessarily.

```bash
cd mobile/ora-android-companion
pnpm install --frozen-lockfile
npx eas-cli login
npx eas-cli build:configure
npx eas-cli build --platform android --profile preview
```

The preview profile builds an installable APK. Set `EXPO_PUBLIC_API_URL` in your EAS build environment for the default backend address, or enter it on the pairing screen. Set the actual EAS project ID when linking your project. No owner key or AI key belongs in `EXPO_PUBLIC_*` variables.

Install the APK. Open web **Connections → Generate pairing code**, then enter the backend URL and one-time code on Android. The code lasts 10 minutes. Device sessions last up to 90 days and can be revoked from the web.

Enable **Schedule on this phone** and test a reminder a few minutes ahead. Android notification/battery policies may affect exact delivery; this is a personal reminder app, not an alarm-clock guarantee. Opening an existing scheduled reminder does not require the server, but syncing a new web reminder does.

For notification awareness: choose apps, enable Android notification access, return to ORA, then enable the selected apps. A new standalone APK is required after changes to native modules. Starting Metro alone does not update Kotlin code in an installed app.

## 6. Final device acceptance

- Pair once; attempting to reuse the code must fail.
- Create a web task; open phone and observe it. Complete it on phone; refresh web.
- Enable a local reminder, close ORA and allow Render to sleep; verify delivery on the physical phone.
- Test microphone denial, transcript review, playback and voice selection.
- Test a selected notification source and a non-selected source; only the former should enter ORA.
- Turn on global pause; no new phone context may be accepted. Resume requires deliberately enabling the listener again.
- Revoke the phone from web; its next synchronization must clear credentials and local schedules. Revocation cannot reach an offline phone immediately; stop locally if needed.
- Disconnect/reconnect, airplane mode, reconnect and conflicting task edits.

## Rollback

Point Render and Vercel back at the original branch/commit and restore the old runtime commands/configuration. Mini's Postgres tables are separate and preserved. Old app credentials and API contracts do not automatically migrate to Mini. Never overwrite the original database with the new development SQLite file.

References: [Render Free](https://render.com/docs/free), [Supabase Postgres connections](https://supabase.com/docs/guides/database/connecting-to-postgres), [Expo notifications](https://docs.expo.dev/versions/v56.0.0/sdk/notifications/), [Expo speech](https://docs.expo.dev/versions/v56.0.0/sdk/speech/).
