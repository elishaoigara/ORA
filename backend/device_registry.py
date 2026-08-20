"""Durable, revocable Android companion device pairing for ORA.

The registry keeps the master ORA API token out of the mobile application.
Pairing codes are short-lived and one-time; redeemed devices receive a random,
device-scoped credential stored only as a hash in ORA's SQLite database.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from database import close_conn, get_conn


class DeviceRegistryError(ValueError):
    """Raised when a pairing or device credential operation is invalid."""

    def __init__(self, message: str, code: str = "device_registry_error") -> None:
        super().__init__(message)
        self.code = code


_PAIRING_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_DEFAULT_PAIRING_TTL_MINUTES = 10
_MAX_PAIRING_TTL_MINUTES = 60
_MAX_PAIRING_ATTEMPTS = 5


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None = None) -> str:
    return (value or _now()).isoformat()


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normalize_code(code: str) -> str:
    return "".join(char for char in str(code).upper() if char.isalnum())


def _format_code(raw: str) -> str:
    return f"ORA-{raw[:5]}-{raw[5:]}"


def _clean_label(value: str, default: str = "Android phone") -> str:
    label = (value or default).strip()
    if not label:
        label = default
    if len(label) > 64:
        raise DeviceRegistryError("Device label must be 64 characters or fewer", "invalid_label")
    return label


def _as_device(row: tuple[Any, ...]) -> dict[str, Any]:
    capabilities: list[str]
    try:
        capabilities = json.loads(row[8] or "[]")
    except (TypeError, json.JSONDecodeError):
        capabilities = []
    return {
        "id": row[0],
        "label": row[1],
        "platform": row[2],
        "app_version": row[3],
        "status": "revoked" if row[7] else "active",
        "paired_at": row[4],
        "last_seen_at": row[5],
        "token_hint": row[6],
        "revoked_at": row[7],
        "capabilities": capabilities,
    }


def init_device_tables() -> None:
    """Create pairing and device tables without requiring a destructive migration."""
    conn = get_conn()
    try:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS ora_devices (
                id TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                platform TEXT NOT NULL,
                app_version TEXT,
                token_hash TEXT NOT NULL,
                token_hint TEXT NOT NULL,
                paired_at TEXT NOT NULL,
                last_seen_at TEXT,
                revoked_at TEXT,
                capabilities_json TEXT NOT NULL DEFAULT '[]'
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS ora_device_pairing_codes (
                id TEXT PRIMARY KEY,
                code_hash TEXT NOT NULL UNIQUE,
                label_hint TEXT,
                platform TEXT NOT NULL DEFAULT 'android',
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                consumed_at TEXT,
                attempts INTEGER NOT NULL DEFAULT 0,
                max_attempts INTEGER NOT NULL DEFAULT 5
            )"""
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ora_devices_status ON ora_devices(revoked_at, last_seen_at)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ora_pairing_expiry ON ora_device_pairing_codes(expires_at, consumed_at)"
        )
        conn.commit()
    finally:
        close_conn()


def create_pairing_code(
    label_hint: str = "Android phone",
    platform: str = "android",
    ttl_minutes: int = _DEFAULT_PAIRING_TTL_MINUTES,
) -> dict[str, str | int]:
    """Create a one-time companion pairing code for an authenticated ORA owner."""
    init_device_tables()
    ttl = max(1, min(int(ttl_minutes), _MAX_PAIRING_TTL_MINUTES))
    label = _clean_label(label_hint)
    normalized_platform = (platform or "android").strip().lower()[:32] or "android"
    raw_code = "".join(secrets.choice(_PAIRING_ALPHABET) for _ in range(10))
    now = _now()
    expires_at = now + timedelta(minutes=ttl)
    record_id = f"pair_{secrets.token_urlsafe(12)}"

    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO ora_device_pairing_codes
               (id, code_hash, label_hint, platform, created_at, expires_at, max_attempts)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (record_id, _hash(raw_code), label, normalized_platform, _iso(now), _iso(expires_at), _MAX_PAIRING_ATTEMPTS),
        )
        conn.commit()
    finally:
        close_conn()

    return {
        "pairing_code": _format_code(raw_code),
        "expires_at": _iso(expires_at),
        "expires_in_minutes": ttl,
        "label_hint": label,
    }


def redeem_pairing_code(
    pairing_code: str,
    device_name: str,
    platform: str = "android",
    app_version: str | None = None,
) -> tuple[dict[str, Any], str]:
    """Redeem a live code once and return a public device record plus raw token."""
    init_device_tables()
    normalized = _normalize_code(pairing_code)
    if len(normalized) != 13 or not normalized.startswith("ORA"):
        raise DeviceRegistryError("Pairing code is invalid", "invalid_pairing_code")
    raw_code = normalized[3:]
    if len(raw_code) != 10:
        raise DeviceRegistryError("Pairing code is invalid", "invalid_pairing_code")

    label = _clean_label(device_name)
    normalized_platform = (platform or "android").strip().lower()[:32] or "android"
    now = _now()
    device_id = f"dev_{secrets.token_urlsafe(12)}"
    raw_token = secrets.token_urlsafe(32)

    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            """SELECT id, label_hint, platform, expires_at, consumed_at, attempts, max_attempts
               FROM ora_device_pairing_codes WHERE code_hash=?""",
            (_hash(raw_code),),
        ).fetchone()
        if not row:
            raise DeviceRegistryError("Pairing code is invalid", "invalid_pairing_code")

        expires_at = datetime.fromisoformat(row[3])
        if row[4]:
            raise DeviceRegistryError("Pairing code has already been used", "pairing_code_used")
        if expires_at <= now:
            raise DeviceRegistryError("Pairing code has expired", "pairing_code_expired")
        if int(row[5]) >= int(row[6]):
            raise DeviceRegistryError("Pairing code is locked; create a new code", "pairing_code_locked")

        updated = conn.execute(
            """UPDATE ora_device_pairing_codes
               SET consumed_at=?, attempts=attempts+1
               WHERE id=? AND consumed_at IS NULL""",
            (_iso(now), row[0]),
        )
        if updated.rowcount != 1:
            raise DeviceRegistryError("Pairing code has already been used", "pairing_code_used")

        conn.execute(
            """INSERT INTO ora_devices
               (id, label, platform, app_version, token_hash, token_hint, paired_at, last_seen_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                device_id,
                label,
                normalized_platform,
                (app_version or "").strip()[:64] or None,
                _hash(raw_token),
                raw_token[-6:],
                _iso(now),
                _iso(now),
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        close_conn()

    return (
        {
            "id": device_id,
            "label": label,
            "platform": normalized_platform,
            "app_version": (app_version or "").strip()[:64] or None,
            "status": "active",
            "paired_at": _iso(now),
            "last_seen_at": _iso(now),
            "token_hint": raw_token[-6:],
            "revoked_at": None,
            "capabilities": [],
        },
        raw_token,
    )


def authenticate_device(device_id: str | None, raw_token: str | None) -> dict[str, Any] | None:
    """Validate a non-revoked device credential and refresh its last-seen time."""
    if not device_id or not raw_token:
        return None
    init_device_tables()
    conn = get_conn()
    try:
        row = conn.execute(
            """SELECT id, label, platform, app_version, paired_at, last_seen_at, token_hint, revoked_at,
                      capabilities_json, token_hash
               FROM ora_devices WHERE id=?""",
            (device_id,),
        ).fetchone()
        if not row or row[7] or not hmac.compare_digest(str(row[9]), _hash(raw_token)):
            return None
        now = _iso()
        conn.execute("UPDATE ora_devices SET last_seen_at=? WHERE id=?", (now, device_id))
        conn.commit()
        return _as_device(row[:6] + (row[6], row[7], row[8])) | {"last_seen_at": now}
    finally:
        close_conn()


def list_devices() -> list[dict[str, Any]]:
    init_device_tables()
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT id, label, platform, app_version, paired_at, last_seen_at, token_hint, revoked_at,
                      capabilities_json
               FROM ora_devices ORDER BY paired_at DESC"""
        ).fetchall()
        return [_as_device(row) for row in rows]
    finally:
        close_conn()


def get_device(device_id: str) -> dict[str, Any] | None:
    init_device_tables()
    conn = get_conn()
    try:
        row = conn.execute(
            """SELECT id, label, platform, app_version, paired_at, last_seen_at, token_hint, revoked_at,
                      capabilities_json
               FROM ora_devices WHERE id=?""",
            (device_id,),
        ).fetchone()
        return _as_device(row) if row else None
    finally:
        close_conn()


def check_in_device(device_id: str) -> dict[str, Any]:
    device = get_device(device_id)
    if not device or device["status"] != "active":
        raise DeviceRegistryError("Device is unavailable", "device_unavailable")
    now = _iso()
    conn = get_conn()
    try:
        conn.execute("UPDATE ora_devices SET last_seen_at=? WHERE id=?", (now, device_id))
        conn.commit()
    finally:
        close_conn()
    return device | {"last_seen_at": now}


def revoke_device(device_id: str) -> dict[str, Any]:
    init_device_tables()
    now = _iso()
    conn = get_conn()
    try:
        updated = conn.execute(
            "UPDATE ora_devices SET revoked_at=? WHERE id=? AND revoked_at IS NULL",
            (now, device_id),
        )
        conn.commit()
        if updated.rowcount != 1:
            raise DeviceRegistryError("Active device not found", "device_not_found")
    finally:
        close_conn()
    device = get_device(device_id)
    if not device:
        raise DeviceRegistryError("Device not found", "device_not_found")
    return device
