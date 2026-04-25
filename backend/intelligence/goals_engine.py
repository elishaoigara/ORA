"""
ORA Goals Engine
Stores and manages user goals. Lightweight — no AI calls for CRUD.
"""

import sqlite3
import os
from datetime import datetime
from typing import Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "ora_knowledge.db")


def _conn():
    return sqlite3.connect(DB_PATH)


def init_goals_table():
    with _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS goals (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                goal      TEXT NOT NULL,
                status    TEXT DEFAULT 'active',
                progress  INTEGER DEFAULT 0,
                due_at    TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        c.commit()


def add_goal(goal: str, due_at: Optional[str] = None) -> int:
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO goals (goal, due_at) VALUES (?, ?)",
            (goal.strip(), due_at)
        )
        c.commit()
        return cur.lastrowid or 0


def get_goals(status: str = "active") -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT id, goal, status, progress, due_at, created_at FROM goals WHERE status = ? ORDER BY created_at DESC",
            (status,)
        ).fetchall()
    return [
        {"id": r[0], "goal": r[1], "status": r[2],
         "progress": r[3], "due_at": r[4], "created_at": r[5]}
        for r in rows
    ]


def complete_goal(goal_id: int) -> None:
    with _conn() as c:
        c.execute(
            "UPDATE goals SET status='completed', progress=100 WHERE id=?",
            (goal_id,)
        )
        c.commit()


def update_goal_progress(goal_id: int, progress: int) -> None:
    with _conn() as c:
        c.execute(
            "UPDATE goals SET progress=? WHERE id=?",
            (max(0, min(100, progress)), goal_id)
        )
        c.commit()


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