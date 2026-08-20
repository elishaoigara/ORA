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


if __name__ == "__main__":
    unittest.main()
