"""
ORA Goals Engine
Stores and manages user goals. Lightweight — no AI calls for CRUD.
"""

import os
from datetime import datetime
from typing import Optional

# ✅ Use config DB_PATH — single source of truth (set via ORA_DATA_DIR env var)
from config import DB_PATH
from database import get_conn, close_conn


def _conn():
    """Use the shared thread-safe connection pool, not a raw sqlite3.connect."""
    return get_conn()


def init_goals_table():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS goals (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            goal       TEXT NOT NULL,
            status     TEXT DEFAULT 'active',
            progress   INTEGER DEFAULT 0,
            due_at     TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    close_conn()


def add_goal(goal: str, due_at: Optional[str] = None) -> int:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO goals (goal, due_at) VALUES (?, ?)",
        (goal.strip(), due_at)
    )
    conn.commit()
    last_id = cur.lastrowid or 0
    close_conn()
    return last_id


def get_goals(status: str = "active") -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, goal, status, progress, due_at, created_at FROM goals WHERE status=? ORDER BY created_at DESC",
        (status,)
    ).fetchall()
    close_conn()
    return [
        {"id": r[0], "goal": r[1], "status": r[2],
         "progress": r[3], "due_at": r[4], "created_at": r[5]}
        for r in rows
    ]


def complete_goal(goal_id: int) -> None:
    conn = get_conn()
    conn.execute(
        "UPDATE goals SET status='completed', progress=100 WHERE id=?",
        (goal_id,)
    )
    conn.commit()
    close_conn()


def update_goal_progress(goal_id: int, progress: int) -> None:
    conn = get_conn()
    conn.execute(
        "UPDATE goals SET progress=? WHERE id=?",
        (max(0, min(100, progress)), goal_id)
    )
    conn.commit()
    close_conn()


def run_goal_checkin() -> None:
    """
    Weekly check-in: logs active goals to console / notifier.
    Called by the scheduler — no Groq call, zero cost.
    """
    try:
        goals = get_goals("active")
        if not goals:
            print("[GOALS] No active goals.")
            return
        print(f"[GOALS] Weekly check-in — {len(goals)} active goal(s):")
        for g in goals:
            due = f" (due {g['due_at'][:10]})" if g["due_at"] else ""
            print(f"  • {g['goal'][:80]}{due} — {g['progress']}%")
    except Exception as e:
        print(f"[GOALS] check-in error: {e}")