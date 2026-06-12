"""
ORA Gmail Connector — multi-account + promotions filter
- Reads from PRIMARY and SECONDARY Google accounts
- Filters out promotions, social, updates, forums by default
- All existing function signatures unchanged (backward-compatible)
- New: account= parameter on key functions for per-account calls
"""

from __future__ import annotations

import base64
import re
import traceback
from typing import List, Optional

from connectors.google_auth import (
    get_access_token,
    is_authorized,
    get_all_authorized_accounts,
)
from database import get_conn, close_conn

GMAIL_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"

# ─────────────────────────────────────────────
# PROMOTIONS FILTER
# Applied to every email fetch by default.
# Gmail search syntax — same as the search bar.
# ─────────────────────────────────────────────
INBOX_FILTER = (
    "in:inbox "
    "-category:promotions "
    "-category:social "
    "-category:updates "
    "-category:forums"
)


# ─────────────────────────────────────────────
# DB INIT
# ─────────────────────────────────────────────

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
            account        TEXT DEFAULT 'primary',
            created_at     TEXT DEFAULT (datetime('now')),
            updated_at     TEXT DEFAULT (datetime('now'))
        )
    """)
    # Add account column to existing tables that don't have it
    try:
        conn.execute("ALTER TABLE suggested_replies ADD COLUMN account TEXT DEFAULT 'primary'")
        conn.commit()
    except Exception:
        pass  # column already exists
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_replies_status
        ON suggested_replies(status, created_at DESC)
    """)
    conn.commit()
    close_conn()
    print("[GMAIL] Tables ready (multi-account)")


# ─────────────────────────────────────────────
# RAW HTTP HELPERS
# ─────────────────────────────────────────────

def _headers(account: str = "primary") -> dict:
    return {"Authorization": f"Bearer {get_access_token(account)}"}


def _gmail_get(path: str, params: dict | None = None,
               account: str = "primary") -> dict:
    import requests
    url = f"{GMAIL_BASE}/{path}"
    r = requests.get(url, headers=_headers(account),
                     params=params or {}, timeout=15)
    r.raise_for_status()
    return r.json()


def _gmail_post(path: str, body: dict, account: str = "primary") -> dict:
    import requests
    url = f"{GMAIL_BASE}/{path}"
    r = requests.post(
        url,
        headers={**_headers(account), "Content-Type": "application/json"},
        json=body,
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


# ─────────────────────────────────────────────
# EMAIL PARSING HELPERS  (unchanged)
# ─────────────────────────────────────────────

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

    plain = next((p for p in parts if p.get("mimeType") == "text/plain"), None)
    if plain:
        return _extract_body(plain)
    for part in parts:
        result = _extract_body(part)
        if result:
            return result
    return ""


def _parse_message(msg: dict, account: str = "primary") -> dict:
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
        "account":   account,   # NEW: tag each email with its source account
    }


# ─────────────────────────────────────────────
# CORE FETCH — single account, with filter
# ─────────────────────────────────────────────

def _fetch_emails_for_account(
    account: str,
    max_results: int = 15,
    include_promotions: bool = False,
) -> List[dict]:
    """Fetch filtered emails for one account (read + unread unless include_promotions changes query)."""
    if not is_authorized(account):
        return []
    try:
        query = "in:inbox is:unread" if include_promotions else INBOX_FILTER
        data  = _gmail_get("messages", {"q": query, "maxResults": max_results},
                           account=account)
        refs  = data.get("messages", [])
        emails = []
        for ref in refs:
            try:
                msg = _gmail_get(f"messages/{ref['id']}", {"format": "full"},
                                 account=account)
                emails.append(_parse_message(msg, account=account))
            except Exception as e:
                print(f"[GMAIL:{account}] fetch {ref['id']} failed: {e}")
        return emails
    except Exception as e:
        print(f"[GMAIL:{account}] _fetch_emails failed: {e}")
        return []


# ─────────────────────────────────────────────
# PUBLIC FUNCTIONS  (backward-compatible signatures)
# ─────────────────────────────────────────────

def get_gmail_summary() -> dict:
    """
    Returns total and unread counts per account (primary + secondary if connected).
    Total excludes promotions/categories, unread is the subset that's unread.
    """
    try:
        result = {"authorized": False, "unread_count": 0, "accounts": {}}
        any_auth = False

        for account in ("primary", "secondary"):
            if not is_authorized(account):
                result["accounts"][account] = {"authorized": False, "unread_count": 0}
                continue
            try:
                any_auth = True
                data = _gmail_get(
                    "messages",
                    {"q": INBOX_FILTER, "maxResults": 1},
                    account=account,
                )
                unread_data = _gmail_get(
                    "messages",
                    {"q": INBOX_FILTER + " is:unread", "maxResults": 1},
                    account=account,
                )
                total_count  = data.get("resultSizeEstimate", 0)
                unread_count = unread_data.get("resultSizeEstimate", 0)
                result["accounts"][account] = {
                    "authorized": True,
                    "total_count": total_count,
                    "unread_count": unread_count,
                }
                result["unread_count"] += unread_count
            except Exception as e:
                print(f"[GMAIL:{account}] summary failed: {e}")
                result["accounts"][account] = {"authorized": True, "unread_count": 0}

        result["authorized"] = any_auth
        return result

    except Exception as e:
        print(f"[GMAIL] summary failed: {e}")
        return {"authorized": False, "unread_count": 0}


def get_unread_count() -> int:
    """Quick integer unread count across all accounts (no promotions)."""
    summary = get_gmail_summary()
    return summary.get("unread_count", 0)


def get_recent_emails(
    max_results: int = 15,
    include_promotions: bool = False,
) -> List[dict]:
    """
    Fetch recent primary-inbox emails from ALL authorized accounts.
    By default fetches all emails (read + unread) excluding promotions/social/updates.
    When include_promotions=True, fetches only unread emails across all categories.
    Results are merged and sorted newest-first.
    """
    all_emails: List[dict] = []
    per_account = max(5, max_results // len(get_all_authorized_accounts() or ["primary"]))

    for account in ("primary", "secondary"):
        emails = _fetch_emails_for_account(
            account,
            max_results=per_account,
            include_promotions=include_promotions,
        )
        all_emails.extend(emails)

    # Sort by date header (best-effort; keep original order on parse failure)
    try:
        from email.utils import parsedate_to_datetime
        def _ts(e):
            try:
                return parsedate_to_datetime(e["date"]).timestamp()
            except Exception:
                return 0
        all_emails.sort(key=_ts, reverse=True)
    except Exception:
        pass

    return all_emails[:max_results]


# ─────────────────────────────────────────────
# PRIORITY SCORING  (unchanged logic)
# ─────────────────────────────────────────────

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
    if "IMPORTANT" in labels:           score += 15
    if "CATEGORY_PROMOTIONS" in labels: score -= 20
    if "CATEGORY_UPDATES" in labels:    score -= 10
    return min(100, max(0, score))


# ─────────────────────────────────────────────
# COMMUNICATION AGENT  (unchanged, now multi-account aware)
# ─────────────────────────────────────────────

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
        account = email_data.get("account", "primary")
        acct_label = "" if account == "primary" else f" (via your {account} account)"

        prompt = f"""You are ORA, the personal AI assistant for Elisha Oigara (software engineer, Nairobi).
Write a reply to this email on Elisha's behalf{acct_label}.

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
    account:        str = "primary",
) -> bool:
    try:
        conn = get_conn()
        conn.execute("""
            INSERT INTO suggested_replies
                (email_id, thread_id, subject, sender, email_body, suggested_text, tone, account)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (email_id, thread_id, subject[:300], sender[:200],
               email_body[:1000], suggested_text, tone, account))
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
                   email_body, suggested_text, tone, status, created_at,
                   COALESCE(account, 'primary') as account
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
                "created_at": r[9], "account": r[10],
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
    try:
        conn = get_conn()
        row = conn.execute("""
            SELECT email_id, subject, sender, email_body,
                   COALESCE(account, 'primary')
            FROM suggested_replies WHERE id=?
        """, (reply_id,)).fetchone()
        close_conn()
        if not row:
            return {"ok": False, "error": "Not found"}

        email_data = {
            "id": row[0], "subject": row[1], "sender": row[2],
            "body": row[3], "account": row[4],
        }
        new_text = suggest_reply(email_data, tone=tone)
        ok = update_reply_text(reply_id, new_text)

        conn = get_conn()
        conn.execute("UPDATE suggested_replies SET tone=?, updated_at=datetime('now') WHERE id=?",
                     (tone, reply_id))
        conn.commit()
        close_conn()

        return {"ok": ok, "suggested_text": new_text}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def approve_and_send_reply(reply_id: int) -> dict:
    try:
        conn = get_conn()
        row = conn.execute("""
            SELECT email_id, thread_id, subject, sender, suggested_text,
                   COALESCE(account, 'primary')
            FROM suggested_replies WHERE id=?
        """, (reply_id,)).fetchone()
        close_conn()

        if not row:
            return {"ok": False, "error": "Reply not found"}

        email_id, thread_id, subject, sender, text, account = row
        sent      = False
        error_msg = None

        if is_authorized(account):
            try:
                _send_gmail_reply(to=sender, subject=subject,
                                  thread_id=thread_id, body=text,
                                  account=account)
                sent = True
            except Exception as e:
                error_msg = str(e)
                print(f"[GMAIL_REPLY:{account}] send failed: {e}")

        new_status = "sent" if sent else "approved"
        conn = get_conn()
        conn.execute("""
            UPDATE suggested_replies
            SET status=?, updated_at=datetime('now')
            WHERE id=?
        """, (new_status, reply_id))
        conn.commit()
        close_conn()

        return {"ok": True, "sent": sent, "status": new_status,
                "error": error_msg, "account": account}

    except Exception as e:
        print(f"[GMAIL_REPLY] approve_and_send failed: {e}")
        return {"ok": False, "error": str(e)}


def _send_gmail_reply(to: str, subject: str, thread_id: Optional[str],
                      body: str, account: str = "primary") -> None:
    from email.mime.text import MIMEText
    msg = MIMEText(body)
    msg["To"]      = to
    msg["Subject"] = subject if subject.startswith("Re:") else f"Re: {subject}"
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
    payload: dict = {"raw": raw}
    if thread_id:
        payload["threadId"] = thread_id
    _gmail_post("messages/send", payload, account=account)


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
                   created_at, updated_at, COALESCE(account, 'primary')
            FROM suggested_replies
            WHERE status IN ('sent', 'approved', 'rejected')
            ORDER BY updated_at DESC LIMIT ?
        """, (limit,)).fetchall()
        close_conn()
        return [
            {"id": r[0], "subject": r[1], "sender": r[2], "text": r[3],
             "status": r[4], "tone": r[5], "created_at": r[6],
             "updated_at": r[7], "account": r[8]}
            for r in rows
        ]
    except Exception:
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


# ─────────────────────────────────────────────
# SCHEDULER HOOK
# ─────────────────────────────────────────────

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
                account=email.get("account", "primary"),
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


print("[GMAIL] Multi-account connector loaded")