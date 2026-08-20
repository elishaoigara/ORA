"""Regression coverage for ORA Phase 6 typed tools and safety gateway."""

from __future__ import annotations

import os
import sys
import unittest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
from uuid import uuid4

sys.path.insert(0, os.path.dirname(__file__))


class TypedToolTests(unittest.TestCase):
    def test_write_tools_expose_typed_risk_and_approval_contracts(self):
        from tool_registry import registry

        specs = {item["name"]: item for item in registry.list_tools()}
        self.assertTrue(specs["gmail_send"]["requires_approval"])
        self.assertTrue(specs["gmail_reply"]["requires_approval"])
        self.assertTrue(specs["calendar_create"]["requires_approval"])
        self.assertTrue(specs["calendar_delete"]["requires_approval"])
        self.assertTrue(specs["gmail_draft"]["requires_approval"])
        self.assertEqual(specs["calendar_create"]["action_type"], "calendar.create")
        self.assertIn("to", specs["gmail_send"]["input_schema"])

    def test_gateway_validates_and_proposes_external_send(self):
        from tool_registry import registry

        invalid = registry.run("gmail_send", {"to": "not-enough"}, source="phase6_test")
        self.assertEqual(invalid["status"], "invalid_input")

        result = registry.run(
            "gmail_send",
            {"to": f"phase6-{uuid4().hex}@example.com", "subject": "Phase 6", "body": "Approval test"},
            source="phase6_test",
        )
        self.assertEqual(result["status"], "action_proposed")
        self.assertEqual(result["action"]["risk"], "external_communication")
        self.assertTrue(result["action"]["requires_approval"])

    def test_gmail_draft_is_proposed_and_records_receipt_after_approval(self):
        from tool_registry import registry

        payload = {
            "to": f"phase6-{uuid4().hex}@example.com",
            "subject": "Draft",
            "body": "Safe draft",
        }
        with patch("connectors.gmail.create_draft", return_value={"ok": True, "draft_id": "draft-phase6"}) as create_draft:
            result = registry.run("gmail_draft", payload, source="phase6_test")
            self.assertEqual(result["status"], "action_proposed")
            from action_ledger import approve_action, execute_action
            approved = approve_action(result["action"]["id"])
            completed = execute_action(approved["id"])

        self.assertEqual(completed["status"], "completed")
        self.assertEqual(completed["result"]["draft_id"], "draft-phase6")
        create_draft.assert_called_once()

    def test_calendar_create_is_a_proposal_and_does_not_mutate(self):
        from tool_registry import registry

        event = {
            "title": "Phase 6 event",
            "start": "2026-08-25T10:00:00+03:00",
            "end": "2026-08-25T11:00:00+03:00",
            "description": "typed proposal",
            "location": "Juja",
            "calendar_id": "primary",
            "reminders": [10],
        }
        with patch("connectors.calendar.parse_event_request", return_value={"ok": True, "event": event}), \
             patch("connectors.calendar.create_event", Mock()) as create_event:
            result = registry.run("calendar_create", {"text": "phase 6 event"}, source="phase6_test")

        self.assertEqual(result["status"], "action_proposed")
        self.assertEqual(result["action"]["action_type"], "calendar.create")
        create_event.assert_not_called()

    def test_gmail_reply_uses_thread_aware_action(self):
        from action_ledger import approve_action, execute_action
        from tool_registry import registry

        reply = {
            "id": 91,
            "sender": "sender@example.com",
            "subject": "Thread subject",
            "suggested_text": "Approved reply",
            "thread_id": "thread-91",
            "account": "primary",
            "updated_at": f"2026-08-20T10:00:00-{uuid4().hex}",
        }
        with patch("connectors.gmail.get_suggested_reply", return_value=reply):
            proposal = registry.run("gmail_reply", {"reply_id": 91}, source="phase6_test")
        self.assertEqual(proposal["status"], "action_proposed")
        self.assertEqual(proposal["action"]["action_type"], "gmail.send_reply")
        self.assertEqual(proposal["action"]["payload"]["thread_id"], "thread-91")

        with patch("connectors.gmail.send_reply", return_value={"ok": True, "reply_id": 91, "status": "sent"}) as send_reply:
            self.assertEqual(approve_action(proposal["action"]["id"])["status"], "approved")
            completed = execute_action(proposal["action"]["id"])
        self.assertEqual(completed["status"], "completed")
        send_reply.assert_called_once()


class LedgerLifecycleTests(unittest.TestCase):
    def test_expired_action_cannot_be_approved_or_executed(self):
        from action_ledger import approve_action, create_action, execute_action, get_action

        action = create_action(
            "phase6-expired",
            "gmail.send_new",
            "Expired action",
            payload={"to": "expired@example.com", "subject": "Expired", "body": "No send"},
            risk="external_communication",
            requires_approval=True,
            source="phase6_test",
            idempotency_key=f"phase6-expired:{uuid4().hex}",
            expires_at=(datetime.now() - timedelta(minutes=1)).isoformat(),
        )
        expired = get_action(action["id"])
        self.assertEqual(expired["status"], "cancelled")
        self.assertEqual(approve_action(action["id"])["status"], "cancelled")
        self.assertEqual(execute_action(action["id"])["status"], "cancelled")

    def test_failed_action_can_retry_only_within_limit(self):
        from action_ledger import create_action, retry_action, transition_action

        action = create_action(
            "phase6-retry",
            "test.action",
            "Retry action",
            risk="personal_change",
            source="phase6_test",
            idempotency_key=f"phase6-retry:{uuid4().hex}",
            max_retries=1,
        )
        transition_action(action["id"], "approved")
        failed = transition_action(action["id"], "failed", error="temporary")
        self.assertEqual(failed["retries"], 1)
        retried = retry_action(action["id"])
        self.assertEqual(retried["status"], "approved")
        exhausted = transition_action(action["id"], "failed", error="again")
        self.assertEqual(exhausted["retries"], 2)
        self.assertEqual(retry_action(action["id"])["status"], "failed")


class Phase6ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("APP_ENV", "development")
        os.environ.setdefault("ORA_API_TOKEN", "phase6-test-token")
        from fastapi.testclient import TestClient
        from api import app
        cls.client = TestClient(app)
        cls.headers = {"X-ORA-Token": "phase6-test-token"}

    def test_capabilities_tools_and_diagnostics(self):
        capabilities = self.client.get("/api/capabilities", headers=self.headers)
        self.assertEqual(capabilities.status_code, 200)
        body = capabilities.json()
        self.assertTrue(body["typed_tools"])
        self.assertIn("external_write", body["approval_required_for"])

        tools = self.client.get("/api/tools", headers=self.headers)
        self.assertEqual(tools.status_code, 200)
        self.assertTrue(any(tool["name"] == "gmail_reply" for tool in tools.json()))

        diagnostics = self.client.get("/api/diagnostics", headers=self.headers)
        self.assertEqual(diagnostics.status_code, 200)
        self.assertIn("scheduler", diagnostics.json())
        self.assertIn("actions", diagnostics.json())

    def test_tool_run_endpoint_returns_proposal_for_external_send(self):
        result = self.client.post(
            "/api/tools/gmail_send/run",
            headers=self.headers,
            json={"to": f"api-{uuid4().hex}@example.com", "subject": "Test", "body": "Approval"},
        )
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["status"], "action_proposed")


if __name__ == "__main__":
    unittest.main()
