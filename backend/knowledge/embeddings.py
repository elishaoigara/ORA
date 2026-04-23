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
from config import DB_PATH


# ============================================================
# DB SETUP — VECTOR TABLE
# ============================================================

def init_vector_db():
    """Create the chunks + embeddings table if it doesn't exist.
    Also repairs a corrupted/mismatched FTS5 table on existing deployments.
    """
    conn = sqlite3.connect(DB_PATH)

    # Main chunks table
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

    # FTS5 table: drop and recreate if broken (column mismatch from old deploy)
    try:
        conn.execute("SELECT chunk_id FROM knowledge_fts LIMIT 1")
    except Exception:
        print("[DB] Rebuilding FTS5 table (schema repair)...")
        conn.execute("DROP TABLE IF EXISTS knowledge_fts")
        conn.execute("""
            CREATE VIRTUAL TABLE knowledge_fts
            USING fts5(
                chunk_id,
                source,
                section,
                text,
                content='knowledge_chunks',
                content_rowid='id'
            )
        """)
        conn.execute("INSERT INTO knowledge_fts(knowledge_fts) VALUES('rebuild')")
        conn.commit()
        print("[DB] FTS5 table rebuilt OK.")

    # Feedback table
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

    # Insights table
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

# Max chunks embedded per document — prevents runaway ingestion on huge PDFs.
# At ~0.3s per batch call, 100 chunks = ~1 call = fast. Tune up if needed.
MAX_CHUNKS_PER_DOC = 120
GROQ_EMBED_BATCH   = 96   # Groq accepts up to 96 inputs per embedding call


def embed_text(text: str) -> Optional[list[float]]:
    """Single-text embedding. Used for query embedding at search time."""
    results = _embed_batch_groq([text])
    return results[0] if results else None


def _embed_batch_groq(texts: list[str]) -> list[Optional[list[float]]]:
    """
    Call Groq embeddings API with a batch of texts in ONE request.
    Returns a list of embeddings (None for any slot that failed).
    Groq supports up to 96 inputs per call.
    """
    try:
        from config import GROQ_API_KEY
        if not GROQ_API_KEY:
            return [None] * len(texts)

        from groq import Groq
        client = Groq(api_key=GROQ_API_KEY)

        # Truncate each text to model token limit
        inputs = [t[:4096] for t in texts]

        response = client.embeddings.create(
            model="nomic-embed-text-v1.5",
            input=inputs
        )

        # Response items are ordered by index
        results = [None] * len(inputs)
        for item in response.data:
            results[item.index] = item.embedding

        return results

    except Exception as e:
        print(f"[EMBED] Batch failed: {e}")
        return [None] * len(texts)


def embed_batch(texts: list[str]) -> list[Optional[list[float]]]:
    """Embed multiple texts in efficient batches."""
    all_results = []
    for i in range(0, len(texts), GROQ_EMBED_BATCH):
        batch = texts[i:i + GROQ_EMBED_BATCH]
        all_results.extend(_embed_batch_groq(batch))
    return all_results


# ============================================================
# STORAGE
# ============================================================

def store_chunks(chunks: list[dict], tags: str = ""):
    """
    Store chunks with embeddings into SQLite.

    Strategy:
      1. Cap total chunks to MAX_CHUNKS_PER_DOC (prevents huge PDFs from
         making hundreds of API calls and timing out Render)
      2. Insert all chunk rows first (without embeddings) in one transaction
      3. Embed all texts in a single batched Groq call
      4. Update rows with their embeddings in one transaction
      5. Rebuild FTS index once at the end

    This reduces N Groq round-trips to ceil(N/96) — typically 1-2 calls.
    """
    from datetime import datetime
    import uuid

    # Cap chunks to avoid unbounded embed time on huge docs
    if len(chunks) > MAX_CHUNKS_PER_DOC:
        # Keep highest-importance chunks
        chunks = sorted(chunks, key=lambda c: -c.get("importance", 0.5))[:MAX_CHUNKS_PER_DOC]
        print(f"[STORE] Capped to {MAX_CHUNKS_PER_DOC} highest-importance chunks")

    now = datetime.now().isoformat()
    conn = sqlite3.connect(DB_PATH)
    stored = 0

    # ── Step 1: assign chunk IDs and insert rows (no embeddings yet) ──
    chunk_ids = []
    for chunk in chunks:
        cid = str(uuid.uuid4())
        chunk_ids.append(cid)
        try:
            conn.execute("""
                INSERT OR IGNORE INTO knowledge_chunks
                    (chunk_id, source, doc_type, tags, section, page_num,
                     chunk_index, text, importance, embedding, indexed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)
            """, (
                cid,
                chunk["source"],
                chunk.get("doc_type", "text"),
                tags,
                chunk.get("section", ""),
                chunk.get("page_num", 1),
                chunk.get("chunk_index", 0),
                chunk["text"],
                chunk.get("importance", 0.5),
                now
            ))
            stored += 1
        except Exception as e:
            print(f"[STORE] Insert failed: {e}")
            chunk_ids.append(None)  # keep alignment

    conn.commit()

    # ── Step 2: batch-embed all texts in as few API calls as possible ──
    texts = [c["text"] for c in chunks]
    print(f"[EMBED] Batching {len(texts)} chunks in {(len(texts)-1)//GROQ_EMBED_BATCH + 1} API call(s)...")
    embeddings = embed_batch(texts)

    # ── Step 3: write embeddings back ──
    for cid, embedding in zip(chunk_ids, embeddings):
        if cid and embedding:
            try:
                conn.execute(
                    "UPDATE knowledge_chunks SET embedding = ? WHERE chunk_id = ?",
                    (json.dumps(embedding), cid)
                )
            except Exception as e:
                print(f"[STORE] Embedding update failed: {e}")

    conn.commit()

    # ── Step 4: rebuild FTS once ──
    try:
        conn.execute("INSERT INTO knowledge_fts(knowledge_fts) VALUES('rebuild')")
        conn.commit()
    except Exception as e:
        print(f"[FTS] Rebuild failed: {e}")

    conn.close()
    print(f"[STORE] Stored {stored} chunks with embeddings")
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