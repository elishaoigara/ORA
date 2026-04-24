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

    # PROFILE
    profile = get_all_profile()
    if profile:
        lines = [f"- {k}: {v}" for k, v in profile.items()]
        sections.append("## USER PROFILE\n" + "\n".join(lines))

    # TIME
    now = datetime.now()
    sections.append(
        "## CURRENT TIME (Nairobi, Kenya)\n"
        f"- {now.strftime('%A, %d %B %Y at %H:%M')}"
    )

    # IMPORTANT EVENTS
    important = get_important_events(min_importance=7, limit=5)
    if important:
        lines = [
            f"- [{e[0]}] {e[1]} (date: {e[4][:10]})"
            for e in important
        ]
        sections.append("## IMPORTANT EVENTS\n" + "\n".join(lines))

    # RECENT ACTIVITY
    recent = get_recent_events(limit=6)
    if recent:
        lines = [f"- {e[1]}" for e in recent]
        sections.append("## RECENT ACTIVITY\n" + "\n".join(lines))

    # PREFERENCES
    prefs = get_preferences()
    if prefs:
        lines = [f"- {p[0]}/{p[1]} = {p[2]}" for p in prefs]
        sections.append("## USER PREFERENCES\n" + "\n".join(lines))

    # ACTIVE ALERTS
    alerts = get_recent_alerts(limit=3)
    unacked = [a for a in alerts if not a[5]]
    if unacked:
        lines = [f"- [{a[3]}] {a[2]}" for a in unacked]
        sections.append("## ACTIVE ALERTS\n" + "\n".join(lines))

    # KNOWLEDGE BASE — only when a query is given, and only if model is already cached
    if query:
        try:
            from config import DATA_DIR
            import os
            model_cache = os.path.join(DATA_DIR, "models")
            model_cached = os.path.exists(model_cache) and any(
                f.startswith("sentence") or f.startswith("all-MiniLM")
                for f in os.listdir(model_cache)
            ) if os.path.exists(model_cache) else False

            if model_cached:
                from knowledge import search_and_format
                knowledge_context = search_and_format(query, n_results=4)
                if knowledge_context:
                    sections.append(
                        "## KNOWLEDGE BASE (uploaded documents)\n"
                        + knowledge_context
                    )
        except Exception as e:
            print(f"[CONTEXT] Knowledge search failed: {e}")

    return "\n\n".join(sections)


# =============================
# SYSTEM PROMPT
# =============================
def build_system_prompt(query=None):
    context = build_context(query=query)

    return (
        "You are ORA — Oigara's Responsive Assistant.\n"
        "You are a private AI assistant for Elisha Lambert Oigara, "
        "a Software Engineer based in Nairobi, Kenya.\n\n"

        "## BEHAVIOUR RULES\n"
        "- Be precise, concise, and factual.\n"
        "- Use the context provided below to answer questions about Elisha, "
        "his tasks, events, and preferences.\n"
        "- If information is NOT in the context, say so clearly — "
        "do NOT invent details, filenames, or document references.\n"
        "- When answering from uploaded documents (KNOWLEDGE BASE section), "
        "mention the filename naturally, e.g. 'According to ORA Report.pdf...'.\n"
        "- When answering from profile/memory (USER PROFILE section), "
        "answer directly — do NOT fabricate a PDF or file citation.\n"
        "- Keep responses under 200 words unless the user asks for detail.\n\n"

        "## CURRENT CONTEXT\n"
        f"{context}\n\n"

        "Respond as ORA. Be helpful, direct, and grounded in the context above."
    )