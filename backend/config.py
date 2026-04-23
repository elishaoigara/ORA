import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")
LOOP_INTERVAL      = int(os.getenv("ORA_LOOP_INTERVAL", 30))
GROQ_API_KEY       = os.getenv("GROQ_API_KEY")

# ── Persistent storage paths ───────────────────────────────────
# On Render: /opt/ora-data  (mounted disk, survives restarts/deploys)
# Locally:   ./data         (auto-created, same structure)

_BASE = os.getenv("ORA_DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))

DATA_DIR     = _BASE
UPLOADS_DIR  = os.getenv("ORA_UPLOADS_DIR",  os.path.join(_BASE, "uploads"))
DB_PATH      = os.getenv("ORA_DB_PATH",       os.path.join(_BASE, "ora_knowledge.db"))
INDEX_PATH   = os.getenv("ORA_INDEX_PATH",    os.path.join(_BASE, "ora_index.json"))

# Create directories on import (safe to call multiple times)
os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(DATA_DIR,    exist_ok=True)