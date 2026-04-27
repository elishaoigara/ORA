"""
ORA Hallucination Guard

Prevents ORA from inventing tasks, events, spend data, or any facts
that aren't actually in memory/context.
"""

import re
from typing import Optional


_RISKY_PATTERNS = re.compile(
    r"\b(what tasks|how many tasks|any tasks|my tasks|show tasks|"
    r"what meetings|any meetings|my calendar|any events|"
    r"what goals|my goals|how many goals|"
    r"how much.*(spent|spend)|my spend|mpesa|"
    r"what.*(emails?|messages?)|any emails?|"
    r"remind me|did i|have i|what did|"
    r"how.*(doing|progressing)|status of|"
    r"what.*(last|recent|latest)|"
    r"any (alerts?|notifications?|updates?))\b",
    re.IGNORECASE
)

_INVENTION_MARKERS = re.compile(
    r"\b(for example|such as|typically|usually|often|generally|"
    r"you might|you could|i would suggest|i recommend|consider|"
    r"it appears|it seems|based on typical|assuming|"
    r"probably|likely have|might have)\b",
    re.IGNORECASE
)


def is_factual_query(text: str) -> bool:
    return bool(_RISKY_PATTERNS.search(text))


def build_grounding_instruction(has_tasks: bool, has_goals: bool,
                                 has_calendar: bool, has_spend: bool) -> str:
    lines = [
        "## GROUNDING RULES — FOLLOW STRICTLY",
        "Only state facts that appear in the context above.",
        "If something isn't in context, say so — never invent or estimate.",
        "",
    ]

    if not has_tasks:
        lines.append("TASKS: No pending tasks in memory. Do NOT list or invent tasks.")
    if not has_goals:
        lines.append("GOALS: No active goals in memory. Do NOT invent goal progress.")
    if not has_calendar:
        lines.append("CALENDAR: Not connected or no events. Say so — don't invent meetings.")
    if not has_spend:
        lines.append("SPEND: No M-Pesa data available. Do NOT estimate spending figures.")

    lines += [
        "",
        "Do NOT use 'for example', 'typically', 'you might have' for factual questions about Elisha's data.",
    ]

    return "\n".join(lines)


def check_response_for_hallucinations(response: str, query: str,
                                       actual_task_count: int = 0,
                                       actual_goal_count: int = 0) -> tuple[str, list[str]]:
    warnings = []

    if is_factual_query(query) and _INVENTION_MARKERS.search(response):
        warnings.append("Response contains speculation language for a factual query")

    task_count_match = re.search(r"\b(\d+)\s+(?:pending\s+)?tasks?\b", response, re.I)
    if task_count_match and actual_task_count >= 0:
        claimed = int(task_count_match.group(1))
        if abs(claimed - actual_task_count) > 1:
            warnings.append(
                f"Claimed {claimed} tasks but actual count is {actual_task_count}"
            )

    return response, warnings


def context_has_tasks(tasks: list) -> bool:
    return len(tasks) > 0

def context_has_goals(goals: list) -> bool:
    return len(goals) > 0

def context_has_calendar(calendar_events: list) -> bool:
    return len(calendar_events) > 0

def context_has_spend(spend_data: Optional[dict]) -> bool:
    if not spend_data:
        return False
    return spend_data.get("today", 0) > 0 or bool(spend_data.get("recent_transactions"))