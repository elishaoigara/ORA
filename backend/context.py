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

    # =================
    # PROFILE
    # =================
    profile = get_all_profile()
    if profile:
        sections.append(
            "## USER PROFILE\n" +
            "\n".join([f"- {k}: {v}" for k, v in profile.items()])
        )

    # =================
    # TIME
    # =================
    now = datetime.now()
    sections.append(
        "## CURRENT TIME (Nairobi, Kenya)\n"
        f"- {now.strftime('%A, %d %B %Y at %H:%M')}"
    )

    # =================
    # GOOGLE CALENDAR (Phase 2)
    # =================
    try:
        from connectors.calendar import get_events_today, format_events_for_context
        events = get_events_today()
        if events:
            formatted = format_events_for_context(events)
            sections.append("## TODAY'S CALENDAR\n" + formatted)
    except Exception:
        pass  # Not connected yet — safe to skip

    # =================
    # IMPORTANT EVENTS
    # =================
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

    # =================
    # RECENT ACTIVITY
    # =================
    try:
        recent = get_recent_events(limit=6)
        if recent:
            sections.append(
                "## RECENT ACTIVITY\n" +
                "\n".join([f"- {e[1]}" for e in recent])
            )
    except Exception as e:
        print(f"[CONTEXT] Recent events error: {e}")

    # =================
    # PREFERENCES
    # =================
    try:
        prefs = get_preferences()
        if prefs:
            sections.append(
                "## USER PREFERENCES\n" +
                "\n".join([f"- {p[0]}/{p[1]} = {p[2]}" for p in prefs])
            )
    except Exception as e:
        print(f"[CONTEXT] Preferences error: {e}")

    # =================
    # ACTIVE ALERTS
    # =================
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

    # =================
    # KNOWLEDGE BASE (RAG)
    # =================
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
        "- Use ONLY the provided context to answer.\n"
        "- If information is missing, say: 'I don't have that in memory.'\n"
        "- Do NOT hallucinate files, documents, or events.\n"
        "- When using knowledge base, rely strictly on retrieved chunks.\n"
        "- Keep responses under 200 words unless asked for detail.\n\n"

        "## CURRENT CONTEXT\n"
        f"{context}\n\n"

        "Respond as ORA. Stay grounded in memory and retrieved knowledge."
    )