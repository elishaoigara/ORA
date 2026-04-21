import time
import psutil
import threading
from datetime import datetime

from config import LOOP_INTERVAL
from database import init_db, log_event, log_alert
from engine import run_rules
from telegram_bot import notify, run_telegram_bot
from memory.profile import init_profile
from memory.events import log_memory_event

def collect_data():
    return {
        "cpu_percent": psutil.cpu_percent(interval=1),
        "ram_percent": psutil.virtual_memory().percent,
        "disk_free_gb": psutil.disk_usage("/").free / (1024 ** 3),
        "timestamp": datetime.now().isoformat()
    }

def run_cycle():
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] ORA cycle...")
    data = collect_data()
    print(f"  CPU: {data['cpu_percent']}% | RAM: {data['ram_percent']}% | Disk: {data['disk_free_gb']:.1f}GB")
    log_event("system", data)
    triggered = run_rules(data)
    for rule_name, message, severity in triggered:
        print(f"  ⚠️  [{severity.upper()}] {message}")
        log_alert(rule_name, message, severity)
        notify(message, is_alert=True)
    if not triggered:
        print("  ✅ All clear.")

def start_api():
    import uvicorn
    from api import app
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")

def main():
    print("=" * 40)
    print("  ORA — Oigara's Responsive Assistant")
    print("=" * 40)

    init_db()
    init_profile()
    log_memory_event("system", "ORA started", importance=6)

    # Start API in background
    api_thread = threading.Thread(target=start_api, daemon=True)
    api_thread.start()

    # Start Telegram bot in background
    telegram_thread = threading.Thread(target=run_telegram_bot, daemon=True)
    telegram_thread.start()

    notify("👁 *ORA is online.* Good to see you, Elisha.")

    # Main loop
    while True:
        try:
            run_cycle()
        except Exception as e:
            print(f"[ERROR] {e}")
        time.sleep(LOOP_INTERVAL)

if __name__ == "__main__":
    main()