"""
ORA Weather Connector
Primary:  Open-Meteo (free, no key) — https://api.open-meteo.com
Fallback: OpenWeatherMap free tier (needs OPENWEATHER_API_KEY env var)
Cache: 1 hour — zero repeated calls.
Location: WEATHER_LAT / WEATHER_LON env vars (default: Nairobi)
"""

from __future__ import annotations

import os
import time
import traceback
from typing import Optional

import requests

LAT = float(os.getenv("WEATHER_LAT", "-1.1019"))   # Juja, Kiambu
LON = float(os.getenv("WEATHER_LON", "37.0144"))   # Juja, Kiambu
OWM_KEY = os.getenv("OPENWEATHER_API_KEY", "")

_cache:     dict  = {}
CACHE_TTL:  int   = 3600   # 1 hour


# ─────────────────────────────────────────────
# WEATHER CODE HELPERS
# ─────────────────────────────────────────────

def _code_to_text(code: int) -> str:
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

def _code_to_icon(code: int) -> str:
    if code == 0:            return "☀️"
    if code in (1, 2):       return "🌤️"
    if code == 3:            return "☁️"
    if code in (45, 48):     return "🌫️"
    if code in (51,53,55):   return "🌦️"
    if code in (61,63,65):   return "🌧️"
    if code in (71,73,75):   return "❄️"
    if code in (80,81,82):   return "🌧️"
    if code in (95, 96):     return "⛈️"
    return "🌡️"

def _owm_icon(icon_id: str) -> str:
    """Map OWM icon code to emoji."""
    prefix = icon_id[:2] if icon_id else ""
    return {
        "01": "☀️", "02": "🌤️", "03": "☁️", "04": "☁️",
        "09": "🌧️", "10": "🌦️", "11": "⛈️", "13": "❄️", "50": "🌫️",
    }.get(prefix, "🌡️")


# ─────────────────────────────────────────────
# FETCHERS
# ─────────────────────────────────────────────

def _fetch_open_meteo() -> Optional[dict]:
    """Open-Meteo — free, no key required."""
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={LAT}&longitude={LON}"
        f"&current=temperature_2m,relative_humidity_2m,"
        f"apparent_temperature,weather_code,wind_speed_10m"
        f"&timezone=Africa%2FNairobi&forecast_days=1"
    )
    resp    = requests.get(url, timeout=8)
    resp.raise_for_status()
    data    = resp.json()
    current = data.get("current", {})

    temp       = current.get("temperature_2m")
    feels_like = current.get("apparent_temperature")
    humidity   = current.get("relative_humidity_2m")
    wind       = current.get("wind_speed_10m")
    code       = current.get("weather_code", 0)

    # Validate — all four must be non-None numbers
    if any(v is None for v in [temp, feels_like, humidity, wind]):
        raise ValueError(f"Open-Meteo returned None values: {current}")

    return {
        "temp":       round(float(temp), 1),
        "feels_like": round(float(feels_like), 1),
        "humidity":   int(humidity),
        "wind_kph":   round(float(wind), 1),
        "condition":  _code_to_text(int(code)),
        "icon":       _code_to_icon(int(code)),
        "source":     "open-meteo",
    }


def _fetch_openweathermap() -> Optional[dict]:
    """OpenWeatherMap free tier — needs OPENWEATHER_API_KEY."""
    if not OWM_KEY:
        return None
    url  = (
        f"https://api.openweathermap.org/data/2.5/weather"
        f"?lat={LAT}&lon={LON}&appid={OWM_KEY}&units=metric"
    )
    resp = requests.get(url, timeout=8)
    resp.raise_for_status()
    data = resp.json()

    main    = data.get("main", {})
    wind    = data.get("wind", {})
    weather = data.get("weather", [{}])[0]
    icon_id = weather.get("icon", "")

    temp       = main.get("temp")
    feels_like = main.get("feels_like")
    humidity   = main.get("humidity")
    wind_speed = wind.get("speed")   # m/s — convert to km/h
    condition  = weather.get("description", "").capitalize()

    if any(v is None for v in [temp, feels_like, humidity, wind_speed]):
        raise ValueError(f"OWM returned None values: {main}")

    return {
        "temp":       round(float(temp), 1),
        "feels_like": round(float(feels_like), 1),
        "humidity":   int(humidity),
        "wind_kph":   round(float(wind_speed) * 3.6, 1),  # m/s → km/h
        "condition":  condition,
        "icon":       _owm_icon(icon_id),
        "source":     "openweathermap",
    }


# ─────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────

def get_weather() -> Optional[dict]:
    """
    Fetch current weather. Tries Open-Meteo first, falls back to OWM.
    Returns None only if both fail.
    Caches for 1 hour.
    """
    global _cache

    now = time.time()
    if _cache and now - _cache.get("_ts", 0) < CACHE_TTL:
        return {k: v for k, v in _cache.items() if not k.startswith("_")}

    result = None

    # 1. Open-Meteo (free, no key)
    try:
        result = _fetch_open_meteo()
        print(f"[WEATHER] Open-Meteo: {result['temp']}°C {result['condition']}")
    except Exception as e:
        print(f"[WEATHER] Open-Meteo failed: {e}")

    # 2. OpenWeatherMap fallback
    if result is None:
        try:
            result = _fetch_openweathermap()
            if result:
                print(f"[WEATHER] OWM fallback: {result['temp']}°C {result['condition']}")
        except Exception as e:
            print(f"[WEATHER] OWM fallback failed: {e}")

    if result:
        result["_ts"] = now
        _cache = result
        # Return a clean copy without internal cache keys
        return {k: v for k, v in result.items() if not k.startswith("_")}

    return result


def get_weather_summary() -> str:
    """
    One-line summary for morning brief and agent context.
    Never returns None°C — returns empty string if weather unavailable.
    """
    w = get_weather()
    if not w:
        return ""

    temp       = w.get("temp")
    feels_like = w.get("feels_like")
    humidity   = w.get("humidity")
    wind       = w.get("wind_kph")
    icon       = w.get("icon", "🌡️")
    condition  = w.get("condition", "")

    # Guard every field — never format None
    temp_s       = f"{temp}°C"        if temp       is not None else "—°C"
    feels_s      = f"{feels_like}°C"  if feels_like is not None else "—°C"
    humidity_s   = f"{humidity}%"     if humidity   is not None else "—%"
    wind_s       = f"{wind} km/h"     if wind       is not None else "— km/h"

    return (
        f"{icon} {condition}, {temp_s} "
        f"(feels {feels_s}), "
        f"humidity {humidity_s}, "
        f"wind {wind_s}"
    )


def get_weather_forecast(hours: int = 6) -> list[dict]:
    """
    Get hourly forecast for the next N hours.
    Used by the weather monitor to detect incoming rain/storms.
    """
    try:
        resp = requests.get(
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={LAT}&longitude={LON}"
            f"&hourly=temperature_2m,weather_code,precipitation_probability"
            f"&timezone=Africa%2FNairobi&forecast_days=1",
            timeout=8,
        )
        resp.raise_for_status()
        data   = resp.json()
        hourly = data.get("hourly", {})
        times  = hourly.get("time", [])
        temps  = hourly.get("temperature_2m", [])
        codes  = hourly.get("weather_code", [])
        probs  = hourly.get("precipitation_probability", [])

        from datetime import datetime
        import zoneinfo as _zi
        now_eat = datetime.now(_zi.ZoneInfo("Africa/Nairobi"))

        result = []
        for i, t in enumerate(times[:24]):
            try:
                dt = datetime.fromisoformat(t).replace(tzinfo=_zi.ZoneInfo("Africa/Nairobi"))
                if dt <= now_eat:
                    continue
                diff_h = (dt - now_eat).total_seconds() / 3600
                if diff_h > hours:
                    break
                result.append({
                    "time":     dt.strftime("%H:%M"),
                    "temp":     temps[i] if i < len(temps) else None,
                    "code":     codes[i] if i < len(codes) else 0,
                    "rain_pct": probs[i] if i < len(probs) else 0,
                    "condition": _code_to_text(codes[i] if i < len(codes) else 0),
                    "icon":      _code_to_icon(codes[i] if i < len(codes) else 0),
                })
            except Exception:
                continue
        return result
    except Exception as e:
        print(f"[WEATHER] forecast failed: {e}")
        return []

    """
    Multi-line detail for /weather command.
    """
    w = get_weather()
    if not w:
        return "❌ Weather data unavailable right now."

    temp       = w.get("temp",       "—")
    feels_like = w.get("feels_like", "—")
    humidity   = w.get("humidity",   "—")
    wind       = w.get("wind_kph",   "—")
    icon       = w.get("icon",       "🌡️")
    condition  = w.get("condition",  "Unknown")
    source     = w.get("source",     "")

    return (
        f"{icon} *Current Weather — Juja, Kiambu*\n\n"
        f"🌡 Temperature: *{temp}°C* (feels like {feels_like}°C)\n"
        f"💧 Humidity: {humidity}%\n"
        f"💨 Wind: {wind} km/h\n"
        f"☁️ Condition: {condition}\n"
        f"_Source: {source}_"
    )