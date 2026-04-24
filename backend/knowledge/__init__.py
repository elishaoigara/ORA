"""
ORA Knowledge Package
=====================

Production-ready RAG pipeline:
- Ingestion (PDF/DOCX/TXT/OCR)
- Semantic chunking
- Embeddings (local sentence-transformers or Groq hybrid)
- Hybrid retrieval (FTS + vector)
- Context formatting
- Feedback loop
- Document distillation
- Background pipeline orchestration

Drop-in replacement for legacy knowledge.py
"""

# ============================================================
# PIPELINE (UPLOAD + INDEXING)
# ============================================================

from knowledge.pipeline import (
    on_upload,
    store_document,
    get_all_documents,
    delete_document,
    UPLOADS_PATH,
)

# ============================================================
# RETRIEVAL (RAG CORE)
# ============================================================

from knowledge.retrieval import (
    retrieve,
    format_context,
    search_and_format,
)

# ============================================================
# LEARNING LOOP (SELF IMPROVEMENT)
# ============================================================

from knowledge.feedback import (
    log_query,
    record_useful,
    record_not_useful,
    auto_signal_from_conversation,
    get_top_chunks_by_feedback,
    get_insights_for_source,
)

# ============================================================
# EMBEDDINGS / VECTOR DB
# ============================================================

from knowledge.embeddings import (
    init_vector_db,
    vector_search,
    embed_text,
)

# ============================================================
# PUBLIC API (STABLE INTERFACE)
# ============================================================

__all__ = [
    # ingestion
    "on_upload",
    "store_document",
    "get_all_documents",
    "delete_document",
    "UPLOADS_PATH",

    # retrieval
    "retrieve",
    "search_and_format",
    "format_context",

    # learning
    "log_query",
    "record_useful",
    "record_not_useful",
    "auto_signal_from_conversation",
    "get_top_chunks_by_feedback",
    "get_insights_for_source",

    # embeddings
    "init_vector_db",
    "vector_search",
    "embed_text",
]