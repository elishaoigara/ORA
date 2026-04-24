"""
ORA Configuration — Production Ready
Handles environment variables, storage paths, and model selection.
"""

import os
from dotenv import load_dotenv

# Load .env locally (Render already injects env vars)
load_dotenv()


# ============================================================
# CORE API KEYS
# ============================================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")

GROQ_API_KEY       = os.getenv("GROQ_API_KEY")


# ============================================================
# ORA RUNTIME CONFIG
# ============================================================
LOOP_INTERVAL = int(os.getenv("ORA_LOOP_INTERVAL", 30))


# ============================================================
# STORAGE (Render persistent disk safe)
# ============================================================
# Render sets ORA_DATA_DIR = /opt/ora-data
# Local fallback = ./data
_BASE = os.getenv(
    "ORA_DATA_DIR",
    os.path.join(os.path.dirname(__file__), "data")
)

DATA_DIR    = _BASE
UPLOADS_DIR = os.path.join(_BASE, "uploads")

DB_PATH     = os.path.join(_BASE, "ora_knowledge.db")
INDEX_PATH  = os.path.join(_BASE, "ora_index.json")


# Ensure directories exist
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(UPLOADS_DIR, exist_ok=True)


# ============================================================
# GROQ MODEL CONFIG (CRITICAL FIX)
# ============================================================
# These can be overridden in Render environment variables

GROQ_MODEL_PRIMARY = os.getenv(
    "GROQ_MODEL_PRIMARY",
    "llama-3.3-70b-versatile"
)

GROQ_MODEL_FALLBACK = os.getenv(
    "GROQ_MODEL_FALLBACK",
    "llama-3.1-8b-instant"
)


# ============================================================
# SAFETY CHECKS (optional but useful)
# ============================================================
if not GROQ_API_KEY:
    print("[CONFIG WARNING] GROQ_API_KEY not set")

if not TELEGRAM_BOT_TOKEN:
    print("[CONFIG WARNING] TELEGRAM_BOT_TOKEN not set")

if not TELEGRAM_CHAT_ID:
    print("[CONFIG WARNING] TELEGRAM_CHAT_ID not set")