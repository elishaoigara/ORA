"""
ORA Telegram Bot — Hardened + Full Commands
Fixes:
- /done now calls database.complete_task()
- Added /tasks, /goals, /mpesa, /brief commands
- notify() function added for briefing.py integration
- Model pulled from config (matches web chat quality)
- Safe polling loop with exponential back-off
- Added rate limiting, retry logic, and better error recovery
"""

import time
import traceback
import requests
from datetime import datetime
from threading import Lock
from typing import Optional, Dict, Any, List, Tuple
from functools import wraps
from collections import defaultdict

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, GROQ_API_KEY, GROQ_MODEL_PRIMARY
from database import save_conversation, get_conversation_history
from context import build_system_prompt
from groq import Groq


# ─────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────

TELEGRAM_ENABLED = bool(TELEGRAM_BOT_TOKEN)
BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}" if TELEGRAM_ENABLED else None

client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
ALLOWED_CHAT_ID = int(TELEGRAM_CHAT_ID) if TELEGRAM_CHAT_ID else None

# Rate limiting
RATE_LIMIT = defaultdict(list)
RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_MAX = 20  # messages per window

print("[TELEGRAM] Enabled:", TELEGRAM_ENABLED)


# ─────────────────────────────────────────────
# DECORATORS
# ─────────────────────────────────────────────

def rate_limit(chat_id: int) -> bool:
    """Check if user is rate limited"""
    now = time.time()
    window_start = now - RATE_LIMIT_WINDOW
    
    # Clean old timestamps
    RATE_LIMIT[chat_id] = [ts for ts in RATE_LIMIT[chat_id] if ts > window_start]
    
    if len(RATE_LIMIT[chat_id]) >= RATE_LIMIT_MAX:
        return False
    
    RATE_LIMIT[chat_id].append(now)
    return True


def retry_on_failure(max_retries: int = 3, delay: float = 1.0):
    """Retry decorator for API calls"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise
                    print(f"[RETRY] {func.__name__} failed (attempt {attempt+1}/{max_retries}): {e}")
                    time.sleep(delay * (2 ** attempt))  # Exponential backoff
            return None
        return wrapper
    return decorator


# ─────────────────────────────────────────────
# CACHE (SAFE)
# ─────────────────────────────────────────────

_CACHE: Dict[str, Dict[str, Any]] = {}
_CACHE_LOCK = Lock()
_CACHE_TTL = 180
_CACHE_MAX_SIZE = 100

def _get_cache(key: str) -> Optional[str]:
    with _CACHE_LOCK:
        item = _CACHE.get(key)
        if not item:
            return None
        if time.time() - item["t"] > _CACHE_TTL:
            _CACHE.pop(key, None)
            return None
        return item["v"]


def _set_cache(key: str, value: str):
    with _CACHE_LOCK:
        if len(_CACHE) >= _CACHE_MAX_SIZE:
            # Remove oldest 20% of entries
            oldest = sorted(_CACHE.items(), key=lambda x: x[1]["t"])[:20]
            for k, _ in oldest:
                _CACHE.pop(k, None)
        _CACHE[key] = {"v": value, "t": time.time()}


# ─────────────────────────────────────────────
# TELEGRAM HELPERS
# ─────────────────────────────────────────────

@retry_on_failure(max_retries=3, delay=1.0)
def tg_send(chat_id: int, text: str, parse_mode: Optional[str] = None, 
            reply_to_message_id: Optional[int] = None) -> Optional[int]:
    """Send message with retry logic"""
    if not TELEGRAM_ENABLED:
        return None
    
    try:
        payload = {
            "chat_id": chat_id,
            "text": text[:4000],  # Telegram limit
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if reply_to_message_id:
            payload["reply_to_message_id"] = reply_to_message_id
        
        r = requests.post(f"{BASE}/sendMessage", json=payload, timeout=15)
        result = r.json()
        
        if not result.get("ok"):
            print(f"[TG SEND ERROR] {result.get('description')}")
            return None
            
        return result.get("result", {}).get("message_id")
    except Exception as e:
        print(f"[TG SEND ERROR] {e}")
        raise


def tg_send_typing(chat_id: int):
    """Send typing action to indicate processing"""
    if not TELEGRAM_ENABLED:
        return
    try:
        requests.post(
            f"{BASE}/sendChatAction",
            json={"chat_id": chat_id, "action": "typing"},
            timeout=5
        )
    except Exception as e:
        print(f"[TG TYPING ERROR] {e}")


@retry_on_failure(max_retries=2, delay=0.5)
def tg_get_updates(offset: Optional[int] = None, timeout: int = 30) -> List[Dict]:
    """Get updates with timeout and error handling"""
    try:
        params: Dict[str, Any] = {"timeout": timeout}
        if offset:
            params["offset"] = offset
        
        r = requests.get(f"{BASE}/getUpdates", params=params, timeout=timeout + 5)
        data = r.json()
        
        if not data.get("ok"):
            print(f"[TG POLL ERROR] {data.get('description')}")
            return []
        
        return data.get("result", [])
    except Exception as e:
        print(f"[TG POLL ERROR] {e}")
        return []


def notify(text: str, is_alert: bool = False):
    """
    Public helper used by briefing.py and intelligence/notifier.py
    to push messages to the owner's Telegram chat.
    """
    if not TELEGRAM_ENABLED or not ALLOWED_CHAT_ID:
        print("[TELEGRAM] notify() called but bot is not configured.")
        return
    
    prefix = "🚨 " if is_alert else "📢 "
    max_length = 4000 - len(prefix) - 10
    
    # Split long messages
    if len(text) > max_length:
        chunks = [text[i:i+max_length] for i in range(0, len(text), max_length)]
        for i, chunk in enumerate(chunks):
            tg_send(ALLOWED_CHAT_ID, f"{prefix}{chunk}")
            time.sleep(0.5)  # Avoid flooding
    else:
        tg_send(ALLOWED_CHAT_ID, f"{prefix}{text}")


# ─────────────────────────────────────────────
# SAFE UPDATE PARSER
# ─────────────────────────────────────────────

def extract_chat_id(update: Dict) -> Optional[int]:
    """Safely extract chat ID from update"""
    try:
        msg = update.get("message")
        if not msg:
            return None
        chat = msg.get("chat")
        if not chat:
            return None
        return chat.get("id")
    except Exception:
        return None


def extract_message_text(update: Dict) -> Tuple[Optional[str], Optional[int]]:
    """Extract text and reply-to message ID from update"""
    try:
        msg = update.get("message", {})
        text = msg.get("text")
        reply_to = msg.get("reply_to_message", {}).get("message_id")
        return text, reply_to
    except Exception:
        return None, None


# ─────────────────────────────────────────────
# SAFE STRING HELPERS
# ─────────────────────────────────────────────

def safe_str(x: Optional[str]) -> str:
    return (x or "").strip()


def safe_int(x: Optional[str]) -> Optional[int]:
    try:
        return int(safe_str(x))
    except (ValueError, TypeError):
        return None


# ─────────────────────────────────────────────
# MESSAGE BUILDER
# ─────────────────────────────────────────────

def build_messages(system_prompt: str, history: List[Tuple[str, str, str]], 
                   user_text: str, max_history: int = 5) -> List[Dict[str, str]]:
    """Build conversation messages for Groq API"""
    messages: List[Dict[str, str]] = [
        {"role": "system", "content": system_prompt}
    ]
    
    # Add conversation history (last N turns)
    for role, content, _ in history[-max_history*2:]:  # *2 because each turn has user+assistant
        if role in ("user", "assistant"):
            messages.append({
                "role": role,
                "content": (content or "")[:500]  # Truncate long history
            })
    
    messages.append({"role": "user", "content": user_text})
    return messages


# ─────────────────────────────────────────────
# CHAT ENGINE
# ─────────────────────────────────────────────

def _handle_chat(chat_id: int, text: str, reply_to: Optional[int] = None):
    """Handle regular chat messages (non-commands)"""
    text = safe_str(text)
    if not text:
        return

    if not client:
        tg_send(chat_id, "❌ Missing Groq API key. Please contact administrator.")
        return

    # Check rate limit
    if not rate_limit(chat_id):
        tg_send(chat_id, "⏳ Rate limit exceeded. Please wait a moment before sending more messages.")
        return

    # Check cache
    cached = _get_cache(text)
    if cached:
        tg_send(chat_id, cached, reply_to_message_id=reply_to)
        return

    # Send typing indicator
    tg_send_typing(chat_id)

    try:
        # Get conversation history
        history = get_conversation_history(limit=10)
        
        # Build system prompt with context
        system_prompt = build_system_prompt(query=text)
        
        # Build messages
        messages = build_messages(system_prompt, history, text)

        # Use the primary model (same quality as web chat)
        model = GROQ_MODEL_PRIMARY or "llama-3.3-70b-versatile"

        # Call Groq API with timeout
        response = client.chat.completions.create(
            model=model,
            messages=messages,  # type: ignore
            max_tokens=500,
            temperature=0.4,
            timeout=30,
        )

        reply = (response.choices[0].message.content or "").strip()

        if not reply:
            reply = "I couldn't generate a response. Please try again."

        # Cache and save
        _set_cache(text, reply)
        save_conversation("user", text[:500])
        save_conversation("assistant", reply[:500])
        
        # Send response
        tg_send(chat_id, reply, reply_to_message_id=reply_to)

    except requests.Timeout:
        tg_send(chat_id, "⏰ Request timed out. Please try again in a moment.", reply_to_message_id=reply_to)
    except Exception as e:
        error_msg = f"❌ ORA error: {str(e)[:100]}"
        tg_send(chat_id, error_msg, reply_to_message_id=reply_to)
        print(f"[CHAT ERROR] {traceback.format_exc()}")


# ─────────────────────────────────────────────
# COMMAND HANDLERS
# ─────────────────────────────────────────────

def _cmd_tasks(chat_id: int, reply_to: Optional[int] = None):
    """Show pending tasks"""
    try:
        from database import get_tasks
        tasks = get_tasks("pending")
        
        if not tasks:
            tg_send(chat_id, "📋 No pending tasks. Great job! 🎉", reply_to_message_id=reply_to)
            return
        
        # Format tasks nicely
        lines = [f"📋 **Pending Tasks** ({len(tasks)})"]
        for t in tasks[:10]:  # Limit to 10 tasks
            task_id, title, priority, status, due_date = t[:5]
            
            # Priority emoji
            priority_emoji = {
                "high": "🔴",
                "medium": "🟡",
                "low": "🟢"
            }.get(priority, "⚪")
            
            # Due date string
            due_str = f" (due {due_date[:10]})" if due_date else ""
            
            lines.append(f"{priority_emoji} *{title[:60]}* — #{task_id}{due_str}")
        
        if len(tasks) > 10:
            lines.append(f"\n... and {len(tasks) - 10} more tasks")
        
        tg_send(chat_id, "\n".join(lines), parse_mode="Markdown", reply_to_message_id=reply_to)
        
    except Exception as e:
        tg_send(chat_id, f"❌ Error fetching tasks: {e}", reply_to_message_id=reply_to)


def _cmd_goals(chat_id: int, reply_to: Optional[int] = None):
    """Show active goals"""
    try:
        from intelligence.goals_engine import get_goals
        goals = get_goals("active")
        
        if not goals:
            tg_send(chat_id, "🎯 No active goals. Set some goals to track your progress!", reply_to_message_id=reply_to)
            return
        
        lines = [f"🎯 **Active Goals** ({len(goals)})"]
        for g in goals[:7]:
            goal_text = g.get('goal', 'Untitled')[:60]
            progress = g.get('progress', 0)
            due = g.get('due_at')
            
            # Progress bar
            bar_length = 10
            filled = int(bar_length * progress / 100)
            bar = "█" * filled + "░" * (bar_length - filled)
            
            due_str = f" — due {due[:10]}" if due else ""
            lines.append(f"• {goal_text}\n  `{bar}` {progress}%{due_str}")
        
        tg_send(chat_id, "\n\n".join(lines), parse_mode="Markdown", reply_to_message_id=reply_to)
        
    except Exception as e:
        tg_send(chat_id, f"❌ Error fetching goals: {e}", reply_to_message_id=reply_to)


def _cmd_mpesa(chat_id: int, reply_to: Optional[int] = None):
    """Show M-Pesa spending"""
    try:
        from mpesa_engine import get_today_spend, get_average_daily_spend
        
        today = get_today_spend()
        avg = get_average_daily_spend()
        
        total = today.get("total", 0) if isinstance(today, dict) else 0
        txns = today.get("transactions", 0) if isinstance(today, dict) else 0
        
        # Determine trend emoji
        if total > avg * 1.3:
            trend = "📈 (above avg)"
        elif total < avg * 0.7:
            trend = "📉 (below avg)"
        else:
            trend = "📊 (normal)"
        
        msg = (
            f"💳 **M-Pesa Summary**\n\n"
            f"**Today:**\n"
            f"  • Spent: KES {total:,.0f} ({txns} transactions)\n"
            f"  • Daily avg: KES {avg:,.0f} {trend}"
        )
        
        tg_send(chat_id, msg, parse_mode="Markdown", reply_to_message_id=reply_to)
        
    except Exception as e:
        tg_send(chat_id, f"❌ Error fetching M-Pesa data: {e}", reply_to_message_id=reply_to)


def _cmd_brief(chat_id: int, reply_to: Optional[int] = None):
    """Generate and send morning briefing"""
    tg_send_typing(chat_id)
    try:
        from briefing import generate_briefing
        briefing = generate_briefing()
        
        # Split long briefing into multiple messages if needed
        if len(briefing) > 4000:
            chunks = [briefing[i:i+4000] for i in range(0, len(briefing), 4000)]
            for i, chunk in enumerate(chunks):
                tg_send(chat_id, chunk, parse_mode="Markdown", 
                       reply_to_message_id=reply_to if i == 0 else None)
                time.sleep(0.5)
        else:
            tg_send(chat_id, briefing, parse_mode="Markdown", reply_to_message_id=reply_to)
            
    except Exception as e:
        tg_send(chat_id, f"❌ Error generating briefing: {e}", reply_to_message_id=reply_to)


def _cmd_done(chat_id: int, arg: str, reply_to: Optional[int] = None):
    """Mark a task as complete"""
    task_id = safe_int(arg)
    
    if task_id is None:
        tg_send(
            chat_id,
            "⚠️ Usage: `/done <task_id>`\n\nExample: `/done 3`\n\nUse `/tasks` to see task IDs.",
            parse_mode="Markdown",
            reply_to_message_id=reply_to
        )
        return
    
    try:
        from database import complete_task
        
        # Verify task exists by trying to get it from tasks list
        from database import get_tasks
        tasks = get_tasks("all")
        task_exists = any(t[0] == task_id for t in tasks)
        
        if not task_exists:
            tg_send(chat_id, f"❌ Task #{task_id} not found.", reply_to_message_id=reply_to)
            return
        
        complete_task(task_id)
        tg_send(chat_id, f"✅ Task #{task_id} marked as complete! Great work! 🎉", 
                reply_to_message_id=reply_to)
        
        # Optionally suggest next task
        pending = get_tasks("pending")
        if pending:
            next_task = pending[0]
            tg_send(chat_id, f"💡 Next task: #{next_task[0]} - {next_task[1][:50]}", 
                    reply_to_message_id=reply_to)
        
    except Exception as e:
        tg_send(chat_id, f"❌ Failed to complete task #{task_id}: {e}", 
                reply_to_message_id=reply_to)


def _cmd_help(chat_id: int, reply_to: Optional[int] = None):
    """Show help message"""
    help_text = (
        "🤖 **ORA Bot Commands**\n\n"
        "**Basic Commands:**\n"
        "/start — Wake ORA up\n"
        "/ping — Check if bot is alive\n"
        "/help — Show this help message\n\n"
        
        "**Task Management:**\n"
        "/tasks — List pending tasks\n"
        "/done <id> — Mark task as complete\n\n"
        
        "**Goals & Progress:**\n"
        "/goals — Show active goals\n"
        "/brief — Get full status briefing\n\n"
        
        "**Finance:**\n"
        "/mpesa — Today's M-Pesa spending\n\n"
        
        "**Chat:**\n"
        "Just type any message to chat with ORA!\n"
        "Reply to a message to continue a conversation."
    )
    tg_send(chat_id, help_text, parse_mode="Markdown", reply_to_message_id=reply_to)


def _cmd_stats(chat_id: int, reply_to: Optional[int] = None):
    """Show bot statistics"""
    try:
        # Get conversation count from database
        conv_count = 0
        try:
            from database import get_conversation_history
            conv_history = get_conversation_history(limit=10000)
            conv_count = len(conv_history) // 2  # Each conversation has user+assistant
        except Exception:
            conv_count = 0
        
        # Get task count
        task_count = 0
        try:
            from database import get_tasks
            all_tasks = get_tasks("all")
            task_count = len(all_tasks)
        except Exception:
            task_count = 0
        
        cache_size = len(_CACHE)
        
        stats_text = (
            f"📊 **ORA Statistics**\n\n"
            f"• Conversations: {conv_count}\n"
            f"• Tasks: {task_count}\n"
            f"• Cache entries: {cache_size}\n"
            f"• Uptime: {_get_uptime()}\n"
            f"• Rate limit: {RATE_LIMIT_MAX} msgs/{RATE_LIMIT_WINDOW}s"
        )
        tg_send(chat_id, stats_text, parse_mode="Markdown", reply_to_message_id=reply_to)
        
    except Exception as e:
        tg_send(chat_id, f"❌ Error fetching stats: {e}", reply_to_message_id=reply_to)


# ─────────────────────────────────────────────
# UTILITY FUNCTIONS
# ─────────────────────────────────────────────

_start_time = time.time()

def _get_uptime() -> str:
    """Get bot uptime as human-readable string"""
    uptime = int(time.time() - _start_time)
    hours = uptime // 3600
    minutes = (uptime % 3600) // 60
    seconds = uptime % 60
    
    if hours > 0:
        return f"{hours}h {minutes}m"
    elif minutes > 0:
        return f"{minutes}m {seconds}s"
    else:
        return f"{seconds}s"


# ─────────────────────────────────────────────
# MESSAGE ROUTER
# ─────────────────────────────────────────────

def handle_message(chat_id: int, text: str = "", reply_to: Optional[int] = None, voice=None):
    """Route incoming messages to appropriate handlers"""
    # Check if chat is allowed
    if ALLOWED_CHAT_ID and chat_id != ALLOWED_CHAT_ID:
        print(f"[TELEGRAM] Unauthorized chat ID: {chat_id}")
        return

    text = safe_str(text)
    lower = text.lower()

    # Voice message handling
    if voice:
        tg_send(chat_id, "🎤 Voice messages aren't supported yet. Please type your message.", 
                reply_to_message_id=reply_to)
        return

    # Command routing
    if lower.startswith("/start"):
        tg_send(chat_id, "🤖 ORA online! Type /help to see available commands.", 
                reply_to_message_id=reply_to)

    elif lower.startswith("/ping"):
        tg_send(chat_id, "🏓 pong!", reply_to_message_id=reply_to)

    elif lower.startswith("/help"):
        _cmd_help(chat_id, reply_to)

    elif lower.startswith("/tasks"):
        _cmd_tasks(chat_id, reply_to)

    elif lower.startswith("/goals"):
        _cmd_goals(chat_id, reply_to)

    elif lower.startswith("/mpesa"):
        _cmd_mpesa(chat_id, reply_to)

    elif lower.startswith("/brief"):
        _cmd_brief(chat_id, reply_to)

    elif lower.startswith("/done"):
        _cmd_done(chat_id, text[5:], reply_to)

    elif lower.startswith("/stats"):
        _cmd_stats(chat_id, reply_to)

    else:
        # Regular chat message
        if client:
            _handle_chat(chat_id, text, reply_to)
        else:
            tg_send(chat_id, "❌ Missing Groq API key. Please contact administrator.", 
                    reply_to_message_id=reply_to)


# ─────────────────────────────────────────────
# MAIN LOOP
# ─────────────────────────────────────────────

def run_telegram_bot():
    """Main bot polling loop with exponential backoff"""
    print("[TELEGRAM] Starting bot with safe polling loop")
    
    offset = None
    empty_cycles = 0
    consecutive_errors = 0
    
    while True:
        try:
            # Exponential backoff on consecutive errors
            if consecutive_errors > 5:
                sleep_time = min(30, 2 ** (consecutive_errors - 5))
                print(f"[TELEGRAM] Too many errors, backing off for {sleep_time}s")
                time.sleep(sleep_time)
            
            # Get updates
            updates = tg_get_updates(offset, timeout=30)
            
            if not updates:
                empty_cycles += 1
                # Dynamic sleep based on activity
                sleep_time = min(5, 1 + empty_cycles * 0.2)
                time.sleep(sleep_time)
                consecutive_errors = 0  # Reset error counter on successful poll
                continue
            
            empty_cycles = 0
            consecutive_errors = 0
            
            # Process updates
            for update in updates:
                offset = update.get("update_id", 0) + 1
                
                chat_id = extract_chat_id(update)
                if not chat_id:
                    continue
                
                msg = update.get("message", {})
                text, reply_to = extract_message_text(update)
                
                handle_message(
                    chat_id,
                    text=text or "",
                    reply_to=reply_to,
                    voice=msg.get("voice"),
                )
                
                # Small delay between processing messages
                time.sleep(0.1)
                
        except KeyboardInterrupt:
            print("[TELEGRAM] Shutting down...")
            break
        except Exception as e:
            print(f"[LOOP ERROR] {e}")
            traceback.print_exc()
            consecutive_errors += 1
            time.sleep(3)


if __name__ == "__main__":
    run_telegram_bot()