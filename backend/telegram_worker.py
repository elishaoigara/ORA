"""
ORA Telegram Worker (production-safe runner)
Handles auto-restart, crash safety, and backoff control.
"""

import time
import traceback
from telegram_bot import run_telegram_bot

print("[TELEGRAM WORKER] Booting ORA Telegram service...")


def main():
    retry_delay = 5
    max_delay = 60

    while True:
        try:
            print("[TELEGRAM WORKER] Starting bot loop...")
            run_telegram_bot()  # This already contains its own infinite loop

        except KeyboardInterrupt:
            print("[TELEGRAM WORKER] Shutdown requested by user.")
            break

        except Exception as e:
            print("[TELEGRAM WORKER ERROR]", str(e))
            traceback.print_exc()

            print(f"[TELEGRAM WORKER] Restarting in {retry_delay}s...")

            time.sleep(retry_delay)

            # exponential backoff (prevents Render restart spam)
            retry_delay = min(retry_delay * 2, max_delay)


if __name__ == "__main__":
    main()