"""
ORA Pattern Engine — Phase 2
Analyzes behavior patterns and detects spending anomalies.
Render free tier safe: pure SQLite/math, zero AI calls.
Runs on a daily cron via scheduler.
"""

from collections import defaultdict
from datetime import datetime, timedelta
from database import get_conversation_history, get_tasks
from memory.preferences import set_preference


# ── Behavior patterns ─────────────────────────────────────────
def analyze_time_patterns():
    """Find peak productivity hour from conversation timestamps."""
    history = get_conversation_history(limit=200)
    if not history:
        return

    hours = defaultdict(int)
    for _, _, timestamp in history:
        try:
            dt = datetime.fromisoformat(timestamp)
            hours[dt.hour] += 1
        except Exception:
            continue

    if not hours:
        return

    peak_hour = max(hours, key=hours.get)
    set_preference("behavior", "active_hour", str(peak_hour), confidence=0.8)
    print(f"[Pattern] Active hour → {peak_hour}:00")


def detect_focus_topics():
    """Find recurring topics from conversation history."""
    history = get_conversation_history(limit=100)
    if not history:
        return

    # Stop words (lightweight — no NLTK needed)
    STOP = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "shall", "can", "need", "dare", "ought",
        "used", "to", "of", "in", "for", "on", "with", "at", "by", "from",
        "as", "into", "through", "during", "above", "below", "between",
        "each", "all", "both", "few", "more", "most", "other", "some",
        "such", "no", "nor", "not", "only", "same", "so", "than", "too",
        "very", "i", "me", "my", "we", "our", "you", "your", "it", "its",
        "this", "that", "and", "or", "but", "if", "then", "what", "how",
        "when", "where", "who", "which", "just", "also", "like", "about",
    }

    keywords = defaultdict(int)
    for _, text, _ in history:
        for word in text.lower().split():
            clean = word.strip(".,!?;:\"'()[]")
            if len(clean) > 4 and clean not in STOP:
                keywords[clean] += 1

    top = sorted(keywords.items(), key=lambda x: x[1], reverse=True)[:5]
    for word, count in top:
        set_preference("interests", word, str(count), confidence=0.6)

    print(f"[Pattern] Top topics → {[w for w, _ in top]}")


def detect_task_delay_patterns():
    """
    Detect which task categories the user consistently delays.
    Stores as a preference for context injection.
    """
    try:
        done = get_tasks("done") if hasattr(get_tasks, "__call__") else []
        pending = get_tasks("pending")

        if not pending:
            return

        # Find tasks older than 3 days that are still pending
        now = datetime.now()
        old_pending = []
        for t in pending:
            try:
                created = datetime.fromisoformat(t[3])
                if (now - created).days > 3:
                    old_pending.append(t[1].lower())
            except Exception:
                continue

        if old_pending:
            # Find common word in delayed tasks
            word_counts = defaultdict(int)
            for title in old_pending:
                for word in title.split():
                    if len(word) > 3:
                        word_counts[word] += 1
            if word_counts:
                top_delay = max(word_counts, key=word_counts.get)
                set_preference("behavior", "delay_pattern", top_delay, confidence=0.7)
                print(f"[Pattern] Delay pattern → '{top_delay}'")

    except Exception as e:
        print(f"[Pattern] task_delay failed: {e}")


# ── Spend anomaly detection ───────────────────────────────────
def detect_spend_anomaly():
    """
    Compare today's spend to 7-day average.
    If > 2x average → fire Telegram alert.
    Zero AI calls — pure math.
    """
    try:
        from mpesa_engine import get_today_spend, get_average_daily_spend
        today = get_today_spend()
        avg = get_average_daily_spend()

        if today is None or avg is None or avg == 0:
            return

        ratio = today / avg

        if ratio >= 2.0:
            msg = (
                f"⚠️ *Spend Alert*\n"
                f"Today: KES {today:,.0f}\n"
                f"Your avg: KES {avg:,.0f}\n"
                f"You're at {ratio:.1f}x your normal spend."
            )
            try:
                from telegram_bot import notify
                notify(msg, is_alert=True)
            except Exception as e:
                print(f"[Pattern] spend alert notify failed: {e}")

        elif ratio >= 1.5:
            print(f"[Pattern] Spend elevated: {ratio:.1f}x avg — below alert threshold")

    except Exception as e:
        print(f"[Pattern] spend_anomaly failed: {e}")


# ── Main entry (called by scheduler daily) ───────────────────
def run_pattern_analysis():
    """Run all pattern checks. Lightweight — ~50ms total."""
    analyze_time_patterns()
    detect_focus_topics()
    detect_task_delay_patterns()
    detect_spend_anomaly()