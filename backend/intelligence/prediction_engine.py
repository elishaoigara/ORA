"""
ORA Prediction Engine — Phase 2
Generates predictions from patterns and fires Telegram alerts.
Render free tier safe:
  - No AI calls — pure rule + data based
  - Cooldown between notifications (prevents spam)
  - Called from scheduler, not per-request
"""

import time
from datetime import datetime
from database import get_tasks
from memory.preferences import get_preference

# ── Cooldown (prevent duplicate alerts same day) ─────────────
_last_fired: dict[str, float] = {}
_COOLDOWN_SECONDS = 6 * 3600   # 6 hours per prediction type


def _can_fire(key: str) -> bool:
    now = time.time()
    if now - _last_fired.get(key, 0) > _COOLDOWN_SECONDS:
        _last_fired[key] = now
        return True
    return False


# ── Predictions ───────────────────────────────────────────────
def predict_needs() -> list[dict]:
    """
    Returns predictions sorted by confidence.
    Same interface as before — now also fires Telegram for high-confidence ones.
    """
    predictions = []
    now = datetime.now()
    hour = now.hour

    # Time-based
    if 6 <= hour <= 8:
        predictions.append({
            "type": "morning_brief",
            "message": "Good morning Elisha. Ready for your daily briefing?",
            "confidence": 0.9,
            "action": "brief",
        })

    if 21 <= hour <= 23:
        predictions.append({
            "type": "night_work",
            "message": "Late night session detected. Deep work mode?",
            "confidence": 0.75,
            "action": "notify",
        })

    # Task-based
    tasks = get_tasks("pending")

    if len(tasks) > 5:
        predictions.append({
            "type": "task_overload",
            "message": f"You have {len(tasks)} pending tasks. Want me to prioritize them?",
            "confidence": 0.85,
            "action": "notify",
        })

    # Overdue tasks
    overdue = []
    for t in tasks:
        if t[4]:
            try:
                if datetime.fromisoformat(t[4]) < now:
                    overdue.append(t[1])
            except Exception:
                pass

    if overdue:
        predictions.append({
            "type": "overdue_tasks",
            "message": f"Overdue: {', '.join(overdue[:3])}",
            "confidence": 0.95,
            "action": "alert",
        })

    # Peak hour
    active_hour = get_preference("behavior", "active_hour")
    if active_hour:
        try:
            if int(active_hour) == hour:
                predictions.append({
                    "type": "peak_time",
                    "message": "This is your peak productivity hour. Focus on high-priority tasks.",
                    "confidence": 0.8,
                    "action": "notify",
                })
        except Exception:
            pass

    # Delay pattern warning
    delay_pattern = get_preference("behavior", "delay_pattern")
    if delay_pattern:
        stalled = [t for t in tasks if delay_pattern in t[1].lower()]
        if stalled:
            predictions.append({
                "type": "delay_warning",
                "message": f"You tend to delay tasks about '{delay_pattern}'. {len(stalled)} pending.",
                "confidence": 0.7,
                "action": "notify",
            })

    predictions.sort(key=lambda x: x["confidence"], reverse=True)
    return predictions


def run_predictions():
    """
    Called by scheduler. Fires Telegram for high-confidence predictions.
    Max 1 alert per type per 6 hours.
    """
    predictions = predict_needs()
    if not predictions:
        return

    try:
        from telegram_bot import notify
    except Exception as e:
        print(f"[PREDICT] telegram import failed: {e}")
        return

    for p in predictions:
        if p["confidence"] >= 0.85 and _can_fire(p["type"]):
            prefix = "🔴 " if p["action"] == "alert" else "💡 "
            notify(f"{prefix}{p['message']}", is_alert=(p["action"] == "alert"))