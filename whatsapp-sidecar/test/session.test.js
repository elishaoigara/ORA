'use strict';

/**
 * A free instance sleeps; a linked WhatsApp device must not care.
 *
 * These tests pin the contract the backend depends on: the credential bundle is
 * restored from the database on boot, pushed back after a rotation, and never
 * re-sent in a tight loop while the instance is awake.
 */

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');

const {
  SessionSync,
  enabled,
  fetchSession,
  putSession,
  restoreFromBackend,
} = require('../src/session');
const {
  loadConfig,
  restoreSession,
  writeSessionFiles,
  hasLocalSession,
} = require('../src/config');
const { createApp } = require('../src/app');

const TOKEN = 'internal-token-0123456789';
const API_SECRET = 'sidecar-secret-abcdef123456';

function config(overrides = {}) {
  return {
    backendUrl: 'https://ora.test',
    internalToken: TOKEN,
    sessionSync: true,
    apiSecret: API_SECRET,
    authDir: fs.mkdtempSync(path.join(os.tmpdir(), 'ora-wa-')),
    maxMessages: 100,
    ...overrides,
  };
}

function bundle(files) {
  return Buffer.from(JSON.stringify(files), 'utf8').toString('base64');
}

function jsonResponse(body, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}

test('session sync needs both a backend URL and the internal token', () => {
  assert.equal(enabled(config()), true);
  assert.equal(enabled(config({ backendUrl: '' })), false);
  assert.equal(enabled(config({ internalToken: '' })), false);
  assert.equal(enabled(config({ sessionSync: false })), false);
});

test('fetchSession reads the bundle with the internal token', async () => {
  const calls = [];
  const b64 = await fetchSession(config(), {
    fetchImpl: async (url, init) => {
      calls.push({ url, init });
      return jsonResponse({ ok: true, b64: 'bundle-1' });
    },
  });
  assert.equal(b64, 'bundle-1');
  assert.equal(calls[0].url, 'https://ora.test/api/whatsapp/session');
  assert.equal(calls[0].init.headers['X-ORA-Token'], TOKEN);
});

test('a 404 means "never paired", not an error', async () => {
  const b64 = await fetchSession(config(), { fetchImpl: async () => jsonResponse({}, 404) });
  assert.equal(b64, null);
});

test('fetchSession does nothing without a backend', async () => {
  let called = false;
  const b64 = await fetchSession(config({ backendUrl: '' }), {
    fetchImpl: async () => {
      called = true;
      return jsonResponse({ b64: 'x' });
    },
  });
  assert.equal(b64, null);
  assert.equal(called, false);
});

test('restoreFromBackend retries while the backend is still booting', async () => {
  let attempts = 0;
  const b64 = await restoreFromBackend(config(), {
    delayMs: 1,
    logger: { warn() {} },
    fetchImpl: async () => {
      attempts += 1;
      if (attempts < 3) throw new Error('ECONNREFUSED');
      return jsonResponse({ ok: true, b64: 'bundle-2' });
    },
  });
  assert.equal(b64, 'bundle-2');
  assert.equal(attempts, 3);
});

test('restoreFromBackend gives up instead of hanging a cold start', async () => {
  let attempts = 0;
  const b64 = await restoreFromBackend(config(), {
    attempts: 4,
    delayMs: 1,
    logger: { warn() {} },
    fetchImpl: async () => {
      attempts += 1;
      throw new Error('ECONNREFUSED');
    },
  });
  assert.equal(b64, null);
  assert.equal(attempts, 4);
});

test('putSession posts the bundle to the backend', async () => {
  const calls = [];
  const ok = await putSession(config(), 'bundle-3', {
    fetchImpl: async (url, init) => {
      calls.push({ url, init });
      return jsonResponse({ ok: true });
    },
  });
  assert.equal(ok, true);
  assert.equal(calls[0].init.method, 'PUT');
  assert.equal(calls[0].init.headers['X-ORA-Token'], TOKEN);
  assert.deepEqual(JSON.parse(calls[0].init.body), { b64: 'bundle-3' });
});

test('SessionSync pushes a rotation once, then stays quiet', async () => {
  const pushes = [];
  const original = globalThis.fetch;
  globalThis.fetch = async (url, init) => {
    pushes.push(JSON.parse(init.body));
    return jsonResponse({ ok: true });
  };
  const sync = new SessionSync({
    config: config(),
    adapter: { sessionBackup: async () => 'bundle-4' },
    logger: { warn() {} },
  });
  try {
    sync.markDirty();
    assert.equal(await sync.flush(), true);
    assert.deepEqual(pushes, [{ b64: 'bundle-4' }]);
    // Unchanged credentials are not written again.
    assert.equal(await sync.flush(), false);
    assert.equal(pushes.length, 1);
  } finally {
    sync.stop();
    globalThis.fetch = original;
  }
});

test('SessionSync rate-limits pushes while credentials keep rotating', async () => {
  const pushes = [];
  const original = globalThis.fetch;
  globalThis.fetch = async (url, init) => {
    pushes.push(init.body);
    return jsonResponse({ ok: true });
  };
  const sync = new SessionSync({
    config: config(),
    adapter: { sessionBackup: async () => 'bundle-5' },
    logger: { warn() {} },
  });
  try {
    sync.markDirty();
    assert.equal(await sync.flush(), true);
    sync.markDirty();
    assert.equal(await sync.flush(), false); // inside the minimum interval
    assert.equal(pushes.length, 1);
  } finally {
    sync.stop();
    globalThis.fetch = original;
  }
});

test('a backup failure is swallowed, never fatal', async () => {
  const sync = new SessionSync({
    config: config(),
    adapter: { sessionBackup: async () => { throw new Error('disk'); } },
    logger: { warn() {} },
  });
  try {
    sync.markDirty();
    assert.equal(await sync.flush(), false);
  } finally {
    sync.stop();
  }
});

test('writeSessionFiles restores a credential bundle to disk', () => {
  const cfg = config();
  const b64 = bundle({ 'creds.json': '{"registered":true}', 'pre-key-1.json': '{}' });
  assert.equal(writeSessionFiles(cfg, b64), true);
  assert.equal(hasLocalSession(cfg), true);
  assert.equal(fs.readFileSync(path.join(cfg.authDir, 'pre-key-1.json'), 'utf8'), '{}');
});

test('a bundle without credentials is rejected', () => {
  const cfg = config();
  assert.throws(() => writeSessionFiles(cfg, bundle({ 'pre-key-1.json': '{}' })));
  assert.throws(() => writeSessionFiles(cfg, 'not-base64'));
  assert.equal(hasLocalSession(cfg), false);
});

test('restoreSession is a no-op without WA_SESSION_B64', () => {
  const cfg = config({ sessionB64: '' });
  assert.equal(restoreSession(cfg), false);
  assert.equal(hasLocalSession(cfg), false);
});

test('loadConfig can disable session sync and reads the auth dir', () => {
  const cfg = loadConfig({ WA_API_SECRET: API_SECRET, WA_SESSION_SYNC: '0', WA_AUTH_DIR: '/data' });
  assert.equal(cfg.sessionSync, false);
  assert.equal(cfg.authDir, '/data');
  assert.equal(loadConfig({ WA_API_SECRET: API_SECRET }).sessionSync, true);
});

async function withServer(run, adapter) {
  const app = createApp({ wa: adapter, config: { apiSecret: API_SECRET }, qrcode: null });
  const server = app.listen(0, '127.0.0.1');
  await new Promise((resolve) => server.once('listening', resolve));
  const base = `http://127.0.0.1:${server.address().port}`;
  try {
    await run({ base });
  } finally {
    server.close();
  }
}

function fakeAdapter(overrides = {}) {
  return {
    state: 'connecting',
    status: () => ({ state: overrides.state || 'connecting', me: '254700000000' }),
    qr: () => null,
    pairingCode: null,
    ...overrides,
  };
}

test('/qr.json reports state and requires the secret', async () => {
  await withServer(async ({ base }) => {
    assert.equal((await fetch(`${base}/qr.json`)).status, 401);
    const response = await fetch(`${base}/qr.json`, { headers: { 'x-api-secret': API_SECRET } });
    assert.equal(response.status, 200);
    const body = await response.json();
    assert.equal(body.linked, false);
    assert.equal(body.state, 'connecting');
    assert.equal(body.qr, null);
  }, fakeAdapter());
});

test('/qr.json marks a linked device as linked and never returns a code', async () => {
  const adapter = fakeAdapter({ state: 'open', status: () => ({ state: 'open', me: '254700000000' }), qr: () => 'raw-qr' });
  await withServer(async ({ base }) => {
    const body = await (await fetch(`${base}/qr.json`, { headers: { 'x-api-secret': API_SECRET } })).json();
    assert.equal(body.linked, true);
    assert.equal(body.qr, null);
  }, adapter);
});

test('/qr.json forwards a phone-number pairing code', async () => {
  const adapter = fakeAdapter({ pairingCode: 'ABCD-1234' });
  adapter.status = () => ({ state: 'connecting' });
  await withServer(async ({ base }) => {
    const body = await (await fetch(`${base}/qr.json`, { headers: { 'x-api-secret': API_SECRET } })).json();
    assert.equal(body.code, 'ABCD-1234');
    assert.equal(body.linked, false);
  }, adapter);
});
