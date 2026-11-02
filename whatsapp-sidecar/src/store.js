'use strict';

/**
 * In-memory message ring buffer plus contact/group caches.
 *
 * The sidecar is deliberately stateless across restarts: WhatsApp does not expose
 * historical messages, so anything older than the current process (or the last
 * `max` messages) is simply not listed. Nothing here is written to disk.
 */

function normalizeBody(message) {
  if (!message || typeof message !== 'object') return '';
  const unwrapped = message.ephemeralMessage?.message
    || message.viewOnceMessage?.message
    || message.viewOnceMessageV2?.message
    || message.documentWithCaptionMessage?.message
    || message;
  return unwrapped.conversation
    || unwrapped.extendedTextMessage?.text
    || unwrapped.imageMessage?.caption
    || unwrapped.videoMessage?.caption
    || unwrapped.documentMessage?.caption
    || (unwrapped.imageMessage ? '[image]' : '')
    || (unwrapped.videoMessage ? '[video]' : '')
    || (unwrapped.audioMessage ? '[voice note]' : '')
    || (unwrapped.stickerMessage ? '[sticker]' : '')
    || (unwrapped.documentMessage ? '[document]' : '')
    || (unwrapped.locationMessage ? '[location]' : '')
    || (unwrapped.contactMessage ? '[contact]' : '')
    || '';
}

function phoneFromJid(jid) {
  return String(jid || '').split('@')[0].split(':')[0].replace(/\D/g, '');
}

class MessageStore {
  constructor({ max = 500 } = {}) {
    this.max = Math.max(20, Number(max) || 500);
    this.messages = [];
    this.readIds = new Set();
    this.contactsByJid = new Map();
    this.groupsByJid = new Map();
  }

  add(message) {
    if (!message || !message.id) return false;
    if (this.messages.some((m) => m.id === message.id)) return false;
    this.messages.push(message);
    if (this.messages.length > this.max) {
      const drop = this.messages.length - this.max;
      this.messages.splice(0, drop);
    }
    if (message.fromName) this.rememberContact(message.remoteJid, message.fromName);
    return true;
  }

  conversationKey(message) {
    return message.isGroup ? message.remoteJid : message.remoteJid;
  }

  rememberContact(jid, name) {
    const phone = phoneFromJid(jid);
    if (!phone || !name) return;
    this.contactsByJid.set(`${phone}@s.whatsapp.net`, { name: String(name), phone });
  }

  upsertContacts(contacts) {
    for (const c of contacts || []) {
      if (!c || !c.id) continue;
      if (String(c.id).endsWith('@g.us')) continue;
      const phone = phoneFromJid(c.id);
      if (!phone) continue;
      const name = c.name || c.notify || c.verifiedName || '';
      if (!name) continue;
      this.contactsByJid.set(c.id, { name: String(name), phone });
    }
  }

  upsertGroups(groups) {
    for (const g of groups || []) {
      if (!g) continue;
      const jid = g.id || g.jid;
      if (!jid || !String(jid).endsWith('@g.us')) continue;
      this.groupsByJid.set(jid, { name: String(g.subject || g.name || jid), jid });
    }
  }

  contacts() {
    return [...this.contactsByJid.values()].sort((a, b) => a.name.localeCompare(b.name));
  }

  groups() {
    return [...this.groupsByJid.values()].sort((a, b) => a.name.localeCompare(b.name));
  }

  resolveContact(name) {
    const needle = String(name || '').trim().toLowerCase();
    if (!needle) return null;
    const all = this.contacts();
    const exact = all.find((c) => c.name.toLowerCase() === needle);
    if (exact) return exact.phone;
    const partial = all.find((c) => c.name.toLowerCase().includes(needle));
    return partial ? partial.phone : null;
  }

  isRead(message) {
    return Boolean(message.read) || this.readIds.has(message.id);
  }

  list({ limit = 20, contact = '', unreadOnly = false, search = '', dmsOnly = false } = {}) {
    const contactNeedle = String(contact || '').trim().toLowerCase();
    const contactDigits = contactNeedle.replace(/\D/g, '');
    const searchNeedle = String(search || '').trim().toLowerCase();
    const out = [];
    for (let i = this.messages.length - 1; i >= 0 && out.length < limit; i -= 1) {
      const m = this.messages[i];
      if (dmsOnly && m.isGroup) continue;
      if (unreadOnly && (m.fromMe || this.isRead(m))) continue;
      if (contactNeedle) {
        const name = (m.fromName || m.groupName || '').toLowerCase();
        const phone = phoneFromJid(m.remoteJid);
        const phoneHit = Boolean(contactDigits) && phone.includes(contactDigits);
        if (!name.includes(contactNeedle) && !phoneHit) continue;
      }
      if (searchNeedle && !`${m.body} ${m.fromName || ''}`.toLowerCase().includes(searchNeedle)) continue;
      out.push(this.toPublic(m));
    }
    return out;
  }

  toPublic(message) {
    return {
      id: message.id,
      from: phoneFromJid(message.remoteJid) || message.remoteJid,
      fromName: message.fromMe ? 'You' : message.fromName || message.groupName || phoneFromJid(message.remoteJid),
      body: message.body,
      timestamp: message.timestamp,
      isGroup: message.isGroup,
      groupName: message.groupName || null,
      read: this.isRead(message),
      fromMe: message.fromMe,
    };
  }

  markRead(ids) {
    const wanted = new Set(ids || []);
    let updated = 0;
    const keys = [];
    for (const m of this.messages) {
      if (!wanted.has(m.id)) continue;
      this.readIds.add(m.id);
      updated += 1;
      keys.push(m.key);
    }
    return { updated, keys };
  }

  unreadSummary() {
    const buckets = new Map();
    for (const m of this.messages) {
      if (m.fromMe || this.isRead(m)) continue;
      const key = this.conversationKey(m);
      const entry = buckets.get(key) || {
        name: m.isGroup ? m.groupName || key : m.fromName || phoneFromJid(m.remoteJid),
        type: m.isGroup ? 'group' : 'dm',
        count: 0,
        latest: '',
      };
      entry.count += 1;
      entry.latest = m.body;
      buckets.set(key, entry);
    }
    const summary = [...buckets.values()].sort((a, b) => b.count - a.count);
    return { total: summary.reduce((sum, item) => sum + item.count, 0), summary };
  }
}

module.exports = { MessageStore, normalizeBody, phoneFromJid };
