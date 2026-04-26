# backend/api_calendar_routes.py

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
import traceback

router = APIRouter()


# ── Google OAuth ─────────────────────────────

@router.get("/api/auth/google")
def google_auth_start():
    try:
        from connectors.google_auth import get_auth_url, CLIENT_ID, REDIRECT_URI

        if not CLIENT_ID:
            raise HTTPException(500, "Missing GOOGLE_CLIENT_ID")
        if not REDIRECT_URI:
            raise HTTPException(500, "Missing GOOGLE_REDIRECT_URI")

        return RedirectResponse(get_auth_url())

    except Exception:
        print(traceback.format_exc())
        raise HTTPException(500, "Auth URL failed")


@router.get("/api/auth/google/callback")
def google_auth_callback(code: str = "", error: str = ""):
    if error:
        return {"status": "error", "detail": error}
    if not code:
        raise HTTPException(400, "Missing code")

    try:
        from connectors.google_auth import exchange_code
        exchange_code(code)
        return {"status": "success", "message": "Google connected"}
    except Exception:
        print(traceback.format_exc())
        raise HTTPException(500, "Token exchange failed")


@router.get("/api/auth/google/status")
def google_auth_status():
    try:
        from connectors.google_auth import is_authorized
        return {"authorized": is_authorized()}
    except Exception:
        return {"authorized": False}


# ── Calendar ─────────────────────────────

@router.get("/api/calendar/today")
def calendar_today():
    try:
        from connectors.calendar import get_events_today
        return get_events_today()
    except Exception:
        raise HTTPException(500, "Calendar failed")


@router.get("/api/calendar/week")
def calendar_week():
    try:
        from connectors.calendar import get_events_this_week
        return get_events_this_week()
    except Exception:
        raise HTTPException(500, "Calendar failed")


@router.get("/api/calendar/imminent")
def calendar_imminent(minutes: int = 30):
    try:
        from connectors.calendar import get_imminent_events
        return get_imminent_events(minutes)
    except Exception:
        raise HTTPException(500, "Calendar failed")