# ORA

ORA is a personal assistant built around a React client and a FastAPI service. The current product intentionally focuses on a smaller, dependable core: chat, tasks, goals, memory, knowledge documents, Gmail/Calendar/Drive integration, alerts, proactive checks, weather, and M-Pesa ingestion.

## Runtime model

The backend has one supported entry point:

```bash
cd backend
uvicorn api:app --host 0.0.0.0 --port 8000
```

The frontend is a Vite application:

```bash
cd frontend
npm install
npm run dev
```

The legacy deployment definition in `render.yaml` starts the backend with `uvicorn api:app` and serves the Vite build as a static site. The recommended production layout keeps the frontend on Vercel and runs the backend from `Dockerfile` with `docker-compose.prod.yml`, using a persistent `ora-data` volume.

For a zero-monthly-cost cloud deployment, see [`deploy/oci/README.md`](deploy/oci/README.md) for the Oracle Cloud Always Free workflow. The root [`Dockerfile`](Dockerfile) and [`docker-compose.prod.yml`](docker-compose.prod.yml) are also portable to a VPS or managed container platform.

## Environment configuration

Copy `backend/.env.example` to `backend/.env` for local development and fill in the credentials required by the integrations you intend to use. Real credentials must never be committed.

For production, configure these values in the hosting dashboard:

| Variable | Purpose |
|---|---|
| `ORA_API_TOKEN` | Protects application API routes with the `X-ORA-Token` header. |
| `CORS_ORIGINS` | Comma-separated list of allowed browser origins. |
| `APP_ENV=production` | Makes missing API authentication fail closed and disables interactive API documentation. |
| `VITE_API_URL` | Public URL of the ORA backend. |
| `VITE_ORA_API_TOKEN` | Token used by the single-user static frontend. |
| `ORA_INTERNAL_TOKEN` | Separate token for the WhatsApp sidecar webhook. |

Health and OAuth handshake routes remain public. The WhatsApp incoming endpoint has its own internal token check and fails closed if `ORA_INTERNAL_TOKEN` is missing.

## Supported frontend pages

The active navigation is intentionally limited to Dashboard, Chat, Inbox, Tasks, Alerts, Knowledge, and Memory. Code Agent, Content Studio, Research, News, voice transcription, and the old Agent Bus panel were removed from the active build because their backend implementations were not present in the deployed API.

## Validation

Run the following checks before pushing changes:

```bash
python3 -m compileall -q backend scheduler brain
npm --prefix frontend run lint
npm --prefix frontend run build
```

The repository ignores environment files, generated SQLite/Chroma data, Python caches, frontend dependencies, and build output. The local copies of previously tracked runtime artifacts are preserved on disk but are no longer part of the source tree. Use `.env.production.example` for the backend host and `frontend/.env.example` for Vercel.

## Autonomous core (phases 1–4)

The current architecture uses Vercel for the React frontend and Render for the FastAPI backend. The Render manifest now contains only the backend service, while the frontend is expected to use `VITE_API_URL` and `VITE_ORA_API_TOKEN` in Vercel. The backend health response includes an `ORA_RELEASE` marker so deployment drift can be identified quickly.

The autonomous core is centered on a structured personal context snapshot. `GET /api/context` aggregates profile, preferences, memory, alerts, tasks, goals, Google Calendar/Gmail data, weather, spending, and predictions with freshness and source metadata. Chat, Telegram, the dashboard, and the agent use the same context service rather than maintaining separate connector snapshots.

ORA now includes a durable action ledger. Actions have a type, risk, source, payload, idempotency key, lifecycle status, and optional result or error. Read-only and personal-notification actions can proceed automatically; external communication, irreversible, and financial actions are automatically marked as requiring approval. The API supports listing, creating, approving, rejecting, and cancelling actions through `/api/actions`.

Tasks may be linked to goals with `goal_id`. The Tasks interface lets you select an active goal when creating a task, goals expose their next pending action, and completing a linked task automatically recalculates goal progress. The dashboard surfaces ORA’s current state, focus, and pending approval queue.

The active supported frontend pages are Dashboard, Chat, Inbox, Tasks, Alerts, Knowledge, and Memory. Research, News, Content, Code, and Agent Bus are intentionally not part of the active product surface because their former endpoints were unsupported or stale.
