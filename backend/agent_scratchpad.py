"""
ORA Agent Scratchpad — Working Memory for Multi-Step Pipelines
==============================================================
Inspired by Claude Code's TodoWriteTool and in-task state persistence.

Problem: ORA's multi-step pipelines (research → content, code scan → notify)
lose intermediate state if a step fails or the server restarts.
The router's MessageBus is in-memory only — gone after each request.

This scratchpad gives agents a place to write intermediate results so:
  - Multi-step tasks survive partial failures
  - Pipeline state is inspectable for debugging
  - Long-running tasks (research + draft) can be resumed

Design:
  - Keyed by session_id + step_name
  - JSON values, TTL-aware (auto-expires stale notes)
  - Thread-safe
  - Lightweight — single SQLite table

Usage (in brain/router.py agents):
    from agent_scratchpad import scratchpad

    # Write intermediate result
    scratchpad.write(session_id, "research_result", {"content": "...", "sources": [...]})

    # Read it later in the content step
    research = scratchpad.read(session_id, "research_result")

    # Check what's been written for a session
    state = scratchpad.get_all(session_id)

    # Clear when pipeline completes
    scratchpad.clear_session(session_id)
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta
from typing import Any, Optional

from database import get_conn, close_conn

# Notes expire after this many seconds (6 hours)
_DEFAULT_TTL_SECONDS = 6 * 3600


# ─── Schema ───────────────────────────────────────────────────────────────────

def init_scratchpad_table() -> None:
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS agent_scratchpad (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  TEXT NOT NULL,
            step_name   TEXT NOT NULL,
            value_json  TEXT NOT NULL DEFAULT '{}',
            expires_at  TEXT NOT NULL,
            written_at  TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_scratchpad_key
        ON agent_scratchpad(session_id, step_name)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_scratchpad_session
        ON agent_scratchpad(session_id, expires_at)
    """)
    conn.commit()
    close_conn()
    print("[SCRATCHPAD] Table ready")


# ─── Scratchpad ───────────────────────────────────────────────────────────────

class AgentScratchpad:
    """Thread-safe per-session working notes for ORA's agent pipeline."""

    _instance: Optional["AgentScratchpad"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "AgentScratchpad":
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._ready = False
            return cls._instance

    def __init__(self):
        if self._ready:
            return
        init_scratchpad_table()
        self._ready = True

    # ── Write ─────────────────────────────────────────────────────────────────

    def write(
        self,
        session_id: str,
        step_name: str,
        value: Any,
        ttl_seconds: int = _DEFAULT_TTL_SECONDS,
    ) -> None:
        """
        Store a value for this session/step. Overwrites if already exists.
        """
        expires_at = (
            datetime.now() + timedelta(seconds=ttl_seconds)
        ).isoformat()

        try:
            value_json = json.dumps(value, ensure_ascii=False)[:16000]
        except Exception:
            value_json = json.dumps(str(value))

        conn = get_conn()
        conn.execute(
            """INSERT INTO agent_scratchpad (session_id, step_name, value_json, expires_at, written_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(session_id, step_name) DO UPDATE SET
                   value_json=excluded.value_json,
                   expires_at=excluded.expires_at,
                   written_at=excluded.written_at""",
            (session_id, step_name, value_json, expires_at, datetime.now().isoformat()),
        )
        conn.commit()
        close_conn()

    # ── Read ──────────────────────────────────────────────────────────────────

    def read(self, session_id: str, step_name: str) -> Any:
        """
        Retrieve a value. Returns None if not found or expired.
        """
        conn = get_conn()
        c = conn.cursor()
        c.execute(
            """SELECT value_json, expires_at FROM agent_scratchpad
               WHERE session_id=? AND step_name=?""",
            (session_id, step_name),
        )
        row = c.fetchone()
        close_conn()

        if not row:
            return None

        # Check expiry
        try:
            if datetime.fromisoformat(row[1]) < datetime.now():
                self._delete_key(session_id, step_name)
                return None
        except Exception:
            pass

        try:
            return json.loads(row[0])
        except Exception:
            return row[0]

    def has(self, session_id: str, step_name: str) -> bool:
        """Check if a non-expired note exists."""
        return self.read(session_id, step_name) is not None

    def get_all(self, session_id: str) -> dict[str, Any]:
        """
        Get all non-expired notes for a session.
        Returns {step_name: value} dict.
        """
        now = datetime.now().isoformat()
        conn = get_conn()
        c = conn.cursor()
        c.execute(
            """SELECT step_name, value_json FROM agent_scratchpad
               WHERE session_id=? AND expires_at > ?
               ORDER BY written_at""",
            (session_id, now),
        )
        rows = c.fetchall()
        close_conn()

        result = {}
        for step, val_json in rows:
            try:
                result[step] = json.loads(val_json)
            except Exception:
                result[step] = val_json
        return result

    # ── Delete ────────────────────────────────────────────────────────────────

    def clear_session(self, session_id: str) -> None:
        """Remove all notes for a session (call after pipeline completes)."""
        conn = get_conn()
        conn.execute(
            "DELETE FROM agent_scratchpad WHERE session_id=?",
            (session_id,)
        )
        conn.commit()
        close_conn()

    def clear_step(self, session_id: str, step_name: str) -> None:
        self._delete_key(session_id, step_name)

    def _delete_key(self, session_id: str, step_name: str) -> None:
        conn = get_conn()
        conn.execute(
            "DELETE FROM agent_scratchpad WHERE session_id=? AND step_name=?",
            (session_id, step_name),
        )
        conn.commit()
        close_conn()

    def purge_expired(self) -> int:
        """Delete all expired notes. Returns count deleted."""
        now = datetime.now().isoformat()
        conn = get_conn()
        c = conn.cursor()
        c.execute("DELETE FROM agent_scratchpad WHERE expires_at <= ?", (now,))
        deleted = c.rowcount
        conn.commit()
        close_conn()
        return deleted

    # ── Convenience: pipeline state helpers ──────────────────────────────────

    def set_pipeline_stage(self, session_id: str, stage: str) -> None:
        """Track which stage a multi-step pipeline is at."""
        self.write(session_id, "_pipeline_stage", stage)

    def get_pipeline_stage(self, session_id: str) -> Optional[str]:
        return self.read(session_id, "_pipeline_stage")

    def mark_step_done(self, session_id: str, step_name: str) -> None:
        """Mark a step as completed (without storing its result)."""
        done = self.read(session_id, "_done_steps") or []
        if step_name not in done:
            done.append(step_name)
        self.write(session_id, "_done_steps", done)

    def is_step_done(self, session_id: str, step_name: str) -> bool:
        done = self.read(session_id, "_done_steps") or []
        return step_name in done

    def get_done_steps(self, session_id: str) -> list[str]:
        return self.read(session_id, "_done_steps") or []


# ─── Global singleton ─────────────────────────────────────────────────────────
scratchpad = AgentScratchpad()
