"""
ORA Telegram Bot — Phase 2 hardened
- Phase 2 commands: /inbox, /replies, /proactive
- Fixed: get_tasks("all") crash
- Fixed: Telegram "Conflict" spam — single getUpdates loop with proper offset
- Fixed: Groq timeout kwarg removed (not supported in groq SDK)
- Render free tier safe: exponential backoff, no runaway threads
"""

import time
import traceback
import requests
from datetime import datetime
from threading import Lock
from typing import Optional, Dict, Any, List, Tuple
from functools import wraps
from collections import defaultdict

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, GROQ_API_KEY, GROQ_MODEL_PRIMARY
from database import save_conversation, get_conversation_history
from context import build_system_prompt
from groq import Groq


# ─────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────

TELEGRAM_ENABLED  = bool(TELEGRAM_BOT_TOKEN)
BASE              = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}" if TELEGRAM_ENABLED else None
client            = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
ALLOWED_CHAT_ID   = int(TELEGRAM_CHAT_ID) if TELEGRAM_CHAT_ID else None

RATE_LIMIT        = defaultdict(list)
RATE_LIMIT_WINDOW = 60
RATE_LIMIT_MAX    = 20

print("[TELEGRAM] Enabled:", TELEGRAM_ENABLED)


# ─────────────────────────────────────────────
# DECORATORS
# ─────────────────────────────────────────────

def rate_limit(chat_id: int) -> bool:
    now = time.time()
    window_start = now - RATE_LIMIT_WINDOW
    RATE_LIMIT[chat_id] = [ts for ts in RATE_LIMIT[chat_id] if ts > window_start]
    if len(RATE_LIMIT[chat_id]) >= RATE_LIMIT_MAX:
        return False
    RATE_LIMIT[chat_id].append(now)
    return True


def retry_on_failure(max_retries: int = 3, delay: float = 1.0):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise
                    time.sleep(delay * (2 ** attempt))
        return wrapper
    return decorator


# ─────────────────────────────────────────────
# CACHE
# ─────────────────────────────────────────────

_CACHE: Dict[str, Dict[str, Any]] = {}
_CACHE_LOCK = Lock()
_CACHE_TTL  = 180
_CACHE_MAX  = 100

def _get_cache(key: str) -> Optional[str]:
    with _CACHE_LOCK:
        item = _CACHE.get(key)
        if not item:
            return None
        if time.time() - item["t"] > _CACHE_TTL:
            _CACHE.pop(key, None)
            return None
        return item["v"]

def _set_cache(key: str, value: str):
    with _CACHE_LOCK:
        if len(_CACHE) >= _CACHE_MAX:
            oldest = sorted(_CACHE.items(), key=lambda x: x[1]["t"])[:20]
            for k, _ in oldest:
                _CACHE.pop(k, None)
        _CACHE[key] = {"v": value, "t": time.time()}


# ─────────────────────────────────────────────
# TELEGRAM HELPERS
# ─────────────────────────────────────────────

@retry_on_failure(max_retries=3, delay=1.0)
def tg_send(chat_id: int, text: str, parse_mode: Optional[str] = None,
            reply_to_message_id: Optional[int] = None) -> Optional[int]:
    if not TELEGRAM_ENABLED:
        return None
    try:
        payload: dict = {"chat_id": chat_id, "text": text[:4000]}
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if reply_to_message_id:
            payload["reply_to_message_id"] = reply_to_message_id
        r = requests.post(f"{BASE}/sendMessage", json=payload, timeout=15)
        result = r.json()
        if not result.get("ok"):
            print(f"[TG SEND ERROR] {result.get('description')}")
            return None
        return result.get("result", {}).get("message_id")
    except Exception as e:
        print(f"[TG SEND ERROR] {e}")
        raise


def tg_send_typing(chat_id: int):
    if not TELEGRAM_ENABLED:
        return
    try:
        requests.post(f"{BASE}/sendChatAction",
                      json={"chat_id": chat_id, "action": "typing"}, timeout=5)
    except Exception:
        pass


def tg_get_updates(offset: Optional[int] = None, timeout: int = 25) -> List[Dict]:
    """
    Long-poll for updates. timeout=25s keeps us under Render's 30s request limit.
    Returns [] on any error — never raises, so the loop stays alive.
    """
    if not TELEGRAM_ENABLED:
        return []
    try:
        params: Dict[str, Any] = {"timeout": timeout}
        if offset is not None:
            params["offset"] = offset
        r = requests.get(f"{BASE}/getUpdates", params=params, timeout=timeout + 5)
        data = r.json()
        if not data.get("ok"):
            # Log but don't crash — Conflict errors are handled by the backoff loop
            desc = data.get("description", "")
            if "Conflict" not in desc:
                print(f"[TG POLL ERROR] {desc}")
            return []
        return data.get("result", [])
    except Exception as e:
        print(f"[TG POLL ERROR] {e}")
        return []


def notify(text: str, is_alert: bool = False):
    """
    Public API: used by proactive_engine, notifier, briefing, etc.
    Push a message to the owner's Telegram.
    """
    if not TELEGRAM_ENABLED or not ALLOWED_CHAT_ID:
        return
    prefix   = "🚨 " if is_alert else "📢 "
    max_len  = 4000 - len(prefix) - 5
    if len(text) > max_len:
        for chunk in [text[i:i+max_len] for i in range(0, len(text), max_len)]:
            tg_send(ALLOWED_CHAT_ID, f"{prefix}{chunk}")
            time.sleep(0.5)
    else:
        tg_send(ALLOWED_CHAT_ID, f"{prefix}{text}")


# ─────────────────────────────────────────────
# SAFE PARSERS
# ─────────────────────────────────────────────

def extract_chat_id(update: Dict) -> Optional[int]:
    try:
        return update.get("message", {}).get("chat", {}).get("id")
    except Exception:
        return None

def extract_message_text(update: Dict) -> Tuple[Optional[str], Optional[int]]:
    try:
        msg      = update.get("message", {})
        text     = msg.get("text")
        reply_to = msg.get("reply_to_message", {}).get("message_id")
        return text, reply_to
    except Exception:
        return None, None

def safe_str(x) -> str:
    return (x or "").strip()

def safe_int(x) -> Optional[int]:
    try:
        return int(safe_str(x))
    except (ValueError, TypeError):
        return None


# ─────────────────────────────────────────────
# CHAT ENGINE
# ─────────────────────────────────────────────

def _handle_chat(chat_id: int, text: str, reply_to: Optional[int] = None):
    text = safe_str(text)
    if not text or not client:
        tg_send(chat_id, "❌ Missing Groq API key.", reply_to_message_id=reply_to)
        return

    if not rate_limit(chat_id):
        tg_send(chat_id, "⏳ Rate limit — wait a moment.", reply_to_message_id=reply_to)
        return

    cached = _get_cache(text)
    if cached:
        tg_send(chat_id, cached, reply_to_message_id=reply_to)
        return

    tg_send_typing(chat_id)

    try:
        history       = get_conversation_history(limit=10)
        system_prompt = build_system_prompt(query=text)
        messages: list = [{"role": "system", "content": system_prompt}]
        for role, content, _ in history[-10:]:
            if role in ("user", "assistant"):
                messages.append({"role": role, "content": (content or "")[:500]})
        messages.append({"role": "user", "content": text})

        # Note: Groq SDK does not accept timeout= kwarg — use requests timeout via the HTTP layer
        response = client.chat.completions.create(
            model=GROQ_MODEL_PRIMARY or "llama-3.3-70b-versatile",
            messages=messages,  # type: ignore
            max_tokens=500,
            temperature=0.4,
        )
        reply = (response.choices[0].message.content or "").strip() or "No response."

        _set_cache(text, reply)
        save_conversation("user",      text[:500])
        save_conversation("assistant", reply[:500])
        tg_send(chat_id, reply, reply_to_message_id=reply_to)

    except Exception as e:
        tg_send(chat_id, f"❌ ORA error: {str(e)[:100]}", reply_to_message_id=reply_to)
        print(f"[CHAT ERROR]\n{traceback.format_exc()}")


# ─────────────────────────────────────────────
# COMMAND HANDLERS
# ─────────────────────────────────────────────

def _cmd_help(chat_id: int, reply_to=None):
    tg_send(chat_id, (
        "🤖 *ORA Commands*\n\n"
        "*Tasks:*\n"
        "/tasks — pending tasks\n"
        "/done <id> — mark complete\n\n"
        "*Goals & Finance:*\n"
        "/goals — active goals\n"
        "/mpesa — M-Pesa summary\n"
        "/brief — full status brief\n\n"
        "*Phase 2:*\n"
        "/inbox — unread Gmail count\n"
        "/replies — pending smart replies\n"
        "/proactive — active signals\n\n"
        "*Utility:*\n"
        "/ping — health check\n"
        "/stats — bot stats\n"
        "/help — this menu\n\n"
        "Or just *type anything* to chat with ORA."
    ), parse_mode="Markdown", reply_to_message_id=reply_to)


def _cmd_tasks(chat_id: int, reply_to=None):
    try:
        from database import get_tasks
        tasks = get_tasks("pending")
        if not tasks:
            tg_send(chat_id, "📋 No pending tasks. 🎉", reply_to_message_id=reply_to)
            return
        lines = [f"📋 *Pending Tasks* ({len(tasks)})"]
        for t in tasks[:10]:
            tid, title, priority, _, due = t[:5]
            emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(priority, "⚪")
            due_s = f" _(due {due[:10]})_" if due else ""
            lines.append(f"{emoji} *{title[:55]}* — #{tid}{due_s}")
        if len(tasks) > 10:
            lines.append(f"_...and {len(tasks)-10} more_")
        tg_send(chat_id, "\n".join(lines), parse_mode="Markdown", reply_to_message_id=reply_to)
    except Exception as e:
        tg_send(chat_id, f"❌ {e}", reply_to_message_id=reply_to)


def _cmd_done(chat_id: int, arg: str, reply_to=None):
    task_id = safe_int(arg)
    if task_id is None:
        tg_send(chat_id, "Usage: `/done <id>`\nGet IDs with /tasks",
                parse_mode="Markdown", reply_to_message_id=reply_to)
        return
    try:
        from database import complete_task, get_tasks
        # get_tasks("all") now works after the database.py fix
        all_tasks = get_tasks("all")
        if not any(t[0] == task_id for t in all_tasks):
            tg_send(chat_id, f"❌ Task #{task_id} not found.", reply_to_message_id=reply_to)
            return
        complete_task(task_id)
        tg_send(chat_id, f"✅ Task #{task_id} done! 🎉", reply_to_message_id=reply_to)
        pending = get_tasks("pending")
        if pending:
            tg_send(chat_id, f"💡 Next: #{pending[0][0]} — {pending[0][1][:50]}",
                    reply_to_message_id=reply_to)
    except Exception as e:
        tg_send(chat_id, f"❌ {e}", reply_to_message_id=reply_to)


def _cmd_goals(chat_id: int, reply_to=None):
    try:
        from intelligence.goals_engine import get_goals
        goals = get_goals("active")
        if not goals:
            tg_send(chat_id, "🎯 No active goals.", reply_to_message_id=reply_to)
            return
        lines = [f"🎯 *Active Goals* ({len(goals)})"]
        for g in goals[:7]:
            name     = g.get("goal", "Untitled")[:55]
            progress = g.get("progress", 0)
            filled   = int(10 * progress / 100)
            bar      = "█" * filled + "░" * (10 - filled)
            due      = g.get("due_at", "")
            due_s    = f" _due {due[:10]}_" if due else ""
            lines.append(f"• {name}\n  `{bar}` {progress}%{due_s}")
        tg_send(chat_id, "\n\n".join(lines), parse_mode="Markdown", reply_to_message_id=reply_to)
    except Exception as e:
        tg_send(chat_id, f"❌ {e}", reply_to_message_id=reply_to)


def _cmd_mpesa(chat_id: int, reply_to=None):
    try:
        from mpesa_engine import get_today_spend, get_average_daily_spend
        today = get_today_spend()
        avg   = get_average_daily_spend()
        total = today.get("total", 0) if isinstance(today, dict) else 0
        txns  = today.get("transactions", 0) if isinstance(today, dict) else 0
        trend = "📈 above avg" if total > avg * 1.3 else ("📉 below avg" if total < avg * 0.7 else "📊 normal")
        tg_send(chat_id, (
            f"💳 *M-Pesa Summary*\n\n"
            f"Today: KES {total:,.0f} ({txns} txns)\n"
            f"Daily avg: KES {avg:,.0f} — {trend}"
        ), parse_mode="Markdown", reply_to_message_id=reply_to)
    except Exception as e:
        tg_send(chat_id, f"❌ {e}", reply_to_message_id=reply_to)


def _cmd_brief(chat_id: int, reply_to=None):
    tg_send_typing(chat_id)
    try:
        from briefing import generate_briefing
        briefing = generate_briefing()
        if len(briefing) > 4000:
            for i, chunk in enumerate([briefing[j:j+4000] for j in range(0, len(briefing), 4000)]):
                tg_send(chat_id, chunk, parse_mode="Markdown",
                        reply_to_message_id=reply_to if i == 0 else None)
                time.sleep(0.5)
        else:
            tg_send(chat_id, briefing, parse_mode="Markdown", reply_to_message_id=reply_to)
    except Exception as e:
        tg_send(chat_id, f"❌ {e}", reply_to_message_id=reply_to)


# ── Phase 2 commands ──────────────────────────────────────────

def _cmd_inbox(chat_id: int, reply_to=None):
    """Show unread Gmail count + pending reply count."""
    try:
        from connectors.gmail import get_gmail_summary, get_reply_stats
        summary = get_gmail_summary()
        stats   = get_reply_stats()
        if not summary.get("authorized"):
            tg_send(chat_id,
                    "📭 Gmail not connected.\nVisit ORA → Settings → Connect Google.",
                    reply_to_message_id=reply_to)
            return
        unread  = summary.get("unread_count", 0)
        pending = stats.get("pending", 0)
        tg_send(chat_id, (
            f"📬 *Gmail Status*\n\n"
            f"Unread: {unread}\n"
            f"Smart replies pending: {pending}\n\n"
            f"Use /replies to review them."
        ), parse_mode="Markdown", reply_to_message_id=reply_to)
    except Exception as e:
        tg_send(chat_id, f"❌ {e}", reply_to_message_id=reply_to)


def _cmd_replies(chat_id: int, reply_to=None):
    """List pending smart replies with approve/reject hint."""
    try:
        from connectors.gmail import get_pending_replies
        pending = get_pending_replies(limit=5)
        if not pending:
            tg_send(chat_id, "✅ No pending reply suggestions.", reply_to_message_id=reply_to)
            return
        lines = [f"📧 *{len(pending)} pending reply suggestion(s):*\n"]
        for r in pending:
            subj = (r.get("subject") or "(no subject)")[:45]
            sndr = (r.get("sender") or "")[:35]
            rid  = r.get("id")
            preview = (r.get("suggested_text") or "")[:80]
            lines.append(
                f"*#{rid}* — {subj}\n"
                f"From: _{sndr}_\n"
                f"Draft: _{preview}_...\n"
            )
        lines.append("Open ORA → Inbox → Smart Replies to approve/edit.")
        tg_send(chat_id, "\n".join(lines), parse_mode="Markdown", reply_to_message_id=reply_to)
    except Exception as e:
        tg_send(chat_id, f"❌ {e}", reply_to_message_id=reply_to)


def _cmd_proactive(chat_id: int, reply_to=None):
    """Show what proactive signals are active right now."""
    try:
        from database import get_tasks, get_conn, close_conn
        now     = datetime.now()
        pending = get_tasks("pending")
        overdue = [t for t in pending if t[4] and datetime.fromisoformat(t[4]) < now]
        high    = [t for t in pending if t[2] == "high"]

        conn       = get_conn()
        old_r      = conn.execute(
            "SELECT COUNT(*) FROM suggested_replies WHERE status='pending' AND created_at < datetime('now','-24 hours')"
        ).fetchone()[0]
        close_conn()

        lines = ["🔔 *Proactive Signal Status*\n"]
        lines.append(f"{'🔴' if overdue else '✅'} Overdue tasks: {len(overdue)}")
        lines.append(f"{'🟡' if len(high) >= 2 else '✅'} High-priority open: {len(high)}")
        lines.append(f"{'🟡' if old_r else '✅'} Unanswered emails (>24h): {old_r}")
        lines.append(f"\n_Next proactive check runs in background._")
        tg_send(chat_id, "\n".join(lines), parse_mode="Markdown", reply_to_message_id=reply_to)
    except Exception as e:
        tg_send(chat_id, f"❌ {e}", reply_to_message_id=reply_to)


def _cmd_stats(chat_id: int, reply_to=None):
    try:
        from database import get_conversation_history, get_tasks
        conv_count  = len(get_conversation_history(limit=10000)) // 2
        task_count  = len(get_tasks("all"))
        cache_size  = len(_CACHE)
        uptime_s    = int(time.time() - _start_time)
        h, m        = divmod(uptime_s // 60, 60)
        uptime_str  = f"{h}h {m}m" if h else f"{m}m"
        tg_send(chat_id, (
            f"📊 *ORA Stats*\n\n"
            f"Conversations: {conv_count}\n"
            f"Tasks: {task_count}\n"
            f"Cache entries: {cache_size}\n"
            f"Uptime: {uptime_str}"
        ), parse_mode="Markdown", reply_to_message_id=reply_to)
    except Exception as e:
        tg_send(chat_id, f"❌ {e}", reply_to_message_id=reply_to)


# ─────────────────────────────────────────────
# MESSAGE ROUTER
# ─────────────────────────────────────────────

_start_time = time.time()


def handle_message(chat_id: int, text: str = "", reply_to: Optional[int] = None, voice=None):
    if ALLOWED_CHAT_ID and chat_id != ALLOWED_CHAT_ID:
        print(f"[TELEGRAM] Rejected chat_id={chat_id}")
        return

    text  = safe_str(text)
    lower = text.lower()

    if voice:
        tg_send(chat_id, "🎤 Voice not supported in Telegram — use the ORA web app for voice input.",
                reply_to_message_id=reply_to)
        return

    if lower.startswith("/start"):
        tg_send(chat_id, "🤖 ORA online. /help for commands.", reply_to_message_id=reply_to)
    elif lower.startswith("/ping"):
        tg_send(chat_id, "🏓 pong!", reply_to_message_id=reply_to)
    elif lower.startswith("/help"):
        _cmd_help(chat_id, reply_to)
    elif lower.startswith("/tasks"):
        _cmd_tasks(chat_id, reply_to)
    elif lower.startswith("/done"):
        _cmd_done(chat_id, text[5:], reply_to)
    elif lower.startswith("/goals"):
        _cmd_goals(chat_id, reply_to)
    elif lower.startswith("/mpesa"):
        _cmd_mpesa(chat_id, reply_to)
    elif lower.startswith("/brief"):
        _cmd_brief(chat_id, reply_to)
    elif lower.startswith("/inbox"):
        _cmd_inbox(chat_id, reply_to)
    elif lower.startswith("/replies"):
        _cmd_replies(chat_id, reply_to)
    elif lower.startswith("/proactive"):
        _cmd_proactive(chat_id, reply_to)
    elif lower.startswith("/stats"):
        _cmd_stats(chat_id, reply_to)
    else:
        _handle_chat(chat_id, text, reply_to)


# ─────────────────────────────────────────────
# MAIN POLLING LOOP
# ─────────────────────────────────────────────

def run_telegram_bot():
    """
    Long-poll loop. Runs in a daemon thread started by api.py lifespan.
    The lifespan wrapper already handles restarting on crash with backoff,
    so this function exits cleanly on error rather than looping internally —
    that prevents the "Conflict: terminated by other getUpdates" log spam.
    """
    print("[TELEGRAM] Starting long-poll loop")
    offset: Optional[int] = None

    while True:
        try:
            updates = tg_get_updates(offset, timeout=25)

            for update in updates:
                offset = update.get("update_id", 0) + 1
                chat_id = extract_chat_id(update)
                if not chat_id:
                    continue
                text, reply_to = extract_message_text(update)
                msg   = update.get("message", {})
                handle_message(
                    chat_id,
                    text=text or "",
                    reply_to=reply_to,
                    voice=msg.get("voice"),
                )
                time.sleep(0.05)

            if not updates:
                time.sleep(1)

        except KeyboardInterrupt:
            print("[TELEGRAM] Shutting down")
            break
        except Exception as e:
            print(f"[TELEGRAM LOOP ERROR] {e}")
            # Re-raise so the lifespan thread restarts us with backoff
            raise


if __name__ == "__main__":
    run_telegram_bot()
