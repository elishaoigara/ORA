import os
import ast
import shutil

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# ========================
# FIXED IMPORTS (RENDER SAFE)
# ========================
from backend.database import (
    get_recent_alerts, get_system_stats,
    acknowledge_alert, get_tasks,
    get_conversation_history, save_conversation
)

from backend.memory.profile import get_all_profile
from backend.memory.events import get_recent_events, log_memory_event
from backend.memory.preferences import get_preferences

from backend.context import build_system_prompt
from backend.knowledge import store_document, get_all_documents, delete_document, UPLOADS_PATH

# ========================
# OPTIONAL IMPORT SAFETY
# ========================
try:
    from groq import Groq
except Exception:
    Groq = None


# ========================
# ENV VARIABLES
# ========================
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")


# ========================
# FASTAPI APP
# ========================
app = FastAPI()


# ========================
# CORS CONFIG
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
os.makedirs(UPLOADS_PATH, exist_ok=True)

app.mount(
    "/uploads",
    StaticFiles(directory=UPLOADS_PATH),
    name="uploads"
)


# ========================
# HEALTH CHECK
# ========================
@app.get("/api/health")
def health():
    return {"status": "ORA online"}


# ========================
# SYSTEM STATUS
# ========================
@app.get("/api/status")
def get_status():
    row = get_system_stats()

    if not row:
        return {"status": "warming_up"}

    data = ast.literal_eval(row[0])

    return {
        "cpu": data.get("cpu_percent"),
        "ram": data.get("ram_percent"),
        "disk_free_gb": round(data.get("disk_free_gb", 0), 1),
        "last_updated": row[1]
    }


# ========================
# ALERTS
# ========================
@app.get("/api/alerts")
def get_alerts():
    alerts = get_recent_alerts(20)

    return [
        {
            "id": a[0],
            "rule": a[1],
            "message": a[2],
            "severity": a[3],
            "timestamp": a[4],
            "acknowledged": bool(a[5])
        }
        for a in alerts
    ]


@app.post("/api/alerts/{alert_id}/ack")
def ack_alert(alert_id: int):
    acknowledge_alert(alert_id)
    return {"status": "acknowledged"}


# ========================
# MEMORY
# ========================
@app.get("/api/memory/profile")
def get_profile():
    return get_all_profile()


@app.get("/api/memory/events")
def get_events():
    events = get_recent_events(limit=20)

    return [
        {
            "type": e[0],
            "summary": e[1],
            "importance": e[3],
            "timestamp": e[4]
        }
        for e in events
    ]


@app.get("/api/memory/preferences")
def get_prefs():
    prefs = get_preferences()

    return [
        {
            "category": p[0],
            "key": p[1],
            "value": p[2],
            "confidence": p[3]
        }
        for p in prefs
    ]


# ========================
# TASKS
# ========================
@app.get("/api/tasks")
def get_all_tasks():
    tasks = get_tasks("pending")

    return [
        {
            "id": t[0],
            "title": t[1],
            "priority": t[2],
            "created_at": t[3],
            "due_at": t[4]
        }
        for t in tasks
    ]


# ========================
# CONVERSATIONS
# ========================
@app.get("/api/conversations")
def get_conversations():
    history = get_conversation_history(limit=50)
    return [{"role": r, "content": c} for r, c in history]


# ========================
# CHAT ENGINE
# ========================
@app.post("/api/chat")
async def chat(payload: dict):
    user_text = payload.get("message", "").strip()

    if not user_text:
        return {"reply": "Say something."}

    save_conversation("user", user_text)
    log_memory_event("conversation", user_text[:80], importance=4)

    if not GROQ_API_KEY or Groq is None:
        return {"reply": "Groq API not configured or missing dependency."}

    try:
        client = Groq(api_key=GROQ_API_KEY)

        history = get_conversation_history(limit=6)

        messages = [
            {
                "role": "system",
                "content": build_system_prompt(query=user_text)
            }
        ]

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

    except Exception as e:
        return {"reply": f"ORA error: {str(e)[:150]}"}


# ========================
# KNOWLEDGE UPLOAD
# ========================
@app.post("/api/knowledge/upload")
async def upload_document(
    file: UploadFile = File(...),
    tags: str = Form("")
):
    filename = file.filename
    filepath = os.path.join(UPLOADS_PATH, filename)

    with open(filepath, "wb") as f:
        shutil.copyfileobj(file.file, f)

    chunks = store_document(filepath, filename, tags=tags)

    return {
        "status": "stored",
        "filename": filename,
        "chunks": chunks
    }


@app.get("/api/knowledge/documents")
def list_documents():
    return get_all_documents()


@app.delete("/api/knowledge/documents/{filename}")
def remove_document(filename: str):
    deleted = delete_document(filename)

    filepath = os.path.join(UPLOADS_PATH, filename)
    if os.path.exists(filepath):
        os.remove(filepath)

    return {"deleted_chunks": deleted}