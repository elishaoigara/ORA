import asyncio
from telegram_bot import notify

def execute(decision: dict):
    for action in decision.get("actions", []):
        if action["type"] == "alert":
            print(f"  🔴 ALERT: {action['message']}")
            notify(action["message"], is_alert=True)
        elif action["type"] == "response":
            print(f"  💬 {action['message']}")
            notify(action["message"])
        elif action["type"] == "log":
            print(f"  ✅ {action['message']}")