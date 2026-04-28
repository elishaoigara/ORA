from __future__ import annotations

import os
import json
import hashlib
import sqlite3
from datetime import datetime

from groq import Groq

try:
    from tavily import TavilyClient
except Exception:
    TavilyClient = None

import config


# ─────────────────────────────────────────────
# DB INIT
# ─────────────────────────────────────────────

def init_db():
    conn = sqlite3.connect(config.DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS research_sessions (
            id TEXT PRIMARY KEY,
            type TEXT,
            title TEXT,
            query TEXT,
            content TEXT,
            sources TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


init_db()


# ─────────────────────────────────────────────
# CLIENTS
# ─────────────────────────────────────────────

def groq_client():
    return Groq(api_key=os.getenv("GROQ_API_KEY"))


def tavily_client():
    if not TavilyClient:
        return None
    key = os.getenv("TAVILY_API_KEY")
    return TavilyClient(api_key=key) if key else None


# ─────────────────────────────────────────────
# WEB SEARCH
# ─────────────────────────────────────────────

def web_search(query: str, n=5):
    client = tavily_client()
    if not client:
        return []

    try:
        res = client.search(query=query, max_results=n)
        return res.get("results", [])
    except Exception:
        return []


def extract_sources(results):
    return [r.get("url") for r in results if r.get("url")]


def format_context(results):
    return "\n\n".join(
        f"{r.get('title','')}\n{r.get('content','')}"
        for r in results
    )


# ─────────────────────────────────────────────
# LLM
# ─────────────────────────────────────────────

def call_llm(messages):
    client = groq_client()

    res = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages,
        temperature=0.3,
        max_tokens=2000
    )

    return (res.choices[0].message.content or "").strip()


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def make_id(text: str):
    return hashlib.md5(text.encode()).hexdigest()[:12]


def save_db(id, type_, title, query, content, sources):
    conn = sqlite3.connect(config.DB_PATH)

    conn.execute("""
        INSERT OR REPLACE INTO research_sessions
        (id, type, title, query, content, sources, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        id,
        type_,
        title,
        query,
        content,
        json.dumps(sources),
        datetime.utcnow().isoformat()
    ))

    conn.commit()
    conn.close()


# ─────────────────────────────────────────────
# CORE RESEARCH (FIXED)
# ─────────────────────────────────────────────

def deep_research(query: str, n_sources: int = 5):

    sid = make_id(query)

    web = web_search(query, n_sources)
    context = format_context(web)
    sources = extract_sources(web)

    result = call_llm([
        {"role": "system", "content": "You are a senior research analyst."},
        {"role": "user", "content": f"Topic: {query}\n\nSources:\n{context}"}
    ])

    save_db(sid, "research", query[:60], query, result, sources)

    return {
        "id": sid,
        "type": "research",
        "title": query,
        "content": result,
        "sources": sources
    }


# ─────────────────────────────────────────────
# ESSAY (FIXED)
# ─────────────────────────────────────────────

def write_essay(query: str):

    data = deep_research(query)

    return {
        "id": data["id"],
        "type": "essay",
        "title": data["title"],
        "content": data["content"],
        "sources": data["sources"],
        "status": "complete"
    }


# ─────────────────────────────────────────────
# DOCUMENT (FIXED)
# ─────────────────────────────────────────────

def analyze_document(query: str, text: str, filename: str):

    sid = make_id(filename)

    result = call_llm([
        {"role": "system", "content": "You analyze documents clearly and concisely."},
        {"role": "user", "content": text[:8000] + "\n\nQuestion: " + query}
    ])

    save_db(sid, "document", filename, query, result, [])

    return {
        "id": sid,
        "type": "document",
        "title": filename,
        "content": result,
        "sources": [],
        "status": "complete"
    }


# ─────────────────────────────────────────────
# PRESENTATION (FIXED — IMPORTANT)
# ─────────────────────────────────────────────

def generate_presentation(query: str, slides: int = 5):

    data = deep_research(query)

    content = data["content"]

    chunks = [
        content[i:i+600]
        for i in range(0, len(content), 600)
    ]

    slides_out = [
        {"title": "Introduction", "content": query}
    ]

    for i, chunk in enumerate(chunks[:max(1, slides-2)]):
        slides_out.append({
            "title": f"Slide {i+1}",
            "content": chunk
        })

    slides_out.append({
        "title": "Sources",
        "content": "\n".join(data["sources"])
    })

    return {
        "id": data["id"],
        "type": "presentation",
        "title": data["title"],
        "slides": slides_out,
        "content": content,   # 🔥 IMPORTANT: backend compatibility fix
        "sources": data["sources"],
        "status": "complete"
    }


# ─────────────────────────────────────────────
# SESSIONS
# ─────────────────────────────────────────────

def get_sessions(limit=15):

    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row

    rows = conn.execute("""
        SELECT * FROM research_sessions
        ORDER BY created_at DESC
        LIMIT ?
    """, (limit,)).fetchall()

    conn.close()

    return [dict(r) for r in rows]