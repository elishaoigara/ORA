# ORA on Render Free: ONE container, TWO processes.
#
# Render Free gives the whole workspace 750 instance hours and a single 512 MB
# instance. A WhatsApp bridge needs a live socket, so as a second free service it
# would spend ~730 h on its own and suspend the backend before the month ends.
# Running it as a supervised child of the API keeps the bill at one service:
# WhatsApp is available whenever ORA is awake, and the linked-device credentials
# live in Postgres, so sleep costs a reconnect instead of a new QR pairing.
#
# See docs/RENDER_FREE_BUDGET.md and docs/WHATSAPP_SETUP.md.

# ── WhatsApp bridge (Node + Baileys) ─────────────────────────────────────────
FROM node:22-bookworm-slim AS bridge
WORKDIR /bridge
COPY whatsapp-sidecar/package.json whatsapp-sidecar/package-lock.json ./
RUN npm ci --omit=dev --no-audit --no-fund
COPY whatsapp-sidecar/src ./src

# ── ORA API (Python) ─────────────────────────────────────────────────────────
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8000 APP_ENV=production

# The Node binary from the stage above links against libstdc++6; both images are
# Debian bookworm, so copying the binary is enough (no second Node install).
RUN apt-get update \
 && apt-get install -y --no-install-recommends libstdc++6 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=node:22-bookworm-slim /usr/local/bin/node /usr/local/bin/node
COPY --from=bridge /bridge /app/whatsapp-sidecar

COPY backend/requirements-mini.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./
RUN mkdir -p /tmp/wa-auth

EXPOSE 8000
CMD ["sh", "-c", "uvicorn next_api:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --limit-concurrency 32 --timeout-keep-alive 5"]
