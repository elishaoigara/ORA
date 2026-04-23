"""
ORA Knowledge — Phase 3
Embedding generation via Groq API + SQLite vector store.

Uses: Groq nomic-embed-text (free tier, fast)
Stores: embeddings as JSON blobs in SQLite (no external vector DB needed)
Retrieves: cosine similarity via numpy
"""

import json
import sqlite3
import numpy as np
from typing import Optional

DB_PATH = "ora_knowledge.db"


# ============================================================
# DB SETUP — VECTOR TABLE
# ============================================================

def init_vector_db():
    """Create the chunks + embeddings table if it doesn't exist."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS knowledge_chunks (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            chunk_id    TEXT    UNIQUE,
            source      TEXT    NOT NULL,
            doc_type    TEXT,
            tags        TEXT    DEFAULT '',
            section     TEXT    DEFAULT '',
            page_num    INTEGER DEFAULT 1,
            chunk_index INTEGER DEFAULT 0,
            text        TEXT    NOT NULL,
            importance  REAL    DEFAULT 0.5,
            embedding   TEXT,
            indexed_at  TEXT    NOT NULL
        )
    """)
    # FTS5 mirror for hybrid search (Phase 4)
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts
        USING fts5(
            chunk_id,
            source,
            section,
            text,
            content='knowledge_chunks',
            content_rowid='id'
        )
    """)
    # Feedback table for Phase 6 self-improvement
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chunk_feedback (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            chunk_id    TEXT,
            query       TEXT,
            was_useful  INTEGER DEFAULT 0,
            boost       REAL    DEFAULT 0.0,
            updated_at  TEXT
        )
    """)
    # Insights table for Phase 7 distillation
    conn.execute("""
        CREATE TABLE IF NOT EXISTS knowledge_insights (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            source          TEXT,
            insight_type    TEXT,
            content         TEXT,
            linked_chunks   TEXT,
            created_at      TEXT
        )
    """)
    conn.commit()
    conn.close()


# ============================================================
# EMBEDDING GENERATION
# ============================================================

def embed_text(text: str) -> Optional[list[float]]:
    """
    Generate embedding via Groq API.
    Model: nomic-embed-text-v1.5 (768 dims, free tier)
    Falls back gracefully if API unavailable.
    """
    try:
        from config import GROQ_API_KEY
        if not GROQ_API_KEY:
            return None

        from groq import Groq
        client = Groq(api_key=GROQ_API_KEY)

        response = client.embeddings.create(
            model="nomic-embed-text-v1_5",
            input=text[:4096]  # model token limit
        )

        return response.data[0].embedding

    except Exception as e:
        print(f"[EMBED] Failed: {e}")
        return None


def embed_batch(texts: list[str]) -> list[Optional[list[float]]]:
    """Embed multiple texts, returning None for any that fail."""
    results = []
    for text in texts:
        results.append(embed_text(text))
    return results


# ============================================================
# STORAGE
# ============================================================

def store_chunks(chunks: list[dict], tags: str = ""):
    """
    Store chunks with embeddings into SQLite.
    Each chunk dict from ingest.py:
    { text, section, source, page_num, chunk_index, importance, doc_type }
    """
    from datetime import datetime
    import uuid

    conn = sqlite3.connect(DB_PATH)
    stored = 0

    for chunk in chunks:
        chunk_id = str(uuid.uuid4())
        text = chunk["text"]

        # Generate embedding
        embedding = embed_text(text)
        embedding_json = json.dumps(embedding) if embedding else None

        now = datetime.now().isoformat()

        try:
            conn.execute("""
                INSERT INTO knowledge_chunks
                    (chunk_id, source, doc_type, tags, section, page_num,
                     chunk_index, text, importance, embedding, indexed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                chunk_id,
                chunk["source"],
                chunk.get("doc_type", "text"),
                tags,
                chunk.get("section", ""),
                chunk.get("page_num", 1),
                chunk.get("chunk_index", 0),
                text,
                chunk.get("importance", 0.5),
                embedding_json,
                now
            ))
            stored += 1
        except Exception as e:
            print(f"[STORE] Chunk insert failed: {e}")

    conn.commit()

    # Rebuild FTS index
    try:
        conn.execute("INSERT INTO knowledge_fts(knowledge_fts) VALUES('rebuild')")
        conn.commit()
    except Exception as e:
        print(f"[FTS] Rebuild failed: {e}")

    conn.close()
    return stored


def delete_source(filename: str):
    """Remove all chunks for a given source file."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM knowledge_chunks WHERE source = ?", (filename,))
    conn.execute("DELETE FROM knowledge_insights WHERE source = ?", (filename,))
    try:
        conn.execute("INSERT INTO knowledge_fts(knowledge_fts) VALUES('rebuild')")
    except:
        pass
    conn.commit()
    conn.close()


# ============================================================
# VECTOR SIMILARITY
# ============================================================

def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two embedding vectors."""
    va = np.array(a, dtype=np.float32)
    vb = np.array(b, dtype=np.float32)
    norm_a = np.linalg.norm(va)
    norm_b = np.linalg.norm(vb)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(va, vb) / (norm_a * norm_b))


def vector_search(query: str, n_results: int = 10) -> list[dict]:
    """
    Embed the query then find most similar chunks by cosine similarity.
    Returns ranked list of chunk dicts with similarity scores.
    """
    query_embedding = embed_text(query)
    if not query_embedding:
        return []

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    rows = conn.execute("""
        SELECT chunk_id, source, section, page_num, text, importance, embedding
        FROM knowledge_chunks
        WHERE embedding IS NOT NULL
        ORDER BY importance DESC
        LIMIT 500
    """).fetchall()
    conn.close()

    scored = []
    for row in rows:
        try:
            chunk_embedding = json.loads(row["embedding"])
            sim = cosine_similarity(query_embedding, chunk_embedding)
            scored.append({
                "chunk_id": row["chunk_id"],
                "text": row["text"],
                "source": row["source"],
                "section": row["section"],
                "page_num": row["page_num"],
                "importance": row["importance"],
                "score": sim,
                "method": "vector"
            })
        except Exception:
            continue

    scored.sort(key=lambda x: -x["score"])
    return scored[:n_results]