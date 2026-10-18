import copy
import os
import time
import unittest
from unittest.mock import patch, Mock
from urllib.parse import urlparse, parse_qs
from cryptography.fernet import Fernet
from fastapi import FastAPI, Depends, Header, HTTPException
from fastapi.testclient import TestClient
from mini import google_workspace as google
from mini import google_tools


class MemoryStore:
    def __init__(self):
        self.state = {'sessions': [{'id': 'owner', 'expires_at': '2999-01-01', 'device_id': None}]}
    def read(self):
        return copy.deepcopy(self.state)
    def mutate(self, fn):
        state = copy.deepcopy(self.state)
        result = fn(state)
        self.state = state
        return result


class GoogleTests(unittest.TestCase):
    def setUp(self):
        self.previous_db = google._db
        self.env = patch.dict(os.environ, {'GOOGLE_CLIENT_ID': 'client', 'GOOGLE_CLIENT_SECRET': 'secret',
            'GOOGLE_REDIRECT_URI': 'https://backend.test/api/v2/google/callback',
            'ORA_GOOGLE_TOKEN_KEY': Fernet.generate_key().decode()})
        self.env.start()
        self.store = MemoryStore()
        app = FastAPI()
        def identity(authorization: str = Header(default='')):
            if authorization not in ('owner', 'phone'):
                raise HTTPException(401)
            return {'id': 'owner', 'device_id': None if authorization == 'owner' else 'phone'}
        def owner(auth=Depends(identity)):
            if auth['device_id']:
                raise HTTPException(403)
            return auth
        google.install(app, lambda: self.store, identity, owner, lambda *_: None)
        self.client = TestClient(app, base_url='https://backend.test', follow_redirects=False)
        self.auth = {'Authorization': 'owner'}

    def tearDown(self):
        self.env.stop()
        google._db = self.previous_db

    def begin(self):
        result = self.client.post('/api/v2/google/connect', headers=self.auth)
        self.assertEqual(result.status_code, 200)
        start = self.client.get(result.json()['url'])
        self.assertEqual(start.status_code, 303)
        return result.json()['url'], parse_qs(urlparse(start.headers['location']).query)['state'][0]

    def test_owner_only_and_one_time_link(self):
        self.assertEqual(self.client.post('/api/v2/google/connect').status_code, 401)
        self.assertEqual(self.client.post('/api/v2/google/connect', headers={'Authorization': 'phone'}).status_code, 403)
        url, state = self.begin()
        self.assertEqual(self.client.get(url).status_code, 400)
        self.assertEqual(self.client.get('/api/v2/google/callback', params={'state': state, 'error': 'access_denied'}).status_code, 200)
        self.assertEqual(self.client.get('/api/v2/google/callback', params={'state': state, 'code': 'reuse'}).status_code, 400)

    def test_wrong_state_cannot_exchange_code(self):
        self.begin()
        with patch.object(google, 'token_post') as exchange:
            r = self.client.get('/api/v2/google/callback', params={'state': 'wrong', 'code': 'code'})
            self.assertEqual(r.status_code, 400)
            exchange.assert_not_called()

    def test_missing_cookie_cannot_exchange(self):
        _, state = self.begin()
        self.client.cookies.clear()
        with patch.object(google, 'token_post') as exchange:
            self.assertEqual(self.client.get('/api/v2/google/callback', params={'state': state, 'code': 'code'}).status_code, 400)
            exchange.assert_not_called()

    def test_success_encryption_status_and_disconnect(self):
        _, state = self.begin()
        token = {'refresh_token': 'private-refresh', 'access_token': 'private-access', 'scope': ' '.join(google.SCOPES)}
        with patch.object(google, 'token_post', return_value=token), patch.object(google.requests, 'get', return_value=Mock(ok=True, json=lambda: {'email': 'owner@example.com'})):
            self.assertEqual(self.client.get('/api/v2/google/callback', params={'state': state, 'code': 'code'}).status_code, 200)
        self.assertNotIn('private-refresh', str(self.store.state))
        status = self.client.get('/api/v2/google/status', headers=self.auth)
        self.assertTrue(status.json()['connected'])
        self.assertNotIn('private-', status.text)
        self.assertEqual(self.client.delete('/api/v2/google/connection', headers={'Authorization': 'phone'}).status_code, 403)
        with patch.object(google.requests, 'post', return_value=Mock(status_code=200)):
            self.assertTrue(self.client.delete('/api/v2/google/connection', headers=self.auth).json()['disconnected'])
        self.assertFalse(google.connected())

    def test_expired_or_revoked_session(self):
        _, state = self.begin()
        self.store.state['sessions'] = []
        self.assertEqual(self.client.get('/api/v2/google/callback', params={'state': state, 'code': 'code'}).status_code, 400)

    def test_sheet_rejects_unbounded_reads(self):
        for value in ['A:Z', 'Sheet1!A1:AZ200', 'Sheet1!A1:B201']:
            with self.assertRaises(HTTPException):
                google_tools.bounded_range(value)

    def test_sheet_stale_approval_does_not_write(self):
        with patch.object(google_tools, 'read', return_value={'values': [['changed']]}), patch.object(google_tools, 'call') as call:
            with self.assertRaises(HTTPException):
                google_tools.write('google.sheets.write', {'id': 'sheet123', 'range': 'A1:A1', 'rows': [['new']], 'before': {'values': [['old']]}})
            call.assert_not_called()

    def test_google_writes_wait_for_approval_and_account_change_blocks_them(self):
        from mini.tools import Runtime
        runtime = Runtime(self.store, lambda *args: None)
        with patch.object(google, 'connected', return_value=True), patch.object(google, 'connection_id', return_value='first'), patch.object(google_tools, 'write') as write:
            run = runtime.run('google.docs.create', {'title': 'Plan', 'text': 'Body'}, {'id': 'owner'}, 'request123')
            self.assertEqual(run['status'], 'awaiting_approval')
            write.assert_not_called()
        with patch.object(google, 'connected', return_value=True), patch.object(google, 'connection_id', return_value='different'), patch.object(google_tools, 'write') as write:
            result = runtime.approve(run['id'], {'id': 'owner'})
            self.assertEqual(result['status'], 'needs_review')
            write.assert_not_called()


if __name__ == '__main__':
    unittest.main()
