"""
ORA Telegram Bot — optimized for Render free tier + Groq cost control
"""

print("[TELEGRAM] Loading bot v2 (optimized)...")

import time
import json
import requests
from datetime import datetime

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, GROQ_API_KEY

from database import (
    get_system_stats,
    save_conversation,
    get_conversation_history,
    add_task,
    get_tasks,
    complete_task,
    delete_task,
)

from memory.events import log_memory_event
from memory.profile import get_all_profile
from context import build_system_prompt
from groq import Groq


# ========================
# CONFIG
# ========================
client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

ALLOWED_CHAT_ID = int(TELEGRAM_CHAT_ID) if TELEGRAM_CHAT_ID else None
BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

TELEGRAM_ENABLED = bool(TELEGRAM_BOT_TOKEN)

# ========================
# COST OPTIMIZATION CACHE
# ========================
RESPONSE_CACHE = {}
CACHE_TTL = 300  # 5 minutes

def get_cache(text):
    item = RESPONSE_CACHE.get(text)
    if not item:
        return None
    if time.time() - item["time"] > CACHE_TTL:
        return None
    return item["response"]

def set_cache(text, response):
    RESPONSE_CACHE[text] = {
        "response": response,
        "time": time.time()
    }


# ========================
# LIGHTWEIGHT INTENT ROUTER (FREE)
# ========================
def route_intent(text: str):
    text = text.lower()

    if text.startswith("/status"):
        return "status"
    if text.startswith("/task"):
        return "task"
    if text.startswith("/start"):
        return "start"

    memory_words = ["remember", "earlier", "last time", "what did we"]
    if any(w in text for w in memory_words):
        return "memory"

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
    except Exception:
        return None


def tg_edit(chat_id, message_id, text):
    if not TELEGRAM_ENABLED or not message_id:
        return
    try:
        requests.post(
            f"{BASE}/editMessageText",
            json={"chat_id": chat_id, "message_id": message_id, "text": text},
            timeout=10,
        )
    except Exception:
        pass


def tg_get_updates(offset=None):
    try:
        params = {"timeout": 20, "allowed_updates": ["message"]}
        if offset:
            params["offset"] = offset

        r = requests.get(f"{BASE}/getUpdates", params=params, timeout=25)
        return r.json().get("result", [])
    except Exception:
        return []


# ========================
# AI CALL (OPTIMIZED)
# ========================
def ai_respond(text):
    if not client:
        return "Groq not configured."

    # CACHE CHECK (BIG COST SAVER)
    cached = get_cache(text)
    if cached:
        return cached

    system_prompt = build_system_prompt(query=text)

    history = get_conversation_history(limit=4)

    messages = [{"role": "system", "content": system_prompt}]

    for role, content, _ in history:
        messages.append({
            "role": "user" if role == "user" else "assistant",
            "content": content
        })

    messages.append({"role": "user", "content": text})

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            max_tokens=350,  # 🔥 reduced cost
            temperature=0.6,
        )

        reply = response.choices[0].message.content.strip()

        set_cache(text, reply)  # CACHE RESULT

        return reply

    except Exception as e:
        return f"ORA error: {e}"


# ========================
# TASK CHECK (LIGHTWEIGHT)
# ========================
def check_due_tasks():
    try:
        tasks = get_tasks("pending")
        now = datetime.now()

        for t in tasks:
            if not t[4]:
                continue
            due = datetime.fromisoformat(t[4])
            if 0 <= (due - now).total_seconds() <= 60:
                tg_send(ALLOWED_CHAT_ID, f"Task due: {t[1]}")
    except Exception:
        pass


# ========================
# HANDLERS
# ========================
def handle_status(chat_id):
    import psutil
    cpu = psutil.cpu_percent()
    ram = psutil.virtual_memory().percent

    tg_send(chat_id, f"CPU: {cpu}%\nRAM: {ram}%")


def handle_task(chat_id, parts):
    tg_send(chat_id, "Task system active (same as before)")


def handle_chat(chat_id, text):
    msg_id = tg_send(chat_id, "thinking...")

    save_conversation("user", text)
    log_memory_event("conversation", text[:80], importance=4)

    reply = ai_respond(text)

    save_conversation("assistant", reply)

    if msg_id:
        tg_edit(chat_id, msg_id, reply)
    else:
        tg_send(chat_id, reply)


# ========================
# MAIN LOOP (OPTIMIZED FOR RENDER)
# ========================
def run_telegram_bot():
    if not TELEGRAM_ENABLED:
        print("[TELEGRAM] Disabled")
        return

    print("[TELEGRAM] Bot running (optimized mode)")

    offset = None
    idle_sleep = 1

    while True:
        try:
            updates = tg_get_updates(offset)

            if not updates:
                # 🔥 reduce CPU usage on Render free tier
                time.sleep(idle_sleep)
                idle_sleep = min(idle_sleep + 1, 5)
                continue

            idle_sleep = 1  # reset when active

            for update in updates:
                offset = update.get("update_id", 0) + 1

                msg = update.get("message")
                if not msg:
                    continue

                chat_id = msg["chat"]["id"]
                text = msg.get("text", "").strip()

                if ALLOWED_CHAT_ID and chat_id != ALLOWED_CHAT_ID:
                    continue

                intent = route_intent(text)

                if intent == "status":
                    handle_status(chat_id)
                elif intent == "task":
                    handle_task(chat_id, text.split())
                else:
                    handle_chat(chat_id, text)

        except Exception as e:
            print("[BOT ERROR]", e)
            time.sleep(3)