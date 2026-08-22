"""Private command-center data for paired ORA Companion devices.

This module deliberately separates user-approved mobile inputs from ORA's
owner-level actions. Every record is scoped to one active device, and the
global awareness pause is checked by ingestion routes before storing data.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from database import close_conn, get_conn, get_recent_alerts, get_tasks, init_db, init_tasks_table


class CommandCenterError(ValueError):
    """A safe, user-actionable command-center error."""


CAPTURE_KINDS = {"text", "link", "voice_transcript", "shared_file"}
CAPTURE_STATUSES = {"inbox", "saved", "archived", "task"}
NOTIFICATION_MODES = {"metadata", "redacted", "full"}
MAX_CAPTURE_BODY = 12_000
MAX_NOTIFICATION_BODY = 1_000
MAX_ACTIVITY_LIMIT = 100


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_active_device(device_id: str) -> None:
    from device_registry import get_device

    device = get_device(device_id)
    if not device or device.get("status") != "active":
        raise CommandCenterError("This device is unavailable. Pair it again before using the command center.")


def init_command_center_tables() -> None:
    """Create command-center tables lazily and safely for cold API starts."""
    init_db()
    init_tasks_table()
    conn = get_conn()
    try:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS ora_device_command_preferences (
                device_id TEXT PRIMARY KEY,
                global_pause INTEGER NOT NULL DEFAULT 0,
                quiet_hours_enabled INTEGER NOT NULL DEFAULT 0,
                quiet_start TEXT,
                quiet_end TEXT,
                updated_at TEXT NOT NULL
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS ora_device_captures (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                title TEXT NOT NULL,
                body TEXT NOT NULL DEFAULT '',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL DEFAULT 'inbox',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS ora_device_notification_sources (
                device_id TEXT NOT NULL,
                package_name TEXT NOT NULL,
                app_label TEXT NOT NULL,
                content_mode TEXT NOT NULL DEFAULT 'metadata',
                enabled INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (device_id, package_name)
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS ora_device_notification_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                package_name TEXT NOT NULL,
                app_label TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                body TEXT NOT NULL DEFAULT '',
                content_mode TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS ora_device_health_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                battery_percent INTEGER,
                is_charging INTEGER,
                network_type TEXT,
                occurred_at TEXT NOT NULL
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS ora_device_contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                display_name TEXT NOT NULL,
                normalized_phone TEXT,
                relationship_label TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(device_id, display_name, normalized_phone)
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS ora_device_activity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                category TEXT NOT NULL,
                title TEXT NOT NULL,
                detail TEXT NOT NULL DEFAULT '',
                occurred_at TEXT NOT NULL,
                retention_hours INTEGER NOT NULL DEFAULT 168
            )"""
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ora_device_captures_device_time "
            "ON ora_device_captures(device_id, created_at DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ora_device_activity_device_time "
            "ON ora_device_activity(device_id, occurred_at DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ora_device_notification_events_device_time "
            "ON ora_device_notification_events(device_id, occurred_at DESC)"
        )
        conn.commit()
    finally:
        close_conn()


def _prefs(device_id: str) -> dict[str, Any]:
    init_command_center_tables()
    _require_active_device(device_id)
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT global_pause, quiet_hours_enabled, quiet_start, quiet_end, updated_at "
            "FROM ora_device_command_preferences WHERE device_id=?",
            (device_id,),
        ).fetchone()
    finally:
        close_conn()
    if not row:
        return {
            "global_pause": False,
            "quiet_hours_enabled": False,
            "quiet_start": None,
            "quiet_end": None,
            "updated_at": None,
        }
    return {
        "global_pause": bool(row[0]),
        "quiet_hours_enabled": bool(row[1]),
        "quiet_start": row[2],
        "quiet_end": row[3],
        "updated_at": row[4],
    }


def is_globally_paused(device_id: str) -> bool:
    return bool(_prefs(device_id)["global_pause"])


def record_activity(
    device_id: str,
    category: str,
    title: str,
    detail: str = "",
    retention_hours: int = 168,
) -> None:
    init_command_center_tables()
    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO ora_device_activity
               (device_id, category, title, detail, occurred_at, retention_hours)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (device_id, category[:40], title[:180], detail[:1000], _iso(), max(1, min(retention_hours, 24 * 30))),
        )
        conn.commit()
    finally:
        close_conn()


def get_preferences(device_id: str) -> dict[str, Any]:
    return _prefs(device_id)


def set_preferences(
    device_id: str,
    *,
    global_pause: bool | None = None,
    quiet_hours_enabled: bool | None = None,
    quiet_start: str | None = None,
    quiet_end: str | None = None,
) -> dict[str, Any]:
    current = _prefs(device_id)
    next_value = {
        "global_pause": current["global_pause"] if global_pause is None else bool(global_pause),
        "quiet_hours_enabled": current["quiet_hours_enabled"] if quiet_hours_enabled is None else bool(quiet_hours_enabled),
        "quiet_start": current["quiet_start"] if quiet_start is None else quiet_start.strip()[:5],
        "quiet_end": current["quiet_end"] if quiet_end is None else quiet_end.strip()[:5],
    }
    if next_value["quiet_hours_enabled"] and (not next_value["quiet_start"] or not next_value["quiet_end"]):
        raise CommandCenterError("Quiet hours need both a start and end time.")
    now = _iso()
    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO ora_device_command_preferences
               (device_id, global_pause, quiet_hours_enabled, quiet_start, quiet_end, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(device_id) DO UPDATE SET
                 global_pause=excluded.global_pause,
                 quiet_hours_enabled=excluded.quiet_hours_enabled,
                 quiet_start=excluded.quiet_start,
                 quiet_end=excluded.quiet_end,
                 updated_at=excluded.updated_at""",
            (
                device_id,
                int(next_value["global_pause"]),
                int(next_value["quiet_hours_enabled"]),
                next_value["quiet_start"],
                next_value["quiet_end"],
                now,
            ),
        )
        conn.commit()
    finally:
        close_conn()
    record_activity(
        device_id,
        "privacy",
        "Awareness paused" if next_value["global_pause"] else "Awareness settings updated",
        "Global awareness pause" if next_value["global_pause"] else "Quiet-hour or delivery settings changed",
    )
    return _prefs(device_id)


def create_capture(
    device_id: str,
    *,
    kind: str,
    title: str,
    body: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    init_command_center_tables()
    _require_active_device(device_id)
    if is_globally_paused(device_id):
        raise CommandCenterError("Awareness is paused. Resume it before sending a capture to ORA.")
    if kind not in CAPTURE_KINDS:
        raise CommandCenterError("Unsupported capture type.")
    cleaned_title = title.strip()[:180]
    cleaned_body = body.strip()[:MAX_CAPTURE_BODY]
    if not cleaned_title and not cleaned_body:
        raise CommandCenterError("Add text or a title before saving a capture.")
    now = _iso()
    conn = get_conn()
    try:
        cursor = conn.execute(
            """INSERT INTO ora_device_captures
               (device_id, kind, title, body, metadata_json, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, 'inbox', ?, ?)""",
            (device_id, kind, cleaned_title or cleaned_body[:80], cleaned_body, json.dumps(metadata or {}, separators=(",", ":")), now, now),
        )
        capture_id = int(cursor.lastrowid)
        conn.commit()
    finally:
        close_conn()
    record_activity(device_id, "capture", "Saved to ORA inbox", cleaned_title or cleaned_body[:80])
    return get_capture(device_id, capture_id)


def get_capture(device_id: str, capture_id: int) -> dict[str, Any]:
    init_command_center_tables()
    conn = get_conn()
    try:
        row = conn.execute(
            """SELECT id, kind, title, body, metadata_json, status, created_at, updated_at
               FROM ora_device_captures WHERE device_id=? AND id=?""",
            (device_id, capture_id),
        ).fetchone()
    finally:
        close_conn()
    if not row:
        raise CommandCenterError("Capture not found.")
    return {
        "id": row[0],
        "kind": row[1],
        "title": row[2],
        "body": row[3],
        "metadata": json.loads(row[4] or "{}"),
        "status": row[5],
        "created_at": row[6],
        "updated_at": row[7],
    }


def list_captures(device_id: str, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    init_command_center_tables()
    _require_active_device(device_id)
    bounded_limit = max(1, min(int(limit), MAX_ACTIVITY_LIMIT))
    conn = get_conn()
    try:
        if status and status in CAPTURE_STATUSES:
            rows = conn.execute(
                """SELECT id, kind, title, body, metadata_json, status, created_at, updated_at
                   FROM ora_device_captures WHERE device_id=? AND status=?
                   ORDER BY id DESC LIMIT ?""",
                (device_id, status, bounded_limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT id, kind, title, body, metadata_json, status, created_at, updated_at
                   FROM ora_device_captures WHERE device_id=? ORDER BY id DESC LIMIT ?""",
                (device_id, bounded_limit),
            ).fetchall()
    finally:
        close_conn()
    return [
        {
            "id": row[0],
            "kind": row[1],
            "title": row[2],
            "body": row[3],
            "metadata": json.loads(row[4] or "{}"),
            "status": row[5],
            "created_at": row[6],
            "updated_at": row[7],
        }
        for row in rows
    ]


def set_capture_status(device_id: str, capture_id: int, status: str) -> dict[str, Any]:
    if status not in CAPTURE_STATUSES:
        raise CommandCenterError("Unsupported capture status.")
    init_command_center_tables()
    capture = get_capture(device_id, capture_id)
    metadata = dict(capture.get("metadata") or {})
    if status == "task" and capture["status"] != "task":
        from database import add_task

        metadata["task_id"] = add_task(capture["title"], priority="medium")
        metadata["converted_to_task_at"] = _iso()
    conn = get_conn()
    try:
        result = conn.execute(
            "UPDATE ora_device_captures SET status=?, metadata_json=?, updated_at=? WHERE device_id=? AND id=?",
            (status, json.dumps(metadata, separators=(",", ":")), _iso(), device_id, capture_id),
        )
        conn.commit()
    finally:
        close_conn()
    if result.rowcount != 1:
        raise CommandCenterError("Capture not found.")
    detail = f"Capture {capture_id}"
    if status == "task" and metadata.get("task_id"):
        detail = f"Capture {capture_id} created task {metadata['task_id']}"
    record_activity(device_id, "capture", f"Capture marked {status}", detail)
    return get_capture(device_id, capture_id)


def list_activity(device_id: str, limit: int = 50) -> list[dict[str, Any]]:
    init_command_center_tables()
    _require_active_device(device_id)
    bounded_limit = max(1, min(int(limit), MAX_ACTIVITY_LIMIT))
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT category, title, detail, occurred_at, retention_hours
               FROM ora_device_activity WHERE device_id=?
               ORDER BY id DESC LIMIT ?""",
            (device_id, bounded_limit),
        ).fetchall()
    finally:
        close_conn()
    return [
        {
            "category": row[0],
            "title": row[1],
            "detail": row[2],
            "occurred_at": row[3],
            "retention_hours": row[4],
        }
        for row in rows
    ]


def get_command_center(device_id: str) -> dict[str, Any]:
    """Return only read-safe daily data for a paired device command center."""
    init_command_center_tables()
    _require_active_device(device_id)
    tasks = [
        {
            "id": row[0],
            "title": row[1],
            "priority": row[2],
            "created_at": row[3],
            "due_at": row[4],
            "goal_id": row[5] if len(row) > 5 else None,
        }
        for row in get_tasks("pending")[:8]
    ]
    alerts = [
        {
            "id": row[0],
            "rule_name": row[1],
            "message": row[2],
            "severity": row[3],
            "timestamp": row[4],
            "acknowledged": bool(row[5]),
        }
        for row in get_recent_alerts(limit=8)
    ]
    attention = [alert for alert in alerts if not alert["acknowledged"]]
    high_priority = sum(1 for task in tasks if task["priority"] == "high")
    briefing_parts = [f"{len(tasks)} pending task{'s' if len(tasks) != 1 else ''}"]
    if high_priority:
        briefing_parts.append(f"{high_priority} high priority")
    if attention:
        briefing_parts.append(f"{len(attention)} alert{'s' if len(attention) != 1 else ''} need attention")
    return {
        "briefing": " · ".join(briefing_parts) if briefing_parts else "All clear.",
        "tasks": tasks,
        "alerts": alerts,
        "attention_count": len(attention),
        "pending_capture_count": len(list_captures(device_id, status="inbox", limit=100)),
        "preferences": _prefs(device_id),
        "activity": list_activity(device_id, limit=8),
    }
