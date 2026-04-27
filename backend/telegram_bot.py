"""
ORA Telegram Bot — Hardened + Full Commands
Fixes:
- /done now calls database.complete_task()
- Added /tasks, /goals, /mpesa, /brief commands
- notify() function added for briefing.py integration
- Model pulled from config (matches web chat quality)
- Safe polling loop with exponential back-off
"""

import time
import traceback
import requests
from datetime import datetime
from threading import Lock
from typing import Optional, TypedDict, Literal, cast

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, GROQ_API_KEY, GROQ_MODEL_PRIMARY
from database import save_conversation, get_conversation_history
from context import build_system_prompt
from groq import Groq
from groq.types.chat import ChatCompletionMessageParam


# ─────────────────────────────────────────────
# INIT
# ─────────────────────────────────────────────

TELEGRAM_ENABLED = bool(TELEGRAM_BOT_TOKEN)
BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}" if TELEGRAM_ENABLED else None

client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
ALLOWED_CHAT_ID = int(TELEGRAM_CHAT_ID) if TELEGRAM_CHAT_ID else None

print("[TELEGRAM] Enabled:", TELEGRAM_ENABLED)


# ─────────────────────────────────────────────
# CACHE (SAFE)
# ─────────────────────────────────────────────

_CACHE: dict = {}
_CACHE_LOCK = Lock()
_CACHE_TTL = 180


def _get_cache(key: str):
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
        if len(_CACHE) > 100:
            oldest = sorted(_CACHE.items(), key=lambda x: x[1]["t"])[:20]
            for k, _ in oldest:
                _CACHE.pop(k, None)
        _CACHE[key] = {"v": value, "t": time.time()}


# ─────────────────────────────────────────────
# TELEGRAM HELPERS
# ─────────────────────────────────────────────

def tg_send(chat_id, text: str):
    if not TELEGRAM_ENABLED:
        return None
    try:
        r = requests.post(
            f"{BASE}/sendMessage",
            json={"chat_id": chat_id, "text": text[:4000]},
            timeout=10,
        )
        return r.json().get("result", {}).get("message_id")
    except Exception as e:
        print("[TG SEND ERROR]", e)
        return None


def tg_get_updates(offset=None):
    try:
        params: dict = {"timeout": 10}
        if offset:
            params["offset"] = offset
        r = requests.get(f"{BASE}/getUpdates", params=params, timeout=15)
        return r.json().get("result", [])
    except Exception as e:
        print("[TG POLL ERROR]", e)
        return []


def notify(text: str, is_alert: bool = False):
    """
    Public helper used by briefing.py and intelligence/notifier.py
    to push messages to the owner's Telegram chat.
    """
    if not TELEGRAM_ENABLED or not ALLOWED_CHAT_ID:
        print("[TELEGRAM] notify() called but bot is not configured.")
        return
    prefix = "🚨 " if is_alert else ""
    tg_send(ALLOWED_CHAT_ID, f"{prefix}{text}")


# ─────────────────────────────────────────────
# SAFE UPDATE PARSER
# ─────────────────────────────────────────────

def extract_chat_id(update: dict) -> Optional[int]:
    if not isinstance(update, dict):
        return None
    msg = update.get("message")
    if not isinstance(msg, dict):
        return None
    chat = msg.get("chat")
    if not isinstance(chat, dict):
        return None
    return chat.get("id")


# ─────────────────────────────────────────────
# SAFE STRING HELPERS
# ─────────────────────────────────────────────

def safe_str(x: Optional[str]) -> str:
    return (x or "").strip()


def safe_int(x: Optional[str]):
    try:
        return int(safe_str(x))
    except Exception:
        return None


# ─────────────────────────────────────────────
# MESSAGE BUILDER
# ─────────────────────────────────────────────

Role = Literal["system", "user", "assistant"]

class ChatMsg(TypedDict):
    role: Role
    content: str


def build_messages(system_prompt: str, history, user_text: str):
    messages: list[ChatMsg] = [
        {"role": "system", "content": system_prompt}
    ]
    for role, content, _ in history:
        messages.append({
            "role": "user" if role == "user" else "assistant",
            "content": (content or "")[:500]
        })
    messages.append({"role": "user", "content": user_text})
    return messages


# ─────────────────────────────────────────────
# CHAT ENGINE
# ─────────────────────────────────────────────

def _handle_chat(chat_id: int, text: str):
    text = safe_str(text)
    if not text:
        return

    if not client:
        tg_send(chat_id, "Missing Groq API key.")
        return

    cached = _get_cache(text)
    if cached:
        tg_send(chat_id, cached)
        return

    tg_send(chat_id, "⋯")

    try:
        history = get_conversation_history(limit=3)
        system_prompt = build_system_prompt(query=text)
        messages = build_messages(system_prompt, history, text)

        # Use the primary model (same quality as web chat)
        model = GROQ_MODEL_PRIMARY or "llama-3.3-70b-versatile"

        response = client.chat.completions.create(
            model=model,
            messages=cast(list[ChatCompletionMessageParam], messages),
            max_tokens=400,
            temperature=0.4,
        )

        reply = (response.choices[0].message.content or "").strip()

        _set_cache(text, reply)
        save_conversation("user", text)
        save_conversation("assistant", reply)
        tg_send(chat_id, reply)

    except Exception as e:
        err = f"ORA error: {str(e)[:120]}"
        tg_send(chat_id, err)
        print("[CHAT ERROR]", traceback.format_exc())


# ─────────────────────────────────────────────
# COMMAND HANDLERS
# ─────────────────────────────────────────────

def _cmd_tasks(chat_id: int):
    try:
        from database import get_tasks
        tasks = get_tasks("pending")
        if not tasks:
            tg_send(chat_id, "📋 No pending tasks.")
            return
        lines = [f"📋 Tasks ({len(tasks)} pending):"]
        for t in tasks[:8]:
            due = f" — due {t[4][:10]}" if t[4] else ""
            pri = f"[{t[2]}]"
            lines.append(f"#{t[0]} {pri} {t[1]}{due}")
        tg_send(chat_id, "\n".join(lines))
    except Exception as e:
        tg_send(chat_id, f"Error fetching tasks: {e}")


def _cmd_goals(chat_id: int):
    try:
        from intelligence.goals_engine import get_goals
        goals = get_goals("active")
        if not goals:
            tg_send(chat_id, "🎯 No active goals.")
            return
        lines = [f"🎯 Goals ({len(goals)} active):"]
        for g in goals[:6]:
            due = f" — due {g['due_at'][:10]}" if g.get("due_at") else ""
            lines.append(f"• {g['goal'][:70]} ({g['progress']}%){due}")
        tg_send(chat_id, "\n".join(lines))
    except Exception as e:
        tg_send(chat_id, f"Error fetching goals: {e}")


def _cmd_mpesa(chat_id: int):
    try:
        from mpesa_engine import get_today_spend, get_average_daily_spend
        today = get_today_spend()
        avg = get_average_daily_spend()
        total = today.get("total", 0)
        txns = today.get("transactions", 0)
        msg = (
            f"💳 M-Pesa Today\n"
            f"Spent: Ksh {total:,.0f} ({txns} transactions)\n"
            f"Daily avg: Ksh {avg:,.0f}"
        )
        tg_send(chat_id, msg)
    except Exception as e:
        tg_send(chat_id, f"Error fetching M-Pesa data: {e}")


def _cmd_brief(chat_id: int):
    try:
        from briefing import generate_briefing
        briefing = generate_briefing()
        tg_send(chat_id, briefing)
    except Exception as e:
        tg_send(chat_id, f"Error generating briefing: {e}")


def _cmd_done(chat_id: int, task_id_str: str):
    task_id = safe_int(task_id_str.strip())
    if task_id is None:
        tg_send(chat_id, "Usage: /done <task_id>\nExample: /done 3")
        return
    try:
        from database import complete_task
        complete_task(task_id)
        tg_send(chat_id, f"✓ Task #{task_id} marked as done.")
    except Exception as e:
        tg_send(chat_id, f"Failed to complete task #{task_id}: {e}")


def _cmd_help(chat_id: int):
    help_text = (
        "ORA Commands:\n\n"
        "/start   — Wake ORA\n"
        "/ping    — Check connection\n"
        "/tasks   — Show pending tasks\n"
        "/goals   — Show active goals\n"
        "/mpesa   — Today's M-Pesa spend\n"
        "/brief   — Morning briefing\n"
        "/done N  — Mark task #N complete\n\n"
        "Or just type anything to chat with ORA."
    )
    tg_send(chat_id, help_text)


# ─────────────────────────────────────────────
# MESSAGE ROUTER
# ─────────────────────────────────────────────

def handle_message(chat_id: int, text: str = "", voice=None):
    if ALLOWED_CHAT_ID and chat_id != ALLOWED_CHAT_ID:
        return

    text = safe_str(text)
    lower = text.lower()

    if voice:
        tg_send(chat_id, "🎤 Voice messages aren't supported yet. Please type your message.")
        return

    if lower.startswith("/start"):
        tg_send(chat_id, "ORA online. Type /help to see available commands.")

    elif lower.startswith("/ping"):
        tg_send(chat_id, "pong")

    elif lower.startswith("/help"):
        _cmd_help(chat_id)

    elif lower.startswith("/tasks"):
        _cmd_tasks(chat_id)

    elif lower.startswith("/goals"):
        _cmd_goals(chat_id)

    elif lower.startswith("/mpesa"):
        _cmd_mpesa(chat_id)

    elif lower.startswith("/brief"):
        _cmd_brief(chat_id)

    elif lower.startswith("/done"):
        _cmd_done(chat_id, text[5:])

    else:
        if client:
            _handle_chat(chat_id, text)
        else:
            tg_send(chat_id, "Missing Groq API key.")


# ─────────────────────────────────────────────
# MAIN LOOP
# ─────────────────────────────────────────────

def run_telegram_bot():
    print("[TELEGRAM] Running safe loop")

    offset = None
    empty_cycles = 0

    while True:
        try:
            updates = tg_get_updates(offset)

            if not updates:
                empty_cycles += 1
                time.sleep(min(1 + empty_cycles * 0.2, 5))
                continue

            empty_cycles = 0

            for update in updates:
                offset = update.get("update_id", 0) + 1

                chat_id = extract_chat_id(update)

                if not chat_id:
                    continue

                msg = update.get("message") or {}

                handle_message(
                    chat_id,
                    text=msg.get("text") or "",
                    voice=msg.get("voice"),
                )

        except Exception as e:
            print("[LOOP ERROR]", e)
            traceback.print_exc()
            time.sleep(3)