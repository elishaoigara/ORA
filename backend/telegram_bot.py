"""
ORA Telegram Bot — pure HTTP implementation
Fixed for Render stability + safe startup + API resilience
"""

print("[TELEGRAM] Loading pure HTTP bot v3 (fixed)...")

import time
import threading
import requests
import json
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
# SAFETY CHECK (FIX #1)
# ========================
if not TELEGRAM_BOT_TOKEN:
    print("[TELEGRAM] Missing bot token - bot disabled")
    TELEGRAM_ENABLED = False
else:
    TELEGRAM_ENABLED = True
    BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


# ========================
# GROQ CLIENT (FIX #2)
# ========================
client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None


# ========================
# TELEGRAM API
# ========================
def tg_send(chat_id, text):
    if not TELEGRAM_ENABLED:
        return
    try:
        requests.post(
            f"{BASE}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=10,
        )
    except Exception as e:
        print(f"[TG SEND ERROR] {e}")


def tg_edit(chat_id, message_id, text):
    if not TELEGRAM_ENABLED:
        return
    try:
        requests.post(
            f"{BASE}/editMessageText",
            json={"chat_id": chat_id, "message_id": message_id, "text": text},
            timeout=10,
        )
    except Exception as e:
        print(f"[TG EDIT ERROR] {e}")


def tg_get_updates(offset=None):
    if not TELEGRAM_ENABLED:
        return []

    try:
        params = {"timeout": 20, "allowed_updates": ["message"]}
        if offset:
            params["offset"] = offset

        r = requests.get(
            f"{BASE}/getUpdates",
            params=params,
            timeout=25
        )

        return r.json().get("result", [])

    except Exception as e:
        print(f"[TG POLL ERROR] {e}")
        return []


# ========================
# NOTIFY
# ========================
def notify(message, is_alert=False):
    prefix = "ORA ALERT\n\n" if is_alert else ""
    tg_send(TELEGRAM_CHAT_ID, prefix + message)


# ========================
# TASK CHECKER
# ========================
_notified_tasks = set()


def check_due_tasks():
    tasks = get_tasks("pending")
    now = datetime.now()

    for t in tasks:
        try:
            task_id, title, _, _, due_at = t

            if not due_at:
                continue

            due_time = datetime.fromisoformat(due_at)
            diff = (due_time - now).total_seconds()

            if 0 <= diff <= 60 and task_id not in _notified_tasks:
                _notified_tasks.add(task_id)
                notify(f"Task due now: {title}", is_alert=True)

        except Exception as e:
            print(f"[TASK ERROR] {e}")


# ========================
# AI RESPONSE (FIXED)
# ========================
LAST_REQUEST = 0
COOLDOWN = 10


def ai_respond(user_text):
    global LAST_REQUEST

    if not client:
        return "GROQ API not configured."

    elapsed = time.time() - LAST_REQUEST
    if elapsed < COOLDOWN:
        time.sleep(COOLDOWN - elapsed)

    LAST_REQUEST = time.time()

    knowledge_context = ""

    try:
        from knowledge import search_knowledge
        chunks = search_knowledge(user_text, n_results=4)

        if chunks:
            knowledge_context = "\n\n".join(
                f"[{c.get('filename','file')}]\n{c.get('text','')[:400]}"
                for c in chunks
            )

    except Exception as e:
        print("[KNOWLEDGE ERROR]", e)

    system_prompt = build_system_prompt(query=user_text)

    if knowledge_context:
        system_prompt = knowledge_context + "\n\n" + system_prompt

    history = get_conversation_history(limit=8)

    messages = [{"role": "system", "content": system_prompt}]

    for role, content in history:
        messages.append({
            "role": "user" if role == "user" else "assistant",
            "content": content
        })

    messages.append({"role": "user", "content": user_text})

    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=messages,
                max_tokens=600,
                temperature=0.6,
            )
            return response.choices[0].message.content.strip()

        except Exception as e:
            print("[GROQ ERROR]", e)
            time.sleep(5 * (attempt + 1))

    return "ORA is temporarily unavailable."


# ========================
# COMMANDS
# ========================
def handle_start(chat_id):
    profile = get_all_profile()
    name = profile.get("name", "Elisha")

    tg_send(chat_id,
        f"ORA online, {name}.\n\n"
        "System active."
    )


def handle_status(chat_id):
    try:
        row = get_system_stats()

        if not row:
            tg_send(chat_id, "ORA warming up.")
            return

        try:
            data = json.loads(row[0])
        except:
            import ast
            data = ast.literal_eval(row[0])

        tg_send(chat_id,
            f"CPU: {data.get('cpu_percent', 0)}%\n"
            f"RAM: {data.get('ram_percent', 0)}%\n"
            f"Disk: {data.get('disk_free_gb', 0)}GB"
        )

    except Exception as e:
        tg_send(chat_id, f"Status error: {e}")


def handle_chat(chat_id, text):
    msg_id = None

    try:
        r = requests.post(
            f"{BASE}/sendMessage",
            json={"chat_id": chat_id, "text": "thinking..."},
        )
        msg_id = r.json().get("result", {}).get("message_id")
    except:
        pass

    save_conversation("user", text)
    log_memory_event("conversation", text[:80], importance=4)

    reply = ai_respond(text)

    save_conversation("assistant", reply)
    log_memory_event("conversation", "ORA replied", importance=3)

    if msg_id:
        tg_edit(chat_id, msg_id, reply)
    else:
        tg_send(chat_id, reply)


# ========================
# MAIN LOOP (FIXED SAFETY)
# ========================
def run_telegram_bot():
    print("[TELEGRAM] Bot started...")

    offset = None

    time.sleep(3)  # FIX: allow Render startup

    while True:
        try:
            updates = tg_get_updates(offset)

            for update in updates:
                offset = update.get("update_id", 0) + 1

                msg = update.get("message")
                if not msg:
                    continue

                chat_id = msg["chat"]["id"]
                text = msg.get("text", "")

                if not text:
                    continue

                if text.startswith("/"):
                    cmd = text.split()[0].lower()

                    if cmd == "/start":
                        handle_start(chat_id)
                    elif cmd == "/status":
                        handle_status(chat_id)
                    else:
                        tg_send(chat_id, f"Unknown command: {cmd}")
                else:
                    handle_chat(chat_id, text)

        except Exception as e:
            print("[BOT LOOP ERROR]", e)
            time.sleep(5)