"""
ORA Telegram Bot — pure HTTP implementation.
No python-telegram-bot library = no set_wakeup_fd restriction.
Runs cleanly in any thread on Render.
"""

print("[TELEGRAM] Loading pure HTTP bot v3...")

import time
import threading
import requests
from datetime import date, datetime

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
# TELEGRAM API
# ========================
BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


def tg_send(chat_id, text):
    try:
        requests.post(
            f"{BASE}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=10,
        )
    except Exception as e:
        print(f"[TG SEND ERROR] {e}")


def tg_edit(chat_id, message_id, text):
    try:
        requests.post(
            f"{BASE}/editMessageText",
            json={"chat_id": chat_id, "message_id": message_id, "text": text},
            timeout=10,
        )
    except Exception as e:
        print(f"[TG EDIT ERROR] {e}")


def tg_get_updates(offset=None):
    try:
        params = {"timeout": 30, "allowed_updates": ["message"]}
        if offset:
            params["offset"] = offset

        r = requests.get(
            f"{BASE}/getUpdates",
            params=params,
            timeout=35
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
# TASK DUE CHECKER
# ========================
_notified_tasks = set()


def check_due_tasks():
    tasks = get_tasks("pending")
    now = datetime.now()

    for t in tasks:
        task_id, title, _, _, due_at = t[0], t[1], t[2], t[3], t[4]

        if not due_at:
            continue

        try:
            due_time = datetime.fromisoformat(due_at)
            diff = (due_time - now).total_seconds()

            if 0 <= diff <= 60 and task_id not in _notified_tasks:
                _notified_tasks.add(task_id)
                notify(f"Task due now: {title}", is_alert=True)

        except Exception as e:
            print(f"[TASK PARSE ERROR] {e}")


# ========================
# GROQ AI
# ========================
client = Groq(api_key=GROQ_API_KEY)
LAST_REQUEST = 0
COOLDOWN = 10


def ai_respond(user_text):
    global LAST_REQUEST

    elapsed = time.time() - LAST_REQUEST
    if elapsed < COOLDOWN:
        time.sleep(COOLDOWN - elapsed)

    LAST_REQUEST = time.time()

    # Knowledge base search
    knowledge_context = ""
    try:
        from knowledge import search_knowledge

        chunks = search_knowledge(user_text, n_results=4)
        if chunks:
            knowledge_context = "\n\n".join([
                f"[From your file: {c['filename']}]\n{c['text'][:400]}"
                for c in chunks
            ])
    except Exception as e:
        print(f"[KNOWLEDGE ERROR] {e}")

    # System prompt
    system_prompt = build_system_prompt(query=user_text)

    if knowledge_context:
        system_prompt = (
            "PRIORITY: Use Elisha's data first.\n\n"
            + knowledge_context
            + "\n\n---\n\n"
            + system_prompt
        )

    history = get_conversation_history(limit=8)

    messages = [{"role": "system", "content": system_prompt}]

    for role, content in history:
        messages.append({
            "role": "user" if role == "user" else "assistant",
            "content": content,
        })

    messages.append({"role": "user", "content": user_text})

    # Groq call with retry
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
            err = str(e)
            if "429" in err or "rate_limit" in err.lower():
                wait = 20 * (attempt + 1)
                print(f"[GROQ] Rate limited, waiting {wait}s")
                time.sleep(wait)
            else:
                print(f"[GROQ ERROR] {e}")
                break

    return "ORA is temporarily rate limited."


# ========================
# COMMANDS
# ========================
def handle_start(chat_id):
    profile = get_all_profile()
    name = profile.get("name", "Elisha")

    tg_send(chat_id,
        f"ORA online, {name}.\n\n"
        "Your personal intelligence system is active.\n"
        "Type /status or just talk."
    )


def handle_status(chat_id):
    import ast

    row = get_system_stats()
    if not row:
        tg_send(chat_id, "ORA warming up.")
        return

    try:
        data = ast.literal_eval(row[0])
        tg_send(chat_id,
            f"CPU: {data.get('cpu_percent')}%\n"
            f"RAM: {data.get('ram_percent')}%\n"
            f"Disk: {data.get('disk_free_gb')}GB"
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
        msg_id = r.json()["result"]["message_id"]
    except:
        pass

    save_conversation("user", text)
    log_memory_event("conversation", text[:80], importance=4)

    if not GROQ_API_KEY:
        tg_send(chat_id, "Missing GROQ key.")
        return

    try:
        reply = ai_respond(text)

        save_conversation("assistant", reply)
        log_memory_event("conversation", "ORA replied", importance=3)

        if msg_id:
            tg_edit(chat_id, msg_id, reply)
        else:
            tg_send(chat_id, reply)

    except Exception as e:
        print("[CHAT ERROR]", e)
        tg_send(chat_id, "ORA error occurred.")


# ========================
# MAIN LOOP
# ========================
def run_telegram_bot():
    print("[TELEGRAM] Bot started...")
    offset = None

    while True:
        try:
            updates = tg_get_updates(offset)

            for update in updates:
                offset = update["update_id"] + 1
                msg = update.get("message", {})

                if not msg:
                    continue

                chat_id = msg["chat"]["id"]
                text = msg.get("text", "").strip()

                if not text:
                    continue

                if text.startswith("/"):
                    parts = text.split()
                    cmd = parts[0].lower().split("@")[0]
                    args = parts[1:]

                    if cmd == "/start":
                        handle_start(chat_id)
                    elif cmd == "/status":
                        handle_status(chat_id)
                    else:
                        tg_send(chat_id, f"Unknown command: {cmd}")
                else:
                    handle_chat(chat_id, text)

        except Exception as e:
            print(f"[BOT LOOP ERROR] {e}")
            time.sleep(5)