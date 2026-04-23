import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")
LOOP_INTERVAL      = int(os.getenv("ORA_LOOP_INTERVAL", 30))
GROQ_API_KEY       = os.getenv("GROQ_API_KEY")

# ── Persistent storage ─────────────────────────────────────────
# ORA_DATA_DIR is set to /opt/ora-data in render.yaml (survives restarts).
# Falls back to ./data/ when running locally.
_BASE = os.getenv("ORA_DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))

DATA_DIR    = _BASE
UPLOADS_DIR = os.path.join(_BASE, "uploads")
DB_PATH     = os.path.join(_BASE, "ora_knowledge.db")
INDEX_PATH  = os.path.join(_BASE, "ora_index.json")

os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(DATA_DIR,    exist_ok=True)