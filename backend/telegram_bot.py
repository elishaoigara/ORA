"""
ORA Telegram Bot — raw requests polling
Features: voice in/out, browse, email, calendar, WhatsApp v2, weather
"""

import io
import re
import time
import traceback
import requests
from collections import defaultdict
from datetime import datetime
from threading import Lock
from typing import Optional, Dict, Any, List

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, GROQ_API_KEY, GROQ_MODEL_PRIMARY
from database import save_conversation, get_conversation_history
from context import build_system_prompt
from groq import Groq

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

TELEGRAM_ENABLED = bool(TELEGRAM_BOT_TOKEN)
BASE             = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}" if TELEGRAM_ENABLED else None
groq_client      = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
ALLOWED_CHAT_ID  = int(TELEGRAM_CHAT_ID) if TELEGRAM_CHAT_ID else None

_RATE        = defaultdict(list)
RATE_WINDOW  = 60
RATE_MAX     = 20
_CACHE:      Dict[str, Dict[str, Any]] = {}
_CACHE_LOCK  = Lock()
_CACHE_TTL   = 180
_CACHE_MAX   = 100
_VOICE_PREFS: Dict[int, bool] = {}
_VOICE_LOCK   = Lock()
_start_time = time.time()

print(f"[TELEGRAM] token={'set' if TELEGRAM_BOT_TOKEN else 'MISSING'} allowed={ALLOWED_CHAT_ID}")


# ─────────────────────────────────────────────
# GUARDS / CACHE / PREFS
# ─────────────────────────────────────────────

def _allowed(chat_id):
    return ALLOWED_CHAT_ID is None or chat_id == ALLOWED_CHAT_ID

def _rate_ok(chat_id):
    now = time.time()
    _RATE[chat_id] = [t for t in _RATE[chat_id] if t > now - RATE_WINDOW]
    if len(_RATE[chat_id]) >= RATE_MAX: return False
    _RATE[chat_id].append(now); return True

def _get_cache(key):
    with _CACHE_LOCK:
        item = _CACHE.get(key)
        if not item: return None
        if time.time() - item["t"] > _CACHE_TTL: _CACHE.pop(key, None); return None
        return item["v"]

def _set_cache(key, value):
    with _CACHE_LOCK:
        if len(_CACHE) >= _CACHE_MAX:
            for k, _ in sorted(_CACHE.items(), key=lambda x: x[1]["t"])[:20]: _CACHE.pop(k, None)
        _CACHE[key] = {"v": value, "t": time.time()}

def _voice_on(chat_id):
    with _VOICE_LOCK: return _VOICE_PREFS.get(chat_id, True)

def _set_voice(chat_id, enabled):
    with _VOICE_LOCK: _VOICE_PREFS[chat_id] = enabled


# ─────────────────────────────────────────────
# RAW TELEGRAM HELPERS
# ─────────────────────────────────────────────

def _tg_post(endpoint, **kwargs):
    if not BASE: return None
    try:
        r = requests.post(f"{BASE}/{endpoint}", **kwargs)
        data = r.json()
        if not data.get("ok"): print(f"[TG {endpoint}] {data.get('description')}"); return None
        return data.get("result")
    except Exception as e:
        print(f"[TG {endpoint}] {e}"); return None

def tg_send(chat_id, text, parse_mode=None, reply_to_message_id=None):
    payload = {"chat_id": chat_id, "text": text[:4000]}
    if parse_mode:           payload["parse_mode"] = parse_mode
    if reply_to_message_id: payload["reply_to_message_id"] = reply_to_message_id
    for _ in range(2):
        result = _tg_post("sendMessage", json=payload, timeout=15)
        if result: return result.get("message_id")
        time.sleep(1)
    return None

def _tg_action(chat_id, action="typing"):
    if not BASE: return
    try: requests.post(f"{BASE}/sendChatAction", json={"chat_id": chat_id, "action": action}, timeout=5)
    except: pass

def _tg_send_voice(chat_id, audio, reply_to=None):
    data = {"chat_id": chat_id}
    if reply_to: data["reply_to_message_id"] = reply_to
    _tg_post("sendVoice", data=data, files={"voice": ("voice.ogg", audio, "audio/ogg")}, timeout=30)

def _tg_get_updates(offset, timeout=25):
    if not BASE: return []
    try:
        params = {"timeout": timeout}
        if offset is not None: params["offset"] = offset
        r = requests.get(f"{BASE}/getUpdates", params=params, timeout=timeout+5)
        data = r.json()
        if not data.get("ok"):
            if "Conflict" not in data.get("description",""): print(f"[TG POLL] {data.get('description')}")
            return []
        return data.get("result", [])
    except Exception as e:
        print(f"[TG POLL] {e}"); return []

def _tg_download_file(file_id):
    try:
        r = requests.get(f"{BASE}/getFile", params={"file_id": file_id}, timeout=10)
        path = r.json()["result"]["file_path"]
        return requests.get(f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{path}", timeout=30).content
    except Exception as e:
        print(f"[TG DL] {e}"); return None


# ─────────────────────────────────────────────
# PUBLIC NOTIFY
# ─────────────────────────────────────────────

def notify(text, is_alert=False):
    if not TELEGRAM_ENABLED or not ALLOWED_CHAT_ID: return
    prefix = "🚨 " if is_alert else "📢 "
    msg    = f"{prefix}{text}"
    for chunk in [msg[i:i+4000] for i in range(0, len(msg), 4000)]:
        tg_send(ALLOWED_CHAT_ID, chunk)
        if len(msg) > 4000: time.sleep(0.4)


# ─────────────────────────────────────────────
# STT / TTS
# ─────────────────────────────────────────────

def _transcribe(file_id, duration=0):
    if not groq_client or duration > 300: return None
    audio = _tg_download_file(file_id)
    if not audio: return None
    try:
        buf = io.BytesIO(audio); buf.name = "voice.ogg"
        result = groq_client.audio.transcriptions.create(model="whisper-large-v3", file=buf, response_format="text")
        text = result.strip() if isinstance(result, str) else (result.text or "").strip()
        print(f"[STT] {text[:80]}"); return text or None
    except Exception as e:
        print(f"[STT] {e}"); return None

def _tts(text):
    try:
        from gtts import gTTS
        import pydub
        clean = re.sub(r"[*_`#~\[\]()]", "", text)
        clean = re.sub(r"\s+", " ", clean).strip()[:500]
        mp3 = io.BytesIO(); gTTS(text=clean, lang="en", slow=False).write_to_fp(mp3); mp3.seek(0)
        ogg = io.BytesIO()
        pydub.AudioSegment.from_mp3(mp3).export(ogg, format="ogg", codec="libopus", parameters=["-vbr","on"])
        ogg.seek(0); return ogg.read()
    except ImportError: return None
    except Exception as e: print(f"[TTS] {e}"); return None


# ─────────────────────────────────────────────
# LLM
# ─────────────────────────────────────────────

def _llm_reply(text):
    if not groq_client: return "❌ Groq API key not set."
    cached = _get_cache(text)
    if cached: return cached
    try:
        history = get_conversation_history(limit=10)
        msgs = [{"role":"system","content":build_system_prompt(query=text)}]
        for role, content, _ in history[-10:]:
            if role in ("user","assistant"): msgs.append({"role":role,"content":(content or "")[:500]})
        msgs.append({"role":"user","content":text})
        resp = groq_client.chat.completions.create(
            model=GROQ_MODEL_PRIMARY or "llama-3.3-70b-versatile",
            messages=msgs, max_tokens=500, temperature=0.4) # pyright: ignore[reportArgumentType]
        reply = (resp.choices[0].message.content or "").strip() or "No response."
        _set_cache(text, reply)
        save_conversation("user", text[:500]); save_conversation("assistant", reply[:500])
        return reply
    except Exception as e:
        print(f"[LLM] {e}\n{traceback.format_exc()}"); return f"❌ ORA error: {str(e)[:100]}"

def _deliver(chat_id, reply, reply_to, with_voice):
    tg_send(chat_id, reply, reply_to_message_id=reply_to)
    if with_voice and _voice_on(chat_id):
        _tg_action(chat_id, "record_voice")
        audio = _tts(reply)
        if audio: _tg_send_voice(chat_id, audio, reply_to)


# ─────────────────────────────────────────────
# COMMANDS
# ─────────────────────────────────────────────

def _cmd_help(chat_id, reply_to=None):
    tg_send(chat_id, (
        "🤖 *ORA Commands*\n\n"
        "*Tasks:*\n/tasks — pending tasks\n/done <id> — mark complete\n\n"
        "*Goals & Finance:*\n/goals — active goals\n/mpesa — M-Pesa summary\n/brief — full brief\n\n"
        "*Inbox:*\n/inbox — Gmail status\n/replies — smart replies\n/proactive — signals\n\n"
        "*WhatsApp:*\n"
        "`/wa` — status\n"
        "`/wa messages` — recent DMs\n"
        "`/wa unread` — unread only\n"
        "`/wa search <keyword>` — search messages\n"
        "`/wa send <name> | <msg>` — send message\n"
        "`/wa reply <name> | <msg>` — ORA drafts reply\n"
        "`/wa groups` — list groups\n"
        "`/wa mute <group name>` — mute group alerts\n"
        "`/wa unmute <group name>` — unmute group\n"
        "`/wa summarise` — summarise unread\n\n"
        "*Calendar:*\n"
        "`/cal` — today\n`/cal week` — this week\n"
        "`/cal add <event>` — create\n`/cal free [day]` — free slots\n"
        "`/cal cancel <name>` — delete\n\n"
        "*Browse:*\n`/browse <url> [question]`\n\n"
        "*Email:*\n`/email to | subject | body`\n`/draft to | subject | body`\n\n"
        "*Voice:*\n/voice on|off — toggle voice replies\n🎤 Send voice note anytime\n\n"
        "*Utility:*\n/weather /ping /stats /help"
    ), "Markdown", reply_to)

def _cmd_tasks(chat_id, reply_to=None):
    try:
        from database import get_tasks
        tasks = get_tasks("pending")
        if not tasks: tg_send(chat_id, "📋 No pending tasks. 🎉", reply_to_message_id=reply_to); return
        lines = [f"📋 *Pending Tasks* ({len(tasks)})"]
        for t in tasks[:10]:
            tid, title, priority, _, due = t[:5]
            emoji = {"high":"🔴","medium":"🟡","low":"🟢"}.get(priority,"⚪")
            due_s = f" _(due {due[:10]})_" if due else ""
            lines.append(f"{emoji} *{title[:55]}* — #{tid}{due_s}")
        if len(tasks) > 10: lines.append(f"_...and {len(tasks)-10} more_")
        tg_send(chat_id, "\n".join(lines), "Markdown", reply_to)
    except Exception as e: tg_send(chat_id, f"❌ {e}", reply_to_message_id=reply_to)

def _cmd_done(chat_id, arg, reply_to=None):
    try: task_id = int(arg.strip())
    except ValueError: tg_send(chat_id, "Usage: `/done <id>`", "Markdown", reply_to); return
    try:
        from database import complete_task, get_tasks
        if not any(t[0] == task_id for t in get_tasks("all")):
            tg_send(chat_id, f"❌ Task #{task_id} not found.", reply_to_message_id=reply_to); return
        complete_task(task_id)
        pending = get_tasks("pending")
        extra = f"\n💡 Next: #{pending[0][0]} — {pending[0][1][:50]}" if pending else ""
        tg_send(chat_id, f"✅ Task #{task_id} done! 🎉{extra}", reply_to_message_id=reply_to)
    except Exception as e: tg_send(chat_id, f"❌ {e}", reply_to_message_id=reply_to)

def _cmd_goals(chat_id, reply_to=None):
    try:
        from intelligence.goals_engine import get_goals
        goals = get_goals("active")
        if not goals: tg_send(chat_id, "🎯 No active goals.", reply_to_message_id=reply_to); return
        lines = [f"🎯 *Active Goals* ({len(goals)})"]
        for g in goals[:7]:
            name = g.get("goal","Untitled")[:55]; progress = g.get("progress",0)
            bar  = "█"*int(10*progress/100) + "░"*(10-int(10*progress/100))
            due_s = f" _due {g['due_at'][:10]}_" if g.get("due_at") else ""
            lines.append(f"• {name}\n  `{bar}` {progress}%{due_s}")
        tg_send(chat_id, "\n\n".join(lines), "Markdown", reply_to)
    except Exception as e: tg_send(chat_id, f"❌ {e}", reply_to_message_id=reply_to)

def _cmd_mpesa(chat_id, reply_to=None):
    try:
        from mpesa_engine import get_today_spend, get_average_daily_spend
        today = get_today_spend(); avg = get_average_daily_spend()
        total = today.get("total",0) if isinstance(today,dict) else 0
        txns  = today.get("transactions",0) if isinstance(today,dict) else 0
        trend = "📈 above avg" if total > avg*1.3 else ("📉 below avg" if total < avg*0.7 else "📊 normal")
        tg_send(chat_id, f"💳 *M-Pesa Summary*\n\nToday: KES {total:,.0f} ({txns} txns)\nDaily avg: KES {avg:,.0f} — {trend}", "Markdown", reply_to)
    except Exception as e: tg_send(chat_id, f"❌ {e}", reply_to_message_id=reply_to)

def _cmd_brief(chat_id, reply_to=None):
    _tg_action(chat_id)
    try:
        from briefing import generate_briefing
        briefing = generate_briefing()
        for i, chunk in enumerate([briefing[j:j+4000] for j in range(0,len(briefing),4000)]):
            tg_send(chat_id, chunk, "Markdown", reply_to if i==0 else None)
            if i > 0: time.sleep(0.4)
    except Exception as e: tg_send(chat_id, f"❌ {e}", reply_to_message_id=reply_to)

def _cmd_inbox(chat_id, reply_to=None):
    try:
        from connectors.gmail import get_gmail_summary, get_reply_stats
        summary = get_gmail_summary()
        if not summary.get("authorized"):
            tg_send(chat_id, "📭 Gmail not connected. Visit ORA → Settings → Connect Google.", reply_to_message_id=reply_to); return
        stats = get_reply_stats()
        tg_send(chat_id, f"📬 *Gmail Status*\n\nUnread: {summary.get('unread_count',0)}\nSmart replies pending: {stats.get('pending',0)}\n\nUse /replies to review.", "Markdown", reply_to)
    except Exception as e: tg_send(chat_id, f"❌ {e}", reply_to_message_id=reply_to)

def _cmd_replies(chat_id, reply_to=None):
    try:
        from connectors.gmail import get_pending_replies
        pending = get_pending_replies(limit=5)
        if not pending: tg_send(chat_id, "✅ No pending reply suggestions.", reply_to_message_id=reply_to); return
        lines = [f"📧 *{len(pending)} pending reply suggestion(s):*\n"]
        for r in pending:
            lines.append(f"*#{r.get('id')}* — {(r.get('subject') or '(no subject)')[:45]}\nFrom: _{(r.get('sender') or '')[:35]}_\nDraft: _{(r.get('suggested_text') or '')[:80]}_...\n")
        lines.append("Open ORA → Inbox → Smart Replies to approve/edit.")
        tg_send(chat_id, "\n".join(lines), "Markdown", reply_to)
    except Exception as e: tg_send(chat_id, f"❌ {e}", reply_to_message_id=reply_to)

def _cmd_proactive(chat_id, reply_to=None):
    try:
        from database import get_tasks, get_conn, close_conn
        now = datetime.now(); pending = get_tasks("pending")
        overdue = [t for t in pending if t[4] and datetime.fromisoformat(t[4]) < now]
        high    = [t for t in pending if t[2] == "high"]
        conn    = get_conn()
        old_r   = conn.execute("SELECT COUNT(*) FROM suggested_replies WHERE status='pending' AND created_at < datetime('now','-24 hours')").fetchone()[0]; close_conn()
        tg_send(chat_id, "\n".join(["🔔 *Proactive Signal Status*\n",
            f"{'🔴' if overdue else '✅'} Overdue tasks: {len(overdue)}",
            f"{'🟡' if len(high)>=2 else '✅'} High-priority open: {len(high)}",
            f"{'🟡' if old_r else '✅'} Unanswered emails (>24h): {old_r}",
            "\n_Next check runs in background._"]), "Markdown", reply_to)
    except Exception as e: tg_send(chat_id, f"❌ {e}", reply_to_message_id=reply_to)

def _cmd_stats(chat_id, reply_to=None):
    try:
        from database import get_conversation_history, get_tasks
        conv = len(get_conversation_history(limit=10000))//2; tasks = len(get_tasks("all"))
        h, m = divmod(int(time.time()-_start_time)//60, 60)
        tg_send(chat_id, f"📊 *ORA Stats*\n\nConversations: {conv}\nTasks: {tasks}\nCache: {len(_CACHE)}\nUptime: {f'{h}h {m}m' if h else f'{m}m'}", "Markdown", reply_to)
    except Exception as e: tg_send(chat_id, f"❌ {e}", reply_to_message_id=reply_to)

def _cmd_voice(chat_id, arg, reply_to=None):
    arg = arg.strip().lower()
    if arg == "on": _set_voice(chat_id, True); tg_send(chat_id, "🔊 Voice replies ON.", reply_to_message_id=reply_to)
    elif arg == "off": _set_voice(chat_id, False); tg_send(chat_id, "🔇 Voice replies OFF.", reply_to_message_id=reply_to)
    else:
        status = "ON 🔊" if _voice_on(chat_id) else "OFF 🔇"
        tg_send(chat_id, f"Voice replies: *{status}*\n\n`/voice on` or `/voice off`", "Markdown", reply_to)

def _cmd_weather(chat_id, reply_to=None):
    _tg_action(chat_id)
    try:
        from connectors.weather import get_weather_detail # type: ignore
        tg_send(chat_id, get_weather_detail(), "Markdown", reply_to)
    except Exception as e: tg_send(chat_id, f"❌ {e}", reply_to_message_id=reply_to)

def _cmd_browse(chat_id, arg, reply_to=None):
    arg = arg.strip()
    if not arg:
        tg_send(chat_id, "🌐 Usage: `/browse <url> [question]`", "Markdown", reply_to); return
    parts = arg.split(None, 1)
    url = parts[0]; question = parts[1].strip() if len(parts) > 1 else None
    tg_send(chat_id, f"🌐 Fetching _{url}_...", "Markdown", reply_to)
    _tg_action(chat_id)
    try:
        from connectors.browse import browse
        result = browse(url, question=question)
    except Exception as e:
        tg_send(chat_id, f"❌ Browse error: {str(e)[:200]}", reply_to_message_id=reply_to)
        print(f"[BROWSE CMD] {traceback.format_exc()}"); return
    if not result.get("ok"): tg_send(chat_id, f"❌ {result.get('error','Could not load page')}", reply_to_message_id=reply_to); return
    title = result.get("title", url); summary = result.get("summary",""); raw_len = result.get("raw_length",0)
    icon = {"pdf":"📄","youtube":"🎥","html":"🌐"}.get(result.get("type","html"),"🌐")
    header = f"{icon} *{title}*\n_{url}_\n\n"; footer = f"\n\n_({raw_len:,} chars read)_"
    body = f"*Q: {question}*\n\n{summary}" if question else summary
    full = header + body + footer
    for i, chunk in enumerate([full[j:j+4000] for j in range(0,len(full),4000)]):
        tg_send(chat_id, chunk, None, reply_to if i==0 else None)
        if i > 0: time.sleep(0.3)

def _cmd_email(chat_id, arg, reply_to=None):
    arg = arg.strip()
    if not arg:
        tg_send(chat_id, "📧 Usage: `/email to@x.com | Subject | Body`", "Markdown", reply_to); return
    parts = [p.strip() for p in arg.split("|")]
    if len(parts) >= 3:
        to, subject, body = parts[0], parts[1], "|".join(parts[2:])
        tg_send(chat_id, f"📤 Sending to *{to}*...", "Markdown", reply_to)
        try:
            from connectors.gmail import send_new_email
            result = send_new_email(to=to, subject=subject, body=body)
            if result.get("ok"): tg_send(chat_id, f"✅ *Email sent!*\n\n*To:* {to}\n*Subject:* {subject}\n_{body[:100]}_", "Markdown", reply_to)
            else: tg_send(chat_id, f"❌ Failed: {result.get('error')}", reply_to_message_id=reply_to)
        except Exception as e: tg_send(chat_id, f"❌ {e}", reply_to_message_id=reply_to)
    else:
        try:
            from Intent_parser import parse_intent, execute_intent
            intent = parse_intent(f"email {arg}") or {"type":"send_email","payload":{"raw":arg,"to":"","subject":"","body":"","needs_llm":True}}
            tg_send(chat_id, "📤 Composing...", reply_to_message_id=reply_to)
            reply_text = execute_intent(intent) or _llm_reply(f"email {arg}")
            tg_send(chat_id, reply_text, "Markdown", reply_to)
        except Exception as e: tg_send(chat_id, f"❌ {e}", reply_to_message_id=reply_to)

def _cmd_draft(chat_id, arg, reply_to=None):
    parts = [p.strip() for p in arg.strip().split("|")]
    if len(parts) >= 3:
        to, subject, body = parts[0], parts[1], "|".join(parts[2:])
        try:
            from connectors.gmail import create_draft
            result = create_draft(to=to, subject=subject, body=body)
            if result.get("ok"): tg_send(chat_id, f"📝 *Draft saved!*\n\n*To:* {to}\n*Subject:* {subject}\n_Open Gmail to send._", "Markdown", reply_to)
            else: tg_send(chat_id, f"❌ {result.get('error')}", reply_to_message_id=reply_to)
        except Exception as e: tg_send(chat_id, f"❌ {e}", reply_to_message_id=reply_to)
    else: tg_send(chat_id, "Usage: `/draft to@x.com | Subject | Body`", "Markdown", reply_to)

def _cmd_cal(chat_id, arg, reply_to=None):
    arg = arg.strip(); lower = arg.lower()
    if not arg or lower == "today":
        try:
            from connectors.calendar import get_events_today, format_events_for_context
            events = get_events_today()
            tg_send(chat_id, f"📅 *Today's schedule:*\n\n{format_events_for_context(events)}" if events else "📅 Nothing on the calendar today.", "Markdown", reply_to)
        except Exception as e: tg_send(chat_id, f"❌ {e}", reply_to_message_id=reply_to)
        return
    if lower == "week":
        try:
            from connectors.calendar import get_events_this_week, format_events_for_context
            events = get_events_this_week()
            tg_send(chat_id, f"📅 *This week:*\n\n{format_events_for_context(events)}" if events else "📅 Nothing this week.", "Markdown", reply_to)
        except Exception as e: tg_send(chat_id, f"❌ {e}", reply_to_message_id=reply_to)
        return
    if lower.startswith(("add ","schedule ","create ")):
        text = re.sub(r"^(add|schedule|create)\s+", "", arg, flags=re.I)
        tg_send(chat_id, "📅 Creating event...", reply_to_message_id=reply_to)
        try:
            from connectors.calendar import quick_event
            result = quick_event(text)
            if result.get("ok"):
                ev = result["event"]; loc_s = f"\n📍 {ev.get('location')}" if ev.get("location") else ""
                tg_send(chat_id, f"✅ *Event created!*\n\n📅 *{ev.get('title','Event')}*\n🕐 {ev.get('start','')} → {ev.get('end','')}{loc_s}", "Markdown", reply_to)
            else: tg_send(chat_id, f"❌ {result.get('error')}", reply_to_message_id=reply_to)
        except Exception as e: tg_send(chat_id, f"❌ {e}", reply_to_message_id=reply_to)
        return
    if lower.startswith("free"):
        date_hint = arg[4:].strip() or "today"
        try:
            from Intent_parser import _do_free_slot
            tg_send(chat_id, _do_free_slot({"date_hint": date_hint, "raw": arg}), "Markdown", reply_to)
        except Exception as e: tg_send(chat_id, f"❌ {e}", reply_to_message_id=reply_to)
        return
    if lower.startswith(("cancel ","delete ")):
        text = re.sub(r"^(cancel|delete)\s+", "", arg, flags=re.I)
        tg_send(chat_id, "🗑 Finding event...", reply_to_message_id=reply_to)
        try:
            from Intent_parser import _do_delete_event
            tg_send(chat_id, _do_delete_event({"raw": text}), "Markdown", reply_to)
        except Exception as e: tg_send(chat_id, f"❌ {e}", reply_to_message_id=reply_to)
        return
    # Fallback: treat as quick event
    tg_send(chat_id, "📅 Creating event...", reply_to_message_id=reply_to)
    try:
        from connectors.calendar import quick_event
        result = quick_event(arg)
        if result.get("ok"):
            ev = result["event"]
            tg_send(chat_id, f"✅ *{ev.get('title','Event')}* scheduled for {ev.get('start','')}", "Markdown", reply_to)
        else: tg_send(chat_id, f"❌ {result.get('error')}\n\nTry `/cal` for help.", "Markdown", reply_to)
    except Exception as e: tg_send(chat_id, f"❌ {e}", reply_to_message_id=reply_to)


def _cmd_wa(chat_id, arg, reply_to=None):
    """
    /wa                          — status
    /wa messages [name]          — recent messages
    /wa unread                   — unread DMs
    /wa search <keyword>         — search by keyword
    /wa send <name> | <msg>      — send message
    /wa reply <name> | <tone>    — ORA drafts reply to latest msg from <name>
    /wa groups                   — list groups + mute status
    /wa mute <group name>        — mute group Telegram alerts
    /wa unmute <group name>      — unmute group
    /wa summarise                — AI summary of all unread
    """
    arg   = arg.strip()
    lower = arg.lower()

    try:
        from connectors.whatsapp import (
            get_status, get_messages, send_message, format_messages_summary,
            is_connected, get_groups, mute_group, get_group_jid,
            get_unread_summary, format_unread_summary, draft_reply, summarise_messages
        )
    except Exception as e:
        tg_send(chat_id, f"❌ WhatsApp connector error: {e}", reply_to_message_id=reply_to); return

    # ── Status ─────────────────────────────────
    if not arg or lower == "status":
        status = get_status(); state = status.get("state","unknown")
        icon = {"open":"✅","connecting":"🔄","qr_pending":"📱","disconnected":"❌"}.get(state,"❓")
        tg_send(chat_id, f"{icon} *WhatsApp:* {state}\n_{status.get('msgs',0)} messages in memory_", "Markdown", reply_to)
        return

    # ── Send ───────────────────────────────────
    if lower.startswith("send "):
        parts = [p.strip() for p in arg[5:].split("|", 1)]
        if len(parts) < 2:
            tg_send(chat_id, "Usage: `/wa send <name or number> | <message>`", "Markdown", reply_to); return
        to, message = parts[0], parts[1]
        if not is_connected(): tg_send(chat_id, "❌ WhatsApp not connected.", reply_to_message_id=reply_to); return
        tg_send(chat_id, f"📤 Sending to *{to}*...", "Markdown", reply_to)
        result = send_message(to, message)
        tg_send(chat_id, f"✅ Sent to *{to}*:\n_{message[:100]}_" if result.get("ok") else f"❌ Failed: {result.get('error')}", "Markdown", reply_to)
        return

    # ── Smart reply: draft ──────────────────────
    if lower.startswith("reply "):
        parts = [p.strip() for p in arg[6:].split("|", 1)]
        contact = parts[0]; tone = parts[1] if len(parts) > 1 else "friendly"
        msgs = get_messages(limit=5, contact=contact).get("messages", [])
        if not msgs:
            tg_send(chat_id, f"❌ No messages found from *{contact}*.", "Markdown", reply_to); return
        latest = msgs[0]
        tg_send(chat_id, f"✍️ Drafting reply to *{latest.get('fromName',contact)}*...", "Markdown", reply_to)
        draft = draft_reply(latest, tone=tone)
        if not draft:
            tg_send(chat_id, "❌ Could not draft reply.", reply_to_message_id=reply_to); return
        tg_send(chat_id,
            f"📝 *Draft reply to {latest.get('fromName',contact)}:*\n\n_{draft}_\n\n"
            f"To send: `/wa send {contact} | {draft[:60]}...`",
            "Markdown", reply_to)
        return

    # ── Groups ─────────────────────────────────
    if lower == "groups":
        groups = get_groups()
        if not groups: tg_send(chat_id, "📱 No groups found yet.", reply_to_message_id=reply_to); return
        lines = [f"👥 *Groups ({len(groups)}):*\n"]
        for g in groups[:15]:
            muted = "🔇" if g.get("muted") else "🔔"
            lines.append(f"{muted} *{g.get('name','?')}* — {g.get('unread',0)} unread")
        lines.append("\n`/wa mute <name>` to silence a group")
        tg_send(chat_id, "\n".join(lines), "Markdown", reply_to)
        return

    # ── Mute group ─────────────────────────────
    if lower.startswith("mute "):
        name = arg[5:].strip()
        jid  = get_group_jid(name)
        if not jid: tg_send(chat_id, f"❌ Group '{name}' not found. Try `/wa groups` to see group names.", "Markdown", reply_to); return
        mute_group(jid, True)
        tg_send(chat_id, f"🔇 *{name}* muted — no more Telegram alerts from this group.", "Markdown", reply_to)
        return

    if lower.startswith("unmute "):
        name = arg[7:].strip()
        jid  = get_group_jid(name)
        if not jid: tg_send(chat_id, f"❌ Group '{name}' not found.", "Markdown", reply_to); return
        mute_group(jid, False)
        tg_send(chat_id, f"🔔 *{name}* unmuted.", "Markdown", reply_to)
        return

    # ── Search ─────────────────────────────────
    if lower.startswith("search "):
        keyword = arg[7:].strip()
        result  = get_messages(limit=15, search=keyword)
        msgs    = result.get("messages", [])
        if not msgs: tg_send(chat_id, f"📱 No messages found containing *{keyword}*.", "Markdown", reply_to); return
        summary = format_messages_summary(msgs)
        tg_send(chat_id, f"🔍 *Messages containing '{keyword}':*\n\n{summary}", "Markdown", reply_to)
        return

    # ── AI summarise ────────────────────────────
    if lower in ("summarise", "summarize", "summary"):
        result = get_messages(limit=50, unread_only=True)
        msgs   = result.get("messages", [])
        if not msgs: tg_send(chat_id, "✅ No unread WhatsApp messages to summarise.", reply_to_message_id=reply_to); return
        tg_send(chat_id, f"🤖 Summarising {len(msgs)} unread messages...", reply_to_message_id=reply_to)
        summary = summarise_messages(msgs)
        tg_send(chat_id, f"📱 *WhatsApp Summary:*\n\n{summary}", "Markdown", reply_to)
        return

    # ── Unread ─────────────────────────────────
    if lower == "unread":
        summary = format_unread_summary()
        tg_send(chat_id, summary or "✅ No unread WhatsApp messages.", "Markdown", reply_to)
        return

    # ── Messages [contact] ───────────────────────
    contact = ""
    if lower.startswith("messages"): contact = arg[8:].strip()
    elif lower.startswith("msgs"):   contact = arg[4:].strip()

    result = get_messages(limit=20, contact=contact)
    msgs   = result.get("messages", [])
    header = f"from *{contact}*" if contact else "recent"
    tg_send(chat_id,
        f"📱 *WhatsApp {header}:*\n\n{format_messages_summary(msgs)}" if msgs
        else f"📱 No WhatsApp messages {header}.",
        "Markdown", reply_to)


# ─────────────────────────────────────────────
# MESSAGE ROUTER
# ─────────────────────────────────────────────

def handle_message(chat_id, text="", reply_to=None, voice=None):
    if not _allowed(chat_id): print(f"[TELEGRAM] Rejected {chat_id}"); return

    if voice:
        _tg_action(chat_id)
        transcript = _transcribe(voice.get("file_id",""), voice.get("duration",0))
        if not transcript:
            tg_send(chat_id, "❌ Couldn't transcribe. Try again or type.", reply_to_message_id=reply_to); return
        tg_send(chat_id, f"🎤 _{transcript}_", "Markdown", reply_to)
        if not _rate_ok(chat_id): tg_send(chat_id, "⏳ Rate limit.", reply_to_message_id=reply_to); return
        reply = _llm_reply(transcript)
        _deliver(chat_id, reply, reply_to, with_voice=True); return

    text  = (text or "").strip(); lower = text.lower()
    if not text: return

    if   lower.startswith("/start"):     tg_send(chat_id, "🤖 ORA online. /help for commands.", reply_to_message_id=reply_to)
    elif lower.startswith("/ping"):      tg_send(chat_id, "🏓 pong!", reply_to_message_id=reply_to)
    elif lower.startswith("/help"):      _cmd_help(chat_id, reply_to)
    elif lower.startswith("/voice"):     _cmd_voice(chat_id, text[6:], reply_to)
    elif lower.startswith("/tasks"):     _cmd_tasks(chat_id, reply_to)
    elif lower.startswith("/done"):      _cmd_done(chat_id, text[5:], reply_to)
    elif lower.startswith("/goals"):     _cmd_goals(chat_id, reply_to)
    elif lower.startswith("/wa"):        _cmd_wa(chat_id, text[3:], reply_to)
    elif lower.startswith("/weather"):   _cmd_weather(chat_id, reply_to)
    elif lower.startswith("/mpesa"):     _cmd_mpesa(chat_id, reply_to)
    elif lower.startswith("/cal"):       _cmd_cal(chat_id, text[4:], reply_to)
    elif lower.startswith("/brief"):     _cmd_brief(chat_id, reply_to)
    elif lower.startswith("/browse"):    _cmd_browse(chat_id, text[7:], reply_to)
    elif lower.startswith("/email"):     _cmd_email(chat_id, text[6:], reply_to)
    elif lower.startswith("/draft"):     _cmd_draft(chat_id, text[6:], reply_to)
    elif lower.startswith("/inbox"):     _cmd_inbox(chat_id, reply_to)
    elif lower.startswith("/replies"):   _cmd_replies(chat_id, reply_to)
    elif lower.startswith("/proactive"): _cmd_proactive(chat_id, reply_to)
    elif lower.startswith("/stats"):     _cmd_stats(chat_id, reply_to)
    else:
        if not _rate_ok(chat_id): tg_send(chat_id, "⏳ Rate limit.", reply_to_message_id=reply_to); return
        try:
            from Intent_parser import parse_intent, execute_intent
            intent = parse_intent(text)
            if intent:
                intent_reply = execute_intent(intent)
                if intent_reply: _deliver(chat_id, intent_reply, reply_to, with_voice=_voice_on(chat_id)); return
        except Exception as e: print(f"[INTENT] {e}")
        _tg_action(chat_id)
        reply = _llm_reply(text)
        _deliver(chat_id, reply, reply_to, with_voice=_voice_on(chat_id))


# ─────────────────────────────────────────────
# POLLING LOOP
# ─────────────────────────────────────────────

def run_telegram_bot():
    if not TELEGRAM_ENABLED: print("[TELEGRAM] No token — bot disabled"); return
    print("[TELEGRAM] Starting long-poll loop")
    offset = None
    while True:
        try:
            updates = _tg_get_updates(offset, timeout=25)
            for update in updates:
                offset  = update.get("update_id",0) + 1
                msg     = update.get("message",{})
                chat_id = msg.get("chat",{}).get("id")
                if not chat_id: continue
                handle_message(chat_id, text=msg.get("text",""),
                    reply_to=msg.get("reply_to_message",{}).get("message_id"),
                    voice=msg.get("voice"))
                time.sleep(0.05)
            if not updates: time.sleep(1)
        except KeyboardInterrupt: print("[TELEGRAM] Shutting down"); break
        except Exception as e:
            print(f"[TELEGRAM LOOP] {e}\n{traceback.format_exc()}"); time.sleep(5)

if __name__ == "__main__":
    run_telegram_bot()