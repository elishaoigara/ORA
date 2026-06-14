"""
ORA Intent Parser — Upgraded
Render free tier safe: pure regex/keyword parsing, zero AI calls.
Every executor is isolated — one broken source never kills the whole parse.

Supported intents:
  add_task          "add task buy milk"
  remind            "remind me at 3pm to call John"
  complete_task     "mark task 3 as done"
  delete_task       "delete task 2"
  set_goal          "my goal is to ship the app by Friday"
  check_tasks       "what are my tasks"
  spend_summary     "how much have I spent today"
  search_docs       "search my docs for budget"
  briefing          "give me a briefing"
  calendar          "what's on my calendar"
  github            "any github activity"
  weather           "what's the weather in nairobi"
  create_content    "draft a linkedin post about ORA"
  reply_email       "/reply" or "approve reply"
"""

import re
from datetime import datetime, timedelta
from typing import Optional


# ── Intent registry (order = priority) ───────────────────────
_INTENTS = [
    # Actions first (highest specificity)
    ("complete_task",
     re.compile(
         r"\b(mark|complete|finish|done|check off)\s+(task|todo)?\s*(\d+|last|latest|first)\b"
         r"|\b(i('ve| have) (done|finished|completed))\b",
         re.I
     )),
    ("delete_task",
     re.compile(
         r"\b(delete|remove|cancel|drop)\s+(task|todo)\s*(\d+|\w+)\b",
         re.I
     )),
    ("add_task",
     re.compile(
         r"\b(add|create|new)\s+(task|todo|reminder)\b.{0,80}"
         r"|\b(i need to|i have to|don't let me forget to)\b.{0,80}",
         re.I
     )),
    ("remind",
     re.compile(
         r"\b(remind me|set a reminder|alert me)\b",
         re.I
     )),
    ("set_goal",
     re.compile(
         r"\b(my goal|i want to|i plan to|i need to finish|set goal|working towards)\b",
         re.I
     )),
    ("goal_progress",
     re.compile(
         r"\b(goal progress|how am i doing on goals?|check my goals?|goal status)\b",
         re.I
     )),
    ("check_tasks",
     re.compile(
         r"\b(what are my tasks|show tasks|pending tasks|my tasks|todo list"
         r"|what do i have to do|what's left|any tasks)\b",
         re.I
     )),
    ("spend_summary",
     re.compile(
         r"\b(how much|spent|spend|mpesa|m-pesa|transactions|balance|money today)\b",
         re.I
     )),
    ("search_docs",
     re.compile(
         r"\b(search|find|look up|check).{0,20}\b(doc|file|pdf|notes|knowledge|uploaded)\b",
         re.I
     )),
    ("briefing",
     re.compile(
         r"\b(briefing|brief me|full brief|status update|what'?s? my status"
         r"|catch me up|what's going on|morning brief|evening brief)\b",
         re.I
     )),
    ("calendar",
     re.compile(
         r"\b(calendar|meetings?|schedule|agenda|what'?s? on today"
         r"|any events|upcoming events)\b",
         re.I
     )),
    ("github",
     re.compile(
         r"\b(github|repos?|commits?|pull requests?|PRs?|issues?|code activity)\b",
         re.I
     )),
    ("weather",
     re.compile(
         r"\b(weather|raining|temperature|forecast|how'?s? the weather|is it hot)\b",
         re.I
     )),
    # ── Content Creation Agent ─────────────────────────────
    ("create_content",
     re.compile(
         r"\b(create|draft|write|generate|make)\s+(post|caption|linkedin|twitter|x|thread|email|content|draft)\b",
         re.I
     )),
    # ── NEW: Send new email ────────────────────────────────────
    ("send_email",
     re.compile(
         r"\b(send|email|mail|shoot an email|write an email|compose)\b.{0,60}"
         r"\b(to|@)\b"
         r"|\bemail\s+\S+@\S+\b"
         r"|\bsend.{0,30}email\b",
         re.I
     )),
    # ── NEW: Save email as draft ───────────────────────────────
    ("draft_email",
     re.compile(
         r"\b(draft|save as draft|prepare an email|compose.{0,20}don'?t send)\b",
         re.I
     )),
    # ── NEW: Gmail Reply Agent ─────────────────────────────
    ("reply_email",
     re.compile(
         r"\b(/reply|reply to email|approve reply|send reply|use suggested reply)\b",
         re.I
     )),
]

# ── Time patterns ─────────────────────────────────────────────
_TIME_PATTERNS = [
    (re.compile(r"\bat (\d{1,2}):(\d{2})\s*(am|pm)?\b", re.I), "hhmm"),
    (re.compile(r"\bat (\d{1,2})\s*(am|pm)\b", re.I),           "hh"),
    (re.compile(r"\bin (\d+)\s*(hour|hr)s?\b", re.I),           "in_hours"),
    (re.compile(r"\bin (\d+)\s*min(ute)?s?\b", re.I),           "in_mins"),
    (re.compile(r"\btomorrow\b", re.I),                          "tomorrow"),
    (re.compile(r"\bnext week\b", re.I),                         "next_week"),
    (re.compile(r"\bon (monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", re.I), "weekday"),
]

_TASK_STRIP  = re.compile(r"^(add|create|new)\s+(task|todo|reminder)\s*(to|:|for)?\s*", re.I)
_REMIND_STRIP = re.compile(r"^(remind me|set a reminder|alert me)\s*(to|about|at|:)?\s*", re.I)
_DAYS = ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"]


def parse_intent(text: str) -> Optional[dict]:
    t = text.strip()
    for intent_name, pattern in _INTENTS:
        if pattern.search(t):
            payload = _extract_payload(intent_name, t)
            return {"type": intent_name, "payload": payload, "confidence": 0.85}
    return None


def execute_intent(intent: dict) -> str:
    itype   = intent["type"]
    payload = intent["payload"]
    try:
        dispatch = {
            "send_email":    lambda: _do_send_email(payload),
            "draft_email":   lambda: _do_draft_email(payload),
            "add_task":       lambda: _do_add_task(payload),
            "remind":         lambda: _do_remind(payload),
            "complete_task":  lambda: _do_complete_task(payload),
            "delete_task":    lambda: _do_delete_task(payload),
            "set_goal":       lambda: _do_set_goal(payload),
            "goal_progress":  lambda: _do_goal_progress(),
            "check_tasks":    lambda: _do_check_tasks(),
            "spend_summary":  lambda: _do_spend_summary(),
            "search_docs":    lambda: _do_search_docs(payload),
            "briefing":       lambda: _do_briefing(),
            "calendar":       lambda: _do_calendar(),
            "github":         lambda: _do_github(),
            "weather":        lambda: _do_weather(),
            "create_content": lambda: _do_create_content(payload),
            "reply_email":    lambda: _do_reply_email(payload),   # ← NEW
        }
        fn = dispatch.get(itype)
        if fn:
            return fn()
    except Exception as e:
        print(f"[INTENT] execute_intent failed ({itype}): {e}")
    return ""


# ── Payload extractors ────────────────────────────────────────
def _extract_payload(intent_name: str, text: str) -> dict:
    if intent_name == "add_task":
        title = _TASK_STRIP.sub("", text).strip()
        title = re.sub(r"^(i need to|i have to|don't let me forget to)\s*", "", title, flags=re.I)
        title = re.sub(r"\s+", " ", title)[:120]
        return {"title": title or text[:80], "priority": _detect_priority(text)}

    if intent_name == "remind":
        when    = _extract_time(text)
        content = _REMIND_STRIP.sub("", text).strip()
        content = re.sub(r"\bat \d{1,2}(:\d{2})?\s*(am|pm)?\b", "", content, flags=re.I)
        content = re.sub(r"\bin \d+ (hour|min)\w*\b", "", content, flags=re.I)
        content = content.strip()[:120]
        return {"content": content or "reminder", "due_at": when}

    if intent_name == "complete_task":
        m = re.search(r"(\d+)", text)
        task_id = int(m.group(1)) if m else None
        last    = bool(re.search(r"\b(last|latest)\b", text, re.I))
        first   = bool(re.search(r"\b(first)\b", text, re.I))
        return {"task_id": task_id, "last": last, "first": first}

    if intent_name == "delete_task":
        m = re.search(r"(\d+)", text)
        return {"task_id": int(m.group(1)) if m else None}

    if intent_name == "set_goal":
        goal = re.sub(
            r"\b(my goal is|i want to|i plan to|i need to finish|set goal|working towards)\b",
            "", text, flags=re.I
        ).strip()
        return {"goal": goal[:200], "due_at": _extract_time(text)}

    if intent_name == "search_docs":
        query = re.sub(
            r"\b(search|find|look up|check|in my|my|the|docs?|files?|pdf|notes|knowledge|uploaded)\b",
            " ", text, flags=re.I
        ).strip()
        query = re.sub(r"\s+", " ", query)[:80]
        return {"query": query or text[:60]}

    # Content Creation Payload
    if intent_name == "create_content":
        topic = re.sub(
            r"\b(create|draft|write|generate|make)\s+(post|caption|linkedin|twitter|x|thread|email|content|draft)\b",
            "", text, flags=re.I
        ).strip()
        
        content_type = "post"
        lower = text.lower()
        if any(word in lower for word in ["linkedin", "twitter", "x"]):
            content_type = "linkedin"
        elif "email" in lower:
            content_type = "email"
        elif "caption" in lower:
            content_type = "caption"
        elif "thread" in lower:
            content_type = "thread"
            
        return {"topic": topic or text[:150], "type": content_type}

    # NEW: Send email payload
    if intent_name in ("send_email", "draft_email"):
        # Extract "to" — look for email address or "to <name>"
        email_match = re.search(r"[\w.+-]+@[\w.-]+\.\w+", text)
        to_addr = email_match.group(0) if email_match else ""

        # Extract subject — "about X", "regarding X", "re: X", or "subject: X"
        subj_match = re.search(
            r"\b(about|regarding|re:|subject:|titled?|called?)\s+([\"']?)(.{3,80?})\2",
            text, re.I
        )
        subject = subj_match.group(3).strip() if subj_match else ""

        # Extract body — "saying X", "that says X", "message: X", "body: X"
        body_match = re.search(
            r"\b(saying|that says|message:|body:|content:|tell them|write)\s+[\"']?(.{5,500})[\"']?$",
            text, re.I
        )
        body = body_match.group(2).strip() if body_match else ""

        return {
            "to": to_addr,
            "subject": subject,
            "body": body,
            "raw": text[:300],
            "needs_llm": not (to_addr and subject and body),
        }

    # NEW: Reply Email Payload
    if intent_name == "reply_email":
        return {"command": "reply", "raw": text[:200]}

    return {"raw": text[:200]}


def _detect_priority(text: str) -> str:
    t = text.lower()
    if any(w in t for w in ("urgent", "asap", "critical", "important", "high", "priority")):
        return "high"
    if any(w in t for w in ("low", "whenever", "sometime", "eventually", "no rush")):
        return "low"
    return "medium"


def _extract_time(text: str) -> Optional[str]:
    now = datetime.now()
    for pattern, kind in _TIME_PATTERNS:
        m = pattern.search(text)
        if not m:
            continue
        if kind == "hhmm":
            h, mi = int(m.group(1)), int(m.group(2))
            ampm  = (m.group(3) or "").lower()
            if ampm == "pm" and h < 12: h += 12
            if ampm == "am" and h == 12: h = 0
            dt = now.replace(hour=h, minute=mi, second=0, microsecond=0)
            if dt < now: dt += timedelta(days=1)
            return dt.isoformat()
        if kind == "hh":
            h    = int(m.group(1))
            ampm = (m.group(2) or "").lower()
            if ampm == "pm" and h < 12: h += 12
            if ampm == "am" and h == 12: h = 0
            dt = now.replace(hour=h, minute=0, second=0, microsecond=0)
            if dt < now: dt += timedelta(days=1)
            return dt.isoformat()
        if kind == "in_hours":
            return (now + timedelta(hours=int(m.group(1)))).isoformat()
        if kind == "in_mins":
            return (now + timedelta(minutes=int(m.group(1)))).isoformat()
        if kind == "tomorrow":
            return (now + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0).isoformat()
        if kind == "next_week":
            return (now + timedelta(weeks=1)).replace(hour=9, minute=0, second=0, microsecond=0).isoformat()
        if kind == "weekday":
            day_name = m.group(1).lower()
            target   = _DAYS.index(day_name)
            delta    = (target - now.weekday()) % 7 or 7
            return (now + timedelta(days=delta)).replace(hour=9, minute=0, second=0, microsecond=0).isoformat()
    return None


# ── Executors ─────────────────────────────────────────────────

def _do_add_task(payload: dict) -> str:
    from database import add_task
    title    = payload.get("title", "New task")
    priority = payload.get("priority", "medium")
    add_task(title, priority, None)
    p_label  = {"high": "🔴 high", "low": "🟢 low"}.get(priority, "🟡 medium")
    return f"Task added: \"{title}\" — {p_label} priority."


def _do_remind(payload: dict) -> str:
    from database import add_task
    content = payload.get("content", "reminder")
    due_at  = payload.get("due_at")
    add_task(content, "high", due_at)
    if due_at:
        try:
            dt       = datetime.fromisoformat(due_at)
            time_str = dt.strftime("%d %b at %H:%M")
        except Exception:
            time_str = due_at
        return f"Reminder set: \"{content}\" — {time_str}."
    return f"Reminder added: \"{content}\"."


def _do_complete_task(payload: dict) -> str:
    from database import get_tasks, complete_task
    task_id = payload.get("task_id")

    if task_id:
        complete_task(task_id)
        return f"Task #{task_id} marked complete."

    tasks = get_tasks("pending")
    if not tasks:
        return "No pending tasks to mark complete."
    if payload.get("first"):
        t = tasks[-1]
    else:
        t = tasks[0]
    complete_task(t[0])
    return f"Done — \"{t[1]}\" marked complete."


def _do_delete_task(payload: dict) -> str:
    from database import delete_task
    task_id = payload.get("task_id")
    if not task_id:
        return "Which task? Give me the task number."
    delete_task(task_id)
    return f"Task #{task_id} deleted."


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


def _do_goal_progress() -> str:
    try:
        from intelligence.goals_engine import get_goals
        goals = get_goals("active")
        if not goals:
            return "No active goals."
        lines = [f"Active goals ({len(goals)}):"]
        for g in goals[:5]:
            bar = "█" * (g.get("progress", 0) // 10) + "░" * (10 - g.get("progress", 0) // 10)
            lines.append(f"• {g['goal'][:60]} [{bar}] {g.get('progress', 0)}%")
        return "\n".join(lines)
    except Exception as e:
        print(f"[INTENT] goal_progress failed: {e}")
        return ""


def _do_check_tasks() -> str:
    try:
        from database import get_tasks
        tasks = get_tasks("pending")
        if not tasks:
            return "No pending tasks. You're clear."
        lines = [f"Pending tasks ({len(tasks)}):"]
        for t in tasks[:8]:
            due = f" — due {t[4][:10]}" if t[4] else ""
            icon = {"high": "🔴", "low": "🟢"}.get(t[2], "🟡")
            lines.append(f"{icon} [{t[0]}] {t[1]}{due}")
        if len(tasks) > 8:
            lines.append(f"...and {len(tasks) - 8} more.")
        return "\n".join(lines)
    except Exception as e:
        print(f"[INTENT] check_tasks failed: {e}")
        return ""


def _do_spend_summary() -> str:
    try:
        from mpesa_engine import get_today_spend, get_average_daily_spend
        _today = get_today_spend()
        _avg   = get_average_daily_spend()
        def safe_float(value):
            try:
                return float(value) if value is not None else None
            except (ValueError, TypeError):
                return None
        today = safe_float(_today)
        avg   = safe_float(_avg)
        lines = ["M-Pesa:"]
        if today is not None:
            lines.append(f"Today: KES {today:,.0f}")
        if avg is not None:
            diff  = (today - avg) if today is not None else 0.0
            arrow = "↑" if diff > 0 else "↓"
            lines.append(f"Daily avg: KES {avg:,.0f} {arrow}")
        return "\n".join(lines) if len(lines) > 1 else "No M-Pesa data."
    except Exception as e:
        print(f"[INTENT] spend_summary failed: {e}")
        return ""


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
    return "Nothing found for that query."


def _do_briefing() -> str:
    lines = ["Here's your current status:\n"]
    try:
        from database import get_tasks
        tasks = get_tasks("pending")
        if tasks:
            high = [t for t in tasks if t[2] == "high"]
            lines.append(f"**Tasks:** {len(tasks)} pending" + (f", {len(high)} high priority" if high else ""))
        else:
            lines.append("**Tasks:** All clear.")
    except Exception:
        pass

    try:
        from intelligence.goals_engine import get_goals
        goals = get_goals("active")
        if goals:
            lines.append(f"**Goals:** {len(goals)} active")
    except Exception:
        pass

    try:
        from database import get_recent_alerts
        alerts = get_recent_alerts(limit=10)
        unacked = [a for a in alerts if not a[5]]
        if unacked:
            lines.append(f"**Alerts:** {len(unacked)} unacknowledged")
    except Exception:
        pass

    try:
        from connectors.calendar import get_events_today
        events = get_events_today()
        if events:
            lines.append(f"**Calendar:** {len(events)} event(s) today")
    except Exception:
        pass

    try:
        from mpesa_engine import get_today_spend
        spend = get_today_spend()
        if spend is not None:
            lines.append(f"**Spend:** KES {spend:,.0f} today")
    except Exception:
        pass

    return "\n".join(lines)


def _do_calendar() -> str:
    try:
        from connectors.calendar import get_events_today, format_events_for_context
        events = get_events_today()
        if not events:
            return "Nothing on the calendar today."
        return format_events_for_context(events)
    except Exception as e:
        print(f"[INTENT] calendar failed: {e}")
        return "Calendar not connected. Check Google auth."


def _do_github() -> str:
    try:
        from connectors.github import get_github_summary
        result = get_github_summary()
        if result:
            return str(result)[:500]
        return "No recent GitHub activity."
    except Exception as e:
        print(f"[INTENT] github failed: {e}")
        return "GitHub connector not available."


def _do_weather() -> str:
    try:
        from connectors.weather import get_weather
        result = get_weather()
        if result:
            return str(result)[:300]
        return "Weather data unavailable."
    except Exception as e:
        print(f"[INTENT] weather failed: {e}")
        return "Weather connector not available."


# ── Content Creation Executor ─────────────────────────────
def _do_create_content(payload: dict) -> str:
    try:
        from agents.content_agent import create_draft
        topic = payload.get("topic", "general update")
        content_type = payload.get("type", "post")
        
        result = create_draft(topic=topic, content_type=content_type)
        
        if result.get("status") == "success":
            draft_preview = result["draft"][:450]
            if len(result["draft"]) > 450:
                draft_preview += "..."
            return f"""✅ **Content Draft Created** (ID: {result['id']})

**Type:** {content_type.title()}
**Topic:** {topic}

{draft_preview}
"""
        else:
            return f"❌ Content draft failed: {result.get('error', 'Unknown error')}"
    except Exception as e:
        print(f"[INTENT] _do_create_content failed: {e}")
        return "Content creation agent is currently unavailable. Please try again later."


# ── NEW: Gmail Reply Executor ─────────────────────────────
def _do_send_email(payload: dict) -> str:
    """
    Send a new email. If regex couldn't extract all fields, falls back to
    asking Groq to extract them from the raw user text.
    """
    to      = payload.get("to", "").strip()
    subject = payload.get("subject", "").strip()
    body    = payload.get("body", "").strip()
    raw     = payload.get("raw", "")

    # If any field missing, use LLM to extract
    if not (to and subject and body):
        try:
            from groq import Groq
            from config import GROQ_API_KEY, GROQ_MODEL_PRIMARY
            client = Groq(api_key=GROQ_API_KEY)
            prompt = (
                "Extract the email fields from this message. "
                "Reply ONLY with JSON: {\"to\": \"...\", \"subject\": \"...\", \"body\": \"...\"}\n\n"
                f"Message: {raw}"
            )
            resp = client.chat.completions.create(
                model=GROQ_MODEL_PRIMARY or "llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300, temperature=0.1,
            )
            import json, re as _re
            raw_json = resp.choices[0].message.content or "{}"
            # Strip markdown code fences if present
            raw_json = _re.sub(r"```(?:json)?|```", "", raw_json).strip()
            extracted = json.loads(raw_json)
            to      = to      or extracted.get("to", "").strip()
            subject = subject or extracted.get("subject", "").strip()
            body    = body    or extracted.get("body", "").strip()
        except Exception as e:
            print(f"[INTENT send_email] LLM extract failed: {e}")

    if not to:
        return "❌ I couldn't find a recipient email address. Try: *email john@example.com about Meeting subject saying Hi John...*"
    if not subject:
        return f"❌ What's the subject? Try: *email {to} about [subject] saying [body]*"
    if not body:
        return f"❌ What should I say? Try: *email {to} about {subject} saying [your message]*"

    from connectors.gmail import send_new_email
    result = send_new_email(to=to, subject=subject, body=body)
    if result.get("ok"):
        return (
            f"✅ Email sent!\n\n"
            f"*To:* {to}\n"
            f"*Subject:* {subject}\n"
            f"*Preview:* _{body[:120]}{'...' if len(body) > 120 else ''}_"
        )
    return f"❌ Failed to send email: {result.get('error', 'unknown error')}"


def _do_draft_email(payload: dict) -> str:
    """Save an email as a draft — same extraction logic as send but saves instead."""
    to      = payload.get("to", "").strip()
    subject = payload.get("subject", "").strip()
    body    = payload.get("body", "").strip()
    raw     = payload.get("raw", "")

    if not (to and subject and body):
        try:
            from groq import Groq
            from config import GROQ_API_KEY, GROQ_MODEL_PRIMARY
            import json, re as _re
            client = Groq(api_key=GROQ_API_KEY)
            prompt = (
                "Extract email fields from this message. "
                "Reply ONLY with JSON: {\"to\": \"...\", \"subject\": \"...\", \"body\": \"...\"}\n\n"
                f"Message: {raw}"
            )
            resp = client.chat.completions.create(
                model=GROQ_MODEL_PRIMARY or "llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300, temperature=0.1,
            )
            raw_json = _re.sub(r"```(?:json)?|```", "", resp.choices[0].message.content or "{}").strip()
            extracted = json.loads(raw_json)
            to      = to      or extracted.get("to", "").strip()
            subject = subject or extracted.get("subject", "").strip()
            body    = body    or extracted.get("body", "").strip()
        except Exception as e:
            print(f"[INTENT draft_email] LLM extract failed: {e}")

    if not to or not subject or not body:
        return "❌ Need recipient, subject and body to save a draft."

    from connectors.gmail import create_draft
    result = create_draft(to=to, subject=subject, body=body)
    if result.get("ok"):
        return (
            f"📝 Draft saved!\n\n"
            f"*To:* {to}\n"
            f"*Subject:* {subject}\n"
            f"_Open Gmail to review and send._"
        )
    return f"❌ Draft failed: {result.get('error', 'unknown error')}"


def _do_reply_email(payload: dict) -> str:
    """Handle /reply or approve reply commands."""
    try:
        from connectors.gmail import get_pending_replies, approve_and_send_reply
        
        pending = get_pending_replies()
        
        if not pending:
            return "✅ No pending email replies at the moment."

        # For simplicity, approve the most recent suggested reply
        latest = pending[0]
        success = approve_and_send_reply(latest["id"])
        
        if success:
            return f"""✅ **Reply Approved**

Subject: {latest['subject'][:90]}...

The reply has been marked as approved. 
(Actual sending via Gmail will be added in the next phase.)"""
        else:
            return "❌ Failed to approve the reply. Please try again."
            
    except Exception as e:
        print(f"[INTENT] _do_reply_email failed: {e}")
        return "Reply system is temporarily unavailable."


# Keep all other _do_ functions unchanged below...