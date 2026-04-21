from datetime import datetime
from database import get_tasks, get_conversation_history
from memory.preferences import get_preference
import json

def predict_needs():
    """
    ORA predicts what you need right now based on:
    - Time of day
    - Pending tasks
    - Past behavior patterns
    - Conversation history
    Returns a list of predictions with confidence scores.
    """
    predictions = []
    now = datetime.now()
    hour = now.hour
    weekday = now.weekday()  # 0=Monday, 6=Sunday

    # --- TIME-BASED PREDICTIONS ---
    if 6 <= hour <= 8:
        predictions.append({
            "type": "morning_brief",
            "message": "Good morning Elisha. Ready for your daily briefing?",
            "confidence": 0.9,
            "action": "brief"
        })

    if 12 <= hour <= 13:
        predictions.append({
            "type": "lunch_reminder",
            "message": "It is around lunch time. Have you eaten?",
            "confidence": 0.7,
            "action": "notify"
        })

    if 21 <= hour <= 23:
        predictions.append({
            "type": "night_work",
            "message": "Late night session detected. Deep work mode?",
            "confidence": 0.75,
            "action": "notify"
        })

    # --- TASK-BASED PREDICTIONS ---
    tasks = get_tasks("pending")

    if len(tasks) > 5:
        predictions.append({
            "type": "task_overload",
            "message": f"You have {len(tasks)} pending tasks. Want me to prioritize them?",
            "confidence": 0.85,
            "action": "notify"
        })

    # Check for overdue tasks
    overdue = []
    for t in tasks:
        if t[4]:
            try:
                due = datetime.fromisoformat(t[4])
                if due < now:
                    overdue.append(t[1])
            except:
                pass

    if overdue:
        predictions.append({
            "type": "overdue_tasks",
            "message": f"Overdue: {', '.join(overdue[:3])}",
            "confidence": 0.95,
            "action": "alert"
        })

    # --- BEHAVIORAL PREDICTIONS ---
    active_hour = get_preference("behavior", "active_hour")
    if active_hour and int(active_hour) == hour:
        predictions.append({
            "type": "peak_time",
            "message": f"This is your peak productivity hour. Focus on high-priority tasks.",
            "confidence": 0.8,
            "action": "notify"
        })

    # Sort by confidence
    predictions.sort(key=lambda x: x["confidence"], reverse=True)
    return predictions