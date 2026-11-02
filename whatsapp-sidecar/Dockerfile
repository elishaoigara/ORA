FROM node:22-slim

ENV NODE_ENV=production \
    PORT=8080 \
    WA_AUTH_DIR=/data

WORKDIR /app

# Dependencies first so rebuilds only reinstall when the lockfile changes.
COPY package.json package-lock.json ./
RUN npm ci --omit=dev && npm cache clean --force

COPY src ./src

# Pairing credentials live here. Without a persistent disk the session must be
# restored from WA_SESSION_B64 (see docs/WHATSAPP_SETUP.md) after a redeploy.
RUN mkdir -p /data
VOLUME ["/data"]

EXPOSE 8080
CMD ["node", "src/server.js"]
