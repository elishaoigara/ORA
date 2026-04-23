from datetime import datetime, timezone
import logging

# ✅ Proper absolute imports (FIX: Pylance issue)
from backend.database import get_tasks
from backend.telegram_bot import notify

logger = logging.getLogger(__name__)


def check_due_tasks():
    """
    ORA V3 Scheduler Task Checker
    Runs periodically to detect due tasks and send alerts
    """

    try:
        tasks = get_tasks("pending")

        # ✅ Use UTC for production safety
        now = datetime.now(timezone.utc)

        for t in tasks:
            task_id = t[0]
            title = t[1]
            due_at = t[4]
            alerted = t[5] if len(t) > 5 else False

            if not due_at or alerted:
                continue

            try:
                due_time = datetime.fromisoformat(due_at)

                # ensure timezone awareness
                if due_time.tzinfo is None:
                    due_time = due_time.replace(tzinfo=timezone.utc)

                diff = (due_time - now).total_seconds()

                # ⏰ trigger 1 min before due
                if 0 <= diff <= 60:
                    notify(f"⏰ ORA Task Due: {title}", is_alert=True)

                    # optional: mark as alerted (if your DB supports it)
                    # mark_task_alerted(task_id)

            except Exception as inner_err:
                logger.error(f"[TASK PARSE ERROR] {inner_err} | Task: {t}")

    except Exception as e:
        logger.error(f"[TASK CHECK FAILED] {e}")