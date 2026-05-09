"""ORA News Agent — API routes"""
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


@router.get("/api/news/headlines")
def news_headlines(limit: int = 20, category: str | None = None):
    from agents.news_agent import get_headlines
    return get_headlines(limit=limit, category=category)


@router.post("/api/news/ingest")
def news_ingest():
    """Pull fresh articles from RSS feeds into the news DB."""
    from agents.news_agent import ingest_latest_news
    return ingest_latest_news()


@router.get("/api/news/digest")
def news_digest_get():
    """Return the most recent AI digest."""
    from agents.news_agent import get_latest_digest
    result = get_latest_digest()
    if not result:
        raise HTTPException(404, "No digest yet. POST /api/news/digest to generate one.")
    return result


@router.post("/api/news/digest")
def news_digest_generate(topic: str = "daily"):
    """Generate (and store) a fresh AI news digest."""
    from agents.news_agent import ingest_latest_news, generate_digest
    ingest_latest_news()
    result = generate_digest(topic=topic)
    if "error" in result:
        raise HTTPException(500, result["error"])
    return result