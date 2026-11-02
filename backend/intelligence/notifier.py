"""
ORA Notifier — Phase 3: Multi-channel (Telegram + WhatsApp + FCM push)
Render free-tier safe — no new threads, WhatsApp/FCM are plain HTTP calls.
"""

import os
import time
from datetime import datetime

def telegram_notify(text: str, is_alert: bool = False):
    """Lazy wrapper — imports at call time so a telegram_bot import error never kills the scheduler."""
    try:
        from telegram_bot import notify
        notify(text, is_alert=is_alert)
    except Exception as e:
        print(f"[NOTIFIER] telegram_notify failed: {e}")


def whatsapp_notify(text: str) -> bool:
    """Send a WhatsApp message to the owner via the WA sidecar. No-op unless configured.

    Requires BOTH ORA_WA_NOTIFY_NUMBER (phone w/ country code, e.g. 2547XXXXXXXX, or an
    exact contact name) and WA_SIDECAR_URL (reachable sidecar). Checking both here means
    a deleted/unreachable sidecar never costs a notification cycle a slow HTTP timeout.
    Never raises — mirrors telegram_notify so WhatsApp can never kill the scheduler.
    """
    number = os.getenv("ORA_WA_NOTIFY_NUMBER", "").strip()
    sidecar = os.getenv("WA_SIDECAR_URL", "").strip()
    if not number or not sidecar:
        return False
    try:
        from connectors.whatsapp import send_message
        result = send_message(number, text)
        if not result.get("ok"):
            print(f"[NOTIFIER] WhatsApp send failed: {result.get('error', 'unknown error')}")
            return False
        return True
    except Exception as e:
        print(f"[NOTIFIER] whatsapp_notify failed: {type(e).__name__}")
        return False

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
    """Send via Telegram, WhatsApp (if configured) AND FCM. Each channel is isolated — one failing won't affect the others."""
    try:
        full_msg = f"*{title}*\n{body}" if title else body
        telegram_notify(full_msg, is_alert=is_alert)
    except Exception as e:
        print(f"[NOTIFIER] Telegram error: {e}")

    try:
        wa_msg = f"*{title}*\n{body}" if title else body
        whatsapp_notify(wa_msg)
    except Exception as e:
        print(f"[NOTIFIER] WhatsApp error: {e}")

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
            print(f"[NOTIFIER] ALERT sent (telegram+wa+fcm): {ptype}")

        elif action == "notify" and should_send(ptype):
            dual_notify(title="ORA", body=msg, is_alert=False)
            print(f"[NOTIFIER] Notify sent (telegram+wa+fcm): {ptype}")

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

        # Weather
        try:
            from connectors.weather import get_weather_summary
            w = get_weather_summary()
            if w:
                lines.append(f"\nWeather: {w}")
        except Exception:
            pass

        cpu = psutil.cpu_percent(interval=1)
        ram = psutil.virtual_memory().percent
        lines.append(f"\nSystem: CPU {cpu:.0f}% | RAM {ram:.0f}%")

        dual_notify(title="ORA Morning Brief", body="\n".join(lines))
        print("[NOTIFIER] Morning brief sent (telegram+wa+fcm)")

    except Exception as e:
        print(f"[NOTIFIER] Morning brief error: {e}")