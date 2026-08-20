"""Durable action ledger for ORA's autonomous execution model."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
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
            executed_at TEXT
        )"""
    )
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
) -> dict[str, Any]:
    """Create or return an action without duplicating an idempotent proposal."""
    init_action_ledger()
    idem = idempotency_key or f"{action_key}:{uuid.uuid4().hex}"
    approval_required = requires_approval or risk in {"external_communication", "irreversible", "financial"}
    now = _now()
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
         status, requires_approval, source, idempotency_key, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, 'proposed', ?, ?, ?, ?, ?)""",
        (
            action_key, action_type, title, description, json.dumps(payload or {}),
            risk, int(approval_required), source, idem, now, now,
        ),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM action_ledger WHERE id=?", (cur.lastrowid,)).fetchone()
    close_conn()
    return _decode(row)


def list_actions(status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    init_action_ledger()
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


def get_action(action_id: int) -> dict[str, Any] | None:
    init_action_ledger()
    conn = get_conn()
    row = conn.execute("SELECT * FROM action_ledger WHERE id=?", (action_id,)).fetchone()
    close_conn()
    return _decode(row) if row else None


def transition_action(
    action_id: int,
    status: str,
    result: dict[str, Any] | None = None,
    error: str | None = None,
) -> dict[str, Any] | None:
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid action status: {status}")
    action = get_action(action_id)
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


def approve_action(action_id: int) -> dict[str, Any] | None:
    action = get_action(action_id)
    if not action or action["status"] != "proposed":
        return action
    return transition_action(action_id, "approved")


def reject_action(action_id: int) -> dict[str, Any] | None:
    action = get_action(action_id)
    if not action or action["status"] not in {"proposed", "approved"}:
        return action
    return transition_action(action_id, "rejected")


def cancel_action(action_id: int) -> dict[str, Any] | None:
    return transition_action(action_id, "cancelled")
