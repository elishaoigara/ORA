import os
import traceback
import psutil

from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from groq import Groq

# ========================
# CONFIG
# ========================
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
FRONTEND_URL = os.getenv("FRONTEND_URL", "*")

client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# ========================
# APP
# ========================
app = FastAPI(title="ORA Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL] if FRONTEND_URL != "*" else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ========================
# STARTUP
# ========================
@app.on_event("startup")
def on_startup():
    from database import init_db, init_tasks_table
    from memory.profile import init_profile
    from mpesa_engine import init_mpesa_table
    init_db()
    init_tasks_table()
    init_profile()
    init_mpesa_table()
    print("[API] Database initialized")

    # ── Telegram Bot ──────────────────────────────────────────
    import threading
    from config import TELEGRAM_BOT_TOKEN

    if TELEGRAM_BOT_TOKEN:
        def _telegram_loop():
            import time
            time.sleep(3)  # wait for API to fully come up
            print("[TELEGRAM] Starting bot thread...")
            from telegram_bot import run_telegram_bot
            while True:
                try:
                    run_telegram_bot()
                except Exception as e:
                    print(f"[TELEGRAM ERROR] {e} — restarting in 10s")
                    time.sleep(10)

        t = threading.Thread(target=_telegram_loop, daemon=True)
        t.start()
        print("[TELEGRAM] Bot thread launched")
    else:
        print("[TELEGRAM] No token set — bot disabled")


# ========================
# HEALTH
# ========================
@app.api_route("/api/health", methods=["GET", "HEAD"])
async def health(request: Request):
    return JSONResponse(content={"status": "ORA online"}, status_code=200)


@app.get("/")
def root():
    return {"status": "ORA API running"}


# ========================
# STATUS
# ========================
@app.get("/api/status")
def status():
    try:
        from datetime import datetime
        return {
            "cpu": psutil.cpu_percent(interval=0.5),
            "ram": psutil.virtual_memory().percent,
            "disk_free_gb": round(psutil.disk_usage("/").free / (1024 ** 3), 2),
            "last_updated": datetime.now().isoformat(),
        }
    except Exception:
        return {"status": "error"}


# ========================
# CHAT — uses full context + memory + knowledge
# ========================
@app.post("/api/chat")
async def chat(payload: dict):
    try:
        if client is None:
            return {"reply": "ERROR: GROQ_API_KEY not configured on server"}

        user_text = payload.get("message", "").strip()
        if not user_text:
            return {"reply": "Please enter a message."}

        from context import build_system_prompt
        from database import save_conversation, get_conversation_history

        system_prompt = build_system_prompt(query=user_text)

        history = get_conversation_history(limit=6)
        messages = [{"role": "system", "content": system_prompt}]
        for role, content, _ in history:
            messages.append({
                "role": "user" if role == "user" else "assistant",
                "content": content
            })
        messages.append({"role": "user", "content": user_text})

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            max_tokens=400,
            temperature=0.4,
        )

        reply = response.choices[0].message.content or "I don't know."

        save_conversation("user", user_text)
        save_conversation("assistant", reply)

        return {"reply": reply}

    except Exception:
        print(traceback.format_exc())
        return {"reply": "ORA error. Please try again."}


# ========================
# CONVERSATIONS
# ========================
@app.get("/api/conversations")
def conversations():
    try:
        from database import get_conversation_history
        rows = get_conversation_history(limit=50)
        return [{"role": r[0], "content": r[1], "timestamp": r[2]} for r in rows]
    except Exception:
        return []


# ========================
# TASKS
# ========================
@app.get("/api/tasks")
def get_tasks_endpoint():
    try:
        from database import get_tasks
        rows = get_tasks("pending")
        return [
            {"id": r[0], "title": r[1], "priority": r[2],
             "created_at": r[3], "due_at": r[4]}
            for r in rows
        ]
    except Exception:
        return []


@app.post("/api/tasks")
async def add_task(payload: dict):
    try:
        from database import add_task
        title = payload.get("title", "").strip()
        if not title:
            return JSONResponse({"error": "title required"}, status_code=400)
        priority = payload.get("priority", "medium")
        due_at = payload.get("due_at")
        add_task(title, priority=priority, due_at=due_at)
        return {"status": "created"}
    except Exception:
        return JSONResponse({"error": "failed"}, status_code=500)


@app.post("/api/tasks/{task_id}/complete")
async def complete_task(task_id: int):
    try:
        from database import complete_task
        complete_task(task_id)
        return {"status": "done"}
    except Exception:
        return JSONResponse({"error": "failed"}, status_code=500)


@app.delete("/api/tasks/{task_id}")
async def delete_task(task_id: int):
    try:
        from database import delete_task
        delete_task(task_id)
        return {"status": "deleted"}
    except Exception:
        return JSONResponse({"error": "failed"}, status_code=500)


# ========================
# ALERTS
# ========================
@app.get("/api/alerts")
def get_alerts():
    try:
        from database import get_recent_alerts
        rows = get_recent_alerts(limit=20)
        return [
            {"id": r[0], "rule_name": r[1], "message": r[2],
             "severity": r[3], "timestamp": r[4], "acknowledged": bool(r[5])}
            for r in rows
        ]
    except Exception:
        return []


@app.post("/api/alerts/{alert_id}/ack")
async def ack_alert(alert_id: int, payload: dict = {}):
    try:
        from database import acknowledge_alert
        feedback = payload.get("feedback") if payload else None
        acknowledge_alert(alert_id, feedback=feedback)
        return {"status": "acknowledged"}
    except Exception:
        return JSONResponse({"error": "failed"}, status_code=500)


# ========================
# THE NUMBER (top task of the day)
# ========================
@app.get("/api/the-number")
def the_number():
    try:
        from core import get_the_number
        result = get_the_number()
        if not result:
            return {"status": "empty"}
        return result
    except Exception:
        return {"status": "empty"}


# ========================
# M-PESA
# ========================
@app.get("/api/mpesa/summary")
def mpesa_summary():
    try:
        from mpesa_engine import get_today_spend, get_average_daily_spend, get_daily_summary
        return {
            "today": get_today_spend(),
            "average_daily": get_average_daily_spend(),
            "last_7_days": get_daily_summary(days=7),
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@app.post("/api/mpesa/sms")
async def mpesa_ingest(payload: dict):
    try:
        from mpesa_engine import ingest_sms
        sms = payload.get("sms", "").strip()
        if not sms:
            return JSONResponse({"error": "sms required"}, status_code=400)
        result = ingest_sms(sms)
        return result
    except Exception:
        return JSONResponse({"error": "failed"}, status_code=500)


@app.get("/api/mpesa/transactions")
def mpesa_transactions():
    try:
        from mpesa_engine import get_recent_transactions
        return get_recent_transactions(limit=50)
    except Exception:
        return []


# ========================
# KNOWLEDGE
# ========================
@app.post("/api/knowledge/upload")
async def knowledge_upload(
    file: UploadFile = File(...),
    tags: str = Form(default="")
):
    try:
        from config import UPLOADS_DIR
        from knowledge import on_upload
        import shutil

        os.makedirs(UPLOADS_DIR, exist_ok=True)
        dest = os.path.join(UPLOADS_DIR, file.filename)

        with open(dest, "wb") as f:
            shutil.copyfileobj(file.file, f)

        result = on_upload(dest, file.filename, tags=tags)
        return result
    except Exception:
        print(traceback.format_exc())
        return JSONResponse({"error": "upload failed"}, status_code=500)


@app.get("/api/knowledge/documents")
def knowledge_documents():
    try:
        from knowledge import get_all_documents
        return get_all_documents()
    except Exception:
        return []


@app.delete("/api/knowledge/documents/{filename}")
async def knowledge_delete(filename: str):
    try:
        from knowledge import delete_document
        delete_document(filename)
        return {"status": "deleted"}
    except Exception:
        return JSONResponse({"error": "failed"}, status_code=500)


@app.get("/api/knowledge/search")
async def knowledge_search(q: str = ""):
    try:
        if not q:
            return {"results": []}
        from knowledge import search_and_format
        context = search_and_format(q, n_results=5)
        return {"context": context}
    except Exception:
        return {"results": []}


# ========================
# MEMORY
# ========================
@app.get("/api/memory/events")
def memory_events():
    try:
        from memory.events import get_recent_events
        rows = get_recent_events(limit=30)
        return [
            {"event_type": r[0], "summary": r[1], "detail": r[2],
             "importance": r[3], "timestamp": r[4]}
            for r in rows
        ]
    except Exception:
        return []


@app.get("/api/memory/profile")
def memory_profile():
    try:
        from memory.profile import get_all_profile
        return get_all_profile()
    except Exception:
        return {}


# ========================
# PREFERENCES
# ========================
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
        return []