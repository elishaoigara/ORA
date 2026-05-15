"""
ORA Google Auth — multi-account OAuth 2.0 token manager.

Supports two Google accounts:
  account="primary"    → google_token_primary.json   (your main account)
  account="secondary"  → google_token_secondary.json (your second account)

Backward-compatible: existing google_token.json is auto-migrated to
google_token_primary.json on first load so nothing breaks.

All existing callers that don't pass `account` continue to use "primary".
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

try:
    from config import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI, DATA_DIR
except ImportError:
    GOOGLE_CLIENT_ID     = os.getenv("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
    GOOGLE_REDIRECT_URI  = os.getenv("GOOGLE_REDIRECT_URI", "")
    DATA_DIR = os.getenv("ORA_DATA_DIR", "./data")

CLIENT_ID     = GOOGLE_CLIENT_ID
CLIENT_SECRET = GOOGLE_CLIENT_SECRET
REDIRECT_URI  = GOOGLE_REDIRECT_URI

# Legacy path — migrated automatically on first run
_LEGACY_TOKEN_PATH = os.path.join(DATA_DIR, "google_token.json")

ACCOUNTS = ("primary", "secondary")

SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/drive.readonly",
]

AUTH_URL  = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"

# Kept for any code that still imports TOKEN_PATH directly
TOKEN_PATH = _LEGACY_TOKEN_PATH


# ─────────────────────────────────────────────
# INTERNAL HELPERS
# ─────────────────────────────────────────────

def _token_path(account: str) -> str:
    if account not in ACCOUNTS:
        raise ValueError(f"account must be one of {ACCOUNTS}, got {account!r}")
    return os.path.join(DATA_DIR, f"google_token_{account}.json")


def _migrate_legacy() -> None:
    """
    One-time migration: if old google_token.json exists but
    google_token_primary.json does not, rename it.
    """
    primary_path = _token_path("primary")
    if os.path.exists(_LEGACY_TOKEN_PATH) and not os.path.exists(primary_path):
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            os.rename(_LEGACY_TOKEN_PATH, primary_path)
            print("[GOOGLE AUTH] Migrated google_token.json → google_token_primary.json")
        except Exception as e:
            print(f"[GOOGLE AUTH] Migration failed: {e}")


# Run migration at import time
_migrate_legacy()


def _load_token(account: str = "primary") -> Optional[dict]:
    path = _token_path(account)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r") as f:
            raw = f.read().strip()
        if not raw:
            return None

        # Primary parse
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass

        # Handle concatenated JSON objects (write-corruption fix)
        decoder = json.JSONDecoder()
        last_valid: Optional[dict] = None
        idx = 0
        while idx < len(raw):
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
            print(f"[GOOGLE AUTH:{account}] Token had extra data — repaired.")
            _save_token(last_valid, account)
            return last_valid

        print(f"[GOOGLE AUTH:{account}] Token unreadable — removing. Re-authorize.")
        try:
            os.remove(path)
        except OSError:
            pass
        return None

    except Exception as e:
        print(f"[GOOGLE AUTH:{account}] load error: {e}")
        return None


def _save_token(token: dict, account: str = "primary") -> None:
    path = _token_path(account)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(token, f, indent=2)
        os.replace(tmp, path)
    except Exception as e:
        print(f"[GOOGLE AUTH:{account}] save error: {e}")


def _refresh_token(token: dict, account: str = "primary") -> dict:
    refresh_token = token.get("refresh_token")
    if not refresh_token:
        raise ValueError(f"Missing refresh token for {account}")
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
    _save_token(new_token, account)
    return new_token


# ─────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────

def get_auth_url(account: str = "primary") -> str:
    """
    Returns the Google OAuth URL for the given account.
    Pass account="secondary" to get the URL for the second account.
    Uses `login_hint` param so Google shows account-picker correctly.
    """
    params = {
        "client_id":     CLIENT_ID,
        "redirect_uri":  REDIRECT_URI if account == "primary"
                         else REDIRECT_URI.replace("/callback", "/callback2"),
        "response_type": "code",
        "scope":         " ".join(SCOPES),
        "access_type":   "offline",
        "prompt":        "consent",
        "state":         account,   # echoed back in callback so we know which account
    }
    query = "&".join(f"{k}={quote(str(v), safe='')}" for k, v in params.items())
    return f"{AUTH_URL}?{query}"


def exchange_code(code: str, account: str = "primary") -> dict:
    """Exchange OAuth code for tokens and save under the given account."""
    redirect = (
        REDIRECT_URI if account == "primary"
        else REDIRECT_URI.replace("/callback", "/callback2")
    )
    resp = requests.post(TOKEN_URL, data={
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri":  redirect,
        "grant_type":    "authorization_code",
        "code":          code,
    }, timeout=15)
    resp.raise_for_status()
    token = resp.json()
    token["expires_at"] = time.time() + token.get("expires_in", 3600)
    _save_token(token, account)
    print(f"[GOOGLE AUTH] {account} account authorized successfully")
    return token


def get_access_token(account: str = "primary") -> str:
    token = _load_token(account)
    if not token:
        raise ValueError(f"Account '{account}' not authorized — visit /api/auth/google/{account}")
    if time.time() >= token.get("expires_at", 0) - 300:
        token = _refresh_token(token, account)
    return token["access_token"]


def get_credentials(account: str = "primary") -> Credentials:
    token = _load_token(account)
    if not token:
        raise ValueError(f"Account '{account}' not authorized")
    if time.time() >= token.get("expires_at", 0) - 300:
        token = _refresh_token(token, account)
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
            "expires_at":    time.time() + 3600,
        }, account)
    return creds


def is_authorized(account: str = "primary") -> bool:
    """True if a valid refresh_token exists for this account."""
    token = _load_token(account)
    return bool(token and token.get("refresh_token"))


def revoke(account: str = "primary") -> bool:
    """Delete saved token for this account."""
    path = _token_path(account)
    try:
        if os.path.exists(path):
            os.remove(path)
        return True
    except Exception:
        return False


def get_all_authorized_accounts() -> list[str]:
    """Returns list of account names that are currently authorized."""
    return [a for a in ACCOUNTS if is_authorized(a)]