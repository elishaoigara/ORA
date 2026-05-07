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
        (lambda: __import__('intelligence.learning_engine', fromlist=['init_learning_tables']).init_learning_tables(), "Learning"),
        (lambda: __import__('research_agent', fromlist=['init_research_tables']).init_research_tables(), "Research DB"),
        (lambda: __import__('agents.content_agent', fromlist=['init_content_drafts_table']).init_content_drafts_table(), "Content Drafts"),
        (lambda: __import__('agents.code_agent', fromlist=['init_code_agent_tables']).init_code_agent_tables(), "Code Agent DB"),
        (lambda: __import__('agents.agent_bus', fromlist=['init_agent_bus_table']).init_agent_bus_table(), "Agent Bus"),
        (lambda: __import__('connectors.gmail', fromlist=['init_gmail_tables']).init_gmail_tables(), "Gmail Replies"),
        # ── New systems (Claude Code improvements) ─────────────────────────────
        (lambda: __import__('task_engine', fromlist=['task_engine']).task_engine, "Task Engine"),
        (lambda: __import__('conversation_history', fromlist=['conversation_history']).conversation_history, "Conv History"),
        (lambda: __import__('agent_scratchpad', fromlist=['scratchpad']).scratchpad, "Scratchpad"),
        (lambda: __import__('tool_registry', fromlist=['registry']).registry, "Tool Registry"),
        (lambda: __import__('dynamic_scheduler', fromlist=['scheduler']).scheduler, "Job Registry"),
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
        from connectors.gmail import run_gmail_reply_checks as sync_gmail
        from connectors.rss import sync_rss
        from connectors.github import get_github_summary as github_sync
        from agents.code_agent import scan_all_repos as code_scan_all
        from agents.agent_bus import process_pending_messages as bus_process

        start_scheduler([
            # ── Core agent loop — every 10min (saves CPU/RAM on Render free tier) ────
            {"trigger": "interval", "minutes": 10,  "fn": run_agent_cycle,              "name": "agent_loop"},
            # ── Intelligence cron jobs (once per day, not spammy) ────────────────────
            {"trigger": "cron",    "hour": 7,  "minute": 0,  "fn": run_predictions,    "name": "morning_preds"},
            {"trigger": "cron",    "hour": 18, "minute": 0,  "fn": run_predictions,    "name": "evening_preds"},
            {"trigger": "cron",    "hour": 2,  "minute": 30, "fn": run_pattern_analysis,"name": "daily_patterns"},
            {"trigger": "cron",    "hour": 8,  "minute": 30, "fn": run_goal_checkin,   "name": "weekly_goals"},
            {"trigger": "cron",    "hour": 7,  "minute": 0,  "fn": generate_daily_brief,"name": "daily_brief"},
            # ── Proactive checks every 15min (reduced from 10) ────────────────────────
            {"trigger": "interval", "minutes": 15, "fn": run_proactive_checks,          "name": "proactive_checks"},
            # ── Notifications every 15min ─────────────────────────────────────────────
            {"trigger": "interval", "minutes": 15, "fn": run_autonomous_notifications,  "name": "auto_notify"},
            # ── Agent Message Bus ─────────────────────────────────────────────────────
            {"trigger": "interval", "minutes": 5,  "fn": bus_process,                   "name": "agent_bus"},
            # ── Data connectors ───────────────────────────────────────────────────────
            {"trigger": "interval", "minutes": 30, "fn": sync_drive,                    "name": "drive_sync"},
            {"trigger": "interval", "minutes": 15, "fn": sync_gmail,                    "name": "gmail_sync"},
            {"trigger": "interval", "hours": 2,    "fn": sync_rss,                      "name": "rss_sync"},
            {"trigger": "interval", "hours": 2,    "fn": github_sync,                   "name": "github_sync"},
            # ── Code Agent — every 8h (CPU-intensive, reduced from 6) ─────────────────
            {"trigger": "interval", "hours": 8,    "fn": code_scan_all,                 "name": "code_scan"},
        ])
        print("[ORA] Scheduler started")
    except Exception:
        print("[SCHEDULER ERROR]")
        print(traceback.format_exc())

    # ── Disk + DB cleanup (keeps Render 1GB disk healthy) ─────────────────────
    try:
        from task_engine import task_engine as _te
        cleaned = _te.purge_old_tasks(days=3)
        print(f"[ORA] Cleanup: removed {cleaned['deleted_rows']} old tasks, {cleaned['deleted_files']} files")
    except Exception:
        pass
    try:
        from agent_scratchpad import scratchpad as _sp
        purged = _sp.purge_expired()
        if purged:
            print(f"[ORA] Scratchpad: purged {purged} expired notes")
    except Exception:
        pass

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

try:
    from api_research_routes import router as research_router
    app.include_router(research_router)
    print("[ORA] Research routes loaded")
except Exception as e:
    print("[ORA] Research routes NOT loaded:", e)

try:
    from api_code_routes import router as code_router
    app.include_router(code_router)
    print("[ORA] Code Agent routes loaded")
except Exception as e:
    print("[ORA] Code Agent routes NOT loaded:", e)


# ── Health ────────────────────────────────────────────────────

@app.api_route("/api/health", methods=["GET", "HEAD"])
async def health(request: Request):
    return {"status": "ok"}

@app.api_route("/", methods=["GET", "HEAD"])
def root():
    return {"status": "ORA running"}

@app.get("/api/google/status")
def google_status():
    """Quick check — is Google OAuth connected?"""
    try:
        from connectors.google_auth import is_authorized
        return {"connected": is_authorized()}
    except Exception:
        return {"connected": False}

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
    session_id: Optional[str] = None

@app.post("/api/chat")
async def chat(payload: ChatRequest):
    try:
        if not client:
            return {"reply": "ORA: Missing API key"}

        text = payload.message.strip()
        if not text:
            return {"reply": "Empty message."}

        # Resolve or create session for conversation history
        session_id = payload.session_id
        try:
            from conversation_history import conversation_history as _ch
            session_id = _ch.get_or_create_session(session_id)
        except Exception:
            pass

        # ── 1. Fast-path: pure-regex intent actions (zero LLM cost) ──────────
        try:
            from Intent_parser import parse_intent, execute_intent
            intent_obj = parse_intent(text)
            if intent_obj:
                result = execute_intent(intent_obj)
                if result:
                    from database import save_conversation
                    save_conversation("user",      text)
                    save_conversation("assistant", result)
                    try:
                        from intelligence.learning_engine import extract_explicit_facts
                        extract_explicit_facts(text)
                    except Exception:
                        pass
                    return {"reply": result,
                            "intent":     intent_obj["type"],
                            "query_type": "action"}
        except Exception as e:
            print(f"[INTENT] {e}")

        # ── 2. Correction detection ───────────────────────────────────────────
        try:
            from intelligence.learning_engine import detect_correction, log_correction
            from database import get_conversation_history
            history_check = get_conversation_history(limit=2)
            if history_check and detect_correction(text):
                last_ora = history_check[-1][1] if history_check else ""
                log_correction(text, last_ora, text)
        except Exception:
            pass

        # ── 3. Multi-agent Coordinator ────────────────────────────────────────
        from brain.router import Coordinator
        result = Coordinator.run(text, save_history=True, session_id=session_id)  # type: ignore[call-arg]
        reply  = result["reply"]
        q_type = result["query_type"]

        # ── 4. Cache (skip document/research results) ─────────────────────────
        try:
            import cache
            if q_type not in ("document", "complex"):
                cache.set(text, reply, "")
        except Exception:
            pass

        # ── 5. Persist conversation ───────────────────────────────────────────
        from database import save_conversation
        save_conversation("user",      text)
        save_conversation("assistant", reply)

        # ── 6. Background learning ────────────────────────────────────────────
        try:
            from intelligence.learning_engine import (
                extract_facts_from_exchange, extract_explicit_facts,
            )
            extract_explicit_facts(text)
            threading.Thread(
                target=extract_facts_from_exchange,
                args=(text, reply),
                daemon=True,
            ).start()
        except Exception:
            pass

        return {
            "reply":      reply,
            "query_type": q_type,
            "model":      "coordinator",
            "intent":     result.get("intent"),
            "pipeline":   result.get("pipeline"),
            "session_id": session_id,
            "task_id":    result.get("task_id"),
        }

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
        return [{"id": r[0], "title": r[1], "priority": r[2],
                 "created_at": r[3], "due_at": r[4]} for r in rows]
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


# ── Alerts ────────────────────────────────────────────────────

@app.get("/api/alerts")
def get_alerts(limit: int = 50):
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
        print(traceback.format_exc())
        return []

@app.post("/api/alerts/{alert_id}/ack")
def ack_alert(alert_id: int):
    try:
        from database import acknowledge_alert
        acknowledge_alert(alert_id)
        return {"ok": True}
    except Exception:
        print(traceback.format_exc())
        raise HTTPException(500, "Ack failed")


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
        today_raw = get_today_spend()
        if isinstance(today_raw, dict):
            today_num = float(today_raw.get("total", 0))
        else:
            today_num = float(today_raw or 0)
        return {
            "today":               today_num,
            "average_daily":       get_average_daily_spend(),
            "last_7_days":         get_daily_summary(days=7),
            "recent_transactions": get_recent_transactions(limit=10),
            "recurring":           get_recurring_patterns(),
        }
    except Exception:
        print(traceback.format_exc())
        return {"status": "error"}


@app.post("/api/mpesa/sms")
async def mpesa_sms_ingest(request: Request):
    """
    Receives M-Pesa SMS forwarded automatically by MacroDroid on your phone.
    MacroDroid POSTs here the moment any SMS from 'MPESA' arrives.
    Body: {"sms": "Confirmed. Ksh500 sent to John..."}
    """
    try:
        body     = await request.json()
        sms_text = body.get("sms", "").strip()
        print(f"[MPESA SMS] received body keys: {list(body.keys())}")
        print(f"[MPESA SMS] sms text: '{sms_text}'")
        if not sms_text:
            return {"status": "error", "message": "empty sms", "body_received": str(body)}

        from mpesa_engine import ingest_sms
        result = ingest_sms(sms_text)
        print(f"[MPESA SMS] parse result: {result}")

        # Notify via Telegram + push if valid transaction saved
        if result.get("status") == "saved":
            txn = result.get("transaction", {})
            try:
                from intelligence.notifier import dual_notify
                from mpesa_engine import check_spend_alert, get_today_spend
                amount = txn.get("amount", 0)
                party  = txn.get("party", "Unknown")
                txtype = txn.get("type", "transaction")
                emoji  = {"received":"💰","sent":"💸","paid":"💳",
                           "withdrawn":"🏧","airtime":"📱"}.get(txtype, "💳")
                verb   = {"received":"Received from","sent":"Sent to","paid":"Paid to",
                           "withdrawn":"Withdrawn","airtime":"Airtime via"}.get(txtype, "Transaction")
                today  = get_today_spend()
                total  = float(today.get("total", 0)) if isinstance(today, dict) else float(today or 0)
                body_lines = [f"{verb} {party}"]
                if txtype in ("sent", "paid", "withdrawn", "airtime"):
                    body_lines.append(f"Today total: Ksh{total:,.0f}")
                dual_notify(
                    title=f"{emoji} Ksh{amount:,.0f} — M-Pesa",
                    body="\n".join(body_lines),
                    is_alert=False,
                )
                alert = check_spend_alert()
                if alert:
                    dual_notify(title="⚠️ Spend Spike", body=alert["message"], is_alert=True)
            except Exception as ne:
                print(f"[MPESA SMS] notify error: {ne}")

        return result

    except Exception as e:
        print(f"[API] mpesa/sms error: {e}")
        print(traceback.format_exc())
        return {"status": "error", "message": str(e)}


@app.get("/api/mpesa/sms/test")
async def mpesa_sms_test():
    """
    Test endpoint — open this in your browser to confirm MacroDroid can reach ORA.
    https://ora-oovf.onrender.com/api/mpesa/sms/test
    """
    return {
        "status": "ok",
        "message": "ORA M-Pesa SMS endpoint is live. MacroDroid can POST here.",
        "endpoint": "POST /api/mpesa/sms",
        "expected_body": {"sms": "ABC123 Confirmed. Ksh500 sent to John Doe 0712345678 on 7/5/26 at 9:00 AM.New M-PESA balance is Ksh1,234.00."},
    }


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

@app.post("/api/goals/{goal_id}/complete")
def complete_goal_ep(goal_id: int):
    try:
        from intelligence.goals_engine import complete_goal
        complete_goal(goal_id)
        return {"status": "completed"}
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


# ── Memory ────────────────────────────────────────────────────

@app.get("/api/memory/profile")
def memory_profile():
    try:
        from memory.profile import get_all_profile
        return get_all_profile()
    except Exception:
        print(traceback.format_exc())
        return {}

@app.get("/api/memory/preferences")
def memory_preferences():
    try:
        from memory.preferences import get_preferences
        rows = get_preferences()
        return [
            {"category": r[0], "key": r[1], "value": r[2], "confidence": r[3]}
            for r in rows
        ]
    except Exception:
        print(traceback.format_exc())
        return []

@app.get("/api/memory/events")
def memory_events(limit: int = 30):
    try:
        from memory.events import get_recent_events
        rows = get_recent_events(limit=limit)
        return [
            {
                "event_type": r[0],
                "summary":    r[1],
                "detail":     r[2],
                "importance": r[3],
                "timestamp":  r[4],
            }
            for r in rows
        ]
    except Exception:
        print(traceback.format_exc())
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
                f"Summarize in 3 bullet points starting with:\n\nDoc: {filename}\n\n{chunks[:2000]}"}],
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
    name = re.sub(r"[^\w.\-]", "_", name)
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
    try:
        from fcm import remove_token
        remove_token(payload.token.strip())
        return {"ok": True}
    except Exception:
        print(traceback.format_exc())
        raise HTTPException(500, "Token removal failed")

@app.get("/api/push/tokens")
async def push_tokens_count():
    try:
        from fcm import get_tokens
        return {"count": len(get_tokens())}
    except Exception:
        return {"count": 0}

@app.post("/api/push/test")
async def push_test(payload: PushTestPayload):
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


# ═══════════════════════════════════════════════════════════════
# MISSING ENDPOINTS (fixing 404s from logs)
# ═══════════════════════════════════════════════════════════════

@app.get("/api/the-number")
def the_number():
    """Dashboard headline metric — real data, never invented."""
    try:
        from database import get_tasks
        from intelligence.goals_engine import get_goals
        pending = get_tasks("pending")
        goals   = get_goals("active")

        now = datetime.now()
        overdue = 0
        for t in pending:
            if t[4]:
                try:
                    if datetime.fromisoformat(t[4]) < now:
                        overdue += 1
                except Exception:
                    pass

        high_priority     = sum(1 for t in pending if t[2] == "high")
        avg_goal_progress = 0
        if goals:
            avg_goal_progress = int(
                sum(g.get("progress", 0) for g in goals) / len(goals)
            )

        context_parts = []
        if overdue:
            context_parts.append(f"{overdue} overdue")
        if high_priority:
            context_parts.append(f"{high_priority} high priority")

        return {
            "number":        len(pending),
            "label":         "pending tasks",
            "context":       ", ".join(context_parts) if context_parts else "on track",
            "goal_progress": avg_goal_progress,
            "goal_count":    len(goals),
        }
    except Exception:
        print(traceback.format_exc())
        return {"number": 0, "label": "tasks", "context": ""}


@app.get("/api/briefing")
def get_briefing():
    """Daily briefing — real data summary for dashboard."""
    try:
        import cache
        cached = cache.get("daily_briefing", "")
        if cached:
            return {"briefing": cached, "source": "cached"}

        from database import get_tasks
        from intelligence.goals_engine import get_goals

        pending = get_tasks("pending")
        goals   = get_goals("active")
        spend   = 0.0
        try:
            from mpesa_engine import get_today_spend
            today_spend = get_today_spend()
            if isinstance(today_spend, dict):
                spend = float(today_spend.get("total", 0))
            else:
                spend = float(today_spend) if today_spend else 0.0
        except Exception:
            pass

        parts = []
        if pending:
            high = [t for t in pending if t[2] == "high"]
            parts.append(
                f"{len(pending)} tasks pending"
                + (f" ({len(high)} high priority)" if high else "")
            )
        else:
            parts.append("No pending tasks")

        if goals:
            avg = int(sum(g.get("progress", 0) for g in goals) / len(goals))
            parts.append(f"{len(goals)} active goals at {avg}% avg progress")

        if spend > 0:
            parts.append(f"KES {spend:.0f} spent today")

        briefing = " · ".join(parts) if parts else "All clear."
        cache.set("daily_briefing", briefing, "")
        return {"briefing": briefing, "source": "live"}
    except Exception:
        print(traceback.format_exc())
        return {"briefing": "Briefing unavailable.", "source": "error"}


@app.post("/api/alerts/ack-all")
def ack_all_alerts():
    """Acknowledge all unread alerts."""
    try:
        from database import get_conn, close_conn
        conn = get_conn()
        c = conn.cursor()
        c.execute("UPDATE alerts SET acknowledged=1 WHERE acknowledged=0")
        count = c.rowcount
        conn.commit()
        close_conn()
        return {"ok": True, "count": count}
    except Exception:
        print(traceback.format_exc())
        raise HTTPException(500, "Ack-all failed")


@app.delete("/api/memory/learned/{fact_id}")
def delete_learned_fact(fact_id: int):
    """Remove a specific learned fact."""
    try:
        from database import get_conn, close_conn
        conn = get_conn()
        c = conn.cursor()
        c.execute("DELETE FROM learned_facts WHERE id=?", (fact_id,))
        conn.commit()
        close_conn()
        return {"ok": True}
    except Exception:
        raise HTTPException(500, "Delete failed")


# ═══════════════════════════════════════════════════════════════
# CONTENT CREATION AGENT ENDPOINTS
# ═══════════════════════════════════════════════════════════════

class ContentDraftRequest(BaseModel):
    topic: str
    content_type: str = "post"
    tone: str = "professional"
    length: str = "medium"
    platform: Optional[str] = None
    extra_context: str = ""

class ContentEditRequest(BaseModel):
    draft_text: str

class RegenerateRequest(BaseModel):
    feedback: str = ""


@app.post("/api/content/draft")
def create_content_draft(payload: ContentDraftRequest):
    """Generate a new content draft."""
    try:
        from agents.content_agent import create_draft
        result = create_draft(
            topic        = payload.topic,
            content_type = payload.content_type,
            tone         = payload.tone,
            length       = payload.length,
            platform     = payload.platform,
            extra_context= payload.extra_context,
        )
        return result
    except Exception as e:
        print(f"[CONTENT API] Error: {e}")
        print(traceback.format_exc())
        raise HTTPException(500, "Failed to generate content draft")


@app.get("/api/content/drafts")
def list_content_drafts(status: str = "all", limit: int = 20, search: str = ""):
    """List saved content drafts."""
    try:
        from agents.content_agent import get_drafts
        return get_drafts(status=status, limit=limit, search=search)
    except Exception as e:
        print(f"[CONTENT API] Error listing drafts: {e}")
        return []


@app.get("/api/content/drafts/{draft_id}")
def get_single_draft(draft_id: int):
    """Get a single draft by ID."""
    try:
        from agents.content_agent import get_draft_by_id
        draft = get_draft_by_id(draft_id)
        if not draft:
            raise HTTPException(404, "Draft not found")
        return draft
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/content/drafts/{draft_id}/status")
def update_content_draft_status(draft_id: int, status: str):
    """Update draft status: draft | approved | sent | rejected | archived"""
    try:
        from agents.content_agent import update_draft_status
        success = update_draft_status(draft_id, status)
        if success:
            return {"ok": True, "message": f"Draft {draft_id} -> {status}"}
        raise HTTPException(404, "Draft not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.put("/api/content/drafts/{draft_id}/text")
def edit_draft_text(draft_id: int, payload: ContentEditRequest):
    """Save manual edits to a draft."""
    try:
        from agents.content_agent import update_draft_text
        ok = update_draft_text(draft_id, payload.draft_text)
        if not ok:
            raise HTTPException(404, "Draft not found")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/content/drafts/{draft_id}/regenerate")
def regenerate_content_draft(draft_id: int, payload: RegenerateRequest):
    """Re-generate a draft with optional feedback."""
    try:
        from agents.content_agent import regenerate_draft
        result = regenerate_draft(draft_id, feedback=payload.feedback)
        return result
    except Exception as e:
        print(f"[CONTENT API] Regenerate failed: {e}")
        raise HTTPException(500, "Regeneration failed")


@app.delete("/api/content/drafts/{draft_id}")
def delete_content_draft(draft_id: int):
    """Permanently delete a draft."""
    try:
        from agents.content_agent import delete_draft
        ok = delete_draft(draft_id)
        if not ok:
            raise HTTPException(404, "Draft not found")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/content/stats")
def content_stats():
    """Content studio analytics."""
    try:
        from agents.content_agent import get_content_stats
        return get_content_stats()
    except Exception as e:
        return {"total": 0, "by_status": {}, "top_types": []}

# ═══════════════════════════════════════════════════════════════
# AGENT MESSAGE BUS ENDPOINTS
# ═══════════════════════════════════════════════════════════════

class BusMessageRequest(BaseModel):
    from_agent: str
    to_agent:   str
    intent:     str
    payload:    dict = {}
    priority:   int  = 5


@app.post("/api/bus/message")
def bus_post_message(payload: BusMessageRequest):
    """Post a message on the agent bus. Returns message ID."""
    try:
        from agents.agent_bus import post_message
        msg_id = post_message(
            from_agent=payload.from_agent,
            to_agent=payload.to_agent,
            intent=payload.intent,
            payload=payload.payload,
            priority=payload.priority,
        )
        return {"ok": True, "id": msg_id}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/bus/message/{msg_id}")
def bus_get_result(msg_id: int):
    """Poll for the result of a specific message."""
    try:
        from agents.agent_bus import get_message_result
        result = get_message_result(msg_id)
        if not result:
            raise HTTPException(404, "Message not found")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/bus/process")
def bus_process_now():
    """Manually trigger bus processing (useful for testing / immediate dispatch)."""
    try:
        from agents.agent_bus import process_pending_messages
        results = process_pending_messages(max_per_run=10)
        return {"processed": len(results), "results": results}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/bus/activity")
def bus_activity(limit: int = 20):
    """Recent bus activity for the dashboard."""
    try:
        from agents.agent_bus import get_recent_activity
        return get_recent_activity(limit=limit)
    except Exception:
        return []


@app.get("/api/bus/stats")
def bus_stats():
    """Agent bus statistics."""
    try:
        from agents.agent_bus import get_bus_stats
        return get_bus_stats()
    except Exception:
        return {"total": 0, "pending": 0, "done": 0, "failed": 0}


@app.get("/api/bus/pending/{agent}")
def bus_pending_for_agent(agent: str):
    """Get pending messages for a specific agent."""
    try:
        from agents.agent_bus import get_pending
        return get_pending(agent)
    except Exception:
        return []

# ═══════════════════════════════════════════════════════════════
# PHASE 2 — GMAIL COMMUNICATION AGENT ENDPOINTS
# ═══════════════════════════════════════════════════════════════

# gmail tables are initialised in lifespan below — no duplicate startup needed


@app.get("/api/gmail/summary")
def gmail_summary():
    try:
        from connectors.gmail import get_gmail_summary
        return get_gmail_summary()
    except Exception as e:
        return {"authorized": False, "unread_count": 0, "error": str(e)}


@app.get("/api/gmail/emails")
def gmail_emails(limit: int = 15):
    try:
        from connectors.gmail import get_recent_emails
        return get_recent_emails(max_results=limit)
    except Exception as e:
        print(f"[API] gmail/emails error: {e}")
        return []


@app.get("/api/gmail/replies/pending")
def gmail_replies_pending(limit: int = 15):
    try:
        from connectors.gmail import get_pending_replies
        return get_pending_replies(limit=limit)
    except Exception as e:
        return []


@app.get("/api/gmail/replies/history")
def gmail_replies_history(limit: int = 20):
    try:
        from connectors.gmail import get_reply_history
        return get_reply_history(limit=limit)
    except Exception as e:
        return []


@app.get("/api/gmail/replies/stats")
def gmail_reply_stats():
    try:
        from connectors.gmail import get_reply_stats
        return get_reply_stats()
    except Exception as e:
        return {"total": 0, "pending": 0, "sent": 0, "approved": 0, "rejected": 0}


class ReplyTextRequest(BaseModel):
    text: str


@app.put("/api/gmail/replies/{reply_id}/text")
def gmail_update_reply_text(reply_id: int, payload: ReplyTextRequest):
    try:
        from connectors.gmail import update_reply_text
        ok = update_reply_text(reply_id, payload.text)
        return {"ok": ok}
    except Exception as e:
        raise HTTPException(500, str(e))


class RegenerateReplyRequest(BaseModel):
    tone: str = "professional"


@app.post("/api/gmail/replies/{reply_id}/regenerate")
def gmail_regenerate_reply(reply_id: int, payload: RegenerateReplyRequest):
    try:
        from connectors.gmail import regenerate_reply
        return regenerate_reply(reply_id, tone=payload.tone)
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/gmail/replies/{reply_id}/approve")
def gmail_approve_reply(reply_id: int):
    try:
        from connectors.gmail import approve_and_send_reply
        return approve_and_send_reply(reply_id)
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/gmail/replies/{reply_id}/reject")
def gmail_reject_reply(reply_id: int):
    try:
        from connectors.gmail import reject_reply
        ok = reject_reply(reply_id)
        return {"ok": ok}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/gmail/replies/generate")
def gmail_generate_replies_now():
    """Manually trigger reply generation for all eligible emails."""
    try:
        from connectors.gmail import get_emails_needing_reply, suggest_reply, save_suggested_reply
        emails = get_emails_needing_reply(limit=5)
        added = 0
        for email in emails:
            text = suggest_reply(email)
            if len(text) > 20:
                saved = save_suggested_reply(
                    email_id=email.get("id", "unknown"),
                    thread_id=email.get("thread_id"),
                    subject=email.get("subject", ""),
                    sender=email.get("sender", ""),
                    email_body=email.get("body", ""),
                    suggested_text=text,
                )
                if saved:
                    added += 1
        return {"ok": True, "generated": added}
    except Exception as e:
        raise HTTPException(500, str(e))


# ═══════════════════════════════════════════════════════════════
# PHASE 2 — VOICE INTERFACE ENDPOINT
# ═══════════════════════════════════════════════════════════════

@app.post("/api/voice/transcribe")
async def voice_transcribe(file: UploadFile = File(...)):
    """
    Accept a web audio blob (webm/mp4/wav/ogg) from the browser,
    transcribe via Groq Whisper, return transcript + ORA's response.
    """
    import tempfile
    import os

    tmp_path = None
    try:
        from config import GROQ_API_KEY, DATA_DIR
        from groq import Groq

        # Write upload to temp file — Whisper needs a real file
        suffix = ".webm"
        filename = (file.filename or "").lower()
        for ext in [".wav", ".mp4", ".ogg", ".m4a", ".webm"]:
            if filename.endswith(ext):
                suffix = ext
                break

        tmp_path = os.path.join(DATA_DIR, f"voice_{int(time.time())}{suffix}")
        content = await file.read()
        if len(content) > 25 * 1024 * 1024:
            raise HTTPException(413, "Audio too large (max 25MB)")

        with open(tmp_path, "wb") as f:
            f.write(content)

        # Transcribe
        groq_client = Groq(api_key=GROQ_API_KEY)
        with open(tmp_path, "rb") as f:
            result = groq_client.audio.transcriptions.create(
                model="whisper-large-v3-turbo",
                file=f,
                response_format="text",
            )

        transcript = result.strip() if isinstance(result, str) else getattr(result, "text", "").strip()

        if not transcript:
            return {"transcript": "", "reply": "", "error": "Could not understand audio"}

        # Route through ORA brain for a response
        from ai_brain import ask_groq
        from database import save_conversation
        save_conversation("user", f"[Voice] {transcript}")
        brain_result = ask_groq(transcript)
        reply = ""
        if isinstance(brain_result, dict):
            reply = brain_result.get("reply") or brain_result.get("raw") or ""
        else:
            reply = str(brain_result)

        if reply:
            save_conversation("assistant", reply)

        return {"transcript": transcript, "reply": reply.strip()}

    except HTTPException:
        raise
    except Exception as e:
        print(f"[VOICE API] Error: {e}")
        raise HTTPException(500, f"Transcription failed: {str(e)}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


# ═══════════════════════════════════════════════════════════════
# PHASE 2 — PROACTIVE INTELLIGENCE: MANUAL TRIGGER
# ═══════════════════════════════════════════════════════════════

@app.post("/api/proactive/run")
def proactive_run_now():
    """Manually fire a proactive check cycle (useful for testing)."""
    try:
        from intelligence.proactive_engine import run_proactive_checks
        from agent_guard import reset_all
        reset_all()  # bypass cooldowns for manual trigger
        run_proactive_checks()
        return {"ok": True, "message": "Proactive checks fired"}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/proactive/status")
def proactive_status():
    """Return what the proactive engine would fire right now."""
    try:
        from datetime import datetime
        from database import get_tasks, get_conn, close_conn

        now    = datetime.now()
        hour   = now.hour
        today  = now.date().isoformat()

        pending = get_tasks("pending")
        overdue = [t for t in pending if t[4] and datetime.fromisoformat(t[4]) < now]
        high    = [t for t in pending if t[2] == "high"]

        # Pending replies older than 24h
        conn = get_conn()
        old_replies = conn.execute("""
            SELECT COUNT(*) FROM suggested_replies
            WHERE status='pending' AND created_at < datetime('now', '-24 hours')
        """).fetchone()[0]
        pending_replies = conn.execute("""
            SELECT COUNT(*) FROM suggested_replies WHERE status='pending'
        """).fetchone()[0]
        close_conn()

        signals = []
        if overdue:
            signals.append({"type": "overdue_tasks", "count": len(overdue), "severity": "high"})
        if len(high) >= 2:
            signals.append({"type": "high_priority_backlog", "count": len(high), "severity": "medium"})
        if old_replies > 0:
            signals.append({"type": "unanswered_emails", "count": old_replies, "severity": "medium"})
        if pending_replies > 0:
            signals.append({"type": "pending_replies", "count": pending_replies, "severity": "low"})

        return {
            "hour":            hour,
            "today":           today,
            "pending_tasks":   len(pending),
            "overdue_tasks":   len(overdue),
            "high_priority":   len(high),
            "pending_replies": pending_replies,
            "old_replies":     old_replies,
            "active_signals":  signals,
        }
    except Exception as e:
        raise HTTPException(500, str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# NEW ENDPOINTS — Task Engine, Tool Registry, Scheduler, Conversation History
# ═══════════════════════════════════════════════════════════════════════════════

# ── Task Engine ───────────────────────────────────────────────────────────────

@app.get("/api/agent-tasks")
def get_agent_tasks(limit: int = 20, kind: str = "", status: str = ""):
    """List recent agent pipeline tasks with status and duration."""
    try:
        from task_engine import task_engine
        tasks = task_engine.get_recent(limit=limit, kind=kind, status=status)
        return {"tasks": tasks, "count": len(tasks)}
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/api/agent-tasks/stats")
def agent_task_stats():
    """Get task pipeline stats: success rate, avg duration, counts by status."""
    try:
        from task_engine import task_engine
        return task_engine.get_stats()
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/api/agent-tasks/{task_id}")
def get_agent_task(task_id: int):
    """Get a single agent task by ID."""
    try:
        from task_engine import task_engine
        task = task_engine.get_task(task_id)
        if not task:
            raise HTTPException(404, f"Task {task_id} not found")
        return task
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))

# ── Tool Registry ─────────────────────────────────────────────────────────────

@app.get("/api/tools")
def list_tools():
    """List all registered ORA tools."""
    try:
        from tool_registry import registry
        return {"tools": registry.list_tools(), "count": len(registry.list_tools())}
    except Exception as e:
        raise HTTPException(500, str(e))

@app.post("/api/tools/{tool_name}/run")
def run_tool(tool_name: str, payload: dict = {}):
    """Run a tool by name with optional input payload."""
    try:
        from tool_registry import registry
        if not registry.has(tool_name):
            raise HTTPException(404, f"Tool '{tool_name}' not found")
        result = registry.run(tool_name, payload)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))

# ── Dynamic Scheduler ─────────────────────────────────────────────────────────

@app.get("/api/scheduler/jobs")
def list_scheduled_jobs():
    """List all scheduled jobs with status and next run info."""
    try:
        from dynamic_scheduler import scheduler
        return {"jobs": scheduler.list_jobs()}
    except Exception as e:
        raise HTTPException(500, str(e))

@app.post("/api/scheduler/jobs/{job_name}/run")
def run_job_now(job_name: str):
    """Manually trigger a scheduled job immediately."""
    try:
        from dynamic_scheduler import scheduler
        result = scheduler.run_now(job_name)
        return result
    except Exception as e:
        raise HTTPException(500, str(e))

@app.post("/api/scheduler/jobs/{job_name}/enable")
def enable_job(job_name: str):
    try:
        from dynamic_scheduler import scheduler
        scheduler.set_enabled(job_name, True)
        return {"ok": True, "job": job_name, "enabled": True}
    except Exception as e:
        raise HTTPException(500, str(e))

@app.post("/api/scheduler/jobs/{job_name}/disable")
def disable_job(job_name: str):
    try:
        from dynamic_scheduler import scheduler
        scheduler.set_enabled(job_name, False)
        return {"ok": True, "job": job_name, "enabled": False}
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/api/scheduler/jobs/{job_name}/history")
def job_history(job_name: str, limit: int = 10):
    try:
        from dynamic_scheduler import scheduler
        return {"job": job_name, "history": scheduler.get_job_history(job_name, limit)}
    except Exception as e:
        raise HTTPException(500, str(e))

# ── Conversation History ──────────────────────────────────────────────────────

@app.get("/api/sessions")
def list_sessions(limit: int = 10):
    """List recent conversation sessions."""
    try:
        from conversation_history import conversation_history
        return {"sessions": conversation_history.get_recent_sessions(limit)}
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/api/sessions/{session_id}/history")
def get_session_history(session_id: str, limit: int = 20, before_id: Optional[int] = None):
    """Get paginated message history for a session."""
    try:
        from conversation_history import conversation_history
        page = conversation_history.get_page(session_id, before_id=before_id, limit=limit)
        return page
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/api/sessions/{session_id}")
def get_session_info(session_id: str):
    """Get session metadata."""
    try:
        from conversation_history import conversation_history
        info = conversation_history.get_session_info(session_id)
        if not info:
            raise HTTPException(404, f"Session {session_id} not found")
        return info
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))