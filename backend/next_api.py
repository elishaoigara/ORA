"""ORA Mini API: stateless Render compute, durable workspace, phone-first reminders."""
import hashlib
import hmac
import io
import os
import secrets
import threading
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
load_dotenv()
from fastapi import FastAPI, Depends, Header, HTTPException, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from mini.store import Store, now
from mini.intelligence import respond, suggestions

store = None
chat_lock = threading.Lock()
rate_lock = threading.Lock()
rates = defaultdict(deque)


def db():
    if store is None:
        raise HTTPException(503, 'Workspace is not ready. Check database configuration.')
    return store


@asynccontextmanager
async def lifespan(app):
    global store
    store = Store()
    yield


app = FastAPI(title='ORA Mini', version='2.0.0', lifespan=lifespan,
              docs_url=None if os.getenv('APP_ENV') == 'production' else '/docs')
app.add_middleware(CORSMiddleware, allow_origins=[s.strip() for s in os.getenv('CORS_ORIGINS', 'http://localhost:5173').split(',') if s.strip()],
                   allow_methods=['GET', 'POST', 'DELETE'], allow_headers=['Authorization', 'Content-Type'])


def limited(key, limit=15):
    with rate_lock:
        stamp = time.monotonic()
        if len(rates) > 1000:
            for old in list(rates):
                if not rates[old] or rates[old][-1] < stamp - 60:
                    del rates[old]
        bucket = rates[key]
        while bucket and bucket[0] < stamp - 60:
            bucket.popleft()
        if len(bucket) >= limit:
            raise HTTPException(429, 'Too many requests. Please wait a minute.', headers={'Retry-After': '60'})
        bucket.append(stamp)


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def identity(authorization: str = Header(default='')):
    token = authorization.removeprefix('Bearer ').strip()
    if not token:
        raise HTTPException(401, 'Connect to ORA first.')
    state = db().read()
    session = next((s for s in state['sessions'] if hmac.compare_digest(s['hash'], digest(token)) and s['expires_at'] > now()), None)
    if not session:
        raise HTTPException(401, 'Connection expired or revoked. Please reconnect.')
    if session.get('device_id'):
        device = next((d for d in state['devices'] if d['id'] == session['device_id'] and not d.get('revoked')), None)
        if not device:
            raise HTTPException(401, 'Device revoked.')
    return session


def owner(auth=Depends(identity)):
    if auth.get('device_id'):
        raise HTTPException(403, 'Use the web owner session for this action.')
    return auth


class Login(BaseModel):
    token: str = Field(min_length=1, max_length=512)


class Pair(BaseModel):
    code: str = Field(min_length=8, max_length=40)
    label: str = Field(default='My Android', min_length=1, max_length=64)


class Operation(BaseModel):
    request_id: str = Field(min_length=16, max_length=100)
    kind: str = Field(max_length=40)
    payload: dict = Field(default_factory=dict)


class Chat(BaseModel):
    request_id: str = Field(min_length=16, max_length=100)
    text: str = Field(min_length=1, max_length=8000)


def new_session(state, device_id=None):
    token = secrets.token_urlsafe(40)
    state['sessions'] = [s for s in state['sessions'] if s['expires_at'] > now()][-49:]
    state['sessions'].append({'id': uuid.uuid4().hex, 'hash': digest(token), 'device_id': device_id,
                              'expires_at': (datetime.now(timezone.utc) + timedelta(days=90 if device_id else 7)).isoformat()})
    return token


@app.get('/api/health')
def health():
    return {'ok': store is not None, 'release': 'ora-mini-2', 'storage': 'postgres' if os.getenv('DATABASE_URL') else 'local-development',
            'reminders': 'android-local', 'ai_configured': bool(os.getenv('GROQ_API_KEY'))}


@app.post('/api/v2/session')
def login(payload: Login, request: Request):
    limited('login:' + (request.client.host if request.client else 'unknown'), 5)
    configured = os.getenv('ORA_API_TOKEN', '')
    if not configured:
        raise HTTPException(503, 'Owner access is not configured.')
    if not hmac.compare_digest(payload.token, configured):
        raise HTTPException(401, 'Incorrect access key.')
    return db().mutate(lambda state: {'token': new_session(state)})


@app.delete('/api/v2/session')
def logout(auth=Depends(identity)):
    def apply(state):
        state['sessions'] = [s for s in state['sessions'] if s['id'] != auth['id']]
        return {'ok': True}
    return db().mutate(apply)


@app.post('/api/v2/pairing-code')
def pairing_code(auth=Depends(owner)):
    code = secrets.token_hex(5).upper()
    def apply(state):
        state['pairing'] = [{'hash': digest(code), 'expires_at': (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()}]
        return {'code': code, 'expires_in': 600}
    return db().mutate(apply)


@app.post('/api/v2/pair')
def pair(payload: Pair, request: Request):
    limited('pair:' + (request.client.host if request.client else 'unknown'), 5)
    def apply(state):
        match = next((p for p in state['pairing'] if hmac.compare_digest(p['hash'], digest(payload.code.strip().upper())) and p['expires_at'] > now()), None)
        if not match:
            raise HTTPException(400, 'Pairing code is invalid or expired.')
        if len([d for d in state['devices'] if not d.get('revoked')]) >= 10:
            raise HTTPException(400, 'Revoke an old device before pairing another.')
        state['pairing'].remove(match)
        device = {'id': uuid.uuid4().hex, 'label': payload.label, 'last_seen': now(), 'permissions': {}, 'paused': False, 'revoked': False}
        state['devices'].append(device)
        return {'token': new_session(state, device['id']), 'device_id': device['id']}
    return db().mutate(apply)


def snapshot(state, auth):
    data = {k: state[k] for k in ('revision', 'tasks', 'messages', 'memories', 'actions', 'settings')}
    data['documents'] = [{'id': d['id'], 'name': d['name'], 'created_at': d['created_at']} for d in state['documents']]
    data['devices'] = [d for d in state['devices'] if not d.get('revoked')]
    data['events'] = [e for e in state['events'] if e['expires_at'] > now()][-30:]
    data['suggestions'] = suggestions(state)
    data['synced_at'] = now()
    data['device_id'] = auth.get('device_id')
    return data


@app.get('/api/v2/sync')
def sync(auth=Depends(identity)):
    return snapshot(db().read(), auth)


def clean_text(value, max_length):
    if not isinstance(value, str) or not value.strip() or len(value) > max_length:
        raise HTTPException(422, 'Text is missing or too long.')
    return value.strip()


def due(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if dt.tzinfo is None:
            raise ValueError()
        return dt.astimezone(timezone.utc).isoformat()
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(422, 'Reminder time must include a timezone.')


def task_payload(p):
    priority = p.get('priority', 2)
    if type(priority) is not int or priority not in (1,2,3):
        raise HTTPException(422, 'Priority must be 1, 2 or 3.')
    return {'title': clean_text(p.get('title'), 240), 'due_at': due(p.get('due_at')), 'priority': priority}


def add_task(state, p, task_id):
    if len(state['tasks']) >= 500:
        raise HTTPException(400, 'Task limit reached. Remove finished tasks first.')
    task = {**task_payload(p), 'id': task_id, 'done': False, 'version': 1, 'created_at': now()}
    state['tasks'].append(task)
    return task


def action_payload(kind, p):
    if kind == 'task':
        return task_payload(p)
    if kind == 'memory':
        return {'text': clean_text(p.get('text'), 1000)}
    if kind == 'message':
        return {'recipient': clean_text(p.get('recipient'), 200), 'body': clean_text(p.get('body'), 4000)}
    raise HTTPException(422, 'Unsupported proposal.')


def apply_operation(state, op, auth):
    p, kind = op.payload, op.kind
    if kind == 'task.create':
        return add_task(state, p, op.request_id)
    if kind in ('task.complete', 'task.delete'):
        task = next((t for t in state['tasks'] if t['id'] == p.get('id')), None)
        if not task:
            raise HTTPException(404, 'Task no longer exists.')
        if p.get('version') != task['version']:
            raise HTTPException(409, 'Task changed on another device. Sync and try again.')
        if kind == 'task.delete':
            state['tasks'].remove(task)
        else:
            task.update(done=not task['done'], version=task['version']+1)
        return {'ok': True}
    if kind == 'memory.save':
        if len(state['memories']) >= 200:
            raise HTTPException(400, 'Memory limit reached. Remove an old memory first.')
        item = {'id': op.request_id, 'text': clean_text(p.get('text'), 1000), 'created_at': now()}
        state['memories'].append(item)
        return item
    if kind == 'memory.delete':
        state['memories'] = [m for m in state['memories'] if m['id'] != p.get('id')]
        return {'ok': True}
    if kind == 'document.delete':
        state['documents'] = [d for d in state['documents'] if d['id'] != p.get('id')]
        return {'ok': True}
    if kind in ('action.approve', 'action.reject'):
        action = next((a for a in state['actions'] if a['id'] == p.get('id')), None)
        if not action:
            raise HTTPException(404, 'Proposal not found.')
        if action['status'] != 'pending':
            return action
        if action['expires_at'] <= now():
            action['status'] = 'expired'
            return action
        if kind == 'action.reject':
            action['status'] = 'rejected'
        else:
            if action['kind'] == 'task':
                add_task(state, action['payload'], action['id'])
            elif action['kind'] == 'memory':
                if len(state['memories']) >= 200:
                    raise HTTPException(400, 'Memory limit reached.')
                state['memories'].append({'id': action['id'], **action['payload'], 'created_at': now()})
            action['status'] = 'ready_to_share' if action['kind'] == 'message' else 'completed'
        return action
    if kind == 'settings.update':
        settings = dict(state['settings'])
        if 'name' in p:
            settings['name'] = clean_text(p['name'], 60)
        if 'timezone' in p:
            try:
                ZoneInfo(p['timezone'])
            except Exception:
                raise HTTPException(422, 'Unknown timezone.')
            settings['timezone'] = p['timezone']
        for key in ('quiet_start', 'quiet_end', 'briefing_hour'):
            if key in p:
                if type(p[key]) is not int or not 0 <= p[key] <= 23:
                    raise HTTPException(422, 'Hours must be from 0 to 23.')
                settings[key] = p[key]
        state['settings'] = settings
        return settings
    if kind in ('device.permissions', 'device.pause', 'device.revoke', 'events.delete'):
        if auth.get('device_id') and p.get('id') and p['id'] != auth['device_id']:
            raise HTTPException(403, 'A phone can only change its own device settings.')
        device_id = auth.get('device_id') or p.get('id')
        device = next((d for d in state['devices'] if d['id'] == device_id and not d.get('revoked')), None)
        if not device:
            raise HTTPException(404, 'Device not found.')
        if kind == 'device.permissions':
            permitted = {'notifications', 'location', 'health', 'contacts', 'calendar'}
            key = p.get('permission')
            if key not in permitted or type(p.get('enabled')) is not bool:
                raise HTTPException(422, 'Invalid permission.')
            device['permissions'][key] = p['enabled']
            if not p['enabled']:
                state['events'] = [e for e in state['events'] if not (e['device_id'] == device_id and e['kind'] == key)]
        elif kind == 'device.pause':
            if type(p.get('paused')) is not bool:
                raise HTTPException(422, 'Paused must be a boolean.')
            device['paused'] = p['paused']
        elif kind == 'device.revoke':
            device['revoked'] = True
            state['sessions'] = [s for s in state['sessions'] if s.get('device_id') != device_id]
            state['events'] = [e for e in state['events'] if e['device_id'] != device_id]
        else:
            state['events'] = [e for e in state['events'] if e['device_id'] != device_id]
        return {'ok': True}
    raise HTTPException(422, 'Unknown operation.')


@app.post('/api/v2/operations')
def operation(op: Operation, auth=Depends(identity)):
    limited(auth['id'], 60)
    return db().mutate(lambda state: apply_operation(state, op, auth), auth['id'] + ':' + op.request_id)


@app.post('/api/v2/chat')
def chat(payload: Chat, auth=Depends(identity)):
    limited('chat:' + auth['id'], 12)
    if not chat_lock.acquire(blocking=False):
        raise HTTPException(409, 'ORA is answering another message. Try again in a moment.')
    try:
        state = db().read()
        cached = next((m for m in state['messages'] if m.get('request_id') == payload.request_id and m['role'] == 'assistant'), None)
        if cached:
            return {'reply': cached['text']}
        def reserve_budget(current):
            today = now()[:10]
            usage = current.setdefault('usage', {'date': today, 'requests': 0})
            if usage['date'] != today:
                usage.update(date=today, requests=0)
            if usage['requests'] >= int(os.getenv('ORA_DAILY_AI_REQUESTS', '100')):
                raise HTTPException(429, 'Your daily AI request budget is used. Tasks, memory and reminders still work.')
            usage['requests'] += 1
        db().mutate(reserve_budget)
        try:
            reply, proposals = respond(state, payload.text)
        except Exception as exc:
            raise HTTPException(503, str(exc) if isinstance(exc, RuntimeError) else 'AI connection failed. Try again.')
        def save(current):
            actions = []
            for index, proposal in enumerate(proposals):
                try:
                    validated = action_payload(proposal['kind'], proposal['payload'])
                except HTTPException:
                    continue
                action = {'id': payload.request_id + ':' + str(index), 'kind': proposal['kind'], 'payload': validated,
                          'status': 'pending', 'created_at': now(), 'expires_at': (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()}
                current['actions'].append(action)
                actions.append(action)
            current['actions'] = current['actions'][-100:]
            current['messages'] += [{'id': uuid.uuid4().hex, 'request_id': payload.request_id, 'role': 'user', 'text': payload.text, 'created_at': now()},
                                    {'id': uuid.uuid4().hex, 'request_id': payload.request_id, 'role': 'assistant', 'text': reply, 'created_at': now()}]
            current['messages'] = current['messages'][-300:]
            return {'reply': reply, 'actions': actions}
        return db().mutate(save, 'chat:' + payload.request_id)
    finally:
        chat_lock.release()


class PhoneEvent(BaseModel):
    request_id: str = Field(min_length=16, max_length=100)
    kind: str
    text: str = Field(min_length=1, max_length=1200)
    observed_at: str


@app.post('/api/v2/events')
def phone_event(payload: PhoneEvent, auth=Depends(identity)):
    if not auth.get('device_id'):
        raise HTTPException(403, 'Pair an Android device first.')
    observed = due(payload.observed_at)
    stamp = datetime.fromisoformat(observed)
    age = (datetime.now(timezone.utc) - stamp).total_seconds()
    if age < -300 or age > 86400:
        raise HTTPException(422, 'Event is too old or has an invalid clock.')
    def apply(state):
        device = next(d for d in state['devices'] if d['id'] == auth['device_id'])
        if device['paused'] or not device['permissions'].get(payload.kind):
            raise HTTPException(403, 'This phone source is paused or disabled.')
        import re
        text = re.sub(r'\b\d{4,10}\b', '[code]', payload.text) if payload.kind == 'notifications' else payload.text
        state['events'] = [e for e in state['events'] if e['expires_at'] > now()][-59:]
        state['events'].append({'id': payload.request_id, 'device_id': device['id'], 'kind': payload.kind, 'text': text,
                                'observed_at': observed, 'expires_at': (stamp + timedelta(hours=24)).isoformat()})
        device['last_seen'] = now()
        return {'ok': True}
    return db().mutate(apply, auth['id'] + ':event:' + payload.request_id)


@app.post('/api/v2/transcribe')
async def transcribe(file: UploadFile = File(...), auth=Depends(identity)):
    limited('voice:' + auth['id'], 8)
    data = await file.read(8 * 1024 * 1024 + 1)
    if not data or len(data) > 8 * 1024 * 1024:
        raise HTTPException(413, 'Record a shorter voice note (maximum 8 MB).')
    import requests
    try:
        from starlette.concurrency import run_in_threadpool
        def call():
            r = requests.post('https://api.groq.com/openai/v1/audio/transcriptions',
                 headers={'Authorization': 'Bearer ' + os.getenv('GROQ_API_KEY', '')},
                 files={'file': (file.filename or 'voice.webm', data)},
                 data={'model': os.getenv('GROQ_STT_MODEL', 'whisper-large-v3-turbo')}, timeout=(10, 45))
            r.raise_for_status()
            return {'text': r.json()['text']}
        return await run_in_threadpool(call)
    except Exception:
        raise HTTPException(503, 'Voice transcription unavailable. Try typing your message.')


@app.post('/api/v2/documents')
async def upload(file: UploadFile = File(...), auth=Depends(identity)):
    data = await file.read(2 * 1024 * 1024 + 1)
    if len(data) > 2 * 1024 * 1024:
        raise HTTPException(413, 'Use a document under 2 MB.')
    name = (file.filename or 'note.txt')[:120]
    try:
        if name.lower().endswith('.pdf'):
            from pypdf import PdfReader
            from starlette.concurrency import run_in_threadpool
            def extract():
                reader = PdfReader(io.BytesIO(data))
                if len(reader.pages) > 80:
                    raise ValueError('Too many pages')
                return '\n'.join((p.extract_text() or '')[:10000] for p in reader.pages)[:50000]
            text = await run_in_threadpool(extract)
        elif name.lower().endswith(('.txt', '.md')):
            text = data.decode('utf-8')[:50000]
        else:
            raise ValueError('Unsupported format')
    except Exception:
        raise HTTPException(422, 'Use a readable PDF, UTF-8 text, or Markdown file (up to 80 PDF pages).')
    if not text.strip():
        raise HTTPException(422, 'No readable text found. Scanned PDFs need OCR first.')
    def save(state):
        if len(state['documents']) >= 20:
            raise HTTPException(400, 'Remove a document before adding another (20 maximum).')
        item = {'id': uuid.uuid4().hex, 'name': name, 'text': text, 'created_at': now()}
        state['documents'].append(item)
        return {'id': item['id'], 'name': name}
    return db().mutate(save)


@app.get('/api/v2/export')
def export(auth=Depends(owner)):
    return snapshot(db().read(), auth) | {'documents': db().read()['documents']}
