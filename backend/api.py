import os
import json
import uuid
import traceback
import threading
import time
import psutil
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

# ========================
# BACKGROUND JOB REGISTRY
# ========================
_upload_jobs: dict = {}
_job_executor = ThreadPoolExecutor(max_workers=2)

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
    log_event,
    log_alert
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

from config import UPLOADS_DIR as UPLOADS_PATH


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
# SCHEDULER + CORE ORCHESTRATOR
# ========================
def start_ora_scheduler():
    try:
        from scheduler import start_scheduler
        from briefing import send_morning_briefing
        from core import evaluate_state
        from mpesa_engine import init_mpesa_table

        init_mpesa_table()

        jobs = [
            {"hour": 7, "minute": 0, "fn": send_morning_briefing, "name": "morning_briefing"},
            {"hour": 20, "minute": 0, "fn": lambda: log_memory_event("scheduler", "Evening check", 4), "name": "evening_check"},
        ]
        start_scheduler(jobs)
        print("[ORA] Scheduler activated")

        def core_loop():
            while True:
                try:
                    evaluate_state()
                except Exception as e:
                    print(f"[CORE LOOP ERROR] {e}")
                time.sleep(1800)

        threading.Thread(target=core_loop, daemon=True).start()
        print("[ORA] Core orchestrator running")
    except Exception as e:
        print(f"[SCHEDULER ERROR] {e}")


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

        threading.Thread(target=monitoring_loop, daemon=True).start()
        print("[ORA] Monitoring thread started")

        threading.Thread(target=start_telegram, daemon=True).start()

        threading.Thread(target=start_ora_scheduler, daemon=True).start()

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

        from knowledge.retrieval import retrieve, format_context
        from knowledge.feedback import log_query, auto_signal_from_conversation

        retrieved_chunks = retrieve(user_text, n_results=5)
        knowledge_context = format_context(retrieved_chunks)

        chunk_ids = [c.get("chunk_id", "") for c in retrieved_chunks]
        log_query(user_text, chunk_ids)

        prev_query = _last_chunks.get("query")
        prev_chunks = _last_chunks.get("chunks", [])
        if prev_query and prev_chunks:
            auto_signal_from_conversation(prev_query, prev_chunks, user_text)

        _last_chunks["query"] = user_text
        _last_chunks["chunks"] = retrieved_chunks

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

        # FIX: get_conversation_history returns (role, content, timestamp) — unpack all 3
        for role, content, _timestamp in history[:-1]:
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

        return {
            "reply": reply,
            "chunk_ids": chunk_ids
        }

    except Exception:
        print("[CHAT ERROR]", traceback.format_exc())
        return {"reply": "ORA temporarily unavailable."}


# ========================
# KNOWLEDGE BASE
# ========================

def _run_pipeline_job(job_id: str, filepath: str, filename: str, tags: str):
    _upload_jobs[job_id]["status"] = "processing"
    try:
        result = on_upload(filepath, filename, tags=tags)
        _upload_jobs[job_id].update({
            "status": "done",
            "result": result,
            "finished_at": datetime.now().isoformat()
        })
        log_memory_event("knowledge", f"Indexed: {filename}", importance=6)
    except Exception:
        err = traceback.format_exc()
        print(f"[UPLOAD JOB {job_id}] ERROR:\n{err}")
        _upload_jobs[job_id].update({
            "status": "error",
            "error": err,
            "finished_at": datetime.now().isoformat()
        })


@app.post("/api/knowledge/upload")
async def upload_knowledge(file: UploadFile = File(...), tags: str = Form("")):
    try:
        content = await file.read()
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail="File too large (10MB max)")

        safe_name = os.path.basename(file.filename or "upload")
        filepath = os.path.join(UPLOADS_PATH, safe_name)

        with open(filepath, "wb") as f:
            f.write(content)

        job_id = str(uuid.uuid4())
        _upload_jobs[job_id] = {
            "status": "queued",
            "filename": safe_name,
            "started_at": datetime.now().isoformat(),
            "result": None,
            "error": None
        }

        _job_executor.submit(_run_pipeline_job, job_id, filepath, safe_name, tags)

        return {
            "status": "queued",
            "job_id": job_id,
            "filename": safe_name,
            "message": "Indexing started. Poll /api/knowledge/status/{job_id} for progress."
        }

    except HTTPException:
        raise
    except Exception:
        print("[UPLOAD ERROR]", traceback.format_exc())
        raise HTTPException(status_code=500, detail="Upload failed")


@app.get("/api/knowledge/status/{job_id}")
def upload_status(job_id: str):
    job = _upload_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/api/knowledge/documents")
def list_documents():
    try:
        return get_all_documents()
    except Exception:
        return []


@app.delete("/api/knowledge/documents/{filename}")
def remove_document(filename: str):
    try:
        delete_document(filename)
        log_memory_event("knowledge", f"Deleted: {filename}", importance=4)
        return {"status": "deleted", "filename": filename}
    except Exception:
        raise HTTPException(status_code=500, detail="Delete failed")


@app.get("/api/knowledge/documents/{filename}/insights")
def document_insights(filename: str):
    try:
        return get_insights_for_source(filename)
    except Exception:
        return []


# ========================
# FEEDBACK LOOP
# ========================

@app.post("/api/feedback")
async def feedback(payload: dict):
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
    try:
        history = get_conversation_history(limit=50)
        # FIX: get_conversation_history returns (role, content, timestamp) — unpack all 3
        return [
            {"role": role, "content": content}
            for role, content, _timestamp in history
        ]
    except Exception:
        return []


# ========================
# THE NUMBER
# ========================

@app.get("/api/the-number")
def the_number():
    try:
        from core import get_the_number
        result = get_the_number()
        if result:
            return result
        return {"status": "empty", "message": "No tasks queued"}
    except Exception:
        return {"status": "error", "detail": traceback.format_exc()}


# ========================
# M-PESA ENGINE
# ========================

@app.post("/api/mpesa/ingest")
async def mpesa_ingest(payload: dict):
    try:
        from mpesa_engine import ingest_sms
        sms = payload.get("sms", "").strip()
        if not sms:
            return {"status": "error", "message": "No SMS provided"}
        result = ingest_sms(sms)

        if result.get("alert"):
            alert = result["alert"]
            log_alert(
                rule_name="mpesa_spend_alert",
                message=alert["message"],
                severity=alert["severity"]
            )
            try:
                from telegram_bot import notify
                notify(alert["message"])
            except Exception:
                pass

        return result
    except Exception:
        return {"status": "error", "detail": traceback.format_exc()}


@app.get("/api/mpesa/summary")
def mpesa_summary():
    try:
        from mpesa_engine import get_today_spend, get_average_daily_spend, get_daily_summary
        today = get_today_spend()
        avg = get_average_daily_spend()
        daily = get_daily_summary(days=7)
        return {
            "today": today,
            "average_daily": round(avg, 2),
            "last_7_days": daily
        }
    except Exception:
        return {"status": "error"}


@app.get("/api/mpesa/transactions")
def mpesa_transactions(limit: int = 20):
    try:
        from mpesa_engine import get_recent_transactions
        return get_recent_transactions(limit=limit)
    except Exception:
        return []


@app.get("/api/mpesa/recurring")
def mpesa_recurring():
    try:
        from mpesa_engine import get_recurring_patterns
        return get_recurring_patterns()
    except Exception:
        return []