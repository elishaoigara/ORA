"""Secret-safe GitHub scheduler client regressions; no network requests."""
import importlib.util
import io
import json
import os
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'companion_tick.py'
spec = importlib.util.spec_from_file_location('companion_tick_script', SCRIPT)
tick = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tick)


class Response(io.BytesIO):
    def __init__(self, payload, status=200):
        super().__init__(json.dumps(payload).encode())
        self.status = status


class CompanionWorkflowTests(unittest.TestCase):
    env = {'ORA_BACKEND_URL': 'https://ora.example', 'ORA_CRON_TOKEN': 'x' * 32}

    def run_main(self, response=None, error=None):
        with patch.dict(os.environ, self.env, clear=True), patch.object(tick.urllib.request, 'build_opener') as opener:
            if error is not None:
                opener.return_value.open.side_effect = error
            else:
                opener.return_value.open.return_value = response
            with patch('builtins.print') as output:
                code = tick.main()
            text = '\n'.join(str(call.args[0]) for call in output.call_args_list)
            request = opener.return_value.open.call_args.args[0] if opener.return_value.open.call_args else None
            return code, text, request

    def test_success_sends_bounded_authenticated_post(self):
        code, text, request = self.run_main(Response({'ok': True, 'processed': 2, 'weather_failures': 0}))
        self.assertEqual(code, 0)
        self.assertIn('processed', text)
        self.assertEqual(request.full_url, 'https://ora.example/api/companion/tick')
        self.assertEqual(request.method, 'POST')
        self.assertEqual(request.data, b'')
        self.assertEqual(request.get_header('Authorization'), 'Bearer ' + 'x' * 32)
        self.assertNotIn('x' * 32, text)

    def test_busy_lease_is_a_successful_noop(self):
        code, text, _ = self.run_main(Response({'busy': True}))
        self.assertEqual(code, 0)
        self.assertIn('another tick holds the backend lease', text)

    def test_http_500_reports_actionable_error_without_updating_status_to_success(self):
        error = urllib.error.HTTPError('https://ora.example/api/companion/tick', 500, 'Internal Server Error', {}, Response({'detail': 'private-db-password'}))
        code, text, _ = self.run_main(error=error)
        self.assertEqual(code, 2)
        self.assertIn('HTTP 500', text)
        self.assertIn('Render logs', text)
        self.assertNotIn('private-db-password', text)

    def test_structured_stage_failure_is_reported_without_private_exception_text(self):
        payload = {'ok': False, 'processed': 1, 'weather_failures': 0,
                   'failed_stages': ['routines'], 'error_types': {'routines': 'RuntimeError'},
                   'detail': 'private-routine-detail', 'token': 'private-token'}
        error = urllib.error.HTTPError('https://ora.example/api/companion/tick', 503, 'Unavailable', {}, Response(payload))
        code, text, _ = self.run_main(error=error)
        self.assertEqual(code, 2)
        self.assertIn('routines', text)
        self.assertIn('RuntimeError', text)
        self.assertNotIn('private-routine-detail', text)
        self.assertNotIn('private-token', text)

    def test_unauthorized_guidance_does_not_echo_token(self):
        error = urllib.error.HTTPError('https://ora.example/api/companion/tick', 401, 'Unauthorized', {}, Response({'detail': 'Invalid scheduler credentials.'}))
        code, text, _ = self.run_main(error=error)
        self.assertEqual(code, 2)
        self.assertIn('does not match the Render backend', text)
        self.assertNotIn('x' * 32, text)

    def test_redirect_is_not_followed(self):
        error = urllib.error.HTTPError('https://ora.example/api/companion/tick', 302, 'Found', {}, Response({'detail': 'redirect'}))
        code, text, _ = self.run_main(error=error)
        self.assertEqual(code, 2)
        self.assertIn('HTTP 302', text)
        self.assertIsNone(tick.NoRedirect().redirect_request(None, None, 302, 'Found', {}, 'https://attacker.example'))

    def test_timeout_is_not_retried(self):
        code, text, _ = self.run_main(error=TimeoutError('private-url'))
        self.assertEqual(code, 3)
        self.assertIn('was not retried', text)
        self.assertNotIn('private-url', text)

    def test_invalid_success_body_is_not_reported_as_success(self):
        code, text, _ = self.run_main(Response({'unexpected': True}))
        self.assertEqual(code, 2)
        self.assertIn('Unexpected backend response', text)

    def test_legacy_http_200_with_weather_failures_is_not_reported_as_success(self):
        code, text, _ = self.run_main(Response({'processed': 0, 'weather_failures': 2}))
        self.assertEqual(code, 2)
        self.assertIn('weather failures', text)

    def test_missing_secrets_fail_clearly(self):
        with patch.dict(os.environ, {}, clear=True), patch('builtins.print') as output:
            self.assertEqual(tick.main(), 1)
        self.assertIn('Set ORA_BACKEND_URL and ORA_CRON_TOKEN', output.call_args.args[0])

    def test_backend_url_must_be_an_origin_not_a_duplicate_endpoint(self):
        with patch.dict(os.environ, {'ORA_BACKEND_URL': 'https://ora.example/api/companion/tick', 'ORA_CRON_TOKEN': 'x' * 32}), patch('builtins.print'):
            self.assertEqual(tick.main(), 1)

    def test_short_or_padded_token_fails_before_request(self):
        for token in ('short', ' ' + 'x' * 32 + ' '):
            with patch.dict(os.environ, {'ORA_BACKEND_URL': 'https://ora.example', 'ORA_CRON_TOKEN': token}), patch('builtins.print'):
                self.assertEqual(tick.main(), 1)

    def test_safe_summary_filters_unknown_fields_and_bounds_lengths(self):
        summary = tick.safe_summary({'processed': 1, 'failed_stages': ['ok', 5, 'x' * 100],
                                     'error_types': {'routines': 'RuntimeError', 'private': 'x' * 100},
                                     'secret': 'do-not-print'})
        self.assertEqual(summary['failed_stages'], ['ok'])
        self.assertEqual(summary['error_types'], {'routines': 'RuntimeError'})
        self.assertNotIn('secret', summary)


if __name__ == '__main__':
    unittest.main()
