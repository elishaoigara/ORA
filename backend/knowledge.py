import os
import json
import uuid
import math
import hashlib
import sqlite3
import re
from datetime import datetime
from pathlib import Path
from collections import Counter

UPLOADS_PATH = "uploads"
KNOWLEDGE_DB = "knowledge.db"
INDEX_PATH = "ora_index.json"

os.makedirs(UPLOADS_PATH, exist_ok=True)


# ─────────────────────────────────────────
# KNOWLEDGE DATABASE
# ─────────────────────────────────────────

def get_knowledge_conn():
    return sqlite3.connect(KNOWLEDGE_DB)


def init_knowledge_db():
    conn = get_knowledge_conn()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS knowledge_chunks (
            id TEXT PRIMARY KEY,
            filename TEXT,
            doc_type TEXT,
            tags TEXT,
            chunk_index INTEGER,
            content TEXT,
            is_summary INTEGER DEFAULT 0,
            uploaded_at TEXT
        )
    ''')
    conn.commit()
    conn.close()


init_knowledge_db()


# ─────────────────────────────────────────
# FILE INDEX
# ─────────────────────────────────────────

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
    if filename in index:
        return index[filename].get("hash") == get_file_hash(filepath)
    return False


# ─────────────────────────────────────────
# TEXT EXTRACTION
# ─────────────────────────────────────────

def extract_from_pdf(filepath):
    try:
        import pdfplumber
        text = ""
        with pdfplumber.open(filepath) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        return text.strip()
    except Exception:
        try:
            import PyPDF2
            text = ""
            with open(filepath, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    text += page.extract_text() or ""
            return text.strip()
        except Exception as e:
            print(f"[PDF Error] {e}")
            return ""


def extract_from_txt(filepath):
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            return f.read().strip()
    except Exception as e:
        print(f"[TXT Error] {e}")
        return ""


def extract_from_image(filepath):
    try:
        from PIL import Image
        img = Image.open(filepath)
        filename = os.path.basename(filepath)
        return (
            f"IMAGE: {filename}\n"
            f"Size: {img.size[0]}x{img.size[1]}px\n"
            f"Mode: {img.mode}"
        )
    except Exception:
        return f"Image: {os.path.basename(filepath)}"


def extract_text(filepath):
    filename = os.path.basename(filepath).lower()
    if filename.endswith(".pdf"):
        return extract_from_pdf(filepath), "pdf"
    elif filename.endswith((".png", ".jpg", ".jpeg", ".webp")):
        return extract_from_image(filepath), "image"
    elif filename.endswith((".md", ".markdown")):
        return extract_from_txt(filepath), "markdown"
    elif filename.endswith(".csv"):
        return extract_from_txt(filepath), "csv"
    elif filename.endswith(".json"):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            return json.dumps(data, indent=2), "json"
        except:
            return extract_from_txt(filepath), "json"
    else:
        return extract_from_txt(filepath), "text"


# ─────────────────────────────────────────
# SMART CHUNKING
# ─────────────────────────────────────────

def smart_chunk(text, chunk_size=600, overlap=100):
    if not text:
        return []
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks = []
    current = ""
    for para in paragraphs:
        if len(current) + len(para) < chunk_size:
            current += para + "\n\n"
        else:
            if current:
                chunks.append(current.strip())
            if len(para) > chunk_size:
                words = para.split()
                sub = ""
                for word in words:
                    if len(sub) + len(word) < chunk_size:
                        sub += word + " "
                    else:
                        if sub:
                            chunks.append(sub.strip())
                        sub = word + " "
                if sub:
                    chunks.append(sub.strip())
                current = ""
            else:
                current = para + "\n\n"
    if current:
        chunks.append(current.strip())
    return [c for c in chunks if len(c) > 50]


# ─────────────────────────────────────────
# TF-IDF SEARCH (no ML models needed)
# ─────────────────────────────────────────

def tokenize(text):
    """Simple tokenizer — lowercase, remove punctuation, split."""
    text = text.lower()
    text = re.sub(r'[^\w\s]', ' ', text)
    tokens = text.split()
    # Remove common stop words
    stopwords = {
        'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
        'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
        'would', 'could', 'should', 'may', 'might', 'shall', 'can',
        'to', 'of', 'in', 'for', 'on', 'with', 'at', 'by', 'from',
        'and', 'or', 'but', 'not', 'this', 'that', 'it', 'its',
        'i', 'my', 'me', 'we', 'our', 'you', 'your', 'he', 'she',
        'they', 'their', 'what', 'which', 'who', 'how', 'when', 'where'
    }
    return [t for t in tokens if t not in stopwords and len(t) > 2]


def tfidf_score(query_tokens, doc_tokens, all_docs_tokens):
    """Calculate TF-IDF relevance score."""
    if not doc_tokens or not query_tokens:
        return 0.0

    doc_counter = Counter(doc_tokens)
    doc_len = len(doc_tokens)
    n_docs = len(all_docs_tokens)
    score = 0.0

    for token in query_tokens:
        # TF: frequency in this doc
        tf = doc_counter.get(token, 0) / doc_len if doc_len > 0 else 0

        # IDF: how rare across all docs
        docs_with_token = sum(
            1 for doc in all_docs_tokens if token in doc
        )
        idf = math.log((n_docs + 1) / (docs_with_token + 1)) + 1

        score += tf * idf

    return round(score, 4)


def search_knowledge(query, n_results=5, tags_filter=None):
    """
    Search knowledge base using TF-IDF.
    No ML models, no GPU, minimal memory.
    """
    try:
        conn = get_knowledge_conn()
        c = conn.cursor()

        if tags_filter:
            c.execute(
                "SELECT id, filename, doc_type, tags, content, is_summary "
                "FROM knowledge_chunks WHERE tags LIKE ?",
                (f"%{tags_filter}%",)
            )
        else:
            c.execute(
                "SELECT id, filename, doc_type, tags, content, is_summary "
                "FROM knowledge_chunks"
            )

        rows = c.fetchall()
        conn.close()

        if not rows:
            return []

        query_tokens = tokenize(query)
        all_docs_tokens = [tokenize(row[4]) for row in rows]

        scored = []
        for i, row in enumerate(rows):
            doc_tokens = all_docs_tokens[i]
            score = tfidf_score(query_tokens, doc_tokens, all_docs_tokens)

            # Boost summaries
            if row[5] == 1:
                score *= 1.5

            if score > 0:
                scored.append({
                    "text": row[4],
                    "filename": row[1],
                    "doc_type": row[2],
                    "tags": row[3] or "",
                    "is_summary": bool(row[5]),
                    "relevance": min(score, 1.0)
                })

        scored.sort(key=lambda x: (-x["is_summary"], -x["relevance"]))
        return scored[:n_results]

    except Exception as e:
        print(f"[Search Error] {e}")
        return []


def search_and_format(query, n_results=4):
    """Format search results for context injection."""
    chunks = search_knowledge(query, n_results=n_results)
    if not chunks:
        return ""

    lines = ["## Relevant knowledge from your files:"]
    seen_files = set()

    for c in chunks:
        fname = c["filename"]
        prefix = "SUMMARY" if c["is_summary"] else "EXCERPT"
        relevance_pct = int(c["relevance"] * 100)

        if fname not in seen_files:
            lines.append(f"\n**[{fname}]** (relevance: {relevance_pct}%)")
            seen_files.add(fname)

        lines.append(f"{prefix}: {c['text'][:400]}")

    return "\n".join(lines)


# ─────────────────────────────────────────
# DOCUMENT SUMMARY
# ─────────────────────────────────────────

def generate_summary(text, filename):
    try:
        from config import GROQ_API_KEY
        from groq import Groq
        if not GROQ_API_KEY or len(text) < 100:
            return None
        client = Groq(api_key=GROQ_API_KEY)
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{
                "role": "user",
                "content": (
                    f"Summarize in 3-5 sentences. "
                    f"Focus on key facts and decisions. "
                    f"File: {filename}\n\n{text[:3000]}"
                )
            }],
            max_tokens=200,
            temperature=0.3
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[Summary Error] {e}")
        return None


# ─────────────────────────────────────────
# STORE DOCUMENT
# ─────────────────────────────────────────

def store_document(filepath, filename, tags="", force=False):
    if not force and is_already_indexed(filepath):
        return {"status": "skipped", "reason": "already indexed", "chunks": 0}

    text, doc_type = extract_text(filepath)
    if not text:
        return {"status": "error", "reason": "no text extracted", "chunks": 0}

    # Remove old version
    delete_document(filename)

    # Generate summary
    print(f"[Knowledge] Generating summary for {filename}...")
    summary = generate_summary(text, filename)

    conn = get_knowledge_conn()
    c = conn.cursor()
    stored = 0

    # Store summary
    if summary:
        c.execute(
            "INSERT INTO knowledge_chunks "
            "(id, filename, doc_type, tags, chunk_index, content, is_summary, uploaded_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                f"SUMMARY_{filename}_{uuid.uuid4().hex[:8]}",
                filename, doc_type, tags, -1,
                f"DOCUMENT SUMMARY: {summary}",
                1, datetime.now().isoformat()
            )
        )
        stored += 1

    # Store chunks
    chunks = smart_chunk(text)
    print(f"[Knowledge] Indexing {len(chunks)} chunks from {filename}...")

    for i, chunk in enumerate(chunks):
        c.execute(
            "INSERT INTO knowledge_chunks "
            "(id, filename, doc_type, tags, chunk_index, content, is_summary, uploaded_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                f"{filename}_{i}_{uuid.uuid4().hex[:8]}",
                filename, doc_type, tags, i,
                chunk, 0, datetime.now().isoformat()
            )
        )
        stored += 1

    conn.commit()
    conn.close()

    # Update index
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

    print(f"[Knowledge] ✓ {filename} → {stored} chunks")
    return {
        "status": "stored",
        "filename": filename,
        "doc_type": doc_type,
        "chunks": stored,
        "summary": summary or "No summary generated"
    }


# ─────────────────────────────────────────
# DOCUMENT MANAGEMENT
# ─────────────────────────────────────────

def get_all_documents():
    index = load_index()
    docs = []
    for filename, meta in index.items():
        docs.append({
            "filename": filename,
            "doc_type": meta.get("doc_type", "text"),
            "tags": meta.get("tags", ""),
            "chunks": meta.get("chunks", 0),
            "summary": meta.get("summary", ""),
            "indexed_at": meta.get("indexed_at", "")
        })
    docs.sort(key=lambda x: x["indexed_at"], reverse=True)
    return docs


def delete_document(filename):
    conn = get_knowledge_conn()
    c = conn.cursor()
    c.execute("DELETE FROM knowledge_chunks WHERE filename=?", (filename,))
    deleted = c.rowcount
    conn.commit()
    conn.close()

    index = load_index()
    if filename in index:
        del index[filename]
        save_index(index)

    return deleted


def get_document_summary(filename):
    index = load_index()
    if filename in index:
        return index[filename].get("summary", "No summary available")
    return "Document not found"


def reindex_all():
    results = []
    for filename in os.listdir(UPLOADS_PATH):
        filepath = os.path.join(UPLOADS_PATH, filename)
        if os.path.isfile(filepath):
            result = store_document(filepath, filename, force=True)
            results.append(result)
    return results


# ─────────────────────────────────────────
# FILE WATCHER
# ─────────────────────────────────────────

def start_file_watcher():
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler

        class UploadHandler(FileSystemEventHandler):
            def on_created(self, event):
                if not event.is_directory:
                    filepath = event.src_path
                    filename = os.path.basename(filepath)
                    if filename.startswith(".") or filename.endswith(".tmp"):
                        return
                    print(f"[Watcher] New file: {filename}")
                    import time
                    time.sleep(1)
                    store_document(filepath, filename)

        observer = Observer()
        observer.schedule(UploadHandler(), UPLOADS_PATH, recursive=False)
        observer.start()
        print(f"[Watcher] Watching {UPLOADS_PATH}...")
        return observer
    except Exception as e:
        print(f"[Watcher] Skipped: {e}")
        return None