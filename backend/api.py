"""
ORA Backend API — Production
"""

import os
import json
import traceback
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

import psutil
from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from groq import Groq


# ─────────────────────────────────────────────────────────────
# LIFESPAN (replaces deprecated @app.on_event("startup"))
# ─────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    from config import DATA_DIR
    os.makedirs(DATA_DIR, exist_ok=True)

    try:
        from database import init_db, init_tasks_table
        init_db()
        init_tasks_table()
        print("[ORA] DB initialized OK")
    except Exception as e:
        print("[ORA DB INIT ERROR]", e)
        traceback.print_exc()

    try:
        from config import TELEGRAM_BOT_TOKEN
        if TELEGRAM_BOT_TOKEN:
            def _bot():
                time.sleep(5)
                from telegram_bot import run_telegram_bot
                while True:
                    try:
                        run_telegram_bot()
                    except Exception as exc:
                        print("[TELEGRAM ERROR]", exc)
                        time.sleep(10)
            threading.Thread(target=_bot, daemon=True).start()
            print("[ORA] Telegram thread started")
    except Exception as e:
        print("[ORA TELEGRAM SKIP]", e)

    yield  # app runs here


# ─────────────────────────────────────────────────────────────
# APP
# ─────────────────────────────────────────────────────────────
app = FastAPI(title="ORA Backend", lifespan=lifespan)

# Mobile app is not a browser — CORS is not enforced by RN.
# Keep specific origins for any web frontend, drop wildcard
# when you're ready to lock down.
ALLOWED_ORIGINS = [
    "https://ora-oovf.onrender.com",
    "https://ora-rho.vercel.app",
    "https://ora.vercel.app",
    "http://localhost:3000",
    "http://localhost:5173",
    "*",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None


# ─────────────────────────────────────────────────────────────
# HEALTH / ROOT
# ─────────────────────────────────────────────────────────────
@app.api_route("/api/health", methods=["GET", "HEAD"])
async def health(request: Request):
    return {"status": "ORA online", "ts": datetime.utcnow().isoformat()}

@app.get("/")
def root():
    return {"status": "ORA running"}


# ─────────────────────────────────────────────────────────────
# STATUS
# ─────────────────────────────────────────────────────────────
@app.get("/api/status")
def status():
    try:
        return {
            "cpu":  psutil.cpu_percent(interval=0.2),
            "ram":  psutil.virtual_memory().percent,
            "disk": psutil.disk_usage("/").percent,
            "time": datetime.utcnow().isoformat(),
        }
    except Exception:
        return {"status": "error"}


# ─────────────────────────────────────────────────────────────
# CHAT
# ─────────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    message: str

@app.post("/api/chat")
async def chat(payload: ChatRequest):
    try:
        if not client:
            return {"reply": "ORA: Groq API key not configured."}

        text = payload.message.strip()
        if not text:
            return {"reply": "Empty message."}

        from database import save_conversation, get_conversation_history
        from context import build_system_prompt

        history = get_conversation_history(limit=8)

        knowledge_ctx = ""
        try:
            from knowledge.pipeline import search_and_format
            knowledge_ctx = search_and_format(text, n_results=3) or ""
        except Exception:
            pass

        system_prompt = build_system_prompt(query=text)
        if knowledge_ctx:
            system_prompt += f"\n\nKNOWLEDGE:\n{knowledge_ctx}"

        messages = [{"role": "system", "content": system_prompt}]
        for role, content, _ in history:
            messages.append({
                "role": "user" if role == "user" else "assistant",
                "content": content,
            })
        messages.append({"role": "user", "content": text})

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            max_tokens=400,
            temperature=0.4,
        )
        reply = response.choices[0].message.content

        save_conversation("user", text)
        save_conversation("assistant", reply)

        return {"reply": reply}

    except Exception:
        traceback.print_exc()
        return {"reply": "ORA encountered an error. Please try again."}


# ─────────────────────────────────────────────────────────────
# CONVERSATIONS
# ─────────────────────────────────────────────────────────────
@app.get("/api/conversations")
def get_conversations(limit: int = 30):
    try:
        from database import get_conversation_history
        rows = get_conversation_history(limit=limit)
        return [{"role": r, "content": c, "timestamp": ts} for r, c, ts in rows]
    except Exception:
        return []


# ─────────────────────────────────────────────────────────────
# TASKS
# ─────────────────────────────────────────────────────────────
class TaskCreate(BaseModel):
    title: str
    priority: str = "medium"
    due_at: Optional[str] = None  # Optional[str] — safe on Python 3.9

@app.get("/api/tasks")
def list_tasks(status: str = "pending"):
    try:
        from database import get_tasks
        rows = get_tasks(status=status)
        return [
            {"id": r[0], "title": r[1], "priority": r[2], "created_at": r[3], "due_at": r[4]}
            for r in rows
        ]
    except Exception:
        traceback.print_exc()
        return []

@app.post("/api/tasks")
def create_task(payload: TaskCreate):
    try:
        from database import add_task
        add_task(payload.title, payload.priority, payload.due_at)
        return {"status": "created"}
    except Exception:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Failed to create task")

# matches mobile: POST /api/tasks/{id}/complete
@app.post("/api/tasks/{task_id}/complete")
def complete_task_route(task_id: int):
    try:
        from database import complete_task
        complete_task(task_id)
        return {"status": "done"}
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to complete task")

@app.delete("/api/tasks/{task_id}")
def remove_task(task_id: int):
    try:
        from database import delete_task
        delete_task(task_id)
        return {"status": "deleted"}
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to delete task")


# ─────────────────────────────────────────────────────────────
# ALERTS
# ─────────────────────────────────────────────────────────────
@app.get("/api/alerts")
def list_alerts(limit: int = 20):
    try:
        from database import get_recent_alerts
        rows = get_recent_alerts(limit=limit)
        return [
            {
                "id":           r[0],
                "rule_name":    r[1],
                "message":      r[2],
                "severity":     r[3],
                "timestamp":    r[4],
                "acknowledged": bool(r[5]),
            }
            for r in rows
        ]
    except Exception:
        traceback.print_exc()
        return []

# matches mobile: POST /api/alerts/{id}/ack
@app.post("/api/alerts/{alert_id}/ack")
def ack_alert(alert_id: int):
    try:
        from database import acknowledge_alert
        acknowledge_alert(alert_id)
        return {"status": "acknowledged"}
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to acknowledge alert")

# matches mobile: POST /api/alerts/ack-all
@app.post("/api/alerts/ack-all")
def ack_all_alerts():
    try:
        from database import get_conn, close_conn
        conn = get_conn()
        c = conn.cursor()           # named cursor — not GC'd before commit
        c.execute("UPDATE alerts SET acknowledged=1")
        conn.commit()
        close_conn()
        return {"status": "all acknowledged"}
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to acknowledge all alerts")


# ─────────────────────────────────────────────────────────────
# MEMORY
# ─────────────────────────────────────────────────────────────
@app.get("/api/memory/preferences")
def get_preferences():
    try:
        from memory.preferences import get_preferences
        rows = get_preferences()
        return [{"category": r[0], "key": r[1], "value": r[2], "confidence": r[3]} for r in rows]
    except Exception:
        return []

@app.get("/api/memory/profile")
def get_profile():
    try:
        from memory.profile import get_all_profile
        return get_all_profile()
    except Exception:
        return {}

@app.get("/api/memory/events")
def get_events(limit: int = 20):
    try:
        from memory.events import get_recent_events
        rows = get_recent_events(limit=limit)
        return [
            {"event_type": r[0], "summary": r[1], "detail": r[2],
             "importance": r[3], "timestamp": r[4]}
            for r in rows
        ]
    except Exception:
        return []


# ─────────────────────────────────────────────────────────────
# KNOWLEDGE
# ─────────────────────────────────────────────────────────────
@app.get("/api/knowledge/documents")
def list_documents():
    try:
        from knowledge.pipeline import get_all_documents
        return get_all_documents()
    except Exception:
        return []

@app.post("/api/knowledge/upload")
async def upload_document(
    file: UploadFile = File(...),
    tags: str = Form(""),
):
    try:
        from config import UPLOADS_DIR
        from knowledge.pipeline import on_upload

        dest = os.path.join(UPLOADS_DIR, file.filename)
        with open(dest, "wb") as f:
            f.write(await file.read())

        return on_upload(dest, file.filename, tags=tags)
    except Exception:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Upload failed")

@app.delete("/api/knowledge/documents/{filename}")
def delete_document(filename: str):
    try:
        from knowledge.pipeline import delete_document as _del
        _del(filename)
        return {"status": "deleted"}
    except Exception:
        raise HTTPException(status_code=500, detail="Delete failed")


# ─────────────────────────────────────────────────────────────
# MPESA
# ─────────────────────────────────────────────────────────────
@app.get("/api/mpesa/summary")
def mpesa_summary():
    try:
        from mpesa_engine import get_summary
        return get_summary()
    except Exception:
        return {"total_in": 0, "total_out": 0, "transactions": [], "note": "M-Pesa not configured"}


# ─────────────────────────────────────────────────────────────
# THE NUMBER
# ─────────────────────────────────────────────────────────────
@app.get("/api/the-number")
def the_number():
    try:
        from database import get_conn, close_conn
        conn = get_conn()
        c = conn.cursor()
        today = datetime.utcnow().strftime("%Y-%m-%d")
        c.execute("SELECT value FROM profile WHERE key=?", (f"daily_number_{today}",))
        row = c.fetchone()
        close_conn()
        if row:
            return {"number": row[0], "date": today}
        return {"number": None, "date": today, "note": "No number set for today"}
    except Exception:
        return {"number": None}


# ─────────────────────────────────────────────────────────────
# BRIEFING
# ─────────────────────────────────────────────────────────────
@app.get("/api/briefing")
def get_briefing():
    try:
        from briefing import build_briefing
        return {"briefing": build_briefing()}
    except Exception:
        return {"briefing": "Briefing unavailable."}