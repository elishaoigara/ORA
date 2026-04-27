"""
ORA Pattern Engine — Upgraded
Domain-aware topic detection + behavioral learning.
Render-safe: pure Python, SQLite only.
"""

from collections import defaultdict
from datetime import datetime
from database import get_conversation_history
from memory.preferences import set_preference


_STOPWORDS = {
    "that", "this", "with", "have", "from", "they", "will", "been", "were",
    "what", "when", "where", "which", "there", "their", "then", "than",
    "about", "would", "could", "should", "your", "just", "also", "into",
    "more", "some", "such", "even", "most", "make", "like", "time", "very",
    "much", "know", "need", "want", "does", "dont", "cant", "well", "over",
    "only", "after", "before", "first", "other", "many", "here", "help",
    "tell", "show", "give", "find", "look", "sure", "okay", "yeah",
    "please", "thanks", "great", "good", "right", "think"
}

_DOMAIN_KEYWORDS: dict[str, set[str]] = {
    "coding":       {"code", "python", "javascript", "react", "api", "bug", "deploy",
                     "github", "commit", "function", "class", "error", "debug", "build"},
    "finance":      {"mpesa", "money", "spend", "cost", "payment", "ksh", "budget",
                     "transaction", "bank", "salary", "invoice", "revenue"},
    "productivity": {"task", "todo", "deadline", "schedule", "meeting", "calendar",
                     "goal", "plan", "priority", "focus", "reminder", "done"},
    "health":       {"sleep", "workout", "exercise", "diet", "water", "run", "gym",
                     "mental", "stress", "rest", "tired"},
    "learning":     {"learn", "study", "course", "book", "research", "read", "practice",
                     "skill", "improve", "understand", "youtube"},
}


def analyze_time_patterns() -> None:
    history = get_conversation_history(limit=200)
    if not history:
        return

    hours: dict[int, int] = {}
    days: dict[str, int] = {}

    for _, _, timestamp in history:
        try:
            dt = datetime.fromisoformat(timestamp)
            hours[dt.hour] = hours.get(dt.hour, 0) + 1
            day = dt.strftime("%A")
            days[day] = days.get(day, 0) + 1
        except Exception:
            continue

    if not hours:
        return

    peak_hour: int = max(hours, key=lambda k: hours[k])
    peak_day: str | None = max(days, key=lambda k: days[k]) if days else None

    set_preference("behavior", "active_hour", str(peak_hour), confidence=0.8)
    if peak_day:
        set_preference("behavior", "active_day", peak_day, confidence=0.7)

    print(f"[Pattern] Active: hour={peak_hour}, day={peak_day}")


def detect_focus_topics() -> None:
    history = get_conversation_history(limit=150)
    if not history:
        return

    domain_scores: dict[str, int] = {d: 0 for d in _DOMAIN_KEYWORDS}
    word_counts: dict[str, int] = {}

    for _, text, _ in history:
        words = set(text.lower().split())
        for domain, keywords in _DOMAIN_KEYWORDS.items():
            domain_scores[domain] = domain_scores.get(domain, 0) + len(words & keywords)
        for word in words:
            if len(word) > 5 and word not in _STOPWORDS and word.isalpha():
                word_counts[word] = word_counts.get(word, 0) + 1

    for domain, score in sorted(domain_scores.items(), key=lambda x: x[1], reverse=True):
        if score > 0:
            set_preference("interests", f"domain_{domain}", str(score), confidence=0.7)

    top_words = sorted(word_counts.items(), key=lambda x: x[1], reverse=True)[:8]
    for word, count in top_words:
        set_preference("interests", f"keyword_{word}", str(count), confidence=0.5)

    if domain_scores:
        top_domain: str = max(domain_scores, key=lambda k: domain_scores[k])
        print(f"[Pattern] Top domain: {top_domain}, words: {[w for w, _ in top_words[:3]]}")


def analyze_response_length_preference() -> None:
    history = get_conversation_history(limit=50)
    if not history:
        return

    user_msgs = [content for role, content, _ in history if role == "user"]
    if not user_msgs:
        return

    avg_len = sum(len(m.split()) for m in user_msgs) / len(user_msgs)
    pref = "brief" if avg_len < 8 else "concise" if avg_len < 20 else "detailed"
    set_preference("communication", "preferred_length", pref, confidence=0.6)
    print(f"[Pattern] Length pref: {pref} (avg: {avg_len:.1f} words)")


def run_pattern_analysis() -> None:
    try:
        analyze_time_patterns()
    except Exception as e:
        print(f"[Pattern] time_patterns failed: {e}")
    try:
        detect_focus_topics()
    except Exception as e:
        print(f"[Pattern] focus_topics failed: {e}")
    try:
        analyze_response_length_preference()
    except Exception as e:
        print(f"[Pattern] response_length failed: {e}")