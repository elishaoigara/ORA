"""Regression coverage for ORA Phase 5 trust and approval controls."""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

sys.path.insert(0, os.path.dirname(__file__))


class MemoryTrustTests(unittest.TestCase):
    def test_candidate_confirm_reject_update_and_forget_lifecycle(self):
        from intelligence.learning_engine import (
            confirm_fact,
            forget_fact,
            get_facts_as_context,
            get_learned_facts,
            init_learning_tables,
            reject_fact,
            store_fact,
            update_fact,
        )
        from personal_context import build_personal_context

        init_learning_tables()
        token = uuid4().hex
        subject = f"phase5-{token}"
        candidate_object = "candidate memory value"
        corrected_object = "corrected memory value"
        fact_id = store_fact("test", subject, "prefers", candidate_object, confidence=0.8)

        candidate = next(f for f in get_learned_facts(status="candidate") if f["id"] == fact_id)
        self.assertEqual(candidate["status"], "candidate")
        self.assertNotIn(candidate_object, get_facts_as_context())
        self.assertNotIn(candidate_object, str(build_personal_context(force=True).get("learned_facts", [])))

        self.assertTrue(confirm_fact(fact_id))
        self.assertIn(candidate_object, get_facts_as_context())
        trusted_context = build_personal_context(force=True).get("learned_facts", [])
        self.assertTrue(any(f["id"] == fact_id and f["status"] == "confirmed" for f in trusted_context))

        self.assertTrue(update_fact(fact_id, obj=corrected_object, confidence=0.95))
        updated = next(f for f in get_learned_facts() if f["id"] == fact_id)
        self.assertEqual(updated["object"], corrected_object)
        self.assertEqual(updated["status"], "candidate")
        self.assertNotIn(corrected_object, get_facts_as_context())

        self.assertTrue(reject_fact(fact_id))
        rejected = next(f for f in get_learned_facts(status="rejected") if f["id"] == fact_id)
        self.assertEqual(rejected["status"], "rejected")
        self.assertNotIn(corrected_object, get_facts_as_context())
        self.assertTrue(forget_fact(fact_id))
        self.assertFalse(any(f["id"] == fact_id for f in get_learned_facts()))


class ApprovalExecutionTests(unittest.TestCase):
    def test_gmail_draft_requires_approval_and_executes_once_after_approval(self):
        from action_ledger import approve_action, create_action, execute_action

        action = create_action(
            "phase5-gmail-draft",
            "gmail.create_draft",
            "Create draft email",
            payload={"to": "test@example.com", "subject": "Test", "body": "Hello"},
            risk="external_write",
            requires_approval=True,
            source="phase5_test",
            idempotency_key=f"phase5-gmail-draft:{uuid4().hex}",
        )
        blocked = execute_action(action["id"])
        self.assertTrue(blocked["execution_blocked"])
        self.assertEqual(blocked["status"], "proposed")

        with patch("connectors.gmail.create_draft", return_value={"ok": True, "draft_id": "draft-1"}) as create_draft:
            approved = approve_action(action["id"])
            self.assertEqual(approved["status"], "approved")
            completed = execute_action(action["id"])
            self.assertEqual(completed["status"], "completed")
            self.assertEqual(completed["result"]["draft_id"], "draft-1")
            create_draft.assert_called_once()

            second = execute_action(action["id"])
            self.assertTrue(second["execution_blocked"])
            create_draft.assert_called_once()

    def test_calendar_create_route_only_proposes_action(self):
        from api_calendar_routes import calendar_create
        from action_ledger import get_action

        event = {
            "title": "Phase 5 test event",
            "start": "2026-08-21T10:00:00+03:00",
            "end": "2026-08-21T11:00:00+03:00",
            "description": "No mutation should happen yet",
            "location": "Juja",
            "calendar_id": "primary",
            "reminders": [10],
        }
        with patch("connectors.calendar.parse_event_request", return_value={"ok": True, "event": event}), \
             patch("connectors.calendar.create_event", Mock()) as create_event:
            result = calendar_create({"text": "schedule the phase 5 test event"})

        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "action_proposed")
        self.assertEqual(result["action"]["status"], "proposed")
        self.assertEqual(result["action"]["action_type"], "calendar.create")
        self.assertTrue(result["action"]["requires_approval"])
        self.assertEqual(get_action(result["action"]["id"])["status"], "proposed")
        create_event.assert_not_called()


class SchedulerTimezoneTests(unittest.TestCase):
    def test_scheduler_uses_nairobi_timezone(self):
        from ora_scheduler import get_scheduler

        self.assertEqual(get_scheduler().timezone.key, "Africa/Nairobi")


class Phase5ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("APP_ENV", "development")
        os.environ.setdefault("ORA_API_TOKEN", "phase5-test-token")
        from fastapi.testclient import TestClient
        from api import app
        cls.client = TestClient(app)

    def test_memory_lifecycle_endpoints(self):
        from intelligence.learning_engine import init_learning_tables, store_fact

        init_learning_tables()
        token = uuid4().hex
        fact_id = store_fact("test", f"api-{token}", "has", "temporary value", confidence=0.7)
        headers = {"X-ORA-Token": "phase5-test-token"}

        candidates = self.client.get("/api/memory/learned?status=candidate", headers=headers)
        self.assertEqual(candidates.status_code, 200)
        self.assertTrue(any(f["id"] == fact_id for f in candidates.json()))

        confirmed = self.client.post(f"/api/memory/learned/{fact_id}/confirm", headers=headers)
        self.assertEqual(confirmed.status_code, 200)
        self.assertEqual(confirmed.json()["status"], "confirmed")

        edited = self.client.patch(
            f"/api/memory/learned/{fact_id}",
            headers=headers,
            json={"object": "updated value"},
        )
        self.assertEqual(edited.status_code, 200)
        self.assertEqual(edited.json()["status"], "candidate")
        self.assertEqual(edited.json()["object"], "updated value")

        rejected = self.client.post(f"/api/memory/learned/{fact_id}/reject", headers=headers)
        self.assertEqual(rejected.status_code, 200)
        self.assertEqual(rejected.json()["status"], "rejected")

        forgotten = self.client.delete(f"/api/memory/learned/{fact_id}", headers=headers)
        self.assertEqual(forgotten.status_code, 200)
        self.assertTrue(forgotten.json()["forgotten"])

    def test_action_execution_endpoint_blocks_unapproved_action(self):
        from action_ledger import create_action

        action = create_action(
            "phase5-api-action",
            "gmail.create_draft",
            "API draft approval test",
            payload={"to": "test@example.com", "subject": "Test", "body": "Hello"},
            risk="external_write",
            requires_approval=True,
            source="phase5_api_test",
            idempotency_key=f"phase5-api-action:{uuid4().hex}",
        )
        response = self.client.post(
            f"/api/actions/{action['id']}/execute",
            headers={"X-ORA-Token": "phase5-test-token"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["execution_blocked"])
        self.assertEqual(response.json()["status"], "proposed")


if __name__ == "__main__":
    unittest.main()
