"""
ORA Configuration — Production Ready
Single source of truth for all environment variables.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── CORE API KEYS ─────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")
GROQ_API_KEY       = os.getenv("GROQ_API_KEY")

# ── GOOGLE OAUTH ──────────────────────────────────────────────
GOOGLE_CLIENT_ID     = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI  = os.getenv("GOOGLE_REDIRECT_URI", "")

# ── GITHUB ────────────────────────────────────────────────────
GITHUB_TOKEN    = os.getenv("GITHUB_TOKEN", "")
GITHUB_USERNAME = os.getenv("GITHUB_USERNAME", "")

# ── WEATHER (Open-Meteo — free, no key needed) ────────────────
WEATHER_LAT = os.getenv("WEATHER_LAT", "-1.2921")   # Nairobi default
WEATHER_LON = os.getenv("WEATHER_LON", "36.8219")

# ── ORA RUNTIME ───────────────────────────────────────────────
LOOP_INTERVAL = int(os.getenv("ORA_LOOP_INTERVAL", 30))

# ── STORAGE (Render persistent disk safe) ────────────────────
_BASE = os.getenv(
    "ORA_DATA_DIR",
    os.path.join(os.path.dirname(__file__), "data")
)

DATA_DIR    = _BASE
UPLOADS_DIR = os.path.join(_BASE, "uploads")
DB_PATH     = os.path.join(_BASE, "ora_knowledge.db")
INDEX_PATH  = os.path.join(_BASE, "ora_index.json")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(UPLOADS_DIR, exist_ok=True)

# ── GROQ MODELS ───────────────────────────────────────────────
GROQ_MODEL_PRIMARY  = os.getenv("GROQ_MODEL_PRIMARY",  "llama-3.3-70b-versatile")
GROQ_MODEL_FALLBACK = os.getenv("GROQ_MODEL_FALLBACK", "llama-3.1-8b-instant")

# ── STARTUP WARNINGS ─────────────────────────────────────────
if not GROQ_API_KEY:
    print("[CONFIG WARNING] GROQ_API_KEY not set")
if not TELEGRAM_BOT_TOKEN:
    print("[CONFIG WARNING] TELEGRAM_BOT_TOKEN not set")
if not TELEGRAM_CHAT_ID:
    print("[CONFIG WARNING] TELEGRAM_CHAT_ID not set")
if not GOOGLE_CLIENT_ID:
    print("[CONFIG WARNING] GOOGLE_CLIENT_ID not set — Google features disabled")
if not GITHUB_TOKEN:
    print("[CONFIG WARNING] GITHUB_TOKEN not set — GitHub connector disabled")
