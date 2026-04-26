from typing import Optional
from knowledge.embeddings import embed_text, vector_search
from knowledge import get_all_documents
import numpy as np


# =========================
# QUERY EMBEDDING
# =========================
def embed_query(query: str) -> Optional[str]:
    return None  # embeddings disabled, FTS handles search


# =========================
# SEMANTIC RETRIEVAL
# =========================
def retrieve_documents(query: str, top_k: int = 5):
    query_vec = embed_query(query)

    if query_vec is None:
        return []

    results = vector_search(query_vec, top_k=top_k)

    # expected format:
    # [(text, metadata, score), ...]

    return results


# =========================
# RERANKING (lightweight)
# =========================
def rerank_results(query, results):
    if not results:
        return []

    query_words = set(query.lower().split())

    scored = []

    for text, meta, score in results:
        text_words = set(text.lower().split())

        overlap = len(query_words & text_words)
        final_score = score + (overlap * 0.05)

        scored.append((text, meta, final_score))

    scored.sort(key=lambda x: x[2], reverse=True)

    return scored


# =========================
# FORMAT FOR LLM CONTEXT
# =========================
def format_context(results, max_chars=2500):
    context = []
    total = 0

    for text, meta, score in results:
        chunk = f"[SOURCE: {meta.get('filename','unknown')}]\n{text}\n"

        if total + len(chunk) > max_chars:
            break

        context.append(chunk)
        total += len(chunk)

    return "\n---\n".join(context)


# =========================
# MAIN RAG PIPELINE
# =========================
def rag_search(query: str):
    raw = retrieve_documents(query, top_k=8)
    ranked = rerank_results(query, raw)
    return format_context(ranked)