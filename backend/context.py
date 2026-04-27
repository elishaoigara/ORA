"""
ORA Context Builder — grounded, non-hallucinating version
"""

from memory.profile import get_all_profile
from memory.events import get_recent_events, get_important_events
from memory.preferences import get_preferences
from database import get_recent_alerts
from datetime import datetime


def _safe_section(title, content_lines):
    if not content_lines:
        return f"{title}\n- No data available"
    return f"{title}\n" + "\n".join(content_lines)


def build_context(query=None):
    sections = []

    # PROFILE
    try:
        profile = get_all_profile()
        if profile:
            lines = [f"- {k}: {v}" for k, v in profile.items()]
        else:
            lines = ["- No profile data"]
        sections.append(_safe_section("## USER PROFILE", lines))
    except Exception:
        sections.append("## USER PROFILE\n- Error loading profile")

    # TIME
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

    # CALENDAR
    try:
        from connectors.calendar import get_events_today, format_events_for_context
        events = get_events_today()
        if events:
            formatted = format_events_for_context(events)
            sections.append("## TODAY'S CALENDAR\n" + formatted)
        else:
            sections.append("## TODAY'S CALENDAR\n- No events found or calendar not connected")
    except Exception:
        sections.append("## TODAY'S CALENDAR\n- Calendar unavailable")

    # IMPORTANT EVENTS
    try:
        important = get_important_events(min_importance=7, limit=5)
        lines = [
            f"- [{e[0]}] {e[1]} (date: {e[4][:10]})"
            for e in important
        ] if important else []
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

    # PREFERENCES
    try:
        prefs = get_preferences()
        lines = [f"- {p[0]}/{p[1]} = {p[2]}" for p in prefs] if prefs else []
        sections.append(_safe_section("## USER PREFERENCES", lines))
    except Exception:
        sections.append("## USER PREFERENCES\n- Error loading data")

    # ALERTS
    try:
        alerts = get_recent_alerts(limit=5)
        unacked = [a for a in alerts if not a[5]] if alerts else []
        lines = [f"- [{a[3]}] {a[2]}" for a in unacked] if unacked else []
        sections.append(_safe_section("## ACTIVE ALERTS", lines))
    except Exception:
        sections.append("## ACTIVE ALERTS\n- Error loading data")

    # RAG
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
        learned = get_facts_as_context(limit=12)
        if learned:
            sections.append("## LEARNED FACTS\n" + learned)
        else:
            sections.append("## LEARNED FACTS\n- No learned facts yet")
    except Exception:
        sections.append("## LEARNED FACTS\n- Learning system unavailable")

    return "\n\n".join(sections)

def build_system_prompt(query=None):
    """
    Alias used by telegram_bot, api, ai_brain, and briefing.
    Wraps build_context() in an ORA system prompt directive.
    """
    context = build_context(query=query)
    return (
        "You are ORA — Elisha's personal AI assistant based in Nairobi, Kenya.\n"
        "You are grounded, direct, and precise. You NEVER invent facts, tasks, "
        "events, or spending data. If information is not in your context, you say so.\n"
        "You speak like a highly capable chief of staff — concise, clear, no fluff.\n"
        "When the user asks about tasks, goals, spending, or calendar events, you "
        "only report what is explicitly present in the context below.\n\n"
        "=== LIVE CONTEXT ===\n"
        f"{context}\n"
        "=== END CONTEXT ===\n\n"
        "Respond only from the context above. If data is missing, state that plainly."
    )
