"""
ORA Knowledge — Phase 3
Embedding generation via Groq API + SQLite vector store.

Uses: sentence-transformers all-MiniLM-L6-v2 (local, CPU, no API key)
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

    # FIX: safer FTS check
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
# EMBEDDING CONFIG
# ============================================================

MAX_CHUNKS_PER_DOC = 150
_EMBED_BATCH_SIZE = 64

_model = None


def _get_model():
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
            _model = SentenceTransformer("all-MiniLM-L6-v2")
            print("[EMBED] Model loaded")
        except Exception as e:
            print(f"[EMBED ERROR] {e}")
            _model = None
    return _model


def embed_batch(texts: list[str]) -> list[Optional[list[float]]]:
    model = _get_model()
    if not model:
        return [None] * len(texts)

    try:
        vectors = model.encode(texts, show_progress_bar=False)
        return [v.tolist() for v in vectors]
    except Exception as e:
        print(f"[EMBED BATCH ERROR] {e}")
        return [None] * len(texts)


def embed_text(text: str):
    return embed_batch([text])[0]


# ============================================================
# STORAGE (FIXED ALIGNMENT BUG HERE 🔥)
# ============================================================

def store_chunks(chunks: list[dict], tags: str = ""):
    from datetime import datetime
    import uuid

    if not chunks:
        return 0

    # limit chunks (Render safety)
    if len(chunks) > MAX_CHUNKS_PER_DOC:
        chunks = sorted(
            chunks,
            key=lambda c: c.get("importance", 0.5),
            reverse=True
        )[:MAX_CHUNKS_PER_DOC]

    conn = sqlite3.connect(DB_PATH)

    now = datetime.now().isoformat()

    all_texts = []
    insert_map = []  # FIX: proper alignment tracking

    # ========================================================
    # STEP 1: INSERT + CHUNK TEXT EXPANSION
    # ========================================================
    for chunk in chunks:
        raw_text = chunk["text"]

        cid_base = str(uuid.uuid4())

        # simple internal chunking (safe + consistent)
        chunk_size = 500
        overlap = 100

        start = 0
        idx = 0

        while start < len(raw_text):
            part = raw_text[start:start + chunk_size].strip()
            if not part:
                break

            chunk_id = f"{cid_base}_{idx}"

            conn.execute("""
                INSERT OR IGNORE INTO knowledge_chunks
                (chunk_id, source, doc_type, tags, section, page_num,
                 chunk_index, text, importance, embedding, indexed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)
            """, (
                chunk_id,
                chunk["source"],
                chunk.get("doc_type", "text"),
                tags,
                chunk.get("section", ""),
                chunk.get("page_num", 1),
                idx,
                part,
                chunk.get("importance", 0.5),
                now
            ))

            all_texts.append(part)
            insert_map.append(chunk_id)

            start += chunk_size - overlap
            idx += 1

    conn.commit()

    # ========================================================
    # STEP 2: EMBEDDINGS
    # ========================================================
    print(f"[EMBED] encoding {len(all_texts)} chunks...")
    embeddings = embed_batch(all_texts)

    # ========================================================
    # STEP 3: SAFE UPDATE (FIXED ZIP BUG)
    # ========================================================
    for i in range(len(insert_map)):
        cid = insert_map[i]
        emb = embeddings[i] if i < len(embeddings) else None

        if emb:
            conn.execute(
                "UPDATE knowledge_chunks SET embedding=? WHERE chunk_id=?",
                (json.dumps(emb), cid)
            )

    conn.commit()

    # ========================================================
    # STEP 4: FTS REBUILD
    # ========================================================
    try:
        conn.execute("INSERT INTO knowledge_fts(knowledge_fts) VALUES('rebuild')")
        conn.commit()
    except:
        pass

    conn.close()

    print(f"[STORE] stored {len(insert_map)} chunks")
    return len(insert_map)


# ============================================================
# VECTOR SEARCH (STABLE + CLEAN)
# ============================================================

def cosine_similarity(a, b):
    va = np.array(a, dtype=np.float32)
    vb = np.array(b, dtype=np.float32)

    denom = np.linalg.norm(va) * np.linalg.norm(vb)
    if denom == 0:
        return 0.0

    return float(np.dot(va, vb) / denom)


def vector_search(query: str, n_results: int = 10):
    query_emb = embed_text(query)
    if not query_emb:
        return []

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    rows = conn.execute("""
        SELECT chunk_id, source, section, page_num, text, importance, embedding
        FROM knowledge_chunks
        WHERE embedding IS NOT NULL
        LIMIT 1000
    """).fetchall()

    conn.close()

    results = []

    for r in rows:
        try:
            emb = json.loads(r["embedding"])
            score = cosine_similarity(query_emb, emb)

            results.append({
                "chunk_id": r["chunk_id"],
                "text": r["text"],
                "source": r["source"],
                "section": r["section"],
                "page_num": r["page_num"],
                "importance": r["importance"],
                "score": score,
                "final_score": (score * 0.75) + (r["importance"] * 0.25),
            })

        except:
            continue

    results.sort(key=lambda x: -x["final_score"])
    return results[:n_results]


# ============================================================
# DELETE
# ============================================================

def delete_source(filename: str):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM knowledge_chunks WHERE source=?", (filename,))
    conn.execute("DELETE FROM knowledge_insights WHERE source=?", (filename,))

    try:
        conn.execute("INSERT INTO knowledge_fts(knowledge_fts) VALUES('rebuild')")
    except:
        pass

    conn.commit()
    conn.close()