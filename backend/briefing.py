"""
ORA Briefing — generates morning/evening briefings.
Uses build_system_prompt — no separate Groq call for context.
One small Groq call (8b model) for the motivational note only.
"""

from datetime import datetime
from database import get_system_stats, get_tasks
from memory.profile import get_all_profile
import json


def generate_briefing() -> str:
    now = datetime.now()
    day = now.strftime("%A, %d %B %Y")
    time_str = now.strftime("%H:%M")
    is_morning = now.hour < 12

    lines = []

    # Header
    greeting = "Good morning" if is_morning else ("Good afternoon" if now.hour < 17 else "Good evening")
    lines.append(f"{'☀️' if is_morning else '🌆'} *{greeting}, Elisha.*")
    lines.append(f"_{day} — {time_str}_\n")

    # Weather (free — no API cost)
    try:
        from connectors.weather import get_weather_summary
        weather = get_weather_summary()
        if weather:
            lines.append(f"🌤 *Weather*\n{weather}\n")
    except Exception:
        pass

    # System Status
    try:
        row = get_system_stats()
        if row:
            data = json.loads(row[0])
            cpu  = data.get("cpu_percent", "?")
            ram  = data.get("ram_percent", "?")
            disk = round(data.get("disk_free_gb", 0), 1)
            lines.append(f"🖥 *System*\nCPU: {cpu}% · RAM: {ram}% · Disk: {disk}GB free\n")
    except Exception:
        pass

    # Calendar (if Google connected)
    try:
        from connectors.google_auth import is_authorized
        from connectors.calendar import get_events_today, format_events_for_context
        if is_authorized():
            events = get_events_today()
            if events:
                lines.append(f"📅 *Calendar ({len(events)} event(s) today)*")
                lines.append(format_events_for_context(events) + "\n")
            else:
                lines.append("📅 *Calendar*\nNo events today.\n")
    except Exception:
        pass

    # Gmail (if Google connected)
    try:
        from connectors.google_auth import is_authorized
        from connectors.gmail import get_gmail_summary
        if is_authorized():
            gmail = get_gmail_summary()
            count = gmail.get("unread_count", 0)
            if count > 0:
                senders = ", ".join(gmail.get("senders", [])[:3])
                lines.append(f"📧 *Email*\n{count} unread from: {senders}\n")
    except Exception:
        pass

    # Pending Tasks
    tasks = get_tasks("pending")
    if tasks:
        high = [t for t in tasks if t[2] == "high"]
        overdue = []
        now_dt = datetime.now()
        for t in tasks:
            if t[4]:
                try:
                    if datetime.fromisoformat(t[4]) < now_dt:
                        overdue.append(t[1])
                except Exception:
                    pass
        lines.append(f"📌 *Tasks ({len(tasks)} pending)*")
        for t in tasks[:5]:
            due = f" ⏰ {t[4][:10]}" if t[4] else ""
            icon = {"high": "🔴", "low": "🟢"}.get(t[2], "🟡")
            lines.append(f"{icon} {t[1]}{due}")
        if overdue:
            lines.append(f"⚠ {len(overdue)} overdue!")
        lines.append("")
    else:
        lines.append("📌 *Tasks*\nAll clear — no pending tasks.\n")

    # Goals
    try:
        from intelligence.goals_engine import get_goals
        goals = get_goals("active")
        if goals:
            avg_progress = int(sum(g.get("progress", 0) for g in goals) / len(goals))
            lines.append(f"🎯 *Goals ({len(goals)} active, {avg_progress}% avg)*")
            for g in goals[:3]:
                bar = "█" * (g.get("progress", 0) // 10) + "░" * (10 - g.get("progress", 0) // 10)
                lines.append(f"• {g['goal'][:50]} [{bar}] {g.get('progress', 0)}%")
            lines.append("")
    except Exception:
        pass

    # M-Pesa
    try:
        from mpesa_engine import get_today_spend, get_average_daily_spend
        def _f(v):
            try: return float(v) if v is not None else 0.0
            except: return 0.0
        today = _f(get_today_spend())
        avg   = _f(get_average_daily_spend())
        if today > 0 or avg > 0:
            lines.append(f"💳 *M-Pesa*\nToday: KES {today:,.0f}" +
                         (f" (avg: KES {avg:,.0f})" if avg > 0 else "") + "\n")
    except Exception:
        pass

    # AI Motivational note — ONE small Groq call (8b, 100 tokens max)
    try:
        from groq import Groq
        from config import GROQ_API_KEY
        if GROQ_API_KEY:
            client = Groq(api_key=GROQ_API_KEY)
            task_names = ", ".join(t[1] for t in tasks[:3]) if tasks else "none"
            prompt = (
                f"You are ORA. Write a single sharp, direct sentence (max 25 words) "
                f"for Elisha's {('morning' if is_morning else 'evening')} briefing. "
                f"Today: {day}. Top tasks: {task_names}. "
                f"Be motivating but not cheesy. No filler words."
            )
            resp = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=80,
                temperature=0.7,
            )
            note = (resp.choices[0].message.content or "").strip()
            if note:
                lines.append(f"🧠 *ORA Note*\n{note}")
    except Exception:
        pass  # Briefing works without the AI note

    return "\n".join(lines)


def send_morning_briefing():
    from telegram_bot import notify
    print("[ORA] Sending morning briefing...")
    briefing = generate_briefing()
    notify(briefing, is_alert=False)
    print("[ORA] Morning briefing sent.")
