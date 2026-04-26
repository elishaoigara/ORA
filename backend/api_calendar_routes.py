"""
ORA Calendar API Routes — Phase 2

Add these routes to api.py by importing and including this router.

In api.py, add these two lines after `app = FastAPI(...)`:

    from api_calendar_routes import router as calendar_router
    app.include_router(calendar_router)
"""

from __future__ import annotations

import traceback
from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

router = APIRouter()


# ── Google OAuth flow ─────────────────────────────────────────

@router.get("/api/auth/google")
def google_auth_start():
    """
    Step 1: Redirect user to Google consent screen.
    Visit this URL once in your browser to authorize ORA.
    """
    try:
        from connectors.google_auth import get_auth_url, CLIENT_ID, REDIRECT_URI
        if not CLIENT_ID:
            raise HTTPException(500, "GOOGLE_CLIENT_ID not configured in env vars")
        if not REDIRECT_URI:
            raise HTTPException(500, "GOOGLE_REDIRECT_URI not configured in env vars")
        url = get_auth_url()
        return RedirectResponse(url)
    except HTTPException:
        raise
    except Exception:
        print(traceback.format_exc())
        raise HTTPException(500, "Failed to build auth URL")


@router.get("/api/auth/google/callback")
def google_auth_callback(code: str = "", error: str = ""):
    """
    Step 2: Google redirects here with ?code=...
    Exchanges the code for tokens and saves them to disk.
    After this succeeds, calendar + drive are live.
    """
    if error:
        return {"status": "error", "detail": error}
    if not code:
        raise HTTPException(400, "No code received from Google")

    try:
        from connectors.google_auth import exchange_code
        exchange_code(code)
        return {
            "status": "success",
            "message": "Google authorized. Calendar and Drive are now connected.",
        }
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(500, f"Token exchange failed: {str(e)[:200]}")


@router.get("/api/auth/google/status")
def google_auth_status():
    """Check whether Google is currently authorized."""
    try:
        from connectors.google_auth import is_authorized
        authorized = is_authorized()
        return {
            "authorized": authorized,
            "message": "Google connected" if authorized else "Not connected. Visit /api/auth/google to authorize.",
        }
    except Exception:
        return {"authorized": False, "message": "Error checking status"}


# ── Calendar endpoints ────────────────────────────────────────

@router.get("/api/calendar/today")
def calendar_today():
    """Events in the next 24 hours."""
    try:
        from connectors.calendar import get_events_today
        return get_events_today()
    except Exception:
        print(traceback.format_exc())
        raise HTTPException(500, "Failed to fetch calendar events")


@router.get("/api/calendar/week")
def calendar_week():
    """Events in the next 7 days."""
    try:
        from connectors.calendar import get_events_this_week
        return get_events_this_week()
    except Exception:
        print(traceback.format_exc())
        raise HTTPException(500, "Failed to fetch calendar events")


@router.get("/api/calendar/imminent")
def calendar_imminent(minutes: int = 30):
    """Events starting within `minutes` from now."""
    try:
        from connectors.calendar import get_imminent_events
        return get_imminent_events(threshold_minutes=minutes)
    except Exception:
        print(traceback.format_exc())
        raise HTTPException(500, "Failed to fetch imminent events")