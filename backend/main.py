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


# -----------------------------
# SYSTEM DATA COLLECTION
# -----------------------------
def collect_data():
    try:
        return {
            "cpu_percent": psutil.cpu_percent(interval=1),
            "ram_percent": psutil.virtual_memory().percent,
            "disk_free_gb": psutil.disk_usage("C:/").free / (1024 ** 3),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        print(f"[DATA ERROR] {e}")
        return {}


# -----------------------------
# MAIN ORA CYCLE
# -----------------------------
def run_cycle():
    now = datetime.now().strftime('%H:%M:%S')
    print(f"\n[{now}] ORA cycle...")

    data = collect_data()
    if not data:
        return

    print(
        f"  CPU: {data['cpu_percent']}% | "
        f"RAM: {data['ram_percent']}% | "
        f"Disk: {data['disk_free_gb']:.1f}GB"
    )

    # Log system state
    log_event("system", data)

    # Context for intelligence engine
    context = {
        "cpu": data["cpu_percent"],
        "ram": data["ram_percent"],
        "disk_free_gb": data["disk_free_gb"],
        "time": data["timestamp"],
    }

    # Decision making
    try:
        decision = decide(context)
        reasoning = decision.get("reasoning", [])
        if reasoning:
            print(f"  Reasoning: {', '.join(reasoning)}")

        execute(decision)

    except Exception as e:
        print(f"[DECISION ERROR] {e}")

    # Task monitoring
    try:
        check_due_tasks()
    except Exception as e:
        print(f"[TASK CHECK ERROR] {e}")


# -----------------------------
# API SERVER
# -----------------------------
def start_api():
    import uvicorn
    from api import app

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8000,
        log_level="warning"
    )


# -----------------------------
# SAFE THREAD WRAPPER
# -----------------------------
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


# -----------------------------
# INTELLIGENCE LAYER
# -----------------------------
def start_intelligence_layer():
    jobs = [
        {
            "hour": 7,
            "minute": 0,
            "fn": send_morning_briefing,
            "name": "morning_briefing"
        },
        # Future jobs:
        # {
        #     "hour": 22,
        #     "minute": 0,
        #     "fn": nightly_reflection,
        #     "name": "night_review"
        # }
    ]

    start_scheduler(jobs)
    print("[ORA] Scheduler started — daily intelligence active")


# -----------------------------
# MAIN START
# -----------------------------
def main():
    print("=" * 40)
    print("  ORA — Oigara's Responsive Assistant")
    print("=" * 40)

    # Init systems
    init_db()
    init_tasks_table()
    init_profile()
    log_memory_event("system", "ORA started", importance=6)

    # Start services
    safe_thread(start_api, "API")
    safe_thread(run_telegram_bot, "TELEGRAM")

    # Start intelligence layer
    start_intelligence_layer()

    # Startup notification
    try:
        notify("👁 ORA is online. Systems stable.")
    except Exception as e:
        print(f"[NOTIFY ERROR] {e}")

    # -----------------------------
    # MAIN LOOP
    # -----------------------------
    while True:
        try:
            run_cycle()
        except Exception as e:
            print(f"[CYCLE ERROR] {e}")

        time.sleep(LOOP_INTERVAL)


if __name__ == "__main__":
    main()