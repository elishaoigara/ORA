import time
from datetime import datetime
from telegram_bot import notify

# Track what was already sent to avoid spam
_sent_today = set()
_last_check = 0
CHECK_INTERVAL = 300  # check every 5 minutes


def should_send(key):
    """Only send each notification type once per day."""
    today = datetime.now().date().isoformat()
    full_key = f"{today}:{key}"
    if full_key in _sent_today:
        return False
    _sent_today.add(full_key)
    return True


def run_autonomous_notifications():
    """
    ORA decides on its own what to send you.
    Runs every 5 minutes inside the scheduler.
    """
    global _last_check

    now = time.time()
    if now - _last_check < CHECK_INTERVAL:
        return
    _last_check = now

    from intelligence.prediction_engine import predict_needs
    from database import get_tasks
    from decision_engine import decide
    import psutil

    predictions = predict_needs()

    for pred in predictions:
        ptype = pred["type"]
        msg = pred["message"]
        confidence = pred["confidence"]
        action = pred["action"]

        if confidence < 0.7:
            continue

        if action == "alert":
            if should_send(ptype):
                notify(f"ORA ALERT: {msg}", is_alert=True)
                print(f"[Notifier] ALERT sent: {ptype}")

        elif action == "notify":
            if should_send(ptype):
                notify(msg)
                print(f"[Notifier] Notify sent: {ptype}")

        elif action == "brief":
            if should_send(ptype):
                tasks = get_tasks("pending")
                brief = f"Good morning, Elisha.\n\n"
                if tasks:
                    brief += f"You have {len(tasks)} pending tasks:\n"
                    for t in tasks[:3]:
                        due = f" (due {t[4][11:16]})" if t[4] else ""
                        brief += f"- {t[1]}{due}\n"
                else:
                    brief += "No pending tasks.\n"

                # System status
                cpu = psutil.cpu_percent(interval=1)
                ram = psutil.virtual_memory().percent
                brief += f"\nSystem: CPU {cpu}% | RAM {ram}%"

                notify(brief)
                print("[Notifier] Morning brief sent")