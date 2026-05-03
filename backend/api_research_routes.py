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


# ═══════════════════════════════════════════════════════════════
# STUDY PARTNER ROUTES — Phase 2 (Quiz, Flashcards, Explain,
#                         Summarize, Study Plan)
# ═══════════════════════════════════════════════════════════════

class QuizRequest(BaseModel):
    topic:      str
    num:        int  = 5     # number of questions
    difficulty: str  = "medium"   # easy | medium | hard
    style:      str  = "mcq"      # mcq | true_false | short_answer | mixed

class FlashcardRequest(BaseModel):
    topic: str
    num:   int = 10

class ExplainRequest(BaseModel):
    topic:   str
    level:   str = "beginner"  # beginner | intermediate | advanced
    analogy: bool = True

class SummarizeRequest(BaseModel):
    text:   str
    style:  str = "bullet"   # bullet | paragraph | cornell | mindmap
    length: str = "medium"   # short | medium | detailed

class StudyPlanRequest(BaseModel):
    subject:   str
    exam_date: str   # e.g. "2 weeks", "Dec 15", "30 days"
    hours_per_day: float = 2.0
    current_level: str = "beginner"


def _llm(prompt: str, max_tokens: int = 1800) -> str:
    """Call Groq with a single user prompt. Returns raw text."""
    try:
        from groq import Groq
        import os
        client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        resp = client.chat.completions.create(
            model   = os.getenv("GROQ_MODEL_PRIMARY", "llama-3.3-70b-versatile"),
            messages= [{"role": "user", "content": prompt}],
            max_tokens= max_tokens,
            temperature= 0.4,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        raise HTTPException(500, f"LLM error: {e}")


@router.post("/quiz")
def generate_quiz(payload: QuizRequest):
    """
    Generate a quiz on any topic. Returns structured JSON with questions.
    style: mcq | true_false | short_answer | mixed
    """
    style_guide = {
        "mcq":          "multiple-choice questions with 4 options (A-D). Mark the correct answer.",
        "true_false":   "True/False questions. State whether the answer is True or False.",
        "short_answer": "short-answer questions. Provide a concise model answer (1-2 sentences).",
        "mixed":        "a mix of multiple-choice (50%), True/False (25%), and short-answer (25%) questions.",
    }.get(payload.style, "multiple-choice questions with 4 options")

    diff_guide = {
        "easy":   "basic recall and definition questions suitable for a beginner",
        "medium": "application and comprehension questions for an intermediate student",
        "hard":   "analysis, synthesis, and evaluation questions for an advanced student",
    }.get(payload.difficulty, "moderate difficulty")

    prompt = f"""You are a smart tutor. Generate exactly {payload.num} {diff_guide} on the topic: "{payload.topic}".

Format: {style_guide}

Return ONLY valid JSON in this exact structure (no markdown, no explanation):
{{
  "topic": "{payload.topic}",
  "difficulty": "{payload.difficulty}",
  "questions": [
    {{
      "id": 1,
      "type": "mcq",
      "question": "Question text here",
      "options": {{"A": "...", "B": "...", "C": "...", "D": "..."}},
      "answer": "A",
      "explanation": "Brief explanation of why this is correct"
    }}
  ]
}}

For true_false, use: "options": {{"A": "True", "B": "False"}} and answer "A" or "B".
For short_answer, use: "options": {{}}, "answer": "model answer text".
Generate all {payload.num} questions now."""

    raw = _llm(prompt, max_tokens=2000)

    # Parse JSON
    import json, re
    try:
        # Strip any markdown fences
        clean = re.sub(r"```json|```", "", raw).strip()
        data  = json.loads(clean)
        return data
    except Exception:
        # Fallback: return raw text with error flag
        return {"topic": payload.topic, "difficulty": payload.difficulty,
                "questions": [], "raw": raw, "parse_error": True}


@router.post("/flashcards")
def generate_flashcards(payload: FlashcardRequest):
    """Generate flashcard pairs (front = question, back = answer)."""
    prompt = f"""You are a study expert. Create exactly {payload.num} flashcards on: "{payload.topic}".

Return ONLY valid JSON (no markdown):
{{
  "topic": "{payload.topic}",
  "cards": [
    {{
      "id": 1,
      "front": "Key term or question",
      "back": "Definition or answer (concise, 1-3 sentences)",
      "hint": "Optional memory hint or mnemonic"
    }}
  ]
}}

Make the cards progressively build on each other. Generate all {payload.num} now."""

    raw = _llm(prompt, max_tokens=2000)

    import json, re
    try:
        clean = re.sub(r"```json|```", "", raw).strip()
        return json.loads(clean)
    except Exception:
        return {"topic": payload.topic, "cards": [], "raw": raw, "parse_error": True}


@router.post("/explain")
def explain_topic(payload: ExplainRequest):
    """Explain a topic at a given level, optionally with analogy."""
    level_guide = {
        "beginner":     "a complete beginner with no prior knowledge. Use simple words, no jargon.",
        "intermediate": "a student who knows the basics. Use proper terminology but explain it.",
        "advanced":     "an advanced student. Use technical depth, nuance, and edge cases.",
    }.get(payload.level, "a student")

    analogy_line = "Include a memorable real-world analogy or metaphor to cement understanding." if payload.analogy else ""

    prompt = f"""You are a world-class teacher. Explain "{payload.topic}" to {level_guide}

{analogy_line}

Structure your explanation as:
1. **What it is** — one-sentence definition
2. **Why it matters** — real-world relevance
3. **How it works** — step-by-step breakdown
4. **Analogy** — (if relevant) a comparison to something familiar
5. **Key things to remember** — 3-5 bullet points
6. **Common mistakes** — what students get wrong

Be clear, engaging, and thorough. Use markdown formatting."""

    content = _llm(prompt, max_tokens=1500)
    return {
        "topic":   payload.topic,
        "level":   payload.level,
        "content": content,
    }


@router.post("/summarize")
def summarize_text(payload: SummarizeRequest):
    """Summarize any text in different styles."""
    length_guide = {"short": "~100 words", "medium": "~250 words", "detailed": "~500 words"}.get(payload.length, "~250 words")

    style_prompts = {
        "bullet":    f"a clean bullet-point summary ({length_guide}). Group related points under bold headings.",
        "paragraph": f"flowing paragraphs ({length_guide}). Capture the main ideas in natural prose.",
        "cornell":   f"Cornell note format: Main Notes | Key Questions | Summary paragraph. Target {length_guide} total.",
        "mindmap":   f"a text-based mind map using indentation. Main topic → subtopics → details. Target {length_guide}.",
    }.get(payload.style, f"a concise summary ({length_guide})")

    prompt = f"""You are a study assistant. Summarize the following text as {style_prompts}

Use markdown formatting. Be accurate — do not add information not in the text.

TEXT TO SUMMARIZE:
{payload.text[:4000]}

SUMMARY:"""

    content = _llm(prompt, max_tokens=800)
    return {
        "style":   payload.style,
        "length":  payload.length,
        "content": content,
    }


@router.post("/study-plan")
def generate_study_plan(payload: StudyPlanRequest):
    """Generate a personalised study plan for an upcoming exam."""
    prompt = f"""You are an expert academic coach. Create a detailed, realistic study plan.

Subject: {payload.subject}
Exam/deadline: {payload.exam_date}
Study time available: {payload.hours_per_day} hours per day
Current level: {payload.current_level}

Create a day-by-day study plan that:
1. Starts with foundational concepts and builds up
2. Includes specific topics to cover each day
3. Balances new learning with revision
4. Includes rest days and mock-exam sessions
5. Suggests specific resources (textbooks, practice problems, etc.)
6. Has daily goals that are achievable in {payload.hours_per_day} hours

Format with markdown: use ## for week headers, ### for day headers, bullet points for tasks.
Be specific — name actual topics, not just "study chapter 1".
End with a "Week Before Exam" cramming strategy."""

    content = _llm(prompt, max_tokens=2000)
    return {
        "subject":       payload.subject,
        "exam_date":     payload.exam_date,
        "hours_per_day": payload.hours_per_day,
        "current_level": payload.current_level,
        "content":       content,
    }


print("[RESEARCH ROUTES] Study Partner routes loaded")
