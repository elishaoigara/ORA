import uuid
from datetime import datetime
from database import get_conn, close_conn

def log_feedback(ora_response, user_rating, user_comment=""):
    conn = get_conn()
    c = conn.cursor()
    c.execute('''INSERT INTO feedback
                 (interaction_id, ora_response, user_rating, user_comment, timestamp)
                 VALUES (?, ?, ?, ?, ?)''',
              (str(uuid.uuid4()), ora_response, user_rating,
               user_comment, datetime.now().isoformat()))
    conn.commit()
    close_conn()

def get_average_rating():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT AVG(user_rating), COUNT(*) FROM feedback")
    row = c.fetchone()
    close_conn()
    return {"average": round(row[0] or 0, 2), "total": row[1]}

def get_low_rated(threshold=2, limit=10):
    conn = get_conn()
    c = conn.cursor()
    c.execute('''SELECT ora_response, user_rating, user_comment, timestamp
                 FROM feedback WHERE user_rating <= ?
                 ORDER BY id DESC LIMIT ?''', (threshold, limit))
    rows = c.fetchall()
    close_conn()
    return rows