"""
ORA Backend API — v3 (Phase 1 + 2)
Render free tier safe — every upgrade has zero extra RAM cost.
"""

import os
import traceback
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Optional

import psutil
import requests
from fastapi import FastAPI, Request, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from groq import Groq

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
ALLOWED_UPLOAD_TYPES = {".pdf", ".docx", ".txt", ".md"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[ORA] Starting...")
    for fn, label in [
        (lambda: __import__('database').init_db() or __import__('database').init_tasks_table(), "DB"),
        (lambda: __import__('mpesa_engine').init_mpesa_table(), "M-Pesa"),
        (lambda: __import__('memory.profile', fromlist=['init_profile']).init_profile(), "Profile"),
        (lambda: __import__('knowledge.embeddings', fromlist=['init_vector_db']).init_vector_db(), "Knowledge DB"),
        (lambda: __import__('intelligence.goals_engine', fromlist=['init_goals_table']).init_goals_table(), "Goals"),
    ]:
        try:
            fn()
            print(f"[ORA] {label} ready")
        except Exception:
            print(f"[ORA] {label} init error")
            print(traceback.format_exc())

    try:
        from ora_scheduler import start_scheduler
        from intelligence.pattern_engine import run_pattern_analysis
        from intelligence.prediction_engine import run_predictions
        from intelligence.goals_engine import run_goal_checkin
        start_scheduler([
            {"hour": 7,  "minute": 0,  "fn": run_predictions,      "name": "morning_preds"},
            {"hour": 18, "minute": 0,  "fn": run_predictions,      "name": "evening_preds"},
            {"hour": 2,  "minute": 30, "fn": run_pattern_analysis,  "name": "daily_patterns"},
            {"hour": 8,  "minute": 30, "fn": run_goal_checkin,     "name": "weekly_goals"},
        ])
        print("[ORA] Scheduler started")
    except Exception:
        print("[SCHEDULER ERROR]")
        print(traceback.format_exc())

    try:
        from config import TELEGRAM_BOT_TOKEN
        if TELEGRAM_BOT_TOKEN:
            def _tg():
                from telegram_bot import run_telegram_bot
                while True:
                    try:
                        run_telegram_bot()
                        time.sleep(2)
                    except Exception as e:
                        print("[TELEGRAM ERROR]", e)
                        time.sleep(5)
            threading.Thread(target=_tg, daemon=True).start()
    except Exception:
        print(traceback.format_exc())

    # ── Keep-alive (prevents Render free tier spin-down) ────────
    render_url = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")
    if render_url:
        def _keep_alive():
            time.sleep(20)  # let startup finish first
            while True:
                try:
                    requests.get(f"{render_url}/api/health", timeout=5)
                except Exception:
                    pass
                time.sleep(30)
        threading.Thread(target=_keep_alive, daemon=True, name="keep-alive").start()
        print("[ORA] Keep-alive pinger started")

    yield
    print("[ORA] Shutdown")


app = FastAPI(title="ORA Backend", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])


# ── Health ────────────────────────────────────────────────────
@app.api_route("/api/health", methods=["GET", "HEAD"])
async def health(request: Request):
    return {"status": "ok"}

@app.api_route("/", methods=["GET", "HEAD"])
def root():
    return {"status": "ORA running"}

@app.get("/api/status")
def status():
    return {"cpu": psutil.cpu_percent(interval=0.1),
            "ram": psutil.virtual_memory().percent,
            "time": datetime.utcnow().isoformat()}

@app.get("/api/cache/stats")
def cache_stats():
    try:
        from cache import stats
        return stats()
    except Exception:
        return {}


# ── Chat ──────────────────────────────────────────────────────
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

        # 1. Intent parser — zero API cost
        try:
            from intent_parser import parse_intent, execute_intent
            intent = parse_intent(text)
            if intent:
                result = execute_intent(intent)
                if result:
                    save_conversation("user", text)
                    save_conversation("assistant", result)
                    return {"reply": result, "intent": intent["type"], "query_type": "action"}
        except Exception as e:
            print(f"[INTENT] {e}")

        # 2. Classify + KB
        q_type = classify(text)
        knowledge_ctx = ""
        try:
            from knowledge.pipeline import search_and_format
            knowledge_ctx = search_and_format(text, n_results=3 if q_type == "document" else 2) or ""
        except Exception:
            pass

        # 3. Cache check
        if q_type != "document":
            cached = cache.get(text, knowledge_ctx)
            if cached:
                save_conversation("user", text)
                save_conversation("assistant", cached)
                return {"reply": cached, "cached": True, "query_type": q_type}

        # 4. Build prompt
        system_prompt = build_system_prompt(query=text)
        if knowledge_ctx:
            system_prompt += f"\n\n## KNOWLEDGE BASE\n{knowledge_ctx[:700]}"

        try:
            from intelligence.goals_engine import get_goals
            goals = get_goals("active")
            if goals:
                glines = "\n".join(f"- {g['goal'][:60]} ({g['progress']}%)" for g in goals[:3])
                system_prompt += f"\n\n## ACTIVE GOALS\n{glines}"
        except Exception:
            pass

        history = get_conversation_history(limit=4)
        messages: list[Any] = [{"role": "system", "content": system_prompt}]
        for role, content, _ in history:
            messages.append({"role": "user" if role == "user" else "assistant", "content": content[:200]})
        messages.append({"role": "user", "content": text})

        # 5. Model selection
        model, max_tok = model_for(q_type)
        try:
            response = client.chat.completions.create(model=model, messages=messages,
                                                      max_tokens=max_tok, temperature=0.4)
        except Exception:
            response = client.chat.completions.create(model="llama-3.1-8b-instant",
                                                      messages=messages, max_tokens=200, temperature=0.4)

        reply = response.choices[0].message.content or "No response"

        if q_type != "document":
            cache.set(text, reply, knowledge_ctx)

        save_conversation("user", text)
        save_conversation("assistant", reply)
        return {"reply": reply, "query_type": q_type, "model": model}

    except Exception:
        print("[CHAT ERROR]")
        print(traceback.format_exc())
        return {"reply": "ORA error. Try again."}


# ── Conversations ─────────────────────────────────────────────
@app.get("/api/conversations")
def get_conversations(limit: int = 40):
    try:
        from database import get_conversation_history
        rows = get_conversation_history(limit=limit)
        return [{"role": r[0], "content": r[1], "timestamp": r[2]} for r in rows]
    except Exception:
        return []


# ── Tasks ─────────────────────────────────────────────────────
class TaskCreate(BaseModel):
    title: str
    priority: str = "medium"
    due_at: Optional[str] = None

@app.get("/api/tasks")
def get_tasks_ep(status: str = "pending"):
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


# ── The Number ────────────────────────────────────────────────
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
        return {"id": task_id, "title": title, "priority": priority, "due_at": due_at,
                "overdue": overdue, "score": score_task(top), "reason": _score_reason(top), "status": "ok"}
    except Exception:
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
            if diff < 0: parts.append("overdue")
            elif diff < 3600: parts.append("due within 1h")
            elif diff < 86400: parts.append("due today")
        except Exception:
            pass
    if "urgent" in title.lower():
        parts.append("marked urgent")
    return ", ".join(parts) if parts else "top pending task"


# ── Alerts ────────────────────────────────────────────────────
@app.get("/api/alerts")
def alerts_ep(limit: int = 10):
    try:
        from database import get_recent_alerts
        rows = get_recent_alerts(limit)
        return [{"id": r[0], "rule_name": r[1], "message": r[2], "severity": r[3],
                 "timestamp": r[4], "acknowledged": bool(r[5])} for r in rows]
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
def ack_all():
    try:
        from database import get_conn
        conn = get_conn()
        conn.execute("UPDATE alerts SET acknowledged=1 WHERE acknowledged=0")
        conn.commit()
        return {"status": "ok"}
    except Exception:
        raise HTTPException(500, "Failed")


# ── M-Pesa ────────────────────────────────────────────────────
class MpesaSMS(BaseModel):
    sms: str

@app.post("/api/mpesa/ingest")
def mpesa_ingest(payload: MpesaSMS):
    try:
        from mpesa_engine import ingest_sms
        return ingest_sms(payload.sms)
    except Exception:
        raise HTTPException(500, "Failed")

@app.get("/api/mpesa/summary")
def mpesa_summary():
    try:
        from mpesa_engine import (get_today_spend, get_average_daily_spend,
                                   get_daily_summary, get_recent_transactions,
                                   get_recurring_patterns)
        return {"today": get_today_spend(),
                "average_daily": get_average_daily_spend(),
                "last_7_days": get_daily_summary(days=7),
                "recent_transactions": get_recent_transactions(limit=10),
                "recurring": get_recurring_patterns()}
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


# ── Memory ────────────────────────────────────────────────────
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
        return [{"event_type": r[0], "summary": r[1], "detail": r[2],
                 "importance": r[3], "timestamp": r[4]} for r in rows]
    except Exception:
        return []

@app.get("/api/memory/important")
def memory_important(min_importance: int = 7, limit: int = 10):
    try:
        from memory.events import get_important_events
        rows = get_important_events(min_importance=min_importance, limit=limit)
        return [{"event_type": r[0], "summary": r[1], "detail": r[2],
                 "importance": r[3], "timestamp": r[4]} for r in rows]
    except Exception:
        return []


# ── Briefing ──────────────────────────────────────────────────
@app.get("/api/briefing")
def get_briefing():
    try:
        from briefing import generate_briefing
        text = generate_briefing()
        return {"briefing": text, "timestamp": datetime.utcnow().isoformat()}
    except Exception:
        print(traceback.format_exc())
        return {"briefing": "ORA standing by.", "timestamp": datetime.utcnow().isoformat()}


# ── Goals ─────────────────────────────────────────────────────
class GoalCreate(BaseModel):
    goal: str
    due_at: Optional[str] = None

@app.get("/api/goals")
def get_goals_ep(status: str = "active"):
    try:
        from intelligence.goals_engine import get_goals
        return get_goals(status)
    except Exception:
        return []

@app.post("/api/goals")
def create_goal(payload: GoalCreate):
    try:
        from intelligence.goals_engine import add_goal
        gid = add_goal(payload.goal, payload.due_at)
        return {"status": "created", "id": gid}
    except Exception:
        raise HTTPException(500, "Failed")

@app.post("/api/goals/{goal_id}/complete")
def complete_goal_ep(goal_id: int):
    try:
        from intelligence.goals_engine import complete_goal
        complete_goal(goal_id)
        return {"status": "done"}
    except Exception:
        raise HTTPException(500, "Failed")

@app.post("/api/goals/checkin")
def trigger_checkin():
    try:
        from intelligence.goals_engine import run_goal_checkin
        run_goal_checkin()
        return {"status": "sent"}
    except Exception:
        raise HTTPException(500, "Failed")


# ── Predictions ───────────────────────────────────────────────
@app.get("/api/predictions")
def get_predictions():
    try:
        from intelligence.prediction_engine import predict_needs
        return predict_needs()
    except Exception:
        return []


# ── Knowledge ─────────────────────────────────────────────────
@app.get("/api/knowledge/documents")
def knowledge_documents():
    try:
        from knowledge.pipeline import get_all_documents
        return get_all_documents()
    except Exception:
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
        return {"result": search_and_format(payload.query, n_results=payload.n_results)}
    except Exception:
        return {"result": ""}

def _run_indexing(filepath: str, filename: str, tags: str):
    try:
        from knowledge.pipeline import on_upload
        result = on_upload(filepath, filename, tags=tags, force=False)
        print(f"[UPLOAD] {filename}: {result}")
    except Exception as e:
        print(f"[UPLOAD] Failed {filename}: {e}")

@app.post("/api/knowledge/upload")
async def knowledge_upload(background_tasks: BackgroundTasks,
                            file: UploadFile = File(...), tags: str = Form(default="")):
    try:
        from config import UPLOADS_DIR
        filename = file.filename or "unknown"
        ext = os.path.splitext(filename)[1].lower()
        if ext not in ALLOWED_UPLOAD_TYPES:
            raise HTTPException(400, f"Unsupported type '{ext}'")
        data = await file.read()
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "File too large. Max 10MB.")
        if not data:
            raise HTTPException(400, "Empty file.")
        safe_name = _safe_filename(filename)
        dest = os.path.join(UPLOADS_DIR, safe_name)
        with open(dest, "wb") as f:
            f.write(data)
        background_tasks.add_task(_run_indexing, dest, safe_name, tags)
        return {"status": "accepted", "filename": safe_name,
                "size_kb": round(len(data) / 1024, 1),
                "message": "Saved. Indexing in background."}
    except HTTPException:
        raise
    except Exception:
        print(traceback.format_exc())
        raise HTTPException(500, "Upload failed")

@app.get("/api/knowledge/summary/{filename}")
def knowledge_summary(filename: str):
    try:
        from knowledge.pipeline import get_all_documents, search_and_format
        import cache
        docs = get_all_documents()
        doc = next((d for d in docs if d["filename"] == filename), None)
        if not doc:
            raise HTTPException(404, "Not found")
        if doc.get("summary") and len(doc["summary"]) > 50:
            return {"filename": filename, "summary": doc["summary"], "source": "stored"}
        ck = f"summary::{filename}"
        cached = cache.get(ck)
        if cached:
            return {"filename": filename, "summary": cached, "source": "cached"}
        if not client:
            raise HTTPException(503, "AI unavailable")
        chunks = search_and_format(filename.replace("_", " ").replace("-", " "), n_results=5)
        if not chunks:
            return {"filename": filename, "summary": "No content.", "source": "empty"}
        resp = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content":
                f"Summarize in 3 bullet points starting with •:\n\nDoc: {filename}\n\n{chunks[:2000]}"}],
            max_tokens=250, temperature=0.3)
        summary = (resp.choices[0].message.content or "").strip()
        cache.set(ck, summary)
        return {"filename": filename, "summary": summary, "source": "generated"}
    except HTTPException:
        raise
    except Exception:
        print(traceback.format_exc())
        raise HTTPException(500, "Summary failed")


# ── Helpers ───────────────────────────────────────────────────
def _safe_filename(name: str) -> str:
    import re
    name = os.path.basename(name)
    name = re.sub(r'[^\w.\-]', '_', name)
    return name[:120]