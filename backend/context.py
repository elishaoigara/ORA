"""
ORA Context Builder — grounded, intelligent, non-hallucinating version.

Injects all live data sources into the system prompt:
  - User profile & learned facts
  - Calendar (Google) — today's events
  - Gmail — unread email summaries
  - Weather (Open-Meteo, free, no key)
  - Tasks, goals, alerts
  - Knowledge base (RAG, query-conditional)
  - M-Pesa spend
  - Memory events & preferences

COST: Zero Groq calls.
"""

from memory.profile import get_all_profile
from memory.events import get_recent_events, get_important_events
from memory.preferences import get_preferences
from database import get_recent_alerts
from datetime import datetime


def _safe_section(title: str, content_lines: list) -> str:
    if not content_lines:
        return f"{title}\n- No data available"
    return f"{title}\n" + "\n".join(content_lines)


def build_context(query=None) -> str:
    sections = []

    # PROFILE
    try:
        profile = get_all_profile()
        lines = [f"- {k}: {v}" for k, v in profile.items()] if profile else ["- No profile data"]
        sections.append(_safe_section("## USER PROFILE", lines))
    except Exception:
        sections.append("## USER PROFILE\n- Error loading profile")

    # CURRENT TIME
    now = datetime.now()
    hour = now.hour
    time_of_day = (
        "early morning" if hour < 6 else
        "morning"       if hour < 12 else
        "afternoon"     if hour < 17 else
        "evening"       if hour < 21 else
        "late night"
    )
    sections.append(
        "## CURRENT TIME (Nairobi, Kenya)\n"
        f"- {now.strftime('%A, %d %B %Y at %H:%M')} ({time_of_day})"
    )

    # WEATHER (free, zero API cost)
    try:
        from connectors.weather import get_weather_summary
        weather = get_weather_summary()
        if weather:
            sections.append(f"## WEATHER (Nairobi)\n- {weather}")
    except Exception:
        pass

    # GOOGLE CALENDAR
    try:
        from connectors.calendar import get_events_today, format_events_for_context
        events = get_events_today()
        if events:
            formatted = format_events_for_context(events)
            sections.append("## TODAY'S CALENDAR\n" + formatted)
        else:
            sections.append("## TODAY'S CALENDAR\n- No events today (or calendar not connected)")
    except Exception:
        sections.append("## TODAY'S CALENDAR\n- Calendar unavailable")

    # GMAIL UNREAD SUMMARY
    try:
        from connectors.gmail import get_gmail_summary
        from connectors.google_auth import is_authorized
        if is_authorized():
            gmail = get_gmail_summary()
            if gmail and gmail.get("unread_count", 0) > 0:
                count = gmail["unread_count"]
                senders = ", ".join(gmail.get("senders", [])[:3])
                lines = [f"- {count} unread email(s)", f"- From: {senders}"]
                for s in gmail.get("subjects", [])[:3]:
                    lines.append(f"  • {s[:80]}")
                sections.append(_safe_section("## UNREAD EMAILS", lines))
            else:
                sections.append("## UNREAD EMAILS\n- Inbox clear")
        else:
            sections.append("## UNREAD EMAILS\n- Gmail not connected")
    except Exception:
        sections.append("## UNREAD EMAILS\n- Gmail unavailable")

    # TASKS with overdue detection
    try:
        from database import get_tasks
        tasks = get_tasks("pending")
        if tasks:
            overdue_count = 0
            lines = []
            for t in tasks[:12]:
                due_str = ""
                if t[4]:
                    try:
                        due_dt = datetime.fromisoformat(t[4])
                        if due_dt < now:
                            due_str = " — ⚠ OVERDUE"
                            overdue_count += 1
                        else:
                            due_str = f" — due {t[4][:10]}"
                    except Exception:
                        pass
                icon = {"high": "🔴", "low": "🟢"}.get(t[2], "🟡")
                lines.append(f"- [{t[0]}] {icon} {t[2].upper()} | {t[1]}{due_str}")
            header = f"## PENDING TASKS ({len(tasks)} total{', ' + str(overdue_count) + ' OVERDUE' if overdue_count else ''})"
            sections.append(_safe_section(header, lines))
        else:
            sections.append("## PENDING TASKS\n- No pending tasks")
    except Exception:
        sections.append("## PENDING TASKS\n- Error loading tasks")

    # ACTIVE GOALS
    try:
        from intelligence.goals_engine import get_goals
        goals = get_goals("active")
        if goals:
            lines = []
            for g in goals[:6]:
                bar = "█" * (g.get("progress", 0) // 10) + "░" * (10 - g.get("progress", 0) // 10)
                due = f" — due {g['due_at'][:10]}" if g.get("due_at") else ""
                lines.append(f"- {g['goal'][:70]} [{bar}] {g.get('progress', 0)}%{due}")
            sections.append(_safe_section(f"## ACTIVE GOALS ({len(goals)})", lines))
        else:
            sections.append("## ACTIVE GOALS\n- No active goals")
    except Exception:
        sections.append("## ACTIVE GOALS\n- Error loading goals")

    # M-PESA SPEND
    try:
        from mpesa_engine import get_today_spend, get_average_daily_spend
        def _f(v):
            try: return float(v) if v is not None else 0.0
            except Exception: return 0.0
        today_spend = _f(get_today_spend())
        avg_spend   = _f(get_average_daily_spend())
        lines = [f"- Today: KES {today_spend:,.0f}"]
        if avg_spend > 0:
            ratio = today_spend / avg_spend
            trend = "↑ above avg" if ratio > 1.3 else ("↓ below avg" if ratio < 0.7 else "≈ normal")
            lines.append(f"- Daily avg: KES {avg_spend:,.0f} ({trend})")
        sections.append(_safe_section("## M-PESA SPEND", lines))
    except Exception:
        sections.append("## M-PESA SPEND\n- No spend data")

    # IMPORTANT MEMORY EVENTS
    try:
        important = get_important_events(min_importance=7, limit=5)
        lines = [f"- [{e[0]}] {e[1]} (date: {e[4][:10]})" for e in important] if important else []
        sections.append(_safe_section("## IMPORTANT EVENTS", lines))
    except Exception:
        sections.append("## IMPORTANT EVENTS\n- Error loading data")

    # RECENT ACTIVITY
    try:
        recent = get_recent_events(limit=6)
        lines = [f"- {e[1]}" for e in recent] if recent else []
        sections.append(_safe_section("## RECENT ACTIVITY", lines))
    except Exception:
        sections.append("## RECENT ACTIVITY\n- Error loading data")

    # USER PREFERENCES
    try:
        prefs = get_preferences()
        lines = [f"- {p[0]}/{p[1]} = {p[2]}" for p in prefs] if prefs else []
        sections.append(_safe_section("## USER PREFERENCES", lines))
    except Exception:
        sections.append("## USER PREFERENCES\n- Error loading data")

    # ACTIVE ALERTS
    try:
        alerts = get_recent_alerts(limit=5)
        unacked = [a for a in alerts if not a[5]] if alerts else []
        lines = [f"- [{a[3]}] {a[2]}" for a in unacked] if unacked else []
        sections.append(_safe_section("## ACTIVE ALERTS", lines))
    except Exception:
        sections.append("## ACTIVE ALERTS\n- Error loading data")

    # RAG KNOWLEDGE — only when query is given
    if query:
        try:
            from knowledge.rag import rag_search
            knowledge_context = rag_search(query)
            if knowledge_context:
                sections.append("## KNOWLEDGE BASE\n" + knowledge_context)
            else:
                sections.append("## KNOWLEDGE BASE\n- No relevant knowledge found")
        except Exception:
            sections.append("## KNOWLEDGE BASE\n- Retrieval error")

    # LEARNED FACTS
    try:
        from intelligence.learning_engine import get_facts_as_context
        learned = get_facts_as_context(limit=15)
        if learned:
            sections.append("## LEARNED FACTS\n" + learned)
        else:
            sections.append("## LEARNED FACTS\n- No learned facts yet")
    except Exception:
        sections.append("## LEARNED FACTS\n- Learning system unavailable")

    return "\n\n".join(sections)


def build_system_prompt(query=None) -> str:
    """
    Full ORA system prompt with live context.
    Used by: api.py, telegram_bot.py, ai_brain.py
    COST: Zero Groq calls.
    """
    context = build_context(query=query)

    return (
        "You are ORA — Elisha's personal AI chief of staff, based in Nairobi, Kenya.\n"
        "\n"
        "PERSONALITY:\n"
        "- Direct, intelligent, warm — not sycophantic\n"
        "- Speak like a trusted advisor who knows Elisha well\n"
        "- Use Nairobi context naturally (KES, EAT timezone, local knowledge)\n"
        "- Brief by default — expand only when depth is needed\n"
        "- Never say 'certainly', 'absolutely', 'great question', 'as an AI'\n"
        "\n"
        "INTELLIGENCE RULES:\n"
        "- Use the LIVE CONTEXT below actively — synthesize, don't just recite\n"
        "- Connect dots: if calendar shows a meeting and tasks include prep, flag it\n"
        "- Proactively surface risks: overdue tasks, high spend, conflicting events\n"
        "- For priority/focus questions: synthesize tasks + goals + calendar together\n"
        "- For factual queries: cite actual numbers from context — never estimate\n"
        "- If data is missing, say so plainly — never invent\n"
        "- When multiple things need attention, rank by urgency\n"
        "\n"
        "FORMATTING:\n"
        "- Use bullet points for lists, bold for key numbers/dates\n"
        "- Keep responses under 300 words unless asked for detail\n"
        "- For briefings: use emoji section headers (📋 Tasks, 📅 Calendar, etc.)\n"
        "\n"
        "=== LIVE CONTEXT ===\n"
        f"{context}\n"
        "=== END CONTEXT ===\n"
        "\n"
        "Ground every factual claim in the context above. "
        "If something isn't in the context, say 'I don't have that data' — never guess."
    )
