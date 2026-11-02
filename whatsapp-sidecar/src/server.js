'use strict';

const fs = require('fs');
const path = require('path');
const { loadConfig, validateConfig, restoreSession } = require('./config');
const { MessageStore } = require('./store');
const { WhatsAppAdapter } = require('./wa');
const { createApp } = require('./app');

let qrcode = null;
try {
  qrcode = require('qrcode');
} catch {
  qrcode = null;
}

async function main() {
  const config = loadConfig();
  const invalid = validateConfig(config);
  if (invalid) {
    console.error(`[startup] refusing to start: ${invalid}`);
    process.exit(1);
  }
  try {
    fs.mkdirSync(config.authDir, { recursive: true });
  } catch (error) {
    // A read-only or missing mount point must not stop the service: fall back to the
    // working directory and rely on WA_SESSION_B64 for continuity.
    console.error(`[startup] auth dir ${config.authDir} unusable (${error?.code || 'error'}); using ./auth_state`);
    config.authDir = path.join(process.cwd(), 'auth_state');
    fs.mkdirSync(config.authDir, { recursive: true });
  }
  try {
    if (restoreSession(config)) console.warn('[startup] restored auth state from WA_SESSION_B64');
  } catch (error) {
    console.error(`[startup] WA_SESSION_B64 ignored (${error?.message || 'invalid'})`);
  }

  const store = new MessageStore({ max: config.maxMessages });
  const wa = new WhatsAppAdapter({ config, store });
  const app = createApp({ wa, config, qrcode });

  app.listen(config.port, '0.0.0.0', () => {
    console.log(`[startup] ora-whatsapp-sidecar listening on 0.0.0.0:${config.port}`);
    console.log(`[startup] pairing page: /qr?secret=<WA_API_SECRET>`);
  });

  try {
    await wa.start();
  } catch (error) {
    console.error(`[startup] socket start failed: ${error?.name || 'error'}`);
  }

  const shutdown = () => {
    wa.stop();
    process.exit(0);
  };
  process.on('SIGTERM', shutdown);
  process.on('SIGINT', shutdown);
}

main().catch((error) => {
  console.error(`[startup] fatal: ${error?.message || error}`);
  process.exit(1);
});
