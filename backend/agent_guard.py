"""
ORA Agent Guard — Deduplication for agent actions.

Prevents the same notification key from firing more than once
per cooldown window. In-memory only — resets on server restart,
which is acceptable (Render restarts are infrequent, and sending
one duplicate alert after a restart is fine).

Usage:
    from agent_guard import can_fire, mark_fired

    if can_fire("overdue_tasks"):
        notify("...")
        mark_fired("overdue_tasks")
"""

from __future__ import annotations

import time

# key → last fired timestamp (unix seconds)
_fired: dict[str, float] = {}

# Default cooldowns per action key pattern
_COOLDOWNS: dict[str, float] = {
    "spend_spike":       3 * 3600,   # 3 h
    "overdue_tasks":     2 * 3600,   # 2 h
    "morning_top_task":  20 * 3600,  # once per day
    "task_backlog":      4 * 3600,   # 4 h
    "morning_brief":     20 * 3600,
    "night_work":        6 * 3600,
    "task_overload":     4 * 3600,
    "peak_time":         6 * 3600,
    "delay_warning":     6 * 3600,
    "default":           1 * 3600,   # fallback: 1 h
}


def _cooldown_for(key: str) -> float:
    """Return the cooldown seconds for a given action key."""
    for pattern, seconds in _COOLDOWNS.items():
        if pattern == "default":
            continue
        if key.startswith(pattern):
            return seconds
    return _COOLDOWNS["default"]


def can_fire(key: str) -> bool:
    """Return True if this action key is past its cooldown window."""
    cooldown = _cooldown_for(key)
    last = _fired.get(key, 0.0)
    return (time.time() - last) >= cooldown


def mark_fired(key: str) -> None:
    """Record that this action key was just executed."""
    _fired[key] = time.time()


def reset(key: str) -> None:
    """Clear a key's cooldown (useful in tests or manual triggers)."""
    _fired.pop(key, None)


def reset_all() -> None:
    """Clear all cooldowns."""
    _fired.clear()