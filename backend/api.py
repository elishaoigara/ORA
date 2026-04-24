"""
ORA Backend API — Production (STABLE FINAL)
"""

import os
import traceback
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

import psutil
from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from groq import Groq


# ============================================================
# CONFIG
# ============================================================
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None


# ============================================================
# LIFESPAN (STARTUP)
# ============================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[ORA] Starting up...")

    try:
        from database import init_db, init_tasks_table

        init_db()
        init_tasks_table()

        print("[ORA] Database initialized")
    except Exception:
        print("[ORA ERROR] DB INIT FAILED")
        print(traceback.format_exc())

    # ================= TELEGRAM =================
    try:
        from config import TELEGRAM_BOT_TOKEN

        if TELEGRAM_BOT_TOKEN:
            def start_bot():
                time.sleep(5)
                from telegram_bot import run_telegram_bot

                print("[TELEGRAM] Worker started")

                while True:
                    try:
                        run_telegram_bot()
                    except Exception as e:
                        print("[TELEGRAM ERROR]", e)
                        time.sleep(10)

            threading.Thread(target=start_bot, daemon=True).start()

    except Exception:
        print("[TELEGRAM INIT ERROR]")
        print(traceback.format_exc())

    yield
    print("[ORA] Shutdown complete")


# ============================================================
# APP
# ============================================================
app = FastAPI(title="ORA Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # fine for mobile + dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# HEALTH
# ============================================================
@app.api_route("/api/health", methods=["GET", "HEAD"])
async def health(request: Request):
    return {
        "status": "ORA online",
        "time": datetime.utcnow().isoformat()
    }


@app.get("/")
def root():
    return {"status": "ORA running"}


# ============================================================
# STATUS
# ============================================================
@app.get("/api/status")
def status():
    try:
        return {
            "cpu": psutil.cpu_percent(interval=0.2),
            "ram": psutil.virtual_memory().percent,
            "disk": psutil.disk_usage("/").percent,
            "time": datetime.utcnow().isoformat(),
        }
    except Exception:
        return {"status": "error"}


# ============================================================
# CHAT
# ============================================================
class ChatRequest(BaseModel):
    message: str


@app.post("/api/chat")
async def chat(payload: ChatRequest):
    try:
        if not client:
            return {"reply": "ORA: Missing GROQ_API_KEY"}

        text = payload.message.strip()
        if not text:
            return {"reply": "Empty message."}

        from database import save_conversation, get_conversation_history
        from context import build_system_prompt

        # ===== MEMORY =====
        history = get_conversation_history(limit=8)

        # ===== KNOWLEDGE =====
        knowledge_ctx = ""
        try:
            from knowledge.pipeline import search_and_format
            knowledge_ctx = search_and_format(text, n_results=3) or ""
        except Exception as e:
            print("[KNOWLEDGE ERROR]", e)

        # ===== PROMPT =====
        system_prompt = build_system_prompt(query=text)

        if knowledge_ctx:
            system_prompt += f"\n\nKNOWLEDGE:\n{knowledge_ctx}"

        # ===== BUILD MESSAGES =====
        messages = [{"role": "system", "content": system_prompt}]

        for role, content, _ in history:
            messages.append({
                "role": "user" if role == "user" else "assistant",
                "content": content
            })

        messages.append({"role": "user", "content": text})

        # ===== GROQ CALL =====
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",  # ✅ FIXED MODEL
            messages=messages,
            max_tokens=400,
            temperature=0.4,
        )

        reply = response.choices[0].message.content or "No response"

        # ===== SAVE =====
        save_conversation("user", text)
        save_conversation("assistant", reply)

        return {"reply": reply}

    except Exception:
        print("[CHAT ERROR]")
        print(traceback.format_exc())
        return {"reply": "ORA error. Try again."}


# ============================================================
# CONVERSATIONS
# ============================================================
@app.get("/api/conversations")
def conversations(limit: int = 30):
    try:
        from database import get_conversation_history
        rows = get_conversation_history(limit=limit)

        return [
            {"role": r, "content": c, "timestamp": t}
            for r, c, t in rows
        ]
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

        return [
            {
                "id": r[0],
                "title": r[1],
                "priority": r[2],
                "created_at": r[3],
                "due_at": r[4],
            }
            for r in rows
        ]
    except Exception:
        return []


@app.post("/api/tasks")
def add_task(payload: TaskCreate):
    try:
        from database import add_task
        add_task(payload.title, payload.priority, payload.due_at)
        return {"status": "created"}
    except Exception:
        raise HTTPException(500, "Failed to create task")


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
# ALERTS
# ============================================================
@app.get("/api/alerts")
def alerts():
    try:
        from database import get_recent_alerts
        rows = get_recent_alerts(20)

        return [
            {
                "id": r[0],
                "rule_name": r[1],
                "message": r[2],
                "severity": r[3],
                "timestamp": r[4],
                "acknowledged": bool(r[5]),
            }
            for r in rows
        ]
    except Exception:
        return []


@app.post("/api/alerts/{alert_id}/ack")
def ack(alert_id: int):
    try:
        from database import acknowledge_alert
        acknowledge_alert(alert_id)
        return {"status": "acknowledged"}
    except Exception:
        raise HTTPException(500, "Failed")