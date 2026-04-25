"""
ORA Telegram Bot — Stable Production Version
Fixes:
- No threading (prevents race + timeout bugs)
- Safe Groq calls
- Proper error visibility
- Reliable response handling
"""

print("[TELEGRAM] Loading bot v4 (stable fixed)...")

import time
import requests
import traceback

from datetime import datetime

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, GROQ_API_KEY

from database import (
    save_conversation,
    get_conversation_history,
)

from memory.events import log_memory_event
from context import build_system_prompt
from groq import Groq


# ========================
# CONFIG
# ========================
TELEGRAM_ENABLED = bool(TELEGRAM_BOT_TOKEN)
BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}" if TELEGRAM_ENABLED else None

client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
ALLOWED_CHAT_ID = int(TELEGRAM_CHAT_ID) if TELEGRAM_CHAT_ID else None

print(f"[TELEGRAM] Enabled: {TELEGRAM_ENABLED}")
print(f"[TELEGRAM] Allowed Chat ID: {ALLOWED_CHAT_ID}")


# ========================
# CACHE (safe)
# ========================
CACHE = {}
CACHE_TTL = 300


def get_cache(key):
    item = CACHE.get(key)
    if not item:
        return None
    if time.time() - item["time"] > CACHE_TTL:
        del CACHE[key]
        return None
    return item["value"]


def set_cache(key, value):
    CACHE[key] = {"value": value, "time": time.time()}


# ========================
# TELEGRAM HELPERS
# ========================
def tg_send(chat_id, text):
    if not TELEGRAM_ENABLED:
        return None
    try:
        r = requests.post(
            f"{BASE}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=10,
        )
        return r.json().get("result", {}).get("message_id")
    except Exception as e:
        print("[TG SEND ERROR]", e)
        return None


def tg_edit(chat_id, message_id, text):
    if not TELEGRAM_ENABLED or not message_id:
        return
    try:
        requests.post(
            f"{BASE}/editMessageText",
            json={
                "chat_id": chat_id,
                "message_id": message_id,
                "text": text,
            },
            timeout=10,
        )
    except Exception as e:
        print("[TG EDIT ERROR]", e)


def tg_get_updates(offset=None):
    if not TELEGRAM_ENABLED:
        return []
    try:
        params = {"timeout": 15}
        if offset:
            params["offset"] = offset

        r = requests.get(f"{BASE}/getUpdates", params=params, timeout=20)
        return r.json().get("result", [])
    except Exception as e:
        print("[TG POLL ERROR]", e)
        return []


# ========================
# INTENT ROUTER
# ========================
def route_intent(text: str):
    t = text.lower()
    if t.startswith("/start"):
        return "start"
    if t.startswith("/status"):
        return "status"
    return "chat"


# ========================
# AI CORE (FIXED)
# ========================
def ai_respond(text: str):
    if not client:
        return "Groq is not configured."

    cached = get_cache(text)
    if cached:
        return cached

    try:
        system_prompt = build_system_prompt(query=text)

        history = get_conversation_history(limit=4)

        messages = [{"role": "system", "content": system_prompt}]

        for role, content, _ in history:
            messages.append({
                "role": "user" if role == "user" else "assistant",
                "content": content
            })

        messages.append({"role": "user", "content": text})

        # IMPORTANT: no timeout param (Groq SDK issue source)
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            max_tokens=300,
            temperature=0.6,
        )

        reply = response.choices[0].message.content.strip()

        set_cache(text, reply)

        return reply

    except Exception as e:
        print("[GROQ ERROR]", str(e))
        traceback.print_exc()
        return f"ORA AI error: {str(e)}"


# ========================
# CHAT HANDLER (FIXED)
# ========================
def handle_chat(chat_id, text):
    msg_id = tg_send(chat_id, "thinking...")

    try:
        save_conversation("user", text)
        log_memory_event("conversation", text[:80], importance=4)

        reply = ai_respond(text)

        save_conversation("assistant", reply)

    except Exception as e:
        print("[HANDLE CHAT ERROR]", str(e))
        traceback.print_exc()
        reply = "Error processing request."

    if msg_id:
        tg_edit(chat_id, msg_id, reply)
    else:
        tg_send(chat_id, reply)


# ========================
# STATUS
# ========================
def handle_status(chat_id):
    try:
        import psutil
        cpu = psutil.cpu_percent()
        ram = psutil.virtual_memory().percent
        tg_send(chat_id, f"CPU: {cpu}%\nRAM: {ram}%")
    except Exception as e:
        tg_send(chat_id, f"Status error: {e}")


# ========================
# MAIN LOOP
# ========================
def run_telegram_bot():
    if not TELEGRAM_ENABLED:
        print("[TELEGRAM] Disabled")
        return

    print("[TELEGRAM] Bot running (stable fixed mode)")

    offset = None
    sleep_time = 1

    while True:
        try:
            updates = tg_get_updates(offset)

            if not updates:
                time.sleep(sleep_time)
                sleep_time = min(sleep_time + 1, 5)
                continue

            sleep_time = 1

            for update in updates:
                offset = update["update_id"] + 1

                msg = update.get("message")
                if not msg:
                    continue

                chat_id = msg["chat"]["id"]
                text = msg.get("text", "").strip()

                if not text:
                    continue

                if ALLOWED_CHAT_ID and chat_id != ALLOWED_CHAT_ID:
                    continue

                intent = route_intent(text)

                if intent == "status":
                    handle_status(chat_id)
                else:
                    handle_chat(chat_id, text)

        except Exception as e:
            print("[BOT LOOP ERROR]", str(e))
            traceback.print_exc()
            time.sleep(3)