import os
import uuid
import json
import hashlib
from datetime import datetime
from pathlib import Path

import chromadb
from PIL import Image

CHROMA_PATH = "ora_memory"
UPLOADS_PATH = "uploads"
INDEX_PATH = "ora_index.json"  # tracks what's been indexed

os.makedirs(CHROMA_PATH, exist_ok=True)
os.makedirs(UPLOADS_PATH, exist_ok=True)

# Init ChromaDB
chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
collection = chroma_client.get_or_create_collection(
    name="ora_knowledge",
    metadata={"hnsw:space": "cosine"}
)


# -----------------------------
# FILE INDEX (prevents duplicates)
# -----------------------------

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
    current_hash = get_file_hash(filepath)
    if filename in index:
        return index[filename].get("hash") == current_hash
    return False


# -----------------------------
# TEXT EXTRACTION
# -----------------------------

def extract_from_pdf(filepath):
    """Extract text from PDF using pdfplumber (best quality)."""
    try:
        import pdfplumber
        text = ""
        with pdfplumber.open(filepath) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"

            # Also extract tables
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    for row in table:
                        clean_row = [str(cell or "") for cell in row]
                        text += " | ".join(clean_row) + "\n"
        return text.strip()
    except ImportError:
        # Fallback to PyPDF2
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
    except Exception as e:
        print(f"[PDF Error] {e}")
        return ""


def extract_from_txt(filepath):
    """Extract text from txt, md, csv files."""
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            return f.read().strip()
    except Exception as e:
        print(f"[TXT Error] {e}")
        return ""


def extract_from_image(filepath):
    """
    Store image metadata. OCR can be added later.
    For now ORA knows the image exists and its properties.
    """
    try:
        img = Image.open(filepath)
        filename = os.path.basename(filepath)
        return (
            f"IMAGE_FILE: {filename}\n"
            f"Dimensions: {img.size[0]}x{img.size[1]}px\n"
            f"Mode: {img.mode}\n"
            f"Format: {img.format}\n"
            f"Uploaded: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )
    except Exception as e:
        return f"Image file: {os.path.basename(filepath)}"


def extract_text(filepath):
    """Auto-detect file type and extract text."""
    filename = os.path.basename(filepath).lower()

    if filename.endswith(".pdf"):
        return extract_from_pdf(filepath), "pdf"
    elif filename.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
        return extract_from_image(filepath), "image"
    elif filename.endswith((".csv",)):
        return extract_from_txt(filepath), "csv"
    elif filename.endswith((".md", ".markdown")):
        return extract_from_txt(filepath), "markdown"
    elif filename.endswith((".json",)):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            return json.dumps(data, indent=2), "json"
        except:
            return extract_from_txt(filepath), "json"
    else:
        return extract_from_txt(filepath), "text"


# -----------------------------
# SMART CHUNKING
# -----------------------------

def smart_chunk(text, chunk_size=600, overlap=100):
    """
    Chunk text intelligently — prefer breaking at paragraph
    boundaries rather than mid-sentence.
    """
    if not text:
        return []

    # Try to split on paragraphs first
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    chunks = []
    current = ""

    for para in paragraphs:
        if len(current) + len(para) < chunk_size:
            current += para + "\n\n"
        else:
            if current:
                chunks.append(current.strip())
            # If paragraph itself is too long, split it
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

    return [c for c in chunks if len(c) > 50]  # filter tiny chunks


# -----------------------------
# GENERATE DOCUMENT SUMMARY
# -----------------------------

def generate_summary(text, filename):
    """
    Generate a brief summary of a document using Groq.
    This summary is stored as a high-importance chunk.
    """
    try:
        from config import GROQ_API_KEY
        from groq import Groq

        if not GROQ_API_KEY or len(text) < 100:
            return None

        client = Groq(api_key=GROQ_API_KEY)
        sample = text[:3000]  # first 3000 chars

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{
                "role": "user",
                "content": (
                    f"Summarize this document in 3-5 sentences. "
                    f"Focus on key facts, decisions, or information. "
                    f"File: {filename}\n\n{sample}"
                )
            }],
            max_tokens=200,
            temperature=0.3
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[Summary Error] {e}")
        return None


# -----------------------------
# STORE DOCUMENT
# -----------------------------

def store_document(filepath, filename, tags="", force=False):
    """
    Process and store a document in ORA's semantic memory.
    - Skips if file already indexed with same content (unless force=True)
    - Generates AI summary
    - Chunks intelligently
    - Returns dict with status and chunk count
    """
    # Check for duplicates
    if not force and is_already_indexed(filepath):
        return {"status": "skipped", "reason": "already indexed", "chunks": 0}

    # Extract text
    text, doc_type = extract_text(filepath)

    if not text:
        return {"status": "error", "reason": "no text extracted", "chunks": 0}

    # Delete old version if re-indexing
    delete_document(filename)

    # Generate AI summary first
    print(f"[ORA Knowledge] Generating summary for {filename}...")
    summary = generate_summary(text, filename)

    stored = 0
    file_hash = get_file_hash(filepath)

    # Store summary as priority chunk
    if summary:
        summary_id = f"SUMMARY_{filename}_{uuid.uuid4().hex[:8]}"
        try:
            collection.add(
                documents=[f"DOCUMENT SUMMARY: {summary}"],
                ids=[summary_id],
                metadatas=[{
                    "filename": filename,
                    "doc_type": doc_type,
                    "chunk_index": -1,  # -1 = summary
                    "tags": tags,
                    "is_summary": "true",
                    "uploaded_at": datetime.now().isoformat()
                }]
            )
            stored += 1
        except Exception as e:
            print(f"[Summary Store Error] {e}")

    # Chunk and store
    chunks = smart_chunk(text)
    print(f"[ORA Knowledge] Indexing {len(chunks)} chunks from {filename}...")

    for i, chunk in enumerate(chunks):
        doc_id = f"{filename}_{i}_{uuid.uuid4().hex[:8]}"
        try:
            collection.add(
                documents=[chunk],
                ids=[doc_id],
                metadatas=[{
                    "filename": filename,
                    "doc_type": doc_type,
                    "chunk_index": i,
                    "tags": tags,
                    "is_summary": "false",
                    "uploaded_at": datetime.now().isoformat()
                }]
            )
            stored += 1
        except Exception as e:
            print(f"[ChromaDB Error] {e}")

    # Update index
    index = load_index()
    index[filename] = {
        "hash": file_hash,
        "doc_type": doc_type,
        "tags": tags,
        "chunks": stored,
        "summary": summary or "",
        "indexed_at": datetime.now().isoformat()
    }
    save_index(index)

    print(f"[ORA Knowledge] ✓ {filename} → {stored} chunks stored")
    return {
        "status": "stored",
        "filename": filename,
        "doc_type": doc_type,
        "chunks": stored,
        "summary": summary or "No summary generated"
    }


# -----------------------------
# SEARCH KNOWLEDGE
# -----------------------------

def search_knowledge(query, n_results=5, tags_filter=None):
    """
    Semantic search across all indexed documents.
    Summaries are weighted higher in results.
    Returns ranked list of relevant chunks with source info.
    """
    try:
        count = collection.count()
        if count == 0:
            return []

        where = None
        if tags_filter:
            where = {"tags": {"$contains": tags_filter}}

        results = collection.query(
            query_texts=[query],
            n_results=min(n_results, count),
            where=where,
            include=["documents", "metadatas", "distances"]
        )

        chunks = []
        if results and results["documents"]:
            for i, doc in enumerate(results["documents"][0]):
                meta = results["metadatas"][0][i] if results["metadatas"] else {}
                distance = results["distances"][0][i] if results["distances"] else 1.0
                relevance = round(1 - distance, 3)

                chunks.append({
                    "text": doc,
                    "filename": meta.get("filename", "unknown"),
                    "doc_type": meta.get("doc_type", "text"),
                    "tags": meta.get("tags", ""),
                    "is_summary": meta.get("is_summary") == "true",
                    "relevance": relevance
                })

        # Sort by relevance, summaries first
        chunks.sort(key=lambda x: (not x["is_summary"], -x["relevance"]))
        return chunks

    except Exception as e:
        print(f"[Search Error] {e}")
        return []


def search_and_format(query, n_results=4):
    """
    Search and format results for injection into ORA's prompt.
    Returns formatted string ready for context injection.
    """
    chunks = search_knowledge(query, n_results=n_results)
    if not chunks:
        return ""

    lines = ["## Relevant knowledge from your files:"]
    seen_files = set()

    for c in chunks:
        fname = c["filename"]
        prefix = "📋 SUMMARY" if c["is_summary"] else "📄 EXCERPT"
        relevance_pct = int(c["relevance"] * 100)

        if fname not in seen_files:
            lines.append(f"\n**[{fname}]** (relevance: {relevance_pct}%)")
            seen_files.add(fname)

        lines.append(f"{prefix}: {c['text'][:400]}")

    return "\n".join(lines)


# -----------------------------
# DOCUMENT MANAGEMENT
# -----------------------------

def get_all_documents():
    """List all stored documents with metadata from index."""
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
    """Delete all chunks of a document from ChromaDB and index."""
    deleted = 0
    try:
        results = collection.get()
        ids_to_delete = [
            results["ids"][i]
            for i, meta in enumerate(results["metadatas"])
            if meta.get("filename") == filename
        ]
        if ids_to_delete:
            collection.delete(ids=ids_to_delete)
            deleted = len(ids_to_delete)
    except Exception as e:
        print(f"[Delete Error] {e}")

    # Remove from index
    index = load_index()
    if filename in index:
        del index[filename]
        save_index(index)

    return deleted


def get_document_summary(filename):
    """Get the AI-generated summary of a specific document."""
    index = load_index()
    if filename in index:
        return index[filename].get("summary", "No summary available")
    return "Document not found"


def reindex_all():
    """
    Re-index all files in the uploads folder.
    Useful for rebuilding the knowledge base.
    """
    results = []
    for filename in os.listdir(UPLOADS_PATH):
        filepath = os.path.join(UPLOADS_PATH, filename)
        if os.path.isfile(filepath):
            result = store_document(filepath, filename, force=True)
            results.append(result)
    return results


# -----------------------------
# AUTO FILE WATCHER
# -----------------------------

def start_file_watcher():
    """
    Watch the uploads folder for new files.
    Auto-indexes anything dropped in.
    """
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler

        class UploadHandler(FileSystemEventHandler):
            def on_created(self, event):
                if not event.is_directory:
                    filepath = event.src_path
                    filename = os.path.basename(filepath)
                    # Skip temp files
                    if filename.startswith(".") or filename.endswith(".tmp"):
                        return
                    print(f"[ORA Watcher] New file detected: {filename}")
                    import time
                    time.sleep(1)  # Wait for file to finish writing
                    store_document(filepath, filename)

        observer = Observer()
        observer.schedule(UploadHandler(), UPLOADS_PATH, recursive=False)
        observer.start()
        print(f"[ORA Watcher] Watching {UPLOADS_PATH} for new files...")
        return observer
    except ImportError:
        print("[ORA Watcher] watchdog not installed, file watching disabled")
        return None
    except Exception as e:
        print(f"[ORA Watcher Error] {e}")
        return None