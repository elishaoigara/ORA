import asyncio
import ast
import time
import threading
from datetime import date, datetime

from telegram import Update, Bot
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from telegram.error import TelegramError

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, GROQ_API_KEY
from database import (
    get_recent_alerts,
    get_system_stats,
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
# GLOBAL CLIENTS
# ========================
client = Groq(api_key=GROQ_API_KEY)
bot = Bot(token=TELEGRAM_BOT_TOKEN)

LAST_REQUEST = 0
COOLDOWN = 2


# ========================
# RATE LIMIT
# ========================
async def rate_limit():
    global LAST_REQUEST
    now = time.time()
    wait = COOLDOWN - (now - LAST_REQUEST)
    if wait > 0:
        await asyncio.sleep(wait)
    LAST_REQUEST = time.time()


# ========================
# NOTIFY — thread-safe, works from anywhere
# ========================
async def _do_send(message, is_alert=False):
    prefix = "ORA ALERT\n\n" if is_alert else ""
    try:
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=prefix + message,
            parse_mode="Markdown",
        )
    except TelegramError as e:
        print(f"[Telegram Error] {e}")


def notify(message, is_alert=False):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(_do_send(message, is_alert))
        else:
            loop.run_until_complete(_do_send(message, is_alert))
    except RuntimeError:
        asyncio.run(_do_send(message, is_alert))


# ========================
# TASK DUE CHECKER
# ========================
_notified_tasks = set()


def check_due_tasks():
    tasks = get_tasks("pending")
    now = datetime.now()
    for t in tasks:
        task_id = t[0]
        due_at = t[4]
        if not due_at:
            continue
        try:
            due_time = datetime.fromisoformat(due_at)
            diff = (due_time - now).total_seconds()
            if 0 <= diff <= 60:
                if task_id not in _notified_tasks:
                    _notified_tasks.add(task_id)
                    notify(f"Task due now: *{t[1]}*", is_alert=True)
        except Exception as e:
            print(f"[TASK PARSE ERROR] {e}")


# ========================
# KNOWLEDGE-FIRST AI RESPONSE
# Searches your uploaded docs/notes before calling Groq
# ========================
async def ai_respond(user_text):
    await rate_limit()

    # 1. Search your knowledge base first
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

    # 2. Build full system prompt (includes profile, memory, alerts, preferences)
    system_prompt = build_system_prompt(query=user_text)

    # 3. If knowledge hits found, make AI use them first
    if knowledge_context:
        system_prompt = (
            "PRIORITY: Answer from Elisha's own data below first. "
            "Only use general knowledge if his data does not cover it.\n\n"
            + knowledge_context
            + "\n\n---\n\n"
            + system_prompt
        )

    # 4. Get conversation history for context
    history = get_conversation_history(limit=8)

    messages = [{"role": "system", "content": system_prompt}]
    for role, content in history:
        messages.append({
            "role": "user" if role == "user" else "assistant",
            "content": content,
        })
    messages.append({"role": "user", "content": user_text})

    # 5. Call Groq with full context
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages,
        max_tokens=600,
        temperature=0.6,
    )

    return response.choices[0].message.content.strip()


# ========================
# COMMANDS
# ========================
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    profile = get_all_profile()
    name = profile.get("name", "Elisha")
    await update.message.reply_text(
        f"ORA online, {name}.\n\n"
        "Your personal intelligence system.\n\n"
        "Commands:\n"
        "/status - System health\n"
        "/task add [title] @HH:MM - Add task\n"
        "/tasks - List pending tasks\n"
        "/remind 5m [message] - Set reminder\n"
        "/predict - ORA predictions\n"
        "/memory - Your profile\n\n"
        "Or just talk to me.",
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    row = get_system_stats()
    if not row:
        await update.message.reply_text("ORA warming up, no data yet.")
        return
    try:
        data = ast.literal_eval(row[0])
        cpu = data.get("cpu_percent", "?")
        ram = data.get("ram_percent", "?")
        disk = data.get("disk_free_gb", 0)
        ts = row[1][11:19]
        msg = (
            f"System Status\n\n"
            f"CPU: {cpu}%\n"
            f"RAM: {ram}%\n"
            f"Disk free: {disk:.1f}GB\n"
            f"Last sync: {ts}"
        )
        await update.message.reply_text(msg)
    except Exception as e:
        await update.message.reply_text(f"Error reading status: {e}")


async def cmd_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tasks = get_tasks("pending")
    if not tasks:
        await update.message.reply_text("No pending tasks.")
        return
    lines = ["Pending Tasks\n"]
    for t in tasks:
        due = f" - due {t[4][11:16]}" if t[4] else ""
        lines.append(f"[{t[0]}] {t[1]}{due} ({t[2]})")
    await update.message.reply_text("\n".join(lines))


async def cmd_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text(
            "/task add [title] @HH:MM\n"
            "/task done [id]\n"
            "/task delete [id]"
        )
        return

    sub = args[0].lower()

    if sub == "add":
        full = " ".join(args[1:])
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
                await update.message.reply_text("Use HH:MM format for time.")
                return
        add_task(title, due_at=due_at)
        await update.message.reply_text(f"Task added: {title}")

    elif sub == "done":
        if len(args) < 2:
            await update.message.reply_text("Usage: /task done [id]")
            return
        try:
            complete_task(int(args[1]))
            await update.message.reply_text(f"Task [{args[1]}] done.")
        except Exception as e:
            await update.message.reply_text(f"Error: {e}")

    elif sub == "delete":
        if len(args) < 2:
            await update.message.reply_text("Usage: /task delete [id]")
            return
        try:
            delete_task(int(args[1]))
            await update.message.reply_text(f"Task [{args[1]}] deleted.")
        except Exception as e:
            await update.message.reply_text(f"Error: {e}")

    else:
        await update.message.reply_text("Unknown subcommand. Use: add, done, delete")


async def cmd_memory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    profile = get_all_profile()
    if not profile:
        await update.message.reply_text("No profile data yet.")
        return
    lines = ["Your Profile\n"]
    for k, v in profile.items():
        lines.append(f"- {k}: {v}")
    await update.message.reply_text("\n".join(lines))


async def cmd_predict(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        from intelligence.prediction_engine import predict_needs
        predictions = predict_needs()
        if not predictions:
            await update.message.reply_text("No predictions right now.")
            return
        lines = ["ORA Predictions\n"]
        for p in predictions[:5]:
            bar = "*" * int(p["confidence"] * 10)
            lines.append(f"[{p['type']}]\n{p['message']}\nConfidence: {bar}\n")
        await update.message.reply_text("\n".join(lines))
    except Exception as e:
        await update.message.reply_text(f"Prediction error: {e}")


async def cmd_remind(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "Usage:\n"
            "/remind 14:30 Call client\n"
            "/remind 5m Check the oven\n"
            "/remind 2h Review PR"
        )
        return

    time_arg = args[0]
    message = " ".join(args[1:])
    now = datetime.now()

    try:
        if time_arg.endswith("m"):
            delay_seconds = int(time_arg[:-1]) * 60
        elif time_arg.endswith("h"):
            delay_seconds = int(time_arg[:-1]) * 3600
        elif ":" in time_arg:
            target = datetime.strptime(
                f"{now.date().isoformat()} {time_arg}", "%Y-%m-%d %H:%M"
            )
            if target < now:
                await update.message.reply_text("That time has already passed today.")
                return
            delay_seconds = (target - now).total_seconds()
        else:
            await update.message.reply_text("Format: 14:30 or 5m or 2h")
            return

        def _fire():
            notify(f"Reminder: {message}")

        timer = threading.Timer(delay_seconds, _fire)
        timer.daemon = True
        timer.start()

        mins = int(delay_seconds / 60)
        secs = int(delay_seconds % 60)
        if delay_seconds < 3600:
            await update.message.reply_text(
                f"Reminder set for {mins}m {secs}s:\n{message}"
            )
        else:
            await update.message.reply_text(
                f"Reminder set for {time_arg}:\n{message}"
            )

    except Exception as e:
        await update.message.reply_text(f"Could not set reminder: {e}")


# ========================
# MESSAGE HANDLER — knowledge-first
# ========================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    thinking = await update.message.reply_text("thinking...")

    save_conversation("user", user_text)
    log_memory_event("conversation", user_text[:80], importance=4)

    if not GROQ_API_KEY:
        await thinking.edit_text("GROQ_API_KEY not configured.")
        return

    try:
        reply = await ai_respond(user_text)
        save_conversation("assistant", reply)
        log_memory_event("conversation", "ORA replied", importance=3)
        await thinking.edit_text(reply)
    except Exception as e:
        print(f"[AI ERROR] {e}")
        await thinking.edit_text("ORA hit an error. Try again.")


# ========================
# BOT RUNNER
# v20 compatible - stop_signals=None lets it run in a non-main thread
# ========================
def run_telegram_bot():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("task", cmd_task))
    app.add_handler(CommandHandler("tasks", cmd_tasks))
    app.add_handler(CommandHandler("memory", cmd_memory))
    app.add_handler(CommandHandler("predict", cmd_predict))
    app.add_handler(CommandHandler("remind", cmd_remind))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("[ORA] Telegram bot polling...")
    app.run_polling(drop_pending_updates=True, stop_signals=None)