"""WhatsApp channel wiring in intelligence.notifier.

Runs without third-party deps: connectors.whatsapp / telegram_bot / fcm are
stubbed in sys.modules before their lazy imports happen inside notifier.
"""
import os
import sys
import types
import unittest
from unittest import mock

os.environ.setdefault("APP_ENV", "test")

from intelligence import notifier


class WhatsAppNotifyTests(unittest.TestCase):
    def setUp(self):
        self._old_env = os.environ.get("ORA_WA_NOTIFY_NUMBER")
        self.calls = []

    def tearDown(self):
        if self._old_env is None:
            os.environ.pop("ORA_WA_NOTIFY_NUMBER", None)
        else:
            os.environ["ORA_WA_NOTIFY_NUMBER"] = self._old_env
        sys.modules.pop("connectors.whatsapp", None)

    def _stub_whatsapp(self, result=None, raises=None):
        module = types.ModuleType("connectors.whatsapp")

        def send_message(to, message):
            self.calls.append((to, message))
            if raises:
                raise raises
            return result if result is not None else {"ok": True}

        module.send_message = send_message
        sys.modules["connectors.whatsapp"] = module
        return module

    def test_noop_without_env_number(self):
        os.environ.pop("ORA_WA_NOTIFY_NUMBER", None)
        result = notifier.whatsapp_notify("hello")
        self.assertFalse(result)
        self.assertEqual(self.calls, [])

    def test_sends_to_configured_number(self):
        os.environ["ORA_WA_NOTIFY_NUMBER"] = "254700000000"
        self._stub_whatsapp({"ok": True})
        result = notifier.whatsapp_notify("hello owner")
        self.assertTrue(result)
        self.assertEqual(self.calls, [("254700000000", "hello owner")])

    def test_sidecar_error_is_swallowed(self):
        os.environ["ORA_WA_NOTIFY_NUMBER"] = "254700000000"
        self._stub_whatsapp({"ok": False, "error": "WA_SIDECAR_URL not set"})
        self.assertFalse(notifier.whatsapp_notify("hi"))

    def test_exception_never_propagates(self):
        os.environ["ORA_WA_NOTIFY_NUMBER"] = "254700000000"
        self._stub_whatsapp(raises=RuntimeError("sidecar down"))
        self.assertFalse(notifier.whatsapp_notify("hi"))

    def test_blank_env_is_noop(self):
        os.environ["ORA_WA_NOTIFY_NUMBER"] = "   "
        self.assertFalse(notifier.whatsapp_notify("hi"))


class DualNotifyWhatsAppTests(unittest.TestCase):
    def setUp(self):
        self._old_env = os.environ.get("ORA_WA_NOTIFY_NUMBER")
        os.environ["ORA_WA_NOTIFY_NUMBER"] = "254700000000"
        self.sent = {"telegram": [], "whatsapp": [], "fcm": []}

        tg = types.ModuleType("telegram_bot")
        tg.notify = lambda text, is_alert=False: self.sent["telegram"].append(text)
        sys.modules["telegram_bot"] = tg

        wa = types.ModuleType("connectors.whatsapp")
        wa.send_message = lambda to, message: (
            self.sent["whatsapp"].append((to, message)) or {"ok": True}
        )
        sys.modules["connectors.whatsapp"] = wa

        fcm = types.ModuleType("fcm")
        fcm.send_push = lambda title, body, data=None, is_alert=False: (
            self.sent["fcm"].append((title, body)) or True
        )
        sys.modules["fcm"] = fcm

    def tearDown(self):
        if self._old_env is None:
            os.environ.pop("ORA_WA_NOTIFY_NUMBER", None)
        else:
            os.environ["ORA_WA_NOTIFY_NUMBER"] = self._old_env
        for name in ("telegram_bot", "connectors.whatsapp", "fcm"):
            sys.modules.pop(name, None)

    def test_all_three_channels_receive_message(self):
        notifier.dual_notify(title="ORA", body="test body")
        self.assertEqual(self.sent["telegram"], ["*ORA*\ntest body"])
        self.assertEqual(self.sent["whatsapp"], [("254700000000", "*ORA*\ntest body")])
        self.assertEqual(self.sent["fcm"], [("ORA", "test body")])

    def test_whatsapp_failure_does_not_block_fcm(self):
        def broken(to, message):
            raise RuntimeError("sidecar offline")

        sys.modules["connectors.whatsapp"].send_message = broken
        notifier.dual_notify(title="ORA", body="still delivered")
        self.assertEqual(self.sent["fcm"], [("ORA", "still delivered")])

    def test_no_whatsapp_when_not_configured(self):
        os.environ.pop("ORA_WA_NOTIFY_NUMBER", None)
        notifier.dual_notify(title="ORA", body="quiet on wa")
        self.assertEqual(self.sent["whatsapp"], [])
        self.assertEqual(self.sent["fcm"], [("ORA", "quiet on wa")])


if __name__ == "__main__":
    unittest.main()
