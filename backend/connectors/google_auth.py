"""
ORA Google Auth — OAuth 2.0 token manager.
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
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

AUTH_URL    = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL   = "https://oauth2.googleapis.com/token"


# ── token storage ─────────────────────────────────────────────
def _load_token() -> Optional[dict]:
    try:
        if os.path.exists(TOKEN_PATH):
            with open(TOKEN_PATH, "r") as f:
                return json.load(f)
    except Exception as e:
        print(f"[GOOGLE AUTH] load error: {e}")
    return None


def _save_token(token: dict) -> None:
    try:
        os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
        with open(TOKEN_PATH, "w") as f:
            json.dump(token, f, indent=2)
    except Exception as e:
        print(f"[GOOGLE AUTH] save error: {e}")


# ── auth URL ──────────────────────────────────────────────────
def get_auth_url() -> str:
    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
    }
    query = "&".join(f"{k}={quote(str(v), safe='')}" for k, v in params.items())
    return f"{AUTH_URL}?{query}"


# ── exchange code ─────────────────────────────────────────────
def exchange_code(code: str) -> dict:
    resp = requests.post(TOKEN_URL, data={
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
        "code": code,
    }, timeout=15)

    resp.raise_for_status()
    token = resp.json()
    token["expires_at"] = time.time() + token.get("expires_in", 3600)
    _save_token(token)
    return token


# ── refresh token ─────────────────────────────────────────────
def _refresh_token(token: dict) -> dict:
    refresh_token = token.get("refresh_token")
    if not refresh_token:
        raise ValueError("Missing refresh token")

    resp = requests.post(TOKEN_URL, data={
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }, timeout=15)

    resp.raise_for_status()
    new_token = resp.json()

    new_token["refresh_token"] = refresh_token
    new_token["expires_at"] = time.time() + new_token.get("expires_in", 3600)

    _save_token(new_token)
    return new_token


# ── ACCESS TOKEN ──────────────────────────────────────────────
def get_access_token() -> str:
    token = _load_token()
    if not token:
        raise ValueError("Not authorized")

    if time.time() >= token.get("expires_at", 0) - 300:
        token = _refresh_token(token)

    return token["access_token"]


# ── ⭐ FIX FOR YOUR ERROR ──────────────────────────────────────
def get_credentials() -> Credentials:
    """
    REQUIRED BY drive.py (fixes Pylance error)
    Returns Google Credentials object for API clients.
    """
    token = _load_token()
    if not token:
        raise ValueError("Google not authorized")

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

    # auto refresh support
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _save_token({
            "access_token": creds.token,
            "refresh_token": creds.refresh_token,
            "expires_at": time.time() + 3600
        })

    return creds


def is_authorized() -> bool:
    token = _load_token()
    return bool(token and token.get("refresh_token"))