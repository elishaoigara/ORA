'use strict';

/**
 * Baileys adapter. All WhatsApp-specific behavior is contained here so the HTTP
 * layer (src/app.js) can be tested against a fake adapter without a live socket.
 *
 * Only outbound owner notifications and read-only queries are exposed. Message
 * bodies live in memory for the life of the process and are never persisted.
 */

const fs = require('fs');
const path = require('path');
const pino = require('pino');
const {
  default: makeWASocket,
  useMultiFileAuthState,
  fetchLatestBaileysVersion,
  DisconnectReason,
  Browsers,
} = require('baileys');
const { normalizeBody, phoneFromJid } = require('./store');

const RECONNECT_MS = 5000;
const GROUPS_TTL_MS = 60000;
const SESSION_FILES = /^[A-Za-z0-9._-]+\.json$/;

function jidFor(value) {
  const raw = String(value || '').trim();
  if (!raw) return null;
  if (raw.includes('@')) return raw;
  const digits = raw.replace(/\D/g, '');
  return digits.length >= 7 ? `${digits}@s.whatsapp.net` : null;
}

class WhatsAppAdapter {
  constructor({ config, store, logger = console, onCreds = null }) {
    this.config = config;
    this.store = store;
    this.logger = logger;
    // Called after any credential rotation so the session can be mirrored to the
    // backend. Credentials on an ephemeral disk do not survive a wake-up.
    this.onCreds = onCreds;
    this.sock = null;
    this.state = 'closed';
    this.me = null;
    this.qrPayload = null;
    this.pairingCode = null;
    this.requestedPairing = false;
    this.pairedAt = null;
    this.lastError = null;
    this.stopped = false;
    this.groupsFetchedAt = 0;
    this.inflightWebhooks = 0;
    this.reconnectTimer = null;
  }

  status() {
    return {
      state: this.state,
      me: this.me ? phoneFromJid(this.me) : null,
      pairedAt: this.pairedAt,
      lastError: this.lastError,
    };
  }

  qr() {
    return this.qrPayload;
  }

  /**
   * Resolve once the socket is usable, or after `timeoutMs`. The default stays
   * below the backend's loopback HTTP timeout so a caller sees an honest failure
   * instead of a request that times out while the message is still in flight.
   *
   * After a free instance wakes up, the socket needs several seconds to link.
   * A notification mirrored in that window used to be dropped as "not linked";
   * waiting briefly turns it into a delivered message.
   */
  async whenOpen(timeoutMs = 4000) {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      if (this.state === 'open') return true;
      await new Promise((resolve) => setTimeout(resolve, 500));
    }
    return this.state === 'open';
  }

  async start() {
    const { state, saveCreds } = await useMultiFileAuthState(this.config.authDir);
    let version;
    try {
      ({ version } = await fetchLatestBaileysVersion());
    } catch {
      version = undefined;
    }
    let logger;
    try {
      logger = pino({ level: this.config.logLevel });
    } catch {
      logger = undefined;
    }
    const sock = makeWASocket({
      version,
      logger,
      auth: state,
      printQRInTerminal: false,
      browser: Browsers.ubuntu('ORA'),
      markOnlineOnConnect: false,
      syncFullHistory: false,
      getMessage: async () => undefined,
    });
    this.sock = sock;
    this.state = 'connecting';

    // Save to disk first, then let the owner of the session copy persist it.
    const persist = () => {
      Promise.resolve()
        .then(() => saveCreds?.())
        .catch(() => {})
        .finally(() => {
          try {
            this.onCreds?.();
          } catch {
            // Persisting a backup must never break the socket.
          }
        });
    };
    sock.ev.on('creds.update', persist);
    sock.ev.on('connection.update', (update) => this.onConnectionUpdate(update, persist));
    sock.ev.on('messages.upsert', ({ messages }) => {
      for (const message of messages || []) this.ingest(message);
    });
    sock.ev.on('messages.update', (updates) => {
      for (const item of updates || []) {
        const status = item?.update?.status;
        if (status !== undefined && status !== null && status >= 3 && item?.key?.id) {
          this.store.markRead([item.key.id]);
        }
      }
    });
    sock.ev.on('contacts.upsert', (contacts) => this.store.upsertContacts(contacts));
    sock.ev.on('contacts.update', (contacts) => this.store.upsertContacts(contacts));
    sock.ev.on('groups.upsert', (groups) => this.store.upsertGroups(groups));
    sock.ev.on('groups.update', (groups) => this.store.upsertGroups(groups));
    sock.ev.on('chats.upsert', (chats) => this.store.upsertGroups(chats));
    sock.ev.on('messaging-history.set', ({ contacts, chats, messages }) => {
      this.store.upsertContacts(contacts);
      this.store.upsertGroups(chats);
      for (const message of messages || []) this.ingest(message, { notify: false });
    });
    return this;
  }

  onConnectionUpdate(update, saveCreds) {
    const { connection, lastDisconnect, qr } = update || {};
    if (qr) {
      this.qrPayload = qr;
      // Pairing by phone number lets the owner link a device from the phone
      // itself, which matters when the only screen available is the one that
      // would have to scan the QR code.
      if (this.config.pairNumber && !this.requestedPairing && !this.pairedAt) {
        this.requestedPairing = true;
        Promise.resolve()
          .then(() => this.sock?.requestPairingCode?.(this.config.pairNumber))
          .then((code) => {
            if (code) {
              this.pairingCode = code;
              this.logger.warn?.('[wa] pairing code issued');
            }
          })
          .catch(() => {
            this.requestedPairing = false;
          });
      }
    }
    if (connection === 'open') {
      this.state = 'open';
      this.qrPayload = null;
      this.pairingCode = null;
      this.requestedPairing = false;
      this.me = this.sock?.user?.id || null;
      this.pairedAt = this.pairedAt || new Date().toISOString();
      this.lastError = null;
      this.logger.warn?.('[wa] linked');
      saveCreds?.();
      try {
        this.onCreds?.();
      } catch {
        // Best effort: the periodic flush retries.
      }
      return;
    }
    if (connection !== 'close') return;
    this.state = 'closed';
    const statusCode = lastDisconnect?.error?.output?.statusCode;
    const loggedOut = statusCode === DisconnectReason?.loggedOut;
    this.lastError = loggedOut ? 'logged out' : (statusCode ? `closed (${statusCode})` : 'closed');
    this.logger.warn?.(`[wa] connection closed: ${this.lastError}`);
    if (loggedOut) {
      // The phone removed this linked device: wipe credentials and require a new pairing.
      this.wipeSession();
      this.pairedAt = null;
      this.pairingCode = null;
      this.requestedPairing = false;
    }
    this.scheduleReconnect();
  }

  scheduleReconnect() {
    if (this.stopped) return;
    clearTimeout(this.reconnectTimer);
    this.reconnectTimer = setTimeout(() => {
      this.start().catch((error) => {
        this.state = 'closed';
        this.lastError = error?.name || 'reconnect failed';
        this.logger.warn?.(`[wa] reconnect failed: ${this.lastError}`);
        this.scheduleReconnect();
      });
    }, RECONNECT_MS);
    this.reconnectTimer.unref?.();
  }

  wipeSession() {
    try {
      for (const name of fs.readdirSync(this.config.authDir)) {
        if (name.endsWith('.json')) fs.rmSync(path.join(this.config.authDir, name), { force: true });
      }
    } catch {
      // Directory may not exist yet.
    }
  }

  ingest(message, { notify = true } = {}) {
    try {
      const key = message?.key || {};
      const remoteJid = key.remoteJid || '';
      if (!remoteJid || remoteJid === 'status@broadcast') return;
      const body = normalizeBody(message.message);
      if (!body) return;
      const isGroup = remoteJid.endsWith('@g.us');
      const fromMe = Boolean(key.fromMe);
      const senderJid = fromMe ? (this.me || '') : (isGroup ? key.participant || '' : remoteJid);
      const contact = this.store.contactsByJid.get(senderJid)
        || (isGroup ? null : this.store.contactsByJid.get(remoteJid));
      const group = isGroup ? this.store.groupsByJid.get(remoteJid) : null;
      const timestamp = Number(message.messageTimestamp || Date.now() / 1000);
      const added = this.store.add({
        id: key.id,
        key: { remoteJid, id: key.id, participant: key.participant, fromMe },
        remoteJid,
        fromMe,
        fromName: fromMe ? 'You' : contact?.name || message.pushName || phoneFromJid(senderJid) || '',
        body,
        timestamp: new Date(timestamp * 1000).toISOString(),
        isGroup,
        groupName: group?.name || null,
        read: fromMe || Boolean(key.read),
      });
      if (added && notify && !fromMe) this.notifyBackend({ added, remoteJid, isGroup, body });
    } catch (error) {
      this.logger.warn?.(`[wa] ingest failed: ${error?.name || 'error'}`);
    }
  }

  notifyBackend({ remoteJid, isGroup, body }) {
    const { backendUrl, internalToken } = this.config;
    if (!backendUrl || !internalToken) return;
    if (this.inflightWebhooks >= 5) return;
    const payload = {
      id: remoteJid,
      from: phoneFromJid(remoteJid),
      fromName: this.store.toPublic(this.store.messages[this.store.messages.length - 1] || {}).fromName,
      body: String(body).slice(0, 500),
      timestamp: new Date().toISOString(),
      isGroup,
      groupName: isGroup ? this.store.groupsByJid.get(remoteJid)?.name || null : null,
    };
    this.inflightWebhooks += 1;
    fetch(`${backendUrl}/api/whatsapp/incoming`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-ORA-Token': internalToken },
      body: JSON.stringify(payload),
      signal: AbortSignal.timeout(5000),
    })
      .catch((error) => {
        this.logger.warn?.(`[wa] webhook failed: ${error?.name || 'error'}`);
      })
      .finally(() => {
        this.inflightWebhooks = Math.max(0, this.inflightWebhooks - 1);
      });
  }

  async send(to, message) {
    if (!this.sock || this.state !== 'open') {
      if (!(await this.whenOpen())) return { ok: false, error: 'WhatsApp is not linked' };
    }
    let jid = jidFor(to);
    if (!jid) {
      const resolved = this.store.resolveContact(to);
      jid = jidFor(resolved);
    }
    if (!jid) return { ok: false, error: 'Recipient not found' };
    try {
      const sent = await this.sock.sendMessage(jid, { text: String(message) });
      if (!sent?.key?.id) return { ok: false, error: 'send not acknowledged' };
      this.store.add({
        id: sent.key.id,
        key: sent.key,
        remoteJid: jid,
        fromMe: true,
        fromName: 'You',
        body: String(message),
        timestamp: new Date().toISOString(),
        isGroup: jid.endsWith('@g.us'),
        groupName: this.store.groupsByJid.get(jid)?.name || null,
        read: true,
      });
      return { ok: true };
    } catch (error) {
      return { ok: false, error: error?.name || 'send failed' };
    }
  }

  messages(query) {
    return this.store.list(query);
  }

  async markRead(ids) {
    const { updated, keys } = this.store.markRead(ids);
    const usable = keys.filter((key) => key && key.remoteJid && key.id);
    if (usable.length && this.sock && this.state === 'open') {
      try {
        await this.sock.readMessages(usable);
      } catch {
        // Read receipts are best-effort; the local view is still updated.
      }
    }
    return updated;
  }

  contacts() {
    return this.store.contacts();
  }

  async groups(force = false) {
    const fresh = Date.now() - this.groupsFetchedAt < GROUPS_TTL_MS;
    if (this.sock && this.state === 'open' && (force || !fresh)) {
      try {
        const participating = await this.sock.groupFetchAllParticipating();
        this.store.upsertGroups(Object.values(participating || {}));
        this.groupsFetchedAt = Date.now();
      } catch {
        // Fall back to whatever the event cache already holds.
      }
    }
    return this.store.groups();
  }

  async setMute(jid, mute) {
    if (!this.sock || this.state !== 'open') return { ok: false, error: 'WhatsApp is not linked' };
    try {
      await this.sock.chatModify({ mute: mute ? 1000 * 60 * 60 * 24 * 365 : null }, jid);
      return { ok: true };
    } catch (error) {
      return { ok: false, error: error?.name || 'mute failed' };
    }
  }

  unreadSummary() {
    return this.store.unreadSummary();
  }

  async sessionBackup() {
    try {
      const files = {};
      for (const name of fs.readdirSync(this.config.authDir)) {
        if (!SESSION_FILES.test(name)) continue;
        files[name] = fs.readFileSync(path.join(this.config.authDir, name), 'utf8');
      }
      if (!files['creds.json']) return null;
      return Buffer.from(JSON.stringify(files), 'utf8').toString('base64');
    } catch {
      return null;
    }
  }

  stop() {
    this.stopped = true;
    clearTimeout(this.reconnectTimer);
    try {
      this.sock?.end?.(undefined);
    } catch {
      // Already closed.
    }
  }
}

module.exports = { WhatsAppAdapter, jidFor };
