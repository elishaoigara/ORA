"""
ORA Google routes — Calendar, Gmail status, OAuth flow.
"""

import os
import traceback

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

router = APIRouter()


# ── Google OAuth ─────────────────────────────────────────────

@router.get("/api/auth/google")
def google_auth_start():
    try:
        from connectors.google_auth import get_auth_url, CLIENT_ID, REDIRECT_URI
        if not CLIENT_ID:
            raise HTTPException(500, "GOOGLE_CLIENT_ID not set in environment variables")
        if not REDIRECT_URI:
            raise HTTPException(500, "GOOGLE_REDIRECT_URI not set in environment variables")
        return RedirectResponse(get_auth_url())
    except HTTPException:
        raise
    except Exception:
        print(traceback.format_exc())
        raise HTTPException(500, "Auth URL failed")


@router.get("/api/auth/google/callback")
def google_auth_callback(code: str = "", error: str = ""):
    # Determine where to send the user back after auth
    frontend_url = (
        os.getenv("FRONTEND_URL", "").rstrip("/")
        or os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")
        or "http://localhost:5173"
    )

    if error:
        return RedirectResponse(f"{frontend_url}?google_auth=error&detail={error}")

    if not code:
        raise HTTPException(400, "Missing code")

    try:
        from connectors.google_auth import exchange_code
        exchange_code(code)
        # ✅ Redirect back to the frontend app (memory page shows auth status)
        return RedirectResponse(f"{frontend_url}?google_auth=success")
    except Exception:
        print(traceback.format_exc())
        return RedirectResponse(f"{frontend_url}?google_auth=error&detail=token_exchange_failed")


@router.get("/api/auth/google/status")
def google_auth_status():
    try:
        from connectors.google_auth import is_authorized, CLIENT_ID
        return {
            "authorized":    is_authorized(),
            "client_configured": bool(CLIENT_ID),
        }
    except Exception:
        return {"authorized": False, "client_configured": False}


@router.delete("/api/auth/google")
def google_auth_revoke():
    """Disconnect Google — delete stored token."""
    try:
        from connectors.google_auth import TOKEN_PATH
        import os
        if os.path.exists(TOKEN_PATH):
            os.remove(TOKEN_PATH)
        return {"status": "disconnected"}
    except Exception:
        raise HTTPException(500, "Disconnect failed")


# ── Calendar ─────────────────────────────────────────────────

@router.get("/api/calendar/today")
def calendar_today():
    try:
        from connectors.calendar import get_events_today
        return get_events_today()
    except Exception:
        print(traceback.format_exc())
        raise HTTPException(500, "Calendar fetch failed")


@router.get("/api/calendar/week")
def calendar_week():
    try:
        from connectors.calendar import get_events_this_week
        return get_events_this_week()
    except Exception:
        raise HTTPException(500, "Calendar fetch failed")


@router.get("/api/calendar/imminent")
def calendar_imminent(minutes: int = 30):
    try:
        from connectors.calendar import get_imminent_events
        return get_imminent_events(minutes)
    except Exception:
        raise HTTPException(500, "Calendar fetch failed")


# ── Gmail ─────────────────────────────────────────────────────

@router.get("/api/gmail/summary")
def gmail_summary_route():
    try:
        from connectors.google_auth import is_authorized
        if not is_authorized():
            return {"authorized": False, "unread_count": 0}
        from connectors.gmail import get_gmail_summary
        result = get_gmail_summary()
        return {**result, "authorized": True}
    except Exception:
        print(traceback.format_exc())
        return {"authorized": False, "unread_count": 0, "error": "Gmail unavailable"}


@router.get("/api/gmail/emails")
def gmail_emails_route(limit: int = 10):
    try:
        from connectors.google_auth import is_authorized
        if not is_authorized():
            return []
        from connectors.gmail import get_recent_emails
        return get_recent_emails(max_results=min(limit, 10))
    except Exception:
        print(traceback.format_exc())
        return []