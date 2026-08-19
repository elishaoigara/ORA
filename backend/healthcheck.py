"""Minimal container health check for the ORA FastAPI process."""

from urllib.request import urlopen


with urlopen("http://127.0.0.1:8000/api/health", timeout=5) as response:
    if response.status != 200:
        raise SystemExit(f"health check failed with HTTP {response.status}")

print("ok")
