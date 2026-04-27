"""
ORA Context Builder — with learned facts + hallucination prevention
"""

from memory.profile import get_all_profile
from memory.events import get_recent_events, get_important_events
from memory.preferences import get_preferences
from database import get_recent_alerts
from datetime import datetime


def build_context(query=None):
    sections = []

    # PROFILE
    profile = get_all_profile()
    if profile:
        sections.append(
            "## USER PROFILE\n" +
            "\n".join([f"- {k}: {v}" for k, v in profile.items()])
        )

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

    # GOOGLE CALENDAR
    try:
        from connectors.calendar import get_events_today, format_events_for_context
        events = get_events_today()
        if events:
            formatted = format_events_for_context(events)
            sections.append("## TODAY'S CALENDAR\n" + formatted)
    except Exception:
        pass

    # IMPORTANT EVENTS
    try:
        important = get_important_events(min_importance=7, limit=5)
        if important:
            sections.append(
                "## IMPORTANT EVENTS\n" +
                "\n".join([
                    f"- [{e[0]}] {e[1]} (date: {e[4][:10]})"
                    for e in important
                ])
            )
    except Exception as e:
        print(f"[CONTEXT] Important events error: {e}")

    # RECENT ACTIVITY
    try:
        recent = get_recent_events(limit=6)
        if recent:
            sections.append(
                "## RECENT ACTIVITY\n" +
                "\n".join([f"- {e[1]}" for e in recent])
            )
    except Exception as e:
        print(f"[CONTEXT] Recent events error: {e}")

    # PREFERENCES
    try:
        prefs = get_preferences()
        if prefs:
            sections.append(
                "## USER PREFERENCES\n" +
                "\n".join([f"- {p[0]}/{p[1]} = {p[2]}" for p in prefs])
            )
    except Exception as e:
        print(f"[CONTEXT] Preferences error: {e}")

    # ACTIVE ALERTS
    try:
        alerts = get_recent_alerts(limit=5)
        if alerts:
            unacked = [a for a in alerts if not a[5]]
            if unacked:
                sections.append(
                    "## ACTIVE ALERTS\n" +
                    "\n".join([f"- [{a[3]}] {a[2]}" for a in unacked])
                )
    except Exception as e:
        print(f"[CONTEXT] Alerts error: {e}")

    # KNOWLEDGE BASE (RAG)
    if query:
        try:
            from knowledge.rag import rag_search
            knowledge_context = rag_search(query)
            if knowledge_context:
                sections.append(
                    "## KNOWLEDGE BASE (RAG RETRIEVAL)\n"
                    f"{knowledge_context}"
                )
        except Exception as e:
            print(f"[RAG ERROR] {e}")

    # LEARNED FACTS (grows over time as ORA learns from conversations)
    try:
        from intelligence.learning_engine import get_facts_as_context
        learned = get_facts_as_context(limit=12)
        if learned:
            sections.append(
                "## WHAT ORA HAS LEARNED ABOUT YOU\n"
                f"{learned}"
            )
    except Exception:
        pass

    return "\n\n".join(sections)


def build_system_prompt(query=None):
    context = build_context(query=query)

    now = datetime.now()
    hour = now.hour

    if hour < 6:
        tone_note = "It's the middle of the night — keep it brief and practical unless he wants to dig in."
    elif hour < 10:
        tone_note = "Morning session — be energizing but grounded. Help him plan the day if that comes up."
    elif hour < 14:
        tone_note = "Midday — he's likely in work mode. Be efficient and direct."
    elif hour < 18:
        tone_note = "Afternoon — he may be wrapping up tasks or planning ahead. Stay practical."
    elif hour < 22:
        tone_note = "Evening — he might be reflecting on the day or planning tomorrow. Match his energy."
    else:
        tone_note = "Late night — be calm, concise. Don't over-explain."

    return (
        "You are ORA — Elisha Lambert Oigara's personal AI assistant. "
        "You're not a chatbot. You're his second brain — the one that knows his tasks, "
        "goals, calendar, spending, and what he's been working on.\n\n"

        "## WHO YOU'RE TALKING TO\n"
        "Elisha is a Software Engineer based in Nairobi, Kenya. He built you. "
        "Talk to him like a sharp, reliable colleague with full context on his life — "
        "not like a generic assistant reading off a template.\n\n"

        "## HOW TO TALK\n"
        "- Be direct. No filler. No 'Certainly!' or 'Great question!' — ever.\n"
        "- Use short sentences. Say what matters. Cut the rest.\n"
        "- If you know the answer from context, give it.\n"
        "- If you don't have the info, say: 'I don't have that in memory' — then suggest what to do.\n"
        "- Match his tone. If he's brief, be brief. If he wants detail, give detail.\n"
        "- You can push back or flag concerns. You're not just agreeable.\n\n"

        "## ANTI-HALLUCINATION RULES (CRITICAL)\n"
        "- NEVER invent tasks, events, meetings, expenses, or facts not in the context below.\n"
        "- NEVER say 'you have X tasks' unless the actual task list is shown in context.\n"
        "- NEVER estimate spending — only report what's in the M-Pesa data.\n"
        "- If data isn't available, say exactly that: 'No tasks in memory' / 'Calendar not connected'.\n"
        "- Do NOT use 'for example', 'typically', 'you might have' for factual questions.\n\n"

        f"## TIME AWARENESS\n"
        f"{tone_note}\n\n"

        "## ACTIONS YOU CAN EXECUTE\n"
        "When Elisha asks you to do something actionable, you do it — "
        "tasks, reminders, goals, M-Pesa summaries, document searches. "
        "After an action, confirm cleanly: what was done, any relevant detail.\n\n"

        "## CURRENT CONTEXT\n"
        f"{context}\n\n"

        "Respond as ORA. Stay grounded in memory and retrieved knowledge."
    )