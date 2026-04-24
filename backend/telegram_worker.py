"""
ORA Telegram Worker (stable production runner)
"""

import time
import traceback
from telegram_bot import run_telegram_bot

print("[TELEGRAM WORKER] Starting...")

def main():
    while True:
        try:
            run_telegram_bot()

        except KeyboardInterrupt:
            print("[TELEGRAM WORKER] Stopped manually")
            break

        except Exception as e:
            print("[TELEGRAM WORKER ERROR]", str(e))
            traceback.print_exc()

            # exponential backoff (prevents Render spam crash loop)
            print("[TELEGRAM WORKER] Restarting in 10 seconds...")
            time.sleep(10)


if __name__ == "__main__":
    main()