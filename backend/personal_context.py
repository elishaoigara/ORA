"""Structured, cached personal context for ORA's autonomous agent.

The service is deliberately read-only. It gathers existing ORA sources into one
stable JSON shape so the API, agent, briefing, and future approval workflows can
reason from the same snapshot instead of each connector being called ad hoc.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime
from typing import Any

_CACHE_TTL_SECONDS = 45
_cache_lock = threading.Lock()
_cached_context: dict[str, Any] | None = None
_cached_at = 0.0


def _now() -> datetime:
    return datetime.now().astimezone()


def _task_dict(row: tuple) -> dict[str, Any]:
    return {
        "id": row[0],
        "title": row[1],
        "priority": row[2],
        "created_at": row[3],
        "due_at": row[4],
        "goal_id": row[5] if len(row) > 5 else None,
    }


def _preference_dict(row: tuple) -> dict[str, Any]:
    return {
        "category": row[0],
        "key": row[1],
        "value": row[2],
        "confidence": row[3],
    }


def _alert_dict(row: tuple) -> dict[str, Any]:
    return {
        "id": row[0],
        "rule_name": row[1],
        "message": row[2],
        "severity": row[3],
        "timestamp": row[4],
        "acknowledged": bool(row[5]),
    }


def _memory_dict(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        return item
    if isinstance(item, (tuple, list)):
        if len(item) == 5:
            keys = ("event_type", "summary", "detail", "importance", "timestamp")
        else:
            keys = ("id", "event_type", "summary", "detail", "importance", "timestamp")
        return {key: item[index] for index, key in enumerate(keys[:len(item)])}
    return {"summary": str(item)}


def _safe_call(default: Any, fn, *args, **kwargs) -> Any:
    try:
        return fn(*args, **kwargs)
    except Exception:
        return default


def _google_context() -> dict[str, Any]:
    try:
        from connectors.google_auth import is_authorized
        connected = bool(is_authorized("primary"))
    except Exception:
        connected = False

    result: dict[str, Any] = {
        "connected": connected,
        "calendar_today": [],
        "calendar_imminent": [],
        "gmail": {},
    }
    if not connected:
        return result

    try:
        from connectors.calendar import get_events_today, get_imminent_events
        result["calendar_today"] = get_events_today()
        result["calendar_imminent"] = get_imminent_events(30)
    except Exception:
        pass

    try:
        from connectors.gmail import get_gmail_summary
        result["gmail"] = get_gmail_summary() or {}
    except Exception:
        pass
    return result


def _build_uncached_context() -> dict[str, Any]:
    now = _now()

    try:
        from memory.profile import get_all_profile
        profile = get_all_profile() or {}
    except Exception:
        profile = {}

    try:
        from memory.preferences import get_preferences
        preferences = [_preference_dict(row) for row in (get_preferences() or [])]
    except Exception:
        preferences = []

    try:
        from memory.events import get_recent_events
        memory = [_memory_dict(item) for item in (get_recent_events(limit=10) or [])]
    except Exception:
        memory = []

    try:
        from intelligence.learning_engine import get_learned_facts
        learned_facts = get_learned_facts(status="confirmed", limit=20)
    except Exception:
        learned_facts = []

    try:
        from database import get_recent_alerts
        alerts = [_alert_dict(row) for row in (get_recent_alerts(limit=20) or [])]
    except Exception:
        alerts = []

    try:
        from intelligence.priority_engine import get_prioritized_tasks
        task_rows = get_prioritized_tasks() or []
    except Exception:
        task_rows = []
    tasks = [_task_dict(row) for row in task_rows]

    overdue = []
    for task in tasks:
        due_at = task.get("due_at")
        if due_at:
            try:
                if datetime.fromisoformat(due_at) < now.replace(tzinfo=None):
                    overdue.append(task)
            except Exception:
                pass

    try:
        from intelligence.goals_engine import get_goals
        goals = get_goals("active") or []
    except Exception:
        goals = []

    for goal in goals:
        goal["next_action"] = next(
            (task for task in tasks if task.get("goal_id") == goal.get("id")),
            None,
        )

    google = _google_context()

    weather = _safe_call({}, lambda: __import__("connectors.weather", fromlist=["get_weather"]).get_weather())
    weather_summary = _safe_call("", lambda: __import__("connectors.weather", fromlist=["get_weather_summary"]).get_weather_summary())

    try:
        from mpesa_engine import get_today_spend, get_average_daily_spend
        spend_today = float(get_today_spend() or 0)
        spend_average = float(get_average_daily_spend() or 0)
    except Exception:
        spend_today = 0.0
        spend_average = 0.0
    spend_ratio = spend_today / spend_average if spend_average else 1.0

    predictions = _safe_call([], lambda: __import__("intelligence.prediction_engine", fromlist=["predict_needs"]).predict_needs())
    spend_alert = _safe_call(None, lambda: __import__("mpesa_engine", fromlist=["check_spend_alert"]).check_spend_alert())
    top_task = tasks[0] if tasks else None
    focus = top_task.get("title") if top_task else (goals[0].get("goal") if goals else None)

    if len(overdue) > 2:
        state = "overloaded"
    elif spend_ratio > 1.3:
        state = "financial_pressure"
    elif len(google["calendar_today"]) > 5:
        state = "busy"
    elif not tasks:
        state = "idle"
    else:
        state = "balanced"

    return {
        "generated_at": now.isoformat(),
        "state": state,
        "focus": focus,
        "profile": profile,
        "preferences": preferences,
        "memory": memory,
        "learned_facts": learned_facts,
        "alerts": alerts,
        "tasks": tasks,
        "overdue": overdue,
        "goals": goals,
        "google": google,
        "weather": weather,
        "weather_summary": weather_summary,
        "spending": {
            "today": spend_today,
            "average_daily": spend_average,
            "ratio": round(spend_ratio, 3),
        },
        "spend_alert": spend_alert,
        "predictions": predictions if isinstance(predictions, list) else [],
        "summary": {
            "pending_tasks": len(tasks),
            "overdue_tasks": len(overdue),
            "goals": len(goals),
            "calendar_events": len(google["calendar_today"]),
            "unread_emails": google.get("gmail", {}).get("unread_count", 0),
            "unread_alerts": sum(1 for alert in alerts if not alert["acknowledged"]),
            "confirmed_memories": len(learned_facts),
        },
        "sources": {
            "profile": bool(profile),
            "memory": bool(memory) or bool(learned_facts),
            "confirmed_memory": bool(learned_facts),
            "google": google["connected"],
            "weather": bool(weather or weather_summary),
            "tasks": True,
            "goals": True,
        },
    }


def build_personal_context(force: bool = False) -> dict[str, Any]:
    """Return a cached, structured snapshot of the user's current context."""
    global _cached_context, _cached_at
    now = time.monotonic()
    with _cache_lock:
        if not force and _cached_context is not None and now - _cached_at < _CACHE_TTL_SECONDS:
            return _cached_context
        _cached_context = _build_uncached_context()
        _cached_at = now
        return _cached_context


def clear_context_cache() -> None:
    global _cached_context, _cached_at
    with _cache_lock:
        _cached_context = None
        _cached_at = 0.0
