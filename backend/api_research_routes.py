"""
ORA Research Agent — API Routes
================================
Add these routes to your existing api.py.

How to integrate:
1. Copy this file to backend/api_research_routes.py
2. In api.py, add near the top (with other router imports):
       from api_research_routes import router as research_router
       app.include_router(research_router)
3. In api.py lifespan startup, add:
       from agents.research_agent import init_research_tables
       init_research_tables()

All routes are prefixed with /api/research
"""

import os
import json
import tempfile
import traceback
from typing import Optional

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/research", tags=["research"])

ALLOWED_TYPES = {".pdf", ".docx", ".txt", ".md"}
MAX_FILE_BYTES = 15 * 1024 * 1024  # 15MB


# ─────────────────────────────────────────────────────────────────
# REQUEST MODELS
# ─────────────────────────────────────────────────────────────────

class ResearchRequest(BaseModel):
    query: str
    n_sources: int = 8

class EssayRequest(BaseModel):
    topic: str
    style: str = "analytical"   # analytical|argumentative|expository|critical|comparative
    length: str = "medium"      # short|medium|long

class PresentationRequest(BaseModel):
    topic: str
    slides: int = 10

class CompareRequest(BaseModel):
    query: str
    filenames: list[str]

class AskDocRequest(BaseModel):
    question: str
    filename: str

class SummarizeRequest(BaseModel):
    filename: str
    style: str = "executive"


# ─────────────────────────────────────────────────────────────────
# SESSIONS
# ─────────────────────────────────────────────────────────────────

@router.get("/sessions")
def list_sessions(limit: int = 30):
    try:
        from agents.research_agent import get_sessions
        return get_sessions(limit=limit)
    except Exception:
        print(traceback.format_exc())
        raise HTTPException(500, "Failed to load sessions")


@router.get("/sessions/{session_id}")
def get_session(session_id: str):
    try:
        from agents.research_agent import get_session
        session = get_session(session_id)
        if not session:
            raise HTTPException(404, "Session not found")
        return session
    except HTTPException:
        raise
    except Exception:
        print(traceback.format_exc())
        raise HTTPException(500, "Failed to load session")


@router.delete("/sessions/{session_id}")
def remove_session(session_id: str):
    try:
        from agents.research_agent import delete_session
        delete_session(session_id)
        return {"ok": True}
    except Exception:
        raise HTTPException(500, "Delete failed")


# ─────────────────────────────────────────────────────────────────
# DOCUMENT UPLOAD + ANALYSIS
# ─────────────────────────────────────────────────────────────────

@router.post("/upload")
async def upload_for_research(
    file: UploadFile = File(...),
    mode: str = Form("analyze"),       # analyze|summarize|extract|index
    query: str = Form(""),
    summary_style: str = Form("executive"),
    tags: str = Form("research")
):
    """
    Upload a document and immediately run analysis on it.
    Also indexes it into ORA's knowledge base for future queries.
    """
    try:
        # Validate
        filename = file.filename or "upload"
        ext = os.path.splitext(filename)[1].lower()
        if ext not in ALLOWED_TYPES:
            raise HTTPException(400, f"Unsupported type. Allowed: {', '.join(ALLOWED_TYPES)}")

        content = await file.read()
        if len(content) > MAX_FILE_BYTES:
            raise HTTPException(400, "File too large (max 15MB)")

        # Save temp
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        # 1. Index into ORA knowledge base
        try:
            from knowledge.pipeline import on_upload
            index_result = on_upload(tmp_path, filename, tags=tags, force=True)
        except Exception as e:
            index_result = {"status": "error", "reason": str(e)}

        # 2. Extract full text for immediate analysis
        try:
            from knowledge.ingest import load_document
            pages, doc_type = load_document(tmp_path)
            full_text = "\n\n".join(p["text"] for p in pages)
        except Exception:
            full_text = ""
            doc_type = ext.lstrip(".")

        # 3. Run requested analysis
        from agents.research_agent import (
            analyze_document, summarize_document, extract_key_points
        )

        result = {}
        if mode == "analyze":
            q = query or f"Provide a comprehensive analysis of {filename}"
            result = analyze_document(q, filename, full_text)
        elif mode == "summarize":
            result = summarize_document(filename, full_text, style=summary_style)
        elif mode == "extract":
            result = extract_key_points(filename, full_text)
        else:
            # Just index, return summary
            result = summarize_document(filename, full_text, style="executive")

        # Cleanup temp
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

        return {
            "filename": filename,
            "doc_type": doc_type,
            "index_result": index_result,
            "analysis": result,
            "page_count": len(pages) if 'pages' in dir() else 0,
            "word_count": len(full_text.split()) if full_text else 0
        }

    except HTTPException:
        raise
    except Exception:
        print(traceback.format_exc())
        raise HTTPException(500, "Upload and analysis failed")


@router.post("/ask-document")
async def ask_about_document(payload: AskDocRequest):
    """Ask a specific question about an already-indexed document."""
    try:
        from agents.research_agent import ask_document
        from knowledge.retrieval import retrieve, format_context

        # Retrieve doc content from KB
        chunks = retrieve(f"{payload.filename} {payload.question}", n_results=6)
        doc_chunks = [c for c in chunks if payload.filename in c.get("source", "")]
        full_text = "\n".join(c.get("text", "") for c in doc_chunks) if doc_chunks else ""

        if not full_text:
            full_text = "\n".join(c.get("text", "") for c in chunks)

        result = ask_document(payload.question, payload.filename, full_text)
        return result
    except Exception:
        print(traceback.format_exc())
        raise HTTPException(500, "Q&A failed")


@router.post("/summarize")
async def summarize(payload: SummarizeRequest):
    """Summarize an indexed document in various styles."""
    try:
        from agents.research_agent import summarize_document
        from knowledge.retrieval import retrieve

        chunks = retrieve(payload.filename, n_results=10)
        doc_chunks = [c for c in chunks if payload.filename in c.get("source", "")]
        full_text = "\n".join(c.get("text", "") for c in doc_chunks)

        if not full_text:
            raise HTTPException(404, "Document content not found in knowledge base")

        result = summarize_document(payload.filename, full_text, style=payload.style)
        return result
    except HTTPException:
        raise
    except Exception:
        print(traceback.format_exc())
        raise HTTPException(500, "Summarization failed")


# ─────────────────────────────────────────────────────────────────
# RESEARCH & SYNTHESIS
# ─────────────────────────────────────────────────────────────────

@router.post("/search")
async def research_search(payload: ResearchRequest):
    """Deep multi-source research synthesis from knowledge base."""
    try:
        from agents.research_agent import deep_research
        result = deep_research(payload.query, n_sources=payload.n_sources)
        return result
    except Exception:
        print(traceback.format_exc())
        raise HTTPException(500, "Research failed")


@router.post("/essay")
async def write_essay(payload: EssayRequest):
    """Generate a structured essay or long-form piece."""
    try:
        from agents.research_agent import write_essay
        result = write_essay(payload.topic, style=payload.style, length=payload.length)
        return result
    except Exception:
        print(traceback.format_exc())
        raise HTTPException(500, "Essay generation failed")


@router.post("/presentation")
async def create_presentation(payload: PresentationRequest):
    """Generate a structured presentation outline."""
    try:
        from agents.research_agent import generate_presentation
        result = generate_presentation(payload.topic, slides=payload.slides)
        return result
    except Exception:
        print(traceback.format_exc())
        raise HTTPException(500, "Presentation generation failed")


@router.post("/compare")
async def compare(payload: CompareRequest):
    """Comparative analysis across multiple documents."""
    try:
        if len(payload.filenames) < 2:
            raise HTTPException(400, "Need at least 2 documents to compare")
        from agents.research_agent import compare_documents
        result = compare_documents(payload.query, payload.filenames)
        return result
    except HTTPException:
        raise
    except Exception:
        print(traceback.format_exc())
        raise HTTPException(500, "Comparison failed")


# ─────────────────────────────────────────────────────────────────
# KNOWLEDGE BASE STATUS
# ─────────────────────────────────────────────────────────────────

@router.get("/documents")
def list_documents():
    """List all documents in ORA's knowledge base."""
    try:
        from knowledge.pipeline import get_all_documents
        return get_all_documents()
    except Exception:
        return []


@router.get("/stats")
def research_stats():
    """Research agent statistics."""
    try:
        import sqlite3
        from config import DB_PATH
        from agents.research_agent import get_sessions

        conn = sqlite3.connect(DB_PATH)

        session_count = conn.execute("SELECT COUNT(*) FROM research_sessions").fetchone()[0]
        doc_count = conn.execute("SELECT COUNT(DISTINCT source) FROM knowledge_chunks").fetchone()[0]
        total_chunks = conn.execute("SELECT COUNT(*) FROM knowledge_chunks").fetchone()[0]
        conn.close()

        sessions = get_sessions(limit=5)
        recent = [{"title": s["title"], "mode": s["mode"], "created_at": s["created_at"]} for s in sessions]

        return {
            "total_sessions": session_count,
            "documents_indexed": doc_count,
            "total_chunks": total_chunks,
            "recent_sessions": recent
        }
    except Exception:
        print(traceback.format_exc())
        return {"total_sessions": 0, "documents_indexed": 0, "total_chunks": 0}