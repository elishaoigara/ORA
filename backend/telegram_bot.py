"""
ORA Telegram Bot â€” Communication Hub
Two-way: ORA reaches you AND you control ORA via Telegram.
Render free tier safe: long-poll with 15s timeout, no webhooks needed.

Commands you can send:
  /start         â€” welcome + command list
  /brief         â€” morning briefing now
  /tasks         â€” list pending tasks
  /done <id>     â€” complete a task
  /goals         â€” list active goals
  /goal <text>   â€” add a new goal
  /spend         â€” today's M-Pesa summary
  /status        â€” system health
  /predict       â€” what ORA thinks you need right now
  /remind <text> â€” set a quick reminder (stored as high-priority task)

Any other text â€” ORA answers it (full chat with KB + router)
"""

print("[TELEGRAM] Loading bot...")

import time
import requests
import traceback
from datetime import datetime

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, GROQ_API_KEY
from database import save_conversation, get_conversation_history
from memory.events import log_memory_event
from context import build_system_prompt
from groq import Groq

TELEGRAM_ENABLED = bool(TELEGRAM_BOT_TOKEN)
BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}" if TELEGRAM_ENABLED else None
client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
ALLOWED_CHAT_ID = int(TELEGRAM_CHAT_ID) if TELEGRAM_CHAT_ID else None

print(f"[TELEGRAM] Enabled: {TELEGRAM_ENABLED}")
print(f"[TELEGRAM] Chat ID: {ALLOWED_CHAT_ID}")

# â”€â”€ Simple response cache (avoid duplicate Groq calls) â”€â”€â”€â”€â”€â”€â”€â”€
_CACHE: dict = {}
_CACHE_TTL = 180

def _get_cache(key):
    item = _CACHE.get(key)
    if not item: return None
    if time.time() - item["t"] > _CACHE_TTL:
        del _CACHE[key]
        return None
    return item["v"]

def _set_cache(key, value):
    if len(_CACHE) > 100:
        oldest = sorted(_CACHE.items(), key=lambda x: x[1]["t"])[:20]
        for k, _ in oldest: del _CACHE[k]
    _CACHE[key] = {"v": value, "t": time.time()}


# â”€â”€ Telegram API helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def tg_send(chat_id, text):
    if not TELEGRAM_ENABLED: return None
    # Telegram message limit is 4096 chars
    text = text[:4000] if len(text) > 4000 else text
    try:
        r = requests.post(
            f"{BASE}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
            timeout=10,
        )
        return r.json().get("result", {}).get("message_id")
    except Exception as e:
        print("[TG SEND ERROR]", e)
        return None

def tg_edit(chat_id, message_id, text):
    if not TELEGRAM_ENABLED or not message_id: return
    try:
        requests.post(
            f"{BASE}/editMessageText",
            json={"chat_id": chat_id, "message_id": message_id, "text": text},
            timeout=10,
        )
    except Exception as e:
        print("[TG EDIT ERROR]", e)

def tg_get_updates(offset=None):
    if not TELEGRAM_ENABLED: return []
    try:
        params = {"timeout": 15, "allowed_updates": ["message"]}
        if offset: params["offset"] = offset
        r = requests.get(f"{BASE}/getUpdates", params=params, timeout=20)
        return r.json().get("result", [])
    except Exception as e:
        print("[TG POLL ERROR]", e)
        return []

def notify(text: str, is_alert: bool = False):
    """Send a proactive message to the user. Called by other modules."""
    if not ALLOWED_CHAT_ID: return
    prefix = "ðŸ”´ *ALERT*\n" if is_alert else "ðŸ’¡ "
    tg_send(ALLOWED_CHAT_ID, f"{prefix}{text}")


# â”€â”€ Command handlers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def _cmd_start(chat_id):
    msg = (
        "*ORA â€” Autonomous Assistant*\n\n"
        "I monitor your tasks, goals, spending and can answer questions.\n\n"
        "*Commands:*\n"
        "`/brief` â€” morning briefing\n"
        "`/tasks` â€” pending tasks\n"
        "`/done <id>` â€” complete task by ID\n"
        "`/goals` â€” active goals\n"
        "`/goal <text>` â€” add a goal\n"
        "`/spend` â€” M-Pesa summary\n"
        "`/status` â€” system health\n"
        "`/predict` â€” what I think you need now\n"
        "`/remind <text>` â€” set a reminder\n\n"
        "Or just type anything â€” I'll answer."
    )
    tg_send(chat_id, msg)


def _cmd_tasks(chat_id):
    try:
        from database import get_tasks
        tasks = get_tasks("pending")
        if not tasks:
            tg_send(chat_id, "âœ… No pending tasks.")
            return
        lines = [f"*Pending tasks ({len(tasks)}):*"]
        for t in tasks[:10]:
            due = f" â€” due {t[4][:10]}" if t[4] else ""
            pri = {"high": "ðŸ”´", "medium": "ðŸŸ¡", "low": "ðŸŸ¢"}.get(t[2], "â€¢")
            lines.append(f"{pri} `[{t[0]}]` {t[1]}{due}")
        tg_send(chat_id, "\n".join(lines))
    except Exception as e:
        tg_send(chat_id, f"Error: {e}")


def _cmd_done(chat_id, args: str):
    try:
        task_id = int(args.strip())
        from database import complete_task, get_tasks
        complete_task(task_id)
        tg_send(chat_id, f"âœ… Task {task_id} marked complete.")
    except ValueError:
        tg_send(chat_id, "Usage: `/done <task_id>` â€” get IDs from `/tasks`")
    except Exception as e:
        tg_send(chat_id, f"Error: {e}")


def _cmd_goals(chat_id):
    try:
        from intelligence.goals_engine import get_goals
        goals = get_goals("active")
        if not goals:
            tg_send(chat_id, "No active goals. Add one with `/goal <text>`")
            return
        lines = [f"*Active goals ({len(goals)}):*"]
        for g in goals:
            bar = "â–ˆ" * (g["progress"] // 10) + "â–‘" * (10 - g["progress"] // 10)
            due = f" â€” due {g['due_at'][:10]}" if g.get("due_at") else ""
            lines.append(f"`[{g['id']}]` {g['goal'][:60]}{due}\n  `[{bar}]` {g['progress']}%")
        tg_send(chat_id, "\n\n".join(lines))
    except Exception as e:
        tg_send(chat_id, f"Error: {e}")


def _cmd_add_goal(chat_id, args: str):
    if not args.strip():
        tg_send(chat_id, "Usage: `/goal <your goal text>`")
        return
    try:
        from intelligence.goals_engine import add_goal
        gid = add_goal(args.strip())
        tg_send(chat_id, f"ðŸŽ¯ Goal added (ID {gid}): _{args.strip()[:80]}_")
    except Exception as e:
        tg_send(chat_id, f"Error: {e}")


def _cmd_spend(chat_id):
    try:
        from mpesa_engine import get_today_spend, get_average_daily_spend, get_recent_transactions
        today = get_today_spend()
        avg = get_average_daily_spend()
        recent = get_recent_transactions(limit=5) or []

        lines = ["*M-Pesa Summary*"]
        if today is not None:
            lines.append(f"Today: *KES {today:,.0f}*")
        if avg is not None:
            diff = float(today) - float(avg) if today is not None else 0.0  # type: ignore[arg-type]
            arrow = "â†‘" if diff > 0 else "â†“"
            lines.append(f"Daily avg: KES {avg:,.0f} ({arrow} {abs(diff):,.0f})")

        if recent:
            lines.append("\n*Recent transactions:*")
            for tx in recent[:5]:
                amount = tx.get("amount", 0)
                desc = tx.get("description", "")[:40]
                lines.append(f"â€¢ KES {amount:,.0f} â€” {desc}")

        tg_send(chat_id, "\n".join(lines))
    except Exception as e:
        tg_send(chat_id, f"Error: {e}")


def _cmd_status(chat_id):
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=0.5)
        ram = psutil.virtual_memory().percent
        now = datetime.now().strftime("%d %b %H:%M")

        # Health indicators
        cpu_icon = "ðŸ”´" if cpu > 80 else "ðŸŸ¡" if cpu > 50 else "ðŸŸ¢"
        ram_icon = "ðŸ”´" if ram > 85 else "ðŸŸ¡" if ram > 65 else "ðŸŸ¢"

        msg = (
            f"*ORA System Status* â€” {now}\n\n"
            f"{cpu_icon} CPU: {cpu:.0f}%\n"
            f"{ram_icon} RAM: {ram:.0f}%\n"
            f"ðŸŸ¢ Backend: online\n"
        )
        tg_send(chat_id, msg)
    except Exception as e:
        tg_send(chat_id, f"Error: {e}")


def _cmd_predict(chat_id):
    try:
        from intelligence.prediction_engine import predict_needs
        preds = predict_needs()
        if not preds:
            tg_send(chat_id, "Nothing to flag right now.")
            return
        lines = ["*What ORA sees right now:*"]
        for p in preds[:4]:
            icon = "ðŸ”´" if p["confidence"] >= 0.9 else "ðŸŸ¡" if p["confidence"] >= 0.75 else "ðŸ’­"
            lines.append(f"{icon} {p['message']}")
        tg_send(chat_id, "\n".join(lines))
    except Exception as e:
        tg_send(chat_id, f"Error: {e}")


def _cmd_remind(chat_id, args: str):
    if not args.strip():
        tg_send(chat_id, "Usage: `/remind <what to remind you about>`")
        return
    try:
        from database import add_task
        add_task(args.strip(), "high", None)
        tg_send(chat_id, f"â° Reminder set: _{args.strip()[:80]}_")
    except Exception as e:
        tg_send(chat_id, f"Error: {e}")


def _cmd_brief(chat_id):
    try:
        from briefing import generate_briefing
        text = generate_briefing()
        tg_send(chat_id, f"*Morning Briefing*\n\n{text}")
    except Exception as e:
        tg_send(chat_id, f"Error: {e}")


# â”€â”€ Chat handler (free-form text â†’ Groq) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def _handle_chat(chat_id, text: str):
    cached = _get_cache(text)
    if cached:
        tg_send(chat_id, cached)
        return

    # Show typing indicator
    mid = tg_send(chat_id, "â‹¯")

    try:
        # Intent parser first (free)
        try:
            from Intent_parser import parse_intent, execute_intent  # type: ignore[import]
            intent = parse_intent(text)
            if intent:
                result = execute_intent(intent)
                if result:
                    if mid: tg_edit(chat_id, mid, result)
                    else: tg_send(chat_id, result)
                    save_conversation("user", text)
                    save_conversation("assistant", result)
                    return
        except Exception as e:
            print(f"[TG INTENT] {e}")

        # KB context
        knowledge_ctx = ""
        try:
            from knowledge.pipeline import search_and_format
            knowledge_ctx = search_and_format(text, n_results=2) or ""
        except Exception:
            pass

        system_prompt = build_system_prompt(query=text)
        if knowledge_ctx:
            system_prompt += f"\n\n## KNOWLEDGE\n{knowledge_ctx[:500]}"

        history = get_conversation_history(limit=3)
        messages = [{"role": "system", "content": system_prompt}]
        for role, content, _ in history:
            messages.append({"role": "user" if role == "user" else "assistant", "content": content[:150]})
        messages.append({"role": "user", "content": text})

        # Small model for Telegram (fast response, low cost)
        from brain.router import classify, model_for
        q_type = classify(text)
        model, max_tok = model_for(q_type)
        # Cap Telegram responses shorter
        max_tok = min(max_tok, 300)

        response = client.chat.completions.create(  # type: ignore[arg-type]
            model=model, messages=messages,  # type: ignore[arg-type]
            max_tokens=max_tok, temperature=0.4,
        )
        reply = (response.choices[0].message.content or "").strip()

        _set_cache(text, reply)
        save_conversation("user", text)
        save_conversation("assistant", reply)

        if mid: tg_edit(chat_id, mid, reply)
        else: tg_send(chat_id, reply)

    except Exception as e:
        err = f"ORA error: {str(e)[:100]}"
        if mid: tg_edit(chat_id, mid, err)
        else: tg_send(chat_id, err)
        print("[TG CHAT ERROR]", traceback.format_exc())


# â”€â”€ Message dispatcher â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def handle_message(chat_id: int, text: str):
    if not text:
        return

    # Security: only respond to the configured chat
    if ALLOWED_CHAT_ID and chat_id != ALLOWED_CHAT_ID:
        print(f"[TG] Blocked unknown chat_id: {chat_id}")
        return

    t = text.strip()
    lower = t.lower()

    if lower.startswith("/start"):
        _cmd_start(chat_id)
    elif lower.startswith("/tasks"):
        _cmd_tasks(chat_id)
    elif lower.startswith("/done"):
        _cmd_done(chat_id, t[5:])
    elif lower.startswith("/goals"):
        _cmd_goals(chat_id)
    elif lower.startswith("/goal"):
        _cmd_add_goal(chat_id, t[5:])
    elif lower.startswith("/spend"):
        _cmd_spend(chat_id)
    elif lower.startswith("/status"):
        _cmd_status(chat_id)
    elif lower.startswith("/predict"):
        _cmd_predict(chat_id)
    elif lower.startswith("/remind"):
        _cmd_remind(chat_id, t[7:])
    elif lower.startswith("/brief"):
        _cmd_brief(chat_id)
    else:
        if client:
            _handle_chat(chat_id, t)
        else:
            tg_send(chat_id, "ORA: Groq API key not configured.")


# â”€â”€ Main poll loop â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def run_telegram_bot():
    """
    Long-poll loop. Runs in a daemon thread from api.py lifespan.
    15s poll timeout keeps connection alive without hammering Telegram.
    """
    print("[TELEGRAM] Bot running")
    offset = None

    while True:
        try:
            updates = tg_get_updates(offset)
            for update in updates:
                offset = update["update_id"] + 1
                msg = update.get("message") or {}
                chat_data = msg.get("chat") or {}
                chat_id: int | None = chat_data.get("id")
                text: str = msg.get("text") or ""
                if chat_id and text:
                    handle_message(chat_id, text)
        except Exception as e:
            print(f"[TELEGRAM LOOP ERROR] {e}")
            time.sleep(5)

