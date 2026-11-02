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

    def test_setup_reports_every_missing_setting_without_values(self):
        with patch.dict(os.environ, {}, clear=False):
            for key in ('GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_SECRET', 'GOOGLE_REDIRECT_URI', 'ORA_GOOGLE_TOKEN_KEY'):
                os.environ.pop(key, None)
            detail = google.setup_detail('https://backend.test/')
            self.assertFalse(detail['ready'])
            self.assertEqual(set(detail['problems']), {'GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_SECRET',
                                                       'GOOGLE_REDIRECT_URI', 'ORA_GOOGLE_TOKEN_KEY'})
            self.assertEqual(detail['expected_redirect_uri'], 'https://backend.test/api/v2/google/callback')
            self.assertTrue(all(check['state'] == 'missing' for check in detail['checks']))
            response = self.client.get('/api/v2/google/status', headers=self.auth)
            self.assertFalse(response.json()['configured'])
            self.assertEqual(len(response.json()['setup']['checks']), 4)

    def test_setup_marks_present_but_invalid_values(self):
        with patch.dict(os.environ, {'GOOGLE_CLIENT_ID': 'cid-should-not-leak',
                                     'GOOGLE_CLIENT_SECRET': 'csecret-should-not-leak',
                                     'GOOGLE_REDIRECT_URI': 'https://ora-tan-three.vercel.app/api/v2/google/callback',
                                     'ORA_GOOGLE_TOKEN_KEY': 'not-a-fernet-key'}):
            detail = google.setup_detail()
            self.assertFalse(detail['ready'])
            self.assertEqual(detail['problems'], {'ORA_GOOGLE_TOKEN_KEY': 'invalid'})
            status = self.client.get('/api/v2/google/status', headers=self.auth).text
            for secret in ('cid-should-not-leak', 'csecret-should-not-leak', 'not-a-fernet-key'):
                self.assertNotIn(secret, status)
        with patch.dict(os.environ, {'GOOGLE_REDIRECT_URI': 'http://backend.test/api/v2/google/callback',
                                     'ORA_GOOGLE_TOKEN_KEY': Fernet.generate_key().decode()}):
            self.assertEqual(google.redirect_problem(), 'invalid')

    def test_redirect_uri_and_credentials_are_trimmed(self):
        with patch.dict(os.environ, {'GOOGLE_CLIENT_ID': ' client ', 'GOOGLE_CLIENT_SECRET': ' secret\n',
                                     'GOOGLE_REDIRECT_URI': ' https://backend.test/api/v2/google/callback/ ',
                                     'ORA_GOOGLE_TOKEN_KEY': Fernet.generate_key().decode() + '\n'}):
            self.assertTrue(google.configured())
            self.assertEqual(google.redirect_uri(), 'https://backend.test/api/v2/google/callback')
            self.assertEqual(google.client_id(), 'client')
            self.assertEqual(google.client_secret(), 'secret')
            started = self.client.get(self.client.post('/api/v2/google/connect', headers=self.auth).json()['url'])
            query = parse_qs(urlparse(started.headers['location']).query)
            self.assertEqual(query['client_id'], ['client'])
            self.assertEqual(query['redirect_uri'], ['https://backend.test/api/v2/google/callback'])
        # A working configuration still reports ready once the moved key is back.
        self.assertTrue(google.configured())

    def test_check_probe_reports_google_reachability(self):
        _, state = self.begin()
        token = {'refresh_token': 'private-refresh', 'access_token': 'private-access', 'scope': ' '.join(google.SCOPES)}
        with patch.object(google, 'token_post', return_value=token), patch.object(google.requests, 'get', return_value=Mock(ok=True, json=lambda: {'email': 'owner@example.com'})):
            self.client.get('/api/v2/google/callback', params={'state': state, 'code': 'code'})
        with patch.object(google, 'access_token', return_value='fresh'), \
                patch.object(google.requests, 'get', return_value=Mock(ok=True, json=lambda: {'email': 'owner@example.com'})):
            result = self.client.get('/api/v2/google/check', headers=self.auth)
            self.assertTrue(result.json()['ok'])
            self.assertEqual(result.json()['email'], 'owner@example.com')
        with patch.object(google, 'access_token', return_value='fresh'), \
                patch.object(google.requests, 'get', return_value=Mock(ok=False, status_code=401)):
            result = self.client.get('/api/v2/google/check', headers=self.auth)
            self.assertFalse(result.json()['ok'])
            self.assertIn('Reconnect', result.json()['message'])
        self.assertEqual(self.client.get('/api/v2/google/check', headers={'Authorization': 'phone'}).status_code, 403)

    def test_check_reports_disabled_cloud_apis(self):
        _, state = self.begin()
        token = {'refresh_token': 'private-refresh', 'access_token': 'private-access', 'scope': ' '.join(google.SCOPES)}
        with patch.object(google, 'token_post', return_value=token), patch.object(google.requests, 'get', return_value=Mock(ok=True, json=lambda: {'email': 'owner@example.com'})):
            self.client.get('/api/v2/google/callback', params={'state': state, 'code': 'code'})

        def fake_get(url, **_):
            if 'sheets' in url:
                return Mock(status_code=403, ok=False,
                            json=lambda: {'error': {'errors': [{'reason': 'accessNotConfigured'}]}})
            return Mock(status_code=200, ok=True, json=lambda: {'email': 'owner@example.com'})

        with patch.object(google, 'access_token', return_value='fresh'), \
                patch.object(google.requests, 'get', side_effect=fake_get):
            result = self.client.get('/api/v2/google/check', headers=self.auth).json()
        self.assertFalse(result['ok'])
        self.assertIn('Sheets API', result['message'])
        self.assertEqual({item['api']: item['enabled'] for item in result['apis']},
                         {'Calendar API': True, 'Drive API': True, 'Docs API': True, 'Sheets API': False})


if __name__ == '__main__':
    unittest.main()
