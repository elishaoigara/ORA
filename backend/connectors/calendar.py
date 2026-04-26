"""
ORA Google Calendar Connector

Fetches upcoming events from Google Calendar and exposes them
in a format the agent loop can use directly in gather_context().

All functions are safe to call even when Google is not yet authorized
— they return empty lists and log a warning rather than crashing.
"""

from __future__ import annotations

import traceback
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests

from connectors.google_auth import get_access_token, is_authorized

CALENDAR_BASE = "https://www.googleapis.com/calendar/v3"
PRIMARY_CALENDAR = "primary"


# ── Core fetch ────────────────────────────────────────────────
def get_upcoming_events(
    hours_ahead: int = 24,
    max_results: int = 10,
    calendar_id: str = PRIMARY_CALENDAR,
) -> list[dict]:
    """
    Return upcoming calendar events within the next `hours_ahead` hours.

    Each event dict:
        {
            "id":        str,
            "title":     str,
            "start":     ISO datetime str,
            "end":       ISO datetime str,
            "location":  str | None,
            "all_day":   bool,
            "minutes_until": int,   # negative = already started
        }
    """
    if not is_authorized():
        print("[CALENDAR] Not authorized — skipping. Visit /api/auth/google to connect.")
        return []

    try:
        token = get_access_token()
        now   = datetime.now(timezone.utc)
        end   = now + timedelta(hours=hours_ahead)

        resp = requests.get(
            f"{CALENDAR_BASE}/calendars/{calendar_id}/events",
            headers={"Authorization": f"Bearer {token}"},
            params={
                "timeMin":      now.isoformat(),
                "timeMax":      end.isoformat(),
                "maxResults":   max_results,
                "singleEvents": True,
                "orderBy":      "startTime",
            },
            timeout=10,
        )
        resp.raise_for_status()
        items = resp.json().get("items", [])

        events = []
        for item in items:
            start_raw = item.get("start", {})
            end_raw   = item.get("end", {})

            # All-day events use "date", timed events use "dateTime"
            all_day    = "date" in start_raw and "dateTime" not in start_raw
            start_str  = start_raw.get("dateTime") or start_raw.get("date", "")
            end_str    = end_raw.get("dateTime")   or end_raw.get("date", "")

            # Compute minutes until start
            minutes_until = None
            if not all_day and start_str:
                try:
                    start_dt    = datetime.fromisoformat(start_str)
                    if start_dt.tzinfo is None:
                        start_dt = start_dt.replace(tzinfo=timezone.utc)
                    minutes_until = int((start_dt - now).total_seconds() / 60)
                except Exception:
                    pass

            events.append({
                "id":           item.get("id", ""),
                "title":        item.get("summary", "(No title)"),
                "start":        start_str,
                "end":          end_str,
                "location":     item.get("location"),
                "all_day":      all_day,
                "minutes_until": minutes_until,
                "description":  (item.get("description") or "")[:200],
            })

        return events

    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 401:
            print("[CALENDAR] Token expired and refresh failed. Re-authorize via /api/auth/google")
        else:
            print(f"[CALENDAR] HTTP error: {e}")
        return []
    except Exception:
        print("[CALENDAR] fetch error:")
        print(traceback.format_exc())
        return []


def get_events_today() -> list[dict]:
    """Convenience: events in the next 24 hours."""
    return get_upcoming_events(hours_ahead=24)


def get_events_this_week() -> list[dict]:
    """Convenience: events in the next 7 days."""
    return get_upcoming_events(hours_ahead=168, max_results=20)


# ── Decision helpers (used by agent.py) ───────────────────────
def get_imminent_events(threshold_minutes: int = 30) -> list[dict]:
    """
    Return events starting within `threshold_minutes`.
    Used by decide() to fire meeting reminders.
    """
    events = get_upcoming_events(hours_ahead=1, max_results=5)
    return [
        e for e in events
        if e["minutes_until"] is not None and 0 <= e["minutes_until"] <= threshold_minutes
    ]


def format_events_for_context(events: list[dict]) -> str:
    """
    Format events as a compact string for injection into the AI system prompt.
    """
    if not events:
        return ""
    lines = []
    for e in events:
        if e["all_day"]:
            lines.append(f"• {e['title']} (all day)")
        elif e["minutes_until"] is not None:
            if e["minutes_until"] < 0:
                lines.append(f"• {e['title']} (in progress)")
            elif e["minutes_until"] < 60:
                lines.append(f"• {e['title']} — in {e['minutes_until']} min")
            else:
                hours = e["minutes_until"] // 60
                mins  = e["minutes_until"] % 60
                time_str = f"{hours}h {mins}m" if mins else f"{hours}h"
                lines.append(f"• {e['title']} — in {time_str}")
        else:
            lines.append(f"• {e['title']} — {e['start'][:10]}")
    return "\n".join(lines)