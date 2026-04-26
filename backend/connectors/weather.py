"""
ORA Weather Connector — Phase 4
Uses Open-Meteo (completely free, no API key).
Caches result 1 hour — zero repeated calls.
Nairobi coordinates hardcoded (can override via env var).
"""

from __future__ import annotations

import traceback
import time
from typing import Optional

# Nairobi
LAT = float(__import__('os').getenv("WEATHER_LAT", "-1.2921"))
LON = float(__import__('os').getenv("WEATHER_LON", "36.8219"))

_cache: dict = {}
CACHE_TTL = 3600  # 1 hour


def get_weather() -> Optional[dict]:
    """
    Fetch current weather from Open-Meteo.
    Returns dict with temp, feels_like, condition, humidity, wind.
    Returns cached result if under 1 hour old.
    """
    global _cache

    now = time.time()
    if _cache and now - _cache.get("_ts", 0) < CACHE_TTL:
        return _cache

    try:
        import requests
        url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={LAT}&longitude={LON}"
            f"&current=temperature_2m,relative_humidity_2m,"
            f"apparent_temperature,weather_code,wind_speed_10m"
            f"&timezone=Africa%2FNairobi"
            f"&forecast_days=1"
        )
        resp = requests.get(url, timeout=8)
        data = resp.json()

        current = data.get("current", {})
        code    = current.get("weather_code", 0)

        result = {
            "temp":       current.get("temperature_2m"),
            "feels_like": current.get("apparent_temperature"),
            "humidity":   current.get("relative_humidity_2m"),
            "wind_kph":   current.get("wind_speed_10m"),
            "condition":  _weather_code_to_text(code),
            "icon":       _weather_code_to_icon(code),
            "_ts":        now,
        }

        _cache = result
        return result

    except Exception:
        print("[WEATHER] fetch failed:")
        print(traceback.format_exc())
        return None


def get_weather_summary() -> str:
    """One-line summary for morning brief and agent context."""
    w = get_weather()
    if not w:
        return ""
    return (
        f"{w['icon']} {w['condition']}, {w['temp']}°C "
        f"(feels {w['feels_like']}°C), "
        f"humidity {w['humidity']}%, "
        f"wind {w['wind_kph']} km/h"
    )


def _weather_code_to_text(code: int) -> str:
    mapping = {
        0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
        45: "Foggy", 48: "Icy fog",
        51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle",
        61: "Light rain", 63: "Rain", 65: "Heavy rain",
        71: "Light snow", 73: "Snow", 75: "Heavy snow",
        80: "Light showers", 81: "Showers", 82: "Heavy showers",
        95: "Thunderstorm", 96: "Thunderstorm with hail",
    }
    return mapping.get(code, "Unknown")


def _weather_code_to_icon(code: int) -> str:
    if code == 0:              return "☀️"
    if code in (1, 2):         return "🌤️"
    if code == 3:              return "☁️"
    if code in (45, 48):       return "🌫️"
    if code in (51, 53, 55):   return "🌦️"
    if code in (61, 63, 65):   return "🌧️"
    if code in (71, 73, 75):   return "❄️"
    if code in (80, 81, 82):   return "🌧️"
    if code in (95, 96):       return "⛈️"
    return "🌡️"