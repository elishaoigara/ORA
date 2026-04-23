import os
import json
import uuid
import traceback
import threading
import time
import psutil
from datetime import datetime

from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from groq import Groq

# ========================
# DATABASE
# ========================
from database import (
    get_recent_alerts,
    get_system_stats,
    acknowledge_alert,
    get_tasks,
    get_conversation_history,
    save_conversation,
    init_db,
    init_tasks_table,
    log_event
)

# ========================
# MEMORY
# ========================
from memory.profile import get_all_profile, init_profile
from memory.events import get_recent_events, log_memory_event
from memory.preferences import get_preferences

# ========================
# CORE
# ========================
from context import build_system_prompt

from knowledge import (
    store_document,
    get_all_documents,
    delete_document,
    search_and_format,
    on_upload,
    record_useful,
    record_not_useful,
    get_insights_for_source,
    UPLOADS_PATH
)

# ========================
# ENV
# ========================
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
FRONTEND_URL = os.getenv("FRONTEND_URL", "*")

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


# ========================
# BACKGROUND MONITOR
# ========================
def monitoring_loop():
    while True:
        try:
            data = {
                "cpu_percent": psutil.cpu_percent(interval=1),
                "ram_percent": psutil.virtual_memory().percent,
                "disk_free_gb": psutil.disk_usage("/").free / (1024 ** 3),
                "timestamp": datetime.now().isoformat()
            }

            # ✅ FIX 1: json.dumps not str() — str() produces invalid JSON (single quotes)
            log_event("system", json.dumps(data))

        except Exception as e:
            print("[MONITOR ERROR]", e)

        time.sleep(5)


# ========================
# TELEGRAM BOT THREAD
# ========================
def start_telegram():
    try:
        from telegram_bot import run_telegram_bot
        print("[ORA] Telegram bot starting...")
        run_telegram_bot()
    except Exception as e:
        print(f"[TELEGRAM] Failed to start: {e}")


# ========================
# INIT
# ========================
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        init_db()
        init_tasks_table()
        init_profile()
        log_memory_event("system", "ORA API started", importance=6)

        # ✅ FIX 2: monitoring thread inside lifespan (on_event is ignored when lifespan is set)
        threading.Thread(target=monitoring_loop, daemon=True).start()
        print("[ORA] Monitoring thread started")

        # ✅ FIX 3: telegram was never launched from api.py — added here
        threading.Thread(target=start_telegram, daemon=True).start()

    except Exception:
        print("[INIT ERROR]", traceback.format_exc())

    yield


app = FastAPI(title="ORA Backend", lifespan=lifespan)


# ========================
# CORS
# ========================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ========================
# STATIC FILES
# ========================
os.makedirs(UPLOADS_PATH, exist_ok=True)

app.mount(
    "/uploads",
    StaticFiles(directory=UPLOADS_PATH),
    name="uploads"
)


# ========================
# HEALTH
# ========================
@app.get("/")
def root():
    return {"status": "ORA backend running"}


@app.get("/api/health")
@app.head("/api/health")
def health():
    return {"status": "ORA online"}


# ========================
# STATUS
# ========================
@app.get("/api/status")
def status():
    try:
        row = get_system_stats()
        if not row:
            return {"status": "warming_up"}

        data = json.loads(row[0])

        return {
            "cpu": data.get("cpu_percent", 0),
            "ram": data.get("ram_percent", 0),
            "disk_free_gb": data.get("disk_free_gb", 0),
            "last_updated": row[1]
        }

    except Exception:
        return {"status": "error", "detail": traceback.format_exc()}


# ========================
# ALERTS
# ========================
@app.get("/api/alerts")
def alerts():
    try:
        data = get_recent_alerts(20)
        return [
            {
                "id": a[0],
                "rule": a[1],
                "message": a[2],
                "severity": a[3],
                "timestamp": a[4],
                "acknowledged": bool(a[5])
            }
            for a in data
        ]
    except Exception:
        return []


@app.post("/api/alerts/{alert_id}/ack")
def ack(alert_id: int):
    try:
        acknowledge_alert(alert_id)
        return {"status": "acknowledged"}
    except Exception:
        return {"status": "error"}


# ========================
# MEMORY
# ========================
@app.get("/api/memory/profile")
def profile():
    return get_all_profile() or {}


@app.get("/api/memory/events")
def events():
    try:
        data = get_recent_events(limit=20)
        return [
            {
                "type": e[0],
                "summary": e[1],
                "importance": e[3],
                "timestamp": e[4]
            }
            for e in data
        ]
    except Exception:
        return []


@app.get("/api/memory/preferences")
def prefs():
    try:
        data = get_preferences()
        return [
            {
                "category": p[0],
                "key": p[1],
                "value": p[2],
                "confidence": p[3]
            }
            for p in data
        ]
    except Exception:
        return []


# ========================
# TASKS
# ========================
@app.get("/api/tasks")
def tasks():
    try:
        data = get_tasks("pending")
        return [
            {
                "id": t[0],
                "title": t[1],
                "priority": t[2],
                "created_at": t[3],
                "due_at": t[4]
            }
            for t in data
        ]
    except Exception:
        return []


# ========================
# CHAT ENGINE
# ========================

# In-memory store of last retrieved chunk_ids per "session" (keyed by query)
# Used for the feedback loop — maps query hash → [chunk_ids]
_last_chunks: dict = {}

@app.post("/api/chat")
async def chat(payload: dict):
    try:
        user_text = payload.get("message", "").strip()
        if not user_text:
            return {"reply": "Say something."}

        save_conversation("user", user_text)
        log_memory_event("conversation", user_text[:80], importance=4)

        if not GROQ_API_KEY:
            return {"reply": "GROQ_API_KEY missing."}

        client = Groq(api_key=GROQ_API_KEY)

        # ── Phase 4+5: Hybrid retrieval ──────────────────────
        from knowledge.retrieval import retrieve, format_context
        from knowledge.feedback import log_query, auto_signal_from_conversation

        retrieved_chunks = retrieve(user_text, n_results=5)
        knowledge_context = format_context(retrieved_chunks)

        # Log retrieved chunks for feedback loop (Phase 6)
        chunk_ids = [c.get("chunk_id", "") for c in retrieved_chunks]
        log_query(user_text, chunk_ids)

        # Auto-signal: if previous query exists, check if this is a follow-up or rephrasing
        prev_query = _last_chunks.get("query")
        prev_chunks = _last_chunks.get("chunks", [])
        if prev_query and prev_chunks:
            auto_signal_from_conversation(prev_query, prev_chunks, user_text)

        # Store current for next turn
        _last_chunks["query"] = user_text
        _last_chunks["chunks"] = retrieved_chunks

        # ── Build prompt ──────────────────────────────────────
        system_prompt = build_system_prompt(query=user_text)

        if knowledge_context:
            system_prompt += (
                "\n\n========================\n"
                "VERIFIED KNOWLEDGE (use ONLY this — cite filename)\n"
                "========================\n"
                + knowledge_context
            )

        history = get_conversation_history(limit=6)

        messages = [{"role": "system", "content": system_prompt}]

        for role, content in history[:-1]:
            messages.append({
                "role": "user" if role == "user" else "assistant",
                "content": content
            })

        messages.append({"role": "user", "content": user_text})

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            max_tokens=500,
            temperature=0.7,
        )

        reply = response.choices[0].message.content

        save_conversation("assistant", reply)
        log_memory_event("conversation", "ORA replied", importance=3)

        # Return chunk_ids so frontend can send feedback signals
        return {
            "reply": reply,
            "chunk_ids": chunk_ids  # frontend can pass these back to /api/feedback
        }

    except Exception:
        print("[CHAT ERROR]", traceback.format_exc())
        return {"reply": "ORA temporarily unavailable."}


# ========================
# KNOWLEDGE BASE
# ========================

@app.post("/api/knowledge/upload")
async def upload_knowledge(file: UploadFile = File(...), tags: str = Form("")):
    """Upload and fully index a document through the pipeline."""
    try:
        filepath = os.path.join(UPLOADS_PATH, file.filename)

        content = await file.read()
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail="File too large (10MB max)")

        with open(filepath, "wb") as f:
            f.write(content)

        # Run full pipeline (extract → chunk → embed → distill → notify)
        result = on_upload(filepath, file.filename, tags=tags)

        log_memory_event("knowledge", f"Indexed: {file.filename}", importance=6)

        return result

    except HTTPException:
        raise
    except Exception:
        print("[UPLOAD ERROR]", traceback.format_exc())
        raise HTTPException(status_code=500, detail="Upload failed")


@app.get("/api/knowledge/documents")
def list_documents():
    """List all indexed documents."""
    try:
        return get_all_documents()
    except Exception:
        return []


@app.delete("/api/knowledge/documents/{filename}")
def remove_document(filename: str):
    """Delete a document and all its chunks, embeddings, and insights."""
    try:
        delete_document(filename)
        log_memory_event("knowledge", f"Deleted: {filename}", importance=4)
        return {"status": "deleted", "filename": filename}
    except Exception:
        raise HTTPException(status_code=500, detail="Delete failed")


@app.get("/api/knowledge/documents/{filename}/insights")
def document_insights(filename: str):
    """Get distilled insights for a specific document."""
    try:
        return get_insights_for_source(filename)
    except Exception:
        return []


# ========================
# FEEDBACK LOOP
# ========================

@app.post("/api/feedback")
async def feedback(payload: dict):
    """
    Receive explicit feedback signal from frontend.
    Called when user clicks thumbs up/down on an ORA response.

    payload: { chunk_ids: [...], query: "...", useful: true/false }
    """
    try:
        chunk_ids = payload.get("chunk_ids", [])
        query = payload.get("query", "")
        useful = payload.get("useful", True)

        for cid in chunk_ids:
            if useful:
                record_useful(cid, query)
            else:
                record_not_useful(cid, query)

        return {"status": "recorded", "chunks": len(chunk_ids)}

    except Exception:
        return {"status": "error"}


# ========================
# CONVERSATIONS
# ========================

@app.get("/api/conversations")
def conversations():
    """Return conversation history for the chat page."""
    try:
        history = get_conversation_history(limit=50)
        return [
            {"role": role, "content": content}
            for role, content in history
        ]
    except Exception:
        return []