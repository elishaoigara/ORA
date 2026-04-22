import time
import threading
import psutil
from datetime import datetime
from queue import Queue

from config import LOOP_INTERVAL
from database import init_db, init_tasks_table, log_event
from decision_engine import decide
from action_engine import execute
from memory.profile import init_profile
from memory.events import log_memory_event
from briefing import send_morning_briefing
from scheduler import start_scheduler


# ─────────────────────────────────────────
# GLOBAL CONTROL LAYER
# ─────────────────────────────────────────
ai_queue = Queue()
decision_cache = {}

last_ai_call = 0
AI_COOLDOWN = 60  # seconds


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
# AI CONTROL HELPERS
# ─────────────────────────────────────────
def should_use_ai(data):
    return (
        data["cpu_percent"] > 85 or
        data["ram_percent"] > 80 or
        data["disk_free_gb"] < 5
    )


def can_call_ai():
    global last_ai_call
    now = time.time()
    if now - last_ai_call > AI_COOLDOWN:
        last_ai_call = now
        return True
    return False


def get_cache_key(context):
    return f"{round(context['cpu'])}-{round(context['ram'])}-{round(context['disk_free_gb'])}"


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

    key = get_cache_key(context)

    # 1. Use cached decision if available
    if key in decision_cache:
        decision = decision_cache[key]
        print("  [CACHE] Using cached decision")
        execute(decision)
        return

    # 2. Decide if AI is needed
    if should_use_ai(data) and can_call_ai():
        print("  [AI] Queuing decision request...")
        ai_queue.put((key, context))
    else:
        decision = {"action": "none", "reasoning": ["system stable / rate-limited"]}
        execute(decision)


# ─────────────────────────────────────────
# AI WORKER (RATE CONTROLLED)
# ─────────────────────────────────────────
def ai_worker():
    while True:
        try:
            key, context = ai_queue.get()

            print("  [AI WORKER] Processing decision...")

            try:
                decision = decide(context)  # Groq call
            except Exception as e:
                print(f"[AI ERROR] {e}")
                decision = {
                    "action": "none",
                    "reasoning": ["fallback triggered"]
                }

            decision_cache[key] = decision
            execute(decision)

        except Exception as e:
            print(f"[WORKER ERROR] {e}")


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
# ─────────────────────────────────────────
def run_telegram_thread():
    from config import TELEGRAM_BOT_TOKEN

    if not TELEGRAM_BOT_TOKEN:
        print("[TELEGRAM] No token — skipping.")
        return

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
# STARTUP
# ─────────────────────────────────────────
def startup():
    print("[ORA] Initializing systems...")

    init_db()
    init_tasks_table()
    init_profile()
    log_memory_event("system", "ORA started", importance=6)

    # Telegram thread
    threading.Thread(target=run_telegram_thread, daemon=True).start()

    # AI worker thread
    threading.Thread(target=ai_worker, daemon=True).start()

    # Scheduler
    start_intelligence_layer()

    # Monitoring loop
    threading.Thread(target=run_monitoring_loop, daemon=True).start()

    print("[ORA] All systems online.")