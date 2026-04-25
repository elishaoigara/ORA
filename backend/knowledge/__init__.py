"""
ORA Knowledge Package (STABLE)
"""

from knowledge.pipeline import (
    on_upload,
    store_document,
    get_all_documents,
    delete_document,
    search_and_format,
)

from knowledge.retrieval import (
    retrieve,
    format_context,
)

from knowledge.feedback import (
    log_query,
    record_useful,
    record_not_useful,
    auto_signal_from_conversation,
    get_top_chunks_by_feedback,
    get_insights_for_source,
)

from knowledge.embeddings import (
    init_vector_db,
    vector_search,
    embed_text,
)

__all__ = [
    "on_upload", "store_document", "get_all_documents", "delete_document",
    "retrieve", "search_and_format", "format_context",
    "log_query", "record_useful", "record_not_useful",
    "auto_signal_from_conversation", "get_top_chunks_by_feedback",
    "get_insights_for_source",
    "init_vector_db", "vector_search", "embed_text",
]