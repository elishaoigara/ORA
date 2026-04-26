"""
ORA Google Auth — OAuth 2.0 token manager.

Uses env vars directly (no credentials.json file needed):
  GOOGLE_CLIENT_ID
  GOOGLE_CLIENT_SECRET
  GOOGLE_REDIRECT_URI     e.g. https://ora-oovf.onrender.com/api/auth/google/callback

Tokens are persisted to Render disk at ORA_DATA_DIR/google_token.json
so they survive server restarts. The refresh token is used automatically
when the access token expires.

Flow:
  1. User visits GET /api/auth/google → redirected to Google consent screen
  2. Google redirects to GOOGLE_REDIRECT_URI with ?code=...
  3. GET /api/auth/google/callback exchanges code → stores token
  4. All subsequent API calls use get_credentials() which auto-refreshes
"""

from __future__ import annotations

import json
import os
import time
from typing import Optional

import requests
from urllib.parse import quote

# ── Config ────────────────────────────────────────────────────
CLIENT_ID       = os.getenv("GOOGLE_CLIENT_ID", "")
CLIENT_SECRET   = os.getenv("GOOGLE_CLIENT_SECRET", "")
REDIRECT_URI    = os.getenv("GOOGLE_REDIRECT_URI", "")

TOKEN_PATH      = os.path.join(
    os.getenv("ORA_DATA_DIR", "./data"),
    "google_token.json"
)

SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

AUTH_URL    = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL   = "https://oauth2.googleapis.com/token"


# ── Token persistence ─────────────────────────────────────────
def _load_token() -> Optional[dict]:
    try:
        if os.path.exists(TOKEN_PATH):
            with open(TOKEN_PATH, "r") as f:
                return json.load(f)
    except Exception as e:
        print(f"[GOOGLE AUTH] load token error: {e}")
    return None


def _save_token(token: dict) -> None:
    try:
        os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
        with open(TOKEN_PATH, "w") as f:
            json.dump(token, f, indent=2)
    except Exception as e:
        print(f"[GOOGLE AUTH] save token error: {e}")


# ── OAuth step 1: build authorization URL ─────────────────────
def get_auth_url() -> str:
    """Return the Google consent URL to redirect the user to."""
    params = {
        "client_id":     CLIENT_ID,
        "redirect_uri":  REDIRECT_URI,
        "response_type": "code",
        "scope":         " ".join(SCOPES),
        "access_type":   "offline",   # gets refresh token
        "prompt":        "consent",   # always show consent to get refresh token
    }
    query = "&".join(f"{k}={quote(str(v), safe='')}" for k, v in params.items())
    return f"{AUTH_URL}?{query}"


# ── OAuth step 2: exchange code → token ───────────────────────
def exchange_code(code: str) -> dict:
    """Exchange auth code for access + refresh tokens. Saves to disk."""
    resp = requests.post(TOKEN_URL, data={
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri":  REDIRECT_URI,
        "grant_type":    "authorization_code",
        "code":          code,
    }, timeout=15)
    resp.raise_for_status()
    token = resp.json()
    # Store expiry as absolute timestamp
    token["expires_at"] = time.time() + token.get("expires_in", 3600)
    _save_token(token)
    print("[GOOGLE AUTH] Token saved successfully")
    return token


# ── Token refresh ─────────────────────────────────────────────
def _refresh_token(token: dict) -> dict:
    """Use the refresh token to get a new access token."""
    refresh_token = token.get("refresh_token")
    if not refresh_token:
        raise ValueError("No refresh token available. Re-authorize via /api/auth/google")

    resp = requests.post(TOKEN_URL, data={
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type":    "refresh_token",
        "refresh_token": refresh_token,
    }, timeout=15)
    resp.raise_for_status()
    new_token = resp.json()
    # Preserve refresh token (Google doesn't always re-send it)
    new_token["refresh_token"] = refresh_token
    new_token["expires_at"] = time.time() + new_token.get("expires_in", 3600)
    _save_token(new_token)
    print("[GOOGLE AUTH] Token refreshed")
    return new_token


# ── Main: get a valid access token ────────────────────────────
def get_access_token() -> str:
    """
    Returns a valid access token, refreshing if needed.
    Raises ValueError if not yet authorized.
    """
    token = _load_token()
    if not token:
        raise ValueError("Google not authorized. Visit /api/auth/google to connect.")

    # Refresh if expiring within 5 minutes
    expires_at = token.get("expires_at", 0)
    if time.time() >= expires_at - 300:
        token = _refresh_token(token)

    access_token = token.get("access_token")
    if not access_token:
        raise ValueError("Invalid token data. Re-authorize via /api/auth/google")
    return access_token


def is_authorized() -> bool:
    """Check if Google is already connected (token exists on disk)."""
    token = _load_token()
    return bool(token and token.get("refresh_token"))