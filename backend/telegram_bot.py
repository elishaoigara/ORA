"""
ORA Telegram Bot — pure HTTP polling implementation
Fixed: tuple unpack, task commands, knowledge search, auth check
"""

print("[TELEGRAM] Loading bot...")

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
# SAFETY CHECK
# ========================
if not TELEGRAM_BOT_TOKEN:
    print("[TELEGRAM] Missing bot token — bot disabled")
    TELEGRAM_ENABLED = False
else:
    TELEGRAM_ENABLED = True
    BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

# Authorised chat — only respond to YOUR chat id
ALLOWED_CHAT_ID = int(TELEGRAM_CHAT_ID) if TELEGRAM_CHAT_ID else None


# ========================
# GROQ CLIENT
# ========================
client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None


# ========================
# TELEGRAM API HELPERS
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
        print(f"[TG SEND ERROR] {e}")
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
    except Exception as e:
        print(f"[TG EDIT ERROR] {e}")


def tg_get_updates(offset=None):
    if not TELEGRAM_ENABLED:
        return []
    try:
        params = {"timeout": 20, "allowed_updates": ["message"]}
        if offset:
            params["offset"] = offset
        r = requests.get(f"{BASE}/getUpdates", params=params, timeout=25)
        return r.json().get("result", [])
    except Exception as e:
        print(f"[TG POLL ERROR] {e}")
        return []


# ========================
# NOTIFY (called from elsewhere in ORA)
# ========================
def notify(message, is_alert=False):
    if not ALLOWED_CHAT_ID:
        return
    prefix = "⚠ ORA ALERT\n\n" if is_alert else ""
    tg_send(ALLOWED_CHAT_ID, prefix + message)


# ========================
# TASK DUE CHECKER
# ========================
_notified_tasks = set()


def check_due_tasks():
    tasks = get_tasks("pending")
    now = datetime.now()
    for t in tasks:
        try:
            task_id, title, _, _, due_at = t[0], t[1], t[2], t[3], t[4]
            if not due_at:
                continue
            due_time = datetime.fromisoformat(due_at)
            diff = (due_time - now).total_seconds()
            if 0 <= diff <= 60 and task_id not in _notified_tasks:
                _notified_tasks.add(task_id)
                notify(f"Task due now: {title}", is_alert=True)
        except Exception as e:
            print(f"[TASK CHECK ERROR] {e}")


# ========================
# AI RESPONSE
# ========================
LAST_REQUEST = 0
COOLDOWN = 10  # seconds between AI calls


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
        # FIX: correct function name is search_and_format, not search_knowledge
        from knowledge import search_and_format
        knowledge_context = search_and_format(user_text, n_results=4)
    except Exception as e:
        print("[KNOWLEDGE ERROR]", e)

    system_prompt = build_system_prompt(query=user_text)
    if knowledge_context:
        system_prompt = knowledge_context + "\n\n" + system_prompt

    # FIX: rows are (role, content, timestamp) — unpack all 3
    history = get_conversation_history(limit=8)
    messages = [{"role": "system", "content": system_prompt}]
    for row in history:
        role = row[0]
        content = row[1]
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
            print(f"[GROQ ERROR] attempt {attempt + 1}: {e}")
            time.sleep(5 * (attempt + 1))

    return "ORA is temporarily unavailable."


# ========================
# COMMAND HANDLERS
# ========================
def handle_start(chat_id):
    profile = get_all_profile()
    name = profile.get("name", "Elisha")
    tg_send(chat_id,
        f"ORA online, {name}.\n\n"
        "Commands:\n"
        "/status — system stats\n"
        "/task add [title] @HH:MM — add task\n"
        "/task list — pending tasks\n"
        "/task done [id] — complete task\n"
        "/task delete [id] — delete task\n\n"
        "Or just chat with me directly."
    )


def handle_status(chat_id):
    try:
        # Use live psutil data — same as API endpoint
        import psutil
        cpu = psutil.cpu_percent(interval=0.1)
        ram = psutil.virtual_memory().percent
        disk = psutil.disk_usage("/").free / (1024 ** 3)
        tg_send(chat_id,
            f"ORA System Status\n"
            f"CPU:  {cpu:.1f}%\n"
            f"RAM:  {ram:.1f}%\n"
            f"Disk: {disk:.1f} GB free"
        )
    except Exception as e:
        tg_send(chat_id, f"Status error: {e}")


def handle_task_command(chat_id, parts):
    """
    /task add Buy milk @14:00
    /task list
    /task done 3
    /task delete 3
    """
    if len(parts) < 2:
        tg_send(chat_id, "Usage: /task add [title] @HH:MM | /task list | /task done [id] | /task delete [id]")
        return

    sub = parts[1].lower()

    if sub == "list":
        tasks = get_tasks("pending")
        if not tasks:
            tg_send(chat_id, "No pending tasks.")
            return
        lines = []
        for t in tasks:
            task_id, title, priority, created_at, due_at = t[0], t[1], t[2], t[3], t[4]
            due_str = f" @{due_at[11:16]}" if due_at else ""
            lines.append(f"[{task_id}] {title}{due_str} ({priority})")
        tg_send(chat_id, "Pending tasks:\n" + "\n".join(lines))

    elif sub == "add":
        if len(parts) < 3:
            tg_send(chat_id, "Usage: /task add [title] @HH:MM")
            return

        rest = " ".join(parts[2:])
        due_at = None

        # Parse optional @HH:MM time
        if "@" in rest:
            title_part, time_part = rest.rsplit("@", 1)
            title = title_part.strip()
            try:
                t = datetime.strptime(time_part.strip(), "%H:%M")
                today = datetime.now().replace(
                    hour=t.hour, minute=t.minute, second=0, microsecond=0
                )
                due_at = today.isoformat()
            except ValueError:
                title = rest  # bad time format — ignore it
        else:
            title = rest

        if not title:
            tg_send(chat_id, "Task title cannot be empty.")
            return

        add_task(title, due_at=due_at)
        due_msg = f" due at {due_at[11:16]}" if due_at else ""
        tg_send(chat_id, f"Task added: {title}{due_msg}")
        log_memory_event("task", f"Task added: {title}", importance=5)

    elif sub == "done":
        if len(parts) < 3:
            tg_send(chat_id, "Usage: /task done [id]")
            return
        try:
            task_id = int(parts[2])
            complete_task(task_id)
            tg_send(chat_id, f"Task {task_id} marked done.")
        except ValueError:
            tg_send(chat_id, "Invalid task ID.")
        except Exception as e:
            tg_send(chat_id, f"Error: {e}")

    elif sub == "delete":
        if len(parts) < 3:
            tg_send(chat_id, "Usage: /task delete [id]")
            return
        try:
            task_id = int(parts[2])
            delete_task(task_id)
            tg_send(chat_id, f"Task {task_id} deleted.")
        except ValueError:
            tg_send(chat_id, "Invalid task ID.")
        except Exception as e:
            tg_send(chat_id, f"Error: {e}")

    else:
        tg_send(chat_id, f"Unknown task subcommand: {sub}\nTry: add, list, done, delete")


def handle_chat(chat_id, text):
    # Send "thinking..." placeholder then edit with real reply
    msg_id = tg_send(chat_id, "thinking...")

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
# MAIN POLLING LOOP
# ========================
def run_telegram_bot():
    if not TELEGRAM_ENABLED:
        print("[TELEGRAM] Bot disabled — no token.")
        return

    print("[TELEGRAM] Bot polling started.")
    time.sleep(3)  # let Render finish startup

    offset = None

    while True:
        try:
            updates = tg_get_updates(offset)

            for update in updates:
                offset = update.get("update_id", 0) + 1

                msg = update.get("message")
                if not msg:
                    continue

                chat_id = msg["chat"]["id"]
                text = msg.get("text", "").strip()

                if not text:
                    continue

                # FIX: Only respond to your own chat — block everyone else
                if ALLOWED_CHAT_ID and chat_id != ALLOWED_CHAT_ID:
                    print(f"[TELEGRAM] Blocked unauthorized chat_id: {chat_id}")
                    tg_send(chat_id, "Unauthorized.")
                    continue

                print(f"[TELEGRAM] Message from {chat_id}: {text[:60]}")

                if text.startswith("/"):
                    parts = text.split()
                    cmd = parts[0].lower()

                    if cmd == "/start":
                        handle_start(chat_id)
                    elif cmd == "/status":
                        handle_status(chat_id)
                    elif cmd == "/task":
                        handle_task_command(chat_id, parts)
                    else:
                        tg_send(chat_id, f"Unknown command: {cmd}\nTry /start for help.")
                else:
                    handle_chat(chat_id, text)

        except Exception as e:
            print(f"[BOT LOOP ERROR] {e}")
            time.sleep(5)