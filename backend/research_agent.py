"""
ORA Research Agent — Intelligence Core v3 (FIXED)
=================================================
"""

from __future__ import annotations

import os
import json
import time
import hashlib
import sqlite3
import re
from datetime import datetime
from typing import List, Dict, Any

from groq import Groq

try:
    from tavily import TavilyClient
except Exception:
    TavilyClient = None

import config


# ─────────────────────────────────────────────
# INIT DB (FIXED - CRITICAL)
# ─────────────────────────────────────────────

def init_db():
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS research_sessions (
            session_id TEXT PRIMARY KEY,
            title TEXT,
            query TEXT,
            result TEXT,
            sources TEXT,
            citations TEXT,
            word_count INTEGER,
            updated_at TEXT
        )
    """)
    conn.commit()
    conn.close()


init_db()  # MUST RUN ON IMPORT


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
    if not key or TavilyClient is None:
        return None
    return TavilyClient(api_key=key)


# ─────────────────────────────────────────────
# WEB SEARCH
# ─────────────────────────────────────────────

def _web_search(query: str, max_results: int = 5):
    client = _tavily_client()

    if not client:
        print("[Web Search] Tavily not available → fallback mode")
        return []

    try:
        res = client.search(query=query, max_results=max_results)
        return res.get("results", [])
    except Exception as e:
        print("[Web Search Error]", e)
        return []


def _format_web(results):
    if not results:
        return ""

    return "\n\n".join([
        f"[{i+1}] {r.get('title','')}\n{r.get('content','')}\nSource: {r.get('url','')}"
        for i, r in enumerate(results)
    ])


# ─────────────────────────────────────────────
# GROQ CALL
# ─────────────────────────────────────────────

def _call_groq(messages, model="llama-3.3-70b-versatile",
               max_tokens=3000, temperature=0.3):

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

    raise RuntimeError("Groq API failed")


# ─────────────────────────────────────────────
# PROMPTS
# ─────────────────────────────────────────────

SYSTEM_PROMPT = """
You are a senior AI research analyst.
Be precise, factual, and analytical.
"""

REFINER_PROMPT = """
Improve clarity, depth, and specificity.
Return only improved output.
"""


# ─────────────────────────────────────────────
# SESSION HELPERS
# ─────────────────────────────────────────────

def _new_session_id(query: str):
    return hashlib.md5(f"{query}{datetime.utcnow()}".encode()).hexdigest()[:12]


def _save_session(session_id, title, query, result, sources, citations, word_count):
    conn = sqlite3.connect(config.DB_PATH)

    conn.execute("""
        INSERT OR REPLACE INTO research_sessions
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


def _extract_citations(text: str):
    return re.findall(r"\[Source:\s*(.*?)\]", text)


# ─────────────────────────────────────────────
# MAIN RESEARCH ENGINE
# ─────────────────────────────────────────────

def deep_research(query: str, n_sources: int = 5):

    session_id = _new_session_id(query)

    web_results = _web_search(query, n_sources)
    web_context = _format_web(web_results)

    prompt = f"""
Topic: {query}

Sources:
{web_context or "No sources available"}

Rules:
- Use only sources above
- Be factual and specific
"""

    draft = _call_groq([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt}
    ])

    refined = _call_groq([
        {"role": "system", "content": REFINER_PROMPT},
        {"role": "user", "content": draft}
    ], temperature=0.2)

    citations = _extract_citations(refined)
    sources = [r.get("url") for r in web_results if r.get("url")]

    _save_session(
        session_id,
        query[:60],
        query,
        refined,
        sources,
        citations,
        len(refined.split())
    )

    return {
        "session_id": session_id,
        "title": query[:60],
        "result": refined,
        "sources": sources,
        "word_count": len(refined.split()),
        "status": "complete"
    }


# ─────────────────────────────────────────────
# DOCUMENT ANALYSIS
# ─────────────────────────────────────────────

def analyze_document(query: str, filename: str, text: str):

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

    _save_session(
        session_id,
        f"Analysis: {filename}",
        query,
        refined,
        [filename],
        [],
        len(refined.split())
    )

    return {
        "session_id": session_id,
        "result": refined,
        "status": "complete"
    }


# ─────────────────────────────────────────────
# SESSION API (FIXED)
# ─────────────────────────────────────────────

def get_sessions(limit: int = 15):

    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row

    try:
        rows = conn.execute("""
            SELECT session_id, title, query, result, word_count, updated_at
            FROM research_sessions
            ORDER BY updated_at DESC
            LIMIT ?
        """, (limit,)).fetchall()
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()

    return [dict(r) for r in rows]