"""
ORA Backend API — v3 (Phase 1 — Autonomous Agent Loop)
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
try:
    client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
except Exception:
    client = None
    print("[ORA] Groq init failed")
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
        (lambda: __import__('fcm').init_fcm_table(), "FCM Tokens"),
    ]:
        try:
            fn()
            print(f"[ORA] {label} ready")
        except Exception:
            print(f"[ORA] {label} init error")
            print(traceback.format_exc())

    try:
        from ora_scheduler import start_scheduler
        from agent import run_agent_cycle
        from intelligence.pattern_engine import run_pattern_analysis
        from intelligence.prediction_engine import run_predictions
        from intelligence.goals_engine import run_goal_checkin
        from intelligence.proactive_engine import run_proactive_checks
        from intelligence.planner_engine import generate_daily_brief
        from intelligence.notifier import run_autonomous_notifications
        from connectors.drive import sync_drive
        from connectors.gmail import sync_gmail
        from connectors.rss import sync_rss
        from connectors.github import get_github_summary as github_sync

        start_scheduler([
            {"trigger": "interval", "minutes": 5,   "fn": run_agent_cycle,             "name": "agent_loop"},
            {"trigger": "cron",     "hour": 7,  "minute": 0,  "fn": run_predictions,   "name": "morning_preds"},
            {"trigger": "cron",     "hour": 18, "minute": 0,  "fn": run_predictions,   "name": "evening_preds"},
            {"trigger": "cron",     "hour": 2,  "minute": 30, "fn": run_pattern_analysis, "name": "daily_patterns"},
            {"trigger": "cron",     "hour": 8,  "minute": 30, "fn": run_goal_checkin,  "name": "weekly_goals"},
            {"trigger": "cron",     "hour": 7,  "minute": 0,  "fn": generate_daily_brief, "name": "daily_brief"},
            {"trigger": "interval", "hours": 1,    "fn": run_pattern_analysis,         "name": "pattern_analysis"},
            {"trigger": "interval", "minutes": 10, "fn": run_proactive_checks,         "name": "proactive_checks"},
            {"trigger": "interval", "minutes": 5,  "fn": run_autonomous_notifications, "name": "auto_notify"},
            # ── Phase 4: Data connectors ───────────────────────
            {"trigger": "interval", "minutes": 30, "fn": sync_drive,  "name": "drive_sync"},
            {"trigger": "interval", "minutes": 15, "fn": sync_gmail,  "name": "gmail_sync"},
            {"trigger": "interval", "hours": 2,    "fn": sync_rss,    "name": "rss_sync"},
            {"trigger": "interval", "hours": 1,    "fn": github_sync, "name": "github_sync"},
        ])
        print("[ORA] Scheduler started")
    except Exception:
        print("[SCHEDULER ERROR]")
        print(traceback.format_exc())

    try:
        from config import TELEGRAM_BOT_TOKEN
        if TELEGRAM_BOT_TOKEN:
            def _tg():
                delay = 5
                max_delay = 60
                while True:
                    try:
                        from telegram_bot import run_telegram_bot
                        run_telegram_bot()
                        delay = 5
                    except Exception as e:
                        print(f"[TELEGRAM ERROR] {e}")
                    time.sleep(delay)
                    delay = min(delay * 2, max_delay)

            threading.Thread(target=_tg, daemon=True, name="telegram-bot").start()
    except Exception:
        print(traceback.format_exc())

    yield
    print("[ORA] Shutdown")


app = FastAPI(title="ORA Backend", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])
try:
    from api_calendar_routes import router as calendar_router
    app.include_router(calendar_router)
    print("[ORA] Calendar routes loaded")
except Exception as e:
    print("[ORA] Calendar routes NOT loaded:", e)


# ── Health ────────────────────────────────────────────────────

from fastapi import Request

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
            "time": datetime.now().isoformat()}

@app.get("/api/cache/stats")
def cache_stats():
    try:
        from cache import stats
        return stats()
    except Exception:
        return {}


# ── Agent ─────────────────────────────────────────────────────
@app.get("/api/agent/status")
def agent_status():
    try:
        from agent import gather_context, decide
        ctx     = gather_context()
        actions = decide(ctx)
        return {
            "timestamp":       ctx.get("timestamp"),
            "tasks":           len(ctx.get("tasks", [])),
            "overdue":         len(ctx.get("overdue", [])),
            "goals":           len(ctx.get("goals", [])),
            "spend_alert":     ctx.get("spend_alert"),
            "predictions":     len(ctx.get("predictions", [])),
            "pending_actions": [
                {"type": a["type"], "key": a.get("key"), "message": a["message"]}
                for a in actions
            ],
        }
    except Exception:
        print(traceback.format_exc())
        return {"error": "agent context unavailable"}

@app.post("/api/agent/run")
def agent_run_now():
    try:
        from agent import run_agent_cycle
        run_agent_cycle()
        return {"status": "cycle complete"}
    except Exception:
        print(traceback.format_exc())
        raise HTTPException(500, "Agent cycle failed")


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

        q_type = classify(text)
        knowledge_ctx = ""
        try:
            from knowledge.pipeline import search_and_format
            knowledge_ctx = search_and_format(text, n_results=3 if q_type == "document" else 2) or ""
        except Exception:
            pass

        if q_type != "document":
            cached = cache.get(text, knowledge_ctx)
            if cached:
                save_conversation("user", text)
                save_conversation("assistant", cached)
                return {"reply": cached, "cached": True, "query_type": q_type}

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


# ── M-Pesa ────────────────────────────────────────────────────
@app.get("/api/mpesa/transactions")
def mpesa_transactions(limit: int = 20):
    try:
        from mpesa_engine import get_recent_transactions
        return get_recent_transactions(limit=limit)
    except Exception:
        return []

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


# ═══════════════════════════════════════════════════════════════
# PHASE 3 — Push notification endpoints
# ═══════════════════════════════════════════════════════════════

class PushTokenPayload(BaseModel):
    token: str
    platform: Optional[str] = "expo"


class PushTestPayload(BaseModel):
    token: Optional[str] = None
    title: Optional[str] = "ORA Test"
    body:  Optional[str] = "Push notifications are working ✓"


@app.post("/api/push/register")
async def push_register(payload: PushTokenPayload):
    """Register an Expo push token. Idempotent — safe to call every app launch."""
    try:
        from fcm import save_token
        token = payload.token.strip()
        if not token:
            raise HTTPException(400, "Token cannot be empty")
        save_token(token, payload.platform or "expo")
        return {"ok": True, "message": "Token registered"}
    except HTTPException:
        raise
    except Exception:
        print(traceback.format_exc())
        raise HTTPException(500, "Token registration failed")


@app.delete("/api/push/register")
async def push_unregister(payload: PushTokenPayload):
    """Remove a push token (user disables notifications)."""
    try:
        from fcm import remove_token
        remove_token(payload.token.strip())
        return {"ok": True}
    except Exception:
        print(traceback.format_exc())
        raise HTTPException(500, "Token removal failed")


@app.get("/api/push/tokens")
async def push_tokens_count():
    """Return count of registered tokens only — no raw tokens exposed."""
    try:
        from fcm import get_tokens
        return {"count": len(get_tokens())}
    except Exception:
        return {"count": 0}


@app.post("/api/push/test")
async def push_test(payload: PushTestPayload):
    """Send a test push. If token provided, send only to that device; else broadcast."""
    try:
        from fcm import send_push, send_push_to_token
        title = payload.title or "ORA Test"
        body  = payload.body  or "Push notifications are working ✓"
        if payload.token:
            sent = send_push_to_token(payload.token.strip(), title, body)
        else:
            sent = send_push(title=title, body=body)
        return {"ok": sent, "message": "Dispatched" if sent else "No tokens registered"}
    except Exception:
        print(traceback.format_exc())
        raise HTTPException(500, "Push test failed")


# ═══════════════════════════════════════════════════════════════
# PHASE 4 — Data connector endpoints
# ═══════════════════════════════════════════════════════════════

@app.get("/api/gmail/summary")
def gmail_summary():
    try:
        from connectors.gmail import get_gmail_summary
        return get_gmail_summary()
    except Exception:
        return {}

@app.get("/api/gmail/emails")
def gmail_emails(limit: int = 10):
    try:
        from connectors.gmail import get_recent_emails
        return get_recent_emails(max_results=min(limit, 10))
    except Exception:
        return []

@app.get("/api/weather")
def weather():
    try:
        from connectors.weather import get_weather
        return get_weather() or {}
    except Exception:
        return {}

@app.get("/api/github/summary")
def github_summary():
    try:
        from connectors.github import get_github_summary
        return get_github_summary()
    except Exception:
        return {}

@app.get("/api/rss/headlines")
def rss_headlines(limit: int = 10):
    try:
        from connectors.rss import get_latest_headlines
        return get_latest_headlines(limit=limit)
    except Exception:
        return []

@app.post("/api/youtube/ingest")
async def youtube_ingest(request: Request):
    try:
        body = await request.json()
        url  = body.get("url", "").strip()
        if not url:
            raise HTTPException(400, "url is required")
        from connectors.youtube import ingest_youtube
        return ingest_youtube(url)
    except HTTPException:
        raise
    except Exception:
        print(traceback.format_exc())
        raise HTTPException(500, "YouTube ingest failed")

@app.post("/api/drive/sync")
def drive_sync_now():
    """Manually trigger a Drive sync."""
    try:
        from connectors.drive import sync_drive
        sync_drive()
        return {"status": "sync triggered"}
    except Exception:
        raise HTTPException(500, "Drive sync failed")
