"""Provider contract regression tests; no real credentials or external calls."""
import os
import unittest
from unittest.mock import Mock, patch

from mini.intelligence import respond


def state():
    return dict(tasks=[], documents=[], events=[], memories=[], messages=[],
                settings={'timezone': 'Africa/Nairobi'})


class DeepSeekTests(unittest.TestCase):
    def test_chat_uses_deepseek_not_groq_credentials(self):
        response = Mock(ok=True)
        response.json.return_value = {'choices': [{'message': {'content': 'Hello'}}]}
        with patch.dict(os.environ, {'DEEPSEEK_API_KEY': 'deepseek-test', 'GROQ_API_KEY': 'groq-test'}, clear=True), patch('mini.tools.catalog', return_value=[]), patch('mini.intelligence.requests.post', return_value=response) as call:
            self.assertEqual(respond(state(), 'Hi'), ('Hello', []))
        self.assertEqual(call.call_args.args[0], 'https://api.deepseek.com/chat/completions')
        self.assertEqual(call.call_args.kwargs['headers']['Authorization'], 'Bearer deepseek-test')
        payload = call.call_args.kwargs['json']
        self.assertEqual(payload['model'], 'deepseek-flash')
        self.assertEqual(payload['thinking'], {'type': 'disabled'})
        self.assertIn('tools', payload)

    def test_groq_key_alone_does_not_enable_chat(self):
        with patch.dict(os.environ, {'GROQ_API_KEY': 'groq-test'}, clear=True), patch('mini.intelligence.requests.post') as call:
            with self.assertRaisesRegex(RuntimeError, 'DEEPSEEK_API_KEY'):
                respond(state(), 'Hi')
            call.assert_not_called()

    def test_model_override_and_failure_do_not_retry(self):
        with patch.dict(os.environ, {'DEEPSEEK_API_KEY': 'test', 'DEEPSEEK_MODEL': 'deepseek-v4-pro'}, clear=True), patch('mini.tools.catalog', return_value=[]), patch('mini.intelligence.requests.post', return_value=Mock(ok=False)) as call:
            with self.assertRaisesRegex(RuntimeError, 'unavailable'):
                respond(state(), 'Hi')
            call.assert_called_once()
            self.assertEqual(call.call_args.kwargs['json']['model'], 'deepseek-v4-pro')
