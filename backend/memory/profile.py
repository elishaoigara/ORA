from datetime import datetime
from database import get_conn, close_conn


def set_profile(key, value):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """INSERT INTO profile (key, value, updated_at) VALUES (?, ?, ?)
           ON CONFLICT(key) DO UPDATE SET
           value=excluded.value, updated_at=excluded.updated_at""",
        (key, value, datetime.now().isoformat())
    )
    conn.commit()
    close_conn()  # FIX: use close_conn() not conn.close() — keeps thread-local pool consistent


def get_profile(key):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT value FROM profile WHERE key=?", (key,))
    row = c.fetchone()
    close_conn()
    return row[0] if row else None


def get_all_profile():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT key, value FROM profile")
    rows = c.fetchall()
    close_conn()
    return {row[0]: row[1] for row in rows}


def init_profile():
    defaults = {
        "name": "Elisha",
        "full_name": "Elisha Lambert Oigara",
        "role": "Software Engineer",
        "timezone": "Africa/Nairobi",
        "language": "English",
        "communication_style": "direct and concise",
        "goals": "build ORA, improve productivity, make better decisions",
        "wake_time": "07:00",
        "sleep_time": "23:00",
        "location": "Nairobi, Kenya",
    }
    for key, value in defaults.items():
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT value FROM profile WHERE key=?", (key,))
        existing = c.fetchone()
        close_conn()
        if not existing:
            set_profile(key, value)