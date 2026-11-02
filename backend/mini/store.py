"""Small single-owner store. Postgres is durable; SQLite is local development only.

Render Free gives one 0.1-CPU instance, so the store is tuned for that budget:

* Postgres connections are pooled. A fresh TLS connection to a hosted database
  costs more CPU and latency than the query itself, and the free instance pays it
  on every request otherwise.
* The serialized workspace is cached in memory for a few seconds. One request
  reads the workspace several times (session lookup, endpoint, snapshot); the
  cache turns that into a single database round trip. Every mutation refreshes
  the cache, so the owner never reads stale data.
* A tiny key/value table holds the WhatsApp bridge session. Render Free wipes the
  container filesystem on every sleep, so the linked-device credentials live in
  the database instead: the bridge reconnects on wake without a new QR pairing.
  Keeping it out of ``ora_mini_workspace`` means it never reaches a client
  snapshot, an export, or the read cache.
"""
import json
import os
import sqlite3
import threading
import time
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
    # Small on purpose: the backend runs one uvicorn worker for a single owner.
    POOL_SIZE = 4
    POOL_IDLE_SECONDS = 120.0
    READ_CACHE_SECONDS = 5.0
    # WhatsApp credential bundles are tens of kilobytes; refuse anything that would
    # bloat the row or a free Postgres instance.
    KV_MAX_BYTES = 512 * 1024

    def __init__(self, url=None, path=None):
        self.url = url if url is not None else os.getenv("DATABASE_URL", "")
        self.path = path or os.getenv("ORA_LOCAL_DB", "ora-mini.db")
        if not self.url and os.getenv("APP_ENV") == "production":
            raise RuntimeError("DATABASE_URL is required: Render Free cannot preserve SQLite")
        self._pool = []
        self._pool_lock = threading.Lock()
        self._cache = None  # (json text, monotonic stamp, revision)
        self._cache_lock = threading.Lock()
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

    @staticmethod
    def _close(conn):
        try:
            conn.close()
        except Exception:
            pass

    def _acquire(self):
        """Reuse an idle Postgres connection instead of paying a TLS handshake."""
        if not self.url:
            # SQLite connections are thread-bound; a fresh one is cheapest here.
            return self.connect()
        while True:
            with self._pool_lock:
                if not self._pool:
                    break
                conn, stamp = self._pool.pop()
            if not conn.closed and not conn.broken and time.monotonic() - stamp < self.POOL_IDLE_SECONDS:
                return conn
            self._close(conn)
        return self.connect()

    def _release(self, conn):
        if not self.url:
            self._close(conn)
            return
        try:
            if conn.closed or conn.broken:
                raise RuntimeError('connection is not reusable')
            conn.rollback()
            with self._pool_lock:
                if len(self._pool) < self.POOL_SIZE:
                    self._pool.append((conn, time.monotonic()))
                    return
        except Exception:
            pass
        self._close(conn)

    def _cached_text(self):
        with self._cache_lock:
            cached = self._cache
        if cached and time.monotonic() - cached[1] < self.READ_CACHE_SECONDS:
            return cached[0]
        return None

    def _remember(self, text, revision=None):
        with self._cache_lock:
            current = self._cache
            # Never let a slower reader replace a newer committed revision.
            if (current and revision is not None and current[2] is not None
                    and revision < current[2]):
                return
            self._cache = (text, time.monotonic(), revision)

    def close(self):
        """Release pooled connections; called from the app shutdown hook."""
        with self._cache_lock:
            self._cache = None
        with self._pool_lock:
            pool, self._pool = self._pool, []
        for conn, _ in pool:
            self._close(conn)

    def initialize(self):
        conn = self.connect()
        try:
            conn.execute("CREATE TABLE IF NOT EXISTS ora_mini_workspace (id INTEGER PRIMARY KEY, data TEXT NOT NULL)")
            conn.execute("CREATE TABLE IF NOT EXISTS ora_mini_receipts (id TEXT PRIMARY KEY, result TEXT NOT NULL, created_at TEXT NOT NULL)")
            conn.execute("CREATE TABLE IF NOT EXISTS ora_mini_kv (k TEXT PRIMARY KEY, v TEXT NOT NULL, updated_at TEXT NOT NULL)")
            placeholder = "%s" if self.url else "?"
            conn.execute(f"INSERT INTO ora_mini_workspace(id,data) VALUES (1,{placeholder}) ON CONFLICT(id) DO NOTHING", (json.dumps(initial()),))
            if self.url:
                conn.execute("ALTER TABLE ora_mini_workspace ENABLE ROW LEVEL SECURITY")
                conn.execute("ALTER TABLE ora_mini_receipts ENABLE ROW LEVEL SECURITY")
                conn.execute("ALTER TABLE ora_mini_kv ENABLE ROW LEVEL SECURITY")
            conn.commit()
        finally:
            self._close(conn)

    def kv_get(self, key):
        """Read one private value (never part of the workspace snapshot)."""
        placeholder = "%s" if self.url else "?"
        conn = self._acquire()
        try:
            row = conn.execute(f"SELECT v FROM ora_mini_kv WHERE k={placeholder}", (key,)).fetchone()
            return row[0] if row else None
        finally:
            self._release(conn)

    def kv_put(self, key, value):
        if not isinstance(value, str) or len(value.encode()) > self.KV_MAX_BYTES:
            raise ValueError("value exceeds the key/value size limit")
        placeholder = "%s" if self.url else "?"
        conn = self._acquire()
        try:
            conn.execute(
                f"INSERT INTO ora_mini_kv(k,v,updated_at) VALUES ({placeholder},{placeholder},{placeholder}) "
                "ON CONFLICT(k) DO UPDATE SET v=EXCLUDED.v, updated_at=EXCLUDED.updated_at",
                (key, value, now()),
            )
            conn.commit()
        finally:
            self._release(conn)

    def kv_delete(self, key):
        placeholder = "%s" if self.url else "?"
        conn = self._acquire()
        try:
            conn.execute(f"DELETE FROM ora_mini_kv WHERE k={placeholder}", (key,))
            conn.commit()
        finally:
            self._release(conn)

    @contextmanager
    def transaction(self):
        conn = self._acquire()
        try:
            if not self.url:
                conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT data FROM ora_mini_workspace WHERE id=1" + (" FOR UPDATE" if self.url else "")).fetchone()
            state = json.loads(row[0])
            state["events"] = [e for e in state["events"] if e.get("expires_at", "") > now()]
            yield state, conn
            state["revision"] += 1
            text = json.dumps(state)
            placeholder = "%s" if self.url else "?"
            conn.execute(f"UPDATE ora_mini_workspace SET data={placeholder} WHERE id=1", (text,))
            conn.commit()
            self._remember(text, state['revision'])
        except BaseException:
            try:
                conn.rollback()
            except Exception:
                pass
            raise
        finally:
            self._release(conn)

    def healthy(self):
        """Check the workspace row without loading personal data into a health probe."""
        conn = self._acquire()
        try:
            return conn.execute("SELECT 1 FROM ora_mini_workspace WHERE id=1").fetchone() is not None
        finally:
            self._release(conn)

    def read(self):
        text = self._cached_text()
        if text is not None:
            return json.loads(text)
        conn = self._acquire()
        try:
            text = conn.execute("SELECT data FROM ora_mini_workspace WHERE id=1").fetchone()[0]
        finally:
            self._release(conn)
        state = json.loads(text)
        self._remember(text, state.get('revision'))
        return state

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
