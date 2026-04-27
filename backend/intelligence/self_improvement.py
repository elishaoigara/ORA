"""
ORA Self-Improvement — Render Free-Tier Optimized
Uses 8B model for critiques (not 70B).
Only critiques responses >30 words.
"""

import os
from groq import Groq

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
_MODEL = "llama-3.1-8b-instant"


def critique_response(user_input: str, ora_response: str) -> list[str]:
    if not GROQ_API_KEY:
        return []
    if len(ora_response.split()) < 30:
        return []

    client = Groq(api_key=GROQ_API_KEY)
    prompt = (
        f"Briefly critique this AI response. List issues only (1 per line, max 3). "
        f"Focus on: hallucinations, unhelpful hedging, wrong tone, missing info.\n\n"
        f"User: {user_input[:200]}\n"
        f"AI: {ora_response[:300]}\n\n"
        f"Issues (or write 'none'):"
    )

    try:
        resp = client.chat.completions.create(
            model=_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100,
            temperature=0.3,
        )
        raw = resp.choices[0].message.content or ""
        text = raw.strip()
        if text.lower().startswith("none"):
            return []
        return [line.strip() for line in text.split("\n") if line.strip()][:3]
    except Exception as e:
        print(f"[SELF-IMPROVEMENT] Critique failed: {e}")
        return []


def refine_response(user_input: str, original_response: str, issues: list[str]) -> str:
    if not issues or not GROQ_API_KEY:
        return original_response

    client = Groq(api_key=GROQ_API_KEY)
    issues_str = "\n".join(f"- {i}" for i in issues)
    prompt = (
        f"Improve this AI response based on the issues listed.\n\n"
        f"User: {user_input[:200]}\n"
        f"Original: {original_response[:400]}\n"
        f"Issues:\n{issues_str}\n\n"
        f"Improved response:"
    )

    try:
        resp = client.chat.completions.create(
            model=_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
            temperature=0.4,
        )
        raw = resp.choices[0].message.content or ""
        return raw.strip()
    except Exception as e:
        print(f"[SELF-IMPROVEMENT] Refinement failed: {e}")
        return original_response