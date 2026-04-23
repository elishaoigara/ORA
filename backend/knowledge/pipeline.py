"""
ORA Knowledge — Phase 9 (Pipeline Orchestrator)
The single entry point for all document operations.

on_upload() triggers the full pipeline:
  Extract → Chunk → Embed → Store → Distill → Notify

All other modules (ingest, embeddings, retrieval, feedback)
are wired together here.
"""

import os
import json
import hashlib
import sqlite3
from datetime import datetime

from knowledge.ingest import load_document, chunk_document
from knowledge.embeddings import init_vector_db, store_chunks, delete_source
from knowledge.retrieval import retrieve, format_context
from knowledge.feedback import distill_document, log_query

DB_PATH = "ora_knowledge.db"
INDEX_PATH = "ora_index.json"
UPLOADS_PATH = "uploads"

os.makedirs(UPLOADS_PATH, exist_ok=True)

# Initialize DB tables on import
init_vector_db()


# ============================================================
# FILE HASH (DEDUP)
# ============================================================

def _get_hash(filepath: str) -> str:
    h = hashlib.md5()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()


def _load_index() -> dict:
    if os.path.exists(INDEX_PATH):
        with open(INDEX_PATH, "r") as f:
            return json.load(f)
    return {}


def _save_index(index: dict):
    with open(INDEX_PATH, "w") as f:
        json.dump(index, f, indent=2)


def _is_already_indexed(filepath: str, filename: str) -> bool:
    index = _load_index()
    return (
        filename in index and
        index[filename].get("hash") == _get_hash(filepath)
    )


# ============================================================
# PHASE 9 — MAIN UPLOAD PIPELINE
# ============================================================

def on_upload(filepath: str, filename: str, tags: str = "", force: bool = False) -> dict:
    """
    Full ingestion pipeline triggered on file upload.

    Steps:
      1. Dedup check
      2. Extract text (multi-format)
      3. Smart semantic chunking
      4. Embed + store chunks
      5. Distill insights + summary
      6. Notify via Telegram
      7. Update index

    Returns: { status, chunks, summary, filename }
    """

    # ── 0. Size check ──────────────────────────────────────
    if os.path.getsize(filepath) > 10 * 1024 * 1024:
        return {"status": "error", "reason": "file too large (10MB max)", "chunks": 0}

    # ── 1. Dedup check ─────────────────────────────────────
    if not force and _is_already_indexed(filepath, filename):
        return {"status": "skipped", "reason": "already indexed", "chunks": 0}

    # ── 2. Remove old version ──────────────────────────────
    delete_source(filename)

    # ── 3. Extract ─────────────────────────────────────────
    print(f"[PIPELINE] Extracting: {filename}")
    pages, doc_type = load_document(filepath)

    if not pages:
        return {"status": "error", "reason": "no extractable text", "chunks": 0}

    full_text = "\n\n".join(p["text"] for p in pages)

    # ── 4. Smart chunking ──────────────────────────────────
    print(f"[PIPELINE] Chunking: {filename} ({len(pages)} pages)")
    chunks = chunk_document(pages, filename, doc_type)

    if not chunks:
        return {"status": "error", "reason": "chunking produced no output", "chunks": 0}

    # ── 5. Embed + store ───────────────────────────────────
    print(f"[PIPELINE] Embedding + storing {len(chunks)} chunks...")
    stored = store_chunks(chunks, tags=tags)

    # Collect chunk IDs for distillation linking
    chunk_ids = [c.get("chunk_id", "") for c in chunks]

    # ── 6. Distill (summary + insights) ───────────────────
    print(f"[PIPELINE] Distilling insights...")
    summary = distill_document(filename, full_text, chunk_ids)

    # ── 7. Notify via Telegram ─────────────────────────────
    _notify_upload(filename, stored, summary)

    # ── 8. Update index ────────────────────────────────────
    index = _load_index()
    index[filename] = {
        "hash": _get_hash(filepath),
        "doc_type": doc_type,
        "tags": tags,
        "chunks": stored,
        "summary": summary or "",
        "indexed_at": datetime.now().isoformat()
    }
    _save_index(index)

    print(f"[PIPELINE] Complete: {filename} → {stored} chunks")

    return {
        "status": "stored",
        "filename": filename,
        "chunks": stored,
        "summary": summary or "",
        "doc_type": doc_type
    }


def _notify_upload(filename: str, chunks: int, summary: str):
    """Send Telegram notification after successful indexing."""
    try:
        from telegram_bot import notify

        msg = f"📄 *Document Indexed*\n`{filename}`\n{chunks} chunks stored."

        if summary:
            # Trim summary for Telegram
            short_summary = summary[:300] + "..." if len(summary) > 300 else summary
            msg += f"\n\n🧠 *ORA Summary*\n{short_summary}"

        notify(msg, is_alert=False)
    except Exception as e:
        print(f"[PIPELINE] Telegram notify failed: {e}")


# ============================================================
# SEARCH — PUBLIC API
# ============================================================

def search_and_format(query: str, n_results: int = 4) -> str:
    """
    Drop-in replacement for the old knowledge.search_and_format().
    Used by api.py chat endpoint.

    Runs full hybrid retrieval and formats context for the LLM.
    Also logs the query for feedback loop.
    """
    chunks = retrieve(query, n_results=n_results)

    if not chunks:
        return ""

    # Log for self-improvement
    chunk_ids = [c.get("chunk_id", "") for c in chunks]
    log_query(query, chunk_ids)

    return format_context(chunks)


# ============================================================
# DOCUMENT MANAGEMENT — PUBLIC API
# ============================================================

def get_all_documents() -> list[dict]:
    """Return all indexed documents from the index file."""
    index = _load_index()
    return [{"filename": k, **v} for k, v in index.items()]


def delete_document(filename: str) -> bool:
    """Remove document from chunks table, FTS, insights, and index."""
    delete_source(filename)
    index = _load_index()
    if filename in index:
        del index[filename]
        _save_index(index)
    return True


def store_document(filepath: str, filename: str, tags: str = "", force: bool = False) -> dict:
    """
    Compatibility wrapper — same signature as old knowledge.store_document().
    Calls the full pipeline.
    """
    return on_upload(filepath, filename, tags=tags, force=force)