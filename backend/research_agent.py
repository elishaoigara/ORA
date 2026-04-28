"""
ORA Research Agent — STEP 3 FIX (API CONTRACT STABLE)
=====================================================
Fixes:
- generate_presentation import error
- write_essay missing safely
- KeyError: mode in stats endpoint
- Unified session schema
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

try:
    from tavily import TavilyClient
except Exception:
    TavilyClient = None

import config


# ─────────────────────────────────────────────
# DB INIT (SAFE FOR RENDER)
# ─────────────────────────────────────────────

def init_db():
    conn = sqlite3.connect(config.DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS research_sessions (
            session_id TEXT PRIMARY KEY,
            title TEXT,
            query TEXT,
            result TEXT,
            sources TEXT,
            citations TEXT,
            word_count INTEGER,
            mode TEXT DEFAULT 'research',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


init_db()


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
        return []

    try:
        res = client.search(query=query, max_results=max_results)
        return res.get("results", [])
    except Exception:
        return []


def _format_web(results):
    return "\n\n".join([
        f"[{i+1}] {r.get('title','')}\n{r.get('content','')}\nSource: {r.get('url','')}"
        for i, r in enumerate(results)
    ]) if results else ""


# ─────────────────────────────────────────────
# GROQ
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
        except Exception:
            time.sleep(1.5 * (attempt + 1))

    raise RuntimeError("Groq API failed")


# ─────────────────────────────────────────────
# PROMPTS
# ─────────────────────────────────────────────

SYSTEM_PROMPT = "You are a precise AI research analyst."

REFINER_PROMPT = "Improve clarity, depth, and accuracy. Return only final version."


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _new_session_id(query: str):
    return hashlib.md5(f"{query}{datetime.utcnow()}".encode()).hexdigest()[:12]


def _extract_citations(text: str):
    return re.findall(r"\[Source:\s*(.*?)\]", text)


def _save_session(session_id, title, query, result, sources, citations, word_count, mode):
    conn = sqlite3.connect(config.DB_PATH)

    conn.execute("""
        INSERT OR REPLACE INTO research_sessions (
            session_id, title, query, result,
            sources, citations, word_count, mode, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
    """, (
        session_id,
        title,
        query,
        result,
        json.dumps(sources),
        json.dumps(citations),
        word_count,
        mode
    ))

    conn.commit()
    conn.close()


# ─────────────────────────────────────────────
# CORE RESEARCH ENGINE
# ─────────────────────────────────────────────

def deep_research(query: str, n_sources: int = 5):

    session_id = _new_session_id(query)

    web_results = _web_search(query, n_sources)
    web_context = _format_web(web_results)

    prompt = f"""
Topic: {query}

Sources:
{web_context}

Use ONLY sources above.
"""

    draft = _call_groq([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt}
    ])

    refined = _call_groq([
        {"role": "system", "content": REFINER_PROMPT},
        {"role": "user", "content": draft}
    ], temperature=0.2)

    sources = [r.get("url") for r in web_results if r.get("url")]
    citations = _extract_citations(refined)

    _save_session(
        session_id,
        query[:60],
        query,
        refined,
        sources,
        citations,
        len(refined.split()),
        "research"
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

    draft = _call_groq([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"{text[:8000]}\n\nQuestion: {query}"}
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
        len(refined.split()),
        "document"
    )

    return {
        "session_id": session_id,
        "result": refined,
        "status": "complete"
    }


# ─────────────────────────────────────────────
# FIX 1: ESSAY (API COMPATIBILITY)
# ─────────────────────────────────────────────

def write_essay(query: str):
    result = deep_research(query)

    return {
        "title": result["title"],
        "essay": result["result"],
        "sources": result["sources"],
        "mode": "essay"
    }


# ─────────────────────────────────────────────
# FIX 2: PRESENTATION (API COMPATIBILITY)
# ─────────────────────────────────────────────

def generate_presentation(query: str):
    result = deep_research(query)

    return {
        "title": result["title"],
        "mode": "presentation",
        "slides": [
            {"title": "Introduction", "content": query},
            {"title": "Key Insights", "content": result["result"][:1200]},
            {"title": "Sources", "content": "\n".join(result["sources"])}
        ]
    }


# ─────────────────────────────────────────────
# FIX 3: SAFE SESSION READ (NO CRASH)
# ─────────────────────────────────────────────

def get_sessions(limit: int = 15):
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row

    try:
        rows = conn.execute("""
            SELECT session_id, title, query, result, word_count, mode, created_at
            FROM research_sessions
            ORDER BY created_at DESC
            LIMIT ?
        """, (limit,)).fetchall()

        return [dict(r) for r in rows]

    except Exception:
        return []

    finally:
        conn.close()