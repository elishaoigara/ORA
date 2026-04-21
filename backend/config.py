import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
LOOP_INTERVAL = int(os.getenv("ORA_LOOP_INTERVAL", 30))
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
