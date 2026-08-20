"""Durable action ledger for ORA's autonomous execution model."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from database import close_conn, get_conn

VALID_STATUSES = {
    "proposed", "approved", "rejected", "executing", "completed",
    "failed", "cancelled",
}


def _now() -> str:
    return datetime.now().isoformat()


def init_action_ledger() -> None:
    conn = get_conn()
    conn.execute(
        """CREATE TABLE IF NOT EXISTS action_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action_key TEXT NOT NULL,
            action_type TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            payload_json TEXT NOT NULL DEFAULT '{}',
            risk TEXT NOT NULL DEFAULT 'read_only',
            status TEXT NOT NULL DEFAULT 'proposed',
            requires_approval INTEGER NOT NULL DEFAULT 0,
            source TEXT,
            idempotency_key TEXT UNIQUE,
            result_json TEXT,
            error TEXT,
            retries INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            executed_at TEXT,
            max_retries INTEGER NOT NULL DEFAULT 0,
            expires_at TEXT,
            verification_status TEXT NOT NULL DEFAULT 'not_required',
            verified_at TEXT,
            verification_json TEXT
        )"""
    )
    columns = {row[1] for row in conn.execute("PRAGMA table_info(action_ledger)").fetchall()}
    migrations = {
        "max_retries": "INTEGER NOT NULL DEFAULT 0",
        "expires_at": "TEXT",
        "verification_status": "TEXT NOT NULL DEFAULT 'not_required'",
        "verified_at": "TEXT",
        "verification_json": "TEXT",
    }
    for name, definition in migrations.items():
        if name not in columns:
            conn.execute(f"ALTER TABLE action_ledger ADD COLUMN {name} {definition}")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_action_ledger_status ON action_ledger(status, id DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_action_ledger_created ON action_ledger(created_at DESC)"
    )
    conn.commit()
    close_conn()


def _decode(row: tuple) -> dict[str, Any]:
    return {
        "id": row[0],
        "action_key": row[1],
        "action_type": row[2],
        "title": row[3],
        "description": row[4],
        "payload": json.loads(row[5] or "{}"),
        "risk": row[6],
        "status": row[7],
        "requires_approval": bool(row[8]),
        "source": row[9],
        "idempotency_key": row[10],
        "result": json.loads(row[11]) if row[11] else None,
        "error": row[12],
        "retries": row[13],
        "created_at": row[14],
        "updated_at": row[15],
        "executed_at": row[16],
        "max_retries": row[17] if len(row) > 17 else 0,
        "expires_at": row[18] if len(row) > 18 else None,
        "verification_status": row[19] if len(row) > 19 else "not_required",
        "verified_at": row[20] if len(row) > 20 else None,
        "verification": json.loads(row[21]) if len(row) > 21 and row[21] else None,
    }


def create_action(
    action_key: str,
    action_type: str,
    title: str,
    description: str = "",
    payload: dict[str, Any] | None = None,
    risk: str = "read_only",
    requires_approval: bool = False,
    source: str = "agent",
    idempotency_key: str | None = None,
    max_retries: int = 0,
    expires_at: str | None = None,
    verification_required: bool = False,
) -> dict[str, Any]:
    """Create or return an action without duplicating an idempotent proposal."""
    init_action_ledger()
    idem = idempotency_key or f"{action_key}:{uuid.uuid4().hex}"
    approval_required = requires_approval or risk in {"external_communication", "external_write", "irreversible", "financial"}
    max_retries = max(0, min(int(max_retries), 5))
    verification_status = "pending" if verification_required else "not_required"
    now = _now()
    if expires_at is None and approval_required:
        expires_at = (datetime.now() + timedelta(hours=24)).isoformat()
    conn = get_conn()
    existing = conn.execute(
        "SELECT * FROM action_ledger WHERE idempotency_key=?", (idem,)
    ).fetchone()
    if existing:
        close_conn()
        return _decode(existing)
    cur = conn.execute(
        """INSERT INTO action_ledger
        (action_key, action_type, title, description, payload_json, risk,
         status, requires_approval, source, idempotency_key, created_at, updated_at,
         max_retries, expires_at, verification_status)
        VALUES (?, ?, ?, ?, ?, ?, 'proposed', ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            action_key, action_type, title, description, json.dumps(payload or {}),
            risk, int(approval_required), source, idem, now, now,
            max_retries, expires_at, verification_status,
        ),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM action_ledger WHERE id=?", (cur.lastrowid,)).fetchone()
    close_conn()
    return _decode(row)


def list_actions(status: str | None = None, limit: int = 50, _skip_expiry: bool = False) -> list[dict[str, Any]]:
    init_action_ledger()
    if not _skip_expiry:
        expire_actions(limit=min(limit, 200))
    conn = get_conn()
    if status and status not in VALID_STATUSES:
        close_conn()
        raise ValueError(f"invalid action status: {status}")
    if status:
        rows = conn.execute(
            "SELECT * FROM action_ledger WHERE status=? ORDER BY id DESC LIMIT ?",
            (status, min(limit, 200)),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM action_ledger ORDER BY id DESC LIMIT ?", (min(limit, 200),)
        ).fetchall()
    close_conn()
    return [_decode(row) for row in rows]


def _is_expired(action: dict[str, Any]) -> bool:
    value = action.get("expires_at")
    if not value:
        return False
    try:
        expires = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        return expires < datetime.now(timezone.utc)
    except Exception:
        return False


def _cancel_if_expired(action: dict[str, Any]) -> dict[str, Any]:
    if action.get("status") in {"proposed", "approved"} and _is_expired(action):
        return transition_action(action["id"], "cancelled", error="Action expired before execution") or action
    return action


def _get_action_raw(action_id: int) -> dict[str, Any] | None:
    init_action_ledger()
    conn = get_conn()
    row = conn.execute("SELECT * FROM action_ledger WHERE id=?", (action_id,)).fetchone()
    close_conn()
    return _decode(row) if row else None


def get_action(action_id: int) -> dict[str, Any] | None:
    action = _get_action_raw(action_id)
    return _cancel_if_expired(action) if action else None


def expire_actions(limit: int = 200) -> int:
    """Cancel stale proposals so old approvals cannot execute later."""
    init_action_ledger()
    actions = list_actions(limit=limit, _skip_expiry=True)
    expired = 0
    for action in actions:
        if action["status"] in {"proposed", "approved"} and _is_expired(action):
            transition_action(action["id"], "cancelled", error="Action expired before execution")
            expired += 1
    return expired


def transition_action(
    action_id: int,
    status: str,
    result: dict[str, Any] | None = None,
    error: str | None = None,
) -> dict[str, Any] | None:
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid action status: {status}")
    action = _get_action_raw(action_id)
    if not action:
        return None
    now = _now()
    executed_at = now if status in {"executing", "completed", "failed", "cancelled"} else action["executed_at"]
    conn = get_conn()
    conn.execute(
        """UPDATE action_ledger SET status=?, result_json=?, error=?,
           retries=retries + ?, updated_at=?, executed_at=? WHERE id=?""",
        (
            status,
            json.dumps(result) if result is not None else action["result"] and json.dumps(action["result"]),
            error,
            int(status == "failed"),
            now,
            executed_at,
            action_id,
        ),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM action_ledger WHERE id=?", (action_id,)).fetchone()
    close_conn()
    return _decode(row)


def _parse_datetime(value: str | None):
    if not value:
        return None
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _execute_payload(action: dict[str, Any]) -> dict[str, Any]:
    payload = action.get("payload") or {}
    action_type = action.get("action_type")
    if action_type == "gmail.create_draft":
        from connectors.gmail import create_draft
        return create_draft(
            to=payload["to"], subject=payload["subject"], body=payload["body"],
            account=payload.get("account", "primary"),
        )
    if action_type == "gmail.send_new":
        from connectors.gmail import send_new_email
        return send_new_email(
            to=payload["to"], subject=payload["subject"], body=payload["body"],
            account=payload.get("account", "primary"), cc=payload.get("cc"),
        )
    if action_type == "gmail.send_reply":
        from connectors.gmail import send_reply
        return send_reply(
            reply_id=payload["reply_id"], to=payload["to"], subject=payload["subject"],
            body=payload["body"], thread_id=payload.get("thread_id"),
            account=payload.get("account", "primary"),
        )
    if action_type == "calendar.create":
        from connectors.calendar import create_event
        return create_event(
            title=payload["title"], start=_parse_datetime(payload["start"]),
            end=_parse_datetime(payload["end"]), description=payload.get("description", ""),
            location=payload.get("location", ""), calendar_id=payload.get("calendar_id", "primary"),
            reminders=payload.get("reminders", [10]),
        )
    if action_type == "calendar.update":
        from connectors.calendar import update_event
        return update_event(
            event_id=payload["event_id"], title=payload.get("title"),
            start=_parse_datetime(payload.get("start")), end=_parse_datetime(payload.get("end")),
            description=payload.get("description"), location=payload.get("location"),
            calendar_id=payload.get("calendar_id", "primary"),
        )
    if action_type == "calendar.delete":
        from connectors.calendar import delete_event
        return delete_event(event_id=payload["event_id"], calendar_id=payload.get("calendar_id", "primary"))
    raise ValueError(f"unsupported action type: {action_type}")


def execute_action(action_id: int) -> dict[str, Any] | None:
    """Execute one approved external action exactly once and record its result."""
    action = get_action(action_id)
    if not action:
        return None
    action = _cancel_if_expired(action)
    if action["status"] == "cancelled":
        return action
    if action["status"] != "approved":
        return {**action, "execution_blocked": True, "execution_reason": "Action must be approved first"}
    executing = transition_action(action_id, "executing")
    if not executing:
        return None
    try:
        result = _execute_payload(executing)
        if not result.get("ok"):
            return transition_action(action_id, "failed", result=result, error=result.get("error", "Connector failed"))
        return transition_action(action_id, "completed", result=result)
    except Exception as exc:
        return transition_action(action_id, "failed", error=str(exc))


def approve_action(action_id: int) -> dict[str, Any] | None:
    action = get_action(action_id)
    if not action or action["status"] != "proposed":
        return action
    if _is_expired(action):
        return transition_action(action_id, "cancelled", error="Action expired before approval")
    return transition_action(action_id, "approved")


def retry_action(action_id: int) -> dict[str, Any] | None:
    """Return a failed action to the safe pre-execution state when retries remain."""
    action = get_action(action_id)
    if not action or action["status"] != "failed":
        return action
    if action["retries"] > action.get("max_retries", 0):
        return action
    if _is_expired(action):
        return transition_action(action_id, "cancelled", error="Action expired before retry")
    return transition_action(action_id, "proposed" if action["requires_approval"] else "approved", error=None)


def verify_action(action_id: int, verified: bool, details: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Record an external read-back verification without changing the action result."""
    action = get_action(action_id)
    if not action:
        return None
    now = _now()
    conn = get_conn()
    conn.execute(
        "UPDATE action_ledger SET verification_status=?, verified_at=?, verification_json=?, updated_at=? WHERE id=?",
        ("verified" if verified else "failed", now, json.dumps(details or {}), now, action_id),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM action_ledger WHERE id=?", (action_id,)).fetchone()
    close_conn()
    return _decode(row)


def reject_action(action_id: int) -> dict[str, Any] | None:
    action = get_action(action_id)
    if not action or action["status"] not in {"proposed", "approved"}:
        return action
    return transition_action(action_id, "rejected")


def cancel_action(action_id: int) -> dict[str, Any] | None:
    return transition_action(action_id, "cancelled")
