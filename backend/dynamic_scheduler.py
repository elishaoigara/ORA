"""
ORA Dynamic Scheduler — SQLite-Backed Job Registry
===================================================
Inspired by Claude Code's ScheduleCronTool.

RENDER FREE TIER NOTE:
  ORA already has ora_scheduler.py which runs jobs via APScheduler inside
  the FastAPI lifespan. That is the single source of scheduling truth.
  This module does NOT run its own background loop — that would double-fire
  every job (github_scan, weather_refresh, etc.) and waste Render's limited CPU.

What this module DOES provide:
  - SQLite-backed job registry (persists job metadata across restarts)
  - Per-job execution history (success/fail/duration for each run)
  - Enable/disable jobs at runtime via API
  - Manual "run now" trigger for any job
  - `record_run()` hook so ora_scheduler can log into this table

This means:
  - ora_scheduler handles timing (APScheduler, already Render-safe)
  - dynamic_scheduler handles observability + control

Usage from ora_scheduler jobs:
    from dynamic_scheduler import scheduler
    scheduler.record_run("github_sync", status="ok", duration_ms=1200)

Usage from API:
    GET  /api/scheduler/jobs          → list all jobs + history
    POST /api/scheduler/jobs/{name}/run  → trigger manually
    POST /api/scheduler/jobs/{name}/disable → pause a job
"""

from __future__ import annotations

import json
import threading
import traceback
from datetime import datetime
from typing import Any, Optional

from database import get_conn, close_conn


# ─── Schema ───────────────────────────────────────────────────────────────────

def init_scheduler_tables() -> None:
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scheduled_jobs (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            name             TEXT UNIQUE NOT NULL,
            description      TEXT DEFAULT '',
            tool_name        TEXT NOT NULL,
            interval_seconds INTEGER NOT NULL DEFAULT 3600,
            enabled          INTEGER DEFAULT 1,
            last_run_at      TEXT DEFAULT NULL,
            run_count        INTEGER DEFAULT 0,
            fail_count       INTEGER DEFAULT 0,
            created_at       TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scheduled_job_runs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            job_name    TEXT NOT NULL,
            status      TEXT NOT NULL,
            result_json TEXT,
            error       TEXT,
            duration_ms INTEGER,
            ran_at      TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_job_runs_name
        ON scheduled_job_runs(job_name, ran_at DESC)
    """)
    conn.commit()
    close_conn()
    print("[SCHEDULER] Tables ready")


# ─── Default job registry entries ────────────────────────────────────────────
# These mirror the jobs already defined in api.py's lifespan/ora_scheduler.
# They exist here ONLY to seed the metadata table — actual scheduling is
# done by APScheduler in ora_scheduler.py, not by this module.

_DEFAULT_JOBS = [
    {"name": "agent_loop",       "description": "Core agent context/decision loop (every 10min)",   "tool_name": "agent_cycle",      "interval_seconds": 600},
    {"name": "morning_preds",    "description": "Morning predictions at 07:00",                      "tool_name": "run_predictions",  "interval_seconds": 86400},
    {"name": "evening_preds",    "description": "Evening predictions at 18:00",                      "tool_name": "run_predictions",  "interval_seconds": 86400},
    {"name": "daily_patterns",   "description": "Pattern analysis at 02:30",                         "tool_name": "pattern_analysis", "interval_seconds": 86400},
    {"name": "weekly_goals",     "description": "Goal check-in at 08:30",                            "tool_name": "goal_checkin",     "interval_seconds": 86400},
    {"name": "daily_brief",      "description": "Daily briefing at 07:00",                           "tool_name": "daily_brief",      "interval_seconds": 86400},
    {"name": "proactive_checks", "description": "Proactive alerts (every 15min)",                    "tool_name": "proactive",        "interval_seconds": 900},
    {"name": "auto_notify",      "description": "Autonomous notifications (every 15min)",             "tool_name": "notify",           "interval_seconds": 900},
    {"name": "agent_bus",        "description": "Agent message bus processing (every 5min)",          "tool_name": "bus_process",      "interval_seconds": 300},
    {"name": "drive_sync",       "description": "Google Drive sync (every 30min)",                   "tool_name": "drive_sync",       "interval_seconds": 1800},
    {"name": "gmail_sync",       "description": "Gmail reply check (every 15min)",                   "tool_name": "gmail_sync",       "interval_seconds": 900},
    {"name": "rss_sync",         "description": "RSS feed sync (every 2h)",                          "tool_name": "rss_sync",         "interval_seconds": 7200},
    {"name": "github_sync",      "description": "GitHub activity sync (every 2h)",                   "tool_name": "github_sync",      "interval_seconds": 7200},
    {"name": "code_scan",        "description": "Full code repo scan (every 8h)",                    "tool_name": "code_scan",        "interval_seconds": 28800},
    {"name": "news_ingest",      "description": "News article ingest (every 3h)",                    "tool_name": "news_ingest",      "interval_seconds": 10800},
    {"name": "news_digest",      "description": "AI news digest (daily at 7am)",                     "tool_name": "news_digest",      "interval_seconds": 86400},
]


# ─── Scheduler ────────────────────────────────────────────────────────────────

class DynamicScheduler:
    """
    Job registry and history store for ORA's scheduler.
    NO background thread — scheduling is handled by APScheduler in ora_scheduler.py.
    This class provides: registration, enable/disable, history, run_now, record_run.
    """

    _instance: Optional["DynamicScheduler"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "DynamicScheduler":
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._ready = False
            return cls._instance

    def __init__(self):
        if self._ready:
            return
        init_scheduler_tables()
        self._seed_defaults()
        self._ready = True

    # ── Seed default jobs ─────────────────────────────────────────────────────

    def _seed_defaults(self) -> None:
        for job in _DEFAULT_JOBS:
            conn = get_conn()
            conn.execute(
                """INSERT OR IGNORE INTO scheduled_jobs
                   (name, description, tool_name, interval_seconds)
                   VALUES (?, ?, ?, ?)""",
                (job["name"], job.get("description", ""), job["tool_name"], job.get("interval_seconds", 3600)),
            )
            conn.commit()
            close_conn()

    # ── Job management ────────────────────────────────────────────────────────

    def add_job(self, name: str, tool_name: str, interval_seconds: int = 3600, description: str = "") -> None:
        conn = get_conn()
        conn.execute(
            """INSERT INTO scheduled_jobs (name, description, tool_name, interval_seconds, enabled)
               VALUES (?, ?, ?, ?, 1)
               ON CONFLICT(name) DO UPDATE SET
                   description=excluded.description,
                   tool_name=excluded.tool_name,
                   interval_seconds=excluded.interval_seconds,
                   enabled=1""",
            (name, description, tool_name, interval_seconds),
        )
        conn.commit()
        close_conn()

    def remove_job(self, name: str) -> None:
        conn = get_conn()
        conn.execute("DELETE FROM scheduled_jobs WHERE name=?", (name,))
        conn.commit()
        close_conn()

    def set_enabled(self, name: str, enabled: bool) -> None:
        conn = get_conn()
        conn.execute("UPDATE scheduled_jobs SET enabled=? WHERE name=?", (1 if enabled else 0, name))
        conn.commit()
        close_conn()

    def is_enabled(self, name: str) -> bool:
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT enabled FROM scheduled_jobs WHERE name=?", (name,))
        row = c.fetchone()
        close_conn()
        return bool(row[0]) if row else True  # default to enabled if not found

    def list_jobs(self) -> list[dict]:
        conn = get_conn()
        c = conn.cursor()
        c.execute("""
            SELECT name, description, tool_name, interval_seconds,
                   enabled, last_run_at, run_count, fail_count
            FROM scheduled_jobs ORDER BY name
        """)
        rows = c.fetchall()
        close_conn()
        return [
            {
                "name": r[0], "description": r[1], "tool_name": r[2],
                "interval_seconds": r[3], "enabled": bool(r[4]),
                "last_run_at": r[5], "run_count": r[6], "fail_count": r[7],
            }
            for r in rows
        ]

    def get_job_history(self, name: str, limit: int = 10) -> list[dict]:
        conn = get_conn()
        c = conn.cursor()
        c.execute(
            """SELECT status, error, duration_ms, ran_at
               FROM scheduled_job_runs WHERE job_name=?
               ORDER BY id DESC LIMIT ?""",
            (name, limit),
        )
        rows = c.fetchall()
        close_conn()
        return [{"status": r[0], "error": r[1], "duration_ms": r[2], "ran_at": r[3]} for r in rows]

    # ── Record a run (called by ora_scheduler after each job fires) ────────────

    def record_run(
        self,
        job_name: str,
        status: str = "ok",
        duration_ms: int = 0,
        error: str = "",
        result: Any = None,
    ) -> None:
        """
        Log a job execution. Call this from ora_scheduler job wrappers:

            from dynamic_scheduler import scheduler
            t0 = time.time()
            try:
                run_agent_cycle()
                scheduler.record_run("agent_loop", status="ok", duration_ms=int((time.time()-t0)*1000))
            except Exception as e:
                scheduler.record_run("agent_loop", status="error", error=str(e))
        """
        now = datetime.now().isoformat()
        result_json = ""
        try:
            result_json = json.dumps(result)[:1000] if result else ""
        except Exception:
            pass

        conn = get_conn()
        conn.execute(
            """INSERT INTO scheduled_job_runs (job_name, status, result_json, error, duration_ms, ran_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (job_name, status, result_json, error[:500], duration_ms, now),
        )
        if status == "ok":
            conn.execute(
                "UPDATE scheduled_jobs SET last_run_at=?, run_count=run_count+1 WHERE name=?",
                (now, job_name),
            )
        else:
            conn.execute(
                "UPDATE scheduled_jobs SET last_run_at=?, fail_count=fail_count+1 WHERE name=?",
                (now, job_name),
            )
        conn.commit()
        close_conn()

    # ── run_now: manually trigger any job ─────────────────────────────────────

    def run_now(self, name: str) -> dict:
        """
        Manually fire a job by name. Uses the same functions ora_scheduler calls.
        This is the implementation behind POST /api/scheduler/jobs/{name}/run.
        """
        import time as _time
        t0 = _time.time()

        _JOB_FNS = {
            "agent_loop":       ("agent",                     "run_agent_cycle"),
            "morning_preds":    ("intelligence.prediction_engine", "run_predictions"),
            "evening_preds":    ("intelligence.prediction_engine", "run_predictions"),
            "daily_patterns":   ("intelligence.pattern_engine",    "run_pattern_analysis"),
            "weekly_goals":     ("intelligence.goals_engine",      "run_goal_checkin"),
            "daily_brief":      ("intelligence.planner_engine",    "generate_daily_brief"),
            "proactive_checks": ("intelligence.proactive_engine",  "run_proactive_checks"),
            "auto_notify":      ("intelligence.notifier",          "run_autonomous_notifications"),
            "agent_bus":        ("agents.agent_bus",               "process_pending_messages"),
            "drive_sync":       ("connectors.drive",               "sync_drive"),
            "gmail_sync":       ("connectors.gmail",               "run_gmail_reply_checks"),
            "rss_sync":         ("connectors.rss",                 "sync_rss"),
            "github_sync":      ("connectors.github",              "get_github_summary"),
            "code_scan":        ("agents.code_agent",              "scan_all_repos"),
            "news_ingest":      ("agents.news_agent",              "ingest_latest_news"),
            "news_digest":      ("agents.news_agent",              "generate_daily_briefing"),
        }

        if name not in _JOB_FNS:
            return {"ok": False, "error": f"Job '{name}' not found"}

        module_path, fn_name = _JOB_FNS[name]
        try:
            import importlib
            mod = importlib.import_module(module_path)
            fn = getattr(mod, fn_name)
            fn()
            ms = int((_time.time() - t0) * 1000)
            self.record_run(name, status="ok", duration_ms=ms)
            return {"ok": True, "job": name, "duration_ms": ms}
        except Exception as e:
            ms = int((_time.time() - t0) * 1000)
            self.record_run(name, status="error", error=str(e), duration_ms=ms)
            traceback.print_exc()
            return {"ok": False, "job": name, "error": str(e)}

    def start(self) -> None:
        """No-op. Scheduling is handled by APScheduler in ora_scheduler.py."""
        print("[SCHEDULER] Registry ready (scheduling via APScheduler in ora_scheduler.py)")


# ─── Global singleton ─────────────────────────────────────────────────────────
scheduler = DynamicScheduler()