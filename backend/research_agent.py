from __future__ import annotations

import os
import json
import time
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
# DB
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
            mode TEXT,
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
# WEB
# ─────────────────────────────────────────────

def web_search(query: str, n=5):
    client = tavily_client()
    if not client:
        return []

    try:
        return client.search(query=query, max_results=n).get("results", [])
    except Exception:
        return []


def format_sources(results):
    return [r.get("url") for r in results if r.get("url")]


# ─────────────────────────────────────────────
# AI CALL
# ─────────────────────────────────────────────

def call_llm(messages):
    client = groq_client()

    res = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages,
        temperature=0.3,
        max_tokens=2000
    )

    content = res.choices[0].message.content or ""
    return content.strip()


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def session_id(text):
    return hashlib.md5(text.encode()).hexdigest()[:12]


def save(session, title, query, result, sources, mode):
    conn = sqlite3.connect(config.DB_PATH)

    conn.execute("""
        INSERT OR REPLACE INTO research_sessions
        (session_id, title, query, result, sources, mode)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        session,
        title,
        query,
        result,
        json.dumps(sources),
        mode
    ))

    conn.commit()
    conn.close()


# ─────────────────────────────────────────────
# CORE ENGINE
# ─────────────────────────────────────────────

def deep_research(query: str):

    sid = session_id(query)

    web = web_search(query)
    context = "\n".join(
        f"{r.get('title','')}: {r.get('content','')}"
        for r in web
    )

    result = call_llm([
        {"role": "system", "content": "You are a research assistant."},
        {"role": "user", "content": f"Topic: {query}\n\nSources:\n{context}"}
    ])

    sources = format_sources(web)

    save(sid, query[:60], query, result, sources, "research")

    return {
        "id": sid,
        "type": "research",
        "title": query,
        "content": result,
        "sources": sources,
        "meta": {
            "word_count": len(result.split()),
            "created_at": str(datetime.utcnow())
        },
        "status": "complete"
    }


# ─────────────────────────────────────────────
# ESSAY
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
# DOCUMENT
# ─────────────────────────────────────────────

def analyze_document(query: str, text: str, filename: str):

    sid = session_id(filename)

    result = call_llm([
        {"role": "system", "content": "You analyze documents clearly."},
        {"role": "user", "content": text[:8000] + "\n\nQuestion: " + query}
    ])

    return {
        "id": sid,
        "type": "document",
        "title": filename,
        "content": result,
        "sources": [],
        "status": "complete"
    }


# ─────────────────────────────────────────────
# PRESENTATION (FIXED OUTPUT)
# ─────────────────────────────────────────────

def generate_presentation(query: str, slides: int = 5):

    data = deep_research(query)

    chunks = [
        data["content"][i:i+600]
        for i in range(0, len(data["content"]), 600)
    ]

    slides_out = [
        {"title": "Intro", "content": query}
    ]

    for i, chunk in enumerate(chunks[:slides-2]):
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
        "status": "complete"
    }


# ─────────────────────────────────────────────
# SESSION FETCH
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