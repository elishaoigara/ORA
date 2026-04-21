from intelligence.priority_engine import get_prioritized_tasks
from telegram_bot import notify
import time

LAST_RUN = 0
COOLDOWN = 600  # 10 minutes


def run_proactive_checks():
    global LAST_RUN

    now = time.time()
    if now - LAST_RUN < COOLDOWN:
        return

    tasks = get_prioritized_tasks()
    if not tasks:
        return

    top = tasks[0][1]

    if "study" in top.lower():
        notify("📚 You’ve been delaying study tasks. Start a 25-min session.")

    elif "project" in top.lower():
        notify("🚀 Break your project into smaller tasks for progress.")

    else:
        notify(f"⚡ Focus now: {top}")

    LAST_RUN = now