"""
ORA Router — Classifies queries and picks the right response strategy.
All routes use Groq only. No external APIs.

Query types:
  simple   → short factual / greeting / task → small model, cached
  document → asks about uploaded docs        → KB lookup first, then Groq
  complex  → long / planning / reasoning     → big model, full context
"""

import re


# ── Keywords that signal document-related intent ──────────────
_DOC_PATTERNS = re.compile(
    r"\b(summarize|summary|document|pdf|file|uploaded|notes|report|"
    r"according to|based on|from the|what does .* say|tell me about the)\b",
    re.IGNORECASE,
)

_COMPLEX_PATTERNS = re.compile(
    r"\b(plan|strategy|analyze|compare|explain|why|how should|"
    r"what would|recommend|advice|steps|roadmap|breakdown)\b",
    re.IGNORECASE,
)


def classify(query: str) -> str:
    """
    Returns: 'simple' | 'document' | 'complex'
    """
    q = query.strip()

    # Very short = simple
    if len(q.split()) <= 6:
        return "simple"

    if _DOC_PATTERNS.search(q):
        return "document"

    if len(q) > 200 or _COMPLEX_PATTERNS.search(q):
        return "complex"

    return "simple"


def model_for(query_type: str) -> tuple[str, int]:
    """
    Returns (model_name, max_tokens) for the query type.
    Groq only — tiered by cost.
    """
    if query_type == "simple":
        return "llama-3.1-8b-instant", 180

    if query_type == "document":
        return "llama-3.1-8b-instant", 350   # KB does the heavy lifting

    # complex
    return "llama-3.3-70b-versatile", 500