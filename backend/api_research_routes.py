"""
ORA Research Routes — Clean, Stable, and Fully Compatible with Frontend
"""
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from pydantic import BaseModel
import os
import tempfile
import traceback
from datetime import datetime

router = APIRouter(prefix="/api/research", tags=["research"])

# ─────────────────────────────────────────────
# REQUEST MODELS
# ─────────────────────────────────────────────
class ResearchRequest(BaseModel):
    query: str
    n_sources: int = 8

class EssayRequest(BaseModel):
    topic: str
    style: str = "analytical"
    length: str = "medium"

class PresentationRequest(BaseModel):
    topic: str
    slides: int = 8

# ─────────────────────────────────────────────
# HELPER: Safe import research_agent
# ─────────────────────────────────────────────
def _get_research_agent():
    try:
        import research_agent
        return research_agent
    except Exception as e:
        print(f"[RESEARCH ROUTES] Failed to import research_agent: {e}")
        raise HTTPException(status_code=500, detail="Research agent not available")

# ─────────────────────────────────────────────
# SESSIONS
# ─────────────────────────────────────────────
@router.get("/sessions")
def list_sessions(limit: int = 15):
    try:
        ra = _get_research_agent()
        return ra.get_sessions(limit=limit)
    except Exception as e:
        print(f"[RESEARCH] list_sessions error: {e}")
        return []

@router.get("/sessions/{session_id}")
def get_session(session_id: str):
    """Used by frontend when loading a previous session"""
    try:
        ra = _get_research_agent()
        session = ra.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        return session
    except Exception as e:
        print(f"[RESEARCH] get_session error: {e}")
        raise HTTPException(status_code=500, detail="Failed to load session")

# ─────────────────────────────────────────────
# UPLOAD (Document Analysis)
# ─────────────────────────────────────────────
@router.post("/upload")
async def upload(
    file: UploadFile = File(...),
    query: str = Form("")
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")
    try:
        content = await file.read()
        filename = file.filename
        # Decode text safely
        try:
            text = content.decode("utf-8", errors="ignore")
        except Exception:
            text = str(content)[:15000]
        ra = _get_research_agent()
        result = ra.analyze_document(
            query=query or "Analyze this document",
            filename=filename,
            text=text
        )
        return result
    except Exception as e:
        print(f"[RESEARCH UPLOAD ERROR] {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Document analysis failed")

# ─────────────────────────────────────────────
# SEARCH
# ─────────────────────────────────────────────
@router.post("/search")
def search(payload: ResearchRequest):
    try:
        ra = _get_research_agent()
        return ra.deep_research(payload.query, payload.n_sources)
    except Exception as e:
        print(f"[RESEARCH SEARCH ERROR] {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Search failed")

# ─────────────────────────────────────────────
# RESEARCH (Main endpoint - FIXED)
# ─────────────────────────────────────────────
@router.post("/research")
def research(payload: ResearchRequest):
    """
    Main research endpoint - performs deep research on a query
    This endpoint was missing and returning 404
    """
    try:
        ra = _get_research_agent()
        print(f"[RESEARCH] Starting research for query: {payload.query}")
        
        # Call the research agent's deep_research method
        result = ra.deep_research(
            query=payload.query,
            n_sources=payload.n_sources
        )
        
        return {
            "status": "success",
            "query": payload.query,
            "result": result.get("result") if isinstance(result, dict) else result,
            "sources": result.get("sources") if isinstance(result, dict) else [],
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        print(f"[RESEARCH ERROR] {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Research failed: {str(e)}"
        )

# ─────────────────────────────────────────────
# ESSAY
# ─────────────────────────────────────────────
@router.post("/essay")
def essay(payload: EssayRequest):
    try:
        ra = _get_research_agent()
        return ra.write_essay(payload.topic)
    except Exception as e:
        print(f"[RESEARCH ESSAY ERROR] {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Essay generation failed")

# ─────────────────────────────────────────────
# PRESENTATION
# ─────────────────────────────────────────────
@router.post("/presentation")
def presentation(payload: PresentationRequest):
    try:
        ra = _get_research_agent()
        return ra.generate_presentation(payload.topic, payload.slides)
    except Exception as e:
        print(f"[RESEARCH PRESENTATION ERROR] {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Presentation generation failed")

# ─────────────────────────────────────────────
# DOCUMENTS (for Knowledge Base tab)
# ─────────────────────────────────────────────
@router.get("/documents")
def get_documents():
    """Return documents for the Knowledge Base tab in Research page"""
    try:
        from knowledge.pipeline import get_all_documents
        return get_all_documents()
    except Exception as e:
        print(f"[RESEARCH DOCUMENTS ERROR] {e}")
        return []

# ─────────────────────────────────────────────
# STATS
# ─────────────────────────────────────────────
@router.get("/stats")
def get_stats():
    """Simple stats for Research header"""
    try:
        import sqlite3
        from config import DB_PATH
        from research_agent import get_sessions
        conn = sqlite3.connect(DB_PATH)
        total_sessions = conn.execute(
            "SELECT COUNT(*) FROM research_sessions"
        ).fetchone()[0]
        conn.close()
        recent_sessions = get_sessions(limit=5)
        return {
            "total_sessions": total_sessions,
            "documents_indexed": 0,      # Can be expanded later
            "total_chunks": 0,
            "recent_sessions": recent_sessions
        }
    except Exception as e:
        print(f"[RESEARCH STATS ERROR] {e}")
        return {
            "total_sessions": 0,
            "documents_indexed": 0,
            "total_chunks": 0,
            "recent_sessions": []
        }
