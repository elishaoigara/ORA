import schedule
import time

from intelligence.pattern_engine import run_pattern_analysis
from intelligence.proactive_engine import run_proactive_checks
from intelligence.planner_engine import generate_daily_brief
from intelligence.notifier import run_autonomous_notifications


def start_scheduler():
    schedule.every(1).hours.do(run_pattern_analysis)
    schedule.every(10).minutes.do(run_proactive_checks)
    schedule.every(5).minutes.do(run_autonomous_notifications)
    schedule.every().day.at("07:00").do(generate_daily_brief)

    print("[ORA] Scheduler running...")
    while True:
        schedule.run_pending()
        time.sleep(5)