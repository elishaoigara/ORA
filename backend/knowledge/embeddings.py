"""
ORA Knowledge Embeddings — FTS-only (Render Free Tier Safe)

- No sentence-transformers (zero RAM heavy ops)
- Uses SQLite FTS5 for retrieval
- Compatible with old vector interface
"""

import sqlite3
from typing import Optional, List, Dict
from config import DB_PATH

MAX_CHUNKS_PER_DOC = 80


# ============================================================
# DB SETUP
# ============================================================
def init_vector_db():
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

    # FTS5 table
    try:
        conn.execute("SELECT 1 FROM knowledge_fts LIMIT 1")
    except Exception:
        print("[DB] Rebuilding FTS5 table...")
        conn.execute("DROP TABLE IF EXISTS knowledge_fts")
        conn.execute("""
            CREATE VIRTUAL TABLE knowledge_fts
            USING fts5(chunk_id, source, section, text)
        """)
        conn.commit()

    conn.commit()
    conn.close()


# ============================================================
# EMBEDDING (NO-OP)
# ============================================================
def embed_text(text: str):
    return None


def get_embedding_model():
    return None


# ============================================================
# SEARCH (FTS5)
# ============================================================
def vector_search(
    query: str,
    top_k: int = 5,
    source_filter: Optional[str] = None,
    n_results: Optional[int] = None,   # backward compatibility
) -> List[Dict]:
    """
    FTS5-based search replacing vector search.
    Supports both top_k (new) and n_results (old).
    """

    # backward compatibility layer
    if n_results is not None:
        top_k = n_results

    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row

        safe_q = _safe_fts_query(query)
        if not safe_q:
            conn.close()
            return []

        if source_filter:
            rows = conn.execute("""
                SELECT chunk_id, source, text,
                       bm25(knowledge_fts) AS score
                FROM knowledge_fts
                WHERE knowledge_fts MATCH ?
                  AND source = ?
                ORDER BY score
                LIMIT ?
            """, (safe_q, source_filter, top_k)).fetchall()
        else:
            rows = conn.execute("""
                SELECT chunk_id, source, text,
                       bm25(knowledge_fts) AS score
                FROM knowledge_fts
                WHERE knowledge_fts MATCH ?
                ORDER BY score
                LIMIT ?
            """, (safe_q, top_k)).fetchall()

        conn.close()

        return [dict(r) for r in rows]

    except Exception as e:
        print(f"[RAG ERROR] FTS search failed: {e}")
        return []


# ============================================================
# STORE CHUNKS
# ============================================================
def store_chunks(chunks: List[Dict]) -> int:
    if not chunks:
        return 0

    chunks = chunks[:MAX_CHUNKS_PER_DOC]
    print(f"[FTS] storing {len(chunks)} chunks...")

    conn = sqlite3.connect(DB_PATH)
    stored = 0

    try:
        for c in chunks:
            try:
                conn.execute("""
                    INSERT OR IGNORE INTO knowledge_chunks
                    (chunk_id, source, doc_type, tags, section,
                     page_num, chunk_index, text, importance,
                     embedding, indexed_at)
                    VALUES (?,?,?,?,?,?,?,?,?,NULL,?)
                """, (
                    c["chunk_id"],
                    c["source"],
                    c.get("doc_type", ""),
                    c.get("tags", ""),
                    c.get("section", ""),
                    c.get("page_num", 1),
                    c.get("chunk_index", 0),
                    c["text"],
                    c.get("importance", 0.5),
                    c["indexed_at"],
                ))

                conn.execute("""
                    INSERT OR IGNORE INTO knowledge_fts
                    (chunk_id, source, section, text)
                    VALUES (?,?,?,?)
                """, (
                    c["chunk_id"],
                    c["source"],
                    c.get("section", ""),
                    c["text"],
                ))

                stored += 1

            except Exception as e:
                print(f"[FTS] insert error: {e}")
                continue

        conn.commit()

    finally:
        conn.close()

    return stored


# ============================================================
# HELPERS
# ============================================================
def _safe_fts_query(query: str) -> str:
    import re

    cleaned = re.sub(r"[^\w\s]", " ", query)
    cleaned = " ".join(cleaned.split())

    if not cleaned:
        return ""

    words = cleaned.split()

    # better ranking than OR spam
    return " ".join(words[:8])


def delete_source(source: str) -> int:
    conn = sqlite3.connect(DB_PATH)

    try:
        conn.execute("DELETE FROM knowledge_fts WHERE source = ?", (source,))
        cur = conn.execute(
            "DELETE FROM knowledge_chunks WHERE source = ?", (source,)
        )

        deleted = cur.rowcount
        conn.commit()
        return deleted

    except Exception as e:
        print(f"[FTS] delete error: {e}")
        return 0

    finally:
        conn.close()