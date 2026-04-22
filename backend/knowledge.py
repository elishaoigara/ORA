import os
import sqlite3
import uuid
from datetime import datetime
import re

import PyPDF2
from PIL import Image

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
        CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts
        USING fts5(
            id UNINDEXED,
            filename,
            doc_type,
            tags,
            uploaded_at UNINDEXED,
            chunk_index UNINDEXED,
            content
        );
    """)
    conn.commit()
    conn.close()

_init_kb()

# ========================
# EXTRACTION
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
            return f.read()
    except:
        return ""


def extract_text_from_image(filepath):
    try:
        img = Image.open(filepath)
        return f"Image: {os.path.basename(filepath)} size {img.size}"
    except:
        return ""


# ========================
# CHUNKING
# ========================
def chunk_text(text, size=500, overlap=50):
    chunks = []
    i = 0
    while i < len(text):
        chunks.append(text[i:i+size])
        i += size - overlap
    return [c for c in chunks if c.strip()]


# ========================
# STORE
# ========================
def store_document(filepath, filename, tags=""):
    if filename.endswith(".pdf"):
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

    for i, chunk in enumerate(chunks):
        conn.execute(
            "INSERT INTO knowledge_fts VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                f"{filename}_{i}_{uuid.uuid4().hex[:6]}",
                filename,
                doc_type,
                tags,
                datetime.now().isoformat(),
                i,
                chunk,
            ),
        )

    conn.commit()
    conn.close()
    return len(chunks)


# ========================
# QUERY EXPANSION (FAKE SEMANTIC)
# ========================
SYNONYMS = {
    "salary": ["pay", "income", "wage"],
    "increase": ["raise", "growth", "boost"],
    "contract": ["agreement", "deal"],
    "meeting": ["discussion", "call"],
}

def expand_query(query):
    words = query.lower().split()
    expanded = set(words)

    for w in words:
        if w in SYNONYMS:
            expanded.update(SYNONYMS[w])

    return " ".join(expanded)


# ========================
# SEARCH
# ========================
def search_knowledge(query, n_results=5):
    conn = _get_conn()

    expanded = expand_query(query)

    rows = conn.execute(
        """
        SELECT filename, doc_type, tags, content
        FROM knowledge_fts
        WHERE knowledge_fts MATCH ?
        LIMIT ?
        """,
        (expanded, n_results * 3),
    ).fetchall()

    conn.close()

    results = []
    for r in rows:
        score = 0

        # Boost tag matches
        if r["tags"] and any(t in query for t in r["tags"].split(",")):
            score += 2

        # Boost filename match
        if any(word in r["filename"].lower() for word in query.split()):
            score += 1

        # Basic keyword density
        density = sum(r["content"].lower().count(w) for w in query.split())
        score += density * 0.1

        results.append({
            "text": r["content"],
            "filename": r["filename"],
            "score": score
        })

    # Rerank
    results.sort(key=lambda x: -x["score"])

    return results[:n_results]


# ========================
# LIST
# ========================
def get_all_documents():
    conn = _get_conn()
    rows = conn.execute(
        """
        SELECT filename, doc_type, tags, uploaded_at, COUNT(*) as chunks
        FROM knowledge_fts
        GROUP BY filename
        ORDER BY uploaded_at DESC
        """
    ).fetchall()
    conn.close()

    return [dict(r) for r in rows]


# ========================
# DELETE
# ========================
def delete_document(filename):
    conn = _get_conn()
    conn.execute("DELETE FROM knowledge_fts WHERE filename = ?", (filename,))
    conn.commit()
    conn.close()