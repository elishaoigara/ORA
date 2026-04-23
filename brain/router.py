import re
from dataclasses import dataclass
from typing import Literal, Dict


Intent = Literal[
    "status",
    "alerts",
    "task",
    "ack",
    "reminder",
    "mood",
    "memory",
    "chat"
]


@dataclass
class RouteResult:
    intent: Intent
    confidence: float
    use_llm: bool = False


# =========================
# TIER 1: FAST RULE ROUTES
# =========================
RULES = {
    "status": r"^/\s*status",
    "alerts": r"^/\s*alerts",
    "task": r"^/\s*task",
    "ack": r"^/\s*ack",
    "reminder": r"^/\s*remind",
    "mood": r"^/\s*mood",
}


MEMORY_KEYWORDS = [
    "remember", "do you remember", "what did we discuss",
    "earlier", "yesterday", "last time",
    "previous chat", "what did i say", "recall"
]


# =========================
# ROUTER CORE
# =========================
def classify_intent(text: str) -> RouteResult:
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)

    # -------------------------
    # TIER 1: RULE MATCHING
    # -------------------------
    for intent, pattern in RULES.items():
        if re.search(pattern, text):
            return RouteResult(intent=intent, confidence=1.0, use_llm=False)

    # -------------------------
    # TIER 2: MEMORY DETECTION
    # -------------------------
    if any(k in text for k in MEMORY_KEYWORDS):
        return RouteResult(intent="memory", confidence=0.85, use_llm=False)

    # -------------------------
    # TIER 2: SIMPLE HEURISTICS
    # -------------------------
    score_chat = 0.5

    if "?" in text:
        score_chat += 0.1

    if len(text) < 10:
        score_chat += 0.2

    # If vague → escalate to LLM
    if score_chat < 0.7:
        return RouteResult(
            intent="chat",
            confidence=score_chat,
            use_llm=True  # ONLY here we call Groq
        )

    return RouteResult(intent="chat", confidence=score_chat, use_llm=False)