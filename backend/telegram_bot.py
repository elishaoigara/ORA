import asyncio
import ast
from telegram import Update, Bot
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.error import TelegramError
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from database import get_recent_alerts, get_system_stats, acknowledge_alert, save_conversation, get_conversation_history
from memory.events import log_memory_event

# --- Send helpers ---

async def _send(text, is_alert=False):
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    prefix = "🔴 *ORA ALERT*\n\n" if is_alert else ""
    try:
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=f"{prefix}{text}",
            parse_mode="Markdown"
        )
    except TelegramError as e:
        print(f"[Telegram Error] {e}")

def notify(message, is_alert=False):
    asyncio.run(_send(message, is_alert))

# --- Command handlers ---

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👁 *ORA is online.*\n\n"
        "I'm your personal intelligence system, Elisha.\n\n"
        "*Commands:*\n"
        "/status — system health\n"
        "/alerts — recent alerts\n"
        "/ack [id] — acknowledge alert\n"
        "/memory — what ORA remembers\n"
        "/help — show commands\n\n"
        "Or just talk to me normally.",
        parse_mode="Markdown"
    )

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    row = get_system_stats()
    if not row:
        await update.message.reply_text("No data yet — ORA is still warming up.")
        return
    data = ast.literal_eval(row[0])
    msg = (
        f"📊 *System Status*\n\n"
        f"🖥 CPU: {data.get('cpu_percent')}%\n"
        f"🧠 RAM: {data.get('ram_percent')}%\n"
        f"💾 Disk free: {data.get('disk_free_gb', 0):.1f}GB\n"
        f"🕐 Last update: {row[1][11:19]}"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def cmd_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    alerts = get_recent_alerts(5)
    if not alerts:
        await update.message.reply_text("✅ No alerts on record.")
        return
    msg = "🔔 *Recent Alerts*\n\n"
    for a in alerts:
        ack = "✅" if a[5] else "🔴"
        msg += f"{ack} `[{a[0]}]` *{a[1]}*\n{a[2]}\n_{a[4][11:19]}_\n\n"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def cmd_ack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        alert_id = int(context.args[0])
        feedback = " ".join(context.args[1:]) or None
        acknowledge_alert(alert_id, feedback)
        await update.message.reply_text(f"✅ Alert `{alert_id}` acknowledged.", parse_mode="Markdown")
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: `/ack [id] [optional feedback]`", parse_mode="Markdown")

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
        "/status — system health snapshot\n"
        "/alerts — last 5 alerts\n"
        "/ack [id] — acknowledge an alert\n"
        "/memory — what ORA knows about you\n"
        "/help — this message\n\n"
        "You can also just talk to me normally.",
        parse_mode="Markdown"
    )

# --- Conversation handler (the magic) ---

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    await update.message.reply_text("🧠 thinking...", parse_mode="Markdown")

    from config import OPENAI_API_KEY
    from context import build_system_prompt
    from database import get_conversation_history, save_conversation

    save_conversation("user", user_text)
    log_memory_event("conversation", f"Elisha asked: {user_text[:80]}", importance=4)

    if not OPENAI_API_KEY:
        reply = (
            "I received your message but my AI reasoning layer isn't connected yet.\n"
            "Add your OPENAI_API_KEY to the .env file to enable full conversation."
        )
        await update.message.reply_text(reply)
        return

    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)

        history = get_conversation_history(limit=10)
        messages = [{"role": "system", "content": build_system_prompt()}]
        for role, content in history:
            messages.append({"role": role, "content": content})

        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages,
            max_tokens=500,
            temperature=0.7
        )

        reply = response.choices[0].message.content
        save_conversation("assistant", reply)
        log_memory_event("conversation", f"ORA replied to Elisha", importance=3)
        await update.message.reply_text(reply)

    except Exception as e:
        await update.message.reply_text(f"⚠️ ORA reasoning error: {str(e)[:100]}")

# --- Bot runner ---

def run_telegram_bot():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("alerts", cmd_alerts))
    app.add_handler(CommandHandler("ack", cmd_ack))
    app.add_handler(CommandHandler("memory", cmd_memory))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("[ORA] Telegram bot listening...")
    app.run_polling()