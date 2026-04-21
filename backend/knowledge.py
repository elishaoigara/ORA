import os
import uuid
from datetime import datetime

# ChromaDB for semantic search
import chromadb
from chromadb.config import Settings

# Document processing
import PyPDF2
from PIL import Image

CHROMA_PATH = "ora_memory"
UPLOADS_PATH = "uploads"

# Ensure folders exist
os.makedirs(CHROMA_PATH, exist_ok=True)
os.makedirs(UPLOADS_PATH, exist_ok=True)

# Init ChromaDB
client = chromadb.PersistentClient(path=CHROMA_PATH)
collection = client.get_or_create_collection(
    name="ora_knowledge",
    metadata={"hnsw:space": "cosine"}
)


# -----------------------------
# DOCUMENT PROCESSING
# -----------------------------

def extract_text_from_pdf(filepath):
    try:
        text = ""
        with open(filepath, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                text += page.extract_text() or ""
        return text.strip()
    except Exception as e:
        print(f"[PDF Error] {e}")
        return ""


def extract_text_from_txt(filepath):
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            return f.read().strip()
    except Exception as e:
        print(f"[TXT Error] {e}")
        return ""


def extract_text_from_image(filepath):
    """
    Basic image handling — stores filename and metadata.
    Full OCR can be added later with tesseract.
    """
    try:
        img = Image.open(filepath)
        return f"Image file: {os.path.basename(filepath)} | Size: {img.size} | Mode: {img.mode}"
    except Exception as e:
        return f"Image: {os.path.basename(filepath)}"


def chunk_text(text, chunk_size=500, overlap=50):
    """Split long text into overlapping chunks for better retrieval."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start = end - overlap
    return chunks


# -----------------------------
# STORE DOCUMENT
# -----------------------------

def store_document(filepath, filename, doc_type="text", tags=""):
    """
    Process and store a document in ORA's semantic memory.
    Returns number of chunks stored.
    """
    # Extract text based on type
    if filename.endswith(".pdf"):
        text = extract_text_from_pdf(filepath)
        doc_type = "pdf"
    elif filename.endswith((".png", ".jpg", ".jpeg", ".webp")):
        text = extract_text_from_image(filepath)
        doc_type = "image"
    else:
        text = extract_text_from_txt(filepath)
        doc_type = "text"

    if not text:
        return 0

    # Chunk and store
    chunks = chunk_text(text)
    stored = 0

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
                    "uploaded_at": datetime.now().isoformat()
                }]
            )
            stored += 1
        except Exception as e:
            print(f"[ChromaDB Error] {e}")

    print(f"[ORA Knowledge] Stored {stored} chunks from {filename}")
    return stored


# -----------------------------
# SEARCH KNOWLEDGE
# -----------------------------

def search_knowledge(query, n_results=3):
    """
    Search ORA's semantic memory for relevant context.
    Returns list of relevant text chunks.
    """
    try:
        count = collection.count()
        if count == 0:
            return []

        results = collection.query(
            query_texts=[query],
            n_results=min(n_results, count)
        )

        chunks = []
        if results and results["documents"]:
            for i, doc in enumerate(results["documents"][0]):
                meta = results["metadatas"][0][i] if results["metadatas"] else {}
                chunks.append({
                    "text": doc,
                    "filename": meta.get("filename", "unknown"),
                    "doc_type": meta.get("doc_type", "text"),
                    "tags": meta.get("tags", "")
                })
        return chunks

    except Exception as e:
        print(f"[Search Error] {e}")
        return []


def get_all_documents():
    """List all stored documents."""
    try:
        results = collection.get()
        seen = {}
        for i, meta in enumerate(results["metadatas"]):
            fname = meta.get("filename", "unknown")
            if fname not in seen:
                seen[fname] = {
                    "filename": fname,
                    "doc_type": meta.get("doc_type", "text"),
                    "tags": meta.get("tags", ""),
                    "uploaded_at": meta.get("uploaded_at", ""),
                    "chunks": 0
                }
            seen[fname]["chunks"] += 1
        return list(seen.values())
    except Exception as e:
        print(f"[Docs Error] {e}")
        return []


def delete_document(filename):
    """Delete all chunks of a document."""
    try:
        results = collection.get()
        ids_to_delete = [
            results["ids"][i]
            for i, meta in enumerate(results["metadatas"])
            if meta.get("filename") == filename
        ]
        if ids_to_delete:
            collection.delete(ids=ids_to_delete)
        return len(ids_to_delete)
    except Exception as e:
        print(f"[Delete Error] {e}")
        return 0