import os
import traceback
import psutil
import threading
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from groq import Groq

# ========================
# APP
# ========================
app = FastAPI(title="ORA Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========================
# GROQ
# ========================
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None


# ============================================================
# FIX 1 — DATABASE INITIALIZATION (CRITICAL)
# ============================================================
@app.on_event("startup")
def startup():
    """
    THIS FIXES YOUR ERROR:
    'no such table: conversations / tasks'
    """

    try:
        from database import init_db, init_tasks_table

        init_db()
        init_tasks_table()

        print("[ORA] DATABASE INITIALIZED SUCCESSFULLY")

    except Exception as e:
        print("[ORA DB INIT ERROR]", e)
        print(traceback.format_exc())


    # ========================
    # TELEGRAM SAFE START
    # ========================
    try:
        from config import TELEGRAM_BOT_TOKEN

        if TELEGRAM_BOT_TOKEN:

            def bot_runner():
                time.sleep(3)
                from telegram_bot import run_telegram_bot

                print("[TELEGRAM] BOT STARTED")

                while True:
                    try:
                        run_telegram_bot()
                    except Exception as e:
                        print("[TELEGRAM ERROR]", e)
                        time.sleep(5)

            threading.Thread(target=bot_runner, daemon=True).start()

    except Exception as e:
        print("[TELEGRAM START ERROR]", e)


# ========================
# HEALTH
# ========================
@app.api_route("/api/health", methods=["GET", "HEAD"])
async def health(request: Request):
    return {"status": "ORA online"}


@app.get("/")
def root():
    return {"status": "ORA running"}


# ========================
# STATUS
# ========================
@app.get("/api/status")
def status():
    try:
        from datetime import datetime

        return {
            "cpu": psutil.cpu_percent(interval=0.2),
            "ram": psutil.virtual_memory().percent,
            "time": datetime.utcnow().isoformat()
        }

    except Exception:
        return {"status": "error"}


# ========================
# CHAT
# ========================
class ChatRequest(BaseModel):
    message: str


@app.post("/api/chat")
async def chat(payload: ChatRequest):
    try:
        if not client:
            return {"reply": "Groq not configured"}

        user_text = payload.message.strip()
        if not user_text:
            return {"reply": "Empty message"}

        # FIX: DB imports AFTER init_db
        from database import save_conversation, get_conversation_history
        from context import build_system_prompt

        history = get_conversation_history(limit=6)

        # OPTIONAL knowledge layer
        knowledge_context = ""
        try:
            from knowledge import search_and_format
            knowledge_context = search_and_format(user_text, n_results=5) or ""
        except Exception:
            pass

        system_prompt = build_system_prompt(query=user_text)

        if knowledge_context:
            system_prompt += f"\n\nKNOWLEDGE:\n{knowledge_context}"

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

        reply = response.choices[0].message.content

        save_conversation("user", user_text)
        save_conversation("assistant", reply)

        return {"reply": reply}

    except Exception as e:
        print(traceback.format_exc())
        return {"reply": "ORA error"}