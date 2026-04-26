"""
ORA Scheduler — single APScheduler instance for the entire application.

All jobs (core + intelligence layer) are registered here on ONE shared
BackgroundScheduler so there are no duplicate executions or SQLite races.

Job dict format:
    {
        "trigger":  "cron" | "interval",

        # For cron:
        "hour":     int,
        "minute":   int,

        # For interval (use whichever unit you need):
        "hours":    int,
        "minutes":  int,
        "seconds":  int,

        "fn":   callable,
        "name": str          # used as APScheduler job id — must be unique
    }
"""

from __future__ import annotations

import traceback
from apscheduler.schedulers.background import BackgroundScheduler

__all__ = ["start_scheduler", "stop_scheduler", "get_scheduler"]

_scheduler = BackgroundScheduler()


def get_scheduler() -> BackgroundScheduler:
    """Return the shared scheduler instance (use to add jobs dynamically)."""
    return _scheduler


def _safe_run(job_fn, job_name: str) -> None:
    """Wrap every job so one failure never crashes the scheduler thread."""
    try:
        print(f"[ORA Scheduler] Running: {job_name}")
        job_fn()
    except Exception:
        print(f"[ORA Scheduler ERROR] {job_name}")
        print(traceback.format_exc())


def start_scheduler(jobs: list[dict]) -> None:
    """
    Register all jobs and start the scheduler.
    Safe to call only once from api.py lifespan.
    """
    for job in jobs:
        trigger = job.get("trigger", "cron")
        name    = job["name"]
        fn      = job["fn"]

        if trigger == "cron":
            _scheduler.add_job(
                _safe_run,
                trigger="cron",
                hour=job.get("hour", 0),
                minute=job.get("minute", 0),
                args=[fn, name],
                id=name,
                replace_existing=True,
            )
        elif trigger == "interval":
            interval_kwargs: dict = {}
            for unit in ("weeks", "days", "hours", "minutes", "seconds"):
                if unit in job:
                    interval_kwargs[unit] = job[unit]
            _scheduler.add_job(
                _safe_run,
                trigger="interval",
                **interval_kwargs,
                args=[fn, name],
                id=name,
                replace_existing=True,
            )
        else:
            print(f"[ORA Scheduler] Unknown trigger '{trigger}' for job '{name}' — skipped")

    _scheduler.start()
    print("[ORA Scheduler] APScheduler started")


def stop_scheduler() -> None:
    """Gracefully shut down the scheduler (called on app teardown if needed)."""
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
        print("[ORA Scheduler] stopped")