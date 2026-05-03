"""
ORA Task Engine — Structured Task State Machine
================================================
Inspired by Claude Code's Task lifecycle system.

Every agent action ORA dispatches is now a tracked Task with:
  - Full status lifecycle: pending → running → completed / failed / cancelled
  - Typed task kinds matching ORA's agent pipeline
  - Disk-persisted output per task
  - Retry logic for transient failures
  - Observable history via SQLite

Task kinds:
  "chat"       — standard conversational query
  "research"   — Tavily web research
  "content"    — content drafting
  "code_scan"  — GitHub repo scan
  "briefing"   — morning/evening briefing
  "memory"     — memory read/write
  "intent"     — structured intent (task/goal/calendar/weather)
  "notify"     — push notification dispatch

Usage (from brain/router.py):
    from task_engine import TaskEngine, TaskKind
    engine = TaskEngine()
    task_id = engine.create("research", "research AI trends in Africa")
    engine.start(task_id)
    # ... do work ...
    engine.complete(task_id, result={"content": "..."})

    # Or fail with retry:
    engine.fail(task_id, error="Timeout", retryable=True)
    if engine.should_retry(task_id):
        engine.retry(task_id)
"""

from __future__ import annotations

import json
import os
import threading
import traceback
from datetime import datetime
from typing import Any, Literal, Optional

from database import get_conn, close_conn

# DATA_DIR is resolved lazily so the module can be safely imported before
# the environment is fully set up (e.g., during uvicorn startup on Render).
def _data_dir() -> str:
    import os
    return os.getenv("ORA_DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))

# ─── Types ───────────────────────────────────────────────────────────────────

TaskKind = Literal[
    "chat", "research", "content", "code_scan",
    "briefing", "memory", "intent", "notify", "unknown"
]

TaskStatus = Literal["pending", "running", "completed", "failed", "cancelled"]

TERMINAL_STATUSES: set[str] = {"completed", "failed", "cancelled"}

# How many times we'll auto-retry a retryable failure
MAX_RETRIES = 2

# Output directory for per-task result files — resolved lazily at first use
def _task_output_dir() -> str:
    import os
    d = os.path.join(_data_dir(), "task_outputs")
    os.makedirs(d, exist_ok=True)
    return d


# ─── Schema init ─────────────────────────────────────────────────────────────

def init_task_engine_table() -> None:
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS agent_tasks (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            kind        TEXT NOT NULL DEFAULT 'unknown',
            description TEXT NOT NULL DEFAULT '',
            status      TEXT NOT NULL DEFAULT 'pending',
            retry_count INTEGER NOT NULL DEFAULT 0,
            max_retries INTEGER NOT NULL DEFAULT 2,
            output_file TEXT,
            result_json TEXT,
            error       TEXT,
            started_at  TEXT,
            ended_at    TEXT,
            created_at  TEXT DEFAULT (datetime('now')),
            duration_ms INTEGER
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_agent_tasks_status
        ON agent_tasks(status, kind, created_at DESC)
    """)
    conn.commit()
    close_conn()
    print("[TASK ENGINE] Table ready")


# ─── Task Engine ─────────────────────────────────────────────────────────────

class TaskEngine:
    """Thread-safe task lifecycle manager for ORA's agent pipeline."""

    _instance: Optional["TaskEngine"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "TaskEngine":
        # Singleton — one engine per process
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._ready = False
            return cls._instance

    def __init__(self):
        if self._ready:
            return
        init_task_engine_table()
        self._ready = True

    # ── Create ────────────────────────────────────────────────────────────────

    def create(self, kind: TaskKind, description: str) -> int:
        """
        Register a new task. Returns its integer ID.
        Status starts as 'pending'.
        """
        output_file = ""
        conn = get_conn()
        c = conn.cursor()
        c.execute(
            """INSERT INTO agent_tasks (kind, description, status, max_retries, created_at)
               VALUES (?, ?, 'pending', ?, ?)""",
            (kind, description[:500], MAX_RETRIES, datetime.now().isoformat()),
        )
        task_id: int = c.lastrowid or 0
        conn.commit()
        close_conn()

        # Set the output file path now that we have the ID
        output_file = os.path.join(_task_output_dir(), f"task_{task_id}.json")
        conn = get_conn()
        conn.execute(
            "UPDATE agent_tasks SET output_file = ? WHERE id = ?",
            (output_file, task_id),
        )
        conn.commit()
        close_conn()

        return task_id

    # ── Lifecycle transitions ─────────────────────────────────────────────────

    def start(self, task_id: int) -> None:
        """Move task from pending → running."""
        conn = get_conn()
        conn.execute(
            "UPDATE agent_tasks SET status='running', started_at=? WHERE id=?",
            (datetime.now().isoformat(), task_id),
        )
        conn.commit()
        close_conn()

    def complete(self, task_id: int, result: Any = None) -> None:
        """
        Move task to completed. Persists result to disk and DB.
        """
        now = datetime.now().isoformat()
        result_json = ""
        try:
            result_json = json.dumps(result, ensure_ascii=False)[:8000] if result else ""
        except Exception:
            result_json = str(result)[:8000]

        # Write to disk output file
        try:
            row = self._get_row(task_id)
            if row and row.get("output_file"):
                with open(row["output_file"], "w", encoding="utf-8") as f:
                    json.dump({
                        "task_id": task_id,
                        "kind": row.get("kind"),
                        "description": row.get("description"),
                        "result": result,
                        "completed_at": now,
                    }, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[TASK ENGINE] Output write failed for task {task_id}: {e}")

        conn = get_conn()
        conn.execute(
            """UPDATE agent_tasks
               SET status='completed', ended_at=?, result_json=?,
                   duration_ms=CAST((julianday(?) - julianday(COALESCE(started_at, created_at))) * 86400000 AS INTEGER)
               WHERE id=?""",
            (now, result_json, now, task_id),
        )
        conn.commit()
        close_conn()

    def fail(self, task_id: int, error: str = "", retryable: bool = False) -> None:
        """Move task to failed. If retryable, retry_count is preserved for retry()."""
        now = datetime.now().isoformat()
        status = "failed"
        conn = get_conn()
        conn.execute(
            """UPDATE agent_tasks
               SET status=?, ended_at=?, error=?,
                   duration_ms=CAST((julianday(?) - julianday(COALESCE(started_at, created_at))) * 86400000 AS INTEGER)
               WHERE id=?""",
            (status, now, error[:1000], now, task_id),
        )
        conn.commit()
        close_conn()

    def cancel(self, task_id: int, reason: str = "") -> None:
        """Cancel a pending or running task."""
        conn = get_conn()
        conn.execute(
            "UPDATE agent_tasks SET status='cancelled', ended_at=?, error=? WHERE id=?",
            (datetime.now().isoformat(), reason[:500], task_id),
        )
        conn.commit()
        close_conn()

    # ── Retry ─────────────────────────────────────────────────────────────────

    def should_retry(self, task_id: int) -> bool:
        row = self._get_row(task_id)
        if not row:
            return False
        return (
            row["status"] == "failed"
            and row["retry_count"] < row["max_retries"]
        )

    def retry(self, task_id: int) -> None:
        """Reset a failed task back to pending and increment retry_count."""
        conn = get_conn()
        conn.execute(
            """UPDATE agent_tasks
               SET status='pending', started_at=NULL, ended_at=NULL,
                   error=NULL, retry_count=retry_count+1
               WHERE id=? AND status='failed'""",
            (task_id,),
        )
        conn.commit()
        close_conn()

    # ── Context manager helper ─────────────────────────────────────────────────

    def run_tracked(self, kind: TaskKind, description: str, fn, *args, **kwargs):
        """
        Convenience wrapper: creates task, runs fn(), marks complete/failed.
        Returns (task_id, result) on success, (task_id, None) on failure.

        Usage:
            task_id, result = engine.run_tracked("research", "AI news", deep_research, query)
        """
        task_id = self.create(kind, description)
        self.start(task_id)
        try:
            result = fn(*args, **kwargs)
            self.complete(task_id, result)
            return task_id, result
        except Exception as e:
            self.fail(task_id, error=str(e), retryable=True)
            traceback.print_exc()
            return task_id, None

    # ── Queries ───────────────────────────────────────────────────────────────

    def get_task(self, task_id: int) -> Optional[dict]:
        return self._get_row(task_id)

    def get_recent(self, limit: int = 20, kind: str = "", status: str = "") -> list[dict]:
        conn = get_conn()
        q = "SELECT * FROM agent_tasks WHERE 1=1"
        params: list = []
        if kind:
            q += " AND kind=?"; params.append(kind)
        if status:
            q += " AND status=?"; params.append(status)
        q += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        c = conn.cursor()
        c.execute(q, params)
        rows = c.fetchall()
        cols = [d[0] for d in c.description]
        close_conn()
        return [dict(zip(cols, row)) for row in rows]

    def get_running(self) -> list[dict]:
        return self.get_recent(limit=50, status="running")

    def get_stats(self) -> dict:
        conn = get_conn()
        c = conn.cursor()
        c.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) as completed,
                SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) as failed,
                SUM(CASE WHEN status='running' THEN 1 ELSE 0 END) as running,
                SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) as pending,
                AVG(CASE WHEN status='completed' THEN duration_ms END) as avg_ms
            FROM agent_tasks
        """)
        row = c.fetchone()
        close_conn()
        if not row:
            return {}
        return {
            "total": row[0],
            "completed": row[1],
            "failed": row[2],
            "running": row[3],
            "pending": row[4],
            "avg_duration_ms": round(row[5]) if row[5] else None,
            "success_rate": round(row[1] / row[0] * 100, 1) if row[0] else None,
        }

    def purge_old_tasks(self, days: int = 3) -> dict:
        """
        Delete completed/failed tasks older than N days and their output files.
        Safe to call from lifespan — keeps the 1GB Render disk clean.
        Render free tier: call this on startup and periodically.
        """
        import os
        from datetime import timedelta
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        # Collect output files to delete
        conn = get_conn()
        c = conn.cursor()
        c.execute(
            """SELECT output_file FROM agent_tasks
               WHERE status IN ('completed','failed','cancelled')
               AND created_at < ?""",
            (cutoff,)
        )
        files = [r[0] for r in c.fetchall() if r[0]]
        c.execute(
            """DELETE FROM agent_tasks
               WHERE status IN ('completed','failed','cancelled')
               AND created_at < ?""",
            (cutoff,)
        )
        deleted_rows = c.rowcount
        conn.commit()
        close_conn()

        # Delete output files from disk
        deleted_files = 0
        for f in files:
            try:
                if f and os.path.exists(f):
                    os.remove(f)
                    deleted_files += 1
            except Exception:
                pass

        return {"deleted_rows": deleted_rows, "deleted_files": deleted_files}

    # ── Internal ──────────────────────────────────────────────────────────────

    def _get_row(self, task_id: int) -> Optional[dict]:
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT * FROM agent_tasks WHERE id=?", (task_id,))
        row = c.fetchone()
        cols = [d[0] for d in c.description] if row else []
        close_conn()
        return dict(zip(cols, row)) if row else None


# ─── Global singleton ─────────────────────────────────────────────────────────
task_engine = TaskEngine()
