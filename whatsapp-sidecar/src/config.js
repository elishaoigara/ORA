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
    // When ORA_BACKEND_URL + ORA_INTERNAL_TOKEN are set, the bridge mirrors its
    // credentials into the backend's database and restores them on boot. Set
    // WA_SESSION_SYNC=0 to keep credentials on disk only.
    sessionSync: clean(env.WA_SESSION_SYNC || '1') !== '0',
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

const SESSION_FILE = /^[A-Za-z0-9._-]+\.json$/;

/** Write a base64 auth-state bundle into the auth directory. */
function writeSessionFiles(config, b64) {
  const files = JSON.parse(Buffer.from(String(b64 || ''), 'base64').toString('utf8'));
  if (!files || typeof files !== 'object') throw new Error('session backup is not an object');
  if (!files['creds.json']) throw new Error('session backup has no creds.json');
  fs.mkdirSync(config.authDir, { recursive: true });
  for (const [name, contents] of Object.entries(files)) {
    if (!SESSION_FILE.test(name)) continue;
    fs.writeFileSync(path.join(config.authDir, name), String(contents));
  }
  return true;
}

/** Restore a base64 auth-state backup into the auth directory (no-op when empty). */
function restoreSession(config) {
  if (!config.sessionB64) return false;
  return writeSessionFiles(config, config.sessionB64);
}

/** True when a device link already exists on this disk (persistent disk deployments). */
function hasLocalSession(config) {
  try {
    return fs.existsSync(path.join(config.authDir, 'creds.json'));
  } catch {
    return false;
  }
}

module.exports = {
  loadConfig,
  validateConfig,
  restoreSession,
  writeSessionFiles,
  hasLocalSession,
  DEFAULT_SECRET,
};
