import sqlite3
from datetime import datetime
import threading

from config import DB_PATH  # single source of truth — set via ORA_DATA_DIR env var

# Thread-local storage for database connections
_thread_local = threading.local()


def get_conn():
    if not hasattr(_thread_local, "conn") or _thread_local.conn is None:
        _thread_local.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        # Do NOT set row_factory — keep rows as plain tuples so index access
        # works consistently everywhere (api.py uses row[0], row[1] etc.)
    return _thread_local.conn


def close_conn():
    if hasattr(_thread_local, "conn") and _thread_local.conn is not None:
        _thread_local.conn.close()
        _thread_local.conn = None


def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute("""CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source TEXT, data TEXT, timestamp TEXT)""")

    c.execute("""CREATE TABLE IF NOT EXISTS alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        rule_name TEXT, message TEXT, severity TEXT,
        timestamp TEXT, acknowledged INTEGER DEFAULT 0,
        feedback TEXT DEFAULT NULL)""")

    c.execute("""CREATE TABLE IF NOT EXISTS profile (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        key TEXT UNIQUE, value TEXT, updated_at TEXT)""")

    c.execute("""CREATE TABLE IF NOT EXISTS memory_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_type TEXT, summary TEXT, detail TEXT,
        importance INTEGER DEFAULT 5, timestamp TEXT)""")

    c.execute("""CREATE TABLE IF NOT EXISTS preferences (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        category TEXT, key TEXT, value TEXT,
        confidence REAL DEFAULT 1.0, updated_at TEXT)""")

    c.execute("""CREATE UNIQUE INDEX IF NOT EXISTS
        idx_preferences ON preferences(category, key)""")

    c.execute("""CREATE TABLE IF NOT EXISTS feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        interaction_id TEXT, ora_response TEXT,
        user_rating INTEGER, user_comment TEXT, timestamp TEXT)""")

    c.execute("""CREATE TABLE IF NOT EXISTS conversations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        role TEXT, content TEXT, timestamp TEXT)""")

    conn.commit()
    close_conn()


def init_tasks_table():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        status TEXT DEFAULT 'pending',
        priority TEXT DEFAULT 'medium',
        created_at TEXT,
        due_at TEXT DEFAULT NULL,
        completed_at TEXT DEFAULT NULL,
        goal_id INTEGER DEFAULT NULL)""")
    columns = {row[1] for row in c.execute("PRAGMA table_info(tasks)").fetchall()}
    if "goal_id" not in columns:
        c.execute("ALTER TABLE tasks ADD COLUMN goal_id INTEGER DEFAULT NULL")
    conn.commit()
    close_conn()


def log_event(source, data):
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT INTO events (source, data, timestamp) VALUES (?, ?, ?)",
              (source, data, datetime.now().isoformat()))
    conn.commit()
    close_conn()


def log_alert(rule_name, message, severity="medium"):
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT INTO alerts (rule_name, message, severity, timestamp) VALUES (?, ?, ?, ?)",
              (rule_name, message, severity, datetime.now().isoformat()))
    conn.commit()
    close_conn()


def get_recent_alerts(limit=10):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""SELECT id, rule_name, message, severity, timestamp, acknowledged
                 FROM alerts ORDER BY id DESC LIMIT ?""", (limit,))
    rows = c.fetchall()
    close_conn()
    return rows


def get_system_stats():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT data, timestamp FROM events WHERE source='system' ORDER BY id DESC LIMIT 1")
    row = c.fetchone()
    close_conn()
    return row


def acknowledge_alert(alert_id, feedback=None):
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE alerts SET acknowledged=1, feedback=? WHERE id=?", (feedback, alert_id))
    conn.commit()
    close_conn()


def save_conversation(role, content):
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT INTO conversations (role, content, timestamp) VALUES (?, ?, ?)",
              (role, content, datetime.now().isoformat()))
    conn.commit()
    close_conn()


def get_conversation_history(limit=20):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT role, content, timestamp FROM conversations ORDER BY id DESC LIMIT ?", (limit,))
    rows = c.fetchall()
    close_conn()
    return list(reversed(rows))


def add_task(title, priority="medium", due_at=None, goal_id=None):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""INSERT INTO tasks
                 (title, priority, created_at, due_at, goal_id)
                 VALUES (?, ?, ?, ?, ?)""",
              (title, priority, datetime.now().isoformat(), due_at, goal_id))
    conn.commit()
    task_id = c.lastrowid
    close_conn()
    return task_id


def get_tasks(status="pending"):
    conn = get_conn()
    c = conn.cursor()
    if status == "all":
        c.execute("SELECT id, title, priority, created_at, due_at, goal_id FROM tasks ORDER BY id DESC")
    else:
        c.execute("SELECT id, title, priority, created_at, due_at, goal_id FROM tasks WHERE status=? ORDER BY id DESC",
              (status,))
    rows = c.fetchall()
    close_conn()
    return rows


def complete_task(task_id):
    conn = get_conn()
    c = conn.cursor()
    row = c.execute("SELECT goal_id FROM tasks WHERE id=?", (task_id,)).fetchone()
    c.execute("UPDATE tasks SET status='done', completed_at=? WHERE id=?",
              (datetime.now().isoformat(), task_id))
    conn.commit()
    close_conn()
    return row[0] if row else None


def delete_task(task_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM tasks WHERE id=?", (task_id,))
    conn.commit()
    close_conn()