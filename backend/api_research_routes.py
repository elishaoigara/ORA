from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from pydantic import BaseModel
import os, tempfile, traceback

router = APIRouter(prefix="/api/research", tags=["research"])


# ─────────────────────────────────────────────
# MODELS
# ─────────────────────────────────────────────

class ResearchRequest(BaseModel):
    query: str
    n_sources: int = 5


class EssayRequest(BaseModel):
    topic: str
    style: str = "analytical"
    length: str = "medium"


class PresentationRequest(BaseModel):
    topic: str
    slides: int = 5


class CompareRequest(BaseModel):
    query: str
    filenames: list[str]


class AskDocRequest(BaseModel):
    question: str
    filename: str


class SummarizeRequest(BaseModel):
    filename: str
    style: str = "executive"


# ─────────────────────────────────────────────
# SAFE IMPORT WRAPPER
# ─────────────────────────────────────────────

def _safe_import(name):
    try:
        from research_agent import __dict__ as ra
        return ra.get(name)
    except Exception:
        return None


# ─────────────────────────────────────────────
# SESSIONS
# ─────────────────────────────────────────────

@router.get("/sessions")
def list_sessions(limit: int = 20):
    try:
        from research_agent import get_sessions
        return get_sessions(limit)
    except Exception:
        return []


# ─────────────────────────────────────────────
# UPLOAD (SAFE MODE ONLY)
# ─────────────────────────────────────────────

@router.post("/upload")
async def upload(file: UploadFile = File(...), query: str = Form("")):
    try:
        content = await file.read()
        filename = file.filename or "doc.txt"

        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(content)
            path = tmp.name

        from research_agent import analyze_document

        text = content.decode("utf-8", errors="ignore")

        result = analyze_document(
            query or "Analyze this document",
            filename,
            text
        )

        os.unlink(path)

        return result

    except Exception:
        print(traceback.format_exc())
        raise HTTPException(500, "Upload failed")


# ─────────────────────────────────────────────
# SEARCH
# ─────────────────────────────────────────────

@router.post("/search")
def search(payload: ResearchRequest):
    try:
        from research_agent import deep_research
        return deep_research(payload.query, payload.n_sources)
    except Exception:
        print(traceback.format_exc())
        raise HTTPException(500, "Search failed")


# ─────────────────────────────────────────────
# ESSAY (FIXED CALL)
# ─────────────────────────────────────────────

@router.post("/essay")
def essay(payload: EssayRequest):
    try:
        from research_agent import write_essay
        return write_essay(payload.topic)
    except Exception:
        print(traceback.format_exc())
        raise HTTPException(500, "Essay failed")


# ─────────────────────────────────────────────
# PRESENTATION (FIXED)
# ─────────────────────────────────────────────

@router.post("/presentation")
def presentation(payload: PresentationRequest):
    try:
        from research_agent import generate_presentation
        return generate_presentation(payload.topic, payload.slides)
    except Exception:
        print(traceback.format_exc())
        raise HTTPException(500, "Presentation failed")


# ─────────────────────────────────────────────
# DOCUMENTS LIST
# ─────────────────────────────────────────────

@router.get("/documents")
def documents():
    try:
        from knowledge.pipeline import get_all_documents
        return get_all_documents()
    except Exception:
        return []


# ─────────────────────────────────────────────
# STATS (FIXED SAFE ACCESS)
# ─────────────────────────────────────────────

@router.get("/stats")
def stats():
    try:
        import sqlite3
        from config import DB_PATH
        from research_agent import get_sessions

        conn = sqlite3.connect(DB_PATH)

        total_sessions = conn.execute(
            "SELECT COUNT(*) FROM research_sessions"
        ).fetchone()[0]

        conn.close()

        sessions = get_sessions(5)

        recent = []
        for s in sessions:
            recent.append({
                "title": s.get("title", ""),
                "mode": s.get("mode", "research"),
                "created_at": s.get("created_at", "")
            })

        return {
            "total_sessions": total_sessions,
            "recent_sessions": recent
        }

    except Exception:
        return {
            "total_sessions": 0,
            "recent_sessions": []
        }