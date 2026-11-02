'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { MessageStore, normalizeBody, phoneFromJid } = require('../src/store');

function message(overrides = {}) {
  return {
    id: overrides.id || 'MSG1',
    key: { remoteJid: '254712345678@s.whatsapp.net', id: overrides.id || 'MSG1' },
    remoteJid: '254712345678@s.whatsapp.net',
    fromMe: false,
    fromName: 'Alice',
    body: 'hello there',
    timestamp: '2026-11-02T09:00:00.000Z',
    isGroup: false,
    groupName: null,
    read: false,
    ...overrides,
  };
}

test('normalizeBody unwraps common message envelopes', () => {
  assert.equal(normalizeBody({ conversation: 'hi' }), 'hi');
  assert.equal(normalizeBody({ extendedTextMessage: { text: 'long text' } }), 'long text');
  assert.equal(normalizeBody({ imageMessage: { caption: 'look' } }), 'look');
  assert.equal(normalizeBody({ imageMessage: {} }), '[image]');
  assert.equal(normalizeBody({ ephemeralMessage: { message: { conversation: 'once' } } }), 'once');
  assert.equal(normalizeBody(null), '');
  assert.equal(normalizeBody({ protocolMessage: {} }), '');
});

test('phoneFromJid strips device suffixes', () => {
  assert.equal(phoneFromJid('254712345678:12@s.whatsapp.net'), '254712345678');
  assert.equal(phoneFromJid('1203630@g.us'), '1203630');
});

test('messages are deduplicated and capped', () => {
  const store = new MessageStore({ max: 20 });
  assert.equal(store.add(message()), true);
  assert.equal(store.add(message()), false);
  for (let i = 2; i <= 40; i += 1) store.add(message({ id: `M${i}`, body: `msg ${i}` }));
  assert.equal(store.messages.length, 20);
  assert.equal(store.messages.at(-1).id, 'M40');
});

test('list filters by unread, contact, search and dms only', () => {
  const store = new MessageStore();
  store.add(message({ id: 'A', body: 'rent due' }));
  store.add(message({ id: 'B', body: 'group chatter', isGroup: true, groupName: 'Fam',
    remoteJid: '120@g.us', fromName: 'Bob' }));
  store.add(message({ id: 'C', body: 'mine', fromMe: true, fromName: 'You',
    remoteJid: '254799999999@s.whatsapp.net' }));

  assert.equal(store.list({ unreadOnly: true }).length, 2);
  assert.equal(store.list({ dmsOnly: true }).length, 2);
  assert.equal(store.list({ search: 'rent' }).length, 1);
  assert.equal(store.list({ contact: 'Alice' }).length, 1);
  assert.equal(store.list({ contact: '254712345678' }).length, 1);
  assert.equal(store.list({ limit: 1 }).length, 1);
});

test('markRead updates unread summary counts', () => {
  const store = new MessageStore();
  store.add(message({ id: 'A' }));
  store.add(message({ id: 'B', id: 'B' }));
  let summary = store.unreadSummary();
  assert.equal(summary.total, 2);
  assert.equal(summary.summary[0].name, 'Alice');
  assert.equal(summary.summary[0].type, 'dm');

  const result = store.markRead(['A', 'B']);
  assert.equal(result.updated, 2);
  summary = store.unreadSummary();
  assert.equal(summary.total, 0);
});

test('unread summary groups conversations and labels groups', () => {
  const store = new MessageStore();
  store.add(message({ id: 'G1', remoteJid: '120@g.us', isGroup: true, groupName: 'Fam', body: 'first' }));
  store.add(message({ id: 'G2', remoteJid: '120@g.us', isGroup: true, groupName: 'Fam', body: 'second' }));
  const summary = store.unreadSummary();
  assert.equal(summary.total, 2);
  assert.equal(summary.summary[0].type, 'group');
  assert.equal(summary.summary[0].count, 2);
  assert.equal(summary.summary[0].latest, 'second');
});

test('contacts resolve exactly and then fuzzily', () => {
  const store = new MessageStore();
  store.upsertContacts([{ id: '254700111222@s.whatsapp.net', name: 'Mum' }]);
  assert.equal(store.resolveContact('mum'), '254700111222');
  assert.equal(store.resolveContact('MU'), '254700111222');
  assert.equal(store.resolveContact('nobody'), null);
  assert.deepEqual(store.contacts(), [{ name: 'Mum', phone: '254700111222' }]);
});

test('groups cache ignores non-group jids', () => {
  const store = new MessageStore();
  store.upsertGroups([
    { id: '120@g.us', subject: 'Team' },
    { id: '254712345678@s.whatsapp.net', subject: 'Not a group' },
  ]);
  assert.deepEqual(store.groups(), [{ name: 'Team', jid: '120@g.us' }]);
});
