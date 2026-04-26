"""
ORA Agent — Unified Autonomous Loop (Phase 1)

Runs every 5 minutes via the scheduler.
Cycle: gather_context() → decide() → execute()

Design rules:
- Rules first, AI only when truly needed (see decide())
- Every failure is isolated — one bad source never kills the loop
- All Telegram notifications go through telegram_bot.notify()
- No infinite loops here — APScheduler owns the timing
"""

from __future__ import annotations

import traceback
from datetime import datetime
from typing import Any

# ─────────────────────────────────────────────────────────────
# 1. GATHER CONTEXT
# ─────────────────────────────────────────────────────────────

def gather_context() -> dict[str, Any]:
    """
    Pull everything ORA knows right now into a single dict.
    Each source is wrapped individually — a broken source returns
    a safe empty value rather than crashing the whole loop.
    """
    ctx: dict[str, Any] = {
        "timestamp": datetime.now().isoformat(),
        "hour": datetime.now().hour,
    }

    # Tasks (pending only, top 10 by priority)
    try:
        from intelligence.priority_engine import get_prioritized_tasks
        ctx["tasks"] = get_prioritized_tasks()        # list of tuples
    except Exception:
        print("[AGENT] gather_context: tasks failed")
        print(traceback.format_exc())
        ctx["tasks"] = []

    # Overdue tasks
    try:
        from database import get_tasks
        now = datetime.now()
        all_pending = get_tasks("pending")
        ctx["overdue"] = [
            t for t in all_pending
            if t[4] and _is_overdue(t[4], now)
        ]
    except Exception:
        print("[AGENT] gather_context: overdue check failed")
        ctx["overdue"] = []

    # Active goals
    try:
        from intelligence.goals_engine import get_goals
        ctx["goals"] = get_goals("active")            # list of dicts
    except Exception:
        print("[AGENT] gather_context: goals failed")
        ctx["goals"] = []

    # Recent memory events (last 10)
    try:
        from memory.events import get_recent_events
        ctx["memory"] = get_recent_events(limit=10)   # list of tuples
    except Exception:
        print("[AGENT] gather_context: memory failed")
        ctx["memory"] = []

    # Unacknowledged alerts
    try:
        from database import get_recent_alerts
        all_alerts = get_recent_alerts(limit=20)
        ctx["alerts"] = [a for a in all_alerts if not a[5]]  # a[5] = acknowledged
    except Exception:
        print("[AGENT] gather_context: alerts failed")
        ctx["alerts"] = []

    # M-Pesa spend check
    try:
        from mpesa_engine import check_spend_alert
        ctx["spend_alert"] = check_spend_alert()      # dict or None
    except Exception:
        ctx["spend_alert"] = None

    # Predictions from prediction engine
    try:
        from intelligence.prediction_engine import predict_needs
        ctx["predictions"] = predict_needs()          # list of dicts
    except Exception:
        print("[AGENT] gather_context: predictions failed")
        ctx["predictions"] = []

    # User profile (name, timezone, wake/sleep times)
    try:
        from memory.profile import get_all_profile
        ctx["profile"] = get_all_profile()            # dict
    except Exception:
        ctx["profile"] = {}

    return ctx


# ─────────────────────────────────────────────────────────────
# 2. DECIDE
# ─────────────────────────────────────────────────────────────

def decide(ctx: dict[str, Any]) -> list[dict]:
    """
    Rule-based decision engine. Returns a list of actions to execute.
    Ordered by priority: spend alerts → overdue tasks → high-priority
    tasks → predictions → goal nudges.

    AI is NOT called here. Rules are fast, free, and predictable.
    AI is reserved for the /api/chat endpoint where the user
    explicitly asks a question.
    """
    actions: list[dict] = []
    now_hour = ctx.get("hour", datetime.now().hour)

    # ── Rule 1: Spend spike alert ────────────────────────────
    spend_alert = ctx.get("spend_alert")
    if spend_alert:
        actions.append({
            "type":     "alert",
            "key":      "spend_spike",
            "message":  spend_alert["message"],
            "severity": spend_alert.get("severity", "high"),
        })

    # ── Rule 2: Overdue tasks ────────────────────────────────
    overdue = ctx.get("overdue", [])
    if overdue:
        titles = ", ".join(t[1][:40] for t in overdue[:3])
        suffix = f" (+{len(overdue) - 3} more)" if len(overdue) > 3 else ""
        actions.append({
            "type":     "alert",
            "key":      "overdue_tasks",
            "message":  f"⚠️ Overdue: {titles}{suffix}",
            "severity": "high",
        })

    # ── Rule 3: High-priority task nudge (once per morning) ──
    if 8 <= now_hour <= 9:
        tasks = ctx.get("tasks", [])
        if tasks:
            top = tasks[0]
            actions.append({
                "type":    "notify",
                "key":     "morning_top_task",
                "message": f"🎯 Top priority today: {top[1][:60]}",
            })

    # ── Rule 4: High-confidence predictions ─────────────────
    for pred in ctx.get("predictions", []):
        if pred.get("confidence", 0) >= 0.85:
            actions.append({
                "type":    "alert" if pred["action"] == "alert" else "notify",
                "key":     pred["type"],
                "message": pred["message"],
                "severity": "high" if pred["action"] == "alert" else "medium",
            })

    # ── Rule 5: Too many pending tasks warning ───────────────
    tasks = ctx.get("tasks", [])
    if len(tasks) >= 8:
        actions.append({
            "type":    "notify",
            "key":     "task_backlog",
            "message": f"📋 You have {len(tasks)} pending tasks. Consider reviewing your list.",
        })

    # ── Rule 6: Goal progress nudge (once per afternoon) ────
    if 14 <= now_hour <= 15:
        goals = ctx.get("goals", [])
        stalled = [g for g in goals if g.get("progress", 0) < 10 and g.get("due_at")]
        if stalled:
            g = stalled[0]
            due = g["due_at"][:10] if g.get("due_at") else "no deadline"
            actions.append({
                "type":    "notify",
                "key":     f"goal_stalled_{g['id']}",
                "message": f"🎯 Goal at 0% progress: '{g['goal'][:60]}' (due {due})",
            })

    return actions


# ─────────────────────────────────────────────────────────────
# 3. EXECUTE
# ─────────────────────────────────────────────────────────────

def execute(actions: list[dict]) -> None:
    """
    Execute the list of actions produced by decide().
    Each action is isolated — one failure doesn't stop the rest.

    Action types:
      "alert"  → log to DB + Telegram with alert prefix
      "notify" → Telegram notify only (no DB log)
      "log"    → DB only, no Telegram
    """
    if not actions:
        return

    for action in actions:
        try:
            atype   = action.get("type", "notify")
            message = action.get("message", "")
            key     = action.get("key", "unknown")

            if not message:
                continue

            if atype == "alert":
                # Log to DB + notify via Telegram
                try:
                    from database import log_alert
                    from telegram_bot import notify
                    log_alert(
                        rule_name=f"agent:{key}",
                        message=message,
                        severity=action.get("severity", "medium"),
                    )
                    notify(message, is_alert=True)
                except Exception:
                    print(f"[AGENT] execute alert failed: {key}")
                    print(traceback.format_exc())

            elif atype == "notify":
                try:
                    from telegram_bot import notify
                    notify(message, is_alert=False)
                except Exception:
                    print(f"[AGENT] execute notify failed: {key}")
                    print(traceback.format_exc())

            elif atype == "log":
                try:
                    from database import log_alert
                    log_alert(
                        rule_name=f"agent:{key}",
                        message=message,
                        severity=action.get("severity", "low"),
                    )
                except Exception:
                    print(f"[AGENT] execute log failed: {key}")
                    print(traceback.format_exc())

        except Exception:
            print(f"[AGENT] execute: unexpected error on action {action}")
            print(traceback.format_exc())


# ─────────────────────────────────────────────────────────────
# 4. MAIN LOOP (called by scheduler every 5 minutes)
# ─────────────────────────────────────────────────────────────

def run_agent_cycle() -> None:
    """
    Entry point registered with APScheduler.
    One full observe → think → act cycle.
    """
    try:
        now = datetime.now().strftime("%H:%M")
        print(f"[AGENT] Cycle starting at {now}")

        ctx     = gather_context()
        actions = decide(ctx)

        task_count = len(ctx.get("tasks", []))
        over_count = len(ctx.get("overdue", []))
        goal_count = len(ctx.get("goals", []))
        print(
            f"[AGENT] Context: {task_count} tasks, "
            f"{over_count} overdue, {goal_count} goals, "
            f"{len(actions)} action(s) queued"
        )

        execute(actions)
        print(f"[AGENT] Cycle complete")

    except Exception:
        print("[AGENT] Cycle failed with unhandled exception")
        print(traceback.format_exc())


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────

def _is_overdue(due_at: str, now: datetime) -> bool:
    try:
        return datetime.fromisoformat(due_at) < now
    except Exception:
        return False