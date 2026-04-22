import time
import threading
import requests
import os


def start_keepalive():
    def ping():
        time.sleep(30)
        render_url = os.getenv("RENDER_EXTERNAL_URL", "")
        if not render_url:
            print("[KEEPALIVE] No RENDER_EXTERNAL_URL — skipping")
            return

        url = f"{render_url}/api/health"
        print(f"[KEEPALIVE] Pinging {url} every 10 minutes")

        while True:
            try:
                r = requests.get(url, timeout=10)  # GET not HEAD
                print(f"[KEEPALIVE] ✓ {r.status_code}")
            except Exception as e:
                print(f"[KEEPALIVE] Failed: {e}")
            time.sleep(600)

    t = threading.Thread(target=ping, daemon=True)
    t.start()