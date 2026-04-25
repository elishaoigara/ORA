"""
ORA Knowledge Embeddings — FTS-only (Render Free Tier Safe)

sentence-transformers removed entirely.
Search uses SQLite FTS5 (full-text search) — fast, zero RAM overhead.
embed_text() returns None so callers stay compatible.
"""

import sqlite3
from typing import Optional
from config import DB_PATH


MAX_CHUNKS_PER_DOC = 80   # lower cap = less RAM during indexing


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
    conn.commit()

    try:
        conn.execute("SELECT 1 FROM knowledge_fts LIMIT 1")
    except Exception:
        print("[DB] Rebuilding FTS5 table...")
        conn.execute("DROP TABLE IF EXISTS knowledge_fts")
        conn.execute("""
            CREATE VIRTUAL TABLE knowledge_fts
            USING fts5(chunk_id, source, section, text)
        """)
        conn.execute("INSERT INTO knowledge_fts(knowledge_fts) VALUES('rebuild')")
        conn.commit()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS chunk_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chunk_id TEXT,
            query TEXT,
            was_useful INTEGER DEFAULT 0,
            boost REAL DEFAULT 0.0,
            updated_at TEXT
        )
    """)
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
    conn.commit()
    conn.close()


# ============================================================
# EMBEDDING (stub — FTS does the work)
# ============================================================
def embed_text(text: str) -> None:
    """No-op. FTS5 handles retrieval — no vector embeddings needed."""
    return None


# Alias for any code still calling the old name
def get_embedding_model():
    return None


# ============================================================
# VECTOR SEARCH — implemented as FTS5 search
# ============================================================
def vector_search(query: str, n_results: int = 5, source_filter: Optional[str] = None) -> list[dict]:
    """
    FTS5 full-text search. Same interface as the old vector search.
    Returns list of {chunk_id, source, text, score} dicts.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row

        # Clean query for FTS5 (strip special chars that break the parser)
        safe_q = _safe_fts_query(query)
        if not safe_q:
            conn.close()
            return []

        if source_filter:
            rows = conn.execute("""
                SELECT kf.chunk_id, kf.source, kf.text,
                       rank as score
                FROM knowledge_fts kf
                WHERE knowledge_fts MATCH ?
                  AND kf.source = ?
                ORDER BY rank
                LIMIT ?
            """, (safe_q, source_filter, n_results)).fetchall()
        else:
            rows = conn.execute("""
                SELECT chunk_id, source, text,
                       rank as score
                FROM knowledge_fts
                WHERE knowledge_fts MATCH ?
                ORDER BY rank
                LIMIT ?
            """, (safe_q, n_results)).fetchall()

        conn.close()
        return [dict(r) for r in rows]

    except Exception as e:
        print(f"[EMBED] FTS search error: {e}")
        return []


# ============================================================
# STORE CHUNKS (called by pipeline after chunking)
# ============================================================
def store_chunks(chunks: list[dict]) -> int:
    """
    Stores text chunks into knowledge_chunks + FTS index.
    chunks: list of {chunk_id, source, doc_type, tags, section,
                      page_num, chunk_index, text, importance, indexed_at}
    Returns number stored.
    """
    if not chunks:
        return 0

    # Cap per-doc to avoid RAM/time blowout on large files
    chunks = chunks[:MAX_CHUNKS_PER_DOC]
    print(f"[EMBED] storing {len(chunks)} chunks (FTS only)...")

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
                    c["chunk_id"], c["source"], c.get("doc_type", ""),
                    c.get("tags", ""), c.get("section", ""),
                    c.get("page_num", 1), c.get("chunk_index", 0),
                    c["text"], c.get("importance", 0.5),
                    c["indexed_at"],
                ))

                # Keep FTS in sync
                conn.execute("""
                    INSERT OR IGNORE INTO knowledge_fts
                    (chunk_id, source, section, text)
                    VALUES (?,?,?,?)
                """, (
                    c["chunk_id"], c["source"],
                    c.get("section", ""), c["text"]
                ))
                stored += 1
            except Exception as e:
                print(f"[EMBED] chunk insert error: {e}")
                continue

        conn.commit()
    finally:
        conn.close()

    return stored


# ============================================================
# HELPERS
# ============================================================
def _safe_fts_query(query: str) -> str:
    """Strip FTS5 special chars to avoid parse errors."""
    import re
    # Remove FTS5 operators/punctuation that break queries
    cleaned = re.sub(r'[^\w\s]', ' ', query)
    cleaned = ' '.join(cleaned.split())
    if not cleaned:
        return ""
    # Wrap multi-word query as phrase search fallback
    words = cleaned.split()
    return " OR ".join(words[:8])  # cap at 8 terms