"""
ORA Research Agent — Intelligence Core v3 (FIXED)
=================================================
- Tavily web search integrated properly
- Clean function structure (no global execution bugs)
- Groq reasoning pipeline (draft → refine)
- Citation extraction
- Render-safe
"""

from __future__ import annotations

import os
import json
import time
import hashlib
import sqlite3
import re
from datetime import datetime
from typing import List, Dict, Any, Optional

from groq import Groq
from tavily import TavilyClient


# ─────────────────────────────────────────────
# CLIENTS
# ─────────────────────────────────────────────

def _groq_client():
    key = os.getenv("GROQ_API_KEY")
    if not key:
        raise RuntimeError("Missing GROQ_API_KEY")
    return Groq(api_key=key)


def _tavily_client():
    key = os.getenv("TAVILY_API_KEY")
    if not key:
        return None
    return TavilyClient(api_key=key)


# ─────────────────────────────────────────────
# WEB SEARCH (TAVILY)
# ─────────────────────────────────────────────

def _web_search(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    client = _tavily_client()
    if not client:
        return []

    try:
        res = client.search(query=query, max_results=max_results)
        return res.get("results", [])
    except Exception as e:
        print("[Tavily Error]", e)
        return []


def _format_web(results: List[Dict[str, Any]]) -> str:
    if not results:
        return ""

    formatted = []
    for i, r in enumerate(results, 1):
        formatted.append(
            f"[{i}] {r.get('title','')}\n"
            f"{r.get('content','')}\n"
            f"Source: {r.get('url','')}"
        )
    return "\n\n".join(formatted)


# ─────────────────────────────────────────────
# GROQ CALL
# ─────────────────────────────────────────────

def _call_groq(messages, model="llama-3.3-70b-versatile",
               max_tokens=3000, temperature=0.3) -> str:
    client = _groq_client()

    for attempt in range(3):
        try:
            res = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return res.choices[0].message.content or ""
        except Exception as e:
            print("[Groq retry]", e)
            time.sleep(1.5 * (attempt + 1))

    raise RuntimeError("Groq API failed after retries")


# ─────────────────────────────────────────────
# PROMPTS
# ─────────────────────────────────────────────

SYSTEM_PROMPT = """
You are a senior AI research analyst.

RULES:
- No vague language
- Always include specific systems, models, companies, or numbers
- Every claim must be grounded in evidence when available
- Focus on insight, not summary

STRUCTURE:
1. Thesis
2. Analytical sections (4–6)
3. Implications
4. Key Takeaways
"""


REFINER_PROMPT = """
Improve this research:
- remove vagueness
- increase specificity
- strengthen reasoning
- add analytical depth

Return only improved version.
"""


# ─────────────────────────────────────────────
# SESSION
# ─────────────────────────────────────────────

def _new_session_id(query: str) -> str:
    return hashlib.md5(f"{query}{datetime.utcnow()}".encode()).hexdigest()[:12]


def _save_session(session_id, title, query, result, sources, citations, word_count):
    from config import DB_PATH

    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT OR REPLACE INTO research_sessions
        (session_id, title, query, result, sources, citations, word_count, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
    """, (
        session_id,
        title,
        query,
        result,
        json.dumps(sources),
        json.dumps(citations),
        word_count
    ))
    conn.commit()
    conn.close()


# ─────────────────────────────────────────────
# UTIL
# ─────────────────────────────────────────────

def _extract_citations(text: str) -> List[str]:
    return re.findall(r"\[Source:\s*(.*?)\]", text)


# ─────────────────────────────────────────────
# MAIN: DEEP RESEARCH
# ─────────────────────────────────────────────

def deep_research(query: str) -> Dict[str, Any]:
    session_id = _new_session_id(query)

    # 1. WEB SEARCH
    web_results = _web_search(query)
    web_context = _format_web(web_results)

    # 2. BUILD PROMPT
    user_prompt = f"""
Research Topic: {query}

Use ONLY these sources:

{web_context if web_context else "No web sources available."}

Rules:
- Do NOT hallucinate facts
- Every claim must reference a source URL if available
- Be specific: models, companies, dates, metrics
"""

    # 3. DRAFT
    draft = _call_groq([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt}
    ])

    # 4. REFINE
    refined = _call_groq([
        {"role": "system", "content": REFINER_PROMPT},
        {"role": "user", "content": draft}
    ], temperature=0.2)

    citations = _extract_citations(refined)
    word_count = len(refined.split())

    title = query[:60]

    sources = [r.get("url") for r in web_results if r.get("url")]

    _save_session(
        session_id,
        title,
        query,
        refined,
        sources,
        citations,
        word_count
    )

    return {
        "session_id": session_id,
        "title": title,
        "result": refined,
        "sources": sources,
        "word_count": word_count,
        "status": "complete"
    }


# ─────────────────────────────────────────────
# DOCUMENT ANALYSIS
# ─────────────────────────────────────────────

def analyze_document(query: str, filename: str, text: str) -> Dict[str, Any]:
    session_id = _new_session_id(filename)

    context = text[:8000]

    draft = _call_groq([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"{context}\n\nQuestion: {query}"}
    ])

    refined = _call_groq([
        {"role": "system", "content": REFINER_PROMPT},
        {"role": "user", "content": draft}
    ])

    word_count = len(refined.split())

    _save_session(
        session_id,
        f"Analysis: {filename}",
        query,
        refined,
        [filename],
        [],
        word_count
    )

    return {
        "session_id": session_id,
        "result": refined,
        "status": "complete"
    }