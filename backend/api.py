import os
import json
import uuid
import traceback
import threading
import time
import psutil
from datetime import datetime

from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from groq import Groq

# ========================
# DATABASE
# ========================
from database import (
    get_recent_alerts,
    get_system_stats,
    acknowledge_alert,
    get_tasks,
    get_conversation_history,
    save_conversation,
    init_db,
    init_tasks_table,
    log_event
)

# ========================
# MEMORY
# ========================
from memory.profile import get_all_profile, init_profile
from memory.events import get_recent_events, log_memory_event
from memory.preferences import get_preferences

# ========================
# CORE
# ========================
from context import build_system_prompt

from knowledge import (
    store_document,
    get_all_documents,
    delete_document,
    search_and_format,
    UPLOADS_PATH
)

# ========================
# ENV
# ========================
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
FRONTEND_URL = os.getenv("FRONTEND_URL", "*")

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


# ========================
# BACKGROUND MONITOR
# ========================
def monitoring_loop():
    while True:
        try:
            data = {
                "cpu_percent": psutil.cpu_percent(interval=1),
                "ram_percent": psutil.virtual_memory().percent,
                "disk_free_gb": psutil.disk_usage("/").free / (1024 ** 3),
                "timestamp": datetime.now().isoformat()
            }

            # ✅ FIX 1: json.dumps not str() — str() produces invalid JSON (single quotes)
            log_event("system", json.dumps(data))

        except Exception as e:
            print("[MONITOR ERROR]", e)

        time.sleep(5)


# ========================
# TELEGRAM BOT THREAD
# ========================
def start_telegram():
    try:
        from telegram_bot import run_telegram_bot
        print("[ORA] Telegram bot starting...")
        run_telegram_bot()
    except Exception as e:
        print(f"[TELEGRAM] Failed to start: {e}")


# ========================
# INIT
# ========================
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        init_db()
        init_tasks_table()
        init_profile()
        log_memory_event("system", "ORA API started", importance=6)

        # ✅ FIX 2: monitoring thread inside lifespan (on_event is ignored when lifespan is set)
        threading.Thread(target=monitoring_loop, daemon=True).start()
        print("[ORA] Monitoring thread started")

        # ✅ FIX 3: telegram was never launched from api.py — added here
        threading.Thread(target=start_telegram, daemon=True).start()

    except Exception:
        print("[INIT ERROR]", traceback.format_exc())

    yield


app = FastAPI(title="ORA Backend", lifespan=lifespan)


# ========================
# CORS
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
# HEALTH
# ========================
@app.get("/")
def root():
    return {"status": "ORA backend running"}


@app.get("/api/health")
@app.head("/api/health")
def health():
    return {"status": "ORA online"}


# ========================
# STATUS
# ========================
@app.get("/api/status")
def status():
    try:
        row = get_system_stats()
        if not row:
            return {"status": "warming_up"}

        data = json.loads(row[0])

        return {
            "cpu": data.get("cpu_percent", 0),
            "ram": data.get("ram_percent", 0),
            "disk_free_gb": data.get("disk_free_gb", 0),
            "last_updated": row[1]
        }

    except Exception:
        return {"status": "error", "detail": traceback.format_exc()}


# ========================
# ALERTS
# ========================
@app.get("/api/alerts")
def alerts():
    try:
        data = get_recent_alerts(20)
        return [
            {
                "id": a[0],
                "rule": a[1],
                "message": a[2],
                "severity": a[3],
                "timestamp": a[4],
                "acknowledged": bool(a[5])
            }
            for a in data
        ]
    except Exception:
        return []


@app.post("/api/alerts/{alert_id}/ack")
def ack(alert_id: int):
    try:
        acknowledge_alert(alert_id)
        return {"status": "acknowledged"}
    except Exception:
        return {"status": "error"}


# ========================
# MEMORY
# ========================
@app.get("/api/memory/profile")
def profile():
    return get_all_profile() or {}


@app.get("/api/memory/events")
def events():
    try:
        data = get_recent_events(limit=20)
        return [
            {
                "type": e[0],
                "summary": e[1],
                "importance": e[3],
                "timestamp": e[4]
            }
            for e in data
        ]
    except Exception:
        return []


@app.get("/api/memory/preferences")
def prefs():
    try:
        data = get_preferences()
        return [
            {
                "category": p[0],
                "key": p[1],
                "value": p[2],
                "confidence": p[3]
            }
            for p in data
        ]
    except Exception:
        return []


# ========================
# TASKS
# ========================
@app.get("/api/tasks")
def tasks():
    try:
        data = get_tasks("pending")
        return [
            {
                "id": t[0],
                "title": t[1],
                "priority": t[2],
                "created_at": t[3],
                "due_at": t[4]
            }
            for t in data
        ]
    except Exception:
        return []


# ========================
# CHAT ENGINE
# ========================
@app.get("/api/conversation-history")
def get_conversation_history_api():
    try:
        history = get_conversation_history(limit=20) # Use the same limit as in chat
        return [
            {"role": h[0], "content": h[1], "timestamp": h[2]}
            for h in history
        ]
    except Exception:
        return []


@app.post("/api/chat")
async def chat(payload: dict):
    try:
        user_text = payload.get("message", "").strip()
        if not user_text:
            return {"reply": "Say something."}

        save_conversation("user", user_text)
        log_memory_event("conversation", user_text[:80], importance=4)

        if not GROQ_API_KEY:
            return {"reply": "GROQ_API_KEY missing."}

        client = Groq(api_key=GROQ_API_KEY)

        system_prompt = build_system_prompt(query=user_text)

        history = get_conversation_history(limit=20)

        messages = [{"role": "system", "content": system_prompt}]

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

    except Exception:
        print("[CHAT ERROR]", traceback.format_exc())
        return {"reply": "ORA temporarily unavailable."}