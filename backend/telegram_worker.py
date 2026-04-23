"""
ORA Telegram Worker (standalone process)
"""

import time
from telegram_bot import run_telegram_bot

print("[TELEGRAM WORKER] Starting...")

if __name__ == "__main__":
    while True:
        try:
            run_telegram_bot()
        except Exception as e:
            print("[TELEGRAM WORKER ERROR]", e)
            time.sleep(5)