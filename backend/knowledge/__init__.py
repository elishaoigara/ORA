"""
ORA Knowledge Package
=====================
Replaces the single knowledge.py file with a full intelligence pipeline.

Phases implemented:
  1. Multi-format ingestion  (ingest.py)
  2. Smart semantic chunking (ingest.py)
  3. Embeddings via Groq     (embeddings.py)
  4. Hybrid FTS + vector     (retrieval.py)
  5. Context injection       (retrieval.py → format_context)
  6. Self-improvement loop   (feedback.py)
  7. Knowledge distillation  (feedback.py → distill_document)
  8. Memory connection       (pipeline.py → _notify_upload links to Telegram)
  9. Background pipeline     (pipeline.py → on_upload)

Public API (same as old knowledge.py — drop-in compatible with api.py):
"""

from knowledge.pipeline import (
    store_document,
    get_all_documents,
    delete_document,
    search_and_format,
    on_upload,
    UPLOADS_PATH,
)

from knowledge.retrieval import retrieve, format_context
from knowledge.feedback import record_useful, record_not_useful, get_insights_for_source
from knowledge.embeddings import init_vector_db

__all__ = [
    # Drop-in compatible (used by existing api.py)
    "store_document",
    "get_all_documents",
    "delete_document",
    "search_and_format",
    "UPLOADS_PATH",
    # New capabilities
    "on_upload",
    "retrieve",
    "format_context",
    "record_useful",
    "record_not_useful",
    "get_insights_for_source",
    "init_vector_db",
]