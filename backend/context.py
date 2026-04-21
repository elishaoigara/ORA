from memory.profile import get_all_profile
from memory.events import get_recent_events, get_important_events
from memory.preferences import get_preferences
from database import get_recent_alerts
from datetime import datetime


def build_context(query=None):
    sections = []

    # 1. Profile
    profile = get_all_profile()
    if profile:
        lines = [f"- {k}: {v}" for k, v in profile.items()]
        sections.append("## About Elisha\n" + "\n".join(lines))

    # 2. Time
    now = datetime.now()
    sections.append(
        f"## Current time\n- {now.strftime('%A, %d %B %Y at %H:%M')} (Nairobi time)"
    )

    # 3. Important memories
    important = get_important_events(min_importance=7, limit=5)
    if important:
        lines = [f"- [{e[0]}] {e[1]} ({e[4][:10]})" for e in important]
        sections.append("## Important events\n" + "\n".join(lines))

    # 4. Recent activity
    recent = get_recent_events(limit=6)
    if recent:
        lines = [f"- {e[1]}" for e in recent]
        sections.append("## Recent activity\n" + "\n".join(lines))

    # 5. Preferences
    prefs = get_preferences()
    if prefs:
        lines = [f"- {p[0]}/{p[1]}: {p[2]}" for p in prefs]
        sections.append("## Known preferences\n" + "\n".join(lines))

    # 6. Active alerts
    alerts = get_recent_alerts(limit=3)
    unacked = [a for a in alerts if not a[5]]
    if unacked:
        lines = [f"- [{a[3]}] {a[2]}" for a in unacked]
        sections.append("## Active alerts\n" + "\n".join(lines))

    # 7. Semantic knowledge (if query provided)
    if query:
        try:
            from knowledge import search_knowledge
            chunks = search_knowledge(query, n_results=3)
            if chunks:
                lines = []
                for c in chunks:
                    lines.append(f"[{c['filename']}]: {c['text'][:300]}")
                sections.append("## Relevant knowledge from your files\n" + "\n\n".join(lines))
        except Exception as e:
            pass

    return "\n\n".join(sections)


def build_system_prompt(query=None):
    context = build_context(query=query)

    prompt = (
        "You are ORA — Oigara's Responsive Assistant.\n\n"
        "You are a personal intelligence system built specifically for "
        "Elisha Lambert Oigara, a Software Engineer in Nairobi, Kenya.\n\n"
        "Your personality:\n"
        "- Direct and honest — no fluff\n"
        "- Intelligent and analytical\n"
        "- Personal — reference Elisha's context naturally\n"
        "- Proactive — flag important things\n"
        "- Concise — short answers unless depth is needed\n\n"
        "When Elisha asks about his documents, notes, or files — search "
        "your knowledge base and give specific answers grounded in what "
        "he has shared with you, not generic responses.\n\n"
        "Current context:\n"
        f"{context}\n\n"
        "Always respond as ORA."
    )
    return prompt