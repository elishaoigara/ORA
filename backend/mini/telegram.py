"""Private Telegram gateway for the active ORA Mini workspace."""
import hashlib
import hmac
import logging
import os
import re
import secrets
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

import requests
from fastapi import Depends, Header, HTTPException, Request

from mini.artifacts import metadata as file_metadata, render as render_file
from mini.store import now


def token():
    return os.getenv('TELEGRAM_BOT_TOKEN', '').strip()


def webhook_secret():
    # Telegram accepts only URL-safe characters. No second secret is needed on Render.
    return hmac.new(token().encode(), b'ora-mini-telegram-webhook-v1', hashlib.sha256).hexdigest()


def public_url():
    value = (os.getenv('ORA_PUBLIC_URL') or os.getenv('RENDER_EXTERNAL_URL', '')).rstrip('/')
    try:
        parsed = urlsplit(value)
        valid = (parsed.scheme == 'https' and parsed.hostname and not parsed.username and
                 not parsed.password and parsed.port in (None, 443) and not parsed.path and
                 not parsed.query and not parsed.fragment)
    except ValueError:
        valid = False
    if not valid:
        return ''
    return value


def bot_call(method, payload=None, files=None):
    if not token():
        raise HTTPException(503, 'Set TELEGRAM_BOT_TOKEN on the Render backend first.')
    try:
        response = requests.post(
            'https://api.telegram.org/bot' + token() + '/' + method,
            data=payload if files else None,
            json=None if files else (payload or {}),
            files=files, timeout=(5, 20))
        data = response.json()
        if not response.ok or data.get('ok') is not True:
            raise ValueError('Telegram API rejected the request.')
        return data['result']
    except (requests.RequestException, ValueError, KeyError, TypeError):
        # Requests exception strings can include the bot token in the URL.
        raise HTTPException(503, 'Telegram is unavailable or rejected the bot credentials. Check the Render token.')


def chunks(text):
    text = str(text).strip() or 'ORA has no text to send.'
    result = []
    while text:
        if len(text) <= 4000:
            result.append(text)
            break
        boundary = text.rfind('\n', 0, 4000)
        if boundary < 2000:
            boundary = 4000
        result.append(text[:boundary])
        text = text[boundary:].lstrip()
    return result


def send_part(chat_id, part, store):
    if part['type'] == 'document':
        document = next((d for d in store.read()['documents'] if d['id'] == part['id']), None)
        if not document:
            bot_call('sendMessage', {'chat_id': chat_id, 'text': 'That file is no longer in ORA.'})
            return
        try:
            data, mime, name = render_file(document)
        except ValueError:
            bot_call('sendMessage', {'chat_id': chat_id, 'text': 'That file cannot be rendered now.'})
            return
        bot_call('sendDocument', {'chat_id': str(chat_id), 'caption': name[:1024]},
                 {'document': (name, data, mime)})
    else:
        bot_call('sendMessage', {'chat_id': chat_id, 'text': part['text'],
                                 'link_preview_options': {'is_disabled': True}})


def command(text, store):
    state = store.read()
    command_name, _, argument = text.partition(' ')
    command_name = command_name.split('@', 1)[0].lower()
    argument = argument.strip()
    if command_name in ('/start', '/help'):
        return [{'type': 'text', 'text': 'Talk to ORA here, or use /tasks, /pending and /files. '
                 'Research and file requests use the same tools as the web app. '
                 'Review proposed changes in ORA web → Tools & activity; then use /files and /file ID to get a finished file.'}]
    if command_name == '/tasks':
        tasks = [t for t in state['tasks'] if not t.get('done')][:15]
        lines = [f"• {t['title'][:160]}" + (f" — {t['due_at'][:16]}" if t.get('due_at') else '') for t in tasks]
        return [{'type': 'text', 'text': 'Open tasks:\n' + '\n'.join(lines) if lines else 'No open tasks.'}]
    if command_name == '/pending':
        actions = [a for a in state['actions'] if a['status'] == 'pending' and a['expires_at'] > now()][-8:]
        runs = [r for r in state.get('tool_runs', []) if r['status'] == 'awaiting_approval' and r['expires'] > time.time()][-8:]
        lines = [f"• {a['kind']}: {str(a['payload'])[:180]}" for a in actions]
        lines += [f"• {r['tool']}: {str(r.get('preview', ''))[:180]}" for r in runs]
        return [{'type': 'text', 'text': 'Review in ORA web → Tools & activity:\n' + '\n'.join(lines) if lines else 'Nothing is waiting for approval.'}]
    if command_name == '/files':
        files = [file_metadata(d) for d in state['documents'][-10:]]
        lines = [f"• {d['name'][:100]} — /file {d['id']}" for d in files]
        return [{'type': 'text', 'text': 'ORA files:\n' + '\n'.join(lines) if lines else 'No files yet. Ask ORA to prepare one and approve it in Tools & activity.'}]
    if command_name == '/file':
        document = next((d for d in state['documents'] if d['id'] == argument), None)
        return ([{'type': 'document', 'id': argument}] if document else
                [{'type': 'text', 'text': 'File not found. Use /files to see current IDs.'}])
    return [{'type': 'text', 'text': 'Unknown command. Use /help to see commands.'}]


def configure(store):
    url = public_url()
    if not url:
        raise HTTPException(503, 'Set ORA_PUBLIC_URL to the HTTPS backend origin.')
    me = bot_call('getMe')
    if not me.get('is_bot') or not me.get('username'):
        raise HTTPException(503, 'Telegram did not return a usable bot username.')
    bot_call('setWebhook', {'url': url + '/api/v2/telegram/webhook',
                            'secret_token': webhook_secret(), 'allowed_updates': ['message'],
                            'max_connections': 1})
    legacy_chat = None
    configured_chat = os.getenv('TELEGRAM_CHAT_ID', '').strip()
    if re.fullmatch(r'[1-9][0-9]{0,15}', configured_chat):
        try:
            candidate = bot_call('getChat', {'chat_id': int(configured_chat)})
            if (candidate.get('type') == 'private' and
                    type(candidate.get('id')) is int and
                    candidate['id'] == int(configured_chat)):
                legacy_chat = {'chat_id': candidate['id'],
                               'first_name': str(candidate.get('first_name') or 'Owner')[:80]}
        except HTTPException:
            # A stale chat ID must not prevent the private pairing flow.
            pass
    def save(s):
        telegram = s.setdefault('telegram', {})
        if telegram.get('bot_id') != me['id']:
            for key in ('chat_id', 'user_id', 'first_name', 'pairing'):
                telegram.pop(key, None)
            s['telegram_updates'] = []
        telegram.update(bot_id=me['id'], username=me['username'])
        if legacy_chat and not telegram.get('chat_id') and not telegram.get('legacy_link_disabled'):
            telegram.update(legacy_chat)
    store.mutate(save)
    return {'ok': True, 'username': me['username']}


def automatic_setup(store):
    if not token() or not public_url():
        return
    try:
        configure(store)
    except Exception:
        logging.getLogger(__name__).warning(
            'Telegram webhook registration failed; retry from ORA Connections.')


def install(app, store_factory, owner, chat, Chat, limited):
    @app.get('/api/v2/telegram/status')
    def status(auth=Depends(owner)):
        state = store_factory().read().get('telegram', {})
        result = {'configured': bool(token()), 'public_url_configured': bool(public_url()),
                  'linked': bool(state.get('chat_id')), 'username': state.get('username'),
                  'first_name': state.get('first_name')}
        if token() and public_url():
            try:
                info = bot_call('getWebhookInfo')
                result['webhook_active'] = info.get('url') == public_url() + '/api/v2/telegram/webhook'
                result['pending_updates'] = info.get('pending_update_count', 0)
            except HTTPException:
                result['webhook_active'] = False
        return result

    @app.post('/api/v2/telegram/setup')
    def setup(auth=Depends(owner)):
        return configure(store_factory())

    @app.post('/api/v2/telegram/pairing-code')
    def pairing_code(auth=Depends(owner)):
        state = store_factory().read().get('telegram', {})
        username = state.get('username')
        if not token() or not public_url() or not username:
            raise HTTPException(503, 'Set up the Telegram webhook first.')
        code = secrets.token_hex(10).upper()
        def save(s):
            s.setdefault('telegram', {})['pairing'] = {
                'hash': hashlib.sha256(code.encode()).hexdigest(),
                'expires_at': (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()}
        store_factory().mutate(save)
        return {'code': code, 'url': 'https://t.me/' + username + '?start=' + code,
                'expires_in': 600}

    @app.delete('/api/v2/telegram/link')
    def unlink(auth=Depends(owner)):
        def save(s):
            telegram = s.setdefault('telegram', {})
            for key in ('chat_id', 'user_id', 'first_name', 'pairing'):
                telegram.pop(key, None)
            telegram['legacy_link_disabled'] = True
            return {'ok': True}
        return store_factory().mutate(save)

    @app.post('/api/v2/telegram/webhook')
    async def webhook(request: Request, x_telegram_bot_api_secret_token: str = Header(default='')):
        if not token() or not hmac.compare_digest(x_telegram_bot_api_secret_token, webhook_secret()):
            raise HTTPException(403, 'Invalid webhook credentials.')
        body = await request.body()
        if len(body) > 131072:
            # Acknowledge unsupported oversized updates so Telegram does not retry forever.
            return {'ok': True}
        try:
            import json
            update = json.loads(body)
        except (ValueError, UnicodeDecodeError):
            raise HTTPException(400, 'Invalid Telegram update.')
        if not isinstance(update, dict) or type(update.get('update_id')) is not int:
            raise HTTPException(400, 'Invalid Telegram update.')
        from starlette.concurrency import run_in_threadpool
        return await run_in_threadpool(process_update, update)

    def process_update(update):
        message = update.get('message')
        if not isinstance(message, dict):
            return {'ok': True}
        peer = message.get('from')
        room = message.get('chat')
        if (not isinstance(peer, dict) or not isinstance(room, dict) or
                room.get('type') != 'private' or type(peer.get('id')) is not int or
                type(room.get('id')) is not int or peer.get('is_bot')):
            return {'ok': True}
        store = store_factory()
        telegram = store.read().get('telegram', {})
        incoming = message.get('text')
        if not isinstance(incoming, str):
            if telegram.get('user_id') != peer['id'] or telegram.get('chat_id') != room['id']:
                return {'ok': True}
            incoming = ''
        authorized = (telegram.get('chat_id') == room['id'] and
                      telegram.get('user_id') in (None, peer['id']))
        if authorized and telegram.get('user_id') is None:
            def bind_private_owner(s):
                row = s.setdefault('telegram', {})
                if row.get('chat_id') != room['id'] or row.get('user_id') not in (None, peer['id']):
                    return False
                row['user_id'] = peer['id']
                return True
            if not store.mutate(bind_private_owner):
                return {'ok': True}
        pairing = telegram.get('pairing', {})
        code = incoming.split(' ', 1)[-1].strip().upper() if incoming.startswith('/start ') else ''
        if not authorized:
            if (not re.fullmatch(r'[A-F0-9]{20}', code) or
                    pairing.get('expires_at', '') <= now() or
                    not hmac.compare_digest(pairing.get('hash', ''), hashlib.sha256(code.encode()).hexdigest())):
                return {'ok': True}
            def link(s):
                row = s.setdefault('telegram', {})
                pending = row.get('pairing', {})
                if pending.get('expires_at', '') <= now() or not hmac.compare_digest(
                        pending.get('hash', ''), hashlib.sha256(code.encode()).hexdigest()):
                    return False
                row.update(user_id=peer['id'], chat_id=room['id'],
                           first_name=str(peer.get('first_name', 'Owner'))[:80])
                row.pop('pairing', None)
                row['legacy_link_disabled'] = True
                return True
            if not store.mutate(link):
                return {'ok': True}
            incoming = '/start'
        update_id = str(update['update_id'])
        def claim(s):
            rows = s.setdefault('telegram_updates', [])
            row = next((r for r in rows if r['id'] == update_id), None)
            if row:
                if row['status'] == 'done':
                    return 'done'
                if row.get('lease_until', 0) > time.time():
                    return 'busy'
            else:
                row = {'id': update_id, 'chat_id': room['id'], 'status': 'processing',
                       'next_part': 0}
                rows.append(row)
                rows[:] = rows[-150:]
            row['lease_until'] = time.time() + 120
            return row['status']
        previous = store.mutate(claim)
        if previous == 'done':
            return {'ok': True}
        if previous == 'busy':
            raise HTTPException(503, 'Telegram update is already processing.')
        try:
            if previous != 'ready':
                if not incoming:
                    parts = [{'type': 'text', 'text': 'Send text to ORA. Use the web or Android app for voice and uploads.'}]
                elif len(incoming) > 8000:
                    parts = [{'type': 'text', 'text': 'Please shorten your message to 8000 characters.'}]
                elif incoming.startswith('/'):
                    parts = command(incoming, store)
                else:
                    try:
                        result = chat(Chat(request_id='telegram-' + update_id.zfill(16),
                                           text=incoming), auth={'id': 'telegram:' + str(peer['id']), 'device_id': None})
                        suffix = ('\n\nReview the proposed change in ORA web → Tools & activity.'
                                  if result.get('actions') else '')
                        parts = [{'type': 'text', 'text': chunk} for chunk in chunks(result['reply'] + suffix)]
                    except HTTPException as exc:
                        if exc.status_code not in (400, 413, 422, 429):
                            raise
                        parts = [{'type': 'text', 'text': str(exc.detail)}]
                def ready(s):
                    row = next(r for r in s['telegram_updates'] if r['id'] == update_id)
                    row.update(status='ready', parts=parts)
                store.mutate(ready)
            while True:
                row = next(r for r in store.read()['telegram_updates'] if r['id'] == update_id)
                if row['next_part'] >= len(row['parts']):
                    break
                send_part(row['chat_id'], row['parts'][row['next_part']], store)
                def sent(s):
                    item = next(r for r in s['telegram_updates'] if r['id'] == update_id)
                    item['next_part'] += 1
                store.mutate(sent)
            def done(s):
                row = next(r for r in s['telegram_updates'] if r['id'] == update_id)
                row['status'] = 'done'
                row.pop('parts', None)
                row.pop('lease_until', None)
            store.mutate(done)
            return {'ok': True}
        except Exception:
            def retry(s):
                row = next((r for r in s.get('telegram_updates', []) if r['id'] == update_id), None)
                if row:
                    row['lease_until'] = 0
            store.mutate(retry)
            raise
