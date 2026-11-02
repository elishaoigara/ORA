"""Regression coverage for deployment probes and companion readiness."""
import os
import unittest
from unittest.mock import patch
from uuid import uuid4
from datetime import datetime, timedelta, timezone

import test_mini
import next_api as api
from mini.intelligence import suggestions


class ReadinessTests(unittest.TestCase):
    setUp = test_mini.MiniTests.setUp
    tearDown = test_mini.MiniTests.tearDown
    phone = test_mini.MiniTests.phone
    op = test_mini.MiniTests.op
    state = test_mini.MiniTests.state

    def test_get_and_head_probes(self):
        for path in ('/', '/api/health'):
            self.assertEqual(self.client.get(path).status_code, 200)
            response = self.client.head(path)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.content, b'')

    def test_health_checks_storage_and_hides_connection_details(self):
        with patch.object(api.store, 'connect', side_effect=RuntimeError('private-db-password')):
            response = self.client.get('/api/health')
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('private-db-password', response.text)

    def test_readiness_requires_auth_and_distinguishes_configuration_from_delivery(self):
        self.assertEqual(self.client.get('/api/v2/readiness').status_code, 401)
        with patch.dict(os.environ, {'DEEPSEEK_API_KEY': 'private-ai-key', 'ORA_CRON_TOKEN': 'x' * 32}):
            response = self.client.get('/api/v2/readiness', headers=self.owner)
        self.assertTrue(response.json()['ai_configured'])
        self.assertTrue(response.json()['scheduler_configured'])
        self.assertIsNone(response.json()['scheduler_last_completed_at'])
        self.assertNotIn('private-ai-key', response.text)
        self.assertNotIn('x' * 32, response.text)

    def tick(self):
        with patch.dict(os.environ, {'ORA_CRON_TOKEN': 'x' * 32}):
            return self.client.post('/api/companion/tick', headers={'Authorization': 'Bearer ' + 'x' * 32})

    def test_scheduler_completion_is_only_written_after_dispatch(self):
        with patch.object(api, 'dispatch', return_value=0), patch('mini.routines.tick_routines'):
            response = self.tick()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['ok'])
        self.assertTrue(api.store.read()['scheduler_completed_at'])
        self.assertEqual(api.store.read()['cron_lease'], 0)
        api.store.mutate(lambda state: state.pop('scheduler_completed_at'))
        with patch.object(api, 'dispatch', side_effect=RuntimeError('private-db-password')), patch('mini.routines.tick_routines'):
            response = self.tick()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['failed_stages'], ['dispatch'])
        self.assertEqual(response.json()['error_types'], {'dispatch': 'RuntimeError'})
        self.assertNotIn('private-db-password', response.text)
        self.assertIsNone(api.store.read().get('scheduler_completed_at'))
        self.assertEqual(api.store.read()['cron_lease'], 0)

    def test_routine_failure_does_not_block_telegram_delivery(self):
        with patch('mini.routines.tick_routines', side_effect=RuntimeError('private-routine-detail')), \
                patch.object(api, 'telegram_check') as briefing, patch.object(api, 'dispatch', return_value=2) as send:
            response = self.tick()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['failed_stages'], ['routines'])
        self.assertEqual(response.json()['processed'], 2)
        briefing.assert_called_once()
        send.assert_called_once()
        self.assertNotIn('private-routine-detail', response.text)
        self.assertIsNone(api.store.read().get('scheduler_completed_at'))
        self.assertEqual(api.store.read()['scheduler_error']['stages'], ['routines'])

    def test_briefing_failure_does_not_block_queued_alert_dispatch(self):
        with patch('mini.routines.tick_routines'), patch.object(api, 'telegram_check', side_effect=ValueError('private-chat-id')), \
                patch.object(api, 'dispatch', return_value=1) as send:
            response = self.tick()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['failed_stages'], ['telegram_briefing'])
        self.assertEqual(response.json()['processed'], 1)
        send.assert_called_once()
        self.assertNotIn('private-chat-id', response.text)

    def test_weather_failure_does_not_block_other_stages(self):
        self.phone()
        with patch.object(api, 'weather_check', side_effect=RuntimeError('private-weather-detail')), \
                patch('mini.routines.tick_routines') as routines, patch.object(api, 'telegram_check') as briefing, \
                patch.object(api, 'dispatch', return_value=0) as send:
            response = self.tick()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['weather_failures'], 1)
        self.assertEqual(response.json()['failed_stages'], ['weather'])
        routines.assert_called_once()
        briefing.assert_called_once()
        send.assert_called_once()
        self.assertNotIn('private-weather-detail', response.text)

    def test_successful_tick_clears_previous_scheduler_error(self):
        api.store.mutate(lambda s: s.update(scheduler_error={'at': 'old', 'stages': ['routines'], 'error_types': {'routines': 'RuntimeError'}}))
        with patch('mini.routines.tick_routines'), patch.object(api, 'dispatch', return_value=0):
            response = self.tick()
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('scheduler_error', api.store.read())
        self.assertIsNone(self.client.get('/api/v2/readiness', headers=self.owner).json()['scheduler_last_error'])

    def test_lease_release_failure_is_reported_without_masking_stage_failure(self):
        original_mutate = api.store.mutate
        def mutate(fn, request_id=None):
            state = api.store.read()
            if state.get('cron_lease_owner') and fn(state) is None and state.get('cron_lease') == 0:
                raise RuntimeError('private-release-detail')
            return original_mutate(fn, request_id)
        with patch('mini.routines.tick_routines', side_effect=ValueError('private-routine-detail')), \
                patch.object(api, 'dispatch', return_value=0), patch.object(api.store, 'mutate', side_effect=mutate):
            response = self.tick()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['failed_stages'], ['routines', 'lease_release'])
        self.assertNotIn('private-release-detail', response.text)
        self.assertNotIn('private-routine-detail', response.text)

    def test_stale_tick_cannot_release_a_newer_lease(self):
        api.store.mutate(lambda s: s.update(cron_lease=9999999999, cron_lease_owner='newer-owner'))
        with patch.dict(os.environ, {'ORA_CRON_TOKEN': 'x' * 32}):
            response = self.client.post('/api/companion/tick', headers={'Authorization': 'Bearer ' + 'x' * 32})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['busy'])
        self.assertEqual(api.store.read()['cron_lease_owner'], 'newer-owner')

    def test_non_ascii_authorization_is_rejected_without_server_error(self):
        with patch.dict(os.environ, {'ORA_CRON_TOKEN': 'x' * 32}):
            response = self.client.post('/api/companion/tick', headers={'Authorization': ('Bearer ' + 'é' * 32).encode('latin-1')})
        self.assertEqual(response.status_code, 401)

    def test_phone_events_only_include_this_device(self):
        phone, device, _ = self.phone()
        other, other_device, _ = self.phone()
        expires = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        api.store.mutate(lambda state: state['events'].extend([
            {'id': 'one', 'device_id': device, 'expires_at': expires},
            {'id': 'two', 'device_id': other_device, 'expires_at': expires},
        ]))
        self.assertEqual([e['id'] for e in self.state(phone)['events']], ['one'])
        self.assertEqual([e['id'] for e in self.state(other)['events']], ['two'])
        self.assertEqual(len(self.state()['events']), 2)

    def test_empty_event_timestamp_is_validation_error(self):
        phone, _, _ = self.phone()
        response = self.client.post('/api/v2/events', headers=phone, json={
            'request_id': uuid4().hex, 'kind': 'notifications', 'text': 'hello', 'observed_at': '',
        })
        self.assertEqual(response.status_code, 422)

    def test_high_priority_wins_when_due_times_match(self):
        state = {'tasks': [
            {'title': 'Low', 'done': False, 'priority': 3, 'due_at': None},
            {'title': 'High', 'done': False, 'priority': 1, 'due_at': None},
        ]}
        self.assertEqual(suggestions(state)[0]['detail'], 'High')
