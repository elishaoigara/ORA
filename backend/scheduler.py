import threading
import time
from datetime import datetime


def run_scheduler(jobs):
    """
    jobs: list of dicts
    {
        "hour": 7,
        "minute": 0,
        "fn": some_function,
        "name": "morning_briefing"
    }
    """
    fired_today = set()

    print("[ORA Scheduler] Running...")

    while True:
        now = datetime.now()
        today_key = now.strftime("%Y-%m-%d")

        for job in jobs:
            job_key = f"{today_key}_{job['name']}"

            if (
                now.hour == job["hour"]
                and now.minute == job["minute"]
                and job_key not in fired_today
            ):
                fired_today.add(job_key)
                print(f"[Scheduler] Running job: {job['name']}")
                try:
                    job["fn"]()
                except Exception as e:
                    print(f"[Scheduler ERROR] {job['name']}: {e}")

        # Clean up yesterday's fired jobs at midnight
        if now.hour == 0 and now.minute == 0:
            fired_today = set()

        time.sleep(30)  # check every 30 seconds


def start_scheduler(jobs):
    t = threading.Thread(target=run_scheduler, args=(jobs,), daemon=True)
    t.start()
    return t