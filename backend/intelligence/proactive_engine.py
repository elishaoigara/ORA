"""
ORA Proactive Engine — fires context-aware nudges.
Zero Groq calls — pure rule-based from real data.
Cooldown prevents spam.
"""

import time
from datetime import datetime

LAST_RUN = 0
COOLDOWN = 600  # 10 min between proactive checks


def run_proactive_checks():
    global LAST_RUN
    now = time.time()
    if now - LAST_RUN < COOLDOWN:
        return
    LAST_RUN = now

    try:
        from intelligence.priority_engine import get_prioritized_tasks
        from telegram_bot import notify
        from agent_guard import can_fire, mark_fired

        tasks = get_prioritized_tasks()
        if not tasks:
            return

        hour = datetime.now().hour

        # Morning focus nudge (7-9am)
        if 7 <= hour <= 9:
            key = f"morning_focus_{datetime.now().date()}"
            if can_fire(key):
                top = tasks[0][1] if tasks else None
                if top:
                    notify(f"☀️ Morning focus: {top}", is_alert=False)
                    mark_fired(key)
            return

        # Overdue task alert
        now_dt = datetime.now()
        try:
            from database import get_tasks
            pending = get_tasks("pending")
            overdue = [t for t in pending if t[4] and _is_overdue(t[4], now_dt)]
            if overdue:
                key = f"overdue_alert_{datetime.now().date()}"
                if can_fire(key):
                    names = ", ".join(t[1][:30] for t in overdue[:3])
                    notify(f"⚠️ {len(overdue)} overdue task(s): {names}", is_alert=True)
                    mark_fired(key)
                return
        except Exception:
            pass

        # Evening wrap-up (6-8pm)
        if 18 <= hour <= 20:
            key = f"evening_wrap_{datetime.now().date()}"
            if can_fire(key):
                try:
                    from database import get_tasks
                    pending = get_tasks("pending")
                    high = [t for t in pending if t[2] == "high"]
                    if high:
                        notify(f"🔴 End of day: {len(high)} high-priority task(s) still pending.", is_alert=False)
                        mark_fired(key)
                except Exception:
                    pass
            return

        # General top-task nudge (business hours only)
        if 9 <= hour <= 17:
            top_title = tasks[0][1] if tasks else None
            if top_title:
                key = f"focus_{top_title[:30]}_{datetime.now().date()}"
                if can_fire(key):
                    notify(f"⚡ Top priority: {top_title}", is_alert=False)
                    mark_fired(key)

    except Exception as e:
        print(f"[PROACTIVE] check failed: {e}")


def _is_overdue(due_at: str, now: datetime) -> bool:
    try:
        return datetime.fromisoformat(due_at) < now
    except Exception:
        return False
