from memory.profile import get_all_profile
from memory.events import get_recent_events, get_important_events
from memory.preferences import get_preferences
from database import get_recent_alerts
from datetime import datetime


# =============================
# CONTEXT BUILDER
# =============================
def build_context(query=None):
    sections = []

    # ---------------- PROFILE ----------------
    profile = get_all_profile()
    if profile:
        lines = [f"- {k}: {v}" for k, v in profile.items()]
        sections.append("## USER PROFILE\n" + "\n".join(lines))

    # ---------------- TIME ----------------
    now = datetime.now()
    sections.append(
        "## CURRENT TIME (Nairobi, Kenya)\n"
        f"- {now.strftime('%A, %d %B %Y at %H:%M')}"
    )

    # ---------------- IMPORTANT EVENTS ----------------
    important = get_important_events(min_importance=7, limit=5)
    if important:
        lines = [
            f"- [{e[0]}] {e[1]} (time: {e[4][:10]})"
            for e in important
        ]
        sections.append("## IMPORTANT EVENTS\n" + "\n".join(lines))

    # ---------------- RECENT ACTIVITY ----------------
    recent = get_recent_events(limit=6)
    if recent:
        lines = [f"- {e[1]}" for e in recent]
        sections.append("## RECENT ACTIVITY\n" + "\n".join(lines))

    # ---------------- PREFERENCES ----------------
    prefs = get_preferences()
    if prefs:
        lines = [f"- {p[0]}/{p[1]} = {p[2]}" for p in prefs]
        sections.append("## USER PREFERENCES\n" + "\n".join(lines))

    # ---------------- ALERTS ----------------
    alerts = get_recent_alerts(limit=3)
    unacked = [a for a in alerts if not a[5]]

    if unacked:
        lines = [f"- [{a[3]}] {a[2]}" for a in unacked]
        sections.append("## ACTIVE ALERTS\n" + "\n".join(lines))

    # ---------------- KNOWLEDGE BASE (CRITICAL FIX) ----------------
    if query:
        try:
            from knowledge import search_and_format

            knowledge_context = search_and_format(query, n_results=4)

            if knowledge_context:
                sections.append(
                    "## KNOWLEDGE BASE (VERIFIED SOURCES ONLY)\n"
                    "RULE: You MUST ONLY use this section when answering.\n"
                    "If a fact is not in this section, say: 'No verified data found.'\n\n"
                    + knowledge_context
                )

        except Exception as e:
            sections.append("## KNOWLEDGE BASE\nERROR LOADING KNOWLEDGE")

    return "\n\n".join(sections)


# =============================
# SYSTEM PROMPT (STRICTER)
# =============================
def build_system_prompt(query=None):
    context = build_context(query=query)

    return (
        "You are ORA — Oigara's Responsive Assistant.\n\n"
        "You are a private intelligence system for Elisha Lambert Oigara, "
        "a Software Engineer in Nairobi, Kenya.\n\n"

        "========================\n"
        "HARD RULES (NON-NEGOTIABLE)\n"
        "========================\n"
        "1. ONLY use information inside the provided context.\n"
        "2. NEVER invent files, PDFs, or document IDs.\n"
        "3. If a document is not shown in context, it does NOT exist.\n"
        "4. If unsure, say: 'No verified information found in memory.'\n"
        "5. Every factual claim MUST reference a filename from context.\n"
        "6. Do NOT fabricate citations under any condition.\n\n"

        "========================\n"
        "CITATION FORMAT (MANDATORY)\n"
        "========================\n"
        "When using knowledge base content, respond like:\n"
        "[filename.pdf] statement or answer here\n\n"

        "If multiple sources exist, list them separately.\n\n"

        "========================\n"
        "PERSONALITY\n"
        "========================\n"
        "- Precise and factual\n"
        "- No guessing\n"
        "- Evidence-based reasoning only\n"
        "- Concise unless depth is requested\n\n"

        "========================\n"
        "CURRENT SYSTEM CONTEXT\n"
        "========================\n"
        f"{context}\n\n"

        "Always respond as ORA. Never break grounding rules."
    )