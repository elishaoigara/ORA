"""
ORA Context Builder — grounded, intelligent, non-hallucinating version.

Enhancements:
- Emotional state inference (lightweight, deterministic)
- Decision engine integration
- Narrative summary (human-like awareness)
- Strict grounding rules to prevent hallucination

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


# ─────────────────────────────────────────
# 🧠 LIGHTWEIGHT STATE INFERENCE (NO ML)
# ─────────────────────────────────────────
def _infer_state(overdue_count=0, task_count=0, spend_ratio=1.0, calendar_count=0):
    if overdue_count > 2:
        return "overloaded"
    if spend_ratio > 1.3:
        return "financial_pressure"
    if calendar_count > 5:
        return "busy"
    if task_count == 0:
        return "idle"
    return "balanced"


# ─────────────────────────────────────────
# 🧾 NARRATIVE SUMMARY (HUMAN-LIKE, GROUNDED)
# ─────────────────────────────────────────
def _build_summary(state, focus, overdue_count):
    lines = []

    if state == "overloaded":
        lines.append("You're carrying a bit much right now")
    elif state == "financial_pressure":
        lines.append("Spending is slightly higher than usual")
    elif state == "busy":
        lines.append("Your schedule is fairly packed today")
    elif state == "idle":
        lines.append("Things look relatively light right now")

    if focus:
        lines.append(f"Main thing to focus on: {focus}")

    if overdue_count > 0:
        lines.append(f"You have {overdue_count} overdue task(s)")

    return lines


def build_context(query=None) -> str:
    sections = []

    # TRACKING VARIABLES (for intelligence layer)
    overdue_count = 0
    task_count = 0
    calendar_count = 0
    spend_ratio = 1.0
    spend_today = 0
    spend_avg = 0
    unread_count = 0

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

    # WEATHER
    try:
        from connectors.weather import get_weather_summary
        weather = get_weather_summary()
        if weather:
            sections.append(f"## WEATHER (Nairobi)\n- {weather}")
    except Exception:
        pass

    # CALENDAR
    try:
        from connectors.calendar import get_events_today, format_events_for_context
        events = get_events_today()
        if events:
            calendar_count = len(events)
            formatted = format_events_for_context(events)
            sections.append("## TODAY'S CALENDAR\n" + formatted)
        else:
            sections.append("## TODAY'S CALENDAR\n- No events today (or calendar not connected)")
    except Exception:
        sections.append("## TODAY'S CALENDAR\n- Calendar unavailable")

    # GMAIL
    try:
        from connectors.gmail import get_gmail_summary
        from connectors.google_auth import is_authorized
        if is_authorized():
            gmail = get_gmail_summary()
            if gmail and gmail.get("unread_count", 0) > 0:
                unread_count = gmail["unread_count"]
                senders = ", ".join(gmail.get("senders", [])[:3])
                lines = [f"- {unread_count} unread email(s)", f"- From: {senders}"]
                for s in gmail.get("subjects", [])[:3]:
                    lines.append(f"  • {s[:80]}")
                sections.append(_safe_section("## UNREAD EMAILS", lines))
            else:
                sections.append("## UNREAD EMAILS\n- Inbox clear")
        else:
            sections.append("## UNREAD EMAILS\n- Gmail not connected")
    except Exception:
        sections.append("## UNREAD EMAILS\n- Gmail unavailable")

    # TASKS
    try:
        from database import get_tasks
        tasks = get_tasks("pending")
        if tasks:
            task_count = len(tasks)
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
            header = f"## PENDING TASKS ({task_count} total{', ' + str(overdue_count) + ' OVERDUE' if overdue_count else ''})"
            sections.append(_safe_section(header, lines))
        else:
            sections.append("## PENDING TASKS\n- No pending tasks")
    except Exception:
        sections.append("## PENDING TASKS\n- Error loading tasks")

    # M-PESA
    try:
        from mpesa_engine import get_today_spend, get_average_daily_spend
        spend_today = float(get_today_spend() or 0) # pyright: ignore[reportArgumentType]
        spend_avg = float(get_average_daily_spend() or 0)

        lines = [f"- Today: KES {spend_today:,.0f}"]

        if spend_avg > 0:
            spend_ratio = spend_today / spend_avg
            trend = "↑ above avg" if spend_ratio > 1.3 else ("↓ below avg" if spend_ratio < 0.7 else "≈ normal")
            lines.append(f"- Daily avg: KES {spend_avg:,.0f} ({trend})")

        sections.append(_safe_section("## M-PESA SPEND", lines))
    except Exception:
        sections.append("## M-PESA SPEND\n- No spend data")

    # ─────────────────────────────────────────
    # 🧠 INTELLIGENCE LAYER (NEW, MINIMAL)
    # ─────────────────────────────────────────
    state = _infer_state(overdue_count, task_count, spend_ratio, calendar_count)

    # decision engine (safe import)
    try:
        from decision_engine import decide
        decision = decide({
            "overdue_tasks": overdue_count
        })
        focus = decision.get("primary_focus")
    except Exception:
        focus = None

    summary_lines = _build_summary(state, focus, overdue_count)

    sections.append(_safe_section("## TODAY SUMMARY", summary_lines))
    sections.append(f"## USER STATE\n- {state}")
    if focus:
        sections.append(f"## PRIORITY FOCUS\n- {focus}")

    # ─────────────────────────────────────────
    # 🧱 GROUNDED FACTS (ANTI-HALLUCINATION)
    # ─────────────────────────────────────────
    sections.append(
        "## GROUNDED FACTS\n"
        f"- Overdue tasks: {overdue_count}\n"
        f"- Pending tasks: {task_count}\n"
        f"- Calendar events: {calendar_count}\n"
        f"- Unread emails: {unread_count}\n"
        f"- Spend today: {spend_today}\n"
        f"- Spend average: {spend_avg}"
    )

    return "\n\n".join(sections)


def build_system_prompt(query=None) -> str:
    context = build_context(query=query)

    return (
        "You are ORA — Elisha's personal AI chief of staff, based in Nairobi, Kenya.\n"
        "\n"
        "PERSONALITY:\n"
        "- Direct, intelligent, warm — not emotional or dramatic\n"
        "- Speak like a trusted advisor who pays attention\n"
        "- Be calm, grounded, and observant\n"
        "\n"
        "INTELLIGENCE RULES:\n"
        "- Use ONLY the provided context\n"
        "- Connect signals carefully — do NOT assume missing links\n"
        "- Prioritize clarity over cleverness\n"
        "- Reduce cognitive load when user is overloaded\n"
        "\n"
        "INFERENCE RULES (STRICT):\n"
        "- 'overloaded' only if overdue tasks > 2\n"
        "- 'busy' only if calendar events > 5\n"
        "- 'financial_pressure' only if spend_today > 1.3 × average\n"
        "- Otherwise do NOT infer state\n"
        "\n"
        "EVIDENCE RULE:\n"
        "- Every insight must be traceable to context data\n"
        "- If no supporting data exists, do not state it\n"
        "\n"
        "HARD CONSTRAINTS:\n"
        "- Do NOT guess or assume\n"
        "- Do NOT invent missing data\n"
        "- If unsure, say: 'I don't have that data'\n"
        "\n"
        "=== LIVE CONTEXT ===\n"
        f"{context}\n"
        "=== END CONTEXT ==="
    )