"""Owner-consented Google Workspace OAuth; encrypted credentials never leave the server."""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from urllib.parse import urlencode, urlparse

import requests
from cryptography.fernet import Fernet, InvalidToken
from fastapi import Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

SCOPES = [
    'https://www.googleapis.com/auth/userinfo.email',
    'https://www.googleapis.com/auth/calendar.readonly',
    'https://www.googleapis.com/auth/calendar.events',
    'https://www.googleapis.com/auth/drive.readonly',
    'https://www.googleapis.com/auth/documents',
    'https://www.googleapis.com/auth/spreadsheets',
]
_db = None
COOKIE = 'ora_google_oauth'
CALLBACK_PATH = '/api/v2/google/callback'
CHECKS = (
    ('GOOGLE_CLIENT_ID', 'OAuth client ID',
     'Google Cloud Console → Clients → the Web application client you created.'),
    ('GOOGLE_CLIENT_SECRET', 'OAuth client secret',
     'The secret shown beside that same Web application client.'),
    ('GOOGLE_REDIRECT_URI', 'Redirect URI',
     'Exactly https://<backend-host>/api/v2/google/callback and registered on that client. '
     'This is the Render backend address, not the Vercel site.'),
    ('ORA_GOOGLE_TOKEN_KEY', 'Token encryption key',
     'A Fernet key from python -c "from cryptography.fernet import Fernet; '
     'print(Fernet.generate_key().decode())". Keep it stable; changing it requires reconnecting.'),
)


def hash_value(value):
    return hashlib.sha256(value.encode()).hexdigest()


def client_id():
    # Env values are frequently pasted with a trailing space or newline; Google
    # rejects those as an invalid_client with no useful message.
    return os.getenv('GOOGLE_CLIENT_ID', '').strip()


def client_secret():
    return os.getenv('GOOGLE_CLIENT_SECRET', '').strip()


def cipher():
    try:
        return Fernet(os.getenv('ORA_GOOGLE_TOKEN_KEY', '').strip().encode())
    except (ValueError, TypeError):
        raise HTTPException(503, 'Google token encryption is not configured.') from None


def seal(value):
    return cipher().encrypt(json.dumps(value).encode()).decode()


def unseal(value):
    try:
        return json.loads(cipher().decrypt(value.encode()))
    except (InvalidToken, ValueError, TypeError, AttributeError):
        raise HTTPException(503, 'Google connection must be renewed.') from None


def redirect_uri():
    # Google compares the redirect URI byte for byte, so trim copy/paste padding
    # and an accidental trailing slash rather than reporting a silent mismatch.
    return os.getenv('GOOGLE_REDIRECT_URI', '').strip().rstrip('/')


def redirect_problem():
    raw = os.getenv('GOOGLE_REDIRECT_URI', '').strip()
    if not raw:
        return 'missing'
    parsed = urlparse(redirect_uri())
    if (parsed.scheme != 'https' or not parsed.netloc or parsed.path != CALLBACK_PATH
            or parsed.query or parsed.fragment):
        return 'invalid'
    return ''


def key_problem():
    if not os.getenv('ORA_GOOGLE_TOKEN_KEY', '').strip():
        return 'missing'
    try:
        cipher()
    except HTTPException:
        return 'invalid'
    return ''


def origin_hint(request=None):
    """Best-known public backend origin, used only to suggest a redirect URI."""
    redirect = redirect_uri()
    if redirect.endswith(CALLBACK_PATH):
        return redirect[:-len(CALLBACK_PATH)]
    external = os.getenv('RENDER_EXTERNAL_URL', '').strip().rstrip('/')
    if external:
        return external
    base = str(getattr(request, 'base_url', '') or '').rstrip('/')
    if base.startswith('http://') and not any(h in base for h in ('localhost', '127.0.0.1')):
        base = 'https://' + base[len('http://'):]
    return base


def problems():
    found = {}
    for key in ('GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_SECRET'):
        if not os.getenv(key, '').strip():
            found[key] = 'missing'
    for key, problem in (('GOOGLE_REDIRECT_URI', redirect_problem()),
                         ('ORA_GOOGLE_TOKEN_KEY', key_problem())):
        if problem:
            found[key] = problem
    return found


def configured():
    return not problems()


def setup_detail(origin=''):
    """Secret-free readiness: which settings are missing and what to paste where.

    Only key names, booleans and the (owner-visible) redirect URI leave the server,
    never credential values.
    """
    found = problems()
    return {
        'ready': not found,
        'problems': found,
        'redirect_uri': redirect_uri(),
        'expected_redirect_uri': (origin.rstrip('/') + CALLBACK_PATH) if origin else '',
        'checks': [{'key': key, 'label': label, 'hint': hint, 'state': found.get(key, 'ok')}
                   for key, label, hint in CHECKS],
    }


# Cheap, read-only probes. Docs and Sheets have no list endpoint, so an
# intentionally unknown file ID distinguishes "API disabled" (403) from
# "no such file" (404), without touching any real document.
PROBES = (
    ('Calendar API', 'https://www.googleapis.com/calendar/v3/users/me/calendarList',
     {'maxResults': '1'}),
    ('Drive API', 'https://www.googleapis.com/drive/v3/about', {'fields': 'user'}),
    ('Docs API', 'https://docs.googleapis.com/v1/documents/ora-probe-unknown-id', None),
    ('Sheets API', 'https://sheets.googleapis.com/v4/spreadsheets/ora-probe-unknown-id', None),
)


def api_enabled(name, url, params, token):
    response = requests.get(url, headers={'Authorization': 'Bearer ' + token},
                            params=params, timeout=(5, 10))
    if response.status_code == 403:
        try:
            reason = response.json().get('error', {}).get('errors', [{}])[0].get('reason', '')
        except (ValueError, AttributeError, IndexError, TypeError):
            reason = ''
        if reason in ('accessNotConfigured', 'SERVICE_DISABLED'):
            return False
    return True


def probe_apis(token):
    try:
        return [{'api': name, 'enabled': api_enabled(name, url, params, token)}
                for name, url, params in PROBES]
    except requests.RequestException:
        # The authorization itself is already proven; a probe failure is not a
        # reason to report the connection as broken.
        return []


def credential():
    if _db is None:
        return None
    encoded = _db().read().get('google_private', {}).get('credential')
    return unseal(encoded) if encoded else None


def connected():
    try:
        c = credential()
        return bool(configured() and c and c.get('refresh_token') and set(SCOPES) <= set(c.get('scopes', [])))
    except Exception:
        # A missing key or unreachable workspace must report "not connected",
        # never break chat or the tool catalog.
        return False


def connection_id():
    if _db is None:
        return None
    return _db().read().get('google_private', {}).get('connection_id')


def token_post(data):
    try:
        response = requests.post('https://oauth2.googleapis.com/token', data=data, timeout=(5, 15))
        response.raise_for_status()
        result = response.json()
        if not result.get('access_token'):
            raise ValueError()
        return result
    except (requests.RequestException, ValueError):
        raise HTTPException(502, 'Google authorization failed. Reconnect Google from Connections.') from None


def access_token():
    c = credential()
    if not c or not connected():
        raise HTTPException(503, 'Connect Google in ORA Connections first.')
    # Refresh per request; never cache credentials in client data or tool results.
    result = token_post({'client_id': client_id(), 'client_secret': client_secret(),
                         'refresh_token': c['refresh_token'], 'grant_type': 'refresh_token'})
    return result['access_token']


def install(app, db, identity, owner, limited):
    global _db
    _db = db

    def valid_owner(state, session_id):
        from mini.store import now
        return any(s['id'] == session_id and not s.get('device_id') and s['expires_at'] > now()
                   for s in state['sessions'])

    @app.get('/api/v2/google/status')
    def status(request: Request, auth=Depends(identity)):
        c = None
        try:
            c = credential()
        except HTTPException:
            pass
        manage = not bool(auth.get('device_id'))
        detail = setup_detail(origin_hint(request) if manage else '')
        response = {'configured': detail['ready'], 'connected': connected(),
                    'email': c.get('email', '') if c else '',
                    'can_manage': manage,
                    'redirect_uri': detail['redirect_uri'] if manage else None,
                    'setup': detail if manage else {'ready': detail['ready'],
                                                    'problems': detail['problems']}}
        return response

    @app.get('/api/v2/google/check')
    def check(auth=Depends(owner)):
        """Owner-triggered probe: proves the stored token still works at Google."""
        limited('google-check:' + auth['id'], 10)
        if not connected():
            return {'ok': False, 'message': 'Connect Google in ORA Connections first.'}
        try:
            token = access_token()
            response = requests.get('https://www.googleapis.com/oauth2/v2/userinfo',
                                    headers={'Authorization': 'Bearer ' + token}, timeout=(5, 10))
        except (requests.RequestException, HTTPException) as error:
            message = error.detail if isinstance(error, HTTPException) else \
                'Google could not be reached just now. Check the backend connection and try again.'
            return {'ok': False, 'message': message}
        if not response.ok:
            return {'ok': False, 'message': 'Google rejected the saved authorization (HTTP %s). Reconnect Google.' % response.status_code}
        try:
            email = str(response.json().get('email', ''))[:254]
        except ValueError:
            email = ''
        apis = probe_apis(token)
        disabled = [item['api'] for item in apis if not item['enabled']]
        message = ('Google answered for this account. All four Workspace APIs are enabled.'
                   if not disabled else
                   'Google answered, but these APIs are not enabled in the Google Cloud project: '
                   + ', '.join(disabled) + '. Enable them, then retry.')
        return {'ok': not disabled, 'email': email, 'apis': apis, 'message': message}

    @app.post('/api/v2/google/connect')
    def connect(auth=Depends(owner)):
        limited('google-connect:' + auth['id'], 5)
        if not configured():
            raise HTTPException(503, 'Set GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI and ORA_GOOGLE_TOKEN_KEY on the backend.')
        ticket = secrets.token_urlsafe(32)
        def save(s):
            private = s.setdefault('google_private', {})
            private['generation'] = secrets.token_hex(16)
            private['pending'] = seal({'ticket': hash_value(ticket), 'session': auth['id'], 'expires': time.time() + 120})
        db().mutate(save)
        origin = redirect_uri().rsplit(CALLBACK_PATH, 1)[0]
        return {'url': origin + '/api/v2/google/start?' + urlencode({'ticket': ticket})}

    @app.get('/api/v2/google/start')
    def start(ticket: str = ''):
        if not ticket or len(ticket) > 100:
            raise HTTPException(400, 'Start Google connection from ORA Connections.')
        state_nonce, browser, verifier = (secrets.token_urlsafe(32) for _ in range(3))
        def claim(s):
            private = s.setdefault('google_private', {})
            if not private.get('pending'):
                raise HTTPException(400, 'Google connection expired. Start again.')
            pending = unseal(private['pending'])
            if (pending.get('expires', 0) < time.time() or not valid_owner(s, pending.get('session'))
                    or not hmac.compare_digest(pending.get('ticket', ''), hash_value(ticket))):
                raise HTTPException(400, 'Google connection link expired. Start again.')
            private['pending'] = seal({'state': hash_value(state_nonce), 'browser': hash_value(browser),
                                       'verifier': verifier, 'session': pending['session'], 'expires': time.time() + 600})
        db().mutate(claim)
        params = {'client_id': client_id(), 'redirect_uri': redirect_uri(),
                  'response_type': 'code', 'scope': ' '.join(SCOPES), 'access_type': 'offline',
                  'prompt': 'consent select_account', 'state': state_nonce,
                  'code_challenge': base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('='),
                  'code_challenge_method': 'S256'}
        response = RedirectResponse('https://accounts.google.com/o/oauth2/v2/auth?' + urlencode(params), status_code=303)
        response.set_cookie(COOKIE, browser, max_age=600, secure=True, httponly=True, samesite='lax', path='/api/v2/google')
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Referrer-Policy'] = 'no-referrer'
        return response

    @app.get('/api/v2/google/callback')
    def callback(request: Request, state: str = '', code: str = '', error: str = ''):
        browser = request.cookies.get(COOKIE, '')
        if not state or not browser or len(state) > 100 or len(code) > 4096:
            raise HTTPException(400, 'Invalid Google connection response. Start again from ORA.')
        def consume(s):
            private = s.setdefault('google_private', {})
            if not private.get('pending'):
                raise HTTPException(400, 'Google connection expired. Start again.')
            pending = unseal(private['pending'])
            if (pending.get('expires', 0) < time.time() or not valid_owner(s, pending.get('session'))
                    or not hmac.compare_digest(pending.get('state', ''), hash_value(state))
                    or not hmac.compare_digest(pending.get('browser', ''), hash_value(browser))):
                raise HTTPException(400, 'Google connection response expired or does not match this browser.')
            private.pop('pending', None)
            # Used to reject a callback racing with disconnect or another connection attempt.
            private['generation'] = hash_value(state)
            return pending
        pending = db().mutate(consume)
        message = 'Connection cancelled. Return to ORA Connections to try again.'
        if not error and code:
            result = token_post({'client_id': client_id(),
                                 'client_secret': client_secret(), 'code': code,
                                 'code_verifier': pending['verifier'], 'redirect_uri': redirect_uri(),
                                 'grant_type': 'authorization_code'})
            scopes = result.get('scope', '').split()
            if not result.get('refresh_token') or not set(SCOPES) <= set(scopes):
                raise HTTPException(400, 'Google did not grant all requested permissions or offline access. Reconnect and approve the requested services.')
            email = ''
            try:
                info = requests.get('https://www.googleapis.com/oauth2/v2/userinfo',
                                    headers={'Authorization': 'Bearer ' + result['access_token']}, timeout=(5, 10))
                if info.ok:
                    email = str(info.json().get('email', ''))[:254]
            except (requests.RequestException, ValueError):
                pass
            encrypted = seal({'refresh_token': result['refresh_token'], 'scopes': scopes, 'email': email})
            def save(s):
                private = s.setdefault('google_private', {})
                if private.get('generation') != hash_value(state) or not valid_owner(s, pending['session']):
                    raise HTTPException(409, 'Connection changed. Start again from ORA.')
                private['credential'] = encrypted
                private['connection_id'] = secrets.token_hex(16)
            db().mutate(save)
            message = 'Google connected. Return to ORA Connections and refresh status. Your paired phone can now use the same Google tools.'
        response = HTMLResponse('<!doctype html><html><head><title>ORA Google connection</title></head><body><h1>ORA</h1><p>' + message + '</p></body></html>')
        response.delete_cookie(COOKIE, path='/api/v2/google', secure=True, httponly=True, samesite='lax')
        response.headers.update({'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer',
                                 'Content-Security-Policy': "default-src 'none'; frame-ancestors 'none'"})
        return response

    @app.delete('/api/v2/google/connection')
    def disconnect(auth=Depends(owner)):
        def remove(s):
            return s.pop('google_private', {}).get('credential')
        encoded = db().mutate(remove)
        revoked = False
        if encoded:
            try:
                c = unseal(encoded)
                response = requests.post('https://oauth2.googleapis.com/revoke',
                                         data={'token': c['refresh_token']}, timeout=(5, 10))
                revoked = response.status_code == 200
            except (requests.RequestException, HTTPException):
                pass
        return {'disconnected': True, 'revoked_at_google': revoked,
                'message': 'Disconnected from ORA.' if revoked else 'Disconnected from ORA. You can also remove access in your Google Account permissions.'}
