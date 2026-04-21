from datetime import datetime
from database import get_conn

def set_preference(category, key, value, confidence=1.0):
    conn = get_conn()
    c = conn.cursor()
    c.execute('''INSERT INTO preferences (category, key, value, confidence, updated_at)
                 VALUES (?, ?, ?, ?, ?)
                 ON CONFLICT(category, key) DO UPDATE SET
                 value=excluded.value, confidence=excluded.confidence,
                 updated_at=excluded.updated_at''',
              (category, key, value, confidence, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_preferences(category=None):
    conn = get_conn()
    c = conn.cursor()
    if category:
        c.execute("""SELECT category, key, value, confidence
                     FROM preferences WHERE category=?
                     ORDER BY confidence DESC""", (category,))
    else:
        c.execute("""SELECT category, key, value, confidence
                     FROM preferences ORDER BY confidence DESC""")
    rows = c.fetchall()
    conn.close()
    return rows

def get_preference(category, key):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT value FROM preferences WHERE category=? AND key=?", (category, key))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None