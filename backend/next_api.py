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
from mini.tools import Runtime, catalog, visible, BY_NAME, public_run, allowed_repos
from mini.artifacts import metadata as file_metadata, render as render_file
from mini.companion import weather_check, dispatch, alert
import re

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
    project_id: str = Field(default="", max_length=100)
    document_ids: list[str] = Field(default_factory=list, max_length=3)
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
            'companion_release': '2.2', 'work_release': '1.0', 'reminders': 'android-local', 'ai_configured': bool(os.getenv('GROQ_API_KEY'))}


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
    data['documents'] = [file_metadata(d) for d in state['documents']]
    data['devices'] = [{k: v for k, v in d.items() if k not in ('push_token', 'weather')} | {'push_registered': bool(d.get('push_token')), 'weather': {k: v for k, v in d.get('weather', {}).items() if k not in ('latitude', 'longitude')}} for d in state['devices'] if not d.get('revoked')]
    data['alerts'] = [{k: v for k, v in a.items() if k not in ('ticket', 'key')} for a in state.get('alerts', []) if not auth.get('device_id') or a['device_id'] == auth['device_id']]
    data['scheduler_at'] = state.get('scheduler_at')
    data['events'] = [e for e in state['events'] if e['expires_at'] > now()][-30:]
    data['suggestions'] = suggestions(state)
    data['synced_at'] = now()
    data['device_id'] = auth.get('device_id')
    data['tool_runs'] = [public_run(r) for r in state.get('tool_runs', []) if visible(r, auth)][-30:]
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
    repeat = p.get('repeat', 'none')
    if repeat not in ('none', 'daily', 'weekly'):
        raise HTTPException(422, 'Choose none, daily or weekly repeat.')
    return {'title': clean_text(p.get('title'), 240), 'due_at': due(p.get('due_at')), 'priority': priority, 'repeat': repeat}


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
    if kind.startswith('companion.'):
        return companion_operation(state, kind, p, auth)
    if kind == 'task.create':
        return add_task(state, p, op.request_id)
    if kind in ('task.complete', 'task.delete', 'task.update'):
        task = next((t for t in state['tasks'] if t['id'] == p.get('id')), None)
        if not task:
            raise HTTPException(404, 'Task no longer exists.')
        if p.get('version') != task['version']:
            raise HTTPException(409, 'Task changed on another device. Sync and try again.')
        if kind == 'task.delete':
            state['tasks'].remove(task)
        elif kind == 'task.update':
            task.update(task_payload({**task, **p}), version=task['version']+1)
        elif not task['done'] and task.get('repeat', 'none') != 'none' and task.get('due_at'):
            step = timedelta(days=1 if task['repeat'] == 'daily' else 7)
            date = datetime.fromisoformat(task['due_at']) + step
            while date <= datetime.now(timezone.utc): date += step
            task.update(due_at=date.isoformat(), version=task['version']+1)
        else:
            task.update(done=not task['done'], version=task['version']+1)
        return {'ok': True}
    if kind == 'memory.save':
        if len(state['memories']) >= 200:
            raise HTTPException(400, 'Memory limit reached. Remove an old memory first.')
        item = {'id': op.request_id, 'text': clean_text(p.get('text'), 1000), 'created_at': now()}
        state['memories'].append(item)
        return item
    if kind == 'memory.update':
        item = next((m for m in state['memories'] if m['id'] == p.get('id')), None)
        if not item: raise HTTPException(404, 'Memory not found.')
        if 'text' in p: item['text'] = clean_text(p['text'], 1000)
        if 'category' in p: item['category'] = clean_text(p['category'], 40)
        if 'pinned' in p: item['pinned'] = bool(p['pinned'])
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
                if key == 'location' and device.get('weather', {}).get('source') == 'location':
                    device.pop('weather', None)
                    device.pop('forecast', None)
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
        from mini.workspaces import project_context
        if payload.project_id:
            state['active_project'] = project_context(state, payload.project_id)
        state['messages'] = [m for m in state['messages'] if m.get('project_id', '') == payload.project_id]
        if payload.document_ids:
            docs = [d for d in state['documents'] if d['id'] in payload.document_ids]
            if len(docs) != len(set(payload.document_ids)):
                raise HTTPException(404, 'Attachment not found.')
            if any(d.get('project_id', '') != payload.project_id for d in docs):
                raise HTTPException(422, 'Choose attachments from this project.')
            state['documents'] = docs
            state['explicit_attachments'] = True
        elif payload.project_id:
            state['documents'] = [d for d in state['documents'] if d.get('project_id') == payload.project_id]
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
            reply, proposals = respond(state, payload.text, execute=lambda name, args, call_id: tool_runtime().run(name, args, auth, payload.request_id+":"+call_id))
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
            current['messages'] += [{'id': uuid.uuid4().hex, 'request_id': payload.request_id, 'role': 'user', 'project_id': payload.project_id, 'document_ids': payload.document_ids, 'text': payload.text, 'created_at': now()},
                                    {'id': uuid.uuid4().hex, 'request_id': payload.request_id, 'role': 'assistant', 'project_id': payload.project_id, 'text': reply, 'created_at': now()}]
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


def companion_operation(state, kind, p, auth):
    device = next((d for d in state['devices'] if d['id'] == auth.get('device_id') and not d.get('revoked')), None)
    if not device: raise HTTPException(403, 'Use a paired phone for companion settings.')
    if kind == 'companion.push':
        token = p.get('token', '')
        if token and not re.fullmatch(r'(?:Exponent|Expo)PushToken\[[A-Za-z0-9_-]{10,200}\]', token):
            raise HTTPException(422, 'Invalid Expo push token.')
        if token: device['push_token'] = token
        else: device.pop('push_token', None)
        device['private_notifications'] = bool(p.get('private', True))
    elif kind == 'companion.weather':
        if not p.get('enabled'):
            device.pop('weather', None); device.pop('forecast', None)
        else:
            if p.get('source') not in ('city', 'location'): raise HTTPException(422, 'Choose city or location.')
            if p['source'] == 'location' and not device['permissions'].get('location'): raise HTTPException(403, 'Location sharing is disabled.')
            for key, low, high in [('latitude', -90, 90), ('longitude', -180, 180), ('rain', 1, 100), ('heat', 15, 55), ('wind', 10, 150)]:
                if type(p.get(key)) not in (int, float) or not low <= p[key] <= high: raise HTTPException(422, 'Invalid weather setting: '+key)
            device['weather'] = {k: p[k] for k in ('latitude', 'longitude', 'rain', 'heat', 'wind', 'source')}
            device['weather'].update(enabled=True, updated=time.time(), label=clean_text(p.get('label', 'Your area'), 80), briefings=bool(p.get('briefings', True)))
            device.pop('forecast', None)
    elif kind == 'companion.alert.read':
        for a in state.get('alerts', []):
            if a['device_id'] == device['id'] and (p.get('id') == a['id'] or p.get('all') is True): a['read'] = True
    elif kind == 'companion.alert.clear':
        state['alerts'] = [a for a in state.get('alerts', []) if a['device_id'] != device['id']]
    elif kind == 'companion.push.test':
        alert(state, device['id'], 'test:'+uuid.uuid4().hex, 'ORA · Push test', 'Your remote notification reached this phone.', 'alerts')
    else: raise HTTPException(422, 'Unknown companion operation.')
    return {'ok': True}


@app.post('/api/v2/weather/refresh')
def refresh_weather(auth=Depends(identity)):
    if not auth.get('device_id'): raise HTTPException(403, 'Use a paired phone.')
    limited('weather:'+auth['id'], 4)
    try: return {'forecast': weather_check(db(), auth['device_id'])}
    except Exception: raise HTTPException(503, 'Weather is temporarily unavailable. Your previous forecast is retained.')


@app.post('/api/companion/tick')
def companion_tick(authorization: str = Header(default='')):
    token = os.getenv('ORA_CRON_TOKEN', '')
    if len(token) < 32 or not hmac.compare_digest(authorization, 'Bearer '+token):
        raise HTTPException(401, 'Invalid scheduler credentials.')
    # A persistent lease prevents overlapping jobs, including across process restarts.
    def claim(s):
        if s.get('cron_lease', 0) > time.time(): return False
        s['cron_lease'] = time.time()+600
        s['scheduler_at'] = now()
        return True
    if not db().mutate(claim): return {'busy': True}
    try:
        failures = 0
        for device in db().read()['devices'][:10]:
            try: weather_check(db(), device['id'])
            except Exception: failures += 1
        from mini.routines import tick_routines
        tick_routines(db())
        sent = dispatch(db())
        return {'processed': sent, 'weather_failures': failures}
    finally:
        db().mutate(lambda s: s.update(cron_lease=0))


def tool_operation(state, kind, payload, request_id, auth):
    return apply_operation(state, Operation(kind=kind,payload=payload,request_id=request_id), auth)


def tool_runtime():
    return Runtime(db(), tool_operation)


class ToolCall(BaseModel):
    name: str = Field(max_length=80)
    args: dict = Field(default_factory=dict)
    request_id: str = Field(min_length=16, max_length=150)


class ToolDecision(BaseModel):
    reject: bool = False


@app.get('/api/v2/tools')
def list_tools(auth=Depends(identity)):
    state=db().read()
    return {'tools': [dict(t, enabled=t['name'] not in state.get('disabled_tools',[])) for t in catalog()],
            'runs': [public_run(r, preview=True) for r in state.get('tool_runs',[]) if visible(r,auth)][-40:],
            'repositories': allowed_repos(), 'documents': [file_metadata(d) for d in state['documents']]}


@app.post('/api/v2/tools/run')
def run_tool(payload: ToolCall, auth=Depends(identity)):
    limited('tools:'+auth['id'],30)
    return tool_runtime().run(payload.name,payload.args,auth,payload.request_id)


@app.post('/api/v2/tools/actions/{run_id}')
def approve_tool(run_id: str, payload: ToolDecision, auth=Depends(identity)):
    limited('tool-approval:'+auth['id'],15)
    return tool_runtime().approve(run_id,auth,payload.reject)


@app.post('/api/v2/tools/settings')
def tool_settings(payload: dict, auth=Depends(owner)):
    name=payload.get('name')
    if name not in BY_NAME or type(payload.get('enabled')) is not bool:raise HTTPException(422,'Invalid tool setting.')
    def update(s):
        disabled=set(s.get('disabled_tools',[]))
        if payload['enabled']:disabled.discard(name)
        else:disabled.add(name)
        s['disabled_tools']=sorted(disabled)
        return {'ok':True}
    return db().mutate(update)


@app.post('/api/v2/routines/{routine_id}/disable')
def disable_routine(routine_id: str, auth=Depends(identity)):
    def update(s):
        r=next((r for r in s.get('routines',[]) if r['id']==routine_id and (not auth.get('device_id') or r.get('device_id')==auth['device_id'])),None)
        if not r:raise HTTPException(404,'Routine not found.')
        r['enabled']=False
        return {'ok':True}
    return db().mutate(update)


@app.get('/api/v2/documents/{document_id}/download')
def download_document(document_id: str, auth=Depends(identity)):
    from fastapi.responses import Response
    d=next((d for d in db().read()['documents'] if d['id']==document_id),None)
    if not d:raise HTTPException(404,'Document not found.')
    try:data,mime,name=render_file(d)
    except ValueError as exc:raise HTTPException(422,str(exc))
    return Response(data,media_type=mime,headers={'Content-Disposition':f'attachment; filename="{name}"',
                                                   'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})


@app.get('/api/v2/tools/runs/{run_id}')
def tool_result(run_id: str, auth=Depends(identity)):
    run=next((r for r in db().read().get('tool_runs',[]) if r['id']==run_id and visible(r,auth)),None)
    if not run:raise HTTPException(404,'Tool result not found.')
    return run


from mini.workspaces import install as install_workspaces
install_workspaces(app, db, identity, limited)
from mini.desktop import install as install_desktop
install_desktop(app, db, identity, owner, limited)
