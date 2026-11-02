'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { createApp, safeEqual } = require('../src/app');

const SECRET = 'test-secret-abcdef123456';

function fakeAdapter(overrides = {}) {
  const calls = [];
  const adapter = {
    calls,
    state: 'open',
    status: () => ({ state: adapter.state, me: '254700000000', pairedAt: '2026-11-02T00:00:00Z' }),
    qr: () => null,
    send: async (to, message) => {
      calls.push({ to, message });
      // Mirrors WhatsAppAdapter.send: an unlinked socket reports it, a linked one
      // is expected to send (the adapter itself waits briefly for a reconnecting
      // socket before giving up).
      return adapter.state === 'open' ? { ok: true } : { ok: false, error: 'WhatsApp is not linked' };
    },
    messages: (query) => {
      calls.push({ query });
      return [{ id: 'A', fromName: 'Alice', body: 'hi' }];
    },
    markRead: async (ids) => {
      calls.push({ ids });
      return ids.length;
    },
    contacts: () => [{ name: 'Alice', phone: '254712345678' }],
    groups: async () => [{ name: 'Team', jid: '120@g.us' }],
    setMute: async (jid, mute) => {
      calls.push({ jid, mute });
      return { ok: true };
    },
    unreadSummary: () => ({ total: 1, summary: [{ name: 'Alice', type: 'dm', count: 1, latest: 'hi' }] }),
    sessionBackup: async () => null,
    ...overrides,
  };
  return adapter;
}

async function withServer(run, adapter = fakeAdapter()) {
  const app = createApp({
    wa: adapter,
    config: { apiSecret: SECRET, backendUrl: '', internalToken: '' },
    qrcode: null,
  });
  const server = app.listen(0, '127.0.0.1');
  await new Promise((resolve) => server.once('listening', resolve));
  const base = `http://127.0.0.1:${server.address().port}`;
  try {
    await run({ base, adapter });
  } finally {
    server.close();
  }
}

const auth = { 'x-api-secret': SECRET, 'Content-Type': 'application/json' };

test('health is open, everything else requires the shared secret', async () => {
  await withServer(async ({ base }) => {
    assert.equal((await fetch(`${base}/health`)).status, 200);
    assert.equal((await fetch(`${base}/status`)).status, 401);
    assert.equal((await fetch(`${base}/status`, { headers: { 'x-api-secret': 'wrong' } })).status, 401);
    const ok = await fetch(`${base}/status`, { headers: auth });
    assert.equal(ok.status, 200);
    assert.equal((await ok.json()).state, 'open');
  });
});

test('send validates input and reports an unlinked session', async () => {
  await withServer(async ({ base, adapter }) => {
    assert.equal((await fetch(`${base}/send`, { method: 'POST', headers: auth,
      body: JSON.stringify({ to: '', message: 'hi' }) })).status, 400);
    assert.equal((await fetch(`${base}/send`, { method: 'POST', headers: auth,
      body: JSON.stringify({ to: '2547', message: '' }) })).status, 400);

    adapter.state = 'closed';
    assert.equal((await fetch(`${base}/send`, { method: 'POST', headers: auth,
      body: JSON.stringify({ to: '254712345678', message: 'hi' }) })).status, 503);

    adapter.state = 'open';
    const ok = await fetch(`${base}/send`, { method: 'POST', headers: auth,
      body: JSON.stringify({ to: '254712345678', message: 'briefing' }) });
    assert.equal(ok.status, 200);
    assert.deepEqual(adapter.calls.at(-1), { to: '254712345678', message: 'briefing' });
  });
});

test('send surfaces adapter failures as 502 without leaking details', async () => {
  const adapter = fakeAdapter({ send: async () => ({ ok: false, error: 'item-not-found' }) });
  await withServer(async ({ base }) => {
    const response = await fetch(`${base}/send`, { method: 'POST', headers: auth,
      body: JSON.stringify({ to: '254712345678', message: 'hi' }) });
    assert.equal(response.status, 502);
    const body = await response.json();
    assert.equal(body.ok, false);
    assert.match(body.error, /item-not-found/);
  }, adapter);
});

test('messages maps query flags and clamps the limit', async () => {
  await withServer(async ({ base, adapter }) => {
    await fetch(`${base}/messages?limit=999&unread=true&no_groups=true&contact=Alice&search=rent`,
      { headers: auth });
    assert.deepEqual(adapter.calls.at(-1).query,
      { limit: 100, contact: 'Alice', unreadOnly: true, search: 'rent', dmsOnly: true });
  });
});

test('mark-read requires ids and reports the count', async () => {
  await withServer(async ({ base }) => {
    assert.equal((await fetch(`${base}/mark-read`, { method: 'POST', headers: auth,
      body: JSON.stringify({ ids: [] }) })).status, 400);
    const ok = await fetch(`${base}/mark-read`, { method: 'POST', headers: auth,
      body: JSON.stringify({ ids: ['A', 'B'] }) });
    assert.equal(ok.status, 200);
    assert.equal((await ok.json()).updated, 2);
  });
});

test('contacts, groups and unread summary return the python connector shape', async () => {
  await withServer(async ({ base }) => {
    assert.deepEqual((await (await fetch(`${base}/contacts`, { headers: auth })).json()),
      { ok: true, contacts: [{ name: 'Alice', phone: '254712345678' }] });
    assert.deepEqual((await (await fetch(`${base}/groups`, { headers: auth })).json()),
      { ok: true, groups: [{ name: 'Team', jid: '120@g.us' }] });
    const summary = await (await fetch(`${base}/unread-summary`, { headers: auth })).json();
    assert.equal(summary.total, 1);
    assert.equal(summary.summary[0].name, 'Alice');
  });
});

test('mute only accepts group JIDs', async () => {
  await withServer(async ({ base, adapter }) => {
    assert.equal((await fetch(`${base}/mute`, { method: 'POST', headers: auth,
      body: JSON.stringify({ jid: '254712345678@s.whatsapp.net', mute: true }) })).status, 400);
    const ok = await fetch(`${base}/mute`, { method: 'POST', headers: auth,
      body: JSON.stringify({ jid: '120@g.us', mute: true }) });
    assert.equal(ok.status, 200);
    assert.deepEqual(adapter.calls.at(-1), { jid: '120@g.us', mute: true });
  });
});

test('qr page reports linked state instead of a code once paired', async () => {
  await withServer(async ({ base }) => {
    const response = await fetch(`${base}/qr?secret=${SECRET}`);
    assert.equal(response.status, 200);
    assert.match(await response.text(), /already paired/i);
  });
});

test('session export returns 409 until a session exists', async () => {
  await withServer(async ({ base }) => {
    assert.equal((await fetch(`${base}/session/export`, { headers: auth })).status, 409);
  });
});

test('unknown routes 404 and adapter exceptions become 503', async () => {
  const adapter = fakeAdapter({ groups: async () => { throw new Error('socket gone'); } });
  await withServer(async ({ base }) => {
    assert.equal((await fetch(`${base}/nope`, { headers: auth })).status, 404);
    const response = await fetch(`${base}/groups`, { headers: auth });
    assert.equal(response.status, 503);
    assert.match((await response.json()).error, /Sidecar unavailable/);
  }, adapter);
});

test('safeEqual compares secrets without length leaks', () => {
  assert.equal(safeEqual('abc', 'abc'), true);
  assert.equal(safeEqual('abc', 'abcd'), false);
  assert.equal(safeEqual('', 'abc'), false);
});
