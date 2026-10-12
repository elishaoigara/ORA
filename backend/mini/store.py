"""Small single-owner store. Postgres is durable; SQLite is local development only."""
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone


def now():
    return datetime.now(timezone.utc).isoformat()


def initial():
    return {"revision": 0, "tasks": [], "messages": [], "memories": [], "actions": [],
            "events": [], "documents": [], "devices": [], "sessions": [], "pairing": [],
            "settings": {"name": "Elisha", "timezone": "Africa/Nairobi", "briefing_hour": 7,
                         "quiet_start": 22, "quiet_end": 7, "voice_rate": 1.0}}


class Store:
    def __init__(self, url=None, path=None):
        self.url = url if url is not None else os.getenv("DATABASE_URL", "")
        self.path = path or os.getenv("ORA_LOCAL_DB", "ora-mini.db")
        if not self.url and os.getenv("APP_ENV") == "production":
            raise RuntimeError("DATABASE_URL is required: Render Free cannot preserve SQLite")
        self.initialize()

    def connect(self):
        if self.url:
            import psycopg
            options = psycopg.conninfo.conninfo_to_dict(self.url)
            if options.get('sslmode') in ('disable', 'allow', 'prefer'):
                raise RuntimeError('Use sslmode=require or stronger for remote storage')
            options.setdefault('sslmode', 'require')
            return psycopg.connect(**options, connect_timeout=10, prepare_threshold=None)
        conn = sqlite3.connect(self.path, timeout=15)
        conn.execute("PRAGMA busy_timeout=15000")
        return conn

    def initialize(self):
        with self.connect() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS ora_mini_workspace (id INTEGER PRIMARY KEY, data TEXT NOT NULL)")
            conn.execute("CREATE TABLE IF NOT EXISTS ora_mini_receipts (id TEXT PRIMARY KEY, result TEXT NOT NULL, created_at TEXT NOT NULL)")
            placeholder = "%s" if self.url else "?"
            conn.execute(f"INSERT INTO ora_mini_workspace(id,data) VALUES (1,{placeholder}) ON CONFLICT(id) DO NOTHING", (json.dumps(initial()),))
            if self.url:
                conn.execute("ALTER TABLE ora_mini_workspace ENABLE ROW LEVEL SECURITY")
                conn.execute("ALTER TABLE ora_mini_receipts ENABLE ROW LEVEL SECURITY")
            conn.commit()
        conn.close()

    @contextmanager
    def transaction(self):
        conn = self.connect()
        try:
            if not self.url:
                conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT data FROM ora_mini_workspace WHERE id=1" + (" FOR UPDATE" if self.url else "")).fetchone()
            state = json.loads(row[0])
            state["events"] = [e for e in state["events"] if e.get("expires_at", "") > now()]
            yield state, conn
            state["revision"] += 1
            placeholder = "%s" if self.url else "?"
            conn.execute(f"UPDATE ora_mini_workspace SET data={placeholder} WHERE id=1", (json.dumps(state),))
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def healthy(self):
        """Check the workspace row without loading personal data into a health probe."""
        conn = self.connect()
        try:
            return conn.execute("SELECT 1 FROM ora_mini_workspace WHERE id=1").fetchone() is not None
        finally:
            conn.close()

    def read(self):
        conn = self.connect()
        try:
            return json.loads(conn.execute("SELECT data FROM ora_mini_workspace WHERE id=1").fetchone()[0])
        finally:
            conn.close()

    def mutate(self, fn, request_id=None):
        with self.transaction() as (state, conn):
            placeholder = "%s" if self.url else "?"
            if request_id:
                row = conn.execute(f"SELECT result FROM ora_mini_receipts WHERE id={placeholder}", (request_id,)).fetchone()
                if row:
                    return json.loads(row[0])
            result = fn(state)
            if request_id:
                conn.execute(f"INSERT INTO ora_mini_receipts(id,result,created_at) VALUES ({placeholder},{placeholder},{placeholder})", (request_id, json.dumps(result), now()))
            return result
