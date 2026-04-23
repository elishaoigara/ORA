import os
import json
import uuid
import traceback
import time
import psutil

from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from groq import Groq
from apscheduler.schedulers.background import BackgroundScheduler

# ========================
# CONFIG
# ========================
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
FRONTEND_URL = os.getenv("FRONTEND_URL", "*")

MAX_FILE_SIZE = 10 * 1024 * 1024
UPLOADS_PATH = os.getenv("UPLOADS_DIR", "uploads")

os.makedirs(UPLOADS_PATH, exist_ok=True)

# ========================
# GLOBAL CLIENT (FIXED)
# ========================
client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# ========================
# BACKGROUND JOB STATE
# ========================
_upload_jobs = {}

# ========================
# IMPORTS (your modules)
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

from memory.events import get_recent_events, log_memory_event
from memory.profile import get_all_profile, init_profile
from memory.preferences import get_preferences

from context import build_system_prompt

from knowledge import (
    store_document,
    get_all_documents,
    delete_document,
    search_and_format,
    on_upload,
    get_insights_for_source
)

# ========================
# SCHEDULER (APScheduler)
# ========================
scheduler = BackgroundScheduler()


# ========================
# SYSTEM MONITOR JOB (REPLACED THREAD LOOP)
# ========================
def system_monitor_job():
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


# ========================
# CORE LOOP JOB (SCHEDULER SAFE VERSION)
# ========================
def core_job():
    try:
        from core import evaluate_state
        evaluate_state()
    except Exception as e:
        print("[CORE ERROR]", e)


# ========================
# INIT SCHEDULER
# ========================
def init_scheduler():
    # system monitoring every 5 sec
    scheduler.add_job(
        system_monitor_job,
        trigger="interval",
        seconds=5,
        id="system_monitor"
    )

    # core evaluation every 30 min
    scheduler.add_job(
        core_job,
        trigger="interval",
        seconds=1800,
        id="core_loop"
    )

    scheduler.start()
    print("[ORA] Scheduler started")


# ========================
# BACKGROUND KNOWLEDGE PIPELINE
# ========================
def run_pipeline_job(job_id: str, filepath: str, filename: str, tags: str):
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
        _upload_jobs[job_id].update({
            "status": "error",
            "error": err,
            "finished_at": datetime.now().isoformat()
        })


# ========================
# FASTAPI APP
# ========================
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    init_tasks_table()
    init_profile()

    log_memory_event("system", "ORA started", importance=6)

    init_scheduler()

    yield

    scheduler.shutdown()


app = FastAPI(title="ORA Backend", lifespan=lifespan)

# ========================
# CORS
# ========================
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========================
# STATIC FILES
# ========================
app.mount("/uploads", StaticFiles(directory=UPLOADS_PATH), name="uploads")


# ========================
# HEALTH
# ========================
@app.get("/")
def root():
    return {"status": "ORA backend running"}


@app.get("/api/health")
def health():
    return {"status": "ORA online"}


# ========================
# CHAT (IMPROVED)
# ========================
_last_chunks = {}

@app.post("/api/chat")
async def chat(payload: dict):
    try:
        if not client:
            return {"reply": "GROQ not configured"}

        user_text = payload.get("message", "").strip()
        if not user_text:
            return {"reply": "Say something."}

        save_conversation("user", user_text)
        log_memory_event("conversation", user_text[:80], importance=4)

        system_prompt = build_system_prompt(user_text)

        history = get_conversation_history(limit=6)

        messages = [{"role": "system", "content": system_prompt}]

        for role, content, _ in history:
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

        return {"reply": reply}

    except Exception:
        print(traceback.format_exc())
        return {"reply": "ORA temporarily unavailable."}


# ========================
# KNOWLEDGE UPLOAD (FIXED: BackgroundTasks)
# ========================
@app.post("/api/knowledge/upload")
async def upload_knowledge(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    tags: str = Form("")
):
    content = await file.read()

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File too large")

    filename = os.path.basename(file.filename)
    filepath = os.path.join(UPLOADS_PATH, filename)

    with open(filepath, "wb") as f:
        f.write(content)

    job_id = str(uuid.uuid4())

    _upload_jobs[job_id] = {
        "status": "queued",
        "filename": filename,
        "started_at": datetime.now().isoformat()
    }

    background_tasks.add_task(
        run_pipeline_job,
        job_id,
        filepath,
        filename,
        tags
    )

    return {"status": "queued", "job_id": job_id}


@app.get("/api/knowledge/status/{job_id}")
def job_status(job_id: str):
    return _upload_jobs.get(job_id, {"error": "not found"})


@app.get("/api/knowledge/documents")
def list_docs():
    return get_all_documents()


@app.delete("/api/knowledge/documents/{filename}")
def delete_doc(filename: str):
    delete_document(filename)
    return {"deleted": filename}


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
            "cpu": data.get("cpu_percent"),
            "ram": data.get("ram_percent"),
            "disk_free_gb": data.get("disk_free_gb"),
            "last_updated": row[1]
        }

    except Exception:
        return {"status": "error"}


# ========================
# ALERTS
# ========================
@app.get("/api/alerts")
def alerts():
    return get_recent_alerts(20)


@app.post("/api/alerts/{alert_id}/ack")
def ack(alert_id: int):
    acknowledge_alert(alert_id)
    return {"status": "acknowledged"}


# ========================
# MEMORY
# ========================
@app.get("/api/memory/profile")
def profile():
    return get_all_profile()


@app.get("/api/memory/events")
def events():
    return get_recent_events(limit=20)


@app.get("/api/memory/preferences")
def prefs():
    return get_preferences()


# ========================
# TASKS
# ========================
@app.get("/api/tasks")
def tasks():
    return get_tasks("pending")


# ========================
# FEEDBACK
# ========================
@app.post("/api/feedback")
def feedback(payload: dict):
    return {"status": "ok"}


# ========================
# CONVERSATIONS
# ========================
@app.get("/api/conversations")
def conversations():
    return [
        {"role": r, "content": c}
        for r, c, _ in get_conversation_history(limit=50)
    ]