from collections import defaultdict
from datetime import datetime
from database import get_conversation_history
from memory.preferences import set_preference


def analyze_time_patterns():
    history = get_conversation_history(limit=200)
    if not history:
        return

    hours = defaultdict(int)

    for _, _, timestamp in history:
        try:
            dt = datetime.fromisoformat(timestamp)
            hours[dt.hour] += 1
        except:
            continue

    if not hours:
        return

    peak_hour = max(hours, key=hours.get)

    set_preference(
        category="behavior",
        key="active_hour",
        value=str(peak_hour),
        confidence=0.8
    )

    print(f"[Pattern] Active hour → {peak_hour}")


def detect_focus_topics():
    history = get_conversation_history(limit=100)
    keywords = defaultdict(int)

    for _, text, _ in history:
        for word in text.lower().split():
            if len(word) > 4:
                keywords[word] += 1

    top = sorted(keywords.items(), key=lambda x: x[1], reverse=True)[:5]

    for word, count in top:
        set_preference(
            category="interests",
            key=word,
            value=str(count),
            confidence=0.6
        )

    print(f"[Pattern] Topics → {top}")


def run_pattern_analysis():
    analyze_time_patterns()
    detect_focus_topics()
