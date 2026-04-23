import os
import json
import traceback
import psutil

from fastapi import FastAPI, Request
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
# HEALTH (FIXED FOR UPTIME ROBOT)
# ========================
@app.api_route("/api/health", methods=["GET", "HEAD"])
def health():
    return JSONResponse({"status": "ORA online"})


# ========================
# ROOT
# ========================
@app.get("/")
def root():
    return {"status": "ORA API running"}


# ========================
# CHAT (COST SAFE)
# ========================
@app.post("/api/chat")
async def chat(payload: dict):
    try:
        if not client:
            return {"reply": "Groq not configured"}

        user_text = payload.get("message", "").strip()
        if not user_text:
            return {"reply": "Empty message"}

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are ORA AI."},
                {"role": "user", "content": user_text}
            ],
            max_tokens=300,
            temperature=0.7,
        )

        return {
            "reply": response.choices[0].message.content
        }

    except Exception:
        print(traceback.format_exc())
        return {"reply": "ORA error"}
        

# ========================
# STATUS (SAFE MONITOR)
# ========================
@app.get("/api/status")
def status():
    return {
        "cpu": psutil.cpu_percent(),
        "ram": psutil.virtual_memory().percent
    }


# ========================
# TASK PLACEHOLDER
# ========================
@app.get("/api/tasks")
def tasks():
    return []