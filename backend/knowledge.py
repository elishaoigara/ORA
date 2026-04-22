import os
import uuid
import json
import hashlib
import sqlite3
from datetime import datetime

UPLOADS_PATH = "uploads"
INDEX_PATH = "ora_index.json"
DB_PATH = "ora_knowledge.db"

os.makedirs(UPLOADS_PATH, exist_ok=True)


# =============================
# DB — separate from main ora.db
# =============================
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_knowledge_db():
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


# Run on import
init_knowledge_db()


# =============================
# INDEX FILE
# =============================
def load_index():
    if os.path.exists(INDEX_PATH):
        try:
            with open(INDEX_PATH, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_index(index):
    with open(INDEX_PATH, "w") as f:
        json.dump(index, f, indent=2)


# =============================
# HASH
# =============================
def get_file_hash(filepath):
    h = hashlib.md5()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()


def is_already_indexed(filepath):
    index = load_index()
    filename = os.path.basename(filepath)
    return (
        filename in index and
        index[filename].get("hash") == get_file_hash(filepath)
    )


# =============================
# TEXT EXTRACTION
# =============================
def extract_text(filepath):
    name = filepath.lower()

    # PDF
    if name.endswith(".pdf"):
        try:
            import PyPDF2
            reader = PyPDF2.PdfReader(filepath)
            pages = [p.extract_text() or "" for p in reader.pages]
            return [p for p in pages if p.strip()], "pdf"
        except Exception as e:
            print("[PDF ERROR]", e)
            return [], "pdf"

    # DOCX — FIX: added docx support (was missing, falling through to text which fails on binary)
    # python-docx installs as 'docx' at runtime — Pylance warning is a false positive
    elif name.endswith(".docx"):
        try:
            import docx  # type: ignore[import-untyped]
            doc = docx.Document(filepath)
            text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
            return [text] if text else [], "text"
        except ImportError:
            # fallback: try reading as zip/xml if python-docx not installed
            try:
                import zipfile
                import xml.etree.ElementTree as ET
                with zipfile.ZipFile(filepath) as z:
                    xml = z.read("word/document.xml")
                root = ET.fromstring(xml)
                ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
                text = " ".join(
                    node.text for node in root.iter(f"{ns}t") if node.text
                )
                return [text] if text else [], "text"
            except Exception as e:
                print("[DOCX FALLBACK ERROR]", e)
                return [], "text"
        except Exception as e:
            print("[DOCX ERROR]", e)
            return [], "text"

    # Image
    elif name.endswith((".png", ".jpg", ".jpeg")):
        try:
            from PIL import Image
            img = Image.open(filepath)
            return [f"Image file: {os.path.basename(filepath)}, size: {img.size}"], "image"
        except Exception as e:
            print("[IMAGE ERROR]", e)
            return [], "image"

    # Plain text / markdown / etc.
    else:
        try:
            with open(filepath, encoding="utf-8", errors="ignore") as f:
                return [f.read()], "text"
        except Exception as e:
            print("[TEXT READ ERROR]", e)
            return [], "text"


# =============================
# CHUNKING
# =============================
def chunk_text(text, size=600, overlap=100):
    chunks = []
    i = 0
    while i < len(text):
        chunks.append(text[i:i + size])
        i += size - overlap
    return [c for c in chunks if len(c.strip()) > 50]


# =============================
# SUMMARY
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
                "content": f"Summarize this document clearly in 2-3 sentences:\n{text[:3000]}"
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
    if os.path.getsize(filepath) > 10 * 1024 * 1024:
        return {"status": "error", "reason": "file too large"}

    if not force and is_already_indexed(filepath):
        return {"status": "skipped", "chunks": 0}

    pages, doc_type = extract_text(filepath)

    if not pages:
        return {"status": "error", "reason": "no extractable text", "chunks": 0}

    delete_document(filename)

    conn = get_conn()
    stored = 0

    # Summary of first pages
    summary_source = "\n".join(pages[:3])
    summary = generate_summary(summary_source, filename)

    if summary:
        conn.execute(
            "INSERT INTO knowledge_fts VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                str(uuid.uuid4()),
                filename,
                doc_type,
                tags,
                "SUMMARY: " + summary,
                "1",
                datetime.now().isoformat(),
            ),
        )
        stored += 1

    # Chunk all pages
    for page in pages:
        for chunk in chunk_text(page):
            conn.execute(
                "INSERT INTO knowledge_fts VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    str(uuid.uuid4()),
                    filename,
                    doc_type,
                    tags,
                    chunk,
                    "0",
                    datetime.now().isoformat(),
                ),
            )
            stored += 1

    conn.commit()
    conn.close()

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
# SEARCH
# =============================
def search_knowledge(query, n_results=5):
    conn = get_conn()
    rows = []

    try:
        # FTS5 match — escape query to avoid syntax errors on special chars
        safe_query = query.replace('"', '""')
        rows = conn.execute(
            """
            SELECT *
            FROM knowledge_fts
            WHERE knowledge_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (safe_query, n_results * 3)
        ).fetchall()
    except sqlite3.OperationalError as e:
        print(f"[FTS ERROR] {e} — falling back to LIKE")
        try:
            rows = conn.execute(
                """
                SELECT *
                FROM knowledge_fts
                WHERE content LIKE ?
                ORDER BY uploaded_at DESC
                LIMIT ?
                """,
                (f"%{query}%", n_results * 3)
            ).fetchall()
        except Exception as e2:
            print(f"[LIKE FALLBACK ERROR] {e2}")

    conn.close()

    results = []
    for r in rows:
        score = 1.0
        if str(r["is_summary"]) == "1":
            score *= 2.0  # boost summaries
        results.append({
            "text": r["content"],
            "filename": r["filename"],
            "score": score
        })

    results.sort(key=lambda x: -x["score"])
    return results[:n_results]


# =============================
# FORMAT FOR CONTEXT
# =============================
def search_and_format(query, n_results=4):
    chunks = search_knowledge(query, n_results)
    if not chunks:
        return ""
    # FIX: was using f-string with dict key inside quotes — broke in Python 3.11
    lines = []
    for c in chunks:
        filename = c["filename"]
        text = c["text"][:300]
        lines.append(f"[{filename}]\n{text}")
    return "\n\n".join(lines)


# =============================
# DOC MANAGEMENT
# =============================
def get_all_documents():
    index = load_index()
    return [{"filename": k, **v} for k, v in index.items()]


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