"""
ORA Gmail Connector — Phase 2: Communication Agent
- Real email parsing (headers, body, thread context)
- AI smart reply generation with tone/context awareness
- Send reply via Gmail REST API
- Inbox triage: priority scoring per email
- Pending reply queue with approve/reject/edit
"""

from __future__ import annotations

import base64
import re
import traceback
from typing import List, Optional

from connectors.google_auth import get_access_token, is_authorized
from database import get_conn, close_conn

GMAIL_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"


# ─────────────────────────────────────────────────────────────
# DB INIT
# ─────────────────────────────────────────────────────────────

def init_gmail_tables() -> None:
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS suggested_replies (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            email_id       TEXT NOT NULL,
            thread_id      TEXT,
            subject        TEXT,
            sender         TEXT,
            email_body     TEXT,
            suggested_text TEXT NOT NULL,
            tone           TEXT DEFAULT 'professional',
            status         TEXT DEFAULT 'pending',
            created_at     TEXT DEFAULT (datetime('now')),
            updated_at     TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_replies_status
        ON suggested_replies(status, created_at DESC)
    """)
    conn.commit()
    close_conn()
    print("[GMAIL] Tables ready")


# ─────────────────────────────────────────────────────────────
# RAW HTTP HELPERS (no google-api-python-client needed)
# ─────────────────────────────────────────────────────────────

def _headers() -> dict:
    return {"Authorization": f"Bearer {get_access_token()}"}


def _gmail_get(path: str, params: dict | None = None) -> dict:
    import requests
    url = f"{GMAIL_BASE}/{path}"
    r = requests.get(url, headers=_headers(), params=params or {}, timeout=15)
    r.raise_for_status()
    return r.json()


def _gmail_post(path: str, body: dict) -> dict:
    import requests
    url = f"{GMAIL_BASE}/{path}"
    r = requests.post(url, headers={**_headers(), "Content-Type": "application/json"},
                      json=body, timeout=15)
    r.raise_for_status()
    return r.json()


# ─────────────────────────────────────────────────────────────
# EMAIL PARSING HELPERS
# ─────────────────────────────────────────────────────────────

def _decode_header_value(raw: str) -> str:
    try:
        from email.header import decode_header
        parts = decode_header(raw or "")
        out = []
        for part, charset in parts:
            if isinstance(part, bytes):
                out.append(part.decode(charset or "utf-8", errors="replace"))
            else:
                out.append(str(part))
        return " ".join(out)
    except Exception:
        return raw or ""


def _extract_body(payload: dict) -> str:
    mime  = payload.get("mimeType", "")
    parts = payload.get("parts", [])
    data  = payload.get("body", {}).get("data", "")

    if mime == "text/plain" and data:
        try:
            decoded = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
            lines = decoded.split("\n")
            clean = []
            for line in lines:
                if line.startswith(">") or re.match(r"On .+wrote:", line):
                    break
                clean.append(line)
            return "\n".join(clean).strip()[:1500]
        except Exception:
            return ""

    if mime == "text/html" and data and not parts:
        try:
            html = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
            text = re.sub(r"<[^>]+>", " ", html)
            return re.sub(r"\s+", " ", text).strip()[:1500]
        except Exception:
            return ""

    # multipart — prefer plain, fallback to html
    plain = next((p for p in parts if p.get("mimeType") == "text/plain"), None)
    if plain:
        return _extract_body(plain)
    for part in parts:
        result = _extract_body(part)
        if result:
            return result
    return ""


def _parse_message(msg: dict) -> dict:
    hdrs = {h["name"].lower(): h["value"]
            for h in msg.get("payload", {}).get("headers", [])}
    return {
        "id":        msg.get("id", ""),
        "thread_id": msg.get("threadId", ""),
        "subject":   _decode_header_value(hdrs.get("subject", "(no subject)")),
        "sender":    _decode_header_value(hdrs.get("from", "")),
        "to":        _decode_header_value(hdrs.get("to", "")),
        "date":      hdrs.get("date", ""),
        "labels":    msg.get("labelIds", []),
        "body":      _extract_body(msg.get("payload", {})),
        "snippet":   msg.get("snippet", ""),
    }


# ─────────────────────────────────────────────────────────────
# BASIC GMAIL FUNCTIONS (used by InboxPage + sidebar badge)
# ─────────────────────────────────────────────────────────────

def get_gmail_summary() -> dict:
    try:
        if not is_authorized():
            return {"authorized": False, "unread_count": 0}
        data = _gmail_get("messages", {"labelIds": "UNREAD", "maxResults": 1})
        unread = data.get("resultSizeEstimate", 0)
        return {"authorized": True, "unread_count": unread}
    except Exception as e:
        print(f"[GMAIL] summary failed: {e}")
        return {"authorized": False, "unread_count": 0}


def get_recent_emails(max_results: int = 15) -> List[dict]:
    """Fetch recent unread emails with full body parsing."""
    try:
        if not is_authorized():
            return []
        data = _gmail_get("messages", {
            "labelIds": ["INBOX", "UNREAD"],
            "maxResults": max_results,
        })
        refs = data.get("messages", [])
        emails = []
        for ref in refs:
            try:
                msg = _gmail_get(f"messages/{ref['id']}", {"format": "full"})
                emails.append(_parse_message(msg))
            except Exception as e:
                print(f"[GMAIL] fetch {ref['id']} failed: {e}")
        return emails
    except Exception as e:
        print(f"[GMAIL] get_recent_emails failed: {e}")
        return []


# ─────────────────────────────────────────────────────────────
# PRIORITY SCORING — which emails need a reply
# ─────────────────────────────────────────────────────────────

_NO_REPLY_SENDERS = re.compile(
    r"no.?reply|noreply|do-not-reply|donotreply|newsletter|notification|"
    r"automated|mailer-daemon|bounce|unsubscribe",
    re.I
)


def _needs_reply(email: dict) -> bool:
    sender  = email.get("sender", "")
    subject = email.get("subject", "")
    if _NO_REPLY_SENDERS.search(sender) or _NO_REPLY_SENDERS.search(subject):
        return False
    if not email.get("body", "").strip():
        return False
    return True


def _priority_score(email: dict) -> int:
    score   = 50
    subject = (email.get("subject") or "").lower()
    body    = (email.get("body") or "").lower()
    labels  = email.get("labels", [])

    for w in ["urgent", "asap", "immediately", "critical", "emergency", "deadline"]:
        if w in subject: score += 20
        if w in body[:400]: score += 5
    if "?" in body[:600]:  score += 10
    to = (email.get("to") or "").lower()
    if "@" in to and len(to.split(",")) == 1:
        score += 8
    if "IMPORTANT" in labels:          score += 15
    if "CATEGORY_PROMOTIONS" in labels: score -= 20
    if "CATEGORY_UPDATES" in labels:    score -= 10
    return min(100, max(0, score))


# ─────────────────────────────────────────────────────────────
# COMMUNICATION AGENT
# ─────────────────────────────────────────────────────────────

def get_emails_needing_reply(limit: int = 8) -> List[dict]:
    try:
        emails = get_recent_emails(max_results=30)
        if not emails:
            return []

        conn = get_conn()
        already_queued = {r[0] for r in conn.execute(
            "SELECT email_id FROM suggested_replies WHERE status='pending'"
        ).fetchall()}
        close_conn()

        candidates = []
        for e in emails:
            if e["id"] in already_queued:
                continue
            if not _needs_reply(e):
                continue
            e["_priority"] = _priority_score(e)
            candidates.append(e)

        candidates.sort(key=lambda x: x["_priority"], reverse=True)
        return candidates[:limit]
    except Exception as e:
        print(f"[GMAIL_REPLY] get_emails_needing_reply failed: {e}")
        return []


def suggest_reply(email_data: dict, tone: str = "professional") -> str:
    """Generate a context-aware smart reply via Groq."""
    try:
        from ai_brain import ask_groq

        tone_guide = {
            "professional": "professional and warm — clear, direct, not stuffy",
            "friendly":     "friendly and conversational, like writing to a colleague",
            "brief":        "very brief — 2-3 sentences max with a clear next step",
            "formal":       "formal and structured for business/legal correspondence",
        }.get(tone, "professional and concise")

        sender  = email_data.get("sender", "Unknown")
        subject = email_data.get("subject", "(no subject)")
        body    = (email_data.get("body") or email_data.get("snippet") or "")[:900]

        prompt = f"""You are ORA, the personal AI assistant for Elisha Oigara (software engineer, Nairobi).
Write a reply to this email on Elisha's behalf.

Tone: {tone_guide}

--- EMAIL ---
From: {sender}
Subject: {subject}
Body:
{body}
--- END ---

Rules:
- Write ONLY the reply body. No salutation, no signature, no subject line.
- Be genuine. If a question is asked, answer it or offer to follow up with a specific timeframe.
- Keep it under 150 words unless the email genuinely requires more.
- End with one clear next step or a warm closing.

Reply:"""

        result = ask_groq(prompt)
        if isinstance(result, dict):
            text = result.get("reply") or result.get("raw") or result.get("text") or str(result)
        else:
            text = str(result)
        return text.strip()

    except Exception as e:
        print(f"[GMAIL_REPLY] suggest_reply failed: {e}")
        return "Thanks for reaching out — I'll follow up with you shortly."


def save_suggested_reply(
    email_id:       str,
    thread_id:      Optional[str] = None,
    subject:        str = "",
    sender:         str = "",
    email_body:     str = "",
    suggested_text: str = "",
    tone:           str = "professional",
) -> bool:
    try:
        conn = get_conn()
        conn.execute("""
            INSERT INTO suggested_replies
                (email_id, thread_id, subject, sender, email_body, suggested_text, tone)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (email_id, thread_id, subject[:300], sender[:200],
               email_body[:1000], suggested_text, tone))
        conn.commit()
        close_conn()
        return True
    except Exception as e:
        print(f"[GMAIL_REPLY] save failed: {e}")
        return False


def get_pending_replies(limit: int = 15) -> List[dict]:
    try:
        conn = get_conn()
        rows = conn.execute("""
            SELECT id, email_id, thread_id, subject, sender,
                   email_body, suggested_text, tone, status, created_at
            FROM suggested_replies
            WHERE status = 'pending'
            ORDER BY created_at DESC LIMIT ?
        """, (limit,)).fetchall()
        close_conn()
        return [
            {
                "id": r[0], "email_id": r[1], "thread_id": r[2],
                "subject": r[3], "sender": r[4], "email_body": r[5],
                "suggested_text": r[6], "tone": r[7], "status": r[8],
                "created_at": r[9],
            }
            for r in rows
        ]
    except Exception as e:
        print(f"[GMAIL_REPLY] get_pending failed: {e}")
        return []


def update_reply_text(reply_id: int, new_text: str) -> bool:
    try:
        conn = get_conn()
        conn.execute("""
            UPDATE suggested_replies
            SET suggested_text=?, updated_at=datetime('now')
            WHERE id=?
        """, (new_text, reply_id))
        conn.commit()
        close_conn()
        return True
    except Exception as e:
        print(f"[GMAIL_REPLY] update_text failed: {e}")
        return False


def regenerate_reply(reply_id: int, tone: str = "professional") -> dict:
    """Re-generate the suggested text for an existing pending reply."""
    try:
        conn = get_conn()
        row = conn.execute("""
            SELECT email_id, subject, sender, email_body
            FROM suggested_replies WHERE id=?
        """, (reply_id,)).fetchone()
        close_conn()
        if not row:
            return {"ok": False, "error": "Not found"}

        email_data = {"id": row[0], "subject": row[1], "sender": row[2], "body": row[3]}
        new_text = suggest_reply(email_data, tone=tone)
        ok = update_reply_text(reply_id, new_text)

        # Also update tone
        conn = get_conn()
        conn.execute("UPDATE suggested_replies SET tone=?, updated_at=datetime('now') WHERE id=?",
                     (tone, reply_id))
        conn.commit()
        close_conn()

        return {"ok": ok, "suggested_text": new_text}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def approve_and_send_reply(reply_id: int) -> dict:
    """
    Approve a reply. Attempts to send via Gmail REST API.
    If gmail.send scope is missing, marks as 'approved' (user copies manually).
    """
    try:
        conn = get_conn()
        row = conn.execute("""
            SELECT email_id, thread_id, subject, sender, suggested_text
            FROM suggested_replies WHERE id=?
        """, (reply_id,)).fetchone()
        close_conn()

        if not row:
            return {"ok": False, "error": "Reply not found"}

        email_id, thread_id, subject, sender, text = row
        sent      = False
        error_msg = None

        if is_authorized():
            try:
                _send_gmail_reply(to=sender, subject=subject,
                                  thread_id=thread_id, body=text)
                sent = True
            except Exception as e:
                # Likely missing gmail.send scope — degrade gracefully
                error_msg = str(e)
                print(f"[GMAIL_REPLY] send failed (marking approved): {e}")

        new_status = "sent" if sent else "approved"
        conn = get_conn()
        conn.execute("""
            UPDATE suggested_replies
            SET status=?, updated_at=datetime('now')
            WHERE id=?
        """, (new_status, reply_id))
        conn.commit()
        close_conn()

        return {"ok": True, "sent": sent, "status": new_status, "error": error_msg}

    except Exception as e:
        print(f"[GMAIL_REPLY] approve_and_send failed: {e}")
        return {"ok": False, "error": str(e)}


def _send_gmail_reply(to: str, subject: str,
                      thread_id: Optional[str], body: str) -> None:
    """Send via Gmail REST API /messages/send."""
    from email.mime.text import MIMEText
    import json

    msg = MIMEText(body)
    msg["To"]      = to
    msg["Subject"] = subject if subject.startswith("Re:") else f"Re: {subject}"

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
    payload: dict = {"raw": raw}
    if thread_id:
        payload["threadId"] = thread_id

    _gmail_post("messages/send", payload)


def reject_reply(reply_id: int) -> bool:
    try:
        conn = get_conn()
        conn.execute("""
            UPDATE suggested_replies
            SET status='rejected', updated_at=datetime('now')
            WHERE id=?
        """, (reply_id,))
        conn.commit()
        close_conn()
        return True
    except Exception as e:
        print(f"[GMAIL_REPLY] reject failed: {e}")
        return False


def get_reply_history(limit: int = 20) -> List[dict]:
    try:
        conn = get_conn()
        rows = conn.execute("""
            SELECT id, subject, sender, suggested_text, status, tone,
                   created_at, updated_at
            FROM suggested_replies
            WHERE status IN ('sent', 'approved', 'rejected')
            ORDER BY updated_at DESC LIMIT ?
        """, (limit,)).fetchall()
        close_conn()
        return [
            {"id": r[0], "subject": r[1], "sender": r[2], "text": r[3],
             "status": r[4], "tone": r[5], "created_at": r[6], "updated_at": r[7]}
            for r in rows
        ]
    except Exception as e:
        return []


def get_reply_stats() -> dict:
    try:
        conn = get_conn()
        total    = conn.execute("SELECT COUNT(*) FROM suggested_replies").fetchone()[0]
        pending  = conn.execute("SELECT COUNT(*) FROM suggested_replies WHERE status='pending'").fetchone()[0]
        sent     = conn.execute("SELECT COUNT(*) FROM suggested_replies WHERE status='sent'").fetchone()[0]
        approved = conn.execute("SELECT COUNT(*) FROM suggested_replies WHERE status='approved'").fetchone()[0]
        rejected = conn.execute("SELECT COUNT(*) FROM suggested_replies WHERE status='rejected'").fetchone()[0]
        close_conn()
        return {"total": total, "pending": pending, "sent": sent,
                "approved": approved, "rejected": rejected}
    except Exception:
        return {"total": 0, "pending": 0, "sent": 0, "approved": 0, "rejected": 0}


# ─────────────────────────────────────────────────────────────
# SCHEDULER HOOK — called every 15 min
# ─────────────────────────────────────────────────────────────

def run_gmail_reply_checks() -> None:
    try:
        from telegram_bot import notify
        from agent_guard import can_fire, mark_fired
        import time

        key = f"gmail_check_{int(time.time() // 1800)}"
        if not can_fire(key):
            return

        emails = get_emails_needing_reply(limit=5)
        if not emails:
            mark_fired(key)
            return

        added = 0
        for email in emails:
            suggested = suggest_reply(email)
            if len(suggested) < 20:
                continue
            if save_suggested_reply(
                email_id=email.get("id", "unknown"),
                thread_id=email.get("thread_id"),
                subject=email.get("subject", ""),
                sender=email.get("sender", ""),
                email_body=email.get("body", ""),
                suggested_text=suggested,
            ):
                added += 1

        if added > 0:
            notify(
                f"📧 *{added} reply suggestion(s) ready*\n"
                f"Open Inbox → Smart Replies to review.",
                is_alert=False,
            )
        mark_fired(key)

    except Exception as e:
        print(f"[GMAIL_REPLY_CHECK] Error: {e}")
        print(traceback.format_exc())


print("[GMAIL] Communication Agent v2 loaded")
