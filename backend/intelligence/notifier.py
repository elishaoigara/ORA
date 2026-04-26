"""
ORA Notifier — Phase 3: Dual-channel (Telegram + FCM push)
Render free-tier safe — no new threads, FCM is a plain HTTP call.
"""

import time
from datetime import datetime
from telegram_bot import notify as telegram_notify

_sent_today: set = set()
_last_check: float = 0
CHECK_INTERVAL = 300


def should_send(key: str) -> bool:
    today = datetime.now().date().isoformat()
    full_key = f"{today}:{key}"
    if full_key in _sent_today:
        return False
    _sent_today.add(full_key)
    return True


def dual_notify(title: str, body: str, is_alert: bool = False) -> None:
    """Send via Telegram AND FCM. Each channel is isolated — one failing won't affect the other."""
    try:
        full_msg = f"*{title}*\n{body}" if title else body
        telegram_notify(full_msg, is_alert=is_alert)
    except Exception as e:
        print(f"[NOTIFIER] Telegram error: {e}")

    try:
        from fcm import send_push
        send_push(title=title, body=body, is_alert=is_alert)
    except Exception as e:
        print(f"[NOTIFIER] FCM error: {e}")


def run_autonomous_notifications() -> None:
    global _last_check

    now = time.time()
    if now - _last_check < CHECK_INTERVAL:
        return
    _last_check = now

    try:
        from intelligence.prediction_engine import predict_needs
        predictions = predict_needs()
    except Exception as e:
        print(f"[NOTIFIER] predict_needs failed: {e}")
        return

    for pred in predictions:
        ptype      = pred.get("type", "unknown")
        msg        = pred.get("message", "")
        confidence = pred.get("confidence", 0)
        action     = pred.get("action", "notify")

        if confidence < 0.7 or not msg:
            continue

        if action == "alert" and should_send(ptype):
            dual_notify(title="ORA Alert", body=msg, is_alert=True)
            print(f"[NOTIFIER] ALERT sent (dual): {ptype}")

        elif action == "notify" and should_send(ptype):
            dual_notify(title="ORA", body=msg, is_alert=False)
            print(f"[NOTIFIER] Notify sent (dual): {ptype}")

        elif action == "brief" and should_send(ptype):
            _send_morning_brief()


def _send_morning_brief() -> None:
    try:
        from database import get_tasks
        import psutil

        tasks = get_tasks("pending")
        lines = ["Good morning, Elisha.\n"]

        if tasks:
            lines.append(f"You have {len(tasks)} pending task(s):")
            for t in tasks[:3]:
                due = f" (due {t[4][11:16]})" if t[4] else ""
                lines.append(f"• {t[1]}{due}")
        else:
            lines.append("No pending tasks.")

        cpu = psutil.cpu_percent(interval=1)
        ram = psutil.virtual_memory().percent
        lines.append(f"\nSystem: CPU {cpu:.0f}% | RAM {ram:.0f}%")

        dual_notify(title="ORA Morning Brief", body="\n".join(lines))
        print("[NOTIFIER] Morning brief sent (dual)")

    except Exception as e:
        print(f"[NOTIFIER] Morning brief error: {e}")