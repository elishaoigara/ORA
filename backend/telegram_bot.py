import asyncio
import ast

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


async def _send(text, is_alert=False):
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    prefix = " *ORA ALERT*\n\n" if is_alert else ""
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


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(" ORA is online.\n\n/status\n/alerts\n/ack [id]\n/help\n\nJust talk to me.")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    row = get_system_stats()
    if not row:
        await update.message.reply_text("ORA is warming up.")
        return
    data = ast.literal_eval(row[0])
    msg = f" System Status\n\nCPU: {data.get('cpu_percent')}%\nRAM: {data.get('ram_percent')}%\nDisk: {data.get('disk_free_gb', 0):.1f}GB\nTime: {row[1][11:19]}"
    await update.message.reply_text(msg)


async def cmd_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    alerts = get_recent_alerts(5)
    if not alerts:
        await update.message.reply_text("No alerts.")
        return
    msg = "Recent Alerts:\n\n"
    for a in alerts:
        status = "" if a[5] else ""
        msg += f"{status} [{a[0]}] {a[1]}\n{a[2]}\n\n"
    await update.message.reply_text(msg)


async def cmd_ack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        alert_id = int(context.args[0])
        feedback = " ".join(context.args[1:]) if len(context.args) > 1 else None
        acknowledge_alert(alert_id, feedback)
        await update.message.reply_text(f"Alert {alert_id} acknowledged.")
    except Exception:
        await update.message.reply_text("Usage: /ack [id] [optional feedback]")


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("/status\n/alerts\n/ack\n/help\n\nTalk normally for AI chat.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    thinking_msg = await update.message.reply_text(" thinking...")

    save_conversation("user", user_text)
    log_memory_event("conversation", f"Elisha: {user_text[:80]}", importance=4)

    if not GROQ_API_KEY:
        await thinking_msg.edit_text("Missing GROQ_API_KEY in .env")
        return

    try:
        from groq import Groq

        history = get_conversation_history(limit=10)
        messages = [{"role": "system", "content": build_system_prompt()}]
        for role, content in history[:-1]:
            groq_role = "user" if role == "user" else "assistant"
            messages.append({"role": groq_role, "content": content})
        messages.append({"role": "user", "content": user_text})

        client = Groq(api_key=GROQ_API_KEY)
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            max_tokens=500,
            temperature=0.7,
        )

        reply = response.choices[0].message.content
        save_conversation("assistant", reply)
        log_memory_event("conversation", "ORA replied", importance=3)
        await thinking_msg.edit_text(reply)

    except Exception as e:
        await thinking_msg.edit_text(f"ORA error: {str(e)[:150]}")


def run_telegram_bot():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("alerts", cmd_alerts))
    app.add_handler(CommandHandler("ack", cmd_ack))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("task", cmd_task))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("[ORA] Telegram bot running...")
    app.run_polling()

async def cmd_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("Task commands:\n/task add [title]\n/task list\n/task done [id]\n/task delete [id]")
        return
    sub = args[0].lower()
    if sub == "add":
        if len(args) < 2:
            await update.message.reply_text("Usage: /task add [title]")
            return
        title = " ".join(args[1:])
        add_task(title)
        await update.message.reply_text(f"? Task added: {title}")
    elif sub == "list":
        tasks = get_tasks("pending")
        if not tasks:
            await update.message.reply_text("? No pending tasks.")
            return
        msg = "?? Pending Tasks:\n\n"
        for t in tasks:
            msg += f"[{t[0]}] {t[1]} ({t[2]})\n"
        await update.message.reply_text(msg)
    elif sub == "done":
        try:
            complete_task(int(args[1]))
            await update.message.reply_text(f"? Task {args[1]} completed.")
        except:
            await update.message.reply_text("Usage: /task done [id]")
    elif sub == "delete":
        try:
            delete_task(int(args[1]))
            await update.message.reply_text(f"?? Task {args[1]} deleted.")
        except:
            await update.message.reply_text("Usage: /task delete [id]")
