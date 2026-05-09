"""
ORA News Agent
Fetches, categorises, and summarises news from RSS + optional NewsAPI.
Stores digests in SQLite. Exposes digest, headlines, and search.
"""
from __future__ import annotations
import json, sqlite3, hashlib
from datetime import datetime
from typing import Optional

from config import DB_PATH, GROQ_API_KEY, GROQ_MODEL_PRIMARY, GROQ_MODEL_FALLBACK
from groq import Groq

_client: Optional[Groq] = None
def _groq() -> Groq:
    global _client
    if _client is None:
        _client = Groq(api_key=GROQ_API_KEY)
    return _client


# ── DB init ────────────────────────────────────────────────────

def init_news_tables() -> None:
    con = sqlite3.connect(DB_PATH)
    con.executescript("""
        CREATE TABLE IF NOT EXISTS news_articles (
            id          TEXT PRIMARY KEY,
            title       TEXT NOT NULL,
            url         TEXT UNIQUE NOT NULL,
            source      TEXT,
            summary     TEXT,
            category    TEXT DEFAULT 'general',
            sentiment   TEXT DEFAULT 'neutral',
            published   TEXT,
            ingested_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS news_digests (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            topic       TEXT DEFAULT 'daily',
            digest_text TEXT NOT NULL,
            article_ids TEXT DEFAULT '[]',
            created_at  TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_news_category ON news_articles(category, ingested_at DESC);
    """)
    con.commit(); con.close()
    print("[NEWS_AGENT] Tables ready")


# ── Ingest from RSS connector ──────────────────────────────────

def ingest_latest_news(limit: int = 30) -> dict:
    """Pull fresh headlines from RSS connector and store them."""
    from connectors.rss import get_latest_headlines
    items = get_latest_headlines(limit=limit)
    stored = 0
    con = sqlite3.connect(DB_PATH)
    for item in items:
        article_id = hashlib.md5(item["url"].encode()).hexdigest()[:12]
        try:
            con.execute(
                """INSERT OR IGNORE INTO news_articles
                   (id, title, url, source, summary, ingested_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (article_id, item["title"], item["url"],
                 item.get("source", ""), item.get("summary", ""),
                 datetime.now().isoformat())
            )
            stored += 1
        except Exception:
            pass
    con.commit(); con.close()
    return {"ingested": stored, "total": len(items)}


# ── AI digest ─────────────────────────────────────────────────

def generate_digest(topic: str = "daily", max_articles: int = 20) -> dict:
    """
    Pull recent articles, send to Groq, return a structured digest.
    Saves result to news_digests table.
    """
    con = sqlite3.connect(DB_PATH)
    rows = con.execute(
        """SELECT title, source, summary FROM news_articles
           ORDER BY ingested_at DESC LIMIT ?""",
        (max_articles,)
    ).fetchall()
    con.close()

    if not rows:
        return {"error": "No articles available. Run ingest first."}

    headlines_text = "\n".join(
        f"- [{r[1]}] {r[0]}: {r[2][:150]}" for r in rows
    )

    prompt = f"""You are a world-class news analyst. Given these headlines, produce a structured news digest.

Headlines:
{headlines_text}

Return a JSON object with:
- "headline": one punchy overall summary sentence
- "sections": array of objects, each with "category" (Tech/Business/World/Africa/Science), "summary" (2-3 sentences), "key_stories": [list of 2-3 headline strings]
- "sentiment": "positive" | "negative" | "mixed"
- "top_story": the single most important story title

Respond with ONLY the JSON, no markdown fences."""

    try:
        resp = _groq().chat.completions.create(
            model=GROQ_MODEL_PRIMARY,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1000,
            temperature=0.3,
        )
        raw = resp.choices[0].message.content or "{}"
        parsed = json.loads(raw)
    except Exception:
        # fallback to simpler model
        try:
            resp = _groq().chat.completions.create(
                model=GROQ_MODEL_FALLBACK,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=800,
            )
            parsed = json.loads(resp.choices[0].message.content or "{}")
        except Exception as e:
            return {"error": str(e)}

    # persist digest
    con = sqlite3.connect(DB_PATH)
    con.execute(
        "INSERT INTO news_digests (topic, digest_text, created_at) VALUES (?, ?, ?)",
        (topic, json.dumps(parsed), datetime.now().isoformat())
    )
    con.commit(); con.close()

    return parsed


# ── Queries ───────────────────────────────────────────────────

def get_headlines(limit: int = 20, category: Optional[str] = None) -> list[dict]:
    con = sqlite3.connect(DB_PATH)
    if category:
        rows = con.execute(
            "SELECT id,title,url,source,summary,category,ingested_at FROM news_articles WHERE category=? ORDER BY ingested_at DESC LIMIT ?",
            (category, limit)
        ).fetchall()
    else:
        rows = con.execute(
            "SELECT id,title,url,source,summary,category,ingested_at FROM news_articles ORDER BY ingested_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
    con.close()
    return [
        {"id": r[0], "title": r[1], "url": r[2], "source": r[3],
         "summary": r[4], "category": r[5], "ingested_at": r[6]}
        for r in rows
    ]


def get_latest_digest() -> Optional[dict]:
    con = sqlite3.connect(DB_PATH)
    row = con.execute(
        "SELECT digest_text, created_at FROM news_digests ORDER BY id DESC LIMIT 1"
    ).fetchone()
    con.close()
    if not row:
        return None
    try:
        return {**json.loads(row[0]), "created_at": row[1]}
    except Exception:
        return {"raw": row[0], "created_at": row[1]}