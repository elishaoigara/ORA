"""Grounded system-prompt context backed by ORA's canonical snapshot."""

from __future__ import annotations

import json
from typing import Any


def build_context(query: str | None = None) -> str:
    """Format the structured personal context for model prompts.

    The snapshot itself remains available through ``/api/context``. This
    formatter exists for the existing chat, Telegram, and coordinator callers.
    """
    from personal_context import build_personal_context

    snapshot = build_personal_context()
    prompt_view: dict[str, Any] = {
        "generated_at": snapshot.get("generated_at"),
        "state": snapshot.get("state"),
        "focus": snapshot.get("focus"),
        "summary": snapshot.get("summary", {}),
        "profile": snapshot.get("profile", {}),
        "preferences": snapshot.get("preferences", []),
        "memory": snapshot.get("memory", []),
        "tasks": snapshot.get("tasks", []),
        "overdue": snapshot.get("overdue", []),
        "goals": snapshot.get("goals", []),
        "google": snapshot.get("google", {}),
        "weather_summary": snapshot.get("weather_summary", ""),
        "spending": snapshot.get("spending", {}),
        "predictions": snapshot.get("predictions", []),
    }
    if query:
        prompt_view["user_query"] = query
    return json.dumps(prompt_view, ensure_ascii=False, default=str, indent=2)


def build_system_prompt(query: str | None = None) -> str:
    context = build_context(query=query)
    return (
        "You are ORA — Elisha's personal AI chief of staff, based in Nairobi, Kenya.\n\n"
        "PERSONALITY:\n"
        "- Direct, intelligent, warm, and concise.\n"
        "- Speak like a trusted advisor who pays attention.\n"
        "- Reduce cognitive load and prefer one useful next step.\n\n"
        "OPERATING RULES:\n"
        "- Use only the supplied context and clearly distinguish facts from suggestions.\n"
        "- Never invent missing personal data. Say when a source is unavailable.\n"
        "- Prefer concrete next actions over generic encouragement.\n"
        "- Do not send messages, change appointments, delete data, or handle money without confirmation.\n"
        "- When the user states a preference or correction, treat it as a candidate memory and confirm when ambiguous.\n\n"
        "=== CANONICAL PERSONAL CONTEXT ===\n"
        f"{context}\n"
        "=== END CANONICAL PERSONAL CONTEXT ==="
    )
