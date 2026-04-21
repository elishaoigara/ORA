import threading
import time
from datetime import datetime, timedelta


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
        try:
            now = datetime.now()
            today = now.strftime("%Y-%m-%d")

            for job in jobs:
                job_id = f"{today}_{job['name']}"

                # Create scheduled time
                scheduled_time = now.replace(
                    hour=job["hour"],
                    minute=job["minute"],
                    second=0,
                    microsecond=0
                )

                # Allow small window (±60 seconds)
                time_diff = (now - scheduled_time).total_seconds()

                if 0 <= time_diff < 60:
                    if job_id not in fired_today:
                        fired_today.add(job_id)

                        print(f"[Scheduler] Running: {job['name']}")

                        try:
                            job["fn"]()
                        except Exception as e:
                            print(f"[Scheduler ERROR] {job['name']}: {e}")

            # Cleanup old entries (keep only today)
            fired_today = {
                jid for jid in fired_today
                if jid.startswith(today)
            }

        except Exception as e:
            print(f"[Scheduler LOOP ERROR] {e}")

        time.sleep(20)  # more responsive than 30s
        

def start_scheduler(jobs):
    t = threading.Thread(
        target=run_scheduler,
        args=(jobs,),
        daemon=True
    )
    t.start()
    return t