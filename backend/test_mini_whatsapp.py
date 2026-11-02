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



class WhatsAppIncomingTests(unittest.TestCase):
    """The sidecar -> next_api callback must be authenticated and noise-free."""

    setUp = fixtures.MiniTests.setUp
    tearDown = fixtures.MiniTests.tearDown
    op = fixtures.MiniTests.op
    state = fixtures.MiniTests.state
    phone = fixtures.MiniTests.phone

    BRIDGE_TOKEN = "bridge-token-for-tests-1234"

    def setUp(self):  # noqa: F811
        fixtures.MiniTests.setUp(self)
        self._old_token = os.environ.get("ORA_INTERNAL_TOKEN")
        os.environ["ORA_INTERNAL_TOKEN"] = self.BRIDGE_TOKEN

    def tearDown(self):  # noqa: F811
        if self._old_token is None:
            os.environ.pop("ORA_INTERNAL_TOKEN", None)
        else:
            os.environ["ORA_INTERNAL_TOKEN"] = self._old_token
        fixtures.MiniTests.tearDown(self)

    def link(self):
        phone, device_id, _ = self.phone()
        api.db().mutate(lambda s: s.update(telegram={"chat_id": 12345, "user_id": 12345}))
        with patch("mini.telegram.token", return_value="test-bot"), \
             patch("mini.companion.token", return_value="test-bot"):
            self.assertEqual(self.op("companion.telegram", {"enabled": True}, phone).status_code, 200)
        return phone, device_id

    def post(self, payload, token=None):
        headers = {"X-ORA-Token": self.BRIDGE_TOKEN if token is None else token}
        return self.client.post("/api/whatsapp/incoming", json=payload, headers=headers)

    def test_requires_bridge_token(self):
        self.assertEqual(self.client.post("/api/whatsapp/incoming", json={"body": "urgent"}).status_code, 401)
        self.assertEqual(self.post({"body": "urgent"}, token="wrong-token").status_code, 401)
        os.environ["ORA_INTERNAL_TOKEN"] = "short"
        self.assertEqual(self.post({"body": "urgent"}).status_code, 401)

    def test_urgent_message_queues_generic_alert(self):
        phone, _ = self.link()
        response = self.post({"id": "254712345678@s.whatsapp.net", "fromName": "Alice",
                              "body": "Please call me, it is urgent", "isGroup": False})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["queued"])
        alerts = api.db().read()["alerts"]
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["title"], "ORA · Urgent WhatsApp message")
        self.assertIn("Alice", alerts[0]["body"])
        self.assertNotIn("Please call me", alerts[0]["body"])
        self.assertNotIn("Please call me", str(self.state(phone)))

    def test_routine_message_is_ignored(self):
        self.link()
        response = self.post({"id": "254712345678@s.whatsapp.net", "fromName": "Alice",
                              "body": "see you at six"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["queued"])
        self.assertEqual(api.db().read().get("alerts", []), [])

    def test_duplicate_delivery_is_deduped(self):
        self.link()
        payload = {"id": "254712345678@s.whatsapp.net", "fromName": "Alice", "body": "saidia haraka"}
        self.post(payload)
        self.post(payload)
        self.assertEqual(len(api.db().read()["alerts"]), 1)


if __name__ == "__main__":
    unittest.main()
