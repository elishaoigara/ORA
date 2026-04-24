"""
ORA Knowledge — Phase 6 + 7
Self-improvement feedback loop and knowledge distillation.
"""

import sqlite3
import json
from datetime import datetime
from config import DB_PATH


# ============================================================
# PHASE 6 — FEEDBACK LOOP
# ============================================================

def log_query(query: str, used_chunk_ids: list[str]):
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS query_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query TEXT,
                chunk_ids TEXT,
                timestamp TEXT
            )
        """)
        conn.execute(
            "INSERT INTO query_log (query, chunk_ids, timestamp) VALUES (?, ?, ?)",
            (query, json.dumps(used_chunk_ids), datetime.now().isoformat())
        )
        conn.commit()
    except Exception as e:
        print(f"[FEEDBACK] log_query failed: {e}")
    finally:
        conn.close()


def _update_boost(chunk_id: str, query: str, was_useful: int, boost: float):
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chunk_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chunk_id TEXT,
                query TEXT,
                was_useful INTEGER,
                boost REAL,
                updated_at TEXT
            )
        """)

        conn.execute("""
            INSERT INTO chunk_feedback
            (chunk_id, query, was_useful, boost, updated_at)
            VALUES (?, ?, ?, ?, ?)
        """, (
            chunk_id,
            query,
            was_useful,
            boost,
            datetime.now().isoformat()
        ))

        conn.commit()

    except Exception as e:
        print(f"[FEEDBACK] update_boost failed: {e}")
    finally:
        conn.close()


def record_useful(chunk_id: str, query: str, boost: float = 0.05):
    _update_boost(chunk_id, query, 1, boost)


def record_not_useful(chunk_id: str, query: str, penalty: float = 0.03):
    _update_boost(chunk_id, query, 0, -penalty)


def get_top_chunks_by_feedback(limit: int = 10):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("""
            SELECT cf.chunk_id, SUM(cf.boost) as total_boost,
                   kc.source, kc.text
            FROM chunk_feedback cf
            JOIN knowledge_chunks kc ON kc.chunk_id = cf.chunk_id
            GROUP BY cf.chunk_id
            ORDER BY total_boost DESC
            LIMIT ?
        """, (limit,)).fetchall()

        return [dict(r) for r in rows]

    except Exception as e:
        print(f"[FEEDBACK] top_chunks failed: {e}")
        return []
    finally:
        conn.close()


def auto_signal_from_conversation(query: str, used_chunks: list[dict], follow_up_query: str):
    if not used_chunks or not follow_up_query:
        return

    q_words = set(query.lower().split())
    f_words = set(follow_up_query.lower().split())

    overlap = len(q_words & f_words) / max(len(q_words), 1)

    for chunk in used_chunks:
        cid = chunk.get("chunk_id")
        if not cid:
            continue

        if overlap < 0.3:
            record_not_useful(cid, query)
        elif overlap > 0.6:
            record_useful(cid, query)


# ============================================================
# PHASE 7 — DISTILLATION
# ============================================================

def distill_document(source: str, full_text: str, chunk_ids: list[str]):
    print(f"[DISTILL] {source}")

    summary = _generate_summary(source, full_text)
    concepts = _extract_key_concepts(full_text)

    insight = _build_insight(source, summary, concepts)

    if insight:
        _store_insight(source, "full_distillation", insight, chunk_ids)

    if summary:
        _store_summary_chunk(source, summary, chunk_ids)

    return summary


# ============================================================
# GROQ HELPERS (SAFE IMPORT)
# ============================================================

def _get_groq_client():
    try:
        from config import GROQ_API_KEY
        from groq import Groq

        if not GROQ_API_KEY:
            return None

        return Groq(api_key=GROQ_API_KEY)
    except Exception:
        return None


def _generate_summary(source: str, text: str) -> str:
    client = _get_groq_client()
    if not client:
        return ""

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{
                "role": "user",
                "content": (
                    f"Summarize this document in 3–5 sentences:\n\n"
                    f"{text[:4000]}"
                )
            }],
            max_tokens=200,
            temperature=0.3
        )

        return response.choices[0].message.content.strip()

    except Exception as e:
        print(f"[DISTILL] summary failed: {e}")
        return ""


def _extract_key_concepts(text: str) -> list[str]:
    client = _get_groq_client()
    if not client:
        return []

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{
                "role": "user",
                "content": (
                    "Extract 5–10 key concepts as JSON list only.\n\n"
                    f"{text[:2000]}"
                )
            }],
            max_tokens=150,
            temperature=0.1
        )

        raw = response.choices[0].message.content
        raw = raw.replace("```json", "").replace("```", "").strip()

        data = json.loads(raw)
        return data if isinstance(data, list) else []

    except Exception as e:
        print(f"[DISTILL] concepts failed: {e}")
        return []


# ============================================================
# STORAGE
# ============================================================

def _store_insight(source, insight_type, content, linked_chunks):
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS knowledge_insights (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT,
                insight_type TEXT,
                content TEXT,
                linked_chunks TEXT,
                created_at TEXT
            )
        """)

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
        print(f"[DISTILL] insight failed: {e}")
    finally:
        conn.close()


def _store_summary_chunk(source: str, summary: str, linked_chunks: list[str]):
    import uuid

    try:
        from knowledge.embeddings import embed_text
        embedding = embed_text(summary)
    except Exception:
        embedding = None

    conn = sqlite3.connect(DB_PATH)

    try:
        conn.execute("""
            INSERT INTO knowledge_chunks
            (chunk_id, source, doc_type, tags, section,
             page_num, chunk_index, text, importance,
             embedding, indexed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(uuid.uuid4()),
            source,
            "summary",
            "auto",
            "SUMMARY",
            0,
            -1,
            f"SUMMARY: {summary}",
            0.95,
            json.dumps(embedding) if embedding else None,
            datetime.now().isoformat()
        ))

        conn.commit()

    except Exception as e:
        print(f"[DISTILL] summary store failed: {e}")
    finally:
        conn.close()


def _build_insight(source: str, summary: str, concepts: list[str]) -> str:
    parts = []

    if summary:
        parts.append(f"SUMMARY: {summary}")

    if concepts:
        parts.append("CONCEPTS: " + ", ".join(concepts))

    return f"[{source}]\n" + "\n".join(parts) if parts else ""


def get_insights_for_source(source: str):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    try:
        rows = conn.execute("""
            SELECT * FROM knowledge_insights
            WHERE source = ?
            ORDER BY created_at DESC
        """, (source,)).fetchall()

        return [dict(r) for r in rows]

    except Exception as e:
        print(f"[DISTILL] fetch insights failed: {e}")
        return []
    finally:
        conn.close()