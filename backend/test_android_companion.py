"""Regression tests for ORA Android Companion pairing and device credentials."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone


_DATA_DIR = tempfile.mkdtemp(prefix="ora-android-companion-tests-")
os.environ["ORA_DATA_DIR"] = _DATA_DIR
os.environ["APP_ENV"] = "test"
os.environ["ORA_API_TOKEN"] = "android-companion-test-token"
sys.path.insert(0, os.path.dirname(__file__))


class DeviceRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from device_registry import init_device_tables

        init_device_tables()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(_DATA_DIR, ignore_errors=True)

    def test_pairing_code_is_one_time_and_device_token_is_revocable(self):
        from device_registry import (
            DeviceRegistryError,
            authenticate_device,
            create_pairing_code,
            redeem_pairing_code,
            revoke_device,
        )

        created = create_pairing_code("Elisha Pixel", ttl_minutes=10)
        device, token = redeem_pairing_code(created["pairing_code"], "Elisha Pixel")

        self.assertEqual(device["status"], "active")
        self.assertTrue(device["id"].startswith("dev_"))
        self.assertGreater(len(token), 30)
        self.assertEqual(authenticate_device(device["id"], token)["id"], device["id"])

        with self.assertRaises(DeviceRegistryError) as reused:
            redeem_pairing_code(created["pairing_code"], "Another phone")
        self.assertEqual(reused.exception.code, "pairing_code_used")

        revoked = revoke_device(device["id"])
        self.assertEqual(revoked["status"], "revoked")
        self.assertIsNone(authenticate_device(device["id"], token))

    def test_expired_pairing_code_is_rejected(self):
        from database import close_conn, get_conn
        from device_registry import DeviceRegistryError, create_pairing_code, redeem_pairing_code

        created = create_pairing_code("Expiring phone", ttl_minutes=1)
        normalized = "".join(char for char in created["pairing_code"] if char.isalnum())
        raw_code = normalized[3:]

        import hashlib
        conn = get_conn()
        conn.execute(
            "UPDATE ora_device_pairing_codes SET expires_at=? WHERE code_hash=?",
            ((datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(), hashlib.sha256(raw_code.encode()).hexdigest()),
        )
        conn.commit()
        close_conn()

        with self.assertRaises(DeviceRegistryError) as expired:
            redeem_pairing_code(created["pairing_code"], "Expired phone")
        self.assertEqual(expired.exception.code, "pairing_code_expired")


class DevicePairingApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        from api import app

        cls.client = TestClient(app)
        cls.owner_headers = {"X-ORA-Token": "android-companion-test-token"}

    def test_pairing_and_device_self_routes(self):
        create = self.client.post(
            "/api/devices/pairing-codes",
            headers=self.owner_headers,
            json={"label_hint": "ORA Pixel", "platform": "android", "expires_in_minutes": 10},
        )
        self.assertEqual(create.status_code, 200)
        code = create.json()["pairing_code"]

        pair = self.client.post(
            "/api/devices/pair",
            json={"pairing_code": code, "device_name": "ORA Pixel", "platform": "android", "app_version": "0.1.0"},
        )
        self.assertEqual(pair.status_code, 200)
        body = pair.json()
        self.assertTrue(body["ok"])
        device_id = body["device"]["id"]
        device_headers = {
            "X-ORA-Device-ID": device_id,
            "X-ORA-Device-Token": body["device_token"],
        }

        current = self.client.get("/api/devices/self", headers=device_headers)
        self.assertEqual(current.status_code, 200)
        self.assertEqual(current.json()["device"]["id"], device_id)

        check_in = self.client.post("/api/devices/self/check-in", headers=device_headers)
        self.assertEqual(check_in.status_code, 200)
        self.assertTrue(check_in.json()["device"]["last_seen_at"])

        revoked = self.client.post("/api/devices/self/revoke", headers=device_headers)
        self.assertEqual(revoked.status_code, 200)
        self.assertEqual(revoked.json()["device"]["status"], "revoked")

        denied = self.client.get("/api/devices/self", headers=device_headers)
        self.assertEqual(denied.status_code, 401)

    def test_owner_can_list_and_revoke_a_paired_device(self):
        create = self.client.post("/api/devices/pairing-codes", headers=self.owner_headers, json={})
        code = create.json()["pairing_code"]
        pair = self.client.post(
            "/api/devices/pair",
            json={"pairing_code": code, "device_name": "Owner revoke test", "platform": "android"},
        )
        self.assertEqual(pair.status_code, 200)
        device_id = pair.json()["device"]["id"]

        listed = self.client.get("/api/devices", headers=self.owner_headers)
        self.assertEqual(listed.status_code, 200)
        self.assertTrue(any(item["id"] == device_id for item in listed.json()["devices"]))

        revoked = self.client.post(f"/api/devices/{device_id}/revoke", headers=self.owner_headers)
        self.assertEqual(revoked.status_code, 200)
        self.assertEqual(revoked.json()["device"]["status"], "revoked")

    def test_device_command_center_is_scoped_and_pause_blocks_new_captures(self):
        from database import add_task, init_db, init_tasks_table, log_alert

        init_db()
        init_tasks_table()

        create = self.client.post("/api/devices/pairing-codes", headers=self.owner_headers, json={})
        pair = self.client.post(
            "/api/devices/pair",
            json={"pairing_code": create.json()["pairing_code"], "device_name": "Command center test", "platform": "android"},
        )
        self.assertEqual(pair.status_code, 200)
        device_headers = {
            "X-ORA-Device-ID": pair.json()["device"]["id"],
            "X-ORA-Device-Token": pair.json()["device_token"],
        }

        task_id = add_task("Review command center", priority="high")
        log_alert("Companion test", "Reviewable test alert", "medium")

        overview = self.client.get("/api/devices/self/command-center", headers=device_headers)
        self.assertEqual(overview.status_code, 200)
        self.assertTrue(any(task["id"] == task_id for task in overview.json()["command_center"]["tasks"]))

        capture = self.client.post(
            "/api/devices/self/captures",
            headers=device_headers,
            json={"kind": "text", "title": "A private thought", "body": "Keep this in the reviewable inbox."},
        )
        self.assertEqual(capture.status_code, 200)
        capture_id = capture.json()["capture"]["id"]
        saved = self.client.patch(
            f"/api/devices/self/captures/{capture_id}", headers=device_headers, json={"status": "saved"}
        )
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()["capture"]["status"], "saved")

        task_capture = self.client.post(
            "/api/devices/self/captures",
            headers=device_headers,
            json={"kind": "text", "title": "Follow up with a client", "body": "Create only after explicit Inbox task conversion."},
        )
        self.assertEqual(task_capture.status_code, 200)
        converted = self.client.patch(
            f"/api/devices/self/captures/{task_capture.json()['capture']['id']}", headers=device_headers, json={"status": "task"}
        )
        self.assertEqual(converted.status_code, 200)
        self.assertEqual(converted.json()["capture"]["status"], "task")
        self.assertIn("task_id", converted.json()["capture"]["metadata"])

        paused = self.client.put(
            "/api/devices/self/preferences", headers=device_headers, json={"global_pause": True}
        )
        self.assertEqual(paused.status_code, 200)
        self.assertTrue(paused.json()["preferences"]["global_pause"])
        blocked = self.client.post(
            "/api/devices/self/captures", headers=device_headers, json={"kind": "text", "title": "Blocked"}
        )
        self.assertEqual(blocked.status_code, 400)

        resumed = self.client.put(
            "/api/devices/self/preferences", headers=device_headers, json={"global_pause": False}
        )
        self.assertEqual(resumed.status_code, 200)
        completed = self.client.post(f"/api/devices/self/tasks/{task_id}/complete", headers=device_headers)
        self.assertEqual(completed.status_code, 200)

        alert_id = overview.json()["command_center"]["alerts"][0]["id"]
        acknowledged = self.client.post(f"/api/devices/self/alerts/{alert_id}/ack", headers=device_headers)
        self.assertEqual(acknowledged.status_code, 200)

        unauthenticated = self.client.get("/api/devices/self/command-center")
        self.assertEqual(unauthenticated.status_code, 401)

    def test_notification_awareness_requires_consent_allowlist_and_respects_pause(self):
        create = self.client.post("/api/devices/pairing-codes", headers=self.owner_headers, json={})
        pair = self.client.post(
            "/api/devices/pair",
            json={"pairing_code": create.json()["pairing_code"], "device_name": "Notification policy test", "platform": "android"},
        )
        self.assertEqual(pair.status_code, 200)
        device_headers = {
            "X-ORA-Device-ID": pair.json()["device"]["id"],
            "X-ORA-Device-Token": pair.json()["device_token"],
        }

        denied_before_consent = self.client.get("/api/devices/self/notification-sources", headers=device_headers)
        self.assertEqual(denied_before_consent.status_code, 400)

        enabled = self.client.put(
            "/api/devices/self/awareness",
            headers=device_headers,
            json={"capability": "notification_access", "enabled": True, "retention_hours": 24},
        )
        self.assertEqual(enabled.status_code, 200)

        blocked_source = self.client.post(
            "/api/devices/self/notification-events",
            headers=device_headers,
            json={"package_name": "com.whatsapp", "title": "Not permitted", "body": "No allowlist yet"},
        )
        self.assertEqual(blocked_source.status_code, 400)

        sources = self.client.put(
            "/api/devices/self/notification-sources",
            headers=device_headers,
            json={"sources": [{"package_name": "com.whatsapp", "app_label": "WhatsApp", "content_mode": "redacted", "enabled": True}]},
        )
        self.assertEqual(sources.status_code, 200)
        self.assertEqual(sources.json()["sources"][0]["content_mode"], "redacted")

        recorded = self.client.post(
            "/api/devices/self/notification-events",
            headers=device_headers,
            json={"package_name": "com.whatsapp", "title": "OTP 123456", "body": "See https://example.test and elisha@example.test"},
        )
        self.assertEqual(recorded.status_code, 200)
        events = self.client.get("/api/devices/self/notification-events", headers=device_headers)
        self.assertEqual(events.status_code, 200)
        self.assertIn("[code]", events.json()["events"][0]["title"])
        self.assertIn("[link]", events.json()["events"][0]["body"])
        self.assertIn("[email]", events.json()["events"][0]["body"])

        paused = self.client.put("/api/devices/self/preferences", headers=device_headers, json={"global_pause": True})
        self.assertEqual(paused.status_code, 200)
        blocked_while_paused = self.client.post(
            "/api/devices/self/notification-events",
            headers=device_headers,
            json={"package_name": "com.whatsapp", "title": "Paused", "body": "Do not store"},
        )
        self.assertEqual(blocked_while_paused.status_code, 400)

        self.client.put("/api/devices/self/preferences", headers=device_headers, json={"global_pause": False})
        cleared = self.client.delete("/api/devices/self/notification-events", headers=device_headers)
        self.assertEqual(cleared.status_code, 200)
        self.assertGreaterEqual(cleared.json()["deleted"], 1)

    def test_selected_contacts_and_device_health_are_consent_scoped_and_deletable(self):
        create = self.client.post("/api/devices/pairing-codes", headers=self.owner_headers, json={})
        pair = self.client.post(
            "/api/devices/pair",
            json={"pairing_code": create.json()["pairing_code"], "device_name": "Private context test", "platform": "android"},
        )
        self.assertEqual(pair.status_code, 200)
        device_headers = {
            "X-ORA-Device-ID": pair.json()["device"]["id"],
            "X-ORA-Device-Token": pair.json()["device_token"],
        }

        self.assertEqual(self.client.get("/api/devices/self/contacts", headers=device_headers).status_code, 400)
        self.assertEqual(self.client.get("/api/devices/self/health", headers=device_headers).status_code, 400)

        for capability in ("selected_contacts", "device_health"):
            enabled = self.client.put(
                "/api/devices/self/awareness",
                headers=device_headers,
                json={"capability": capability, "enabled": True, "retention_hours": 24},
            )
            self.assertEqual(enabled.status_code, 200)

        contacts = self.client.put(
            "/api/devices/self/contacts",
            headers=device_headers,
            json={"contacts": [{"display_name": "Sam Example", "normalized_phone": "+254712345678", "relationship_label": "Family"}]},
        )
        self.assertEqual(contacts.status_code, 200)
        self.assertEqual(contacts.json()["contacts"][0]["display_name"], "Sam Example")

        health = self.client.post(
            "/api/devices/self/health",
            headers=device_headers,
            json={"battery_percent": 68, "is_charging": True, "network_type": "wifi"},
        )
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["health"]["battery_percent"], 68)

        self.client.put("/api/devices/self/preferences", headers=device_headers, json={"global_pause": True})
        blocked = self.client.post(
            "/api/devices/self/health",
            headers=device_headers,
            json={"battery_percent": 67, "is_charging": False, "network_type": "cellular"},
        )
        self.assertEqual(blocked.status_code, 400)

        self.client.put("/api/devices/self/preferences", headers=device_headers, json={"global_pause": False})
        cleared_health = self.client.delete("/api/devices/self/health", headers=device_headers)
        self.assertEqual(cleared_health.status_code, 200)
        self.assertEqual(cleared_health.json()["deleted"], 1)

        disabled_contacts = self.client.put(
            "/api/devices/self/awareness",
            headers=device_headers,
            json={"capability": "selected_contacts", "enabled": False},
        )
        self.assertEqual(disabled_contacts.status_code, 200)
        self.assertEqual(self.client.get("/api/devices/self/contacts", headers=device_headers).status_code, 400)

    def test_device_approval_queue_requires_separate_approve_and_execute_taps(self):
        from action_ledger import create_action

        create = self.client.post("/api/devices/pairing-codes", headers=self.owner_headers, json={})
        pair = self.client.post(
            "/api/devices/pair",
            json={"pairing_code": create.json()["pairing_code"], "device_name": "Approval test", "platform": "android"},
        )
        self.assertEqual(pair.status_code, 200)
        device_headers = {
            "X-ORA-Device-ID": pair.json()["device"]["id"],
            "X-ORA-Device-Token": pair.json()["device_token"],
        }
        action = create_action(
            action_key="test-device-approval",
            action_type="test.unsupported_action",
            title="Review a safe test action",
            description="A test proposal that has no connector implementation.",
            payload={"private_value": "must_not_be_exposed"},
            risk="external_write",
            requires_approval=True,
        )

        listed = self.client.get("/api/devices/self/approvals", headers=device_headers)
        self.assertEqual(listed.status_code, 200)
        summary = next(item for item in listed.json()["approvals"] if item["id"] == action["id"])
        self.assertNotIn("payload", summary)
        self.assertEqual(summary["status"], "proposed")

        premature = self.client.post(f"/api/devices/self/approvals/{action['id']}/execute", headers=device_headers)
        self.assertEqual(premature.status_code, 400)

        approved = self.client.post(f"/api/devices/self/approvals/{action['id']}/approve", headers=device_headers)
        self.assertEqual(approved.status_code, 200)
        self.assertTrue(approved.json()["execution_requires_user_tap"])
        self.assertEqual(approved.json()["approval"]["status"], "approved")

        executed = self.client.post(f"/api/devices/self/approvals/{action['id']}/execute", headers=device_headers)
        self.assertEqual(executed.status_code, 200)
        self.assertEqual(executed.json()["approval"]["status"], "failed")

        rejected_action = create_action(
            action_key="test-device-rejection",
            action_type="test.unsupported_action",
            title="Reject a safe test action",
            risk="external_write",
            requires_approval=True,
        )
        rejected = self.client.post(f"/api/devices/self/approvals/{rejected_action['id']}/reject", headers=device_headers)
        self.assertEqual(rejected.status_code, 200)
        self.assertEqual(rejected.json()["approval"]["status"], "rejected")


if __name__ == "__main__":
    unittest.main()
