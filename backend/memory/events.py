import os
from datetime import datetime, timedelta
from database import get_conn, close_conn
from groq import Groq

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

def log_memory_event(event_type, summary, detail="", importance=5):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""INSERT INTO memory_events
                 (event_type, summary, detail, importance, timestamp)
                 VALUES (?, ?, ?, ?, ?)""",
              (event_type, summary, detail, importance, datetime.now().isoformat()))
    conn.commit()
    close_conn()

def get_recent_events(limit=20, event_type=None):
    conn = get_conn()
    c = conn.cursor()
    if event_type:
        c.execute("""SELECT event_type, summary, detail, importance, timestamp
                     FROM memory_events WHERE event_type=?
                     ORDER BY id DESC LIMIT ?""", (event_type, limit))
    else:
        c.execute("""SELECT event_type, summary, detail, importance, timestamp
                     FROM memory_events ORDER BY id DESC LIMIT ?""", (limit,))
    rows = c.fetchall()
    close_conn()
    return rows

def get_important_events(min_importance=7, limit=10):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""SELECT event_type, summary, detail, importance, timestamp
                 FROM memory_events WHERE importance >= ?
                 ORDER BY importance DESC, id DESC LIMIT ?""",
              (min_importance, limit))
    rows = c.fetchall()
    close_conn()
    return rows

def summarize_old_events(days_old=7, max_events=50):
    if not GROQ_API_KEY:
        print("[MEMORY] GROQ_API_KEY not set. Skipping event summarization.")
        return

    client = Groq(api_key=GROQ_API_KEY)
    conn = get_conn()
    c = conn.cursor()

    # Get events older than `days_old`
    cutoff_date = (datetime.now() - timedelta(days=days_old)).isoformat()
    c.execute("SELECT id, event_type, summary, detail, timestamp FROM memory_events WHERE timestamp < ? ORDER BY timestamp ASC LIMIT ?", (cutoff_date, max_events))
    old_events = c.fetchall()

    if not old_events:
        close_conn()
        return

    # Group events by type for better summarization
    grouped_events = {}
    for event in old_events:
        event_type = event["event_type"]
        if event_type not in grouped_events:
            grouped_events[event_type] = []
        grouped_events[event_type].append(f"[{event["timestamp"]}] {event["summary"]}: {event["detail"]}")

    summaries = []
    for event_type, events_list in grouped_events.items():
        if not events_list:
            continue

        events_text = "\n".join(events_list)
        prompt = f"""
        Summarize the following {event_type} events concisely. Focus on key themes and outcomes.
        Events:
        {events_text}
        """
        try:
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
                temperature=0.3,
            )
            summary_text = response.choices[0].message.content.strip()
            summaries.append(f"Summary of old {event_type} events: {summary_text}")
        except Exception as e:
            print(f"[MEMORY ERROR] Summarization failed for {event_type}: {e}")

    if summaries:
        full_summary = "\n".join(summaries)
        log_memory_event("system_summary", "Periodic event summarization", full_summary, importance=2)
        print(f"[MEMORY] Summarized {len(old_events)} old events.")

        # Delete summarized events
        old_event_ids = [event["id"] for event in old_events]
        c.execute(f"DELETE FROM memory_events WHERE id IN ({','.join(['?' * len(old_event_ids)])})", old_event_ids)
        conn.commit()

    close_conn()
