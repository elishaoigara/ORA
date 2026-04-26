"""
Intelligence layer scheduler — delegates to the shared ORA scheduler.

This module no longer owns a BackgroundScheduler instance.
All intelligence jobs are registered on the single shared scheduler
that lives in ora_scheduler.py, which is started once from api.py.

Call register_intelligence_jobs() during startup if you need to add
intelligence jobs dynamically (e.g. from a plugin or test), passing
the shared scheduler returned by ora_scheduler.get_scheduler().

In normal operation, api.py's lifespan function registers every job
directly via start_scheduler([...]), so this file is only needed for:
  - standalone local testing
  - future dynamic job registration
"""

from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler

from intelligence.pattern_engine import run_pattern_analysis
from intelligence.proactive_engine import run_proactive_checks
from intelligence.planner_engine import generate_daily_brief
from intelligence.notifier import run_autonomous_notifications


# Job definitions for the intelligence layer.
# api.py reads these via start_scheduler() — kept here as the canonical
# source of truth for intelligence scheduling config.
INTELLIGENCE_JOBS = [
    {"trigger": "interval", "hours":   1, "fn": run_pattern_analysis,       "name": "pattern_analysis"},
    {"trigger": "interval", "minutes": 10, "fn": run_proactive_checks,      "name": "proactive_checks"},
    {"trigger": "interval", "minutes":  5, "fn": run_autonomous_notifications, "name": "auto_notify"},
    {"trigger": "cron",     "hour":    7,  "fn": generate_daily_brief,      "name": "daily_brief"},
]


def register_intelligence_jobs(scheduler: BackgroundScheduler) -> None:
    """
    Register intelligence jobs onto an *existing, already-started* scheduler.

    This is a helper for tests or dynamic use. In production, api.py passes
    all job dicts (including these) directly into start_scheduler() so this
    function is not called.
    """
    from ora_scheduler import _safe_run  # reuse the safe wrapper

    for job in INTELLIGENCE_JOBS:
        trigger = job["trigger"]
        name    = job["name"]
        fn      = job["fn"]

        if trigger == "cron":
            scheduler.add_job(
                _safe_run,
                trigger="cron",
                hour=job.get("hour", 0),
                minute=job.get("minute", 0),
                args=[fn, name],
                id=name,
                replace_existing=True,
            )
        elif trigger == "interval":
            interval_kwargs = {k: job[k] for k in ("weeks", "days", "hours", "minutes", "seconds") if k in job}
            scheduler.add_job(
                _safe_run,
                trigger="interval",
                **interval_kwargs,
                args=[fn, name],
                id=name,
                replace_existing=True,
            )


def start_intelligence_scheduler() -> BackgroundScheduler:
    """
    Standalone entry point for local testing ONLY.

    Creates and starts its own scheduler. Do NOT call this in production —
    api.py uses the shared scheduler from ora_scheduler.py.
    """
    scheduler = BackgroundScheduler()
    register_intelligence_jobs(scheduler)
    scheduler.start()
    print("[Intelligence] Scheduler started (standalone/test mode)")
    return scheduler