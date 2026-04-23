"""
Intelligence layer scheduler — uses APScheduler to match the rest of ORA.
The old 'schedule' library blocked in a while-loop and conflicted with
APScheduler's background mode used in main.py.
"""
from apscheduler.schedulers.background import BackgroundScheduler

from intelligence.pattern_engine import run_pattern_analysis
from intelligence.proactive_engine import run_proactive_checks
from intelligence.planner_engine import generate_daily_brief
from intelligence.notifier import run_autonomous_notifications


def start_intelligence_scheduler(scheduler: BackgroundScheduler = None):
    """
    Register intelligence jobs on the provided APScheduler instance.
    If none is given, creates and starts a new one (for standalone use).
    """
    own_scheduler = scheduler is None
    if own_scheduler:
        scheduler = BackgroundScheduler()

    scheduler.add_job(run_pattern_analysis,    "interval", hours=1,   id="pattern_analysis",   replace_existing=True)
    scheduler.add_job(run_proactive_checks,    "interval", minutes=10, id="proactive_checks",  replace_existing=True)
    scheduler.add_job(run_autonomous_notifications, "interval", minutes=5, id="auto_notify",  replace_existing=True)
    scheduler.add_job(generate_daily_brief,    "cron",     hour=7,    id="daily_brief",         replace_existing=True)

    if own_scheduler:
        scheduler.start()
        print("[Intelligence] Scheduler started (standalone)")

    return scheduler
