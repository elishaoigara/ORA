"""
ORA Telegram Bot — optimized for Render free tier + Groq cost control (STABLE)
"""

print("[TELEGRAM] Loading bot v3 (stable)...")

import time
import requests
import traceback
from datetime import datetime

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, GROQ_API_KEY

from database import (
    save_conversation,
    get_conversation_history,
    get_tasks,
)

from memory.events import log_memory_event
from context import build_system_prompt
from groq import Groq


# ========================
# CONFIG SAFETY
# ========================
TELEGRAM_ENABLED = bool(TELEGRAM_BOT_TOKEN)

BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}" if TELEGRAM_ENABLED else None

client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

ALLOWED_CHAT_ID = int(TELEGRAM_CHAT_ID) if TELEGRAM_CHAT_ID else None

print(f"[TELEGRAM] Enabled: {TELEGRAM_ENABLED}")
print(f"[TELEGRAM] Allowed Chat ID: {ALLOWED_CHAT_ID}")


# ========================
# COST CACHE (SAFE LIMIT)
# ========================
RESPONSE_CACHE = {}
CACHE_TTL = 300
MAX_CACHE_SIZE = 100


def get_cache(text):
    item = RESPONSE_CACHE.get(text)
    if not item:
        return None

    if time.time() - item["time"] > CACHE_TTL:
        del RESPONSE_CACHE[text]
        return None

    return item["response"]


def set_cache(text, response):
    if len(RESPONSE_CACHE) > MAX_CACHE_SIZE:
        RESPONSE_CACHE.clear()  # prevent memory leak

    RESPONSE_CACHE[text] = {
        "response": response,
        "time": time.time()
    }


# ========================
# INTENT ROUTER
# ========================
def route_intent(text: str):
    text = text.lower()

    if text.startswith("/status"):
        return "status"
    if text.startswith("/task"):
        return "task"
    if text.startswith("/start"):
        return "start"

    return "chat"


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
                "text": text
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

        r = requests.get(
            f"{BASE}/getUpdates",
            params=params,
            timeout=20
        )

        return r.json().get("result", [])

    except Exception as e:
        print("[TG POLL ERROR]", e)
        return []


# ========================
# AI RESPONSE (OPTIMIZED)
# ========================
def ai_respond(text):
    if not client:
        return "Groq not configured."

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

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            max_tokens=300,   # cheaper
            temperature=0.6,
        )

        reply = response.choices[0].message.content.strip()

        set_cache(text, reply)

        return reply

    except Exception as e:
        print("[GROQ ERROR]", e)
        return "ORA is temporarily unavailable."


# ========================
# HANDLERS
# ========================
def handle_status(chat_id):
    try:
        import psutil
        cpu = psutil.cpu_percent()
        ram = psutil.virtual_memory().percent

        tg_send(chat_id, f"CPU: {cpu}%\nRAM: {ram}%")

    except Exception:
        tg_send(chat_id, "Status error")


def handle_chat(chat_id, text):
    msg_id = tg_send(chat_id, "thinking...")

    try:
        save_conversation("user", text)
        log_memory_event("conversation", text[:80], importance=4)

        reply = ai_respond(text)

        save_conversation("assistant", reply)

        if msg_id:
            tg_edit(chat_id, msg_id, reply)
        else:
            tg_send(chat_id, reply)

    except Exception:
        print(traceback.format_exc())
        tg_send(chat_id, "Error processing request")


# ========================
# MAIN LOOP (RENDER SAFE)
# ========================
def run_telegram_bot():
    if not TELEGRAM_ENABLED:
        print("[TELEGRAM] Disabled - no token")
        return

    print("[TELEGRAM] Bot running (stable mode)")

    offset = None
    idle_sleep = 1

    while True:
        try:
            updates = tg_get_updates(offset)

            if not updates:
                time.sleep(idle_sleep)
                idle_sleep = min(idle_sleep + 1, 5)
                continue

            idle_sleep = 1

            for update in updates:
                offset = update.get("update_id", 0) + 1

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
            print("[BOT LOOP ERROR]", e)
            print(traceback.format_exc())
            time.sleep(3)