"""
ORA Google Calendar Connector — read + write

Read functions (existing, unchanged):
  get_upcoming_events()     — fetch events in a time window
  get_events_today()        — next 24 h
  get_events_this_week()    — next 7 days
  get_imminent_events()     — starting within N minutes
  format_events_for_context() — compact string for AI prompt

Write functions (new):
  create_event()            — create a new event
  update_event()            — edit title/time/location/description
  delete_event()            — delete an event by ID
  quick_event()             — natural-language shortcut (e.g. "Lunch at 1pm for 1hr")
  find_free_slot()          — find the next open gap of N minutes in the calendar

All functions are safe when Google is not authorized — return None/[] and log.
Requires scope: https://www.googleapis.com/auth/calendar  (not .readonly)
"""

from __future__ import annotations

import json
import traceback
import zoneinfo
from datetime import datetime, timedelta, timezone
from typing import Optional
import re

import requests

from connectors.google_auth import get_access_token, is_authorized

CALENDAR_BASE    = "https://www.googleapis.com/calendar/v3"
PRIMARY_CALENDAR = "primary"

# Cache calendar list to avoid fetching on every call
_CALENDAR_IDS_CACHE: list[str] = []
_CALENDAR_IDS_TTL   = 300   # seconds
_CALENDAR_IDS_FETCHED_AT: float = 0.0


def get_all_calendar_ids() -> list[str]:
    """
    Return IDs of all calendars the user has access to (owned + subscribed).
    Falls back to ["primary"] if fetch fails or user not authorized.
    Results cached for 5 minutes.
    """
    global _CALENDAR_IDS_CACHE, _CALENDAR_IDS_FETCHED_AT
    import time as _time

    if _CALENDAR_IDS_CACHE and (_time.time() - _CALENDAR_IDS_FETCHED_AT) < _CALENDAR_IDS_TTL:
        return _CALENDAR_IDS_CACHE

    if not is_authorized():
        return [PRIMARY_CALENDAR]

    try:
        data = _cal_get("users/me/calendarList", {"minAccessRole": "reader"})
        ids  = [item["id"] for item in data.get("items", [])
                if not item.get("deleted")]
        if not ids:
            ids = [PRIMARY_CALENDAR]
        _CALENDAR_IDS_CACHE      = ids
        _CALENDAR_IDS_FETCHED_AT = _time.time()
        print(f"[CALENDAR] Found {len(ids)} calendar(s): {ids}")
        return ids
    except Exception as e:
        print(f"[CALENDAR] get_all_calendar_ids failed: {e}")
        return [PRIMARY_CALENDAR]


NAIROBI_TZ       = "Africa/Nairobi"


# ─────────────────────────────────────────────
# INTERNAL HELPERS
# ─────────────────────────────────────────────

def _headers() -> dict:
    return {"Authorization": f"Bearer {get_access_token()}",
            "Content-Type": "application/json"}


def _safe_cal_id(cid: str) -> str:
    from urllib.parse import quote
    return quote(cid, safe="")


def _cal_get(path: str, params: dict | None = None) -> dict:
    r = requests.get(f"{CALENDAR_BASE}/{path}",
                     headers=_headers(), params=params or {}, timeout=10)
    r.raise_for_status()
    return r.json()


def _cal_post(path: str, body: dict) -> dict:
    r = requests.post(f"{CALENDAR_BASE}/{path}",
                      headers=_headers(), json=body, timeout=10)
    r.raise_for_status()
    return r.json()


def _cal_patch(path: str, body: dict) -> dict:
    r = requests.patch(f"{CALENDAR_BASE}/{path}",
                       headers=_headers(), json=body, timeout=10)
    r.raise_for_status()
    return r.json()


def _cal_delete(path: str) -> bool:
    r = requests.delete(f"{CALENDAR_BASE}/{path}",
                        headers=_headers(), timeout=10)
    return r.status_code in (200, 204)


def _now_nairobi() -> datetime:
    return datetime.now(timezone.utc).astimezone(
        zoneinfo.ZoneInfo(NAIROBI_TZ)
    )


def _parse_event(item: dict) -> dict:
    """Normalise a raw Calendar API event into ORA's format."""
    start_raw    = item.get("start", {})
    end_raw      = item.get("end", {})
    all_day      = "date" in start_raw and "dateTime" not in start_raw
    start_str    = start_raw.get("dateTime") or start_raw.get("date", "")
    end_str      = end_raw.get("dateTime")   or end_raw.get("date", "")
    now          = datetime.now(timezone.utc)
    minutes_until = None
    if not all_day and start_str:
        try:
            start_dt = datetime.fromisoformat(start_str)
            if start_dt.tzinfo is None:
                start_dt = start_dt.replace(tzinfo=timezone.utc)
            minutes_until = int((start_dt - now).total_seconds() / 60)
        except Exception:
            pass
    return {
        "id":            item.get("id", ""),
        "title":         item.get("summary", "(No title)"),
        "start":         start_str,
        "end":           end_str,
        "location":      item.get("location"),
        "all_day":       all_day,
        "minutes_until": minutes_until,
        "description":   (item.get("description") or "")[:200],
        "html_link":     item.get("htmlLink", ""),
    }


# ─────────────────────────────────────────────
# READ FUNCTIONS  (unchanged signatures)
# ─────────────────────────────────────────────

def get_upcoming_events(
    hours_ahead: int = 24,
    max_results: int = 10,
    calendar_id: str = PRIMARY_CALENDAR,
) -> list[dict]:
    if not is_authorized():
        print("[CALENDAR] Not authorized — visit /api/auth/google")
        return []

    # When using the default primary, expand to all calendars
    cal_ids = get_all_calendar_ids() if calendar_id == PRIMARY_CALENDAR else [calendar_id]

    try:
        now    = datetime.now(timezone.utc)
        end    = now + timedelta(hours=hours_ahead)
        params = {
            "timeMin":      now.isoformat(),
            "timeMax":      end.isoformat(),
            "maxResults":   max_results,
            "singleEvents": True,
            "orderBy":      "startTime",
        }

        all_events: list[dict] = []
        seen_ids: set[str]     = set()

        for cid in cal_ids:
            try:
                safe_cid = _safe_cal_id(cid)
                data   = _cal_get(f"calendars/{safe_cid}/events", params)
                events = [_parse_event(i) for i in data.get("items", [])]
                for ev in events:
                    eid = ev.get("id", "")
                    if eid and eid not in seen_ids:
                        ev["_calendar_id"] = cid   # tag source calendar
                        all_events.append(ev)
                        seen_ids.add(eid)
            except Exception as e:
                print(f"[CALENDAR] Error reading calendar {cid}: {e}")

        # Sort merged results by start time
        def _sort_key(ev: dict) -> str:
            return ev.get("start") or ev.get("date") or ""

        all_events.sort(key=_sort_key)
        return all_events[:max_results]

    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 401:
            print("[CALENDAR] Token expired — re-authorize via /api/auth/google")
        else:
            print(f"[CALENDAR] HTTP error: {e}")
        return []
    except Exception:
        print("[CALENDAR] fetch error:")
        print(traceback.format_exc())
        return []


def get_events_today() -> list[dict]:
    return get_upcoming_events(hours_ahead=24)


def get_events_this_week() -> list[dict]:
    return get_upcoming_events(hours_ahead=168, max_results=20)


def get_imminent_events(threshold_minutes: int = 30) -> list[dict]:
    events = get_upcoming_events(hours_ahead=1, max_results=5)
    return [
        e for e in events
        if e["minutes_until"] is not None and 0 <= e["minutes_until"] <= threshold_minutes
    ]


def format_events_for_context(events: list[dict]) -> str:
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
                h = e["minutes_until"] // 60
                m = e["minutes_until"] % 60
                lines.append(f"• {e['title']} — in {h}h {m}m" if m else f"• {e['title']} — in {h}h")
        else:
            lines.append(f"• {e['title']} — {e['start'][:10]}")
    return "\n".join(lines)


# ─────────────────────────────────────────────
# WRITE FUNCTIONS  (new)
# ─────────────────────────────────────────────

def create_event(
    title:       str,
    start:       datetime,
    end:         datetime,
    description: str = "",
    location:    str = "",
    calendar_id: str = PRIMARY_CALENDAR,
    reminders:   list[int] | None = None,   # minutes before, e.g. [10, 30]
) -> dict:
    """
    Create a new calendar event. Returns the created event dict.

    Example:
        from datetime import datetime, timezone, timedelta
        start = datetime(2026, 5, 16, 14, 0, tzinfo=timezone.utc)
        create_event("Team standup", start, start + timedelta(hours=1))
    """
    if not is_authorized():
        return {"ok": False, "error": "Google not authorized"}
    try:
        def _fmt(dt: datetime) -> str:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.isoformat()

        body: dict = {
            "summary":     title,
            "description": description,
            "location":    location,
            "start": {"dateTime": _fmt(start), "timeZone": NAIROBI_TZ},
            "end":   {"dateTime": _fmt(end),   "timeZone": NAIROBI_TZ},
        }

        if reminders:
            body["reminders"] = {
                "useDefault": False,
                "overrides":  [{"method": "popup", "minutes": m} for m in reminders],
            }
        else:
            body["reminders"] = {"useDefault": True}

        result = _cal_post(f"calendars/{_safe_cal_id(calendar_id)}/events", body)
        event  = _parse_event(result)
        print(f"[CALENDAR] Created: {title} @ {start}")
        return {"ok": True, "event": event}

    except Exception as e:
        print(f"[CALENDAR] create_event failed: {e}")
        return {"ok": False, "error": str(e)}


def update_event(
    event_id:    str,
    title:       str | None = None,
    start:       datetime | None = None,
    end:         datetime | None = None,
    description: str | None = None,
    location:    str | None = None,
    calendar_id: str = PRIMARY_CALENDAR,
) -> dict:
    """
    Edit an existing event. Only pass the fields you want to change.
    Returns the updated event dict.
    """
    if not is_authorized():
        return {"ok": False, "error": "Google not authorized"}
    try:
        patch: dict = {}
        if title       is not None: patch["summary"]     = title
        if description is not None: patch["description"] = description
        if location    is not None: patch["location"]    = location
        if start is not None:
            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
            patch["start"] = {"dateTime": start.isoformat(), "timeZone": NAIROBI_TZ}
        if end is not None:
            if end.tzinfo is None:
                end = end.replace(tzinfo=timezone.utc)
            patch["end"] = {"dateTime": end.isoformat(), "timeZone": NAIROBI_TZ}

        if not patch:
            return {"ok": False, "error": "No fields to update"}

        result = _cal_patch(f"calendars/{_safe_cal_id(calendar_id)}/events/{event_id}", patch)
        event  = _parse_event(result)
        print(f"[CALENDAR] Updated event {event_id}")
        return {"ok": True, "event": event}

    except Exception as e:
        print(f"[CALENDAR] update_event failed: {e}")
        return {"ok": False, "error": str(e)}


def delete_event(
    event_id:    str,
    calendar_id: str = PRIMARY_CALENDAR,
) -> dict:
    """Delete an event by its ID."""
    if not is_authorized():
        return {"ok": False, "error": "Google not authorized"}
    try:
        ok = _cal_delete(f"calendars/{_safe_cal_id(calendar_id)}/events/{event_id}")
        print(f"[CALENDAR] Deleted event {event_id}: {ok}")
        return {"ok": ok}
    except Exception as e:
        print(f"[CALENDAR] delete_event failed: {e}")
        return {"ok": False, "error": str(e)}


def find_free_slot(
    duration_minutes: int = 60,
    hours_ahead:      int = 48,
    earliest_hour:    int = 8,    # don't suggest slots before 8am EAT
    latest_hour:      int = 18,   # don't suggest slots after 6pm EAT
    calendar_id:      str = PRIMARY_CALENDAR,
) -> dict:
    """
    Find the next free gap of `duration_minutes` in the calendar.
    Returns {"ok": True, "start": datetime, "end": datetime} or {"ok": False}.
    """
    if not is_authorized():
        return {"ok": False, "error": "Google not authorized"}
    try:
        events = get_upcoming_events(hours_ahead=hours_ahead, max_results=50,
                                     calendar_id=calendar_id)

        # Build list of busy windows
        busy: list[tuple[datetime, datetime]] = []
        for e in events:
            if e["all_day"]:
                continue
            try:
                s = datetime.fromisoformat(e["start"])
                en = datetime.fromisoformat(e["end"])
                if s.tzinfo is None: s  = s.replace(tzinfo=timezone.utc)
                if en.tzinfo is None: en = en.replace(tzinfo=timezone.utc)
                busy.append((s, en))
            except Exception:
                pass
        busy.sort()

        # Walk forward in 15-min increments
        eat = zoneinfo.ZoneInfo(NAIROBI_TZ)
        candidate = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        # Round up to next 15-min boundary
        mins = candidate.minute
        candidate += timedelta(minutes=(15 - mins % 15) % 15 or 15)
        deadline = candidate + timedelta(hours=hours_ahead)

        while candidate < deadline:
            slot_end = candidate + timedelta(minutes=duration_minutes)
            local    = candidate.astimezone(eat)

            # Check working hours
            if not (earliest_hour <= local.hour < latest_hour):
                # Jump to start of next working day
                next_day = (local + timedelta(days=1)).replace(
                    hour=earliest_hour, minute=0, second=0, microsecond=0)
                candidate = next_day.astimezone(timezone.utc)
                continue

            # Check for conflicts
            conflict = any(s < slot_end and en > candidate for s, en in busy)
            if not conflict:
                return {"ok": True, "start": candidate, "end": slot_end}

            # Advance past the conflicting event
            for s, en in busy:
                if s < slot_end and en > candidate:
                    candidate = en
                    break
            else:
                candidate += timedelta(minutes=15)

        return {"ok": False, "error": "No free slot found in the next 48 hours"}

    except Exception as e:
        print(f"[CALENDAR] find_free_slot failed: {e}")
        return {"ok": False, "error": str(e)}


def quick_event(
    natural_text: str,
    calendar_id:  str = PRIMARY_CALENDAR,
) -> dict:
    """
    Parse a natural-language event description and create it.
    Called by the brain router when the user says things like:
      "Schedule a team meeting tomorrow at 3pm for 1 hour"
      "Block 2 hours for deep work tomorrow morning"
      "Add dentist appointment Friday at 10am"

    Uses Groq to parse the intent, then calls create_event().
    Returns the created event or an error.
    """
    if not is_authorized():
        return {"ok": False, "error": "Google not authorized"}
    try:
        from ai_brain import ask_groq

        now_eat = _now_nairobi()
        prompt  = f"""Today is {now_eat.strftime('%A %d %B %Y, %H:%M')} EAT (Africa/Nairobi).

The user wants to create a calendar event. Extract the details from this request:
"{natural_text}"

Respond ONLY with a valid JSON object — no markdown, no explanation:
{{
  "title": "event title",
  "date": "YYYY-MM-DD",
  "start_time": "HH:MM",
  "end_time": "HH:MM",
  "location": "",
  "description": ""
}}

Rules:
- "tomorrow" = {(now_eat + timedelta(days=1)).strftime('%Y-%m-%d')}
- Default duration 1 hour if not specified
- Default time 09:00 if not specified
- 24-hour format for times
- Empty string for missing location/description"""

        raw = ask_groq(prompt)
        if isinstance(raw, dict):
            text = raw.get("reply") or raw.get("raw") or raw.get("text") or str(raw)
        else:
            text = str(raw)

        # Strip markdown fences if present
        text = re.sub(r"```(?:json)?|```", "", text).strip()
        parsed = json.loads(text)

        date_str  = parsed.get("date", now_eat.strftime("%Y-%m-%d"))
        start_str = parsed.get("start_time", "09:00")
        end_str   = parsed.get("end_time", "10:00")

        eat = zoneinfo.ZoneInfo(NAIROBI_TZ)

        start_dt = datetime.strptime(f"{date_str} {start_str}", "%Y-%m-%d %H:%M").replace(tzinfo=eat)
        end_dt   = datetime.strptime(f"{date_str} {end_str}",   "%Y-%m-%d %H:%M").replace(tzinfo=eat)

        return create_event(
            title       = parsed.get("title", natural_text[:60]),
            start       = start_dt,
            end         = end_dt,
            description = parsed.get("description", ""),
            location    = parsed.get("location", ""),
            calendar_id = calendar_id,
            reminders   = [10],   # 10-min popup by default
        )

    except json.JSONDecodeError as e:
        return {"ok": False, "error": f"Could not parse event details: {e}"}
    except Exception as e:
        print(f"[CALENDAR] quick_event failed: {e}\n{traceback.format_exc()}")
        return {"ok": False, "error": str(e)}