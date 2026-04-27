"""
ORA Intent Parser — Phase 1
Detects action intents from natural chat messages and executes them.
Render free tier safe: no AI calls for parsing (pure regex/keyword),
AI only used for ambiguous cases via the small 8b model.

Supported intents:
  - add_task       "add task buy milk"
  - remind         "remind me at 3pm to call John"
  - search_docs    "search my docs for budget"
  - spend_summary  "how much have I spent today"
  - set_goal       "my goal is to finish the project by Friday"
  - check_tasks    "what are my tasks"

NOTE: This file is intentionally lowercase (intent_parser.py).
      The old Intent_parser.py must be deleted to avoid import confusion
      on Linux/macOS case-sensitive file systems.
"""

import re
from datetime import datetime, timedelta
from typing import Optional


# ── Pattern registry (order matters — first match wins) ──────
_INTENTS = [
    ("add_task",
     re.compile(
         r"\b(add|create|new)\s+(task|todo|reminder)\b.{0,60}",
         re.I
     )),
    ("remind",
     re.compile(
         r"\b(remind me|set a reminder|alert me)\b",
         re.I
     )),
    ("search_docs",
     re.compile(
         r"\b(search|find|look up|check).{0,20}\b(doc|file|pdf|notes|knowledge|uploaded)\b",
         re.I
     )),
    ("spend_summary",
     re.compile(
         r"\b(how much|spent|spend|mpesa|transactions|balance)\b",
         re.I
     )),
    ("set_goal",
     re.compile(
         r"\b(my goal|i want to|i plan to|i need to finish|set goal)\b",
         re.I
     )),
    ("check_tasks",
     re.compile(
         r"\b(what are my tasks|show tasks|pending tasks|my tasks|todo list)\b",
         re.I
     )),
]

# ── Time extraction patterns ──────────────────────────────────
_TIME_PATTERNS = [
    (re.compile(r"\bat (\d{1,2}):(\d{2})\s*(am|pm)?\b", re.I), "hhmm"),
    (re.compile(r"\bat (\d{1,2})\s*(am|pm)\b", re.I),           "hh"),
    (re.compile(r"\bin (\d+)\s*(hour|hr)s?\b", re.I),           "in_hours"),
    (re.compile(r"\bin (\d+)\s*min(ute)?s?\b", re.I),           "in_mins"),
    (re.compile(r"\btomorrow\b", re.I),                          "tomorrow"),
]

# ── Task content extraction ───────────────────────────────────
_TASK_STRIP = re.compile(
    r"^(add|create|new)\s+(task|todo|reminder)\s*(to|:)?\s*",
    re.I
)
_REMIND_STRIP = re.compile(
    r"^(remind me|set a reminder|alert me)\s*(to|about|at|:)?\s*",
    re.I
)


def parse_intent(text: str) -> Optional[dict]:
    """
    Returns an intent dict or None if no action detected.
    {type, payload, confidence}
    """
    t = text.strip()

    for intent_name, pattern in _INTENTS:
        if pattern.search(t):
            payload = _extract_payload(intent_name, t)
            return {
                "type": intent_name,
                "payload": payload,
                "confidence": 0.85,
            }

    return None


def execute_intent(intent: dict) -> str:
    """
    Executes the intent and returns a human-readable confirmation.
    All DB ops are lightweight — no Groq calls here.
    """
    itype = intent["type"]
    payload = intent["payload"]

    try:
        if itype == "add_task":
            return _do_add_task(payload)

        if itype == "remind":
            return _do_remind(payload)

        if itype == "search_docs":
            return _do_search_docs(payload)

        if itype == "spend_summary":
            return _do_spend_summary()

        if itype == "set_goal":
            return _do_set_goal(payload)

        if itype == "check_tasks":
            return _do_check_tasks()

    except Exception as e:
        print(f"[INTENT] execute_intent failed ({itype}): {e}")
        return ""

    return ""


# ── Payload extractors ────────────────────────────────────────

def _extract_payload(intent_name: str, text: str) -> dict:
    if intent_name == "add_task":
        title = _TASK_STRIP.sub("", text).strip()
        title = re.sub(r"\s+", " ", title)[:120]
        return {"title": title or text[:80], "priority": _detect_priority(text)}

    if intent_name == "remind":
        when = _extract_time(text)
        content = _REMIND_STRIP.sub("", text).strip()
        content = re.sub(r"\bat \d{1,2}(:\d{2})?\s*(am|pm)?\b", "", content, flags=re.I)
        content = re.sub(r"\bin \d+ (hour|min)\w*\b", "", content, flags=re.I)
        content = content.strip()[:120]
        return {"content": content or "reminder", "due_at": when}

    if intent_name == "search_docs":
        query = re.sub(
            r"\b(search|find|look up|check|in my|my|the|docs?|files?|pdf|notes|knowledge|uploaded)\b",
            " ", text, flags=re.I
        ).strip()
        query = re.sub(r"\s+", " ", query)[:80]
        return {"query": query or text[:60]}

    if intent_name == "set_goal":
        goal = re.sub(
            r"\b(my goal is|i want to|i plan to|i need to finish|set goal)\b",
            "", text, flags=re.I
        )
        goal = goal.strip()[:200]
        due = _extract_time(text)
        return {"goal": goal, "due_at": due}

    return {"raw": text[:200]}


def _detect_priority(text: str) -> str:
    t = text.lower()
    if any(w in t for w in ("urgent", "asap", "critical", "important", "high")):
        return "high"
    if any(w in t for w in ("low", "whenever", "sometime", "eventually")):
        return "low"
    return "medium"


def _extract_time(text: str) -> Optional[str]:
    """Parse a time reference and return ISO string or None."""
    now = datetime.now()

    for pattern, kind in _TIME_PATTERNS:
        m = pattern.search(text)
        if not m:
            continue

        if kind == "hhmm":
            h, mi = int(m.group(1)), int(m.group(2))
            ampm = (m.group(3) or "").lower()
            if ampm == "pm" and h < 12:
                h += 12
            if ampm == "am" and h == 12:
                h = 0
            dt = now.replace(hour=h, minute=mi, second=0, microsecond=0)
            if dt < now:
                dt += timedelta(days=1)
            return dt.isoformat()

        if kind == "hh":
            h = int(m.group(1))
            ampm = (m.group(2) or "").lower()
            if ampm == "pm" and h < 12:
                h += 12
            if ampm == "am" and h == 12:
                h = 0
            dt = now.replace(hour=h, minute=0, second=0, microsecond=0)
            if dt < now:
                dt += timedelta(days=1)
            return dt.isoformat()

        if kind == "in_hours":
            return (now + timedelta(hours=int(m.group(1)))).isoformat()

        if kind == "in_mins":
            return (now + timedelta(minutes=int(m.group(1)))).isoformat()

        if kind == "tomorrow":
            return (now + timedelta(days=1)).replace(
                hour=9, minute=0, second=0, microsecond=0
            ).isoformat()

    return None


# ── Executors ─────────────────────────────────────────────────

def _do_add_task(payload: dict) -> str:
    from database import add_task
    title = payload.get("title", "New task")
    priority = payload.get("priority", "medium")
    add_task(title, priority, None)
    return f"Task added: \"{title}\" [{priority} priority]"


def _do_remind(payload: dict) -> str:
    from database import add_task
    content = payload.get("content", "reminder")
    due_at = payload.get("due_at")
    add_task(content, "high", due_at)
    if due_at:
        try:
            dt = datetime.fromisoformat(due_at)
            time_str = dt.strftime("%d %b at %H:%M")
        except Exception:
            time_str = due_at
        return f"Reminder set: \"{content}\" on {time_str}"
    return f"Reminder added: \"{content}\""


def _do_search_docs(payload: dict) -> str:
    query = payload.get("query", "")
    if not query:
        return ""
    try:
        from knowledge.pipeline import search_and_format
        result = search_and_format(query, n_results=3)
        if result and len(result) > 20:
            return f"From your documents:\n\n{result[:600]}"
    except Exception as e:
        print(f"[INTENT] search_docs failed: {e}")
    return ""


def _do_spend_summary() -> str:
    try:
        from mpesa_engine import get_today_spend, get_average_daily_spend
        today = get_today_spend()
        avg = get_average_daily_spend()
        total = today.get("total", 0)
        txns = today.get("transactions", 0)
        lines = ["M-Pesa summary:"]
        lines.append(f"Today: KES {total:,.0f} ({txns} transactions)")
        if avg:
            lines.append(f"Daily average: KES {avg:,.0f}")
        return "\n".join(lines)
    except Exception as e:
        print(f"[INTENT] spend_summary failed: {e}")
        return ""


def _do_set_goal(payload: dict) -> str:
    goal = payload.get("goal", "").strip()
    if not goal:
        return ""
    try:
        from intelligence.goals_engine import add_goal
        add_goal(goal)
        return f"Goal noted: \"{goal[:100]}\""
    except Exception as e:
        print(f"[INTENT] set_goal failed: {e}")
        return ""


def _do_check_tasks() -> str:
    try:
        from database import get_tasks
        tasks = get_tasks("pending")
        if not tasks:
            return "No pending tasks."
        lines = [f"Pending tasks ({len(tasks)}):"]
        for t in tasks[:6]:
            due = f" — due {t[4][:10]}" if t[4] else ""
            lines.append(f"• {t[1]}{due} [{t[2]}]")
        return "\n".join(lines)
    except Exception as e:
        print(f"[INTENT] check_tasks failed: {e}")
        return ""