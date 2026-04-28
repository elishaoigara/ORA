"""
ORA Research Agent — PRODUCTION SAFE CORE (FINAL HARDENED VERSION)
==================================================================
Fixes:
- Render stability issues
- Groq timeout safety
- Safe DB handling
- Web search null safety
- Production cost control hooks ready
"""

from __future__ import annotations

import os
import json
import time
import hashlib
import sqlite3
import re
from datetime import datetime
from typing import Optional

from groq import Groq

try:
    from tavily import TavilyClient
except Exception:
    TavilyClient = None

import config


# ─────────────────────────────────────────────
# DB INIT (SAFE)
# ─────────────────────────────────────────────

def init_db():
    conn = sqlite3.connect(config.DB_PATH, timeout=10)
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
# WEB SEARCH (SAFE)
# ─────────────────────────────────────────────

def _web_search(query: str, max_results: int = 5):
    client = _tavily_client()

    if not client:
        return []

    try:
        res = client.search(query=query, max_results=max_results)
        return res.get("results") or []
    except Exception:
        return []


def _format_web(results):
    if not results:
        return ""

    return "\n\n".join(
        f"[{i+1}] {r.get('title','')}\n{r.get('content','')}\nSource: {r.get('url','')}"
        for i, r in enumerate(results)
    )


# ─────────────────────────────────────────────
# GROQ CALL (PROTECTED)
# ─────────────────────────────────────────────

def _call_groq(messages, model="llama-3.3-70b-versatile",
               max_tokens=1800, temperature=0.3):

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
            wait = 1.5 * (attempt + 1)
            time.sleep(wait)

    return "Error: AI service unavailable."


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _new_session_id(query: str):
    return hashlib.md5(
        f"{query}{datetime.utcnow()}".encode()
    ).hexdigest()[:12]


def _extract_citations(text: str):
    return re.findall(r"\[Source:\s*(.*?)\]", text)


def _safe_db():
    return sqlite3.connect(config.DB_PATH, timeout=10)


def _save_session(session_id, title, query, result,
                  sources, citations, word_count, mode):

    try:
        conn = _safe_db()
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

    except Exception:
        pass


# ─────────────────────────────────────────────
# CORE RESEARCH ENGINE (COST OPTIMIZED)
# ─────────────────────────────────────────────

def deep_research(query: str, n_sources: int = 5):

    session_id = _new_session_id(query)

    web_results = _web_search(query, n_sources)
    web_context = _format_web(web_results)

    prompt = f"""
Topic: {query}

Sources:
{web_context}

Rules:
- Be concise
- Use only sources
"""

    result = _call_groq([
        {"role": "system", "content": "You are a precise research AI."},
        {"role": "user", "content": prompt}
    ])

    sources = [r.get("url") for r in web_results if r.get("url")]
    citations = _extract_citations(result)

    _save_session(
        session_id,
        query[:60],
        query,
        result,
        sources,
        citations,
        len(result.split()),
        "research"
    )

    return {
        "session_id": session_id,
        "title": query[:60],
        "result": result[:2500],  # HARD COST LIMIT
        "sources": sources,
        "word_count": len(result.split()),
        "status": "complete"
    }


# ─────────────────────────────────────────────
# DOCUMENT ANALYSIS
# ─────────────────────────────────────────────

def analyze_document(query: str, filename: str, text: str):

    session_id = _new_session_id(filename)

    result = _call_groq([
        {"role": "system", "content": "You are a document analyst."},
        {"role": "user", "content": f"{text[:8000]}\n\nQuestion: {query}"}
    ])

    _save_session(
        session_id,
        f"Analysis: {filename}",
        query,
        result,
        [filename],
        [],
        len(result.split()),
        "document"
    )

    return {
        "session_id": session_id,
        "result": result[:2500],
        "status": "complete"
    }


# ─────────────────────────────────────────────
# ESSAY (SAFE)
# ─────────────────────────────────────────────

def write_essay(query: str, **kwargs):

    result = deep_research(query)

    return {
        "title": result["title"],
        "essay": result["result"],
        "sources": result["sources"],
        "mode": "essay"
    }


# ─────────────────────────────────────────────
# PRESENTATION (SAFE + FAST)
# ─────────────────────────────────────────────

def generate_presentation(query: str, slides: int = 5):

    result = deep_research(query, n_sources=slides)

    slides = max(3, min(slides, 6))  # cost control

    chunks = [
        result["result"][i:i + 500]
        for i in range(0, min(len(result["result"]), 2000), 500)
    ]

    output = [{"title": "Introduction", "content": query}]

    for i in range(min(slides - 2, len(chunks))):
        output.append({
            "title": f"Insight {i+1}",
            "content": chunks[i]
        })

    output.append({
        "title": "Sources",
        "content": "\n".join(result["sources"])
    })

    return {
        "title": result["title"],
        "mode": "presentation",
        "slides": output
    }


# ─────────────────────────────────────────────
# DOCUMENT COMPATIBILITY
# ─────────────────────────────────────────────

def summarize_document(query: str, filename: str = "", text: str = ""):
    return analyze_document(query, filename, text)


# ─────────────────────────────────────────────
# SESSION API
# ─────────────────────────────────────────────

def get_sessions(limit: int = 15):

    try:
        conn = _safe_db()
        conn.row_factory = sqlite3.Row

        rows = conn.execute("""
            SELECT session_id, title, query, result, word_count, mode, created_at
            FROM research_sessions
            ORDER BY created_at DESC
            LIMIT ?
        """, (limit,)).fetchall()

        conn.close()

        return [dict(r) for r in rows]

    except Exception:
        return []