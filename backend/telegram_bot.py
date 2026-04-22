"""
ORA Telegram Bot — pure HTTP implementation.
No python-telegram-bot library = no asyncio restrictions.
Runs cleanly in any thread on Railway/Render.
"""
print("[TELEGRAM] Loading pure HTTP bot...")

import ast
import time
import threading
import requests
from datetime import date, datetime

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, GROQ_API_KEY
from database import (
    get_system_stats,
    get_recent_alerts,
    acknowledge_alert,
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
# TELEGRAM API HELPERS
# ========================
BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


def tg_send(chat_id, text):
    """Send a message. Returns message_id."""
    try:
        r = requests.post(
            f"{BASE}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "Markdown"
            },
            timeout=10,
        )
        return r.json().get("result", {}).get("message_id")
    except Exception as e:
        print(f"[TG SEND ERROR] {e}")
        return None


def tg_edit(chat_id, message_id, text):
    """Edit an existing message."""
    try:
        requests.post(
            f"{BASE}/editMessageText",
            json={
                "chat_id": chat_id,
                "message_id": message_id,
                "text": text,
                "parse_mode": "Markdown"
            },
            timeout=10,
        )
    except Exception as e:
        print(f"[TG EDIT ERROR] {e}")


def tg_get_updates(offset=None):
    """Long-poll for new messages."""
    try:
        params = {"timeout": 30, "allowed_updates": ["message"]}
        if offset:
            params["offset"] = offset
        r = requests.get(f"{BASE}/getUpdates", params=params, timeout=35)
        return r.json().get("result", [])
    except Exception as e:
        print(f"[TG POLL ERROR] {e}")
        return []


# ========================
# NOTIFY — call from anywhere
# ========================
def notify(message, is_alert=False):
    prefix = "🔴 ORA ALERT\n\n" if is_alert else ""
    tg_send(TELEGRAM_CHAT_ID, prefix + message)


# ========================
# TASK DUE CHECKER
# ========================
_notified_tasks = set()


def check_due_tasks():
    tasks = get_tasks("pending")
    now = datetime.now()
    for t in tasks:
        task_id = t[0]
        title = t[1]
        due_at = t[4]
        if not due_at:
            continue
        try:
            due_time = datetime.fromisoformat(due_at)
            diff = (due_time - now).total_seconds()
            if 0 <= diff <= 60 and task_id not in _notified_tasks:
                _notified_tasks.add(task_id)
                notify(f"⏰ Task due now: *{title}*", is_alert=True)
        except Exception as e:
            print(f"[TASK PARSE ERROR] {e}")


# ========================
# GROQ AI
# ========================
client = Groq(api_key=GROQ_API_KEY)
LAST_REQUEST = 0
COOLDOWN = 2


def ai_respond(user_text):
    global LAST_REQUEST
    elapsed = time.time() - LAST_REQUEST
    if elapsed < COOLDOWN:
        time.sleep(COOLDOWN - elapsed)
    LAST_REQUEST = time.time()

    # Search knowledge base first
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

    # Build system prompt
    system_prompt = build_system_prompt(query=user_text)

    # Inject knowledge as top priority
    if knowledge_context:
        system_prompt = (
            "PRIORITY: Answer from Elisha's own files first.\n\n"
            + knowledge_context
            + "\n\n---\n\n"
            + system_prompt
        )

    # Build messages with history
    history = get_conversation_history(limit=8)
    messages = [{"role": "system", "content": system_prompt}]
    for role, content in history:
        messages.append({
            "role": "user" if role == "user" else "assistant",
            "content": content,
        })
    messages.append({"role": "user", "content": user_text})

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages,
        max_tokens=600,
        temperature=0.6,
    )
    return response.choices[0].message.content.strip()


# ========================
# COMMAND HANDLERS
# ========================

def handle_start(chat_id):
    profile = get_all_profile()
    name = profile.get("name", "Elisha")
    tg_send(chat_id,
        f"👁 *ORA online, {name}.*\n\n"
        "Your personal intelligence system.\n\n"
        "*Commands:*\n"
        "/status — system health\n"
        "/alerts — recent alerts\n"
        "/tasks — pending tasks\n"
        "/task add [title] @HH:MM\n"
        "/task done [id]\n"
        "/task delete [id]\n"
        "/remind 5m [message]\n"
        "/remind 14:30 [message]\n"
        "/brief — morning briefing\n"
        "/knowledge — your files\n"
        "/memory — your profile\n\n"
        "Or just talk to me."
    )


def handle_status(chat_id):
    row = get_system_stats()
    if not row:
        tg_send(chat_id, "ORA warming up, no data yet.")
        return
    try:
        data = ast.literal_eval(row[0])
        cpu = data.get("cpu_percent", "?")
        ram = data.get("ram_percent", "?")
        disk = round(data.get("disk_free_gb", 0), 1)
        ts = row[1][11:19]
        tg_send(chat_id,
            f"📊 *System Status*\n\n"
            f"🖥 CPU: {cpu}%\n"
            f"🧠 RAM: {ram}%\n"
            f"💾 Disk: {disk}GB free\n"
            f"🕐 Last sync: {ts}"
        )
    except Exception as e:
        tg_send(chat_id, f"Error reading status: {e}")


def handle_alerts(chat_id):
    alerts = get_recent_alerts(5)
    if not alerts:
        tg_send(chat_id, "✅ No alerts on record.")
        return
    lines = ["🔔 *Recent Alerts*\n"]
    for a in alerts:
        status = "✅" if a[5] else "🔴"
        lines.append(f"{status} [{a[0]}] *{a[1]}*\n{a[2]}")
    tg_send(chat_id, "\n".join(lines))


def handle_ack(chat_id, args):
    if not args:
        tg_send(chat_id, "Usage: /ack [id]")
        return
    try:
        alert_id = int(args[0])
        feedback = " ".join(args[1:]) or None
        acknowledge_alert(alert_id, feedback)
        tg_send(chat_id, f"✅ Alert [{alert_id}] acknowledged.")
    except Exception as e:
        tg_send(chat_id, f"Error: {e}")


def handle_tasks(chat_id):
    tasks = get_tasks("pending")
    if not tasks:
        tg_send(chat_id, "No pending tasks.")
        return
    lines = ["📌 *Pending Tasks*\n"]
    for t in tasks:
        due = f" ⏰ {t[4][11:16]}" if t[4] else ""
        lines.append(f"`[{t[0]}]` {t[1]}{due}")
    tg_send(chat_id, "\n".join(lines))


def handle_task(chat_id, args):
    if not args:
        tg_send(chat_id,
            "/task add [title] @HH:MM\n"
            "/task done [id]\n"
            "/task delete [id]"
        )
        return

    sub = args[0].lower()

    if sub == "add":
        full = " ".join(args[1:])
        if not full:
            tg_send(chat_id, "Usage: /task add [title] @HH:MM")
            return
        due_at = None
        title = full
        if "@" in full:
            parts = full.split("@")
            title = parts[0].strip()
            time_str = parts[1].strip()
            try:
                due_at = datetime.strptime(
                    f"{date.today().isoformat()} {time_str}", "%Y-%m-%d %H:%M"
                ).isoformat()
            except Exception:
                tg_send(chat_id, "Use HH:MM format. Example: /task add Meeting @14:30")
                return
        add_task(title, due_at=due_at)
        reply = f"✅ Task added: *{title}*"
        if due_at:
            reply += f"\n⏰ Due at {due_at[11:16]}"
        tg_send(chat_id, reply)

    elif sub == "done":
        if len(args) < 2:
            tg_send(chat_id, "Usage: /task done [id]")
            return
        try:
            complete_task(int(args[1]))
            tg_send(chat_id, f"✅ Task [{args[1]}] completed.")
        except Exception as e:
            tg_send(chat_id, f"Error: {e}")

    elif sub == "delete":
        if len(args) < 2:
            tg_send(chat_id, "Usage: /task delete [id]")
            return
        try:
            delete_task(int(args[1]))
            tg_send(chat_id, f"🗑 Task [{args[1]}] deleted.")
        except Exception as e:
            tg_send(chat_id, f"Error: {e}")

    else:
        tg_send(chat_id, "Unknown subcommand. Use: add, done, delete")


def handle_memory(chat_id):
    from memory.preferences import get_preferences
    profile = get_all_profile()
    prefs = get_preferences()

    if not profile:
        tg_send(chat_id, "No profile data yet.")
        return

    lines = ["🧠 *ORA Memory*\n\n*Profile:*"]
    for k, v in profile.items():
        lines.append(f"- {k}: {v}")

    if prefs:
        lines.append("\n*Preferences:*")
        for p in prefs:
            lines.append(f"- {p[0]}/{p[1]}: {p[2]}")

    tg_send(chat_id, "\n".join(lines))


def handle_brief(chat_id):
    tg_send(chat_id, "📋 Generating your briefing...")
    try:
        from briefing import generate_briefing
        briefing = generate_briefing()
        tg_send(chat_id, briefing)
    except Exception as e:
        tg_send(chat_id, f"Briefing error: {e}")


def handle_knowledge(chat_id, args):
    if not args:
        try:
            from knowledge import get_all_documents
            docs = get_all_documents()
            if not docs:
                tg_send(chat_id, "No documents indexed yet.\nUpload via the web dashboard.")
                return
            lines = [f"📚 *Knowledge Base* — {len(docs)} files\n"]
            for d in docs[:8]:
                lines.append(f"◈ *{d['filename']}*")
                if d.get("summary"):
                    lines.append(f"  _{d['summary'][:100]}..._")
                lines.append(f"  {d['chunks']} chunks · {d['doc_type']}\n")
            tg_send(chat_id, "\n".join(lines))
        except Exception as e:
            tg_send(chat_id, f"Knowledge error: {e}")
        return

    sub = args[0].lower()

    if sub == "search":
        query = " ".join(args[1:])
        if not query:
            tg_send(chat_id, "Usage: /knowledge search [query]")
            return
        try:
            from knowledge import search_knowledge
            results = search_knowledge(query, n_results=3)
            if not results:
                tg_send(chat_id, "Nothing found for that query.")
                return
            lines = [f"🔍 *Search: {query}*\n"]
            for r in results:
                lines.append(f"📄 *{r['filename']}* ({int(r['relevance']*100)}% match)")
                lines.append(f"{r['text'][:250]}...\n")
            tg_send(chat_id, "\n".join(lines))
        except Exception as e:
            tg_send(chat_id, f"Search error: {e}")

    elif sub == "summary":
        filename = " ".join(args[1:])
        try:
            from knowledge import get_document_summary
            summary = get_document_summary(filename)
            tg_send(chat_id, f"📋 *{filename}*\n\n{summary}")
        except Exception as e:
            tg_send(chat_id, f"Error: {e}")


def handle_remind(chat_id, args):
    if len(args) < 2:
        tg_send(chat_id,
            "Usage:\n"
            "/remind 14:30 Call client\n"
            "/remind 5m Check oven\n"
            "/remind 2h Review PR"
        )
        return

    time_arg = args[0]
    message = " ".join(args[1:])
    now = datetime.now()

    try:
        if time_arg.endswith("m"):
            delay = int(time_arg[:-1]) * 60
        elif time_arg.endswith("h"):
            delay = int(time_arg[:-1]) * 3600
        elif ":" in time_arg:
            target = datetime.strptime(
                f"{now.date().isoformat()} {time_arg}", "%Y-%m-%d %H:%M"
            )
            if target < now:
                tg_send(chat_id, "That time has already passed today.")
                return
            delay = (target - now).total_seconds()
        else:
            tg_send(chat_id, "Format: 14:30 or 5m or 2h")
            return

        def _fire():
            notify(f"⏰ Reminder: {message}")

        t = threading.Timer(delay, _fire)
        t.daemon = True
        t.start()

        mins = int(delay / 60)
        if delay < 3600:
            tg_send(chat_id, f"⏰ Reminder set for {mins} minutes:\n_{message}_")
        else:
            tg_send(chat_id, f"⏰ Reminder set for {time_arg}:\n_{message}_")

    except Exception as e:
        tg_send(chat_id, f"Could not set reminder: {e}")


def handle_chat(chat_id, text):
    msg_id = tg_send(chat_id, "🧠 thinking...")

    save_conversation("user", text)
    log_memory_event("conversation", text[:80], importance=4)

    if not GROQ_API_KEY:
        tg_send(chat_id, "GROQ_API_KEY not configured.")
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
        print(f"[AI ERROR] {e}")
        err = "ORA hit an error. Try again in a moment."
        if msg_id:
            tg_edit(chat_id, msg_id, err)
        else:
            tg_send(chat_id, err)


# ========================
# MAIN POLLING LOOP
# ========================
def run_telegram_bot():
    print("[TELEGRAM] Bot polling started...")
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
                    elif cmd == "/alerts":
                        handle_alerts(chat_id)
                    elif cmd == "/ack":
                        handle_ack(chat_id, args)
                    elif cmd == "/tasks":
                        handle_tasks(chat_id)
                    elif cmd == "/task":
                        handle_task(chat_id, args)
                    elif cmd == "/memory":
                        handle_memory(chat_id)
                    elif cmd == "/brief":
                        handle_brief(chat_id)
                    elif cmd == "/knowledge":
                        handle_knowledge(chat_id, args)
                    elif cmd == "/remind":
                        handle_remind(chat_id, args)
                    elif cmd == "/help":
                        handle_start(chat_id)
                    else:
                        tg_send(chat_id, f"Unknown command. Send /start to see all commands.")
                else:
                    handle_chat(chat_id, text)

        except Exception as e:
            print(f"[TELEGRAM LOOP ERROR] {e}")
            time.sleep(5)