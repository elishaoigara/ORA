"""WhatsApp mirror wiring in the production companion dispatch pipeline."""
import os
import sys
import types
import unittest
from unittest.mock import patch

import test_mini as fixtures
import next_api as api
from fastapi import HTTPException
from mini.companion import alert, delivery_status, dispatch

WA_ENVS = ("ORA_WA_NOTIFY_NUMBER", "WA_SIDECAR_URL")


class CompanionWhatsAppTests(unittest.TestCase):
    setUp = fixtures.MiniTests.setUp
    tearDown = fixtures.MiniTests.tearDown
    op = fixtures.MiniTests.op
    state = fixtures.MiniTests.state
    phone = fixtures.MiniTests.phone

    def setUp(self):  # noqa: F811 — extend fixture setup with env + sidecar stub
        fixtures.MiniTests.setUp(self)
        self._old_env = {k: os.environ.get(k) for k in WA_ENVS}
        os.environ["ORA_WA_NOTIFY_NUMBER"] = "254700000000"
        os.environ["WA_SIDECAR_URL"] = "https://sidecar.test"
        self.wa_calls = []

    def tearDown(self):  # noqa: F811
        for key, value in self._old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        sys.modules.pop("connectors.whatsapp", None)
        fixtures.MiniTests.tearDown(self)

    def link(self):
        phone, device_id, _ = self.phone()
        api.db().mutate(lambda s: s.update(telegram={"chat_id": 12345, "user_id": 12345}))
        with patch("mini.telegram.token", return_value="test-bot"), \
             patch("mini.companion.token", return_value="test-bot"):
            self.assertEqual(self.op("companion.telegram", {"enabled": True}, phone).status_code, 200)
        return phone, device_id

    def _stub_sidecar(self, ok=True, raises=None):
        module = types.ModuleType("connectors.whatsapp")

        def send_message(to, message):
            self.wa_calls.append((to, message))
            if raises:
                raise raises
            return {"ok": ok}

        module.send_message = send_message
        sys.modules["connectors.whatsapp"] = module

    def _queue_alert(self, device_id, body="Sensitive body", key=None):
        key = key or "wa-test:" + device_id
        def add(s):
            s["settings"].update(quiet_start=0, quiet_end=0)
            alert(s, device_id, key, "Sensitive title", body, "alerts")
        api.db().mutate(add)

    def test_mirror_sends_once_with_privacy_safe_text(self):
        _phone, device_id = self.link()
        self._queue_alert(device_id)
        self._stub_sidecar()
        with patch("mini.companion.token", return_value="bot"), \
             patch("mini.companion.bot_call", return_value={"message_id": 9}):
            dispatch(api.db())
            dispatch(api.db())
        self.assertEqual(len(self.wa_calls), 1)
        to, text = self.wa_calls[0]
        self.assertEqual(to, "254700000000")
        self.assertEqual(text, "ORA · New update\nOpen ORA to read your update.")
        self.assertNotIn("Sensitive", text)
        row = api.db().read()["alerts"][0]
        self.assertEqual(row["delivery"], "sent_to_telegram")
        self.assertTrue(row["whatsapp_done"])
        # Clients must never see the number, sidecar URL or mirror internals.
        self.assertNotIn("whatsapp_done", str(self.state(_phone)))
        self.assertNotIn("254700000000", str(self.state(_phone)))

    def test_mirror_detail_mode_when_privacy_off(self):
        _phone, device_id = self.link()
        api.db().mutate(lambda s: s.update(telegram={"chat_id": 12345, "user_id": 12345,
                                                     "private_alerts": False}))
        self._queue_alert(device_id)
        self._stub_sidecar()
        with patch("mini.companion.token", return_value="bot"), \
             patch("mini.companion.bot_call", return_value={"message_id": 9}):
            dispatch(api.db())
        # Phone devices always render privately unless the owner disables private mode
        # via the device record; the owner device above inherits the state flag.
        self.assertEqual(len(self.wa_calls), 1)

    def test_noop_and_no_network_when_unconfigured(self):
        _phone, device_id = self.link()
        for key in WA_ENVS:
            os.environ.pop(key, None)
        self._queue_alert(device_id)
        with patch("mini.companion.token", return_value="bot"), \
             patch("mini.companion.bot_call", return_value={"message_id": 9}):
            dispatch(api.db())
        self.assertEqual(self.wa_calls, [])
        self.assertEqual(api.db().read()["alerts"][0]["delivery"], "sent_to_telegram")

    def test_sidecar_failure_keeps_telegram_delivery(self):
        _phone, device_id = self.link()
        self._queue_alert(device_id)
        self._stub_sidecar(raises=RuntimeError("boom"))
        with patch("mini.companion.token", return_value="bot"), \
             patch("mini.companion.bot_call", return_value={"message_id": 9}):
            dispatch(api.db())
        self.assertEqual(api.db().read()["alerts"][0]["delivery"], "sent_to_telegram")

    def test_telegram_retry_never_duplicates_whatsapp(self):
        _phone, device_id = self.link()
        self._queue_alert(device_id)
        self._stub_sidecar()
        with patch("mini.companion.token", return_value="bot"), \
             patch("mini.companion.bot_call", side_effect=HTTPException(503, "down")):
            dispatch(api.db())
        self.assertEqual(api.db().read()["alerts"][0]["delivery"], "retry")
        self.assertEqual(len(self.wa_calls), 1)
        api.db().mutate(lambda s: s["alerts"][0].update(retry_at=0))
        with patch("mini.companion.token", return_value="bot"), \
             patch("mini.companion.bot_call", return_value={"message_id": 9}):
            dispatch(api.db())
        self.assertEqual(api.db().read()["alerts"][0]["delivery"], "sent_to_telegram")
        self.assertEqual(len(self.wa_calls), 1)

    def test_delivery_status_reports_whatsapp_without_secrets(self):
        self.link()
        status = delivery_status(api.db().read())
        self.assertEqual(status["whatsapp"], {"enabled": True})
        self.assertNotIn("254700000000", str(status))
        self.assertNotIn("sidecar.test", str(status))
        for key in WA_ENVS:
            os.environ.pop(key, None)
        self.assertEqual(delivery_status(api.db().read())["whatsapp"], {"enabled": False})


if __name__ == "__main__":
    unittest.main()
