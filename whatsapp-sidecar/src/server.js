'use strict';

const fs = require('fs');
const path = require('path');
const {
  loadConfig,
  validateConfig,
  restoreSession,
  writeSessionFiles,
  hasLocalSession,
} = require('./config');
const { SessionSync, restoreFromBackend, enabled: sessionSyncEnabled } = require('./session');
const { MessageStore } = require('./store');
const { WhatsAppAdapter } = require('./wa');
const { createApp } = require('./app');

let qrcode = null;
try {
  qrcode = require('qrcode');
} catch {
  qrcode = null;
}

/**
 * Make a linked device survive a sleep.
 *
 * Order of preference: an explicit WA_SESSION_B64 override, then whatever is
 * already on disk (a persistent disk deployment), then the copy the backend
 * saved in its database. Only when all three are empty does the bridge wait for
 * a QR pairing.
 */
async function restoreLinkedSession(config) {
  try {
    if (restoreSession(config)) {
      console.warn('[startup] restored auth state from WA_SESSION_B64');
      return true;
    }
  } catch (error) {
    console.error(`[startup] WA_SESSION_B64 ignored (${error?.message || 'invalid'})`);
  }
  if (hasLocalSession(config)) {
    console.warn('[startup] using the auth state already on disk');
    return true;
  }
  if (!sessionSyncEnabled(config)) return false;
  const b64 = await restoreFromBackend(config, { logger: console });
  if (!b64) return false;
  try {
    writeSessionFiles(config, b64);
    console.warn('[startup] restored the linked session from the ORA backend');
    return true;
  } catch (error) {
    console.error(`[startup] stored session ignored (${error?.message || 'invalid'})`);
    return false;
  }
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
    // working directory and rely on the stored session for continuity.
    console.error(`[startup] auth dir ${config.authDir} unusable (${error?.code || 'error'}); using ./auth_state`);
    config.authDir = path.join(process.cwd(), 'auth_state');
    fs.mkdirSync(config.authDir, { recursive: true });
  }

  await restoreLinkedSession(config);

  const store = new MessageStore({ max: config.maxMessages });
  const sessionSync = new SessionSync({ config, logger: console });
  const wa = new WhatsAppAdapter({ config, store, onCreds: () => sessionSync.markDirty() });
  sessionSync.adapter = wa;
  sessionSync.start();
  const app = createApp({ wa, config, qrcode });

  app.listen(config.port, '0.0.0.0', () => {
    console.log(`[startup] ora-whatsapp bridge listening on 0.0.0.0:${config.port}`);
    console.log(`[startup] pairing page: /qr?secret=<WA_API_SECRET>`);
  });

  try {
    await wa.start();
  } catch (error) {
    console.error(`[startup] socket start failed: ${error?.name || 'error'}`);
  }

  let closing = false;
  const shutdown = async () => {
    if (closing) return;
    closing = true;
    sessionSync.stop();
    wa.stop();
    // One last best-effort save so a fresh rotation is not lost on redeploy.
    await Promise.race([
      sessionSync.flush().catch(() => {}),
      new Promise((resolve) => setTimeout(resolve, 3000)),
    ]);
    process.exit(0);
  };
  process.on('SIGTERM', shutdown);
  process.on('SIGINT', shutdown);
}

main().catch((error) => {
  console.error(`[startup] fatal: ${error?.message || error}`);
  process.exit(1);
});
