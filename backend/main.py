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


# ─────────────────────────────────────────
# SYSTEM DATA COLLECTION
# ─────────────────────────────────────────
def collect_data():
    try:
        return {
            "cpu_percent": psutil.cpu_percent(interval=1),
            "ram_percent": psutil.virtual_memory().percent,
            "disk_free_gb": psutil.disk_usage("/").free / (1024 ** 3),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        print(f"[DATA ERROR] {e}")
        return {}


# ─────────────────────────────────────────
# MONITORING CYCLE
# ─────────────────────────────────────────
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


# ─────────────────────────────────────────
# MONITORING LOOP
# ─────────────────────────────────────────
def run_monitoring_loop():
    while True:
        try:
            run_cycle()
        except Exception as e:
            print(f"[CYCLE ERROR] {e}")
        time.sleep(LOOP_INTERVAL)


# ─────────────────────────────────────────
# TELEGRAM THREAD
# Pure sync — no asyncio needed with new bot
# ─────────────────────────────────────────
def run_telegram_thread():
    from config import TELEGRAM_BOT_TOKEN
    if not TELEGRAM_BOT_TOKEN:
        print("[TELEGRAM] No token — skipping.")
        return

    # Wait for uvicorn to fully start
    time.sleep(3)
    print("[TELEGRAM] Starting bot in dedicated thread...")

    while True:
        try:
            from telegram_bot import run_telegram_bot
            run_telegram_bot()
        except Exception as e:
            print(f"[TELEGRAM ERROR] {e} — restarting in 10s")
            time.sleep(10)


# ─────────────────────────────────────────
# INTELLIGENCE LAYER
# ─────────────────────────────────────────
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
    print("[ORA] Scheduler started — daily briefing at 07:00 Nairobi")


# ─────────────────────────────────────────
# STARTUP — called by api.py lifespan
# ─────────────────────────────────────────
def startup():
    print("[ORA] Initializing systems...")

    init_db()
    init_tasks_table()
    init_profile()
    log_memory_event("system", "ORA started", importance=6)

    # Telegram — pure sync thread, no event loop
    t_telegram = threading.Thread(target=run_telegram_thread, daemon=True, name="telegram")
    t_telegram.start()

    # Intelligence scheduler
    start_intelligence_layer()

    # Monitoring loop
    t_monitor = threading.Thread(target=run_monitoring_loop, daemon=True, name="monitor")
    t_monitor.start()

    print("[ORA] All systems online.")