"""
ORA Knowledge — Phase 6 + 7
Self-improvement feedback loop and knowledge distillation.

Phase 6: Log queries, capture signals, boost/downrank chunks.
Phase 7: Generate summaries, key concepts, insights after ingestion.
         These are stored separately and retrieved alongside raw chunks.
"""

import sqlite3
import json
from datetime import datetime

DB_PATH = "ora_knowledge.db"


# ============================================================
# PHASE 6 — SELF-IMPROVEMENT FEEDBACK LOOP
# ============================================================

def log_query(query: str, used_chunk_ids: list[str]):
    """
    Log every retrieval for later analysis.
    This is the raw data that feeds the improvement loop.
    """
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS query_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                query       TEXT,
                chunk_ids   TEXT,
                timestamp   TEXT
            )
        """)
        conn.execute(
            "INSERT INTO query_log (query, chunk_ids, timestamp) VALUES (?, ?, ?)",
            (query, json.dumps(used_chunk_ids), datetime.now().isoformat())
        )
        conn.commit()
    except Exception as e:
        print(f"[FEEDBACK] Log failed: {e}")
    finally:
        conn.close()


def record_useful(chunk_id: str, query: str, boost: float = 0.05):
    """
    Mark a chunk as useful for a given query.
    Called when: user asks follow-up, gives explicit thumbs-up,
    or a long engaged conversation follows this retrieval.
    """
    _update_boost(chunk_id, query, was_useful=1, boost=boost)


def record_not_useful(chunk_id: str, query: str, penalty: float = 0.03):
    """
    Mark a chunk as not useful.
    Called when: user immediately rephrases the question (weak answer signal).
    """
    _update_boost(chunk_id, query, was_useful=0, boost=-penalty)


def _update_boost(chunk_id: str, query: str, was_useful: int, boost: float):
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("""
            INSERT INTO chunk_feedback (chunk_id, query, was_useful, boost, updated_at)
            VALUES (?, ?, ?, ?, ?)
        """, (chunk_id, query, was_useful, boost, datetime.now().isoformat()))
        conn.commit()
    except Exception as e:
        print(f"[FEEDBACK] Update failed: {e}")
    finally:
        conn.close()


def get_top_chunks_by_feedback(limit: int = 10) -> list[dict]:
    """Return the chunks that have proven most useful over time."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT cf.chunk_id, SUM(cf.boost) as total_boost, kc.source, kc.text
        FROM chunk_feedback cf
        JOIN knowledge_chunks kc ON kc.chunk_id = cf.chunk_id
        GROUP BY cf.chunk_id
        ORDER BY total_boost DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def auto_signal_from_conversation(query: str, used_chunks: list[dict], follow_up_query: str):
    """
    Automatic feedback signal:
    - If follow-up is very different from original → previous answer was weak → penalize
    - If follow-up is a continuation/deepening → answer was strong → boost
    """
    if not used_chunks or not follow_up_query:
        return

    query_words = set(query.lower().split())
    follow_words = set(follow_up_query.lower().split())

    overlap = len(query_words & follow_words) / max(len(query_words), 1)

    for chunk in used_chunks:
        cid = chunk.get("chunk_id", "")
        if not cid:
            continue

        if overlap < 0.3:
            # Very different follow-up → weak answer
            record_not_useful(cid, query)
        elif overlap > 0.6:
            # Continuation → strong answer
            record_useful(cid, query)


# ============================================================
# PHASE 7 — KNOWLEDGE DISTILLATION
# ============================================================

def distill_document(source: str, full_text: str, chunk_ids: list[str]):
    """
    After ingestion, generate structured insights from the document.
    Stores: summary, key concepts, relationships.
    These are retrieved alongside raw chunks for richer answers.
    """
    print(f"[DISTILL] Processing {source}...")

    summary = _generate_summary(source, full_text)
    concepts = _extract_key_concepts(full_text)
    insight_text = _build_insight(source, summary, concepts)

    if insight_text:
        _store_insight(
            source=source,
            insight_type="full_distillation",
            content=insight_text,
            linked_chunks=chunk_ids
        )

    # Also embed and store the summary as a high-importance chunk
    if summary:
        _store_summary_chunk(source, summary, chunk_ids)

    print(f"[DISTILL] Done: {source}")
    return summary


def _generate_summary(source: str, text: str) -> str:
    """Generate a concise document summary via Groq."""
    try:
        from config import GROQ_API_KEY
        from groq import Groq

        if not GROQ_API_KEY:
            return ""

        client = Groq(api_key=GROQ_API_KEY)
        sample = text[:4000]

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{
                "role": "user",
                "content": (
                    f"Document: {source}\n\n"
                    f"Content:\n{sample}\n\n"
                    "Write a precise 3-5 sentence summary. "
                    "Include: main topic, key facts, and any action items or conclusions. "
                    "Be specific, not generic."
                )
            }],
            max_tokens=200,
            temperature=0.3
        )

        return response.choices[0].message.content.strip()

    except Exception as e:
        print(f"[DISTILL] Summary failed: {e}")
        return ""


def _extract_key_concepts(text: str) -> list[str]:
    """
    Extract key concepts and entities from document text.
    Uses Groq for intelligent extraction.
    """
    try:
        from config import GROQ_API_KEY
        from groq import Groq

        if not GROQ_API_KEY:
            return []

        client = Groq(api_key=GROQ_API_KEY)

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{
                "role": "user",
                "content": (
                    f"Extract 5-10 key concepts, terms, or entities from this text.\n"
                    f"Return ONLY a JSON array of strings. No explanation.\n\n"
                    f"Text:\n{text[:2000]}"
                )
            }],
            max_tokens=150,
            temperature=0.1
        )

        raw = response.choices[0].message.content.strip()
        # Strip markdown fences if present
        raw = raw.replace("```json", "").replace("```", "").strip()
        concepts = json.loads(raw)
        return concepts if isinstance(concepts, list) else []

    except Exception as e:
        print(f"[DISTILL] Concepts failed: {e}")
        return []


def _build_insight(source: str, summary: str, concepts: list[str]) -> str:
    """Combine summary + concepts into a structured insight entry."""
    parts = []

    if summary:
        parts.append(f"SUMMARY: {summary}")

    if concepts:
        parts.append(f"KEY CONCEPTS: {', '.join(concepts)}")

    return f"[{source}]\n" + "\n".join(parts) if parts else ""


def _store_insight(source: str, insight_type: str, content: str, linked_chunks: list[str]):
    """Persist insight to knowledge_insights table."""
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("""
            INSERT INTO knowledge_insights
                (source, insight_type, content, linked_chunks, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (
            source,
            insight_type,
            content,
            json.dumps(linked_chunks),
            datetime.now().isoformat()
        ))
        conn.commit()
    except Exception as e:
        print(f"[DISTILL] Store insight failed: {e}")
    finally:
        conn.close()


def _store_summary_chunk(source: str, summary: str, linked_chunks: list[str]):
    """
    Store the summary as a high-importance chunk with its own embedding.
    This ensures summaries appear in retrieval for broad questions.
    """
    import uuid
    from knowledge.embeddings import embed_text

    embedding = embed_text(summary)
    embedding_json = json.dumps(embedding) if embedding else None

    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("""
            INSERT INTO knowledge_chunks
                (chunk_id, source, doc_type, tags, section, page_num,
                 chunk_index, text, importance, embedding, indexed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(uuid.uuid4()),
            source,
            "summary",
            "auto-generated",
            "DOCUMENT SUMMARY",
            0,
            -1,  # -1 marks as summary (sorted before other chunks)
            f"SUMMARY: {summary}",
            0.95,  # summaries get highest importance
            embedding_json,
            datetime.now().isoformat()
        ))
        conn.commit()
        # Rebuild FTS
        try:
            conn.execute("INSERT INTO knowledge_fts(knowledge_fts) VALUES('rebuild')")
            conn.commit()
        except:
            pass
    except Exception as e:
        print(f"[DISTILL] Summary chunk store failed: {e}")
    finally:
        conn.close()


def get_insights_for_source(source: str) -> list[dict]:
    """Retrieve all insights for a given document."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT * FROM knowledge_insights WHERE source = ?
        ORDER BY created_at DESC
    """, (source,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]