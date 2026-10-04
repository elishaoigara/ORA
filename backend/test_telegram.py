"""Telegram pairing, webhook auth, retries and shared workspace regression tests."""
import os
import tempfile
import unittest
from unittest.mock import patch
from requests import ConnectionError as RequestConnectionError

os.environ['APP_ENV'] = 'test'
os.environ['ORA_API_TOKEN'] = 'telegram-test-owner-key'

from fastapi.testclient import TestClient
import next_api as api
from mini.store import Store
from mini.telegram import webhook_secret


class Reply:
    ok = True
    def __init__(self, result):
        self.result = result
    def json(self):
        return {'ok': True, 'result': self.result}


class TelegramTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        api.store = Store(url='', path=self.temp.name + '/db')
        api.rates.clear()
        self.env = patch.dict(os.environ, {'TELEGRAM_BOT_TOKEN': '123:testing',
                                           'ORA_PUBLIC_URL': 'https://ora.example'})
        self.env.start()
        self.sent = []
        self.webhook_url = ''
        self.fail_send = False
        self.provider = patch('mini.telegram.requests.post', side_effect=self.telegram_api)
        self.provider.start()
        self.client = TestClient(api.app)
        token = self.client.post('/api/v2/session', json={'token': os.environ['ORA_API_TOKEN']}).json()['token']
        self.owner = {'Authorization': 'Bearer ' + token}

    def tearDown(self):
        self.provider.stop()
        self.env.stop()
        self.temp.cleanup()

    def telegram_api(self, url, data=None, json=None, files=None, timeout=None):
        method = url.rsplit('/', 1)[-1]
        payload = data if files else json
        if method == 'getMe':
            return Reply({'id': 777, 'is_bot': True, 'username': 'ora_test_bot'})
        if method == 'setWebhook':
            self.webhook_url = payload['url']
            self.assertEqual(payload['secret_token'], webhook_secret())
            self.assertEqual(payload['allowed_updates'], ['message'])
            return Reply(True)
        if method == 'getWebhookInfo':
            return Reply({'url': self.webhook_url, 'pending_update_count': 0})
        if method in ('sendMessage', 'sendDocument'):
            if self.fail_send:
                self.fail_send = False
                raise RequestConnectionError('Simulated Telegram outage')
            self.sent.append((method, payload, files))
            return Reply({'message_id': len(self.sent)})
        raise AssertionError('Unexpected Telegram API method: ' + method)

    def update(self, update_id, user=11, text='/start', chat_type='private'):
        message = {'from': {'id': user, 'first_name': 'Owner'},
                   'chat': {'id': user, 'type': chat_type}, 'text': text}
        return self.client.post('/api/v2/telegram/webhook',
                                headers={'X-Telegram-Bot-Api-Secret-Token': webhook_secret()},
                                json={'update_id': update_id, 'message': message})

    def pair(self):
        self.assertEqual(self.client.post('/api/v2/telegram/setup', headers=self.owner).status_code, 200)
        code = self.client.post('/api/v2/telegram/pairing-code', headers=self.owner).json()['code']
        self.assertEqual(self.update(100, text='/start ' + code).status_code, 200)
        return code

    def test_owner_only_setup_and_one_time_private_pairing(self):
        self.assertEqual(self.client.post('/api/v2/telegram/setup').status_code, 401)
        self.assertEqual(self.update(1, text='Hello').status_code, 200)
        self.assertEqual(self.client.post('/api/v2/telegram/webhook', json={}).status_code, 403)
        code = self.pair()
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.update(100, text='/start ' + code).status_code, 200)
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.update(101, user=22, text='/start ' + code).status_code, 200)
        self.assertEqual(self.update(102, user=22, text='/tasks').status_code, 200)
        self.assertEqual(self.update(103, text='/tasks', chat_type='group').status_code, 200)
        self.assertEqual(len(self.sent), 1)
        self.assertNotIn('telegram', self.client.get('/api/v2/sync', headers=self.owner).json())
        self.assertTrue(self.client.get('/api/v2/telegram/status', headers=self.owner).json()['linked'])
        self.assertEqual(self.client.delete('/api/v2/telegram/link', headers=self.owner).status_code, 200)
        self.assertEqual(self.update(104, text='/tasks').status_code, 200)
        self.assertEqual(len(self.sent), 1)

    def test_chat_and_approval_share_workspace_once(self):
        self.pair()
        with patch.object(api, 'respond', return_value=('I prepared a reminder.', [
            {'kind': 'task', 'payload': {'title': 'Call home', 'due_at': '', 'priority': 2}}])) as model:
            self.assertEqual(self.update(110, text='Remind me to call home').status_code, 200)
            self.assertEqual(self.update(110, text='Remind me to call home').status_code, 200)
            model.assert_called_once()
        state = self.client.get('/api/v2/sync', headers=self.owner).json()
        self.assertEqual(len(state['messages']), 2)
        self.assertEqual(len(state['actions']), 1)
        self.assertEqual(len(self.sent), 2)
        self.assertIn('Tools & activity', self.sent[-1][1]['text'])
        action = state['actions'][0]
        self.client.post('/api/v2/operations', headers=self.owner,
                         json={'request_id': 'approval-for-telegram-task',
                               'kind': 'action.approve', 'payload': {'id': action['id']}})
        self.assertEqual(self.update(111, text='/tasks').status_code, 200)
        self.assertIn('Call home', self.sent[-1][1]['text'])

    def test_delivery_retry_does_not_repeat_ai(self):
        self.pair()
        self.fail_send = True
        with patch.object(api, 'respond', return_value=('A durable reply.', [])) as model:
            self.assertEqual(self.update(120, text='Hi ORA').status_code, 503)
            self.assertEqual(self.update(120, text='Hi ORA').status_code, 200)
            model.assert_called_once()
        self.assertEqual(self.sent[-1][1]['text'], 'A durable reply.')

    def test_file_download_and_wrong_bot_reset(self):
        self.pair()
        api.store.mutate(lambda s: s['documents'].append(
            {'id': 'file123', 'name': 'plan.pdf', 'created_at': '2026-01-01T00:00:00+00:00',
             'text': 'A plan', 'format': 'pdf'}))
        self.assertEqual(self.update(130, text='/files').status_code, 200)
        self.assertIn('/file file123', self.sent[-1][1]['text'])
        with patch('mini.telegram.render_file', return_value=(b'%PDF', 'application/pdf', 'plan.pdf')):
            self.assertEqual(self.update(131, text='/file file123').status_code, 200)
        self.assertEqual(self.sent[-1][0], 'sendDocument')
        self.assertEqual(self.sent[-1][2]['document'][1], b'%PDF')
        api.store.mutate(lambda s: s['telegram'].update(bot_id=1234))
        self.client.post('/api/v2/telegram/setup', headers=self.owner)
        self.assertFalse(self.client.get('/api/v2/telegram/status', headers=self.owner).json()['linked'])


if __name__ == '__main__':
    unittest.main()
