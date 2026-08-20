from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(__file__))


class Phase14ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("APP_ENV", "development")
        os.environ.setdefault("ORA_API_TOKEN", "phase14-test-token")
        from fastapi.testclient import TestClient
        from api import app
        cls.client = TestClient(app)

    def test_capabilities_and_health_are_truthful(self):
        health = self.client.get("/api/health")
        capabilities = self.client.get("/api/capabilities", headers={"X-ORA-Token": "phase14-test-token"})
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["service"], "ora-backend")
        self.assertIn("action_ledger", capabilities.json())
        self.assertNotIn("news", capabilities.json()["pages"])

    def test_context_endpoint_has_structured_shape(self):
        response = self.client.get("/api/context", headers={"X-ORA-Token": "phase14-test-token"})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("summary", body)
        self.assertIn("sources", body)
        self.assertIn("state", body)

    def test_action_ledger_requires_approval_for_external_risk(self):
        response = self.client.post("/api/actions", headers={"X-ORA-Token": "phase14-test-token"}, json={
            "action_key": "phase14-email",
            "action_type": "send_email",
            "title": "Send an email",
            "risk": "external_communication",
            "requires_approval": False,
            "idempotency_key": "phase14-email-smoke",
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["requires_approval"])
        self.assertEqual(response.json()["status"], "proposed")


if __name__ == "__main__":
    unittest.main()
