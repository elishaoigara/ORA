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
from memory.events import log_memory_event, summarize_old_events
from briefing import send_morning_briefing
from ora_scheduler import start_scheduler

from ai_budget import ai_budget
from intelligence.pattern_engine import run_pattern_analysis

# ─────────────────────────────────────────
# GLOBAL STATE
# ─────────────────────────────────────────
ai_queue = Queue()
decision_cache = {}

last_ai_call = 0
AI_COOLDOWN = 60


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
# AI CONTROL LOGIC
# ─────────────────────────────────────────
def should_use_ai(data):
    return (
        (88 < data["cpu_percent"] <= 95) or
        (85 < data["ram_percent"] <= 92) or
        (3 <= data["disk_free_gb"] <= 5)
    )


def can_call_ai():
    global last_ai_call
    now = time.time()

    if now - last_ai_call > AI_COOLDOWN:
        last_ai_call = now
        return True

    return False


def get_cache_key(context):
    return f"{round(context['cpu'])}.{round(context['ram'])}.{round(context['disk_free_gb'])}"


# ─────────────────────────────────────────
# MAIN CYCLE
# ─────────────────────────────────────────
def run_cycle():
    now = datetime.now().strftime("%H:%M:%S")
    print(f"\n[{now}] ORA cycle...")

    data = collect_data()
    if not data:
        return

    print(
        f"  CPU: {data['cpu_percent']}% | "
        f"RAM: {data['ram_percent']}% | "
        f"Disk: {data['disk_free_gb']:.1f}GB"
    )

    import json as _json; log_event("system", _json.dumps(data))

    context = {
        "cpu": data["cpu_percent"],
        "ram": data["ram_percent"],
        "disk_free_gb": data["disk_free_gb"],
        "time": data["timestamp"],
    }

    key = get_cache_key(context)

    # 1. CACHE HIT
    if key in decision_cache:
        print("  [CACHE] Using cached decision")
        execute(decision_cache[key])
        return

    # 2. RULE ENGINE
    decision = decide(context)

    if decision.get("actions"):
        decision_cache[key] = decision
        execute(decision)
        return

    # 3. AI QUEUE LIMIT
    if ai_queue.qsize() > 3:
        print("[AI] Queue full — skipping request")
        return

    # 4. AI GATING
    if should_use_ai(data) and can_call_ai() and ai_budget.can_use_ai():
        print("  [AI] Queuing decision request...")
        ai_queue.put((key, context))
        return

    # 5. FALLBACK
    decision = {
        "reasoning": ["system stable / no AI needed"],
        "actions": []
    }

    decision_cache[key] = decision
    execute(decision)


# ─────────────────────────────────────────
# AI WORKER (FIXED)
# ─────────────────────────────────────────
def ai_worker():
    while True:
        try:
            key, context = ai_queue.get()

            print("  [AI WORKER] Processing decision...")

            if not ai_budget.can_use_ai():
                print("[AI WORKER] BLOCKED by AI budget controller")
                ai_queue.task_done()
                continue

            try:
                decision = decide(context, use_ai=True)
                ai_budget.register_call()

            except Exception as e:
                print(f"[AI ERROR] {e}")
                decision = {
                    "reasoning": ["fallback triggered"],
                    "actions": []
                }

            decision_cache[key] = decision
            execute(decision)

            ai_queue.task_done()

        except Exception as e:
            print(f"[WORKER ERROR] {e}")


# ─────────────────────────────────────────
# KEEP-ALIVE (Render free tier)
# ─────────────────────────────────────────
def run_keep_alive():
    import os, requests as _req
    url = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")
    if not url:
        return
    time.sleep(20)
    while True:
        try:
            _req.get(f"{url}/api/health", timeout=5)
        except Exception:
            pass
        time.sleep(30)


# ─────────────────────────────────────────
# MONITOR LOOP
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
    print("[TELEGRAM] Starting bot...")

    from telegram_bot import run_telegram_bot

    while True:
        try:
            run_telegram_bot()
        except Exception as e:
            print(f"[TELEGRAM ERROR] {e} — restarting in 10s")
            time.sleep(10)


# ─────────────────────────────────────────
# INTELLIGENCE LAYER
# ─────────────────────────────────────────
def start_intelligence_layer():
    jobs = [
        {"hour": 7, "minute": 0, "fn": send_morning_briefing, "name": "morning_briefing"},
        {"hour": 23, "minute": 0, "fn": run_pattern_analysis, "name": "daily_pattern_analysis"},
        {"hour": 2, "minute": 0, "fn": summarize_old_events, "name": "summarize_old_events"},
    ]

    start_scheduler(jobs)
    print("[ORA] Scheduler started")


# ─────────────────────────────────────────
# STARTUP
# ─────────────────────────────────────────
def startup():
    print("[ORA] Initializing systems...")

    init_db()
    init_tasks_table()
    init_profile()
    log_memory_event("system", "ORA started", importance=6)

    start_intelligence_layer()

    print("[ORA] Core systems online")

# ─────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────
if __name__ == "__main__":
    startup()

    t_telegram = threading.Thread(target=run_telegram_thread, daemon=True)
    t_telegram.start()

    t_ai_worker = threading.Thread(target=ai_worker, daemon=True)
    t_ai_worker.start()

    t_keepalive = threading.Thread(target=run_keep_alive, daemon=True, name="keep-alive")
    t_keepalive.start()

    run_monitoring_loop()