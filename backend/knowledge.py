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
        with open(INDEX_PATH, "r") as f:
            return json.load(f)
    return {}


def save_index(index):
    with open(INDEX_PATH, "w") as f:
        json.dump(index, f, indent=2)


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
# EXTRACTION (STREAMING)
# =============================
def extract_text(filepath):
    name = filepath.lower()

    # --- PDF (STREAMING) ---
    if name.endswith(".pdf"):
        try:
            import PyPDF2
            reader = PyPDF2.PdfReader(filepath)

            def page_generator():
                for p in reader.pages:
                    yield (p.extract_text() or "")

            return page_generator(), "pdf"

        except Exception as e:
            print("[PDF ERROR]", e)
            return None, "pdf"

    # --- IMAGE ---
    elif name.endswith((".png", ".jpg", ".jpeg")):
        try:
            img = Image.open(filepath)
            return f"Image {img.size}", "image"
        except:
            return "", "image"

    # --- TEXT ---
    else:
        try:
            with open(filepath, encoding="utf-8", errors="ignore") as f:
                return f.read(), "text"
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
# SUMMARY (SAFE)
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
                "content": f"Summarize this document:\n{text[:3000]}"
            }],
            max_tokens=150
        )

        return res.choices[0].message.content.strip()
    except Exception as e:
        print("[SUMMARY ERROR]", e)
        return None


# =============================
# STORE DOCUMENT
# =============================
def store_document(filepath, filename, tags="", force=False):

    # --- FILE SIZE PROTECTION ---
    if os.path.getsize(filepath) > 10 * 1024 * 1024:
        return {"status": "error", "reason": "file too large"}

    if not force and is_already_indexed(filepath):
        return {"status": "skipped", "chunks": 0}

    text, doc_type = extract_text(filepath)
    if not text:
        return {"status": "error", "chunks": 0}

    delete_document(filename)

    conn = get_conn()
    stored = 0

    # =============================
    # SUMMARY (SAFE SAMPLE ONLY)
    # =============================
    summary_text = ""

    if doc_type == "pdf":
        for i, page in enumerate(text):
            summary_text += page
            if i >= 3:  # only first 4 pages
                break
    else:
        summary_text = text[:3000]

    summary = generate_summary(summary_text, filename)

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

    # =============================
    # CHUNKING + INSERT (STREAMING)
    # =============================
    if doc_type == "pdf":
        for page in text:
            chunks = chunk_text(page)
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
    else:
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

    # =============================
    # UPDATE INDEX
    # =============================
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
# SEARCH (FTS5 + BM25)
# =============================
def search_knowledge(query, n_results=5):
    conn = get_conn()

    rows = conn.execute(
        """
        SELECT *, bm25(knowledge_fts) as rank
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
            score += 1

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
# DOCUMENT MANAGEMENT
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