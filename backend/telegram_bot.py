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


# -----------------------------
# GLOBAL CLIENTS
# -----------------------------
client = Groq(api_key=GROQ_API_KEY)
bot = Bot(token=TELEGRAM_BOT_TOKEN)

LAST_REQUEST = 0
COOLDOWN = 2  # slightly faster


# -----------------------------
# RATE LIMIT
# -----------------------------
async def rate_limit():
    global LAST_REQUEST
    now = time.time()
    wait = COOLDOWN - (now - LAST_REQUEST)
    if wait > 0:
        await asyncio.sleep(wait)
    LAST_REQUEST = time.time()


# -----------------------------
# SAFE NOTIFIER (FIXED)
# -----------------------------
async def _send(text, is_alert=False):
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
    """
    SAFE version — works inside threads + async loops
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(_send(message, is_alert))
        else:
            asyncio.run(_send(message, is_alert))
    except RuntimeError:
        asyncio.run(_send(message, is_alert))


# -----------------------------
# TASK CHECKER (NO SPAM)
# -----------------------------
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
                    notify(f"⏰ Task due now: *{t[1]}*", is_alert=True)

        except Exception as e:
            print(f"[TASK PARSE ERROR] {e}")


# -----------------------------
# COMMANDS (unchanged core)
# -----------------------------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👁 *ORA is online.*\n\n"
        "I'm your personal intelligence system.\n\n"
        "Use /help to explore capabilities.",
        parse_mode="Markdown"
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    row = get_system_stats()

    if not row:
        await update.message.reply_text("ORA warming up...")
        return

    data = ast.literal_eval(row[0])

    msg = (
        f"📊 *System Status*\n\n"
        f"CPU: {data.get('cpu_percent')}%\n"
        f"RAM: {data.get('ram_percent')}%\n"
        f"Disk: {data.get('disk_free_gb', 0):.1f}GB\n"
        f"Time: {row[1][11:19]}"
    )

    await update.message.reply_text(msg, parse_mode="Markdown")


async def cmd_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args

    if not args:
        await update.message.reply_text("/task add [title] @HH:MM")
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
                    f"{date.today().isoformat()} {time_str}",
                    "%Y-%m-%d %H:%M",
                ).isoformat()
            except:
                await update.message.reply_text("Use HH:MM format")
                return

        add_task(title, due_at)
        await update.message.reply_text(f"✅ {title}")


# -----------------------------
# AI CHAT (UPGRADED)
# -----------------------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    thinking = await update.message.reply_text("🧠 thinking...")

    save_conversation("user", user_text)
    log_memory_event("conversation", user_text[:80], importance=4)

    if not GROQ_API_KEY:
        await thinking.edit_text("Missing GROQ_API_KEY")
        return

    try:
        await rate_limit()

        history = get_conversation_history(limit=8)

        messages = [{"role": "system", "content": build_system_prompt(query=user_text)}]

        for role, content in history:
            messages.append({
                "role": "user" if role == "user" else "assistant",
                "content": content,
            })

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            max_tokens=500,
            temperature=0.7,
        )

        reply = response.choices[0].message.content.strip()

        save_conversation("assistant", reply)
        log_memory_event("conversation", "ORA replied", importance=3)

        await thinking.edit_text(reply)

    except Exception as e:
        print("[GROQ ERROR]", e)
        await thinking.edit_text("⚠️ ORA hit a thinking error. Try again.")


# -----------------------------
# BOT RUNNER
# -----------------------------
def run_telegram_bot():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("task", cmd_task))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("[ORA] Telegram bot running...")
    app.run_polling()