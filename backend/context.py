from memory.profile import get_all_profile
from memory.events import get_recent_events, get_important_events
from memory.preferences import get_preferences
from database import get_recent_alerts
from datetime import datetime

def build_context():
    sections = []

    profile = get_all_profile()
    if profile:
        lines = [f"- {k}: {v}" for k, v in profile.items()]
        sections.append("## About Elisha\n" + "\n".join(lines))

    now = datetime.now()
    sections.append(f"## Current time\n- {now.strftime('%A, %d %B %Y at %H:%M')} (Nairobi time)")

    important = get_important_events(min_importance=7, limit=5)
    if important:
        lines = [f"- [{e[0]}] {e[1]} ({e[4][:10]})" for e in important]
        sections.append("## Important recent events\n" + "\n".join(lines))

    recent = get_recent_events(limit=8)
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

    return "\n\n".join(sections)


def build_system_prompt():
    context = build_context()

    prompt = (
        "You are ORA — Oigara's Responsive Assistant.\n\n"
        "You are not a generic chatbot. You are a personal intelligence system "
        "built specifically for Elisha Lambert Oigara, a Software Engineer based "
        "in Nairobi, Kenya.\n\n"
        "Your personality:\n"
        "- Direct and honest — no fluff, no filler\n"
        "- Intelligent and analytical — think before responding\n"
        "- Personal — you know Elisha, reference his context when relevant\n"
        "- Proactive — if you notice something worth flagging, say it\n"
        "- Concise — keep responses short unless depth is needed\n\n"
        "Current context about Elisha:\n"
        f"{context}\n\n"
        "Always respond as ORA. Never say you are an AI or that you lack personal data."
    )
    return prompt