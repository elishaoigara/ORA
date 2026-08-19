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

The deployment definition in `render.yaml` starts the backend with `uvicorn api:app` and serves the Vite build as a static site.

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

The repository ignores environment files, generated SQLite/Chroma data, Python caches, frontend dependencies, and build output. The local copies of previously tracked runtime artifacts are preserved on disk but are no longer part of the source tree.
