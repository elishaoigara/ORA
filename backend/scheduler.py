from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import traceback

scheduler = BackgroundScheduler()


# ========================
# WRAPPER FOR SAFETY
# ========================
def safe_run(job_fn, job_name: str):
    try:
        print(f"[ORA Scheduler] Running: {job_name}")
        job_fn()
    except Exception:
        print(f"[ORA Scheduler ERROR] {job_name}")
        print(traceback.format_exc())


# ========================
# INIT SCHEDULER
# ========================
def start_scheduler(jobs):
    """
    jobs format:
    {
        "hour": 7,
        "minute": 0,
        "fn": callable,
        "name": "job_name"
    }
    """

    for job in jobs:
        scheduler.add_job(
            safe_run,
            trigger="cron",
            hour=job["hour"],
            minute=job["minute"],
            args=[job["fn"], job["name"]],
            id=job["name"],
            replace_existing=True
        )

    scheduler.start()
    print("[ORA Scheduler] APScheduler started")


# ========================
# OPTIONAL: STOP
# ========================
def stop_scheduler():
    scheduler.shutdown()
    print("[ORA Scheduler] stopped")