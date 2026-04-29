"""
ORA Content Creation Agent
Generates social posts, captions, emails, threads, etc. using Groq.
Stores drafts in content_drafts table for review/approval.
"""

from typing import Dict, Any, Optional
import json

from groq import Groq
from config import GROQ_API_KEY
from database import get_conn, close_conn
from ai_gateway import safe_ai_call
from ai_brain import ask_groq

client = Groq(api_key=GROQ_API_KEY)


def init_content_drafts_table():
    """Create content_drafts table on startup."""
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS content_drafts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content_type TEXT DEFAULT 'post',
            topic TEXT,
            draft_text TEXT NOT NULL,
            tone TEXT DEFAULT 'professional',
            length TEXT DEFAULT 'medium',
            status TEXT DEFAULT 'draft',           -- draft, approved, sent, rejected
            target_platform TEXT DEFAULT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            metadata TEXT DEFAULT '{}'
        )
    """)
    conn.commit()
    close_conn()
    print("[CONTENT_AGENT] content_drafts table ready")


def create_draft(
    topic: str,
    content_type: str = "post",
    tone: str = "professional",
    length: str = "medium",
    target_platform: Optional[str] = None,
    extra_context: str = ""
) -> Dict[str, Any]:
    """Generate and store a content draft."""
    try:
        system_prompt = f"""You are ORA's Content Agent for Elisha Oigara (Nairobi-based founder building autonomous AI systems).
Write clear, engaging, professional-yet-warm content.
Tone: {tone}. Target length: {length}.
Platform/context: {target_platform or 'general'}.

Generate a ready-to-use {content_type} about: {topic}

Rules:
- Be concise and actionable
- Use natural emojis sparingly
- Include a strong hook and clear call-to-action when appropriate
- Return ONLY the final draft text. No explanations.
"""

        user_msg = f"Topic: {topic}\nExtra context: {extra_context[:800]}"

        # Use safe_ai_call for budget/cooldown protection (fallback if not available)
        try:
            result = safe_ai_call(ask_groq, user_msg)
        except NameError:
            result = ask_groq(user_msg)

        if isinstance(result, dict) and "reply" in result:
            draft_text = result["reply"]
        else:
            draft_text = str(result).strip()

        # Save to DB
        conn = get_conn()
        c = conn.cursor()
        c.execute("""
            INSERT INTO content_drafts 
            (title, content_type, topic, draft_text, tone, length, target_platform, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            f"{content_type.title()}: {topic[:90]}",
            content_type,
            topic,
            draft_text,
            tone,
            length,
            target_platform,
            json.dumps({"extra_context": extra_context[:500]})
        ))
        draft_id = c.lastrowid
        conn.commit()
        close_conn()

        return {
            "id": draft_id,
            "status": "success",
            "draft": draft_text,
            "type": content_type,
            "topic": topic,
            "tone": tone
        }

    except Exception as e:
        print(f"[CONTENT_AGENT] create_draft failed: {e}")
        return {"status": "error", "error": str(e)}


def get_drafts(status: str = "draft", limit: int = 20):
    """List drafts."""
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT id, title, content_type, topic, draft_text, tone, status, created_at 
        FROM content_drafts 
        WHERE status = ? 
        ORDER BY created_at DESC LIMIT ?
    """, (status, limit))
    rows = c.fetchall()
    close_conn()
    return [
        {
            "id": r[0], "title": r[1], "type": r[2], "topic": r[3],
            "draft": r[4], "tone": r[5], "status": r[6], "ts": r[7]
        }
        for r in rows
    ]


def update_draft_status(draft_id: int, new_status: str):
    """Approve / reject / mark sent."""
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE content_drafts SET status=? WHERE id=?", (new_status, draft_id))
    conn.commit()
    close_conn()
    return c.rowcount > 0