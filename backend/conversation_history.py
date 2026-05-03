"""
ORA Conversation History — Cursor-Based Paginated Storage
==========================================================
Inspired by Claude Code's sessionHistory.ts pagination model.

Problems this solves:
  - Old system stored only last 4 messages in context (hard-coded in router)
  - No way to retrieve older context for long sessions
  - Conversation turns were stored with no session grouping

New design:
  - Every message has a numeric ID (cursor)
  - Sessions are grouped by session_id (UUID per chat session)
  - Pagination: get_history(session_id, before_id=None, limit=20)
  - Full conversation reconstructed by chaining pages
  - Automatic context window trimming (newest N chars) for LLM injection

Usage:
    from conversation_history import ConversationHistory

    history = ConversationHistory()
    session_id = history.new_session()

    history.add(session_id, "user", "What's the weather?")
    history.add(session_id, "assistant", "It's sunny in Nairobi today.")

    # Get last 10 messages (newest first, then reversed for LLM)
    messages = history.get_page(session_id, limit=10)

    # Get older messages before a specific ID
    older = history.get_page(session_id, before_id=42, limit=10)

    # For LLM injection — trimmed to fit token budget
    lm_messages = history.get_for_llm(session_id, max_chars=1200)
"""

from __future__ import annotations

import uuid
import threading
from datetime import datetime
from typing import Optional

from database import get_conn, close_conn


# ─── Schema ───────────────────────────────────────────────────────────────────

def init_conversation_history_table() -> None:
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS conversation_history (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role       TEXT NOT NULL CHECK(role IN ('user','assistant','system')),
            content    TEXT NOT NULL,
            intent     TEXT DEFAULT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_conv_session
        ON conversation_history(session_id, id DESC)
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS conversation_sessions (
            session_id TEXT PRIMARY KEY,
            started_at TEXT DEFAULT (datetime('now')),
            last_at    TEXT DEFAULT (datetime('now')),
            turn_count INTEGER DEFAULT 0,
            summary    TEXT DEFAULT NULL
        )
    """)
    conn.commit()
    close_conn()
    print("[CONV HISTORY] Tables ready")


# ─── ConversationHistory ──────────────────────────────────────────────────────

class ConversationHistory:
    """Thread-safe paginated conversation store."""

    _instance: Optional["ConversationHistory"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "ConversationHistory":
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._ready = False
            return cls._instance

    def __init__(self):
        if self._ready:
            return
        init_conversation_history_table()
        self._ready = True

    # ── Sessions ──────────────────────────────────────────────────────────────

    def new_session(self) -> str:
        """Create and register a new session. Returns session_id."""
        session_id = str(uuid.uuid4())
        conn = get_conn()
        conn.execute(
            "INSERT INTO conversation_sessions (session_id, started_at) VALUES (?, ?)",
            (session_id, datetime.now().isoformat()),
        )
        conn.commit()
        close_conn()
        return session_id

    def get_or_create_session(self, session_id: Optional[str]) -> str:
        """Return existing session_id if valid, else create new one."""
        if session_id:
            conn = get_conn()
            c = conn.cursor()
            c.execute(
                "SELECT session_id FROM conversation_sessions WHERE session_id=?",
                (session_id,)
            )
            row = c.fetchone()
            close_conn()
            if row:
                return session_id
        return self.new_session()

    # ── Write ─────────────────────────────────────────────────────────────────

    def add(
        self,
        session_id: str,
        role: str,
        content: str,
        intent: Optional[str] = None,
    ) -> int:
        """
        Append a message. Returns its ID (usable as a cursor).
        Automatically updates session metadata.
        """
        now = datetime.now().isoformat()
        conn = get_conn()
        c = conn.cursor()
        c.execute(
            """INSERT INTO conversation_history (session_id, role, content, intent, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (session_id, role, content[:4000], intent, now),
        )
        msg_id: int = c.lastrowid or 0
        conn.execute(
            """INSERT INTO conversation_sessions (session_id, started_at, last_at, turn_count)
               VALUES (?, ?, ?, 1)
               ON CONFLICT(session_id) DO UPDATE SET
                   last_at=excluded.last_at,
                   turn_count=turn_count+1""",
            (session_id, now, now),
        )
        conn.commit()
        close_conn()
        return msg_id

    # ── Read (paginated) ──────────────────────────────────────────────────────

    def get_page(
        self,
        session_id: str,
        before_id: Optional[int] = None,
        limit: int = 20,
    ) -> dict:
        """
        Fetch a page of messages in chronological order.

        Returns:
            {
                "messages": [{"id", "role", "content", "intent", "created_at"}, ...],
                "has_more": bool,        # True if older messages exist
                "first_id": int | None,  # oldest ID in this page (use as before_id cursor)
                "last_id": int | None,   # newest ID in this page
            }
        """
        conn = get_conn()
        c = conn.cursor()

        # Fetch one extra to detect has_more
        if before_id is not None:
            c.execute(
                """SELECT id, role, content, intent, created_at
                   FROM conversation_history
                   WHERE session_id=? AND id < ?
                   ORDER BY id DESC LIMIT ?""",
                (session_id, before_id, limit + 1),
            )
        else:
            c.execute(
                """SELECT id, role, content, intent, created_at
                   FROM conversation_history
                   WHERE session_id=?
                   ORDER BY id DESC LIMIT ?""",
                (session_id, limit + 1),
            )

        rows = c.fetchall()
        close_conn()

        has_more = len(rows) > limit
        rows = rows[:limit]
        # Reverse so messages are chronological (oldest first)
        rows = list(reversed(rows))

        messages = [
            {
                "id": r[0],
                "role": r[1],
                "content": r[2],
                "intent": r[3],
                "created_at": r[4],
            }
            for r in rows
        ]

        return {
            "messages": messages,
            "has_more": has_more,
            "first_id": messages[0]["id"] if messages else None,
            "last_id": messages[-1]["id"] if messages else None,
        }

    def get_latest(self, session_id: str, limit: int = 20) -> list[dict]:
        """Shortcut: get the N most recent messages, chronological order."""
        page = self.get_page(session_id, limit=limit)
        return page["messages"]

    # ── LLM context builder ───────────────────────────────────────────────────

    def get_for_llm(
        self,
        session_id: str,
        max_chars: int = 1200,
        limit: int = 20,
    ) -> list[dict]:
        """
        Returns a trimmed list of {role, content} dicts ready to pass to Groq.
        Fits within max_chars total by dropping oldest messages first.
        Only includes 'user' and 'assistant' roles.
        """
        messages = self.get_latest(session_id, limit=limit)
        # Filter to LLM-compatible roles
        messages = [m for m in messages if m["role"] in ("user", "assistant")]

        # Trim oldest messages until total chars fit
        while messages:
            total = sum(len(m["content"]) for m in messages)
            if total <= max_chars:
                break
            messages = messages[1:]  # drop oldest

        return [{"role": m["role"], "content": m["content"]} for m in messages]

    # ── Session summary ───────────────────────────────────────────────────────

    def save_summary(self, session_id: str, summary: str) -> None:
        conn = get_conn()
        conn.execute(
            "UPDATE conversation_sessions SET summary=? WHERE session_id=?",
            (summary[:1000], session_id),
        )
        conn.commit()
        close_conn()

    def get_session_info(self, session_id: str) -> Optional[dict]:
        conn = get_conn()
        c = conn.cursor()
        c.execute(
            "SELECT session_id, started_at, last_at, turn_count, summary FROM conversation_sessions WHERE session_id=?",
            (session_id,)
        )
        row = c.fetchone()
        close_conn()
        if not row:
            return None
        return {
            "session_id": row[0],
            "started_at": row[1],
            "last_at": row[2],
            "turn_count": row[3],
            "summary": row[4],
        }

    def get_recent_sessions(self, limit: int = 10) -> list[dict]:
        conn = get_conn()
        c = conn.cursor()
        c.execute(
            """SELECT session_id, started_at, last_at, turn_count, summary
               FROM conversation_sessions
               ORDER BY last_at DESC LIMIT ?""",
            (limit,),
        )
        rows = c.fetchall()
        close_conn()
        return [
            {
                "session_id": r[0],
                "started_at": r[1],
                "last_at": r[2],
                "turn_count": r[3],
                "summary": r[4],
            }
            for r in rows
        ]


# ─── Global singleton ─────────────────────────────────────────────────────────
conversation_history = ConversationHistory()
