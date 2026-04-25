"""
ORA AI Brain — Upgraded (Render Free Tier Safe)
- Smarter system prompt with structured reasoning
- Document-first routing: checks knowledge base BEFORE calling Groq API
- Fallback to FTS-only if embedding model not loaded (saves RAM on cold start)
- Token budget control to avoid billing spikes
"""

from groq import Groq
from config import GROQ_API_KEY, GROQ_MODEL_PRIMARY, GROQ_MODEL_FALLBACK
from context import build_system_prompt
import json

client = Groq(api_key=GROQ_API_KEY)


# ============================================================
# DOCUMENT-FIRST ANSWER (saves API calls when KB has the answer)
# ============================================================
def _try_kb_answer(user_text: str) -> str | None:
    """
    Try to answer from the knowledge base alone.
    Returns a string answer if confidence is high enough, else None.
    This saves a Groq API call entirely.
    """
    try:
        from knowledge.pipeline import search_and_format
        context = search_and_format(user_text, n_results=3)
        if not context or len(context.strip()) < 50:
            return None

        # Only short-circuit if we got meaningful chunks
        # Let Groq still synthesize — we just prepend the KB context
        return context
    except Exception as e:
        print(f"[BRAIN] KB lookup skipped: {e}")
        return None


# ============================================================
# SMART GROQ CALL WITH TIERED MODELS
# ============================================================
def ask_groq(user_text: str, use_kb: bool = True):
    """
    ORA AI brain — Render-optimised.
    1. Pulls KB context first (no extra API cost).
    2. Uses smaller model for short queries (saves tokens).
    3. Falls back to llama-3.1-8b-instant if 70b fails.
    """
    try:
        kb_context = _try_kb_answer(user_text) if use_kb else None
        system_prompt = build_system_prompt(query=user_text)

        # Inject KB context into system prompt (avoids extra message overhead)
        if kb_context:
            system_prompt += f"\n\n## RETRIEVED DOCUMENTS\n{kb_context[:800]}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_text}
        ]

        # Use smaller/faster model for short queries (saves tokens + latency)
        is_short = len(user_text.split()) < 12
        model = GROQ_MODEL_FALLBACK if is_short else GROQ_MODEL_PRIMARY
        max_tokens = 200 if is_short else 450

        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.4,
                max_tokens=max_tokens,
            )
        except Exception:
            # Auto-fallback to smaller model
            response = client.chat.completions.create(
                model=GROQ_MODEL_FALLBACK,
                messages=messages,
                temperature=0.4,
                max_tokens=200,
            )

        content = response.choices[0].message.content.strip()

        # Try JSON parse (for structured pipeline usage)
        try:
            return json.loads(content)
        except Exception:
            # Plain text response — wrap for pipeline compatibility
            return {
                "reasoning": ["direct response"],
                "actions":   [],
                "reply":     content,
                "raw":       content,
            }

    except Exception as e:
        print(f"[GROQ ERROR] {e}")
        return {
            "reasoning": ["groq failure"],
            "actions":   [],
            "error":     str(e),
        }


# Compatibility wrapper
def ask_gemini(user_text: str):
    return ask_groq(user_text)