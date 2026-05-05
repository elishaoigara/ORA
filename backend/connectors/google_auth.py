"""
ORA Google Auth — OAuth 2.0 token manager.
Reads credentials from config.py (env vars).
"""

from __future__ import annotations

import json
import os
import time
from typing import Optional

import requests
from urllib.parse import quote
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

# Pull from config (which reads env vars)
try:
    from config import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI, DATA_DIR
    TOKEN_PATH = os.path.join(DATA_DIR, "google_token.json")
except ImportError:
    GOOGLE_CLIENT_ID     = os.getenv("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
    GOOGLE_REDIRECT_URI  = os.getenv("GOOGLE_REDIRECT_URI", "")
    TOKEN_PATH = os.path.join(
        os.getenv("ORA_DATA_DIR", "./data"),
        "google_token.json"
    )

# Aliases used internally
CLIENT_ID     = GOOGLE_CLIENT_ID
CLIENT_SECRET = GOOGLE_CLIENT_SECRET
REDIRECT_URI  = GOOGLE_REDIRECT_URI

SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",       # Phase 2: send smart replies
    "https://www.googleapis.com/auth/gmail.modify",     # Phase 2: mark as read after reply
    "https://www.googleapis.com/auth/drive.readonly",
]

AUTH_URL  = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"


def _load_token() -> Optional[dict]:
    """
    Load the stored OAuth token from disk.

    Handles corrupted token files gracefully:
    - Extra data / multiple JSON objects concatenated (the current production bug)
    - Truncated / partial writes
    - Completely invalid JSON

    If the file is corrupt it is removed so the next auth flow writes a clean one.
    """
    if not os.path.exists(TOKEN_PATH):
        return None
    try:
        with open(TOKEN_PATH, "r") as f:
            raw = f.read().strip()

        if not raw:
            return None

        # Primary parse attempt — valid single-object files succeed here
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass

        # FIX: Handle "Extra data" — file contains multiple JSON objects.
        # A common corruption mode is appending a new token dict to the file
        # instead of overwriting it, producing two back-to-back objects.
        # We extract and return only the LAST complete object so we always
        # have the freshest token.
        decoder = json.JSONDecoder()
        last_valid: Optional[dict] = None
        idx = 0
        while idx < len(raw):
            # Skip whitespace between objects
            while idx < len(raw) and raw[idx] in " \t\r\n":
                idx += 1
            if idx >= len(raw):
                break
            try:
                obj, end_idx = decoder.raw_decode(raw, idx)
                if isinstance(obj, dict):
                    last_valid = obj
                idx = end_idx
            except json.JSONDecodeError:
                break

        if last_valid is not None:
            print("[GOOGLE AUTH] Token file had extra data — repaired in memory. "
                  "It will be rewritten cleanly on next save.")
            # Overwrite the file now with just the last (freshest) object
            _save_token(last_valid)
            return last_valid

        # Unrecoverable — remove so re-auth creates a clean file
        print("[GOOGLE AUTH] Token file is unreadable — removing. "
              "Please re-authorize at /api/auth/google")
        try:
            os.remove(TOKEN_PATH)
        except OSError:
            pass
        return None

    except Exception as e:
        print(f"[GOOGLE AUTH] load error: {e}")
        return None


def _save_token(token: dict) -> None:
    try:
        os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
        # Write to a temp file then atomically rename to avoid partial writes
        tmp_path = TOKEN_PATH + ".tmp"
        with open(tmp_path, "w") as f:
            json.dump(token, f, indent=2)
        os.replace(tmp_path, TOKEN_PATH)
    except Exception as e:
        print(f"[GOOGLE AUTH] save error: {e}")


def get_auth_url() -> str:
    params = {
        "client_id":     CLIENT_ID,
        "redirect_uri":  REDIRECT_URI,
        "response_type": "code",
        "scope":         " ".join(SCOPES),
        "access_type":   "offline",
        "prompt":        "consent",
    }
    query = "&".join(f"{k}={quote(str(v), safe='')}" for k, v in params.items())
    return f"{AUTH_URL}?{query}"


def exchange_code(code: str) -> dict:
    resp = requests.post(TOKEN_URL, data={
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri":  REDIRECT_URI,
        "grant_type":    "authorization_code",
        "code":          code,
    }, timeout=15)
    resp.raise_for_status()
    token = resp.json()
    token["expires_at"] = time.time() + token.get("expires_in", 3600)
    _save_token(token)
    return token


def _refresh_token(token: dict) -> dict:
    refresh_token = token.get("refresh_token")
    if not refresh_token:
        raise ValueError("Missing refresh token")
    resp = requests.post(TOKEN_URL, data={
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type":    "refresh_token",
        "refresh_token": refresh_token,
    }, timeout=15)
    resp.raise_for_status()
    new_token = resp.json()
    new_token["refresh_token"] = refresh_token
    new_token["expires_at"] = time.time() + new_token.get("expires_in", 3600)
    _save_token(new_token)
    return new_token


def get_access_token() -> str:
    token = _load_token()
    if not token:
        raise ValueError("Not authorized — visit /api/auth/google")
    if time.time() >= token.get("expires_at", 0) - 300:
        token = _refresh_token(token)
    return token["access_token"]


def get_credentials() -> Credentials:
    """Returns Google Credentials object for API clients (Drive, Gmail)."""
    token = _load_token()
    if not token:
        raise ValueError("Google not authorized — visit /api/auth/google")
    if time.time() >= token.get("expires_at", 0) - 300:
        token = _refresh_token(token)
    creds = Credentials(
        token=token.get("access_token"),
        refresh_token=token.get("refresh_token"),
        token_uri=TOKEN_URL,
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        scopes=SCOPES,
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _save_token({
            "access_token":  creds.token,
            "refresh_token": creds.refresh_token,
            "expires_at":    time.time() + 3600
        })
    return creds


def is_authorized() -> bool:
    """True if a valid refresh_token exists. Cheap check — no network call."""
    token = _load_token()
    return bool(token and token.get("refresh_token"))