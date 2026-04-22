import os
import json
import shutil
import uuid
import traceback

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
    init_tasks_table
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
    UPLOADS_PATH
)

# ========================
# ENV
# ========================
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
FRONTEND_URL = os.getenv("FRONTEND_URL", "*")

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


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
    except Exception as e:
        print("[INIT ERROR]", traceback.format_exc())

    yield


app = FastAPI(title="ORA Backend", lifespan=lifespan)


# ========================
# CORS
# ========================
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL] if FRONTEND_URL != "*" else ["*"],
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
            "cpu": data.get("cpu_percent"),
            "ram": data.get("ram_percent"),
            "disk_free_gb": data.get("disk_free_gb"),
            "last_updated": row[1]
        }

    except Exception as e:
        return {"status": "error", "detail": str(e)}


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
    except Exception as e:
        return {"error": str(e)}


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


@app.get("/api/memory/preferences")
def prefs():
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


# ========================
# TASKS
# ========================
@app.get("/api/tasks")
def tasks():
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


# ========================
# CHAT HISTORY
# ========================
@app.get("/api/conversations")
def conversations():
    data = get_conversation_history(limit=50)
    return [{"role": r, "content": c} for r, c in data]


# ========================
# CHAT ENGINE (STABLE + GROUNDED)
# ========================
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

        # 🔥 KNOWLEDGE RETRIEVAL (anti hallucination)
        knowledge_context = search_and_format(user_text, n_results=4)

        system_prompt = build_system_prompt(query=user_text)

        if knowledge_context:
            system_prompt += "\n\n" + knowledge_context
        else:
            system_prompt += "\n\nNo relevant documents found in memory."

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

        return {"reply": reply}

    except Exception:
        print("[CHAT ERROR]", traceback.format_exc())
        return {"reply": "ORA temporarily unavailable."}


# ========================
# KNOWLEDGE UPLOAD
# ========================
def safe_filename(name: str):
    return f"{uuid.uuid4().hex}_{os.path.basename(name)}"


@app.post("/api/knowledge/upload")
async def upload(file: UploadFile = File(...), tags: str = Form("")):
    try:
        if not file:
            raise HTTPException(status_code=400, detail="No file provided")

        filename = safe_filename(file.filename)
        filepath = os.path.join(UPLOADS_PATH, filename)

        size = 0

        with open(filepath, "wb") as f:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)

                if size > MAX_FILE_SIZE:
                    os.remove(filepath)
                    raise HTTPException(status_code=413, detail="File too large")

                f.write(chunk)

        result = store_document(filepath, filename, tags=tags)

        return {
            "status": "stored",
            "filename": filename,
            "chunks": result
        }

    except Exception:
        print("[UPLOAD ERROR]", traceback.format_exc())
        return {"error": "Upload failed"}


# ========================
# KNOWLEDGE BASE
# ========================
@app.get("/api/knowledge/documents")
def documents():
    return get_all_documents()


@app.delete("/api/knowledge/documents/{filename}")
def delete_doc(filename: str):
    delete_document(filename)

    path = os.path.join(UPLOADS_PATH, filename)
    if os.path.exists(path):
        os.remove(path)

    return {"status": "deleted"}