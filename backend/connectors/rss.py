"""
ORA RSS Connector — Phase 4
Polls feeds every 2 hours. Ingests new articles into knowledge base.
Free, no API key, pure HTTP.
"""

from __future__ import annotations

import traceback

# ── Feeds ──────────────────────────────────────────────────────
FEEDS = [
    "https://feeds.arstechnica.com/arstechnica/technology-lab",
    "https://www.wired.com/feed/rss",
    "https://www.deeplearning.ai/feed/",
    "https://techcrunch.com/tag/africa/feed/",
    "https://businessdailyafrica.com/feed",
    "https://feeds.bbci.co.uk/news/world/rss.xml",
]

MAX_ARTICLES_PER_FEED = 5
MAX_BODY_CHARS = 3000


# ── SAFE INGESTION (FIX FOR PYLANCE) ──────────────────────────
def _ingest(text: str, source: str, tags: str) -> None:
    """
    Safe ingestion bridge.
    No direct symbol import → avoids Pylance errors.
    """
    try:
        import knowledge.pipeline as kp  # import module, not symbol

        ingest_fn = getattr(kp, "ingest_text", None)

        if callable(ingest_fn):
            ingest_fn(
                text=text,
                source=source,
                tags=tags
            )
        else:
            print("[RSS] ingest_text not found in knowledge.pipeline")

    except Exception as e:
        print(f"[RSS] ingestion error: {e}")


# ── Seen tracking ─────────────────────────────────────────────
def _get_seen_urls() -> set:
    try:
        from config import DB_PATH
        import sqlite3

        con = sqlite3.connect(DB_PATH)
        con.execute("""
            CREATE TABLE IF NOT EXISTS rss_seen (
                url TEXT PRIMARY KEY,
                seen_at TEXT DEFAULT (datetime('now'))
            )
        """)

        rows = con.execute("SELECT url FROM rss_seen").fetchall()
        con.close()

        return {r[0] for r in rows}
    except Exception:
        return set()


def _mark_seen(urls: list[str]) -> None:
    try:
        from config import DB_PATH
        import sqlite3

        con = sqlite3.connect(DB_PATH)
        con.executemany(
            "INSERT OR IGNORE INTO rss_seen (url) VALUES (?)",
            [(u,) for u in urls]
        )

        con.execute("""
            DELETE FROM rss_seen
            WHERE seen_at < datetime('now', '-7 days')
        """)

        con.commit()
        con.close()
    except Exception:
        pass


# ── MAIN SYNC ─────────────────────────────────────────────────
def sync_rss() -> None:
    try:
        import feedparser

        seen = _get_seen_urls()
        new_urls: list[str] = []
        ingested = 0

        for feed_url in FEEDS:
            try:
                feed = feedparser.parse(feed_url)

                for entry in feed.entries[:MAX_ARTICLES_PER_FEED]:
                    url = entry.get("link", "")
                    title = entry.get("title", "")
                    summary = entry.get("summary", "") or entry.get("description", "")

                    if not url or url in seen:
                        continue

                    text = f"Title: {title}\nSource: {url}\n\n{summary[:MAX_BODY_CHARS]}"

                    if len(text.strip()) < 80:
                        continue

                    _ingest(
                        text=text,
                        source=f"RSS: {title[:80]}",
                        tags=f"rss:{feed.feed.get('title', 'feed')[:40]}",
                    )

                    new_urls.append(url)
                    ingested += 1

            except Exception as e:
                print(f"[RSS] Feed failed {feed_url}: {e}")

        _mark_seen(new_urls)

        print(f"[RSS] Sync complete — {ingested} articles ingested")

    except Exception:
        print("[RSS] sync_rss failed:")
        print(traceback.format_exc())


# ── HEADLINES ONLY API ────────────────────────────────────────
def get_latest_headlines(limit: int = 10) -> list[dict]:
    try:
        import feedparser

        results = []

        for feed_url in FEEDS[:3]:
            try:
                feed = feedparser.parse(feed_url)
                source = feed.feed.get("title", "unknown")

                for entry in feed.entries[:3]:
                    results.append({
                        "title": entry.get("title", ""),
                        "url": entry.get("link", ""),
                        "source": source,
                        "summary": entry.get("summary", "")[:200],
                    })

            except Exception:
                continue

        return results[:limit]

    except Exception:
        return []