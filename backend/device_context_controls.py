"""Privacy-bounded selected contacts and device-health records for ORA Companion."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from database import close_conn, get_conn

MAX_CONTACTS = 12
MAX_HEALTH_RETENTION_HOURS = 24 * 7
PHONE_RE = re.compile(r"^\+?[0-9]{7,20}$")


class DeviceContextError(ValueError):
    """A safe user-actionable contact or device-health error."""


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require(device_id: str, capability: str) -> dict[str, Any]:
    from device_awareness import _require_active_device, _require_enabled
    from device_command_center import init_command_center_tables, is_globally_paused

    init_command_center_tables()
    _require_active_device(device_id)
    if is_globally_paused(device_id):
        raise DeviceContextError("Awareness is paused. Resume it before sending new device context.")
    return _require_enabled(device_id, capability)


def list_selected_contacts(device_id: str) -> list[dict[str, Any]]:
    _require(device_id, "selected_contacts")
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT id, display_name, normalized_phone, relationship_label, created_at
               FROM ora_device_contacts WHERE device_id=? ORDER BY id DESC""",
            (device_id,),
        ).fetchall()
    finally:
        close_conn()
    return [
        {"id": row[0], "display_name": row[1], "normalized_phone": row[2], "relationship_label": row[3], "created_at": row[4]}
        for row in rows
    ]


def replace_selected_contacts(device_id: str, contacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    _require(device_id, "selected_contacts")
    if len(contacts) > MAX_CONTACTS:
        raise DeviceContextError(f"Save at most {MAX_CONTACTS} selected contacts.")
    normalized: list[tuple[str, str | None, str | None]] = []
    seen: set[tuple[str, str | None]] = set()
    for contact in contacts:
        name = str(contact.get("display_name", "")).strip()[:120]
        raw_phone = str(contact.get("normalized_phone") or "").strip().replace(" ", "").replace("-", "")
        phone = raw_phone or None
        relationship = str(contact.get("relationship_label") or "").strip()[:40] or None
        if not name:
            raise DeviceContextError("Each selected contact needs a name.")
        if phone and not PHONE_RE.fullmatch(phone):
            raise DeviceContextError("A selected contact phone number must contain 7–20 digits and may start with +.")
        key = (name.casefold(), phone)
        if key in seen:
            raise DeviceContextError("Each selected contact must be unique.")
        seen.add(key)
        normalized.append((name, phone, relationship))
    now = _iso()
    conn = get_conn()
    try:
        conn.execute("DELETE FROM ora_device_contacts WHERE device_id=?", (device_id,))
        conn.executemany(
            """INSERT INTO ora_device_contacts (device_id, display_name, normalized_phone, relationship_label, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            [(device_id, name, phone, relationship, now) for name, phone, relationship in normalized],
        )
        conn.commit()
    finally:
        close_conn()
    try:
        from device_command_center import record_activity

        record_activity(device_id, "privacy", "Selected contacts updated", f"{len(normalized)} selected contact(s)")
    except Exception:
        pass
    return list_selected_contacts(device_id)


def _cleanup_health(device_id: str, retention_hours: int) -> None:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=retention_hours)).isoformat()
    conn = get_conn()
    try:
        conn.execute("DELETE FROM ora_device_health_events WHERE device_id=? AND occurred_at < ?", (device_id, cutoff))
        conn.commit()
    finally:
        close_conn()


def record_device_health(device_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    consent = _require(device_id, "device_health")
    try:
        battery_percent = int(payload.get("battery_percent"))
    except (TypeError, ValueError) as exc:
        raise DeviceContextError("Device health needs a battery percentage from 0 to 100.") from exc
    if not 0 <= battery_percent <= 100:
        raise DeviceContextError("Device health battery percentage must be from 0 to 100.")
    is_charging = bool(payload.get("is_charging", False))
    network_type = str(payload.get("network_type") or "unknown").strip().lower()[:32]
    if network_type not in {"wifi", "cellular", "ethernet", "vpn", "bluetooth", "other", "none", "unknown"}:
        network_type = "unknown"
    now = _iso()
    conn = get_conn()
    try:
        cursor = conn.execute(
            """INSERT INTO ora_device_health_events (device_id, battery_percent, is_charging, network_type, occurred_at)
               VALUES (?, ?, ?, ?, ?)""",
            (device_id, battery_percent, int(is_charging), network_type, now),
        )
        event_id = int(cursor.lastrowid)
        conn.commit()
    finally:
        close_conn()
    retention = max(1, min(int(consent["retention_hours"]), MAX_HEALTH_RETENTION_HOURS))
    _cleanup_health(device_id, retention)
    try:
        from device_command_center import record_activity

        record_activity(device_id, "health", "Device health updated", f"Battery {battery_percent}% · {network_type}", retention)
    except Exception:
        pass
    return {"id": event_id, "battery_percent": battery_percent, "is_charging": is_charging, "network_type": network_type, "occurred_at": now, "retention_hours": retention}


def get_latest_device_health(device_id: str) -> dict[str, Any] | None:
    consent = _require(device_id, "device_health")
    _cleanup_health(device_id, max(1, min(int(consent["retention_hours"]), MAX_HEALTH_RETENTION_HOURS)))
    conn = get_conn()
    try:
        row = conn.execute(
            """SELECT id, battery_percent, is_charging, network_type, occurred_at
               FROM ora_device_health_events WHERE device_id=? ORDER BY id DESC LIMIT 1""",
            (device_id,),
        ).fetchone()
    finally:
        close_conn()
    if not row:
        return None
    return {"id": row[0], "battery_percent": row[1], "is_charging": bool(row[2]), "network_type": row[3], "occurred_at": row[4]}


def delete_device_health(device_id: str) -> int:
    _require(device_id, "device_health")
    conn = get_conn()
    try:
        result = conn.execute("DELETE FROM ora_device_health_events WHERE device_id=?", (device_id,))
        conn.commit()
        return max(result.rowcount, 0)
    finally:
        close_conn()
