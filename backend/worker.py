import time
import threading

from decision_engine import decide
from action_engine import execute
from ai_budget import ai_budget

# OPTIONAL: only import telegram safely
try:
    from telegram_bot import run_telegram_bot
except Exception:
    run_telegram_bot = None


# ─────────────────────────────────────────
# MONITORING LOOP (SAFE STUB)
# ─────────────────────────────────────────
def monitoring_loop():
    """
    This avoids missing imports and keeps worker alive.
    Your real monitoring already runs in api or startup system.
    """
    while True:
        try:
            time.sleep(10)
        except Exception as e:
            print(f"[MONITOR ERROR] {e}")


# ─────────────────────────────────────────
# AI WORKER (SAFE MODE)
# ─────────────────────────────────────────
def ai_worker():
    while True:
        try:
            time.sleep(5)

            # Worker stays alive — real AI logic is inside API layer
            continue

        except Exception as e:
            print(f"[AI WORKER ERROR] {e}")


# ─────────────────────────────────────────
# TELEGRAM WORKER
# ─────────────────────────────────────────
def telegram_worker():
    if run_telegram_bot is None:
        print("[TELEGRAM] Bot not available")
        return

    while True:
        try:
            run_telegram_bot()
        except Exception as e:
            print(f"[TELEGRAM ERROR] {e}")
            time.sleep(5)


# ─────────────────────────────────────────
# START ALL WORKERS
# ─────────────────────────────────────────
def start_workers():
    print("[WORKER] ORA background system starting...")

    threading.Thread(target=monitoring_loop, daemon=True).start()
    threading.Thread(target=ai_worker, daemon=True).start()

    if run_telegram_bot:
        threading.Thread(target=telegram_worker, daemon=True).start()

    while True:
        time.sleep(60)


if __name__ == "__main__":
    start_workers()