"""Allowlisted, consented Android notification awareness for one paired device.

Notification records are informational only. ORA never replies, dismisses, or
acts on a third-party notification from this module.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from database import close_conn, get_conn

PACKAGE_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*(?:\.[a-zA-Z][a-zA-Z0-9_]*)+$")
MODES = {"metadata", "redacted", "full"}
MAX_SOURCES = 12
MAX_TITLE = 200
MAX_BODY = 1_000


class NotificationAwarenessError(ValueError):
    """A safe user-actionable notification-awareness error."""


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_enabled(device_id: str) -> dict[str, Any]:
    from device_awareness import _require_active_device, _require_enabled as require_awareness_consent
    from device_command_center import init_command_center_tables, is_globally_paused

    init_command_center_tables()
    _require_active_device(device_id)
    if is_globally_paused(device_id):
        raise NotificationAwarenessError("Awareness is paused. Resume it before receiving notification data.")
    return require_awareness_consent(device_id, "notification_access")


def _redact(value: str) -> str:
    value = re.sub(r"https?://\S+", "[link]", value)
    value = re.sub(r"\b\d{4,10}\b", "[code]", value)
    value = re.sub(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b", "[email]", value)
    return value[:MAX_BODY]


def _cleanup(device_id: str, retention_hours: int) -> None:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=retention_hours)).isoformat()
    conn = get_conn()
    try:
        conn.execute("DELETE FROM ora_device_notification_events WHERE device_id=? AND occurred_at < ?", (device_id, cutoff))
        conn.commit()
    finally:
        close_conn()


def list_sources(device_id: str) -> list[dict[str, Any]]:
    _require_enabled(device_id)
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT package_name, app_label, content_mode, enabled, updated_at
               FROM ora_device_notification_sources WHERE device_id=? ORDER BY app_label COLLATE NOCASE""",
            (device_id,),
        ).fetchall()
    finally:
        close_conn()
    return [
        {"package_name": row[0], "app_label": row[1], "content_mode": row[2], "enabled": bool(row[3]), "updated_at": row[4]}
        for row in rows
    ]


def replace_sources(device_id: str, sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    _require_enabled(device_id)
    if len(sources) > MAX_SOURCES:
        raise NotificationAwarenessError(f"Choose at most {MAX_SOURCES} notification sources.")
    normalized: list[tuple[str, str, str, int]] = []
    seen: set[str] = set()
    for source in sources:
        package_name = str(source.get("package_name", "")).strip()
        label = str(source.get("app_label", "")).strip()[:80]
        mode = str(source.get("content_mode", "metadata")).strip()
        if not PACKAGE_RE.fullmatch(package_name) or package_name in seen:
            raise NotificationAwarenessError("Each source needs a unique Android package name.")
        if not label:
            raise NotificationAwarenessError("Each notification source needs a label.")
        if mode not in MODES:
            raise NotificationAwarenessError("Use metadata, redacted, or full content mode.")
        normalized.append((package_name, label, mode, int(bool(source.get("enabled", True)))))
        seen.add(package_name)
    now = _iso()
    conn = get_conn()
    try:
        conn.execute("DELETE FROM ora_device_notification_sources WHERE device_id=?", (device_id,))
        conn.executemany(
            """INSERT INTO ora_device_notification_sources
               (device_id, package_name, app_label, content_mode, enabled, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            [(device_id, package_name, label, mode, enabled, now) for package_name, label, mode, enabled in normalized],
        )
        conn.commit()
    finally:
        close_conn()
    try:
        from device_command_center import record_activity

        record_activity(device_id, "privacy", "Notification sources updated", f"{len(normalized)} selected app(s)")
    except Exception:
        pass
    return list_sources(device_id)


def record_notification_event(device_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    consent = _require_enabled(device_id)
    package_name = str(payload.get("package_name", "")).strip()
    if not PACKAGE_RE.fullmatch(package_name):
        raise NotificationAwarenessError("Notification source is invalid.")
    conn = get_conn()
    try:
        source = conn.execute(
            """SELECT app_label, content_mode FROM ora_device_notification_sources
               WHERE device_id=? AND package_name=? AND enabled=1""",
            (device_id, package_name),
        ).fetchone()
    finally:
        close_conn()
    if not source:
        raise NotificationAwarenessError("This notification source is not allowlisted for ORA.")
    app_label, mode = source
    title = str(payload.get("title", "")).strip()[:MAX_TITLE]
    body = str(payload.get("body", "")).strip()[:MAX_BODY]
    if mode == "metadata":
        body = ""
    elif mode == "redacted":
        title = _redact(title)
        body = _redact(body)
    occurred_at = _iso()
    retention = int(consent["retention_hours"])
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=retention)).isoformat()
    conn = get_conn()
    try:
        cursor = conn.execute(
            """INSERT INTO ora_device_notification_events
               (device_id, package_name, app_label, title, body, content_mode, occurred_at, expires_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (device_id, package_name, app_label, title, body, mode, occurred_at, expires_at),
        )
        event_id = int(cursor.lastrowid)
        conn.commit()
    finally:
        close_conn()
    _cleanup(device_id, retention)
    try:
        from device_command_center import record_activity

        record_activity(device_id, "notification", f"{app_label} notification received", f"Mode: {mode}", retention)
    except Exception:
        pass
    return {"id": event_id, "app_label": app_label, "content_mode": mode, "occurred_at": occurred_at, "retention_hours": retention}


def list_notification_events(device_id: str, limit: int = 50) -> list[dict[str, Any]]:
    consent = _require_enabled(device_id)
    _cleanup(device_id, int(consent["retention_hours"]))
    bounded_limit = max(1, min(int(limit), 100))
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT id, package_name, app_label, title, body, content_mode, occurred_at, expires_at
               FROM ora_device_notification_events WHERE device_id=? ORDER BY id DESC LIMIT ?""",
            (device_id, bounded_limit),
        ).fetchall()
    finally:
        close_conn()
    return [
        {
            "id": row[0], "package_name": row[1], "app_label": row[2], "title": row[3], "body": row[4],
            "content_mode": row[5], "occurred_at": row[6], "expires_at": row[7],
        }
        for row in rows
    ]


def delete_notification_events(device_id: str) -> int:
    _require_enabled(device_id)
    conn = get_conn()
    try:
        result = conn.execute("DELETE FROM ora_device_notification_events WHERE device_id=?", (device_id,))
        conn.commit()
        return max(result.rowcount, 0)
    finally:
        close_conn()
