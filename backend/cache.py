"""
ORA Cache — Simple in-memory response cache.
Avoids repeat Groq API calls for identical queries.
Render-safe: lives in process memory, resets on redeploy (that's fine).
"""

import time
import hashlib

_cache: dict = {}
_TTL = 300  # 5 minutes — short enough to stay fresh, long enough to save calls


def _key(query: str, context: str = "") -> str:
    raw = f"{query.strip().lower()}::{context[:100]}"
    return hashlib.md5(raw.encode()).hexdigest()


def get(query: str, context: str = "") -> str | None:
    k = _key(query, context)
    entry = _cache.get(k)
    if not entry:
        return None
    if time.time() - entry["ts"] > _TTL:
        del _cache[k]
        return None
    return entry["value"]


def set(query: str, value: str, context: str = "") -> None:
    # Cap cache size to avoid memory growth on Render free tier
    if len(_cache) > 200:
        # Drop oldest 50 entries
        oldest = sorted(_cache.items(), key=lambda x: x[1]["ts"])[:50]
        for k, _ in oldest:
            del _cache[k]
    k = _key(query, context)
    _cache[k] = {"value": value, "ts": time.time()}


def clear() -> None:
    _cache.clear()


def stats() -> dict:
    return {"entries": len(_cache), "ttl_seconds": _TTL}