"""
ORA Telegram Bot — Hardened Safe Version
Fixes:
- Pylance OptionalMemberAccess errors
- None-safe Telegram update parsing
- Stable polling loop
- Safe Groq message formatting
"""

import time
import traceback
import requests
from datetime import datetime
from threading import Lock
from typing import Optional, TypedDict, Literal, cast

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, GROQ_API_KEY
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

_CACHE = {}
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
        params = {"timeout": 10}
        if offset:
            params["offset"] = offset

        r = requests.get(f"{BASE}/getUpdates", params=params, timeout=15)
        return r.json().get("result", [])
    except Exception as e:
        print("[TG POLL ERROR]", e)
        return []


# ─────────────────────────────────────────────
# SAFE UPDATE PARSER (FIXES YOUR ERROR)
# ─────────────────────────────────────────────

def extract_chat_id(update: dict) -> Optional[int]:
    """
    Fully safe extraction of chat_id.
    Fixes:
    - None message
    - missing chat
    - Pylance OptionalMemberAccess errors
    """

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
    except:
        return None


# ─────────────────────────────────────────────
# MESSAGE BUILDER (FIXED TYPES)
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

    cached = _get_cache(text)
    if cached:
        tg_send(chat_id, cached)
        return

    mid = tg_send(chat_id, "⋯")

    try:
        history = get_conversation_history(limit=3)
        system_prompt = build_system_prompt(query=text)

        messages = build_messages(system_prompt, history, text)

        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=cast(list[ChatCompletionMessageParam], messages),
            max_tokens=300,
            temperature=0.4,
        )

        reply = (response.choices[0].message.content or "").strip()

        _set_cache(text, reply)
        save_conversation("user", text)
        save_conversation("assistant", reply)

        if mid:
            tg_send(chat_id, reply)

    except Exception as e:
        err = f"ORA error: {str(e)[:120]}"
        tg_send(chat_id, err)
        print("[CHAT ERROR]", traceback.format_exc())


# ─────────────────────────────────────────────
# MESSAGE ROUTER
# ─────────────────────────────────────────────

def handle_message(chat_id: int, text: str = "", voice=None):
    if ALLOWED_CHAT_ID and chat_id != ALLOWED_CHAT_ID:
        return

    text = safe_str(text)
    lower = text.lower()

    if voice:
        tg_send(chat_id, "🎤 Voice received")
        return

    if lower.startswith("/start"):
        tg_send(chat_id, "ORA online.")

    elif lower.startswith("/ping"):
        tg_send(chat_id, "pong")

    elif lower.startswith("/done"):
        task_id = safe_int(text[5:])
        if task_id is None:
            tg_send(chat_id, "Usage: /done <id>")
            return
        tg_send(chat_id, f"Task {task_id} done.")

    else:
        if client:
            _handle_chat(chat_id, text)
        else:
            tg_send(chat_id, "Missing Groq API key.")


# ─────────────────────────────────────────────
# MAIN LOOP (FIXED + SAFE)
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