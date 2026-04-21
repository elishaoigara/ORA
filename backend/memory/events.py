from datetime import datetime
from database import get_conn

def log_memory_event(event_type, summary, detail="", importance=5):
    conn = get_conn()
    c = conn.cursor()
    c.execute('''INSERT INTO memory_events
                 (event_type, summary, detail, importance, timestamp)
                 VALUES (?, ?, ?, ?, ?)''',
              (event_type, summary, detail, importance, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_recent_events(limit=20, event_type=None):
    conn = get_conn()
    c = conn.cursor()
    if event_type:
        c.execute('''SELECT event_type, summary, detail, importance, timestamp
                     FROM memory_events WHERE event_type=?
                     ORDER BY id DESC LIMIT ?''', (event_type, limit))
    else:
        c.execute('''SELECT event_type, summary, detail, importance, timestamp
                     FROM memory_events ORDER BY id DESC LIMIT ?''', (limit,))
    rows = c.fetchall()
    conn.close()
    return rows

def get_important_events(min_importance=7, limit=10):
    conn = get_conn()
    c = conn.cursor()
    c.execute('''SELECT event_type, summary, detail, importance, timestamp
                 FROM memory_events WHERE importance >= ?
                 ORDER BY importance DESC, id DESC LIMIT ?''',
              (min_importance, limit))
    rows = c.fetchall()
    conn.close()
    return rows