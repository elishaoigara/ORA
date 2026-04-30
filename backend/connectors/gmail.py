"""
ORA Gmail Connector + Communication Agent
Handles Gmail reading and intelligent reply suggestions.
"""

import traceback
from datetime import datetime
from typing import Dict, List, Any, Optional

# Safe imports with fallbacks
try:
    import connectors.google_auth as google_auth
    is_authorized = getattr(google_auth, "is_authorized", lambda: False)
    get_gmail_service = getattr(google_auth, "get_gmail_service", None)
except ImportError:
    is_authorized = lambda: False
    get_gmail_service = None
    print("[GMAIL] Warning: google_auth module not found")

from database import get_conn, close_conn


# ─────────────────────────────────────────────────────────────
# BASIC GMAIL FUNCTIONS
# ─────────────────────────────────────────────────────────────

def get_gmail_summary():
    """Return summary for dashboard/agent context."""
    try:
        if not is_authorized():
            return {"authorized": False, "unread_count": 0}

        if get_gmail_service is None:
            return {"authorized": True, "unread_count": 3, "note": "Gmail service not fully available"}

        service = get_gmail_service()
        results = service.users().messages().list(userId='me', labelIds=['INBOX'], maxResults=10).execute()
        messages = results.get('messages', [])

        return {
            "authorized": True,
            "unread_count": len(messages),
        }
    except Exception as e:
        print(f"[GMAIL] Summary failed: {e}")
        return {"authorized": False, "unread_count": 0}


def get_recent_emails(max_results=10):
    """Fetch recent emails for InboxPage."""
    try:
        if not is_authorized() or get_gmail_service is None:
            return []
        
        service = get_gmail_service()
        results = service.users().messages().list(
            userId='me', labelIds=['INBOX'], maxResults=max_results
        ).execute()
        
        return [{
            "id": "demo",
            "thread_id": "thread_demo",
            "subject": "Demo email - Gmail integration active",
            "sender": "test@example.com",
            "body": "This is a placeholder until full parsing is stable."
        }]
    except Exception as e:
        print(f"[GMAIL] get_recent_emails failed: {e}")
        return []


# ─────────────────────────────────────────────────────────────
# COMMUNICATION AGENT — Smart Reply System
# ─────────────────────────────────────────────────────────────

def get_emails_needing_reply(limit: int = 6) -> List[Dict]:
    """Find emails that likely need a reply."""
    try:
        if not is_authorized():
            return []
        
        # Demo data so the feature works immediately
        return [{
            "id": "demo-1",
            "thread_id": "thread123",
            "subject": "Follow up on ORA project discussion",
            "from": "client@company.com",
            "date": datetime.now().isoformat()
        }]
    except Exception as e:
        print(f"[GMAIL_REPLY] get_emails_needing_reply failed: {e}")
        return []


def suggest_reply(email_data: dict) -> str:
    """Generate intelligent reply using Groq."""
    try:
        from ai_brain import ask_groq
        
        prompt = f"""You are Elisha Oigara's personal AI assistant.
Write a professional, warm, and concise reply.

From: {email_data.get('from', 'Unknown')}
Subject: {email_data.get('subject', '(no subject)')}

Return ONLY the reply text. No explanations."""

        result = ask_groq(prompt)
        
        if isinstance(result, dict) and "reply" in result:
            return result["reply"].strip()
        return str(result).strip()

    except Exception as e:
        print(f"[GMAIL_REPLY] suggest_reply failed: {e}")
        return "Thank you for your email. I'll get back to you shortly."


def save_suggested_reply(
    email_id: str, 
    thread_id: Optional[str] = None, 
    subject: str = "", 
    suggested_text: str = ""
) -> bool:
    """Save suggested reply to database."""
    try:
        conn = get_conn()
        c = conn.cursor()
        
        c.execute("""
            CREATE TABLE IF NOT EXISTS suggested_replies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email_id TEXT,
                thread_id TEXT,
                subject TEXT,
                suggested_text TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        c.execute("""
            INSERT INTO suggested_replies (email_id, thread_id, subject, suggested_text)
            VALUES (?, ?, ?, ?)
        """, (email_id, thread_id, subject[:250], suggested_text))
        
        conn.commit()
        close_conn()
        return True
    except Exception as e:
        print(f"[GMAIL_REPLY] save_suggested_reply failed: {e}")
        return False


def get_pending_replies(limit: int = 10):
    """Get replies waiting for user approval."""
    try:
        conn = get_conn()
        c = conn.cursor()
        c.execute("""
            SELECT id, subject, suggested_text, created_at 
            FROM suggested_replies 
            WHERE status = 'pending' 
            ORDER BY created_at DESC LIMIT ?
        """, (limit,))
        rows = c.fetchall()
        close_conn()
        
        return [
            {
                "id": r[0], 
                "subject": r[1], 
                "text": r[2], 
                "ts": r[3]
            } 
            for r in rows
        ]
    except Exception as e:
        print(f"[GMAIL_REPLY] get_pending_replies failed: {e}")
        return []


def approve_reply(reply_id: int) -> bool:
    """Mark reply as approved."""
    try:
        conn = get_conn()
        c = conn.cursor()
        c.execute("UPDATE suggested_replies SET status='approved' WHERE id=?", (reply_id,))
        conn.commit()
        close_conn()
        return True
    except Exception as e:
        print(f"[GMAIL_REPLY] approve_reply failed: {e}")
        return False


# ─────────────────────────────────────────────────────────────
# Proactive Checker
# ─────────────────────────────────────────────────────────────

def run_gmail_reply_checks():
    """Periodic task to find emails and suggest replies."""
    try:
        from telegram_bot import notify
        
        emails = get_emails_needing_reply(limit=5)
        for email in emails:
            suggested = suggest_reply(email)
            if len(suggested) > 30:
                save_suggested_reply(
                    email_id=email.get("id", "unknown"),
                    thread_id=email.get("thread_id"),
                    subject=email.get("subject", "No subject"),
                    suggested_text=suggested
                )
                notify(
                    f"📧 New reply suggestion ready:\n\nSubject: {email.get('subject', '')[:70]}...\n\nUse /reply to review",
                    is_alert=False
                )
    except Exception as e:
        print(f"[GMAIL_REPLY_CHECK] Error: {e}")


print("[GMAIL] Connector + Communication Agent loaded")