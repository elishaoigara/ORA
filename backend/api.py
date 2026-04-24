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

    # INIT M-PESA TABLE
    try:
        from mpesa_engine import init_mpesa_table
        init_mpesa_table()
        print("[ORA] M-Pesa table ready")
    except Exception:
        print("[MPESA INIT ERROR]")
        print(traceback.format_exc())

    # INIT PROFILE DEFAULTS
    try:
        from memory.profile import init_profile
        init_profile()
        print("[ORA] Profile initialized")
    except Exception:
        print("[PROFILE INIT ERROR]")
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
            # FIX: search_and_format lives in knowledge.pipeline, not knowledge.retrieval
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
# CONVERSATIONS  ← NEW
# ============================================================
@app.get("/api/conversations")
def get_conversations(limit: int = 40):
    try:
        from database import get_conversation_history
        rows = get_conversation_history(limit=limit)
        return [
            {"role": r[0], "content": r[1], "timestamp": r[2]}
            for r in rows
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
# THE NUMBER (AI-PRIORITIZED TOP TASK)  ← NEW
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
            "id": task_id,
            "title": title,
            "priority": priority,
            "due_at": due_at,
            "overdue": overdue,
            "score": score_task(top),
            "reason": _score_reason(top),
            "status": "ok",
        }
    except Exception:
        print("[THE-NUMBER ERROR]")
        print(traceback.format_exc())
        return {"status": "empty"}


def _score_reason(task):
    _, title, priority, _, due_at = task
    parts = []
    if priority == "high":
        parts.append("high priority")
    if due_at:
        try:
            diff = (datetime.fromisoformat(due_at) - datetime.now()).total_seconds()
            if diff < 0:
                parts.append("overdue")
            elif diff < 3600:
                parts.append("due within 1h")
            elif diff < 86400:
                parts.append("due today")
        except Exception:
            pass
    if "urgent" in title.lower():
        parts.append("marked urgent")
    return ", ".join(parts) if parts else "top pending task"


# ============================================================
# ALERTS
# ============================================================
@app.get("/api/alerts")
def alerts(limit: int = 10):
    try:
        from database import get_recent_alerts
        rows = get_recent_alerts(limit)

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
def ack_alert(alert_id: int, feedback: Optional[str] = None):
    try:
        from database import acknowledge_alert
        acknowledge_alert(alert_id, feedback)
        return {"status": "acknowledged"}
    except Exception:
        raise HTTPException(500, "Failed")


# ============================================================
# M-PESA  ← NEW
# ============================================================
class MpesaSMS(BaseModel):
    sms: str


@app.post("/api/mpesa/ingest")
def mpesa_ingest(payload: MpesaSMS):
    try:
        from mpesa_engine import ingest_sms
        result = ingest_sms(payload.sms)
        return result
    except Exception:
        raise HTTPException(500, "M-Pesa ingest failed")


@app.get("/api/mpesa/summary")
def mpesa_summary():
    try:
        from mpesa_engine import (
            get_today_spend,
            get_average_daily_spend,
            get_daily_summary,
            get_recent_transactions,
            get_recurring_patterns,
        )
        return {
            "today": get_today_spend(),
            "average_daily": get_average_daily_spend(),
            "last_7_days": get_daily_summary(days=7),
            "recent_transactions": get_recent_transactions(limit=10),
            "recurring": get_recurring_patterns(),
        }
    except Exception:
        print("[MPESA SUMMARY ERROR]")
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
# MEMORY  ← NEW
# ============================================================
@app.get("/api/memory/profile")
def memory_profile():
    try:
        from memory.profile import get_all_profile
        profile = get_all_profile()
        return profile
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
        return [
            {"category": r[0], "key": r[1], "value": r[2], "confidence": r[3]}
            for r in rows
        ]
    except Exception:
        return []


@app.get("/api/memory/events")
def memory_events(limit: int = 20, event_type: Optional[str] = None):
    try:
        from memory.events import get_recent_events
        rows = get_recent_events(limit=limit, event_type=event_type)
        return [
            {
                "event_type": r[0],
                "summary": r[1],
                "detail": r[2],
                "importance": r[3],
                "timestamp": r[4],
            }
            for r in rows
        ]
    except Exception:
        return []


@app.get("/api/memory/important")
def memory_important(min_importance: int = 7, limit: int = 10):
    try:
        from memory.events import get_important_events
        rows = get_important_events(min_importance=min_importance, limit=limit)
        return [
            {
                "event_type": r[0],
                "summary": r[1],
                "detail": r[2],
                "importance": r[3],
                "timestamp": r[4],
            }
            for r in rows
        ]
    except Exception:
        return []


# ============================================================
# KNOWLEDGE  ← NEW
# ============================================================
@app.get("/api/knowledge/documents")
def knowledge_documents():
    try:
        from knowledge.pipeline import get_all_documents
        return get_all_documents()
    except Exception:
        print("[KNOWLEDGE LIST ERROR]")
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