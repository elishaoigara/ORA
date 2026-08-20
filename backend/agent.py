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
    """Return the canonical structured context with legacy agent aliases."""
    try:
        from personal_context import build_personal_context
        snapshot = build_personal_context()
        google = snapshot.get("google", {})
        return {
            **snapshot,
            "timestamp": snapshot.get("generated_at", datetime.now().isoformat()),
            "hour": datetime.now().hour,
            "calendar_today": google.get("calendar_today", []),
            "calendar_imminent": google.get("calendar_imminent", []),
            "gmail": google.get("gmail", {}),
            "github": {},
        }
    except Exception:
        print("[AGENT] canonical context failed")
        print(traceback.format_exc())
        return {
            "timestamp": datetime.now().isoformat(),
            "hour": datetime.now().hour,
            "tasks": [],
            "overdue": [],
            "goals": [],
            "memory": [],
            "alerts": [],
            "spend_alert": None,
            "predictions": [],
            "profile": {},
            "calendar_today": [],
            "calendar_imminent": [],
            "gmail": {},
            "github": {},
        }


# ─────────────────────────────────────────────────────────────
# 2. DECIDE
# ─────────────────────────────────────────────────────────────

def _task_value(task: Any, key: str, index: int, default: Any = None) -> Any:
    if isinstance(task, dict):
        return task.get(key, default)
    try:
        return task[index]
    except (IndexError, TypeError):
        return default


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
        titles = ", ".join(str(_task_value(t, "title", 1, "task"))[:40] for t in overdue[:3])
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
            "message": f"🎯 Top priority today: {str(_task_value(top, 'title', 1, 'task'))[:60]}",
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

def _ledger_actions(actions: list[dict]) -> None:
    """Persist proposed low-risk personal notifications before execution."""
    try:
        from action_ledger import create_action, transition_action
        for action in actions:
            ledger = create_action(
                action_key=action.get("key", "unknown"),
                action_type=action.get("type", "notify"),
                title=action.get("message", "ORA notification")[:120],
                description="Autonomous notification generated from current personal context.",
                payload={"message": action.get("message", "")},
                risk="personal_notification",
                requires_approval=False,
                source="agent",
                idempotency_key=f"agent:{action.get('key', 'unknown')}:{datetime.now().date().isoformat()}",
            )
            action["ledger_id"] = ledger["id"]
            if ledger["status"] == "proposed":
                transition_action(ledger["id"], "approved")
    except Exception:
        print("[AGENT] action ledger unavailable")


def execute(actions: list[dict]) -> None:
    if not actions:
        return

    for action in actions:
        ledger_id = action.get("ledger_id")
        try:
            if ledger_id:
                from action_ledger import transition_action
                transition_action(ledger_id, "executing")

            atype = action.get("type", "notify")
            message = action.get("message", "")
            key = action.get("key", "unknown")
            if not message:
                continue

            if atype == "alert":
                from database import log_alert
                from telegram_bot import notify
                log_alert(f"agent:{key}", message, action.get("severity", "medium"))
                notify(message, is_alert=True)
                mark_fired(key)
                if ledger_id:
                    from action_ledger import transition_action
                    transition_action(ledger_id, "completed", {"sent": True})

            elif atype == "notify":
                from telegram_bot import notify
                notify(message, is_alert=False)
                mark_fired(key)
                if ledger_id:
                    from action_ledger import transition_action
                    transition_action(ledger_id, "completed", {"sent": True})

            elif atype == "log":
                from database import log_alert
                log_alert(f"agent:{key}", message, action.get("severity", "low"))
                mark_fired(key)
                if ledger_id:
                    from action_ledger import transition_action
                    transition_action(ledger_id, "completed", {"logged": True})

        except Exception:
            if ledger_id:
                try:
                    from action_ledger import transition_action
                    transition_action(ledger_id, "failed", error=f"{action.get('type', 'action')} failed")
                except Exception:
                    pass
            print(f"[AGENT] execute failed: {key if 'key' in locals() else 'unknown'}")
            print(traceback.format_exc())


# ─────────────────────────────────────────────────────────────
# 4. MAIN LOOP
# ─────────────────────────────────────────────────────────────

def run_agent_cycle() -> None:
    try:
        print(f"[AGENT] Cycle @ {datetime.now().strftime('%H:%M')}")

        ctx = gather_context()
        actions = decide(ctx)
        _ledger_actions(actions)

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