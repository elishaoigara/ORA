"""
ORA Knowledge — Phase 9 (Pipeline Orchestrator - CLEAN FIXED)
Production-safe ingestion pipeline with correct embeddings API usage.
"""

import os
import json
import hashlib
from datetime import datetime

from knowledge.ingest import load_document, chunk_document
from knowledge.embeddings import store_chunks, delete_source
from knowledge.retrieval import retrieve, format_context
from knowledge.feedback import distill_document, log_query
from config import INDEX_PATH


# ============================================================
# FILE HASH
# ============================================================

def _get_hash(filepath: str) -> str:
    h = hashlib.md5()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()


def _load_index():
    if os.path.exists(INDEX_PATH):
        with open(INDEX_PATH, "r") as f:
            return json.load(f)
    return {}


def _save_index(index):
    with open(INDEX_PATH, "w") as f:
        json.dump(index, f, indent=2)


def _is_already_indexed(filepath, filename):
    index = _load_index()
    file_hash = _get_hash(filepath)

    return (
        filename in index and
        index[filename].get("hash") == file_hash
    )


# ============================================================
# MAIN PIPELINE
# ============================================================

def on_upload(filepath: str, filename: str, tags: str = "", force: bool = False) -> dict:

    start_time = datetime.now()

    # ── 0. size check ─────────────────────────────
    if os.path.getsize(filepath) > 10 * 1024 * 1024:
        return {"status": "error", "reason": "file too large", "chunks": 0}

    # ── 1. dedup ─────────────────────────────────
    if not force and _is_already_indexed(filepath, filename):
        return {"status": "skipped", "reason": "already indexed", "chunks": 0}

    # ── 2. cleanup old version ────────────────────
    delete_source(filename)

    # ── 3. extract ───────────────────────────────
    try:
        pages, doc_type = load_document(filepath)
    except Exception as e:
        return {"status": "error", "reason": f"extract failed: {e}"}

    if not pages:
        return {"status": "error", "reason": "no text extracted"}

    full_text = "\n\n".join(p["text"] for p in pages)

    # ── 4. chunking ───────────────────────────────
    try:
        chunks = chunk_document(pages, filename, doc_type)
    except Exception as e:
        return {"status": "error", "reason": f"chunking failed: {e}"}

    if not chunks:
        return {"status": "error", "reason": "no chunks generated"}

    # ── 5. FIX: attach metadata correctly ─────────
    for c in chunks:
        c["tags"] = tags
        c["source"] = filename
        c["doc_type"] = doc_type

    # ── 6. embed + store ──────────────────────────
    try:
        stored = store_chunks(chunks)
    except Exception as e:
        return {"status": "error", "reason": f"embedding failed: {e}"}

    # ── 7. distillation ───────────────────────────
    summary = ""
    try:
        summary = distill_document(filename, full_text, [])
    except Exception as e:
        print(f"[PIPELINE] distillation failed: {e}")

    # ── 8. telegram notify ────────────────────────
    try:
        from telegram_bot import notify

        msg = f"📄 Document Indexed: {filename}\nChunks: {stored}"

        if summary:
            msg += f"\n\n🧠 Summary:\n{summary[:300]}..."

        notify(msg, is_alert=False)
    except Exception as e:
        print(f"[PIPELINE] notify failed: {e}")

    # ── 9. index update ───────────────────────────
    index = _load_index()
    index[filename] = {
        "hash": _get_hash(filepath),
        "doc_type": doc_type,
        "tags": tags,
        "chunks": stored,
        "summary": summary,
        "indexed_at": datetime.now().isoformat()
    }
    _save_index(index)

    duration = (datetime.now() - start_time).total_seconds()

    print(f"[PIPELINE] COMPLETE: {filename} | {stored} chunks | {duration:.2f}s")

    return {
        "status": "stored",
        "filename": filename,
        "chunks": stored,
        "summary": summary,
        "doc_type": doc_type,
        "time": duration
    }


# ============================================================
# SEARCH API
# ============================================================

def search_and_format(query: str, n_results: int = 4) -> str:
    chunks = retrieve(query, n_results=n_results)

    if not chunks:
        return ""

    try:
        log_query(query, [c.get("chunk_id", "") for c in chunks])
    except Exception:
        pass

    return format_context(chunks)


# ============================================================
# DOC MANAGEMENT
# ============================================================

def get_all_documents():
    index = _load_index()
    return [{"filename": k, **v} for k, v in index.items()]


def delete_document(filename: str):
    delete_source(filename)
    index = _load_index()
    if filename in index:
        del index[filename]
        _save_index(index)
    return True


def store_document(filepath: str, filename: str, tags: str = "", force: bool = False):
    return on_upload(filepath, filename, tags, force)