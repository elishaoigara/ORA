from datetime import datetime
from database import get_tasks


def score_task(task):
    _, title, priority, created_at, due_at = task

    score = 0

    # urgency
    if due_at:
        try:
            due = datetime.fromisoformat(due_at)
            diff = (due - datetime.now()).total_seconds()

            if diff < 3600:
                score += 5
            elif diff < 86400:
                score += 3
        except:
            pass

    # priority weight
    if priority == "high":
        score += 3
    elif priority == "medium":
        score += 2

    # keyword signals
    if "urgent" in title.lower():
        score += 4

    return score


def get_prioritized_tasks():
    tasks = get_tasks("pending")
    ranked = sorted(tasks, key=score_task, reverse=True)
    return ranked[:5]