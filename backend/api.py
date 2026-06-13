"""
ORA Backend API — v4 (Cleaned)
- Removed deleted agents: code_agent, content_agent, agent_bus, news_agent
- Removed deleted connectors: rss, github, youtube
- Removed deleted modules: research_agent, agent_scratchpad, dynamic_scheduler,
  tool_registry, task_engine, voice_handler
- Added /api/ping for keep-alive (set up cron-job.org to hit this every 10min)
- Scheduler now only references files that exist
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

    # ── Init tables (only modules that still exist) ────────────────────────────
    for fn, label in [
        (lambda: __import__('database').init_db() or __import__('database').init_tasks_table(), "DB"),
        (lambda: __import__('mpesa_engine').init_mpesa_table(), "M-Pesa"),
        (lambda: __import__('memory.profile', fromlist=['init_profile']).init_profile(), "Profile"),
        (lambda: __import__('knowledge.embeddings', fromlist=['init_vector_db']).init_vector_db(), "Knowledge DB"),
        (lambda: __import__('intelligence.goals_engine', fromlist=['init_goals_table']).init_goals_table(), "Goals"),
        (lambda: __import__('fcm').init_fcm_table(), "FCM Tokens"),
        (lambda: __import__('intelligence.learning_engine', fromlist=['init_learning_tables']).init_learning_tables(), "Learning"),
        (lambda: __import__('connectors.gmail', fromlist=['init_gmail_tables']).init_gmail_tables(), "Gmail"),
        (lambda: __import__('conversation_history', fromlist=['conversation_history']).conversation_history, "Conv History"),
    ]:
        try:
            fn()
            print(f"[ORA] {label} ready")
        except Exception:
            print(f"[ORA] {label} init error")
            print(traceback.format_exc())

    # ── Scheduler (only jobs whose modules exist) ──────────────────────────────
    try:
        from ora_scheduler import start_scheduler
        from agent import run_agent_cycle
        from intelligence.pattern_engine import run_pattern_analysis
        from intelligence.prediction_engine import run_predictions
        from intelligence.goals_engine import run_goal_checkin
        from intelligence.proactive_engine import run_proactive_checks
        from intelligence.notifier import run_autonomous_notifications
        from connectors.drive import sync_drive
        from connectors.gmail import run_gmail_reply_checks as sync_gmail

        def morning_brief():
            try:
                from intelligence.notifier import dual_notify
                from database import get_tasks
                from connectors.weather import get_weather_summary
                tasks = get_tasks("pending")
                high  = [t for t in tasks if t[2] == "high"]
                lines = [f"Good morning Elisha. {len(tasks)} tasks pending."]
                if high:
                    lines.append(f"High priority: {high[0][1][:60]}")
                try:
                    w = get_weather_summary()
                    if w: lines.append(f"Weather: {w}")
                except Exception:
                    pass
                dual_notify(title="ORA Morning Brief", body="\n".join(lines))
            except Exception:
                print(traceback.format_exc())

        start_scheduler([
            # Core agent loop
            {"trigger": "interval", "minutes": 10,  "fn": run_agent_cycle,             "name": "agent_loop"},
            # Intelligence — daily
            {"trigger": "cron",    "hour": 7,  "minute": 0,  "fn": run_predictions,   "name": "morning_preds"},
            {"trigger": "cron",    "hour": 18, "minute": 0,  "fn": run_predictions,   "name": "evening_preds"},
            {"trigger": "cron",    "hour": 2,  "minute": 30, "fn": run_pattern_analysis, "name": "daily_patterns"},
            {"trigger": "cron",    "hour": 8,  "minute": 30, "fn": run_goal_checkin,  "name": "goal_checkin"},
            {"trigger": "cron",    "hour": 7,  "minute": 5,  "fn": morning_brief,     "name": "morning_brief"},
            # Proactive + notifications
            {"trigger": "interval", "minutes": 15, "fn": run_proactive_checks,         "name": "proactive_checks"},
            {"trigger": "interval", "minutes": 15, "fn": run_autonomous_notifications, "name": "auto_notify"},
            # Data connectors
            {"trigger": "interval", "minutes": 30, "fn": sync_drive,                   "name": "drive_sync"},
            {"trigger": "interval", "minutes": 15, "fn": sync_gmail,                   "name": "gmail_sync"},
        ])
        print("[ORA] Scheduler started")
    except Exception:
        print("[SCHEDULER ERROR]")
        print(traceback.format_exc())

    # ── Telegram bot thread (PTB async — handles reconnects internally) ────────
    try:
        from config import TELEGRAM_BOT_TOKEN
        if TELEGRAM_BOT_TOKEN:
            def _tg():
                try:
                    from telegram_bot import run_telegram_bot
                    run_telegram_bot()   # PTB run_polling — blocks until process exits
                except Exception as e:
                    print(f"[TELEGRAM ERROR] {e}\n{traceback.format_exc()}")
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


# ── Keep-alive + Health ───────────────────────────────────────────────────────
# Set up cron-job.org to GET /api/ping every 10 minutes — keeps Render awake
# and ensures the scheduler never sleeps.

@app.get("/api/ping")
async def ping():
    """Keep-alive endpoint. Hit this every 10min from cron-job.org."""
    return {"status": "alive", "time": datetime.now().isoformat()}

@app.api_route("/api/health", methods=["GET", "HEAD"])
async def health(request: Request):
    return {"status": "ok"}

@app.api_route("/", methods=["GET", "HEAD"])
def root():
    return {"status": "ORA running"}

@app.get("/api/google/status")
def google_status():
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


# ── Agent ─────────────────────────────────────────────────────────────────────

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


# ── Chat ──────────────────────────────────────────────────────────────────────

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

        session_id = payload.session_id
        try:
            from conversation_history import conversation_history as _ch
            session_id = _ch.get_or_create_session(session_id)
        except Exception:
            pass

        # Fast-path: regex intent
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
                    return {"reply": result, "intent": intent_obj["type"], "query_type": "action"}
        except Exception as e:
            print(f"[INTENT] {e}")

        # Correction detection
        try:
            from intelligence.learning_engine import detect_correction, log_correction
            from database import get_conversation_history
            history_check = get_conversation_history(limit=2)
            if history_check and detect_correction(text):
                last_ora = history_check[-1][1] if history_check else ""
                log_correction(text, last_ora, text)
        except Exception:
            pass

        # Brain router
        from brain.router import Coordinator
        result = Coordinator.run(text, save_history=True, session_id=session_id)
        reply  = result["reply"]
        q_type = result["query_type"]

        # Cache
        try:
            import cache
            if q_type not in ("document", "complex"):
                cache.set(text, reply, "")
        except Exception:
            pass

        # Persist
        from database import save_conversation
        save_conversation("user",      text)
        save_conversation("assistant", reply)

        # Background learning
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
        }

    except Exception:
        print("[CHAT ERROR]")
        print(traceback.format_exc())
        return {"reply": "ORA error. Try again."}


# ── Conversations ─────────────────────────────────────────────────────────────

@app.get("/api/conversations")
def get_conversations(limit: int = 40):
    try:
        from database import get_conversation_history
        rows = get_conversation_history(limit=limit)
        return [{"role": r[0], "content": r[1], "timestamp": r[2]} for r in rows]
    except Exception:
        return []

@app.get("/api/sessions")
def list_sessions(limit: int = 10):
    try:
        from conversation_history import conversation_history
        return {"sessions": conversation_history.get_recent_sessions(limit)}
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/api/sessions/{session_id}/history")
def get_session_history(session_id: str, limit: int = 20, before_id: Optional[int] = None):
    try:
        from conversation_history import conversation_history
        return conversation_history.get_page(session_id, before_id=before_id, limit=limit)
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/api/sessions/{session_id}")
def get_session_info(session_id: str):
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


# ── Tasks ─────────────────────────────────────────────────────────────────────

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


# ── Alerts ────────────────────────────────────────────────────────────────────

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
        raise HTTPException(500, "Ack failed")

@app.post("/api/alerts/ack-all")
def ack_all_alerts():
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
        raise HTTPException(500, "Ack-all failed")


# ── M-Pesa ────────────────────────────────────────────────────────────────────

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
        today_num = float(today_raw.get("total", 0)) if isinstance(today_raw, dict) else float(today_raw or 0)
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
    try:
        body     = await request.json()
        sms_text = body.get("sms", "").strip()
        if not sms_text:
            return {"status": "error", "message": "empty sms"}

        from mpesa_engine import ingest_sms
        result = ingest_sms(sms_text)

        if result.get("status") == "saved":
            txn = result.get("transaction", {})
            try:
                from intelligence.notifier import dual_notify
                from mpesa_engine import check_spend_alert, get_today_spend
                amount = txn.get("amount", 0)
                party  = txn.get("party", "Unknown")
                txtype = txn.get("type", "transaction")
                emoji  = {"received": "💰", "sent": "💸", "paid": "💳",
                           "withdrawn": "🏧", "airtime": "📱"}.get(txtype, "💳")
                verb   = {"received": "Received from", "sent": "Sent to", "paid": "Paid to",
                           "withdrawn": "Withdrawn", "airtime": "Airtime via"}.get(txtype, "Transaction")
                today  = get_today_spend()
                total  = float(today.get("total", 0)) if isinstance(today, dict) else float(today or 0)
                body_lines = [f"{verb} {party}"]
                if txtype in ("sent", "paid", "withdrawn", "airtime"):
                    body_lines.append(f"Today total: Ksh{total:,.0f}")
                dual_notify(title=f"{emoji} Ksh{amount:,.0f} — M-Pesa", body="\n".join(body_lines))
                alert = check_spend_alert()
                if alert:
                    dual_notify(title="Spend Spike", body=alert["message"], is_alert=True)
            except Exception as ne:
                print(f"[MPESA SMS] notify error: {ne}")

        return result
    except Exception as e:
        print(traceback.format_exc())
        return {"status": "error", "message": str(e)}

@app.get("/api/mpesa/sms/test")
async def mpesa_sms_test():
    return {
        "status": "ok",
        "message": "ORA M-Pesa SMS endpoint is live.",
        "endpoint": "POST /api/mpesa/sms",
    }


# ── Location ──────────────────────────────────────────────────────────────────

@app.post("/api/location/event")
async def location_event(request: Request):
    try:
        body  = await request.json()
        event = body.get("event", "").strip()
        loc   = body.get("location", "unknown")
        wifi  = body.get("wifi", "")
        note  = body.get("note", "")

        if not event:
            return {"status": "error", "message": "event field required"}

        try:
            from database import get_conn, close_conn
            conn = get_conn()
            conn.execute("CREATE TABLE IF NOT EXISTS kv_store (key TEXT PRIMARY KEY, value TEXT)")
            conn.execute("INSERT INTO kv_store (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                         ("location_context", f"{event}|{loc}|{wifi}"))
            conn.execute("INSERT INTO kv_store (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                         ("last_location_event", datetime.now().isoformat()))
            conn.commit()
            close_conn()
        except Exception as e:
            print(f"[LOCATION] kv save failed: {e}")

        try:
            from memory.profile import update_profile # type: ignore
            location_map = {"arrived_home": "home", "left_home": "away",
                            "arrived_work": "work", "left_work": "away", "charging_started": "home"}
            update_profile("current_location", location_map.get(event, loc))
            update_profile("last_location_event", event)
            update_profile("last_seen", datetime.now().strftime("%Y-%m-%d %H:%M"))
        except Exception:
            pass

        notifs = {
            "arrived_home":     "Welcome home, Elisha.",
            "left_home":        "You have left home. ORA is watching.",
            "arrived_work":     "At work. Focus mode on.",
            "left_work":        "Left work. Good job today.",
            "charging_started": "Phone charging. ORA running checks.",
        }
        msg = notifs.get(event)

        if event == "arrived_home":
            try:
                from database import get_tasks
                from mpesa_engine import get_today_spend
                pending = get_tasks("pending")
                high    = [t for t in pending if t[2] == "high"]
                spend   = get_today_spend()
                total   = float(spend.get("total", 0)) if isinstance(spend, dict) else float(spend or 0)
                parts   = []
                if high:      parts.append(f"{len(high)} high-priority task(s) open")
                elif pending: parts.append(f"{len(pending)} tasks pending")
                else:         parts.append("All tasks clear")
                if total > 0: parts.append(f"Ksh{total:,.0f} spent today")
                note = " · ".join(parts)
            except Exception:
                pass

        elif event == "charging_started":
            try:
                threading.Thread(target=__import__('intelligence.proactive_engine',
                    fromlist=['run_proactive_checks']).run_proactive_checks, daemon=True).start()
            except Exception:
                pass

        if msg:
            try:
                from intelligence.notifier import dual_notify
                dual_notify(title=msg, body=note or "", is_alert=False)
            except Exception as ne:
                print(f"[LOCATION] notify error: {ne}")

        return {"status": "ok", "event": event, "location": loc}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/location/current")
def location_current():
    try:
        from database import get_conn, close_conn
        conn = get_conn()
        conn.execute("CREATE TABLE IF NOT EXISTS kv_store (key TEXT PRIMARY KEY, value TEXT)")
        ctx = conn.execute("SELECT value FROM kv_store WHERE key=?", ("location_context",)).fetchone()
        ts  = conn.execute("SELECT value FROM kv_store WHERE key=?", ("last_location_event",)).fetchone()
        close_conn()
        if not ctx:
            return {"location": "unknown", "last_event": None}
        parts = (ctx[0] or "").split("|")
        return {
            "last_event": parts[0] if len(parts) > 0 else None,
            "location":   parts[1] if len(parts) > 1 else "unknown",
            "wifi":       parts[2] if len(parts) > 2 else None,
            "last_seen":  ts[0] if ts else None,
        }
    except Exception as e:
        return {"location": "unknown", "error": str(e)}


# ── Goals ─────────────────────────────────────────────────────────────────────

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


# ── Predictions ───────────────────────────────────────────────────────────────

@app.get("/api/predictions")
def get_predictions():
    try:
        from intelligence.prediction_engine import predict_needs
        return predict_needs()
    except Exception:
        return []


# ── Memory ────────────────────────────────────────────────────────────────────

@app.get("/api/memory/profile")
def memory_profile():
    try:
        from memory.profile import get_all_profile
        return get_all_profile()
    except Exception:
        return {}

@app.get("/api/memory/preferences")
def memory_preferences():
    try:
        from memory.preferences import get_preferences
        rows = get_preferences()
        return [{"category": r[0], "key": r[1], "value": r[2], "confidence": r[3]} for r in rows]
    except Exception:
        return []

@app.get("/api/memory/events")
def memory_events(limit: int = 30):
    try:
        from memory.events import get_recent_events
        rows = get_recent_events(limit=limit)
        return [{"event_type": r[0], "summary": r[1], "detail": r[2],
                 "importance": r[3], "timestamp": r[4]} for r in rows]
    except Exception:
        return []

@app.delete("/api/memory/learned/{fact_id}")
def delete_learned_fact(fact_id: int):
    try:
        from database import get_conn, close_conn
        conn = get_conn()
        conn.cursor().execute("DELETE FROM learned_facts WHERE id=?", (fact_id,))
        conn.commit()
        close_conn()
        return {"ok": True}
    except Exception:
        raise HTTPException(500, "Delete failed")


# ── Knowledge ─────────────────────────────────────────────────────────────────

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
                "size_kb": round(len(data) / 1024, 1), "message": "Saved. Indexing in background."}
    except HTTPException:
        raise
    except Exception:
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
                f"Summarize in 3 bullet points:\n\nDoc: {filename}\n\n{chunks[:2000]}"}],
            max_tokens=250, temperature=0.3)
        summary = (resp.choices[0].message.content or "").strip()
        cache.set(ck, summary)
        return {"filename": filename, "summary": summary, "source": "generated"}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(500, "Summary failed")


# ── Push notifications ────────────────────────────────────────────────────────

class PushTokenPayload(BaseModel):
    token: str
    platform: Optional[str] = "expo"

class PushTestPayload(BaseModel):
    token: Optional[str] = None
    title: Optional[str] = "ORA Test"
    body:  Optional[str] = "Push notifications are working"

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
        raise HTTPException(500, "Token registration failed")

@app.delete("/api/push/register")
async def push_unregister(payload: PushTokenPayload):
    try:
        from fcm import remove_token
        remove_token(payload.token.strip())
        return {"ok": True}
    except Exception:
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
        body  = payload.body  or "Push notifications are working"
        if payload.token:
            sent = send_push_to_token(payload.token.strip(), title, body)
        else:
            sent = send_push(title=title, body=body)
        return {"ok": sent, "message": "Dispatched" if sent else "No tokens registered"}
    except Exception:
        raise HTTPException(500, "Push test failed")


# ── Weather ───────────────────────────────────────────────────────────────────

@app.get("/api/weather")
def weather():
    try:
        from connectors.weather import get_weather
        return get_weather() or {}
    except Exception:
        return {}


# ── Drive ─────────────────────────────────────────────────────────────────────

@app.post("/api/drive/sync")
def drive_sync_now():
    try:
        from connectors.drive import sync_drive
        sync_drive()
        return {"status": "sync triggered"}
    except Exception:
        raise HTTPException(500, "Drive sync failed")


# ── Gmail ─────────────────────────────────────────────────────────────────────

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
    except Exception:
        return []

@app.get("/api/gmail/replies/pending")
def gmail_replies_pending(limit: int = 15):
    try:
        from connectors.gmail import get_pending_replies
        return get_pending_replies(limit=limit)
    except Exception:
        return []

@app.get("/api/gmail/replies/history")
def gmail_replies_history(limit: int = 20):
    try:
        from connectors.gmail import get_reply_history
        return get_reply_history(limit=limit)
    except Exception:
        return []

@app.get("/api/gmail/replies/stats")
def gmail_reply_stats():
    try:
        from connectors.gmail import get_reply_stats
        return get_reply_stats()
    except Exception:
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


class GenerateSingleRequest(BaseModel):
    email_id:       str
    thread_id:      Optional[str] = None
    subject:        str = ""
    sender:         str = ""
    email_body:     str = ""
    suggested_text: Optional[str] = None  # if provided, skip AI generation
    tone:           str = "professional"
    account:        str = "primary"

@app.post("/api/gmail/replies/generate-single")
def gmail_generate_single(payload: GenerateSingleRequest):
    """Generate (or save) a reply for one specific email. Used by the compose modal."""
    try:
        from connectors.gmail import suggest_reply, save_suggested_reply

        text = payload.suggested_text
        if not text:
            email_data = {
                "id":      payload.email_id,
                "subject": payload.subject,
                "sender":  payload.sender,
                "body":    payload.email_body,
                "account": payload.account,
            }
            text = suggest_reply(email_data, tone=payload.tone)

        saved = save_suggested_reply(
            email_id=payload.email_id,
            thread_id=payload.thread_id,
            subject=payload.subject,
            sender=payload.sender,
            email_body=payload.email_body,
            suggested_text=text,
            tone=payload.tone,
            account=payload.account,
        )

        from database import get_conn, close_conn
        conn = get_conn()
        row = conn.execute(
            "SELECT id FROM suggested_replies WHERE email_id=? ORDER BY created_at DESC LIMIT 1",
            (payload.email_id,)
        ).fetchone()
        close_conn()

        return {
            "ok":             saved,
            "suggested_text": text,
            "reply_id":       row[0] if row else None,
        }
    except Exception as e:
        raise HTTPException(500, str(e))


# ── Dashboard endpoints ───────────────────────────────────────────────────────

@app.get("/api/the-number")
def the_number():
    try:
        from database import get_tasks
        from intelligence.goals_engine import get_goals
        pending = get_tasks("pending")
        goals   = get_goals("active")
        now = datetime.now()
        overdue = sum(1 for t in pending if t[4] and datetime.fromisoformat(t[4]) < now)
        high_priority = sum(1 for t in pending if t[2] == "high")
        avg_goal_progress = int(sum(g.get("progress", 0) for g in goals) / len(goals)) if goals else 0
        context_parts = []
        if overdue:       context_parts.append(f"{overdue} overdue")
        if high_priority: context_parts.append(f"{high_priority} high priority")
        return {
            "number":        len(pending),
            "label":         "pending tasks",
            "context":       ", ".join(context_parts) if context_parts else "on track",
            "goal_progress": avg_goal_progress,
            "goal_count":    len(goals),
        }
    except Exception:
        return {"number": 0, "label": "tasks", "context": ""}

@app.get("/api/briefing")
def get_briefing():
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
            spend = float(today_spend.get("total", 0)) if isinstance(today_spend, dict) else float(today_spend or 0)
        except Exception:
            pass
        parts = []
        if pending:
            high = [t for t in pending if t[2] == "high"]
            parts.append(f"{len(pending)} tasks pending" + (f" ({len(high)} high priority)" if high else ""))
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
        return {"briefing": "Briefing unavailable.", "source": "error"}


# ── Proactive ─────────────────────────────────────────────────────────────────

@app.post("/api/proactive/run")
def proactive_run_now():
    try:
        from intelligence.proactive_engine import run_proactive_checks
        from agent_guard import reset_all
        reset_all()
        run_proactive_checks()
        return {"ok": True, "message": "Proactive checks fired"}
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/api/proactive/status")
def proactive_status():
    try:
        from database import get_tasks, get_conn, close_conn
        now     = datetime.now()
        pending = get_tasks("pending")
        overdue = [t for t in pending if t[4] and datetime.fromisoformat(t[4]) < now]
        high    = [t for t in pending if t[2] == "high"]
        conn = get_conn()
        old_replies     = conn.execute("SELECT COUNT(*) FROM suggested_replies WHERE status='pending' AND created_at < datetime('now', '-24 hours')").fetchone()[0]
        pending_replies = conn.execute("SELECT COUNT(*) FROM suggested_replies WHERE status='pending'").fetchone()[0]
        close_conn()
        signals = []
        if overdue:       signals.append({"type": "overdue_tasks",       "count": len(overdue), "severity": "high"})
        if len(high) >= 2: signals.append({"type": "high_priority_backlog", "count": len(high),   "severity": "medium"})
        if old_replies:   signals.append({"type": "unanswered_emails",   "count": old_replies,   "severity": "medium"})
        return {
            "hour":            now.hour,
            "pending_tasks":   len(pending),
            "overdue_tasks":   len(overdue),
            "high_priority":   len(high),
            "pending_replies": pending_replies,
            "old_replies":     old_replies,
            "active_signals":  signals,
        }
    except Exception as e:
        raise HTTPException(500, str(e))


# ── Agent status ──────────────────────────────────────────────────────────────

@app.post("/api/agent/run")
def agent_run_now_post():
    try:
        from agent import run_agent_cycle
        run_agent_cycle()
        return {"status": "cycle complete"}
    except Exception:
        raise HTTPException(500, "Agent cycle failed")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _safe_filename(name: str) -> str:
    import re
    name = os.path.basename(name)
    name = re.sub(r"[^\w.\-]", "_", name)
    return name[:120]