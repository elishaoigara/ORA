'use strict';

const fs = require('fs');
const path = require('path');

const DEFAULT_SECRET = 'ora-wa-secret-change-me';

function clean(value) {
  return String(value || '').trim();
}

function loadConfig(env = process.env) {
  const apiSecret = clean(env.WA_API_SECRET);
  return {
    port: Number.parseInt(env.PORT || '8080', 10),
    apiSecret,
    authDir: clean(env.WA_AUTH_DIR) || path.join(process.cwd(), 'auth_state'),
    maxMessages: Number.parseInt(env.WA_MAX_MESSAGES || '500', 10),
    // Where to POST inbound messages (ORA backend). Both must be set to enable.
    backendUrl: clean(env.ORA_BACKEND_URL).replace(/\/+$/, ''),
    internalToken: clean(env.ORA_INTERNAL_TOKEN),
    // Optional base64 auth-state backup so a redeploy on an ephemeral disk can resume
    // without re-pairing. Produced by GET /session/export.
    sessionB64: clean(env.WA_SESSION_B64),
    pairNumber: clean(env.WA_PAIR_NUMBER).replace(/\D/g, ''),
    logLevel: clean(env.WA_LOG_LEVEL) || 'warn',
  };
}

/**
 * Fail closed: the sidecar moves private messages, so it refuses to boot with a
 * missing or well-known shared secret.
 */
function validateConfig(config) {
  if (!config.apiSecret) return 'WA_API_SECRET is required';
  if (config.apiSecret === DEFAULT_SECRET) return 'WA_API_SECRET still uses the public default';
  if (config.apiSecret.length < 12) return 'WA_API_SECRET must be at least 12 characters';
  if (!Number.isFinite(config.port) || config.port <= 0) return 'PORT is invalid';
  if (config.backendUrl && !config.internalToken) return 'ORA_INTERNAL_TOKEN is required when ORA_BACKEND_URL is set';
  return null;
}

/** Restore a base64 auth-state backup into the auth directory (no-op when empty). */
function restoreSession(config) {
  if (!config.sessionB64) return false;
  const files = JSON.parse(Buffer.from(config.sessionB64, 'base64').toString('utf8'));
  if (!files || typeof files !== 'object') throw new Error('WA_SESSION_B64 is not a valid session backup');
  fs.mkdirSync(config.authDir, { recursive: true });
  for (const [name, contents] of Object.entries(files)) {
    if (!/^[A-Za-z0-9._-]+$/.test(name)) continue;
    fs.writeFileSync(path.join(config.authDir, name), String(contents));
  }
  return true;
}

module.exports = { loadConfig, validateConfig, restoreSession, DEFAULT_SECRET };
