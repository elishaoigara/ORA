import os
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

# SAFE CLIENT INIT
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
# SYSTEM PROMPT (ANTI-HALLUCINATION FIX)
# ========================
SYSTEM_PROMPT = """
You are ORA, a strict factual AI assistant.

RULES:
- Never invent facts.
- If unsure, say "I don't know".
- Do not assume identity, files, or external data.
- Be concise and grounded.
"""

# ========================
# HEALTH (FIXED FOR UPTIME ROBOT)
# ========================
@app.api_route("/api/health", methods=["GET", "HEAD"])
async def health(request: Request):
    return JSONResponse(
        content={"status": "ORA online"},
        status_code=200
    )

# ========================
# ROOT
# ========================
@app.get("/")
def root():
    return {"status": "ORA API running"}

# ========================
# CHAT (PRODUCTION SAFE)
# ========================
@app.post("/api/chat")
async def chat(payload: dict):
    try:
        if client is None:
            return {"reply": "ERROR: GROQ_API_KEY not configured on server"}

        user_text = payload.get("message", "").strip()
        if not user_text:
            return {"reply": "Please enter a message."}

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_text}
            ],
            max_tokens=250,     # lower = more stable + less hallucination
            temperature=0.3     # 🔥 IMPORTANT FIX (reduces hallucination)
        )

        reply = response.choices[0].message.content

        # safety cleanup (optional guardrail)
        if reply is None:
            reply = "I don't know."

        return {"reply": reply}

    except Exception:
        print(traceback.format_exc())
        return {"reply": "ORA error. Please try again."}

# ========================
# STATUS (SYSTEM MONITOR)
# ========================
@app.get("/api/status")
def status():
    try:
        return {
            "cpu": psutil.cpu_percent(interval=0.5),
            "ram": psutil.virtual_memory().percent
        }
    except Exception:
        return {"status": "error"}

# ========================
# TASKS (PLACEHOLDER SAFE)
# ========================
@app.get("/api/tasks")
def tasks():
    return []