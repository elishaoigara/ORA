"""
ORA Knowledge Package (STABLE)
"""

# ── Pipeline (upload + indexing) ──────────────────────────────
from knowledge.pipeline import (
    on_upload,
    store_document,
    get_all_documents,
    delete_document,
)

# ── Retrieval (RAG core) ──────────────────────────────────────
from knowledge.retrieval import (
    retrieve,
    format_context,
    search_and_format,   # ✅ ONLY defined here
)

# ── Learning loop ─────────────────────────────────────────────
from knowledge.feedback import (
    log_query,
    record_useful,
    record_not_useful,
    auto_signal_from_conversation,
    get_top_chunks_by_feedback,
    get_insights_for_source,
)

# ── Embeddings / vector DB ────────────────────────────────────
from knowledge.embeddings import (
    init_vector_db,
    vector_search,
    embed_text,
)

__all__ = [
    # ingestion
    "on_upload",
    "store_document",
    "get_all_documents",
    "delete_document",

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