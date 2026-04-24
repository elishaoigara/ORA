"""
ORA Backend API — Render Optimized (Free Tier Safe)
"""

import os
import traceback
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

import psutil
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from groq import Groq


# ============================================================
# CONFIG
# ============================================================
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

MAX_TOKENS = 250          # ↓ reduce cost + speed
MODEL_NAME = "llama-3.3-70b-versatile"


# ============================================================
# LIFESPAN (LIGHTWEIGHT STARTUP)
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
        print("[DB ERROR]")
        print(traceback.format_exc())

    # TELEGRAM (LOW CPU MODE)
    try:
        from config import TELEGRAM_BOT_TOKEN

        if TELEGRAM_BOT_TOKEN:

            def telegram_worker():
                from telegram_bot import run_telegram_bot

                print("[TELEGRAM] Worker started")

                while True:
                    try:
                        run_telegram_bot()
                        time.sleep(2)  # 🔥 prevents CPU spike
                    except Exception as e:
                        print("[TELEGRAM ERROR]", e)
                        time.sleep(5)

            threading.Thread(target=telegram_worker, daemon=True).start()

    except Exception:
        print("[TELEGRAM INIT ERROR]")
        print(traceback.format_exc())

    yield
    print("[ORA] Shutdown")


# ============================================================
# APP
# ============================================================
app = FastAPI(title="ORA Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # mobile safe
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# HEALTH (FAST)
# ============================================================
@app.api_route("/api/health", methods=["GET", "HEAD"])
async def health(request: Request):
    return {"status": "ok"}


@app.get("/")
def root():
    return {"status": "ORA running"}


# ============================================================
# STATUS (LIGHTWEIGHT)
# ============================================================
@app.get("/api/status")
def status():
    return {
        "cpu": psutil.cpu_percent(interval=0.1),  # ↓ faster
        "ram": psutil.virtual_memory().percent,
        "time": datetime.utcnow().isoformat(),
    }


# ============================================================
# CHAT (OPTIMIZED)
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

        # ===== MEMORY (LIMITED) =====
        history = get_conversation_history(limit=5)  # 🔥 smaller

        # ===== KNOWLEDGE (SAFE + LIGHT) =====
        knowledge_ctx = ""

        try:
            from knowledge.pipeline import search_and_format
            knowledge_ctx = search_and_format(text, n_results=2) or ""
        except Exception:
            pass  # silent fail (important for stability)

        # ===== PROMPT =====
        system_prompt = build_system_prompt(query=text)

        if knowledge_ctx:
            system_prompt += f"\n\nKNOWLEDGE:\n{knowledge_ctx[:500]}"  # 🔥 truncate

        messages = [{"role": "system", "content": system_prompt}]

        for role, content, _ in history:
            messages.append({
                "role": "user" if role == "user" else "assistant",
                "content": content[:300]  # 🔥 limit memory size
            })

        messages.append({"role": "user", "content": text})

        # ===== GROQ CALL (CONTROLLED) =====
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            max_tokens=MAX_TOKENS,
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
        raise HTTPException(500, "Failed")


# ============================================================
# ALERTS
# ============================================================
@app.get("/api/alerts")
def alerts():
    try:
        from database import get_recent_alerts
        rows = get_recent_alerts(10)  # 🔥 reduced load

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