"""Regression gates for the Render Free budget work.

Render Free gives one 0.1-CPU, 512 MB instance and 750 workspace instance hours a
month. These tests protect the request-level behaviour that keeps usage low:
compressed snapshots, bodyless 304 replies for unchanged workspaces, and a health
probe that fails when storage is unreachable.

This module is self-contained (it imports only the app) so `test_mini` can import
the classes below and the existing CI gate runs them without a workflow edit.
"""
import os
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

os.environ.setdefault('APP_ENV', 'test')
os.environ.setdefault('ORA_API_TOKEN', 'test-key-not-a-secret')

from fastapi.testclient import TestClient

import next_api as api
from mini.store import Store


class _Workspace:
    """Fixture shared by both classes; mirrors test_mini without importing it."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        api.store = Store(url='', path=self.temp.name + '/db')
        api.rates.clear()
        self.client = TestClient(api.app)
        token = self.client.post(
            '/api/v2/session', json={'token': os.environ['ORA_API_TOKEN']}).json()['token']
        self.owner = {'Authorization': 'Bearer ' + token}

    def tearDown(self):
        self.temp.cleanup()

    def op(self, kind, payload, auth=None, rid=None):
        return self.client.post('/api/v2/operations', headers=auth or self.owner,
                                json={'kind': kind, 'payload': payload,
                                      'request_id': rid or uuid4().hex})

    def state(self, auth=None):
        return self.client.get('/api/v2/sync', headers=auth or self.owner).json()

    def phone(self):
        code = self.client.post('/api/v2/pairing-code', headers=self.owner).json()['code']
        paired = self.client.post('/api/v2/pair', json={'code': code}).json()
        return {'Authorization': 'Bearer ' + paired['token']}, paired['device_id']


class FreeTierTests(_Workspace, unittest.TestCase):
    def fill(self, count=12):
        """Write enough rows that the snapshot clears the gzip threshold."""
        for index in range(count):
            response = self.op('task.create', {
                'title': 'Detailed workspace task number %d with a representative title' % index,
                'due_at': '2030-09-05T18:00:00+03:00',
                'priority': 2,
            }, rid=uuid4().hex)
            self.assertEqual(response.status_code, 200)

    def test_snapshot_is_compressed(self):
        self.fill()
        response = self.client.get('/api/v2/sync', headers={**self.owner, 'Accept-Encoding': 'gzip'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get('content-encoding'), 'gzip')
        # httpx decodes transparently; the payload must still be the full snapshot.
        self.assertEqual(len(response.json()['tasks']), 12)

    def test_downloads_skip_compression(self):
        self.fill()
        response = self.client.get('/api/v2/documents/missing/download',
                                   headers={**self.owner, 'Accept-Encoding': 'gzip'})
        self.assertNotEqual(response.headers.get('content-encoding'), 'gzip')

    def test_unchanged_sync_returns_empty_304(self):
        self.fill()
        first = self.client.get('/api/v2/sync', headers=self.owner)
        etag = first.headers['etag']
        self.assertEqual(first.headers['cache-control'], 'private, no-cache')
        second = self.client.get('/api/v2/sync', headers={**self.owner, 'If-None-Match': etag})
        self.assertEqual(second.status_code, 304)
        self.assertEqual(second.content, b'')
        self.assertEqual(second.headers['etag'], etag)

    def test_etag_changes_after_a_mutation(self):
        before = self.client.get('/api/v2/sync', headers=self.owner).headers['etag']
        self.op('memory.save', {'text': 'The owner prefers short answers.'})
        response = self.client.get('/api/v2/sync', headers={**self.owner, 'If-None-Match': before})
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(response.headers['etag'], before)
        self.assertEqual(len(response.json()['memories']), 1)

    def test_phone_scope_has_its_own_etag(self):
        phone, _ = self.phone()
        owner = self.client.get('/api/v2/sync', headers=self.owner).headers['etag']
        self.assertNotEqual(self.client.get('/api/v2/sync', headers=phone).headers['etag'], owner)

    def test_health_fails_when_storage_is_unreachable(self):
        with patch.object(api.store, 'connect', side_effect=RuntimeError('private-db-password')):
            response = self.client.get('/api/health')
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('private-db-password', response.text)

    def test_health_reports_free_tier_flag(self):
        with patch.dict(os.environ, {'ORA_FREE_TIER': '1'}):
            body = self.client.get('/api/health').json()
        self.assertTrue(body['free_tier'])
        self.assertIn('ai_provider', body)


class StoreEfficiencyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(url='', path=self.temp.name + '/db')

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_mutation_is_visible_immediately(self):
        self.assertEqual(self.store.read()['memories'], [])
        self.store.mutate(lambda state: state['memories'].append({'id': 'm1', 'text': 'Remember this'}))
        # A cached read must never hide the owner's own write.
        self.assertEqual(len(self.store.read()['memories']), 1)

    def test_close_is_idempotent_and_reads_still_work(self):
        self.store.close()
        self.store.close()
        self.assertEqual(self.store.read()['revision'], 0)


if __name__ == '__main__':
    unittest.main()
