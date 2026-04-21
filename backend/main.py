import time
import psutil
import threading
from datetime import datetime

from config import LOOP_INTERVAL
from database import init_db, init_tasks_table, log_event
from decision_engine import decide
from action_engine import execute
from telegram_bot import notify, run_telegram_bot, check_due_tasks
from memory.profile import init_profile
from memory.events import log_memory_event
from briefing import send_morning_briefing
from scheduler import start_scheduler


def collect_data():
    return {
        "cpu_percent": psutil.cpu_percent(interval=1),
        "ram_percent": psutil.virtual_memory().percent,
        "disk_free_gb": psutil.disk_usage("C:/").free / (1024 ** 3),
        "timestamp": datetime.now().isoformat()
    }


def run_cycle():
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] ORA cycle...")
    data = collect_data()
    print(f"  CPU: {data['cpu_percent']}% | RAM: {data['ram_percent']}% | Disk: {data['disk_free_gb']:.1f}GB")
    log_event("system", data)

    context = {
        "cpu": data["cpu_percent"],
        "ram": data["ram_percent"],
        "disk_free_gb": data["disk_free_gb"],
    }

    decision = decide(context)
    print(f"  Reasoning: {', '.join(decision.get('reasoning', []))}")
    execute(decision)

    try:
        check_due_tasks()
    except Exception as e:
        print(f"[TASK CHECK ERROR] {e}")


def start_api():
    import uvicorn
    from api import app
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")


def safe_thread(target, name):
    def wrapper():
        while True:
            try:
                target()
            except Exception as e:
                print(f"[{name} ERROR] {e}")
                time.sleep(5)
    t = threading.Thread(target=wrapper, daemon=True)
    t.start()
    return t


def main():
    print("=" * 40)
    print("  ORA — Oigara's Responsive Assistant")
    print("=" * 40)

    init_db()
    init_tasks_table()
    init_profile()
    log_memory_event("system", "ORA started", importance=6)

    # Start API
    safe_thread(start_api, "API")

    # Start Telegram bot
    safe_thread(run_telegram_bot, "TELEGRAM")

    # Start scheduler with jobs
    jobs = [
        {
            "hour": 7,
            "minute": 0,
            "fn": send_morning_briefing,
            "name": "morning_briefing"
        }
    ]
    start_scheduler(jobs)
    print("[ORA] Scheduler started — morning briefing at 07:00")

    notify("👁 ORA is online. Good to see you, Elisha.")

    while True:
        try:
            run_cycle()
        except Exception as e:
            print(f"[CYCLE ERROR] {e}")
        time.sleep(LOOP_INTERVAL)


if __name__ == "__main__":
    main()