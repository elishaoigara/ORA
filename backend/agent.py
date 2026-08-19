"""
ORA Agent — Unified Autonomous Loop (Phase 2: + Google Calendar + Phase 4)

Cycle every 5 minutes: gather_context() → decide() → execute()

Design rules:
- Rules first, AI only when truly needed
- Every source is isolated — one broken source never kills the loop
- Deduplication via agent_guard.py prevents notification spam
- Calendar + external context feeds both decisions AND AI system prompt
"""

from __future__ import annotations

import traceback
from datetime import datetime
from typing import Any

from agent_guard import can_fire, mark_fired


# ─────────────────────────────────────────────────────────────
# 1. GATHER CONTEXT
# ─────────────────────────────────────────────────────────────

def gather_context() -> dict[str, Any]:
    """
    Pull everything ORA knows right now into a single dict.
    Each source is individually wrapped — a broken source returns
    a safe empty value rather than crashing the whole loop.
    """
    ctx: dict[str, Any] = {
        "timestamp": datetime.now().isoformat(),
        "hour": datetime.now().hour,
    }

    # Tasks (pending, top 10 by priority score)
    try:
        from intelligence.priority_engine import get_prioritized_tasks
        ctx["tasks"] = get_prioritized_tasks()
    except Exception:
        print("[AGENT] gather_context: tasks failed")
        print(traceback.format_exc())
        ctx["tasks"] = []

    # Overdue tasks
    try:
        from database import get_tasks
        now = datetime.now()
        ctx["overdue"] = [
            t for t in get_tasks("pending")
            if t[4] and _is_overdue(t[4], now)
        ]
    except Exception:
        print("[AGENT] gather_context: overdue check failed")
        ctx["overdue"] = []

    # Active goals
    try:
        from intelligence.goals_engine import get_goals
        ctx["goals"] = get_goals("active")
    except Exception:
        print("[AGENT] gather_context: goals failed")
        ctx["goals"] = []

    # Recent memory events (last 10)
    try:
        from memory.events import get_recent_events
        ctx["memory"] = get_recent_events(limit=10)
    except Exception:
        print("[AGENT] gather_context: memory failed")
        ctx["memory"] = []

    # Unacknowledged alerts
    try:
        from database import get_recent_alerts
        all_alerts = get_recent_alerts(limit=20)
        ctx["alerts"] = [a for a in all_alerts if not a[5]]
    except Exception:
        print("[AGENT] gather_context: alerts failed")
        ctx["alerts"] = []

    # M-Pesa spend check
    try:
        from mpesa_engine import check_spend_alert
        ctx["spend_alert"] = check_spend_alert()
    except Exception:
        ctx["spend_alert"] = None

    # Predictions
    try:
        from intelligence.prediction_engine import predict_needs
        ctx["predictions"] = predict_needs()
    except Exception:
        print("[AGENT] gather_context: predictions failed")
        ctx["predictions"] = []

    # User profile
    try:
        from memory.profile import get_all_profile
        ctx["profile"] = get_all_profile()
    except Exception:
        ctx["profile"] = {}

    # ── Phase 2: Google Calendar ─────────────────────────────
    try:
        from connectors.calendar import get_events_today, get_imminent_events
        ctx["calendar_today"] = get_events_today()
        ctx["calendar_imminent"] = get_imminent_events(30)
    except Exception:
        print("[AGENT] gather_context: calendar failed")
        print(traceback.format_exc())
        ctx["calendar_today"] = []
        ctx["calendar_imminent"] = []

    # ── Phase 4: Gmail summary ───────────────────────────────
    try:
        from connectors.gmail import get_gmail_summary
        ctx["gmail"] = get_gmail_summary()
    except Exception:
        print("[AGENT] gather_context: gmail failed")
        ctx["gmail"] = {}

    # ── Phase 4: Weather ─────────────────────────────────────
    try:
        from connectors.weather import get_weather_summary
        ctx["weather"] = get_weather_summary()
    except Exception:
        print("[AGENT] gather_context: weather failed")
        ctx["weather"] = ""

    # GitHub context is intentionally omitted until its connector is deployed.
    ctx["github"] = {}

    return ctx


# ─────────────────────────────────────────────────────────────
# 2. DECIDE
# ─────────────────────────────────────────────────────────────

def decide(ctx: dict[str, Any]) -> list[dict]:
    actions: list[dict] = []
    now_hour = ctx.get("hour", datetime.now().hour)

    # Spend spike alert
    spend_alert = ctx.get("spend_alert")
    if spend_alert and can_fire("spend_spike"):
        actions.append({
            "type": "alert",
            "key": "spend_spike",
            "message": spend_alert["message"],
            "severity": spend_alert.get("severity", "high"),
        })

    # Overdue tasks
    overdue = ctx.get("overdue", [])
    if overdue and can_fire("overdue_tasks"):
        titles = ", ".join(t[1][:40] for t in overdue[:3])
        suffix = f" (+{len(overdue) - 3} more)" if len(overdue) > 3 else ""
        actions.append({
            "type": "alert",
            "key": "overdue_tasks",
            "message": f"⚠️ Overdue: {titles}{suffix}",
            "severity": "high",
        })

    # Morning top task
    tasks = ctx.get("tasks", [])
    if 8 <= now_hour <= 9 and tasks and can_fire("morning_top_task"):
        top = tasks[0]
        actions.append({
            "type": "notify",
            "key": "morning_top_task",
            "message": f"🎯 Top priority today: {top[1][:60]}",
        })

    # Predictions
    for pred in ctx.get("predictions", []):
        if pred.get("confidence", 0) >= 0.85 and can_fire(pred["type"]):
            actions.append({
                "type": "alert" if pred["action"] == "alert" else "notify",
                "key": pred["type"],
                "message": pred["message"],
                "severity": "high" if pred["action"] == "alert" else "medium",
            })

    # Task backlog
    if len(tasks) >= 8 and can_fire("task_backlog"):
        actions.append({
            "type": "notify",
            "key": "task_backlog",
            "message": f"📋 You have {len(tasks)} pending tasks. Consider reviewing your list.",
        })

    # Afternoon goal nudge
    if 14 <= now_hour <= 15:
        goals = ctx.get("goals", [])
        stalled = [g for g in goals if g.get("progress", 0) < 10 and g.get("due_at")]
        if stalled:
            g = stalled[0]
            key = f"goal_stalled_{g['id']}"
            if can_fire(key):
                due = g["due_at"][:10] if g.get("due_at") else "no deadline"
                actions.append({
                    "type": "notify",
                    "key": key,
                    "message": f"🎯 Goal at 0% progress: '{g['goal'][:60]}' (due {due})",
                })

    # Calendar reminders
    for event in ctx.get("calendar_imminent", []):
        mins = event.get("minutes_until")
        title = event.get("title", "Meeting")
        ev_id = event.get("id", title)
        key = f"meeting_{ev_id}"

        if mins is None:
            continue

        if can_fire(key):
            loc = f" @ {event['location']}" if event.get("location") else ""
            if mins <= 5:
                msg = f"🔔 Starting NOW: {title}{loc}"
            elif mins <= 15:
                msg = f"🔔 {title}{loc} in {mins} minutes"
            else:
                msg = f"📅 Coming up: {title}{loc} in {mins} minutes"

            actions.append({
                "type": "notify",
                "key": key,
                "message": msg,
            })

    # Daily calendar summary
    if now_hour == 8:
        events_today = ctx.get("calendar_today", [])
        if events_today and can_fire("calendar_daily_summary"):
            count = len(events_today)
            titles = ", ".join(e["title"][:30] for e in events_today[:3])
            suffix = f" and {count - 3} more" if count > 3 else ""
            actions.append({
                "type": "notify",
                "key": "calendar_daily_summary",
                "message": f"📅 {count} event{'s' if count > 1 else ''} today: {titles}{suffix}",
            })

    return actions


# ─────────────────────────────────────────────────────────────
# 3. EXECUTE
# ─────────────────────────────────────────────────────────────

def execute(actions: list[dict]) -> None:
    if not actions:
        return

    for action in actions:
        try:
            atype = action.get("type", "notify")
            message = action.get("message", "")
            key = action.get("key", "unknown")

            if not message:
                continue

            if atype == "alert":
                try:
                    from database import log_alert
                    from telegram_bot import notify
                    log_alert(f"agent:{key}", message, action.get("severity", "medium"))
                    notify(message, is_alert=True)
                    mark_fired(key)
                except Exception:
                    print(f"[AGENT] alert failed: {key}")
                    print(traceback.format_exc())

            elif atype == "notify":
                try:
                    from telegram_bot import notify
                    notify(message, is_alert=False)
                    mark_fired(key)
                except Exception:
                    print(f"[AGENT] notify failed: {key}")
                    print(traceback.format_exc())

            elif atype == "log":
                try:
                    from database import log_alert
                    log_alert(f"agent:{key}", message, action.get("severity", "low"))
                    mark_fired(key)
                except Exception:
                    print(f"[AGENT] log failed: {key}")
                    print(traceback.format_exc())

        except Exception:
            print(f"[AGENT] execute crash: {action}")
            print(traceback.format_exc())


# ─────────────────────────────────────────────────────────────
# 4. MAIN LOOP
# ─────────────────────────────────────────────────────────────

def run_agent_cycle() -> None:
    try:
        print(f"[AGENT] Cycle @ {datetime.now().strftime('%H:%M')}")

        ctx = gather_context()
        actions = decide(ctx)

        print(
            f"[AGENT] tasks={len(ctx.get('tasks', []))} "
            f"overdue={len(ctx.get('overdue', []))} "
            f"calendar={len(ctx.get('calendar_today', []))} "
            f"actions={len(actions)}"
        )

        execute(actions)
        print("[AGENT] Cycle complete")

    except Exception:
        print("[AGENT] CRASH")
        print(traceback.format_exc())


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────

def _is_overdue(due_at: str, now: datetime) -> bool:
    try:
        return datetime.fromisoformat(due_at) < now
    except Exception:
        return False