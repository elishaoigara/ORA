from memory.profile import get_all_profile
from memory.events import get_recent_events, get_important_events
from memory.preferences import get_preferences
from database import get_recent_alerts
from datetime import datetime


def build_context(query=None):
    sections = []

    profile = get_all_profile()
    if profile:
        lines = [f"- {k}: {v}" for k, v in profile.items()]
        sections.append("## About Elisha\n" + "\n".join(lines))

    now = datetime.now()
    sections.append(
        f"## Current time\n- {now.strftime('%A, %d %B %Y at %H:%M')} (Nairobi time)"
    )

    important = get_important_events(min_importance=7, limit=5)
    if important:
        lines = [f"- [{e[0]}] {e[1]} ({e[4][:10]})" for e in important]
        sections.append("## Important events\n" + "\n".join(lines))

    recent = get_recent_events(limit=6)
    if recent:
        lines = [f"- {e[1]}" for e in recent]
        sections.append("## Recent activity\n" + "\n".join(lines))

    prefs = get_preferences()
    if prefs:
        lines = [f"- {p[0]}/{p[1]}: {p[2]}" for p in prefs]
        sections.append("## Known preferences\n" + "\n".join(lines))

    alerts = get_recent_alerts(limit=3)
    unacked = [a for a in alerts if not a[5]]
    if unacked:
        lines = [f"- [{a[3]}] {a[2]}" for a in unacked]
        sections.append("## Active alerts\n" + "\n".join(lines))

    # Semantic knowledge search
    if query:
        try:
            from knowledge import search_and_format
            knowledge_context = search_and_format(query, n_results=4)
            if knowledge_context:
                sections.append(knowledge_context)
        except Exception as e:
            pass

    return "\n\n".join(sections)


def build_system_prompt(query=None):
    context = build_context(query=query)

    prompt = (
        "You are ORA — Oigara's Responsive Assistant.\n\n"
        "You are a personal intelligence system built specifically for "
        "Elisha Lambert Oigara, a Software Engineer in Nairobi, Kenya.\n\n"
        "CRITICAL INSTRUCTION — When answering questions:\n"
        "1. If relevant knowledge from files is provided in context, USE IT.\n"
        "2. Always cite which file your answer came from.\n"
        "3. If you find conflicting information across files, flag it.\n"
        "4. Never give generic answers when specific file content is available.\n"
        "5. If asked about a document, quote directly from it.\n\n"
        "Your personality:\n"
        "- Direct and honest\n"
        "- Cites sources from Elisha's files\n"
        "- Flags important patterns or contradictions\n"
        "- Concise unless depth is needed\n\n"
        "Current context:\n"
        f"{context}\n\n"
        "Always respond as ORA."
    )
    return prompt