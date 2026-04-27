"""
ORA Hallucination Guard — strict, enforced version

- Detects factual queries
- Blocks responses when required data is missing
- Prevents speculative language
- Normalizes spend data safely
"""

import re
from typing import Optional, Tuple, List


# ---------------------------
# QUERY DETECTION
# ---------------------------

_RISKY_PATTERNS = re.compile(
    r"\b(what tasks|how many tasks|any tasks|my tasks|show tasks|"
    r"what meetings|any meetings|my calendar|any events|"
    r"what goals|my goals|how many goals|"
    r"how much.*(spent|spend)|my spend|mpesa|"
    r"what.*(emails?|messages?)|any emails?|"
    r"remind me|did i|have i|what did|"
    r"how.*(doing|progressing)|status of|"
    r"what.*(last|recent|latest)|"
    r"any (alerts?|notifications?|updates?)|"
    r"(hello|hi|hey|what's up|update me))\b",
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


# ---------------------------
# CONTEXT STATE HELPERS
# ---------------------------

def context_has_tasks(tasks: Optional[list]) -> bool:
    return bool(tasks)


def context_has_goals(goals: Optional[list]) -> bool:
    return bool(goals)


def context_has_calendar(events: Optional[list]) -> bool:
    return bool(events)


def context_has_spend(spend_data: Optional[dict]) -> bool:
    """
    Safe spend detection (fixes your crash)
    """
    if not spend_data:
        return False

    today = spend_data.get("today", 0)

    try:
        if isinstance(today, dict):
            today = float(today.get("amount", 0))
        else:
            today = float(today)

        return today > 0 or bool(spend_data.get("recent_transactions"))

    except Exception:
        return False


# ---------------------------
# GROUNDING INSTRUCTION
# ---------------------------

def build_grounding_instruction(
    has_tasks: bool,
    has_goals: bool,
    has_calendar: bool,
    has_spend: bool
) -> str:

    lines = [
        "## GROUNDING RULES — FOLLOW STRICTLY",
        "Only state facts that appear in the context.",
        "If something isn't available, say so — never invent.",
        ""
    ]

    if not has_tasks:
        lines.append("TASKS: No tasks in memory. Do NOT invent tasks.")

    if not has_goals:
        lines.append("GOALS: No goals in memory. Do NOT invent progress.")

    if not has_calendar:
        lines.append("CALENDAR: No events or not connected. Do NOT invent meetings.")

    if not has_spend:
        lines.append("SPEND: No M-Pesa data. Do NOT estimate spending.")

    lines.append("")
    lines.append("Do NOT use speculative language like 'typically', 'you might', etc.")

    return "\n".join(lines)


# ---------------------------
# HARD BLOCK (CRITICAL)
# ---------------------------

def enforce_grounding(
    query: str,
    has_tasks: bool,
    has_goals: bool,
    has_calendar: bool,
    has_spend: bool
) -> Optional[str]:
    """
    HARD STOP before LLM is called
    """

    q = query.lower()

    # spending
    if "spend" in q or "mpesa" in q:
        if not has_spend:
            return "I don't have your spending data yet."

    # calendar
    if any(x in q for x in ["meeting", "calendar", "event"]):
        if not has_calendar:
            return "No events in your calendar today."

    # tasks
    if "task" in q:
        if not has_tasks:
            return "No tasks in memory."

    # goals
    if "goal" in q:
        if not has_goals:
            return "No goals in memory."

    return None


# ---------------------------
# RESPONSE VALIDATION (POST LLM)
# ---------------------------

def check_response_for_hallucinations(
    response: str,
    query: str,
    actual_task_count: int = 0,
    actual_goal_count: int = 0
) -> Tuple[str, List[str]]:

    warnings = []

    # speculative language on factual query
    if is_factual_query(query) and _INVENTION_MARKERS.search(response):
        warnings.append("Speculative language detected")

    # task count mismatch
    match = re.search(r"\b(\d+)\s+tasks?\b", response, re.I)
    if match:
        claimed = int(match.group(1))
        if abs(claimed - actual_task_count) > 1:
            warnings.append(
                f"Task mismatch: claimed {claimed}, actual {actual_task_count}"
            )

    return response, warnings


# ---------------------------
# SAFE RESPONSE WRAPPER
# ---------------------------

def safe_llm_response(
    query: str,
    llm_response: str,
    has_tasks: bool,
    has_goals: bool,
    has_calendar: bool,
    has_spend: bool
) -> str:
    """
    Final safety layer AFTER LLM
    """

    # block speculative answers
    if is_factual_query(query) and _INVENTION_MARKERS.search(llm_response):
        return "I don't have enough data to answer that."

    # block forbidden claims
    if not has_calendar and "meeting" in llm_response.lower():
        return "No calendar data available."

    if not has_spend and "spent" in llm_response.lower():
        return "No spending data available."

    return llm_response