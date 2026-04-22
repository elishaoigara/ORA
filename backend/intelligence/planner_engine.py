from datetime import datetime
from intelligence.priority_engine import get_prioritized_tasks
from intelligence.goals_engine import get_goals

LAST_RUN_DAY = None


def generate_daily_brief():
    global LAST_RUN_DAY

    now = datetime.now()

    if now.hour != 7:
        return

    if LAST_RUN_DAY == now.date():
        return

    try:
        from telegram_bot import notify
    except ImportError:
        print("[TELEGRAM] Telegram bot not configured, skipping daily brief notification.")
        return

    tasks = get_prioritized_tasks()
    goals = get_goals()

    msg = "🌅 Daily Briefing\n\n"

    if tasks:
        msg += "Top priorities:\n"
        for t in tasks:
            msg += f"- {t[1]}\n"
    else:
        msg += "No pending tasks.\n"

    if goals:
        msg += "\n🎯 Goals:\n"
        for g in goals:
            msg += f"- {g}\n"

    notify(msg)
    LAST_RUN_DAY = now.date()
