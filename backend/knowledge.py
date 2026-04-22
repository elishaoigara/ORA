"""
ORA Hybrid Knowledge Base
SQLite FTS5 + MiniLM embeddings + lightweight reranking

- FTS5 → fast keyword retrieval
- Embeddings → semantic meaning search
- Hybrid scoring → best of both worlds
- No ChromaDB (avoids RAM crash)
"""

import os
import sqlite3
import uuid
import numpy as np
from datetime import datetime

import PyPDF2
from PIL import Image

# ========================
# EMBEDDINGS (MiniLM - lightweight)
# ========================
from sentence_transformers import SentenceTransformer

EMBED_MODEL = SentenceTransformer("all-MiniLM-L6-v2")

UPLOADS_PATH = os.getenv("UPLOADS_PATH", "uploads")
KB_DB_PATH = os.getenv("KB_DB_PATH", "ora_knowledge.db")

os.makedirs(UPLOADS_PATH, exist_ok=True)


# ========================
# DATABASE
# ========================
def _get_conn():
    conn = sqlite3.connect(KB_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_kb():
    conn = _get_conn()

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS knowledge (
            id TEXT PRIMARY KEY,
            filename TEXT,
            doc_type TEXT,
            tags TEXT,
            uploaded_at TEXT,
            chunk_index INTEGER,
            content TEXT,
            embedding BLOB
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts
        USING fts5(content);
    """)

    conn.commit()
    conn.close()
    print("[Knowledge] Hybrid DB ready (SQLite + Embeddings)")


_init_kb()


# ========================
# TEXT EXTRACTION
# ========================
def extract_text_from_pdf(filepath):
    try:
        text = ""
        with open(filepath, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                text += page.extract_text() or ""
        return text.strip()
    except:
        return ""


def extract_text_from_txt(filepath):
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            return f.read().strip()
    except:
        return ""


def extract_text_from_image(filepath):
    try:
        img = Image.open(filepath)
        return f"Image: {img.size} {img.mode}"
    except:
        return ""


# ========================
# CHUNKING
# ========================
def chunk_text(text, size=500, overlap=80):
    chunks = []
    start = 0
    while start < len(text):
        end = start + size
        chunks.append(text[start:end])
        start = end - overlap
    return [c for c in chunks if c.strip()]


# ========================
# EMBEDDINGS
# ========================
def get_embedding(text: str):
    vec = EMBED_MODEL.encode(text)
    return np.array(vec, dtype=np.float32).tobytes()


def cosine_sim(a, b):
    a = np.frombuffer(a, dtype=np.float32)
    b = np.frombuffer(b, dtype=np.float32)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))


# ========================
# STORE DOCUMENT
# ========================
def store_document(filepath, filename, doc_type="text", tags=""):
    if filename.lower().endswith(".pdf"):
        text = extract_text_from_pdf(filepath)
        doc_type = "pdf"
    elif filename.lower().endswith((".png", ".jpg", ".jpeg")):
        text = extract_text_from_image(filepath)
        doc_type = "image"
    else:
        text = extract_text_from_txt(filepath)
        doc_type = "text"

    if not text:
        return 0

    chunks = chunk_text(text)
    conn = _get_conn()
    now = datetime.now().isoformat()

    stored = 0

    for i, chunk in enumerate(chunks):
        emb = get_embedding(chunk)
        doc_id = f"{filename}_{i}_{uuid.uuid4().hex[:8]}"

        conn.execute("""
            INSERT INTO knowledge
            (id, filename, doc_type, tags, uploaded_at, chunk_index, content, embedding)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (doc_id, filename, doc_type, tags, now, i, chunk, emb))

        conn.execute("INSERT INTO knowledge_fts (content) VALUES (?)", (chunk,))
        stored += 1

    conn.commit()
    conn.close()

    return stored


# ========================
# HYBRID SEARCH ENGINE
# ========================
def search_knowledge(query, n_results=5):
    conn = _get_conn()

    query_emb = get_embedding(query)

    rows = conn.execute("""
        SELECT filename, doc_type, tags, content, embedding
        FROM knowledge
    """).fetchall()

    results = []

    for row in rows:
        semantic_score = cosine_sim(query_emb, row["embedding"])

        keyword_score = 0
        if query.lower() in row["content"].lower():
            keyword_score = 0.3

        hybrid_score = (semantic_score * 0.7) + (keyword_score * 0.3)

        results.append({
            "text": row["content"],
            "filename": row["filename"],
            "doc_type": row["doc_type"],
            "tags": row["tags"],
            "score": hybrid_score
        })

    conn.close()

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:n_results]


# ========================
# FORMAT FOR LLM
# ========================
def search_and_format(query, n_results=4):
    chunks = search_knowledge(query, n_results)

    if not chunks:
        return ""

    out = ["## ORA MEMORY CONTEXT\n"]

    for c in chunks:
        out.append(f"[{c['filename']}] (score: {round(c['score'], 2)})")
        out.append(c["text"][:400])

    return "\n".join(out)


# ========================
# LIST DOCS
# ========================
def get_all_documents():
    conn = _get_conn()

    rows = conn.execute("""
        SELECT filename, doc_type, tags, uploaded_at, COUNT(*) as chunks
        FROM knowledge
        GROUP BY filename
    """).fetchall()

    conn.close()

    return [
        dict(row)
        for row in rows
    ]


# ========================
# DELETE DOC
# ========================
def delete_document(filename):
    conn = _get_conn()

    conn.execute("DELETE FROM knowledge WHERE filename=?", (filename,))
    conn.execute("DELETE FROM knowledge_fts WHERE content LIKE ?", (f"%{filename}%",))

    conn.commit()
    conn.close()

    return True