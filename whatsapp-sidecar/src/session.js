'use strict';

/**
 * Session continuity for a service that sleeps.
 *
 * Render Free stops an idle instance after 15 minutes, and its container
 * filesystem goes with it. A linked WhatsApp device therefore cannot depend on
 * `auth_state/`: after the first nap the bridge would come back with no
 * credentials and demand a new QR scan from the owner's phone.
 *
 * So the backend owns the copy. The bridge restores the credential bundle from
 * Postgres on boot and pushes it back whenever WhatsApp rotates keys. Pairing
 * happens once; waking up is free.
 *
 * The bundle is only ever exchanged with the backend over loopback (or the
 * backend's own URL) using ORA_INTERNAL_TOKEN, and it is never logged.
 */

const SESSION_PATH = '/api/whatsapp/session';
const PUSH_DEBOUNCE_MS = 3000;
const PUSH_MIN_INTERVAL_MS = 15000;
const PERIODIC_FLUSH_MS = 2 * 60 * 1000;
const RESTORE_ATTEMPTS = 10;
const RESTORE_DELAY_MS = 2000;

function baseUrl(config) {
  return String(config?.backendUrl || '').replace(/\/+$/, '');
}

function enabled(config) {
  return Boolean(config && config.sessionSync !== false && baseUrl(config) && config.internalToken);
}

/**
 * Fetch the saved bundle, or null when the backend has none.
 * A 404 means "never paired" and returns immediately; transport errors (the
 * backend may still be booting) throw so the caller can retry.
 */
async function fetchSession(config, { fetchImpl = fetch, timeoutMs = 8000 } = {}) {
  if (!enabled(config)) return null;
  const res = await fetchImpl(`${baseUrl(config)}${SESSION_PATH}`, {
    headers: { 'X-ORA-Token': config.internalToken },
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`session fetch failed (${res.status})`);
  const body = await res.json().catch(() => null);
  return typeof body?.b64 === 'string' && body.b64 ? body.b64 : null;
}

async function putSession(config, b64, { fetchImpl = fetch, timeoutMs = 15000 } = {}) {
  const res = await fetchImpl(`${baseUrl(config)}${SESSION_PATH}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', 'X-ORA-Token': config.internalToken },
    body: JSON.stringify({ b64 }),
    signal: AbortSignal.timeout(timeoutMs),
  });
  return res.ok;
}

/** Restore helper used at boot: retries only while the backend is unreachable. */
async function restoreFromBackend(config, { attempts = RESTORE_ATTEMPTS, delayMs = RESTORE_DELAY_MS,
  fetchImpl = fetch, logger = console } = {}) {
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      return await fetchSession(config, { fetchImpl });
    } catch (error) {
      if (attempt === attempts) {
        logger.warn?.(`[session] restore gave up: ${error?.name || 'error'}`);
        return null;
      }
      logger.warn?.(`[session] restore attempt ${attempt}/${attempts}: ${error?.name || 'error'}`);
      await new Promise((resolve) => setTimeout(resolve, delayMs));
    }
  }
  return null;
}

/**
 * Pushes credential changes upstream. Debounced, rate-limited and never
 * overlapping: a free instance should not spend its wake-up on database writes.
 */
class SessionSync {
  constructor({ config, adapter = null, logger = console }) {
    this.config = config;
    this.adapter = adapter;
    this.logger = logger;
    this.dirty = false;
    this.inflight = false;
    this.lastPush = 0;
    this.debounce = null;
    this.interval = null;
  }

  start() {
    if (!enabled(this.config) || this.interval) return this;
    this.interval = setInterval(() => {
      this.flush().catch(() => {});
    }, PERIODIC_FLUSH_MS);
    this.interval.unref?.();
    return this;
  }

  stop() {
    clearTimeout(this.debounce);
    clearInterval(this.interval);
    this.debounce = null;
    this.interval = null;
  }

  markDirty() {
    if (!enabled(this.config)) return;
    this.dirty = true;
    clearTimeout(this.debounce);
    this.debounce = setTimeout(() => {
      this.flush().catch(() => {});
    }, PUSH_DEBOUNCE_MS);
    this.debounce.unref?.();
  }

  async flush() {
    if (!enabled(this.config) || this.inflight || !this.adapter) return false;
    if (!this.dirty && Date.now() - this.lastPush < PERIODIC_FLUSH_MS) return false;
    if (Date.now() - this.lastPush < PUSH_MIN_INTERVAL_MS) return false;
    this.inflight = true;
    try {
      const b64 = await this.adapter.sessionBackup();
      if (!b64) return false;
      if (!(await putSession(this.config, b64))) return false;
      this.dirty = false;
      this.lastPush = Date.now();
      return true;
    } catch (error) {
      // Credentials are sensitive: log the error class only, never the payload.
      this.logger.warn?.(`[session] backup failed: ${error?.name || 'error'}`);
      return false;
    } finally {
      this.inflight = false;
    }
  }
}

module.exports = {
  SessionSync,
  enabled,
  fetchSession,
  putSession,
  restoreFromBackend,
  SESSION_PATH,
};
