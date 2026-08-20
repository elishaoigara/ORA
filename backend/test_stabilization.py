from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.dirname(__file__))


class SecurityTests(unittest.TestCase):
    def test_production_without_api_token_fails_closed(self):
        from security import is_authorized

        with patch("security._API_TOKEN", ""), patch("security._APP_ENV", "production"):
            self.assertFalse(is_authorized(None))
            self.assertFalse(is_authorized("anything"))

    def test_configured_token_uses_constant_time_comparison(self):
        from security import is_authorized

        with patch("security._API_TOKEN", "secret-token"):
            self.assertTrue(is_authorized("secret-token"))
            self.assertFalse(is_authorized("wrong-token"))


class SchedulerTests(unittest.TestCase):
    def test_disabled_optional_job_is_skipped(self):
        from ora_scheduler import _safe_run
        callback = Mock()

        _safe_run(callback, "google_sync", lambda: False)

        callback.assert_not_called()

    def test_enabled_optional_job_runs(self):
        from ora_scheduler import _safe_run
        callback = Mock()

        _safe_run(callback, "google_sync", lambda: True)

        callback.assert_called_once_with()


class ConversationTests(unittest.TestCase):
    def test_session_messages_round_trip(self):
        from conversation_history import ConversationHistory

        history = ConversationHistory()
        session_id = history.new_session()
        history.add(session_id, "user", "Remember this test message")
        history.add(session_id, "assistant", "I will keep it in this session.")
        messages = history.get_latest(session_id, limit=10)

        self.assertEqual([m["role"] for m in messages], ["user", "assistant"])
        self.assertEqual(messages[0]["content"], "Remember this test message")
        self.assertEqual(messages[1]["content"], "I will keep it in this session.")


if __name__ == "__main__":
    unittest.main()
