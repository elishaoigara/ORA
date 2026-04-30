"""
ORA Agent Message Bus
=====================
A lightweight SQLite-backed message bus that lets all agents communicate.

How it works:
  - Any agent POSTs a message to the bus (from_agent, to_agent, payload)
  - The coordinator polls the bus and routes pending messages
  - Results are written back so the sender can read them
  - All activity is persisted — ORA builds intelligence from it over time

Design principles:
  - Zero new dependencies (pure SQLite)
  - Render free tier safe — no Redis, no Celery, no RabbitMQ
  - Thread-safe (uses the existing get_conn pool)
  - Every message is stored permanently for learning/analytics

Agent IDs (canonical names):
  "orchestrator"  — the coordinator (brain/router.py)
  "research"      — research_agent.py
  "content"       — agents/content_agent.py
  "code"          — agents/code_agent.py
  "executive"     — planner_engine.py
  "memory"        — learning_engine.py
  "notifier"      — intelligence/notifier.py
  "user"          — a message initiated by the user via chat/UI
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from database import get_conn, close_conn


# ─── Schema ───────────────────────────────────────────────────────────────────

def init_agent_bus_table() -> None:
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS agent_messages (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            from_agent  TEXT NOT NULL,
            to_agent    TEXT NOT NULL,
            intent      TEXT NOT NULL,
            payload     TEXT DEFAULT '{}',
            result      TEXT DEFAULT NULL,
            status      TEXT DEFAULT 'pending',
            priority    INTEGER DEFAULT 5,
            created_at  TEXT DEFAULT (datetime('now')),
            updated_at  TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_bus_status
        ON agent_messages(to_agent, status, priority DESC, created_at)
    """)
    conn.commit()
    close_conn()
    print("[AGENT BUS] Table ready")


# ─── Write ────────────────────────────────────────────────────────────────────

def post_message(
    from_agent: str,
    to_agent: str,
    intent: str,
    payload: dict | None = None,
    priority: int = 5,
) -> int:
    """
    Post a message on the bus.
    Returns the message ID so the caller can poll for the result.

    Intents (examples):
      "research.run"      — trigger a research query
      "content.generate"  — generate a content draft
      "code.scan"         — scan a repo
      "notify.send"       — send a Telegram notification
      "memory.store"      — store a learned fact
      "executive.plan"    — generate daily plan
    """
    conn = get_conn()
    cur = conn.execute(
        """INSERT INTO agent_messages
           (from_agent, to_agent, intent, payload, priority, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (from_agent, to_agent, intent,
         json.dumps(payload or {}), priority,
         datetime.now().isoformat(), datetime.now().isoformat())
    )
    msg_id = cur.lastrowid or 0
    conn.commit()
    close_conn()
    print(f"[AGENT BUS] {from_agent} → {to_agent} [{intent}] id={msg_id}")
    return msg_id


def complete_message(msg_id: int, result: Any) -> None:
    """Mark a message as done and write its result."""
    conn = get_conn()
    conn.execute(
        """UPDATE agent_messages
           SET status='done', result=?, updated_at=?
           WHERE id=?""",
        (json.dumps(result), datetime.now().isoformat(), msg_id)
    )
    conn.commit()
    close_conn()


def fail_message(msg_id: int, error: str) -> None:
    """Mark a message as failed."""
    conn = get_conn()
    conn.execute(
        """UPDATE agent_messages
           SET status='failed', result=?, updated_at=?
           WHERE id=?""",
        (json.dumps({"error": error}), datetime.now().isoformat(), msg_id)
    )
    conn.commit()
    close_conn()


# ─── Read ─────────────────────────────────────────────────────────────────────

def get_pending(to_agent: str, limit: int = 10) -> list[dict]:
    """Get pending messages for a specific agent, highest priority first."""
    conn = get_conn()
    rows = conn.execute(
        """SELECT id, from_agent, to_agent, intent, payload, priority, created_at
           FROM agent_messages
           WHERE to_agent=? AND status='pending'
           ORDER BY priority DESC, created_at ASC
           LIMIT ?""",
        (to_agent, limit)
    ).fetchall()
    close_conn()
    return [
        {
            "id":         r[0],
            "from_agent": r[1],
            "to_agent":   r[2],
            "intent":     r[3],
            "payload":    _safe_json(r[4]),
            "priority":   r[5],
            "created_at": r[6],
        }
        for r in rows
    ]


def get_message_result(msg_id: int) -> Optional[dict]:
    """Poll for the result of a specific message."""
    conn = get_conn()
    row = conn.execute(
        "SELECT id, status, result, updated_at FROM agent_messages WHERE id=?",
        (msg_id,)
    ).fetchone()
    close_conn()
    if not row:
        return None
    return {
        "id":         row[0],
        "status":     row[1],
        "result":     _safe_json(row[2]) if row[2] else None,
        "updated_at": row[3],
    }


def get_recent_activity(limit: int = 20) -> list[dict]:
    """Recent bus activity for the dashboard/UI."""
    conn = get_conn()
    rows = conn.execute(
        """SELECT id, from_agent, to_agent, intent, status, created_at, updated_at
           FROM agent_messages
           ORDER BY id DESC LIMIT ?""",
        (limit,)
    ).fetchall()
    close_conn()
    return [
        {
            "id":         r[0],
            "from_agent": r[1],
            "to_agent":   r[2],
            "intent":     r[3],
            "status":     r[4],
            "created_at": r[5],
            "updated_at": r[6],
        }
        for r in rows
    ]


def get_bus_stats() -> dict:
    """Quick stats for the dashboard."""
    conn = get_conn()
    total   = conn.execute("SELECT COUNT(*) FROM agent_messages").fetchone()[0]
    pending = conn.execute("SELECT COUNT(*) FROM agent_messages WHERE status='pending'").fetchone()[0]
    done    = conn.execute("SELECT COUNT(*) FROM agent_messages WHERE status='done'").fetchone()[0]
    failed  = conn.execute("SELECT COUNT(*) FROM agent_messages WHERE status='failed'").fetchone()[0]
    top_agents = conn.execute(
        """SELECT from_agent, COUNT(*) as cnt FROM agent_messages
           GROUP BY from_agent ORDER BY cnt DESC LIMIT 5"""
    ).fetchall()
    close_conn()
    return {
        "total":      total,
        "pending":    pending,
        "done":       done,
        "failed":     failed,
        "top_agents": [{"agent": r[0], "count": r[1]} for r in top_agents],
    }


# ─── Coordinator (the router that processes pending messages) ──────────────────

def process_pending_messages(max_per_run: int = 5) -> list[dict]:
    """
    Called by the APScheduler every 5 minutes OR triggered manually.
    Picks up pending messages and dispatches them to the right agent function.
    Returns list of results.
    """
    # Collect all pending messages across all agents
    conn = get_conn()
    rows = conn.execute(
        """SELECT id, from_agent, to_agent, intent, payload
           FROM agent_messages
           WHERE status='pending'
           ORDER BY priority DESC, created_at ASC
           LIMIT ?""",
        (max_per_run,)
    ).fetchall()
    close_conn()

    if not rows:
        return []

    results = []
    for row in rows:
        msg_id, from_a, to_a, intent, payload_raw = row
        payload = _safe_json(payload_raw)

        print(f"[BUS COORDINATOR] Processing msg {msg_id}: {from_a}→{to_a} [{intent}]")

        try:
            result = _dispatch(to_a, intent, payload)
            complete_message(msg_id, result)
            results.append({"id": msg_id, "intent": intent, "status": "done"})
        except Exception as e:
            fail_message(msg_id, str(e))
            results.append({"id": msg_id, "intent": intent, "status": "failed", "error": str(e)})
            print(f"[BUS COORDINATOR] msg {msg_id} failed: {e}")

    return results


def _dispatch(to_agent: str, intent: str, payload: dict) -> Any:
    """
    Route a message to the correct agent function.
    Each agent exposes a handle_message(intent, payload) or specific functions.
    """

    # ── Research agent ──────────────────────────────────────
    if to_agent == "research":
        from agents.research_agent import deep_research, write_essay, generate_presentation

        if intent == "research.run":
            return deep_research(payload.get("query", ""), n_sources=payload.get("n_sources", 8))
        if intent == "research.essay":
            return write_essay(payload.get("topic", ""), style=payload.get("style", "analytical"),
                               length=payload.get("length", "medium"))
        if intent == "research.presentation":
            return generate_presentation(payload.get("topic", ""), slides=payload.get("slides", 10))

    # ── Content agent ───────────────────────────────────────
    elif to_agent == "content":
        from agents.content_agent import create_draft

        if intent == "content.generate":
            return create_draft(
                topic=payload.get("topic", ""),
                content_type=payload.get("content_type", "post"),
                tone=payload.get("tone", "professional"),
                length=payload.get("length", "medium"),
                platform=payload.get("platform"),
            )

    # ── Code agent ──────────────────────────────────────────
    elif to_agent == "code":
        from agents.code_agent import scan_repo, scan_all_repos

        if intent == "code.scan":
            repo = payload.get("repo", "")
            return scan_repo(repo) if repo else scan_all_repos()

    # ── Notifier ─────────────────────────────────────────────
    elif to_agent == "notifier":
        from intelligence.notifier import notify # pyright: ignore[reportAttributeAccessIssue]

        if intent == "notify.send":
            notify(payload.get("message", ""), is_alert=payload.get("is_alert", False))
            return {"sent": True}

    # ── Memory agent ─────────────────────────────────────────
    elif to_agent == "memory":
        from intelligence.learning_engine import store_fact

        if intent == "memory.store":
            store_fact(
                category=payload.get("category", "general"),
                subject=payload.get("subject", "Elisha"),
                predicate=payload.get("predicate", ""),
                obj=payload.get("object", ""),
                confidence=payload.get("confidence", 0.8),
                source=payload.get("source", "agent_bus"),
            )
            return {"stored": True}

    # ── Executive / planner ──────────────────────────────────
    elif to_agent == "executive":
        if intent == "executive.plan":
            try:
                from intelligence.planner_engine import generate_daily_plan # pyright: ignore[reportAttributeAccessIssue]
                return generate_daily_plan()
            except ImportError:
                from briefing import send_morning_briefing
                send_morning_briefing()
                return {"sent": True}

    raise ValueError(f"Unknown agent '{to_agent}' or intent '{intent}'")


# ─── Convenience: high-level dispatch helpers ─────────────────────────────────

def request_research(query: str, from_agent: str = "user", priority: int = 7) -> int:
    """Post a research request. Returns message ID."""
    return post_message(from_agent, "research", "research.run",
                        {"query": query}, priority=priority)


def request_content(topic: str, content_type: str = "post", tone: str = "professional",
                    from_agent: str = "user", priority: int = 6) -> int:
    """Post a content generation request. Returns message ID."""
    return post_message(from_agent, "content", "content.generate",
                        {"topic": topic, "content_type": content_type, "tone": tone},
                        priority=priority)


def notify_user(message: str, from_agent: str = "orchestrator", priority: int = 8) -> int:
    """Post a notification request. Returns message ID."""
    return post_message(from_agent, "notifier", "notify.send",
                        {"message": message}, priority=priority)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _safe_json(s: str | None) -> dict:
    try:
        return json.loads(s) if s else {}
    except Exception:
        return {}
