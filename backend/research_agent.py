"""
ORA Research Agent — Clean, Frontend-Compatible, Pylance-safe
"""

from __future__ import annotations

import os
import json
import hashlib
import sqlite3
from datetime import datetime
from typing import Dict, Any, Optional

try:
    from tavily import TavilyClient
except ImportError:
    TavilyClient = None

from groq import Groq
import config


# ─────────────────────────────────────────────
# DB INIT
# ─────────────────────────────────────────────

def init_research_tables():
    """Initialize research sessions table"""
    conn: Optional[sqlite3.Connection] = None
    try:
        conn = sqlite3.connect(config.DB_PATH)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS research_sessions (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                title TEXT,
                query TEXT,
                content TEXT,
                sources TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
    finally:
        if conn:
            conn.close()


init_research_tables()


# ─────────────────────────────────────────────
# CLIENTS
# ─────────────────────────────────────────────

def groq_client() -> Groq:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY environment variable is not set")
    return Groq(api_key=api_key)


def tavily_client():
    if not TavilyClient:
        return None
    key = os.getenv("TAVILY_API_KEY")
    return TavilyClient(api_key=key) if key else None


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def make_id(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()[:12]


def save_session(session_id: str, session_type: str, title: str, query: str, content: str, sources: list):
    """Save research session to database"""
    conn: Optional[sqlite3.Connection] = None
    try:
        conn = sqlite3.connect(config.DB_PATH)
        conn.execute("""
            INSERT OR REPLACE INTO research_sessions 
            (id, type, title, query, content, sources, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            session_id,
            session_type,
            title[:200],
            query,
            content,
            json.dumps(sources),
            datetime.utcnow().isoformat()
        ))
        conn.commit()
    except Exception as e:
        print(f"[RESEARCH] Failed to save session: {e}")
    finally:
        if conn:
            conn.close()


# ─────────────────────────────────────────────
# WEB SEARCH
# ─────────────────────────────────────────────

def web_search(query: str, n_sources: int = 8):
    client = tavily_client()
    if not client:
        return []
    try:
        res = client.search(query=query, max_results=n_sources)
        return res.get("results", [])
    except Exception as e:
        print(f"[Tavily Error] {e}")
        return []


# ─────────────────────────────────────────────
# LLM CALL
# ─────────────────────────────────────────────

def call_llm(messages: list, max_tokens: int = 2000) -> str:
    try:
        client = groq_client()
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            temperature=0.35,
            max_tokens=max_tokens,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        print(f"[Groq Error] {e}")
        return "Failed to generate response due to API error."


# ─────────────────────────────────────────────
# CORE FUNCTIONS
# ─────────────────────────────────────────────

def deep_research(query: str, n_sources: int = 8) -> Dict[str, Any]:
    """Deep Research"""
    session_id = make_id(query)

    results = web_search(query, n_sources)
    context = "\n\n".join(
        f"Title: {r.get('title','')}\nURL: {r.get('url','')}\nContent: {r.get('content','')[:700]}"
        for r in results
    ) if results else ""

    sources = [r.get("url") for r in results if r.get("url")]

    response_text = call_llm([
        {"role": "system", "content": "You are a senior research analyst. Be insightful and well-structured."},
        {"role": "user", "content": f"Topic: {query}\n\nSources:\n{context}"}
    ])

    save_session(session_id, "research", query[:100], query, response_text, sources)

    return {
        "title": query,
        "result": response_text,
        "content": response_text,
        "sources": sources
    }


def write_essay(topic: str) -> Dict[str, Any]:
    """Write Essay"""
    research = deep_research(topic, n_sources=8)

    essay = call_llm([
        {"role": "system", "content": "Write a clear, coherent, and well-structured essay."},
        {"role": "user", "content": f"Write an essay on: {topic}\n\nUse this research:\n{research['content']}"}
    ])

    save_session(make_id(topic), "essay", f"Essay: {topic[:60]}", topic, essay, research.get("sources", []))

    return {
        "title": f"Essay: {topic}",
        "result": essay,
        "content": essay,
        "sources": research.get("sources", [])
    }


def analyze_document(query: str, filename: str, text: str):
    """Document Analysis - returns shape expected by frontend"""
    session_id = make_id(filename)

    analysis = call_llm([
        {"role": "system", "content": "You are an expert document analyst."},
        {"role": "user", "content": f"Document: {filename}\n\nContent:\n{text[:10000]}\n\nRequest: {query or 'Provide a detailed analysis.'}"}
    ])

    save_session(session_id, "document", filename, query or "Analysis", analysis, [])

    return {
        "analysis": {
            "title": f"Analysis: {filename}",
            "result": analysis,
            "content": analysis,
            "filename": filename
        }
    }


def generate_presentation(topic: str, slides: int = 8) -> Dict[str, Any]:
    """Generate Presentation"""
    research = deep_research(topic, n_sources=7)

    pptx_data = {
        "slides": [
            {"type": "title", "title": topic, "points": []}
        ]
    }

    content = research.get("content", "")
    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]

    for i, para in enumerate(paragraphs[:max(1, slides - 2)]):
        points = [s.strip() for s in para.split(". ") if s.strip()]
        pptx_data["slides"].append({
            "type": "bullets",
            "title": f"Key Insight {i+1}",
            "points": points[:6]
        })

    pptx_data["slides"].append({
        "type": "conclusion",
        "title": "Sources",
        "points": research.get("sources", [])[:6]
    })

    save_session(make_id(topic), "presentation", f"Presentation: {topic[:50]}", topic, content, research.get("sources", []))

    return {
        "title": f"Presentation: {topic}",
        "pptx_data": pptx_data,
        "slides": pptx_data["slides"],
        "content": content,
        "sources": research.get("sources", [])
    }


# ─────────────────────────────────────────────
# SESSION MANAGEMENT
# ─────────────────────────────────────────────

def get_sessions(limit: int = 15):
    """Get recent sessions"""
    conn: Optional[sqlite3.Connection] = None
    try:
        conn = sqlite3.connect(config.DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT id, type, title, query, content, sources, created_at 
            FROM research_sessions 
            ORDER BY created_at DESC 
            LIMIT ?
        """, (limit,)).fetchall()
        return [dict(row) for row in rows]
    except Exception as e:
        print(f"[RESEARCH] get_sessions error: {e}")
        return []
    finally:
        if conn:
            conn.close()


def get_session(session_id: str):
    """Get single session by ID"""
    conn: Optional[sqlite3.Connection] = None
    try:
        conn = sqlite3.connect(config.DB_PATH)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM research_sessions WHERE id = ?", (session_id,)).fetchone()
        return dict(row) if row else None
    finally:
        if conn:
            conn.close()