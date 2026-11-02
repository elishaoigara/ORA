'use strict';

/**
 * HTTP surface consumed by ORA (backend/connectors/whatsapp.py).
 *
 * Contract (all routes except /health require the `x-api-secret` header):
 *   GET  /health              -> liveness for platform health checks (no secrets)
 *   GET  /status              -> { ok, state, me, pairedAt }
 *   GET  /qr                  -> pairing page/PNG when the session is not linked
 *   POST /send                -> { to, message }
 *   GET  /messages            -> ?limit&contact&unread&search&no_groups
 *   POST /mark-read           -> { ids }
 *   GET  /contacts            -> { contacts: [{ name, phone }] }
 *   GET  /groups              -> { groups: [{ name, jid }] }
 *   POST /mute                -> { jid, mute }
 *   GET  /unread-summary      -> { total, summary: [{ name, type, count, latest }] }
 *   GET  /session/export      -> base64 auth state for WA_SESSION_B64 (owner only)
 */

const crypto = require('crypto');
const express = require('express');

function digest(value) {
  return crypto.createHash('sha256').update(String(value || '')).digest();
}

function safeEqual(a, b) {
  return crypto.timingSafeEqual(digest(a), digest(b));
}

function bool(value) {
  return String(value || '').toLowerCase() === 'true';
}

function int(value, fallback, min, max) {
  const parsed = Number.parseInt(String(value ?? ''), 10);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.min(max, Math.max(min, parsed));
}

function createApp({ wa, config, qrcode }) {
  const app = express();
  app.disable('x-powered-by');
  app.use(express.json({ limit: '256kb' }));

  const requireSecret = (req, res, next) => {
    const provided = req.get('x-api-secret') || String(req.query.secret || '');
    if (!config.apiSecret || !safeEqual(provided, config.apiSecret)) {
      return res.status(401).json({ ok: false, error: 'Unauthorized' });
    }
    return next();
  };

  const guarded = (handler) => async (req, res) => {
    try {
      await handler(req, res);
    } catch (error) {
      // Never echo upstream errors verbatim: they can embed session material.
      const reason = error && error.name ? error.name : 'Error';
      res.status(503).json({ ok: false, error: `Sidecar unavailable (${reason})` });
    }
  };

  // Unauthenticated on purpose: platform health checks must succeed before pairing.
  app.get('/health', (req, res) => {
    res.json({ ok: true, state: wa.status().state, service: 'ora-whatsapp-sidecar' });
  });

  app.get('/status', requireSecret, guarded(async (req, res) => {
    res.json({ ok: true, ...wa.status() });
  }));

  app.get('/qr', requireSecret, guarded(async (req, res) => {
    const status = wa.status();
    const payload = wa.qr();
    if (status.state === 'open' || !payload) {
      return res.status(200).type('text/html').send(
        `<!doctype html><meta charset="utf-8"><title>ORA WhatsApp</title>
         <body style="font:16px system-ui;padding:2rem;max-width:36rem">
         <h1>ORA WhatsApp sidecar</h1>
         <p>State: <strong>${status.state === 'open' ? 'linked' : 'not linked'}</strong></p>
         <p>${status.state === 'open'
            ? 'This device is already paired. Unlink from WhatsApp → Linked devices first to pair again.'
            : 'No pairing code right now. Reload in a few seconds while the socket connects.'}</p>
         <p><a href="?secret=${encodeURIComponent(String(req.query.secret || ''))}">Reload</a></p></body>`,
      );
    }
    const dataUrl = qrcode ? await qrcode.toDataURL(payload, { margin: 1, width: 320 }) : '';
    if (!qrcode) return res.status(503).type('text/html').send('qrcode module unavailable');
    return res.type('text/html').send(
      `<!doctype html><meta charset="utf-8"><title>ORA WhatsApp pairing</title>
       <meta http-equiv="refresh" content="20">
       <body style="font:16px system-ui;padding:2rem;text-align:center">
       <h1>Pair ORA WhatsApp</h1>
       <p>WhatsApp → Settings → Linked devices → Link a device</p>
       <img alt="pairing QR" src="${dataUrl}" width="320" height="320" />
       <p style="color:#666">Code refreshes automatically. Close this page when paired.</p></body>`,
    );
  }));

  app.post('/send', requireSecret, guarded(async (req, res) => {
    const to = String(req.body?.to || '').trim();
    const message = String(req.body?.message || '');
    if (!to || !message) return res.status(400).json({ ok: false, error: 'to and message are required' });
    if (message.length > 8000) return res.status(400).json({ ok: false, error: 'message too long' });
    const status = wa.status();
    if (status.state !== 'open') return res.status(503).json({ ok: false, error: 'WhatsApp is not linked' });
    const result = await wa.send(to, message);
    if (!result.ok) return res.status(502).json({ ok: false, error: result.error || 'send failed' });
    return res.json({ ok: true });
  }));

  app.get('/messages', requireSecret, guarded(async (req, res) => {
    res.json({
      ok: true,
      messages: wa.messages({
        limit: int(req.query.limit, 20, 1, 100),
        contact: String(req.query.contact || ''),
        unreadOnly: bool(req.query.unread),
        search: String(req.query.search || ''),
        dmsOnly: bool(req.query.no_groups),
      }),
    });
  }));

  app.post('/mark-read', requireSecret, guarded(async (req, res) => {
    const ids = Array.isArray(req.body?.ids) ? req.body.ids.slice(0, 200).map(String) : [];
    if (!ids.length) return res.status(400).json({ ok: false, error: 'ids are required' });
    return res.json({ ok: true, updated: await wa.markRead(ids) });
  }));

  app.get('/contacts', requireSecret, guarded(async (req, res) => {
    res.json({ ok: true, contacts: wa.contacts() });
  }));

  app.get('/groups', requireSecret, guarded(async (req, res) => {
    res.json({ ok: true, groups: await wa.groups() });
  }));

  app.post('/mute', requireSecret, guarded(async (req, res) => {
    const jid = String(req.body?.jid || '').trim();
    if (!jid.endsWith('@g.us')) return res.status(400).json({ ok: false, error: 'jid must be a group JID' });
    const result = await wa.setMute(jid, req.body?.mute !== false);
    if (!result.ok) return res.status(502).json({ ok: false, error: result.error || 'mute failed' });
    return res.json({ ok: true });
  }));

  app.get('/unread-summary', requireSecret, guarded(async (req, res) => {
    res.json({ ok: true, ...wa.unreadSummary() });
  }));

  app.get('/session/export', requireSecret, guarded(async (req, res) => {
    const backup = await wa.sessionBackup();
    if (!backup) return res.status(409).json({ ok: false, error: 'No linked session to export' });
    return res.json({ ok: true, b64: backup });
  }));

  app.use((req, res) => res.status(404).json({ ok: false, error: 'Not found' }));
  return app;
}

module.exports = { createApp, safeEqual };
