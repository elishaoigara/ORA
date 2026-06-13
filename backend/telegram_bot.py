"""
ORA Telegram Bot — PTB async (python-telegram-bot v20+)
- STT: Groq Whisper (whisper-large-v3)
- TTS: gTTS → OGG Opus voice notes
- /voice on|off  — toggle voice replies
- Single PTB Application polling loop — no Conflict errors
- All original commands preserved
"""

from __future__ import annotations

import asyncio
import io
import re
import time
import traceback
from datetime import datetime
from typing import Optional, Dict
from threading import Lock
from collections import defaultdict

import requests
from groq import Groq

from telegram import Update, Bot
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, GROQ_API_KEY, GROQ_MODEL_PRIMARY
from database import save_conversation, get_conversation_history
from context import build_system_prompt


# ─────────────────────────────────────────────
# INIT
# ─────────────────────────────────────────────

groq_client   = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
ALLOWED_CHAT  = int(TELEGRAM_CHAT_ID) if TELEGRAM_CHAT_ID else None

# Voice reply preference per chat_id (default: on)
_VOICE_PREFS: Dict[int, bool] = {}
_VOICE_LOCK  = Lock()

# Rate limiting
_RATE:        dict = defaultdict(list)
RATE_WINDOW   = 60
RATE_MAX      = 20

# Response cache
_CACHE:       Dict[str, dict] = {}
_CACHE_LOCK   = Lock()
_CACHE_TTL    = 180
_CACHE_MAX    = 100

_start_time   = time.time()

print("[TELEGRAM] PTB async bot initialising")


# ─────────────────────────────────────────────
# GUARDS
# ─────────────────────────────────────────────

def _allowed(chat_id: int) -> bool:
    return ALLOWED_CHAT is None or chat_id == ALLOWED_CHAT

def _rate_ok(chat_id: int) -> bool:
    now   = time.time()
    cutoff = now - RATE_WINDOW
    _RATE[chat_id] = [t for t in _RATE[chat_id] if t > cutoff]
    if len(_RATE[chat_id]) >= RATE_MAX:
        return False
    _RATE[chat_id].append(now)
    return True


# ─────────────────────────────────────────────
# CACHE
# ─────────────────────────────────────────────

def _get_cache(key: str) -> Optional[str]:
    with _CACHE_LOCK:
        item = _CACHE.get(key)
        if not item:
            return None
        if time.time() - item["t"] > _CACHE_TTL:
            _CACHE.pop(key, None)
            return None
        return item["v"]

def _set_cache(key: str, value: str):
    with _CACHE_LOCK:
        if len(_CACHE) >= _CACHE_MAX:
            for k, _ in sorted(_CACHE.items(), key=lambda x: x[1]["t"])[:20]:
                _CACHE.pop(k, None)
        _CACHE[key] = {"v": value, "t": time.time()}


# ─────────────────────────────────────────────
# VOICE PREFS
# ─────────────────────────────────────────────

def _voice_on(chat_id: int) -> bool:
    with _VOICE_LOCK:
        return _VOICE_PREFS.get(chat_id, True)  # default ON

def _set_voice(chat_id: int, enabled: bool):
    with _VOICE_LOCK:
        _VOICE_PREFS[chat_id] = enabled


# ─────────────────────────────────────────────
# STT — Groq Whisper
# ─────────────────────────────────────────────

async def _download_tg_file(bot: Bot, file_id: str) -> Optional[bytes]:
    try:
        tg_file = await bot.get_file(file_id)
        buf = io.BytesIO()
        await tg_file.download_to_memory(buf)
        buf.seek(0)
        return buf.read()
    except Exception as e:
        print(f"[STT] Download error: {e}")
        return None


async def transcribe(bot: Bot, voice) -> Optional[str]:
    """Download Telegram voice OGG → Groq Whisper → transcript string."""
    if not groq_client:
        return None
    if voice.duration > 300:
        return None

    audio_bytes = await _download_tg_file(bot, voice.file_id)
    if not audio_bytes:
        return None

    try:
        buf = io.BytesIO(audio_bytes)
        buf.name = "voice.ogg"
        result = groq_client.audio.transcriptions.create(
            model="whisper-large-v3",
            file=buf,
            response_format="text",
        )
        text = result.strip() if isinstance(result, str) else (result.text or "").strip()
        print(f"[STT] {text[:80]}")
        return text or None
    except Exception as e:
        print(f"[STT] Whisper error: {e}")
        return None


# ─────────────────────────────────────────────
# TTS — gTTS → OGG Opus
# ─────────────────────────────────────────────

def _tts(text: str) -> Optional[bytes]:
    """
    Text → OGG Opus bytes for Telegram voice notes.
    Returns None (silently) if gTTS/pydub/ffmpeg unavailable.
    """
    try:
        from gtts import gTTS
        import pydub

        clean = re.sub(r"[*_`#~\[\]()]", "", text)
        clean = re.sub(r"\s+", " ", clean).strip()
        if len(clean) > 500:
            clean = clean[:497] + "..."

        mp3 = io.BytesIO()
        gTTS(text=clean, lang="en", slow=False).write_to_fp(mp3)
        mp3.seek(0)

        audio = pydub.AudioSegment.from_mp3(mp3)
        ogg   = io.BytesIO()
        audio.export(ogg, format="ogg", codec="libopus",
                     parameters=["-vbr", "on", "-compression_level", "10"])
        ogg.seek(0)
        return ogg.read()

    except ImportError as e:
        print(f"[TTS] Missing lib ({e}) — text-only")
        return None
    except Exception as e:
        print(f"[TTS] Error: {e}")
        return None


# ─────────────────────────────────────────────
# LLM
# ─────────────────────────────────────────────

def _llm_reply(text: str) -> str:
    if not groq_client:
        return "❌ Groq API key not set."

    cached = _get_cache(text)
    if cached:
        return cached

    history       = get_conversation_history(limit=10)
    system_prompt = build_system_prompt(query=text)
    messages: list = [{"role": "system", "content": system_prompt}]
    for role, content, _ in history[-10:]:
        if role in ("user", "assistant"):
            messages.append({"role": role, "content": (content or "")[:500]})
    messages.append({"role": "user", "content": text})

    response = groq_client.chat.completions.create(
        model=GROQ_MODEL_PRIMARY or "llama-3.3-70b-versatile",
        messages=messages,  # type: ignore
        max_tokens=500,
        temperature=0.4,
    )
    reply = (response.choices[0].message.content or "").strip() or "No response."
    _set_cache(text, reply)
    save_conversation("user",      text[:500])
    save_conversation("assistant", reply[:500])
    return reply


# ─────────────────────────────────────────────
# DELIVER — text always, voice if prefs allow
# ─────────────────────────────────────────────

async def _deliver(update: Update, reply: str, with_voice: bool = False):
    await update.message.reply_text(reply)

    if with_voice and _voice_on(update.effective_chat.id):
        await update.effective_chat.send_action(ChatAction.RECORD_VOICE)
        audio = await asyncio.get_event_loop().run_in_executor(None, _tts, reply)
        if audio:
            await update.message.reply_voice(voice=audio)


# ─────────────────────────────────────────────
# PUBLIC NOTIFY (used by proactive_engine etc.)
# ─────────────────────────────────────────────

_bot_instance: Optional[Bot] = None

def set_bot(bot: Bot):
    global _bot_instance
    _bot_instance = bot

def notify(text: str, is_alert: bool = False):
    """Push a message to owner's Telegram from non-async context."""
    if not _bot_instance or not ALLOWED_CHAT:
        return
    prefix  = "🚨 " if is_alert else "📢 "
    payload = f"{prefix}{text}"[:4096]
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(_bot_instance.send_message(ALLOWED_CHAT, payload))
        else:
            loop.run_until_complete(_bot_instance.send_message(ALLOWED_CHAT, payload))
    except Exception as e:
        print(f"[NOTIFY] {e}")


# ─────────────────────────────────────────────
# COMMAND HANDLERS
# ─────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update.effective_chat.id): return
    await update.message.reply_text("🤖 ORA online. /help for commands.")

async def cmd_ping(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update.effective_chat.id): return
    await update.message.reply_text("🏓 pong!")

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update.effective_chat.id): return
    await update.message.reply_text(
        "🤖 *ORA Commands*\n\n"
        "*Tasks:*\n/tasks — pending tasks\n/done <id> — mark complete\n\n"
        "*Goals & Finance:*\n/goals — active goals\n/mpesa — M-Pesa summary\n/brief — full brief\n\n"
        "*Inbox:*\n/inbox — Gmail status\n/replies — smart replies\n/proactive — active signals\n\n"
        "*Voice:*\n/voice on — ORA replies with voice + text\n/voice off — text only\n"
        "🎤 Send a voice note anytime\n\n"
        "*Utility:*\n/ping — health\n/stats — stats\n/help — this menu\n\n"
        "Or just *type or speak* anything.",
        parse_mode=ParseMode.MARKDOWN,
    )

async def cmd_voice(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update.effective_chat.id): return
    arg = " ".join(ctx.args or []).lower()
    if arg == "on":
        _set_voice(update.effective_chat.id, True)
        await update.message.reply_text("🔊 Voice replies ON.")
    elif arg == "off":
        _set_voice(update.effective_chat.id, False)
        await update.message.reply_text("🔇 Voice replies OFF — text only.")
    else:
        status = "ON 🔊" if _voice_on(update.effective_chat.id) else "OFF 🔇"
        await update.message.reply_text(
            f"Voice replies: *{status}*\n\nUse `/voice on` or `/voice off`",
            parse_mode=ParseMode.MARKDOWN,
        )

async def cmd_tasks(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update.effective_chat.id): return
    try:
        from database import get_tasks
        tasks = get_tasks("pending")
        if not tasks:
            await update.message.reply_text("📋 No pending tasks. 🎉")
            return
        lines = [f"📋 *Pending Tasks* ({len(tasks)})"]
        for t in tasks[:10]:
            tid, title, priority, _, due = t[:5]
            emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(priority, "⚪")
            due_s = f" _(due {due[:10]})_" if due else ""
            lines.append(f"{emoji} *{title[:55]}* — #{tid}{due_s}")
        if len(tasks) > 10:
            lines.append(f"_...and {len(tasks)-10} more_")
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")

async def cmd_done(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update.effective_chat.id): return
    arg = " ".join(ctx.args or "")
    try:
        task_id = int(arg.strip())
    except ValueError:
        await update.message.reply_text("Usage: `/done <id>`", parse_mode=ParseMode.MARKDOWN)
        return
    try:
        from database import complete_task, get_tasks
        if not any(t[0] == task_id for t in get_tasks("all")):
            await update.message.reply_text(f"❌ Task #{task_id} not found.")
            return
        complete_task(task_id)
        await update.message.reply_text(f"✅ Task #{task_id} done! 🎉")
        pending = get_tasks("pending")
        if pending:
            await update.message.reply_text(f"💡 Next: #{pending[0][0]} — {pending[0][1][:50]}")
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")

async def cmd_goals(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update.effective_chat.id): return
    try:
        from intelligence.goals_engine import get_goals
        goals = get_goals("active")
        if not goals:
            await update.message.reply_text("🎯 No active goals.")
            return
        lines = [f"🎯 *Active Goals* ({len(goals)})"]
        for g in goals[:7]:
            name     = g.get("goal", "Untitled")[:55]
            progress = g.get("progress", 0)
            filled   = int(10 * progress / 100)
            bar      = "█" * filled + "░" * (10 - filled)
            due_s    = f" _due {g['due_at'][:10]}_" if g.get("due_at") else ""
            lines.append(f"• {name}\n  `{bar}` {progress}%{due_s}")
        await update.message.reply_text("\n\n".join(lines), parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")

async def cmd_mpesa(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update.effective_chat.id): return
    try:
        from mpesa_engine import get_today_spend, get_average_daily_spend
        today = get_today_spend()
        avg   = get_average_daily_spend()
        total = today.get("total", 0) if isinstance(today, dict) else 0
        txns  = today.get("transactions", 0) if isinstance(today, dict) else 0
        trend = "📈 above avg" if total > avg * 1.3 else ("📉 below avg" if total < avg * 0.7 else "📊 normal")
        await update.message.reply_text(
            f"💳 *M-Pesa Summary*\n\nToday: KES {total:,.0f} ({txns} txns)\nDaily avg: KES {avg:,.0f} — {trend}",
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")

async def cmd_brief(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update.effective_chat.id): return
    await update.effective_chat.send_action(ChatAction.TYPING)
    try:
        from briefing import generate_briefing
        briefing = generate_briefing()
        for i, chunk in enumerate([briefing[j:j+4000] for j in range(0, len(briefing), 4000)]):
            await update.message.reply_text(chunk, parse_mode=ParseMode.MARKDOWN)
            if i > 0:
                await asyncio.sleep(0.4)
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")

async def cmd_inbox(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update.effective_chat.id): return
    try:
        from connectors.gmail import get_gmail_summary, get_reply_stats
        summary = get_gmail_summary()
        if not summary.get("authorized"):
            await update.message.reply_text("📭 Gmail not connected. Visit ORA → Settings → Connect Google.")
            return
        stats   = get_reply_stats()
        await update.message.reply_text(
            f"📬 *Gmail Status*\n\nUnread: {summary.get('unread_count', 0)}\n"
            f"Smart replies pending: {stats.get('pending', 0)}\n\nUse /replies to review.",
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")

async def cmd_replies(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update.effective_chat.id): return
    try:
        from connectors.gmail import get_pending_replies
        pending = get_pending_replies(limit=5)
        if not pending:
            await update.message.reply_text("✅ No pending reply suggestions.")
            return
        lines = [f"📧 *{len(pending)} pending reply suggestion(s):*\n"]
        for r in pending:
            subj    = (r.get("subject") or "(no subject)")[:45]
            sndr    = (r.get("sender") or "")[:35]
            preview = (r.get("suggested_text") or "")[:80]
            lines.append(f"*#{r.get('id')}* — {subj}\nFrom: _{sndr}_\nDraft: _{preview}_...\n")
        lines.append("Open ORA → Inbox → Smart Replies to approve/edit.")
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")

async def cmd_proactive(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update.effective_chat.id): return
    try:
        from database import get_tasks, get_conn, close_conn
        now     = datetime.now()
        pending = get_tasks("pending")
        overdue = [t for t in pending if t[4] and datetime.fromisoformat(t[4]) < now]
        high    = [t for t in pending if t[2] == "high"]
        conn    = get_conn()
        old_r   = conn.execute(
            "SELECT COUNT(*) FROM suggested_replies WHERE status='pending' AND created_at < datetime('now','-24 hours')"
        ).fetchone()[0]
        close_conn()
        lines = ["🔔 *Proactive Signal Status*\n",
                 f"{'🔴' if overdue else '✅'} Overdue tasks: {len(overdue)}",
                 f"{'🟡' if len(high) >= 2 else '✅'} High-priority open: {len(high)}",
                 f"{'🟡' if old_r else '✅'} Unanswered emails (>24h): {old_r}",
                 "\n_Next proactive check runs in background._"]
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")

async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update.effective_chat.id): return
    try:
        from database import get_conversation_history, get_tasks
        conv  = len(get_conversation_history(limit=10000)) // 2
        tasks = len(get_tasks("all"))
        h, m  = divmod(int(time.time() - _start_time) // 60, 60)
        await update.message.reply_text(
            f"📊 *ORA Stats*\n\nConversations: {conv}\nTasks: {tasks}\n"
            f"Cache: {len(_CACHE)}\nUptime: {f'{h}h {m}m' if h else f'{m}m'}",
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")


# ─────────────────────────────────────────────
# MESSAGE HANDLERS
# ─────────────────────────────────────────────

async def on_voice(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Voice note → Whisper STT → LLM → text + optional voice reply."""
    chat_id = update.effective_chat.id
    if not _allowed(chat_id): return
    if not _rate_ok(chat_id):
        await update.message.reply_text("⏳ Rate limit — wait a moment.")
        return

    await update.effective_chat.send_action(ChatAction.TYPING)
    transcript = await transcribe(ctx.bot, update.message.voice)

    if not transcript:
        await update.message.reply_text("❌ Couldn't transcribe audio. Try again or type your message.")
        return

    # Echo what was heard
    await update.message.reply_text(f"🎤 _{transcript}_", parse_mode=ParseMode.MARKDOWN)

    try:
        reply = await asyncio.get_event_loop().run_in_executor(None, _llm_reply, transcript)
        await _deliver(update, reply, with_voice=True)
    except Exception as e:
        await update.message.reply_text(f"❌ ORA error: {str(e)[:100]}")
        print(f"[VOICE HANDLER]\n{traceback.format_exc()}")


async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Plain text → LLM → text (+ voice if prefs on)."""
    chat_id = update.effective_chat.id
    if not _allowed(chat_id): return

    text = (update.message.text or "").strip()
    if not text: return

    if not _rate_ok(chat_id):
        await update.message.reply_text("⏳ Rate limit — wait a moment.")
        return

    await update.effective_chat.send_action(ChatAction.TYPING)
    try:
        reply = await asyncio.get_event_loop().run_in_executor(None, _llm_reply, text)
        await _deliver(update, reply, with_voice=_voice_on(chat_id))
    except Exception as e:
        await update.message.reply_text(f"❌ ORA error: {str(e)[:100]}")
        print(f"[TEXT HANDLER]\n{traceback.format_exc()}")


# ─────────────────────────────────────────────
# APP BUILDER
# ─────────────────────────────────────────────

def build_app() -> Application:
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("ping",      cmd_ping))
    app.add_handler(CommandHandler("help",      cmd_help))
    app.add_handler(CommandHandler("voice",     cmd_voice))
    app.add_handler(CommandHandler("tasks",     cmd_tasks))
    app.add_handler(CommandHandler("done",      cmd_done))
    app.add_handler(CommandHandler("goals",     cmd_goals))
    app.add_handler(CommandHandler("mpesa",     cmd_mpesa))
    app.add_handler(CommandHandler("brief",     cmd_brief))
    app.add_handler(CommandHandler("inbox",     cmd_inbox))
    app.add_handler(CommandHandler("replies",   cmd_replies))
    app.add_handler(CommandHandler("proactive", cmd_proactive))
    app.add_handler(CommandHandler("stats",     cmd_stats))

    app.add_handler(MessageHandler(filters.VOICE, on_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    return app


# ─────────────────────────────────────────────
# ENTRY POINTS
# ─────────────────────────────────────────────

def run_telegram_bot():
    """
    Blocking entry point — called from api.py lifespan in a daemon thread.
    Runs PTB's own event loop internally via run_polling().
    """
    if not TELEGRAM_BOT_TOKEN:
        print("[TELEGRAM] No token — bot disabled")
        return

    print("[TELEGRAM] Starting PTB async polling")
    app = build_app()
    set_bot(app.bot)
    app.run_polling(
        allowed_updates=["message"],
        drop_pending_updates=True,   # ignore backlog on restart
        close_loop=False,            # don't kill the outer loop
    )


async def run_telegram_bot_async():
    """
    Async entry point — use this if api.py lifespan is already async.
    await run_telegram_bot_async() inside your lifespan.
    """
    if not TELEGRAM_BOT_TOKEN:
        print("[TELEGRAM] No token — bot disabled")
        return

    print("[TELEGRAM] Starting PTB async polling (async mode)")
    app = build_app()
    set_bot(app.bot)
    await app.initialize()
    await app.start()
    await app.updater.start_polling(
        allowed_updates=["message"],
        drop_pending_updates=True,
    )
    try:
        await asyncio.Event().wait()   # run until cancelled
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()


if __name__ == "__main__":
    run_telegram_bot()