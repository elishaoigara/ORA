"""
ORA Core Orchestrator — The "prefrontal cortex"
Gathers signals from all engines and decides autonomous actions.
"""

import json
from datetime import datetime, timedelta
from database import get_tasks, log_alert
from memory.events import get_recent_events, log_memory_event
from memory.preferences import get_preferences


# ─────────────────────────────────────────────
# SIGNAL GATHERING
# ─────────────────────────────────────────────

def gather_signals() -> dict:
    """Pull current state from all subsystems."""
    signals = {}

    try:
        tasks = get_tasks("pending")
        overdue = []
        now = datetime.now()
        for t in tasks:
            if t[4]:
                try:
                    due = datetime.fromisoformat(t[4])
                    if due < now:
                        overdue.append(t)
                except Exception:
                    pass
        signals["tasks"] = {"total": len(tasks), "overdue": overdue, "all": tasks}
    except Exception as e:
        signals["tasks"] = {"total": 0, "overdue": [], "all": [], "error": str(e)}

    try:
        events = get_recent_events(limit=20)
        signals["events"] = events
    except Exception:
        signals["events"] = []

    try:
        prefs = get_preferences()
        signals["preferences"] = {p[1]: p[2] for p in prefs} if prefs else {}
    except Exception:
        signals["preferences"] = {}

    return signals


# ─────────────────────────────────────────────
# DECISION ENGINE
# ─────────────────────────────────────────────

def decide(signals: dict) -> list:
    actions = []
    now = datetime.now()

    # Rule 1: Overdue tasks → escalate
    overdue = signals["tasks"].get("overdue", [])
    for task in overdue[:3]:
        title = task[1]
        actions.append({
            "type": "alert",
            "message": f"⚠️ OVERDUE: '{title}' — mark done or reschedule.",
            "severity": "high"
        })

    # Rule 2: No activity in last 24h → nudge
    events = signals.get("events", [])
    if events:
        try:
            last_event_time = datetime.fromisoformat(events[0][4])
            hours_since = (now - last_event_time).total_seconds() / 3600
            if hours_since > 24:
                actions.append({
                    "type": "nudge",
                    "message": f"👁 ORA has been dormant for {int(hours_since)}h. Check in with your system.",
                    "severity": "low"
                })
        except Exception:
            pass

    # Rule 3: Too many high-priority tasks piling up
    all_tasks = signals["tasks"].get("all", [])
    high_pri = [t for t in all_tasks if t[2] == "high"]
    if len(high_pri) >= 3:
        actions.append({
            "type": "nudge",
            "message": f"🔴 {len(high_pri)} high-priority tasks queued. ORA recommends immediate triage.",
            "severity": "medium"
        })

    return actions


# ─────────────────────────────────────────────
# EXECUTION
# ─────────────────────────────────────────────

def execute_actions(actions: list):
    for action in actions:
        try:
            if action["type"] in ("alert", "nudge"):
                log_alert(
                    rule_name="core_orchestrator",
                    message=action["message"],
                    severity=action.get("severity", "medium")
                )
                try:
                    from telegram_bot import notify
                    notify(action["message"])
                except Exception:
                    pass
            log_memory_event("core", action["message"][:80], importance=5)
        except Exception as e:
            print(f"[CORE] execute error: {e}")


# ─────────────────────────────────────────────
# MAIN EVALUATE LOOP (called by scheduler)
# ─────────────────────────────────────────────

def evaluate_state():
    print("[CORE] Evaluating system state...")
    try:
        signals = gather_signals()
        actions = decide(signals)
        if actions:
            execute_actions(actions)
            print(f"[CORE] Executed {len(actions)} actions")
        else:
            print("[CORE] No actions required")
    except Exception as e:
        print(f"[CORE ERROR] {e}")


# ─────────────────────────────────────────────
# "THE NUMBER" — today's single focus task
# ─────────────────────────────────────────────

def get_the_number() -> dict | None:
    try:
        tasks = get_tasks("pending")
        if not tasks:
            return None

        now = datetime.now()
        scored = []

        for t in tasks:
            task_id, title, priority, created_at, due_at = t[0], t[1], t[2], t[3], t[4]
            score = 0

            pri_scores = {"high": 20, "medium": 10, "low": 3}
            score += pri_scores.get(priority, 0)

            if due_at:
                try:
                    due = datetime.fromisoformat(due_at)
                    if due < now:
                        days_overdue = (now - due).days
                        score += 30 + (days_overdue * 5)
                except Exception:
                    pass

            try:
                created = datetime.fromisoformat(created_at)
                days_old = (now - created).days
                score += min(days_old * 2, 20)
            except Exception:
                pass

            scored.append({
                "id": task_id,
                "title": title,
                "priority": priority,
                "due_at": due_at,
                "score": score
            })

        best = sorted(scored, key=lambda x: x["score"], reverse=True)[0]

        overdue = False
        if best["due_at"]:
            try:
                overdue = datetime.fromisoformat(best["due_at"]) < now
            except Exception:
                pass

        return {
            **best,
            "overdue": overdue,
            "reason": (
                "overdue + high priority" if overdue and best["priority"] == "high" else
                "overdue" if overdue else
                f"{best['priority']} priority"
            )
        }
    except Exception as e:
        print(f"[THE NUMBER ERROR] {e}")
        return None