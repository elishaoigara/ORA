import os
import uuid
import json
import hashlib
import sqlite3
from datetime import datetime

from PIL import Image

UPLOADS_PATH = "uploads"
INDEX_PATH = "ora_index.json"
DB_PATH = "ora_knowledge.db"

os.makedirs(UPLOADS_PATH, exist_ok=True)

# =============================
# DATABASE INIT (SQLite FTS5)
# =============================
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts
        USING fts5(
            id,
            filename,
            doc_type,
            tags,
            content,
            is_summary,
            uploaded_at
        )
    """)
    conn.commit()
    conn.close()


init_db()

# =============================
# FILE INDEX
# =============================
def load_index():
    if os.path.exists(INDEX_PATH):
        return json.load(open(INDEX_PATH))
    return {}


def save_index(index):
    json.dump(index, open(INDEX_PATH, "w"), indent=2)


def get_file_hash(filepath):
    h = hashlib.md5()
    with open(filepath, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def is_already_indexed(filepath):
    index = load_index()
    filename = os.path.basename(filepath)
    return filename in index and index[filename]["hash"] == get_file_hash(filepath)


# =============================
# EXTRACTION
# =============================
def extract_text(filepath):
    name = filepath.lower()

    if name.endswith(".pdf"):
        try:
            import PyPDF2
            text = ""
            with open(filepath, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                for p in reader.pages:
                    text += p.extract_text() or ""
            return text, "pdf"
        except:
            return "", "pdf"

    elif name.endswith((".png", ".jpg", ".jpeg")):
        try:
            img = Image.open(filepath)
            return f"Image {img.size}", "image"
        except:
            return "", "image"

    else:
        try:
            return open(filepath, encoding="utf-8", errors="ignore").read(), "text"
        except:
            return "", "text"


# =============================
# CHUNKING
# =============================
def chunk_text(text, size=600, overlap=100):
    chunks = []
    i = 0
    while i < len(text):
        chunks.append(text[i:i+size])
        i += size - overlap
    return [c for c in chunks if len(c.strip()) > 50]


# =============================
# SUMMARY (UNCHANGED)
# =============================
def generate_summary(text, filename):
    try:
        from config import GROQ_API_KEY
        from groq import Groq

        if not GROQ_API_KEY or len(text) < 100:
            return None

        client = Groq(api_key=GROQ_API_KEY)

        res = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{
                "role": "user",
                "content": f"Summarize this:\n{text[:3000]}"
            }],
            max_tokens=150
        )

        return res.choices[0].message.content.strip()
    except:
        return None


# =============================
# STORE DOCUMENT
# =============================
def store_document(filepath, filename, tags="", force=False):

    if not force and is_already_indexed(filepath):
        return {"status": "skipped", "chunks": 0}

    text, doc_type = extract_text(filepath)
    if not text:
        return {"status": "error", "chunks": 0}

    delete_document(filename)

    conn = get_conn()

    stored = 0

    # SUMMARY
    summary = generate_summary(text, filename)
    if summary:
        conn.execute(
            "INSERT INTO knowledge_fts VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                str(uuid.uuid4()),
                filename,
                doc_type,
                tags,
                "SUMMARY: " + summary,
                1,
                datetime.now().isoformat(),
            ),
        )
        stored += 1

    # CHUNKS
    chunks = chunk_text(text)

    for chunk in chunks:
        conn.execute(
            "INSERT INTO knowledge_fts VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                str(uuid.uuid4()),
                filename,
                doc_type,
                tags,
                chunk,
                0,
                datetime.now().isoformat(),
            ),
        )
        stored += 1

    conn.commit()
    conn.close()

    # UPDATE INDEX
    index = load_index()
    index[filename] = {
        "hash": get_file_hash(filepath),
        "doc_type": doc_type,
        "tags": tags,
        "chunks": stored,
        "summary": summary or "",
        "indexed_at": datetime.now().isoformat()
    }
    save_index(index)

    return {"status": "stored", "chunks": stored}


# =============================
# SEARCH (SMART LIGHTWEIGHT)
# =============================
def search_knowledge(query, n_results=5):
    conn = get_conn()

    rows = conn.execute(
        """
        SELECT *, rank
        FROM knowledge_fts
        WHERE knowledge_fts MATCH ?
        ORDER BY rank
        LIMIT ?
        """,
        (query, n_results * 3)
    ).fetchall()

    conn.close()

    results = []
    for r in rows:
        score = 1.0 / (r["rank"] + 1)

        if r["is_summary"]:
            score += 1  # boost summaries

        results.append({
            "text": r["content"],
            "filename": r["filename"],
            "score": score
        })

    results.sort(key=lambda x: -x["score"])
    return results[:n_results]


# =============================
# FORMAT FOR AI
# =============================
def search_and_format(query, n_results=4):
    chunks = search_knowledge(query, n_results)

    if not chunks:
        return ""

    lines = ["## Relevant knowledge:\n"]

    for c in chunks:
        lines.append(f"[{c['filename']}] {c['text'][:300]}")

    return "\n".join(lines)


# =============================
# DOC MANAGEMENT
# =============================
def get_all_documents():
    index = load_index()
    return [
        {
            "filename": k,
            **v
        }
        for k, v in index.items()
    ]


def delete_document(filename):
    conn = get_conn()
    conn.execute("DELETE FROM knowledge_fts WHERE filename = ?", (filename,))
    conn.commit()
    conn.close()

    index = load_index()
    if filename in index:
        del index[filename]
        save_index(index)

    return True