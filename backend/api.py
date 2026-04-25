"""
ORA Backend API — v2 (Render Free Tier Safe)
Upgrades vs v1:
  - Response cache (avoids repeat Groq calls)
  - Smart query router (right model for right query)
  - /api/knowledge/upload  — file upload with background indexing
  - /api/knowledge/summary — per-document AI summary on demand
  - /api/cache/stats       — debug endpoint
"""

import os
import traceback
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

import psutil
from fastapi import FastAPI, Request, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from groq import Groq

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

ALLOWED_UPLOAD_TYPES = {".pdf", ".docx", ".txt", ".md"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


# ============================================================
# LIFESPAN
# ============================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[ORA] Starting...")

    try:
        from database import init_db, init_tasks_table
        init_db()
        init_tasks_table()
        print("[ORA] DB Ready")
    except Exception:
        print(traceback.format_exc())

    try:
        from mpesa_engine import init_mpesa_table
        init_mpesa_table()
    except Exception:
        print(traceback.format_exc())

    try:
        from memory.profile import init_profile
        init_profile()
    except Exception:
        print(traceback.format_exc())

    try:
        from knowledge.embeddings import init_vector_db
        init_vector_db()
        print("[ORA] Knowledge DB ready")
    except Exception:
        print("[KNOWLEDGE INIT ERROR]")
        print(traceback.format_exc())

    try:
        from config import TELEGRAM_BOT_TOKEN
        if TELEGRAM_BOT_TOKEN:
            def telegram_worker():
                from telegram_bot import run_telegram_bot
                while True:
                    try:
                        run_telegram_bot()
                        time.sleep(2)
                    except Exception as e:
                        print("[TELEGRAM ERROR]", e)
                        time.sleep(5)
            threading.Thread(target=telegram_worker, daemon=True).start()
    except Exception:
        print(traceback.format_exc())

    yield
    print("[ORA] Shutdown")


# ============================================================
# APP
# ============================================================
app = FastAPI(title="ORA Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# HEALTH / ROOT / STATUS
# ============================================================
@app.api_route("/api/health", methods=["GET", "HEAD"])
async def health(request: Request):
    return {"status": "ok"}

@app.get("/")
def root():
    return {"status": "ORA running"}

@app.get("/api/status")
def status():
    return {
        "cpu": psutil.cpu_percent(interval=0.1),
        "ram": psutil.virtual_memory().percent,
        "time": datetime.utcnow().isoformat(),
    }

@app.get("/api/cache/stats")
def cache_stats():
    try:
        from cache import stats
        return stats()
    except Exception:
        return {}


# ============================================================
# CHAT — with cache + router
# ============================================================
class ChatRequest(BaseModel):
    message: str

@app.post("/api/chat")
async def chat(payload: ChatRequest):
    try:
        if not client:
            return {"reply": "ORA: Missing API key"}

        text = payload.message.strip()
        if not text:
            return {"reply": "Empty message."}

        from database import save_conversation, get_conversation_history
        from context import build_system_prompt
        from brain.router import classify, model_for   
        import cache

        # ── 1. Classify query ─────────────────────────────────
        q_type = classify(text)

        # ── 2. Pull KB context ────────────────────────────────
        knowledge_ctx = ""
        try:
            from knowledge.pipeline import search_and_format
            n = 3 if q_type == "document" else 2
            knowledge_ctx = search_and_format(text, n_results=n) or ""
        except Exception:
            pass

        # ── 3. Check cache (skip for document queries — always fresh) ──
        if q_type != "document":
            cached = cache.get(text, knowledge_ctx)
            if cached:
                save_conversation("user", text)
                save_conversation("assistant", cached)
                return {"reply": cached, "cached": True}

        # ── 4. Build prompt ───────────────────────────────────
        system_prompt = build_system_prompt(query=text)
        if knowledge_ctx:
            system_prompt += f"\n\n## KNOWLEDGE BASE\n{knowledge_ctx[:700]}"

        history = get_conversation_history(limit=4)
        messages = [{"role": "system", "content": system_prompt}]
        for role, content, _ in history:
            messages.append({
                "role": "user" if role == "user" else "assistant",
                "content": content[:200]
            })
        messages.append({"role": "user", "content": text})

        # ── 5. Pick model via router ──────────────────────────
        model, max_tok = model_for(q_type)

        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tok,
                temperature=0.4,
            )
        except Exception:
            # Fallback to small model
            response = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=messages,
                max_tokens=200,
                temperature=0.4,
            )

        reply = response.choices[0].message.content or "No response"

        # ── 6. Cache + save ───────────────────────────────────
        if q_type != "document":
            cache.set(text, reply, knowledge_ctx)

        save_conversation("user", text)
        save_conversation("assistant", reply)

        return {"reply": reply, "query_type": q_type, "model": model}

    except Exception:
        print("[CHAT ERROR]")
        print(traceback.format_exc())
        return {"reply": "ORA error. Try again."}


# ============================================================
# CONVERSATIONS
# ============================================================
@app.get("/api/conversations")
def get_conversations(limit: int = 40):
    try:
        from database import get_conversation_history
        rows = get_conversation_history(limit=limit)
        return [{"role": r[0], "content": r[1], "timestamp": r[2]} for r in rows]
    except Exception:
        return []


# ============================================================
# TASKS
# ============================================================
class TaskCreate(BaseModel):
    title: str
    priority: str = "medium"
    due_at: Optional[str] = None

@app.get("/api/tasks")
def get_tasks(status: str = "pending"):
    try:
        from database import get_tasks
        rows = get_tasks(status)
        return [{"id": r[0], "title": r[1], "priority": r[2], "created_at": r[3], "due_at": r[4]} for r in rows]
    except Exception:
        return []

@app.post("/api/tasks")
def add_task(payload: TaskCreate):
    try:
        from database import add_task
        add_task(payload.title, payload.priority, payload.due_at)
        return {"status": "created"}
    except Exception:
        raise HTTPException(500, "Failed")

@app.post("/api/tasks/{task_id}/complete")
def complete_task(task_id: int):
    try:
        from database import complete_task
        complete_task(task_id)
        return {"status": "done"}
    except Exception:
        raise HTTPException(500, "Failed")

@app.delete("/api/tasks/{task_id}")
def delete_task(task_id: int):
    try:
        from database import delete_task
        delete_task(task_id)
        return {"status": "deleted"}
    except Exception:
        raise HTTPException(500, "Failed")


# ============================================================
# THE NUMBER
# ============================================================
@app.get("/api/the-number")
def the_number():
    try:
        from intelligence.priority_engine import get_prioritized_tasks, score_task
        ranked = get_prioritized_tasks()
        if not ranked:
            return {"status": "empty"}
        top = ranked[0]
        task_id, title, priority, created_at, due_at = top
        overdue = False
        if due_at:
            try:
                overdue = datetime.fromisoformat(due_at) < datetime.now()
            except Exception:
                pass
        return {
            "id": task_id, "title": title, "priority": priority,
            "due_at": due_at, "overdue": overdue,
            "score": score_task(top), "reason": _score_reason(top), "status": "ok",
        }
    except Exception:
        print(traceback.format_exc())
        return {"status": "empty"}

def _score_reason(task):
    _, title, priority, _, due_at = task
    parts = []
    if priority == "high": parts.append("high priority")
    if due_at:
        try:
            diff = (datetime.fromisoformat(due_at) - datetime.now()).total_seconds()
            if diff < 0: parts.append("overdue")
            elif diff < 3600: parts.append("due within 1h")
            elif diff < 86400: parts.append("due today")
        except Exception: pass
    if "urgent" in title.lower(): parts.append("marked urgent")
    return ", ".join(parts) if parts else "top pending task"


# ============================================================
# ALERTS
# ============================================================
@app.get("/api/alerts")
def alerts(limit: int = 10):
    try:
        from database import get_recent_alerts
        rows = get_recent_alerts(limit)
        return [{"id": r[0], "rule_name": r[1], "message": r[2], "severity": r[3], "timestamp": r[4], "acknowledged": bool(r[5])} for r in rows]
    except Exception:
        return []

@app.post("/api/alerts/{alert_id}/ack")
def ack_alert(alert_id: int, feedback: Optional[str] = None):
    try:
        from database import acknowledge_alert
        acknowledge_alert(alert_id, feedback)
        return {"status": "acknowledged"}
    except Exception:
        raise HTTPException(500, "Failed")

@app.post("/api/alerts/ack-all")
def ack_all_alerts():
    try:
        from database import get_conn
        conn = get_conn()
        conn.execute("UPDATE alerts SET acknowledged=1 WHERE acknowledged=0")
        conn.commit()
        return {"status": "all acknowledged"}
    except Exception:
        raise HTTPException(500, "Failed")


# ============================================================
# M-PESA
# ============================================================
class MpesaSMS(BaseModel):
    sms: str

@app.post("/api/mpesa/ingest")
def mpesa_ingest(payload: MpesaSMS):
    try:
        from mpesa_engine import ingest_sms
        return ingest_sms(payload.sms)
    except Exception:
        raise HTTPException(500, "M-Pesa ingest failed")

@app.get("/api/mpesa/summary")
def mpesa_summary():
    try:
        from mpesa_engine import get_today_spend, get_average_daily_spend, get_daily_summary, get_recent_transactions, get_recurring_patterns
        return {
            "today": get_today_spend(),
            "average_daily": get_average_daily_spend(),
            "last_7_days": get_daily_summary(days=7),
            "recent_transactions": get_recent_transactions(limit=10),
            "recurring": get_recurring_patterns(),
        }
    except Exception:
        print(traceback.format_exc())
        return {"status": "error"}

@app.get("/api/mpesa/transactions")
def mpesa_transactions(limit: int = 20):
    try:
        from mpesa_engine import get_recent_transactions
        return get_recent_transactions(limit=limit)
    except Exception:
        return []


# ============================================================
# MEMORY
# ============================================================
@app.get("/api/memory/profile")
def memory_profile():
    try:
        from memory.profile import get_all_profile
        return get_all_profile()
    except Exception:
        return {}

class ProfileUpdate(BaseModel):
    key: str
    value: str

@app.post("/api/memory/profile")
def update_profile(payload: ProfileUpdate):
    try:
        from memory.profile import set_profile
        set_profile(payload.key, payload.value)
        return {"status": "updated"}
    except Exception:
        raise HTTPException(500, "Failed")

@app.get("/api/memory/preferences")
def memory_preferences(category: Optional[str] = None):
    try:
        from memory.preferences import get_preferences
        rows = get_preferences(category=category)
        return [{"category": r[0], "key": r[1], "value": r[2], "confidence": r[3]} for r in rows]
    except Exception:
        return []

@app.get("/api/memory/events")
def memory_events(limit: int = 20, event_type: Optional[str] = None):
    try:
        from memory.events import get_recent_events
        rows = get_recent_events(limit=limit, event_type=event_type)
        return [{"event_type": r[0], "summary": r[1], "detail": r[2], "importance": r[3], "timestamp": r[4]} for r in rows]
    except Exception:
        return []

@app.get("/api/memory/important")
def memory_important(min_importance: int = 7, limit: int = 10):
    try:
        from memory.events import get_important_events
        rows = get_important_events(min_importance=min_importance, limit=limit)
        return [{"event_type": r[0], "summary": r[1], "detail": r[2], "importance": r[3], "timestamp": r[4]} for r in rows]
    except Exception:
        return []


# ============================================================
# BRIEFING
# ============================================================
@app.get("/api/briefing")
def get_briefing():
    try:
        from briefing import generate_briefing
        text = generate_briefing()
        return {"briefing": text, "timestamp": datetime.utcnow().isoformat()}
    except Exception:
        print(traceback.format_exc())
        return {"briefing": "ORA standing by.", "timestamp": datetime.utcnow().isoformat()}


# ============================================================
# KNOWLEDGE — LIST / DELETE / SEARCH
# ============================================================
@app.get("/api/knowledge/documents")
def knowledge_documents():
    try:
        from knowledge.pipeline import get_all_documents
        return get_all_documents()
    except Exception:
        print(traceback.format_exc())
        return []

@app.delete("/api/knowledge/documents/{filename}")
def knowledge_delete(filename: str):
    try:
        from knowledge.pipeline import delete_document
        delete_document(filename)
        return {"status": "deleted"}
    except Exception:
        raise HTTPException(500, "Failed")

class KnowledgeQuery(BaseModel):
    query: str
    n_results: int = 4

@app.post("/api/knowledge/search")
def knowledge_search(payload: KnowledgeQuery):
    try:
        from knowledge.pipeline import search_and_format
        result = search_and_format(payload.query, n_results=payload.n_results)
        return {"result": result}
    except Exception:
        return {"result": ""}


# ============================================================
# KNOWLEDGE — UPLOAD (background indexing)
# ============================================================
def _run_indexing(filepath: str, filename: str, tags: str):
    try:
        from knowledge.pipeline import on_upload
        result = on_upload(filepath, filename, tags=tags, force=False)
        print(f"[UPLOAD] Indexed {filename}: {result}")
    except Exception as e:
        print(f"[UPLOAD] Indexing failed for {filename}: {e}")

@app.post("/api/knowledge/upload")
async def knowledge_upload(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    tags: str = Form(default=""),
):
    try:
        from config import UPLOADS_DIR
        filename = file.filename or "unknown"
        ext = os.path.splitext(filename)[1].lower()
        if ext not in ALLOWED_UPLOAD_TYPES:
            raise HTTPException(400, f"Unsupported type '{ext}'. Allowed: {', '.join(ALLOWED_UPLOAD_TYPES)}")
        data = await file.read()
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "File too large. Max 10MB.")
        if len(data) == 0:
            raise HTTPException(400, "Empty file.")
        safe_name = _safe_filename(filename)
        dest = os.path.join(UPLOADS_DIR, safe_name)
        with open(dest, "wb") as f:
            f.write(data)
        background_tasks.add_task(_run_indexing, dest, safe_name, tags)
        return {
            "status": "accepted",
            "filename": safe_name,
            "size_kb": round(len(data) / 1024, 1),
            "message": "File saved. Indexing in background — check /api/knowledge/documents in a few seconds.",
        }
    except HTTPException:
        raise
    except Exception:
        print(traceback.format_exc())
        raise HTTPException(500, "Upload failed")


# ============================================================
# KNOWLEDGE — AI SUMMARY (on-demand, 1 Groq call per doc) ← NEW
# ============================================================
@app.get("/api/knowledge/summary/{filename}")
def knowledge_summary(filename: str):
    """
    Returns an AI-generated summary for an indexed document.
    Uses the stored summary if available (free).
    Falls back to generating one via Groq if not (1 API call, cached after).
    """
    try:
        from knowledge.pipeline import get_all_documents, search_and_format
        import cache

        # Check stored summary first (zero cost)
        docs = get_all_documents()
        doc = next((d for d in docs if d["filename"] == filename), None)
        if not doc:
            raise HTTPException(404, "Document not found")

        if doc.get("summary") and len(doc["summary"]) > 50:
            return {"filename": filename, "summary": doc["summary"], "source": "stored"}

        # Check cache
        cache_key = f"summary::{filename}"
        cached = cache.get(cache_key)
        if cached:
            return {"filename": filename, "summary": cached, "source": "cached"}

        # Generate via Groq (1 call, stored forever after)
        if not client:
            raise HTTPException(503, "AI unavailable")

        # Pull top chunks from this document
        chunks = search_and_format(filename.replace("_", " ").replace("-", " "), n_results=5)
        if not chunks:
            return {"filename": filename, "summary": "No content extracted.", "source": "empty"}

        prompt = f"""Summarize this document in 3 concise bullet points. Be factual, no fluff.

Document: {filename}
Content:
{chunks[:2000]}

Return exactly 3 bullet points starting with •"""

        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=250,
            temperature=0.3,
        )
        summary = response.choices[0].message.content.strip()

        # Cache it
        cache.set(cache_key, summary)

        return {"filename": filename, "summary": summary, "source": "generated"}

    except HTTPException:
        raise
    except Exception:
        print(traceback.format_exc())
        raise HTTPException(500, "Summary failed")


def _safe_filename(name: str) -> str:
    import re
    name = os.path.basename(name)
    name = re.sub(r'[^\w.\-]', '_', name)
    return name[:120]