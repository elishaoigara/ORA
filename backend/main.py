import os
import time
import threading
import psutil
from datetime import datetime

from config import LOOP_INTERVAL
from database import init_db, init_tasks_table, log_event
from decision_engine import decide
from action_engine import execute
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
            # Fixed: use "/" (Linux root) instead of "C:/"
            "disk_free_gb": psutil.disk_usage("/").free / (1024 ** 3),
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

    log_event("system", data)

    context = {
        "cpu": data["cpu_percent"],
        "ram": data["ram_percent"],
        "disk_free_gb": data["disk_free_gb"],
        "time": data["timestamp"],
    }

    try:
        decision = decide(context)
        reasoning = decision.get("reasoning", [])
        if reasoning:
            print(f"  Reasoning: {', '.join(reasoning)}")
        execute(decision)
    except Exception as e:
        print(f"[DECISION ERROR] {e}")


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
    ]
    start_scheduler(jobs)
    print("[ORA] Scheduler started — daily intelligence active")


# -----------------------------
# BACKGROUND LOOP (runs in thread)
# -----------------------------
def run_background():
    """
    ORA's monitoring loop — runs as a daemon thread alongside the API.
    On Render free tier this keeps the intelligence layer alive as long
    as the web service is up.
    """
    # Init systems
    init_db()
    init_tasks_table()
    init_profile()
    log_memory_event("system", "ORA started", importance=6)

    # Start intelligence layer (Telegram + scheduler)
    try:
        from telegram_bot import notify, run_telegram_bot
        safe_thread(run_telegram_bot, "TELEGRAM")
        notify("👁 ORA is online. Systems stable.")
    except Exception as e:
        print(f"[TELEGRAM INIT] Skipped: {e}")

    start_intelligence_layer()

    # Main monitoring loop
    while True:
        try:
            run_cycle()
        except Exception as e:
            print(f"[CYCLE ERROR] {e}")
        time.sleep(LOOP_INTERVAL)


# -----------------------------
# STARTUP — called by api.py lifespan
# -----------------------------
def startup():
    t = threading.Thread(target=run_background, daemon=True)
    t.start()
    print("[ORA] Background thread started")