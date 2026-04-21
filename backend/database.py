import sqlite3
from datetime import datetime

DB_PATH = "ora.db"

def get_conn():
    return sqlite3.connect(DB_PATH)

def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source TEXT, data TEXT, timestamp TEXT)''')

    c.execute('''CREATE TABLE IF NOT EXISTS alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        rule_name TEXT, message TEXT, severity TEXT,
        timestamp TEXT, acknowledged INTEGER DEFAULT 0,
        feedback TEXT DEFAULT NULL)''')

    c.execute('''CREATE TABLE IF NOT EXISTS profile (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        key TEXT UNIQUE, value TEXT, updated_at TEXT)''')

    c.execute('''CREATE TABLE IF NOT EXISTS memory_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_type TEXT, summary TEXT, detail TEXT,
        importance INTEGER DEFAULT 5, timestamp TEXT)''')

    c.execute('''CREATE TABLE IF NOT EXISTS preferences (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        category TEXT, key TEXT, value TEXT,
        confidence REAL DEFAULT 1.0, updated_at TEXT)''')

    c.execute('''CREATE UNIQUE INDEX IF NOT EXISTS
        idx_preferences ON preferences(category, key)''')

    c.execute('''CREATE TABLE IF NOT EXISTS feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        interaction_id TEXT, ora_response TEXT,
        user_rating INTEGER, user_comment TEXT, timestamp TEXT)''')

    c.execute('''CREATE TABLE IF NOT EXISTS conversations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        role TEXT, content TEXT, timestamp TEXT)''')

    conn.commit()
    conn.close()

def log_event(source, data):
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT INTO events (source, data, timestamp) VALUES (?, ?, ?)",
              (source, str(data), datetime.now().isoformat()))
    conn.commit()
    conn.close()

def log_alert(rule_name, message, severity="medium"):
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT INTO alerts (rule_name, message, severity, timestamp) VALUES (?, ?, ?, ?)",
              (rule_name, message, severity, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_recent_alerts(limit=10):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""SELECT id, rule_name, message, severity, timestamp, acknowledged
                 FROM alerts ORDER BY id DESC LIMIT ?""", (limit,))
    rows = c.fetchall()
    conn.close()
    return rows

def get_system_stats():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT data, timestamp FROM events WHERE source='system' ORDER BY id DESC LIMIT 1")
    row = c.fetchone()
    conn.close()
    return row

def acknowledge_alert(alert_id, feedback=None):
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE alerts SET acknowledged=1, feedback=? WHERE id=?", (feedback, alert_id))
    conn.commit()
    conn.close()

def save_conversation(role, content):
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT INTO conversations (role, content, timestamp) VALUES (?, ?, ?)",
              (role, content, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_conversation_history(limit=20):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT role, content FROM conversations ORDER BY id DESC LIMIT ?", (limit,))
    rows = c.fetchall()
    conn.close()
    return list(reversed(rows))
def init_tasks_table():
    conn = get_conn()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        status TEXT DEFAULT 'pending',
        priority TEXT DEFAULT 'medium',
        created_at TEXT,
        due_at TEXT DEFAULT NULL,
        completed_at TEXT DEFAULT NULL)''')
    conn.commit()
    conn.close()

def add_task(title, priority="medium", due_at=None):
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT INTO tasks (title, priority, created_at, due_at) VALUES (?, ?, ?, ?)",
              (title, priority, datetime.now().isoformat(), due_at))
    conn.commit()
    conn.close()

def get_tasks(status="pending"):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, title, priority, created_at, due_at FROM tasks WHERE status=? ORDER BY id DESC",
              (status,))
    rows = c.fetchall()
    conn.close()
    return rows

def complete_task(task_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE tasks SET status='done', completed_at=? WHERE id=?",
              (datetime.now().isoformat(), task_id))
    conn.commit()
    conn.close()

def delete_task(task_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM tasks WHERE id=?", (task_id,))
    conn.commit()
    conn.close()
