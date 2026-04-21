import asyncio
import ast
import time
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
from context import build_system_prompt

from groq import Groq

client = Groq(api_key=GROQ_API_KEY)

LAST_REQUEST = 0
COOLDOWN = 3


async def rate_limit():
    global LAST_REQUEST
    now = time.time()
    wait = COOLDOWN - (now - LAST_REQUEST)
    if wait > 0:
        await asyncio.sleep(wait)
    LAST_REQUEST = time.time()


# -----------------------------
# NOTIFIER
# -----------------------------
async def _send(text, is_alert=False):
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    prefix = "🔴 ORA ALERT\n\n" if is_alert else ""
    try:
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=f"{prefix}{text}",
            parse_mode="Markdown",
        )
    except TelegramError as e:
        print(f"[Telegram Error] {e}")


def notify(message, is_alert=False):
    asyncio.run(_send(message, is_alert))


# -----------------------------
# TASK CHECKER
# -----------------------------
def check_due_tasks():
    tasks = get_tasks("pending")
    now = datetime.now()
    for t in tasks:
        due_at = t[4]
        if not due_at:
            continue
        try:
            due_time = datetime.fromisoformat(due_at)
            diff = (due_time - now).total_seconds()
            if 0 <= diff <= 60:
                notify(f"⏰ Task due now: *{t[1]}*", is_alert=True)
        except Exception as e:
            print(f"[TASK PARSE ERROR] {e}")


# -----------------------------
# COMMANDS
# -----------------------------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👁 *ORA is online.*\n\n"
        "I'm your personal intelligence system, Elisha.\n\n"
        "*Commands:*\n"
        "/status — system health\n"
        "/alerts — recent alerts\n"
        "/ack [id] — acknowledge alert\n"
        "/task — manage tasks\n"
        "/memory — what ORA remembers\n"
        "/help — show commands\n\n"
        "Or just talk to me normally.",
        parse_mode="Markdown"
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    row = get_system_stats()
    if not row:
        await update.message.reply_text("ORA is warming up...")
        return
    data = ast.literal_eval(row[0])
    msg = (
        f"📊 *System Status*\n\n"
        f"🖥 CPU: {data.get('cpu_percent')}%\n"
        f"🧠 RAM: {data.get('ram_percent')}%\n"
        f"💾 Disk: {data.get('disk_free_gb', 0):.1f}GB\n"
        f"🕐 Updated: {row[1][11:19]}"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def cmd_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    alerts = get_recent_alerts(5)
    if not alerts:
        await update.message.reply_text("✅ No alerts.")
        return
    msg = "🔔 *Recent Alerts*\n\n"
    for a in alerts:
        status = "✅" if a[5] else "🔴"
        msg += f"{status} `[{a[0]}]` *{a[1]}*\n{a[2]}\n\n"
    await update.message.reply_text(msg, parse_mode="Markdown")


async def cmd_ack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        alert_id = int(context.args[0])
        feedback = " ".join(context.args[1:]) if len(context.args) > 1 else None
        acknowledge_alert(alert_id, feedback)
        await update.message.reply_text(f"✅ Alert `{alert_id}` acknowledged.", parse_mode="Markdown")
    except Exception:
        await update.message.reply_text("Usage: /ack [id] [optional note]")


async def cmd_memory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from memory.profile import get_all_profile
    from memory.preferences import get_preferences
    profile = get_all_profile()
    prefs = get_preferences()
    msg = "🧠 *ORA Memory*\n\n*Profile:*\n"
    for k, v in profile.items():
        msg += f"- {k}: {v}\n"
    if prefs:
        msg += "\n*Preferences:*\n"
        for p in prefs:
            msg += f"- {p[0]}/{p[1]}: {p[2]}\n"
    await update.message.reply_text(msg, parse_mode="Markdown")


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "*ORA Commands*\n\n"
        "/status — system health\n"
        "/alerts — last 5 alerts\n"
        "/ack [id] — acknowledge alert\n"
        "/task add [title] @HH:MM — add task\n"
        "/task list — see pending tasks\n"
        "/task done [id] — complete task\n"
        "/task delete [id] — delete task\n"
        "/memory — ORA profile\n"
        "/help — this message",
        parse_mode="Markdown"
    )


async def cmd_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text(
            "*Task Manager*\n\n"
            "/task add [title] @HH:MM\n"
            "/task list\n"
            "/task done [id]\n"
            "/task delete [id]",
            parse_mode="Markdown"
        )
        return

    sub = args[0].lower()

    if sub == "add":
        if len(args) < 2:
            await update.message.reply_text("Usage: /task add [title] @HH:MM")
            return
        full = " ".join(args[1:])
        due_at = None
        title = full
        time_str = None
        if "@" in full:
            parts = full.split("@")
            title = parts[0].strip()
            time_str = parts[1].strip()
            try:
                due_at = datetime.strptime(
                    f"{date.today().isoformat()} {time_str}", "%Y-%m-%d %H:%M"
                ).isoformat()
            except ValueError:
                await update.message.reply_text("Time format should be HH:MM e.g. @14:30")
                return
        add_task(title, due_at=due_at)
        reply = f"✅ Task added: *{title}*"
        if time_str:
            reply += f"\n⏰ Due at {time_str}"
        await update.message.reply_text(reply, parse_mode="Markdown")

    elif sub == "list":
        tasks = get_tasks("pending")
        if not tasks:
            await update.message.reply_text("No pending tasks.")
            return
        msg = "📌 *Pending Tasks*\n\n"
        for t in tasks:
            due = f" ⏰ {t[4][11:16]}" if t[4] else ""
            msg += f"`[{t[0]}]` {t[1]}{due}\n"
        await update.message.reply_text(msg, parse_mode="Markdown")

    elif sub == "done":
        try:
            complete_task(int(args[1]))
            await update.message.reply_text("✅ Task completed.")
        except Exception:
            await update.message.reply_text("Usage: /task done [id]")

    elif sub == "delete":
        try:
            delete_task(int(args[1]))
            await update.message.reply_text("🗑 Task deleted.")
        except Exception:
            await update.message.reply_text("Usage: /task delete [id]")


# -----------------------------
# AI CONVERSATION
# -----------------------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    thinking = await update.message.reply_text("🧠 thinking...")

    save_conversation("user", user_text)
    log_memory_event("conversation", user_text[:80], importance=4)

    if not GROQ_API_KEY:
        await thinking.edit_text("Missing GROQ_API_KEY in .env")
        return

    try:
        await rate_limit()

        history = get_conversation_history(limit=6)
        messages = [{"role": "system", "content": build_system_prompt()}]

        for role, content in history[:-1]:
            messages.append({
                "role": "user" if role == "user" else "assistant",
                "content": content,
            })

        messages.append({"role": "user", "content": user_text})

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            max_tokens=450,
            temperature=0.7,
        )

        reply = response.choices[0].message.content
        save_conversation("assistant", reply)
        log_memory_event("conversation", "ORA replied", importance=3)
        await thinking.edit_text(reply)

    except Exception as e:
        await thinking.edit_text(f"ORA error: {str(e)[:200]}")


# -----------------------------
# BOT RUNNER
# -----------------------------
def run_telegram_bot():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("alerts", cmd_alerts))
    app.add_handler(CommandHandler("ack", cmd_ack))
    app.add_handler(CommandHandler("memory", cmd_memory))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("task", cmd_task))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("[ORA] Telegram bot running...")
    app.run_polling()