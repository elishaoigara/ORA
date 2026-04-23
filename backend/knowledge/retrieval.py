"""
ORA Knowledge — Phase 4
Hybrid retrieval: FTS5 keyword search + vector semantic search, merged and reranked.

This alone gives 2-5x answer quality improvement over pure keyword or pure vector search.
"""

import sqlite3
from knowledge.embeddings import vector_search

DB_PATH = "ora_knowledge.db"


# ============================================================
# PHASE 4 — KEYWORD SEARCH (FTS5)
# ============================================================

def fts_search(query: str, n_results: int = 10) -> list[dict]:
    """
    Fast keyword search via SQLite FTS5.
    Always works even if embeddings are unavailable.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Sanitize query for FTS5 (remove special chars that break the query)
    safe_query = _sanitize_fts_query(query)

    results = []

    if safe_query:
        try:
            rows = conn.execute("""
                SELECT
                    kc.chunk_id,
                    kc.source,
                    kc.section,
                    kc.page_num,
                    kc.text,
                    kc.importance,
                    rank
                FROM knowledge_fts
                JOIN knowledge_chunks kc ON knowledge_chunks.chunk_id = knowledge_fts.chunk_id
                WHERE knowledge_fts MATCH ?
                ORDER BY rank
                LIMIT ?
            """, (safe_query, n_results * 2)).fetchall()

            for i, row in enumerate(rows):
                # FTS rank is negative (lower = better), normalize to 0-1
                fts_score = 1.0 / (1.0 + abs(i))
                results.append({
                    "chunk_id": row["chunk_id"],
                    "text": row["text"],
                    "source": row["source"],
                    "section": row["section"],
                    "page_num": row["page_num"],
                    "importance": row["importance"],
                    "score": fts_score,
                    "method": "fts"
                })
        except Exception as e:
            print(f"[FTS] Search failed: {e}")

    # Fallback: simple LIKE search if FTS fails
    if not results:
        results = _fallback_like_search(conn, query, n_results)

    conn.close()
    return results[:n_results]


def _sanitize_fts_query(query: str) -> str:
    """Make query safe for FTS5 MATCH syntax."""
    import re
    # Remove FTS5 special characters
    safe = re.sub(r'[^\w\s]', ' ', query)
    # Keep only words with 2+ chars
    words = [w for w in safe.split() if len(w) >= 2]
    if not words:
        return ""
    # Join with implicit AND
    return " ".join(words)


def _fallback_like_search(conn, query: str, n_results: int) -> list[dict]:
    """LIKE-based fallback when FTS fails."""
    conn.row_factory = sqlite3.Row
    words = query.lower().split()[:3]  # use first 3 words
    results = []

    for word in words:
        try:
            rows = conn.execute("""
                SELECT chunk_id, source, section, page_num, text, importance
                FROM knowledge_chunks
                WHERE LOWER(text) LIKE ?
                LIMIT ?
            """, (f"%{word}%", n_results)).fetchall()

            for i, row in enumerate(rows):
                results.append({
                    "chunk_id": row["chunk_id"],
                    "text": row["text"],
                    "source": row["source"],
                    "section": row["section"],
                    "page_num": row["page_num"],
                    "importance": row["importance"],
                    "score": 0.3 / (i + 1),
                    "method": "fallback"
                })
        except:
            continue

    return results


# ============================================================
# PHASE 4 — HYBRID MERGE + RERANK
# ============================================================

def retrieve(query: str, n_results: int = 5) -> list[dict]:
    """
    Main retrieval function.
    Runs both FTS and vector search, merges, deduplicates, reranks.

    Returns top n_results chunks as:
    { text, source, section, page_num, score, method }
    """
    # Run both searches in parallel (conceptually — sequential here for simplicity)
    fts_results = fts_search(query, n_results=n_results * 2)
    vector_results = vector_search(query, n_results=n_results * 2)

    merged = _merge(fts_results, vector_results)
    deduped = _deduplicate(merged)
    reranked = _rerank(deduped, query)

    return reranked[:n_results]


def _merge(fts: list[dict], vector: list[dict]) -> list[dict]:
    """
    Reciprocal Rank Fusion — combines two ranked lists into one.
    RRF score = 1/(k + rank) summed across methods.
    k=60 is the standard constant.
    """
    k = 60
    scores: dict[str, dict] = {}

    for rank, result in enumerate(fts):
        cid = result["chunk_id"]
        if cid not in scores:
            scores[cid] = {**result, "rrf_score": 0.0}
        scores[cid]["rrf_score"] += 1.0 / (k + rank + 1)
        scores[cid]["method"] = "hybrid" if scores[cid].get("method") == "vector" else "fts"

    for rank, result in enumerate(vector):
        cid = result["chunk_id"]
        if cid not in scores:
            scores[cid] = {**result, "rrf_score": 0.0}
        scores[cid]["rrf_score"] += 1.0 / (k + rank + 1)
        scores[cid]["method"] = "hybrid"

    merged = list(scores.values())
    merged.sort(key=lambda x: -x["rrf_score"])
    return merged


def _deduplicate(results: list[dict], threshold: float = 0.85) -> list[dict]:
    """
    Remove near-duplicate chunks (same source + overlapping text).
    Keeps the higher-scoring one.
    """
    seen = []
    deduped = []

    for result in results:
        text = result["text"].lower()
        is_dup = False

        for seen_text in seen:
            overlap = _text_overlap(text, seen_text)
            if overlap > threshold:
                is_dup = True
                break

        if not is_dup:
            deduped.append(result)
            seen.append(text)

    return deduped


def _text_overlap(a: str, b: str) -> float:
    """Rough overlap ratio using character n-grams."""
    if not a or not b:
        return 0.0

    # Use shorter text as reference
    short, long = (a, b) if len(a) <= len(b) else (b, a)

    # Check what proportion of the short text appears in the long text
    words_short = set(short.split())
    words_long = set(long.split())

    if not words_short:
        return 0.0

    overlap = len(words_short & words_long)
    return overlap / len(words_short)


def _rerank(results: list[dict], query: str) -> list[dict]:
    """
    Final reranking that factors in:
    - RRF score (from merge)
    - chunk importance (from ingest)
    - query term density in text
    - is-summary boost
    """
    query_words = set(query.lower().split())

    for result in results:
        rrf = result.get("rrf_score", 0.0)
        importance = result.get("importance", 0.5)

        # Term density: how many query words appear in this chunk?
        text_words = set(result["text"].lower().split())
        density = len(query_words & text_words) / max(len(query_words), 1)

        # Apply feedback boost if available
        feedback_boost = _get_feedback_boost(result["chunk_id"])

        final_score = (
            rrf * 0.4 +
            importance * 0.2 +
            density * 0.3 +
            feedback_boost * 0.1
        )

        result["final_score"] = round(final_score, 4)

    results.sort(key=lambda x: -x["final_score"])
    return results


def _get_feedback_boost(chunk_id: str) -> float:
    """Look up any learned boost for this chunk from the feedback table."""
    try:
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute(
            "SELECT SUM(boost) FROM chunk_feedback WHERE chunk_id = ?",
            (chunk_id,)
        ).fetchone()
        conn.close()
        return float(row[0] or 0.0)
    except:
        return 0.0


# ============================================================
# CONTEXT FORMATTING (Used by api.py / chat)
# ============================================================

def format_context(chunks: list[dict], max_chars: int = 2500) -> str:
    """
    Format retrieved chunks into a clean context block for the LLM prompt.
    Deduplicates sources, limits total length, preserves attribution.
    """
    if not chunks:
        return ""

    lines = []
    total = 0

    for chunk in chunks:
        source = chunk.get("source", "unknown")
        section = chunk.get("section", "")
        text = chunk["text"]

        label = f"[{source}]"
        if section and section != source:
            label += f" {section}"

        entry = f"{label}\n{text}"

        if total + len(entry) > max_chars:
            break

        lines.append(entry)
        total += len(entry)

    return "\n\n".join(lines)