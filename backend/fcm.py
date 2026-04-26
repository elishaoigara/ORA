"""
ORA FCM — Firebase Cloud Messaging channel
Render free-tier safe:
  - Uses Expo Push API (plain HTTPS) — no Firebase Admin SDK, no extra RAM
  - Token persistence via existing SQLite DB
  - Graceful no-op when env vars are absent
"""

from __future__ import annotations

import os
import traceback
from typing import Optional

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"


# ── Token storage (SQLite — uses existing DB) ─────────────────

def _get_db():
    from config import DB_PATH
    import sqlite3
    return sqlite3.connect(DB_PATH)


def init_fcm_table() -> None:
    try:
        con = _get_db()
        con.execute("""
            CREATE TABLE IF NOT EXISTS push_tokens (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                token       TEXT UNIQUE NOT NULL,
                platform    TEXT DEFAULT 'expo',
                created_at  TEXT DEFAULT (datetime('now')),
                last_seen   TEXT DEFAULT (datetime('now'))
            )
        """)
        con.commit()
        con.close()
        print("[FCM] push_tokens table ready")
    except Exception:
        print("[FCM] init_fcm_table error")
        print(traceback.format_exc())


def save_token(token: str, platform: str = "expo") -> None:
    try:
        con = _get_db()
        con.execute("""
            INSERT INTO push_tokens (token, platform, last_seen)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(token) DO UPDATE SET
                last_seen = datetime('now'),
                platform  = excluded.platform
        """, (token, platform))
        con.commit()
        con.close()
    except Exception:
        print("[FCM] save_token error:", traceback.format_exc())


def get_tokens() -> list[str]:
    try:
        con = _get_db()
        rows = con.execute("SELECT token FROM push_tokens").fetchall()
        con.close()
        return [r[0] for r in rows]
    except Exception:
        return []


def remove_token(token: str) -> None:
    try:
        con = _get_db()
        con.execute("DELETE FROM push_tokens WHERE token = ?", (token,))
        con.commit()
        con.close()
    except Exception:
        pass


# ── Send via Expo Push API ────────────────────────────────────

def _send_expo_batch(tokens: list[str], title: str, body: str, data: dict) -> list[str]:
    """Send to Expo Push API. Returns list of invalid tokens to remove."""
    import requests as _req

    to_remove: list[str] = []

    for i in range(0, len(tokens), 100):
        chunk = tokens[i : i + 100]
        messages = [
            {
                "to":       tok,
                "title":    title,
                "body":     body,
                "data":     data,
                "sound":    "default",
                "priority": "high",
            }
            for tok in chunk
        ]
        try:
            resp = _req.post(
                EXPO_PUSH_URL,
                json=messages,
                headers={"Accept": "application/json", "Accept-encoding": "gzip, deflate"},
                timeout=10,
            )
            results = resp.json().get("data", [])
            for tok, result in zip(chunk, results):
                if result.get("status") == "error":
                    err = result.get("details", {}).get("error", "")
                    if err in ("DeviceNotRegistered", "InvalidCredentials"):
                        to_remove.append(tok)
                        print(f"[FCM] Invalid token removed: {tok[:20]}…")
        except Exception:
            print("[FCM] Expo batch error:", traceback.format_exc())

    return to_remove


def send_push(title: str, body: str, data: Optional[dict] = None, is_alert: bool = False) -> bool:
    tokens = get_tokens()
    if not tokens:
        return False

    if data is None:
        data = {}
    data["is_alert"] = is_alert

    invalid = _send_expo_batch(tokens, title, body, data)
    for tok in invalid:
        remove_token(tok)

    return True


def send_push_to_token(token: str, title: str, body: str, data: Optional[dict] = None) -> bool:
    invalid = _send_expo_batch([token], title, body, data or {})
    return token not in invalid