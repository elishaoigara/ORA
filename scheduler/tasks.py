from datetime import datetime
import asyncio

from database import get_tasks
from telegram_bot import notify


def check_due_tasks():
    tasks = get_tasks("pending")
    now = datetime.now()

    for t in tasks:
        due_at = t[4]

        if not due_at:
            continue

        try:
            due_time = datetime.fromisoformat(due_at)
            diff = (due_time - now).total_seconds()

            if 0 <= diff <= 60:
                asyncio.run(
                    notify(f"⏰ Task due: {t[1]}", is_alert=True)
                )

        except Exception as e:
            print("[TASK ERROR]", e)