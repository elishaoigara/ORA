"""
ORA Google routes — Calendar, Gmail status, OAuth flow.
Multi-account support: primary + secondary Gmail accounts.
"""

import os
import traceback

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

router = APIRouter()


# ── Primary Google Account OAuth ─────────────────────────────

@router.get("/api/auth/google")
def google_auth_start():
    try:
        from connectors.google_auth import get_auth_url, CLIENT_ID, REDIRECT_URI
        if not CLIENT_ID:
            raise HTTPException(500, "GOOGLE_CLIENT_ID not set in environment variables")
        if not REDIRECT_URI:
            raise HTTPException(500, "GOOGLE_REDIRECT_URI not set in environment variables")
        return RedirectResponse(get_auth_url(account="primary"))
    except HTTPException:
        raise
    except Exception:
        print(traceback.format_exc())
        raise HTTPException(500, "Auth URL failed")


@router.get("/api/auth/google/callback")
def google_auth_callback(code: str = "", error: str = ""):
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
        exchange_code(code, account="primary")
        return RedirectResponse(f"{frontend_url}?google_auth=success")
    except Exception:
        print(traceback.format_exc())
        return RedirectResponse(f"{frontend_url}?google_auth=error&detail=token_exchange_failed")


@router.get("/api/auth/google/status")
def google_auth_status():
    try:
        from connectors.google_auth import is_authorized, CLIENT_ID
        return {
            "authorized":        is_authorized("primary"),
            "client_configured": bool(CLIENT_ID),
        }
    except Exception:
        return {"authorized": False, "client_configured": False}


@router.delete("/api/auth/google")
def google_auth_revoke():
    """Disconnect primary Google account."""
    try:
        from connectors.google_auth import revoke
        revoke("primary")
        return {"status": "disconnected"}
    except Exception:
        raise HTTPException(500, "Disconnect failed")


# ── Secondary Google Account OAuth ───────────────────────────
# Before using: add /api/auth/google/callback2 as an authorised
# redirect URI in Google Cloud Console (same OAuth client).

@router.get("/api/auth/google/secondary")
def google_auth_secondary_start():
    """Start OAuth flow for the second Gmail account."""
    try:
        from connectors.google_auth import get_auth_url, CLIENT_ID
        if not CLIENT_ID:
            raise HTTPException(500, "GOOGLE_CLIENT_ID not set")
        return RedirectResponse(get_auth_url(account="secondary"))
    except HTTPException:
        raise
    except Exception:
        print(traceback.format_exc())
        raise HTTPException(500, "Auth URL failed")


@router.get("/api/auth/google/callback2")
def google_auth_secondary_callback(code: str = "", error: str = ""):
    """OAuth callback for the second Gmail account."""
    frontend_url = (
        os.getenv("FRONTEND_URL", "").rstrip("/")
        or os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")
        or "http://localhost:5173"
    )

    if error:
        return RedirectResponse(f"{frontend_url}?google_auth2=error&detail={error}")
    if not code:
        raise HTTPException(400, "Missing code")

    try:
        from connectors.google_auth import exchange_code
        exchange_code(code, account="secondary")
        return RedirectResponse(f"{frontend_url}?google_auth2=success")
    except Exception:
        print(traceback.format_exc())
        return RedirectResponse(f"{frontend_url}?google_auth2=error&detail=token_exchange_failed")


@router.get("/api/auth/google/secondary/status")
def google_auth_secondary_status():
    """Check if the secondary account is authorized."""
    try:
        from connectors.google_auth import is_authorized
        return {"authorized": is_authorized("secondary")}
    except Exception:
        return {"authorized": False}


@router.delete("/api/auth/google/secondary")
def google_auth_secondary_revoke():
    """Disconnect the secondary Google account."""
    try:
        from connectors.google_auth import revoke
        revoke("secondary")
        return {"status": "disconnected"}
    except Exception:
        raise HTTPException(500, "Disconnect failed")


@router.get("/api/auth/google/accounts")
def google_accounts_status():
    """Auth status for all accounts in one call."""
    try:
        from connectors.google_auth import is_authorized, get_all_authorized_accounts
        return {
            "primary":   {"authorized": is_authorized("primary")},
            "secondary": {"authorized": is_authorized("secondary")},
            "connected": get_all_authorized_accounts(),
        }
    except Exception:
        return {
            "primary":   {"authorized": False},
            "secondary": {"authorized": False},
            "connected": [],
        }


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
    """
    Returns combined unread count from all authorized accounts.
    Promotions/social/updates excluded automatically.
    """
    try:
        from connectors.google_auth import is_authorized
        if not is_authorized("primary") and not is_authorized("secondary"):
            return {"authorized": False, "unread_count": 0}
        from connectors.gmail import get_gmail_summary
        result = get_gmail_summary()
        return {**result, "authorized": True}
    except Exception:
        print(traceback.format_exc())
        return {"authorized": False, "unread_count": 0, "error": "Gmail unavailable"}


@router.get("/api/gmail/emails")
def gmail_emails_route(limit: int = 10):
    """
    Returns primary-inbox unread emails from all authorized accounts,
    merged and sorted newest-first. Promotions excluded.
    """
    try:
        from connectors.google_auth import is_authorized
        if not is_authorized("primary") and not is_authorized("secondary"):
            return []
        from connectors.gmail import get_recent_emails
        return get_recent_emails(max_results=min(limit, 20))
    except Exception:
        print(traceback.format_exc())
        return []


# ── Calendar write routes ─────────────────────────────────────

@router.post("/api/calendar/create")
def calendar_create(body: dict):
    """
    Create a calendar event from natural language.
    Body: {"text": "Team meeting tomorrow at 3pm for 1 hour"}
    """
    try:
        from connectors.calendar import quick_event
        text = (body.get("text") or "").strip()
        if not text:
            raise HTTPException(400, "text is required")
        return quick_event(text)
    except HTTPException:
        raise
    except Exception:
        print(traceback.format_exc())
        raise HTTPException(500, "Calendar create failed")


@router.patch("/api/calendar/update/{event_id}")
def calendar_update(event_id: str, body: dict):
    """
    Update an existing event.
    Body: {title?, start? (ISO), end? (ISO), location?, description?}
    """
    try:
        from connectors.calendar import update_event
        from datetime import datetime, timezone

        def _dt(s):
            if not s:
                return None
            dt = datetime.fromisoformat(s)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

        return update_event(
            event_id    = event_id,
            title       = body.get("title"),
            start       = _dt(body.get("start")),
            end         = _dt(body.get("end")),
            description = body.get("description"),
            location    = body.get("location"),
        )
    except Exception:
        print(traceback.format_exc())
        raise HTTPException(500, "Calendar update failed")


@router.delete("/api/calendar/delete/{event_id}")
def calendar_delete(event_id: str):
    """Delete a calendar event by ID."""
    try:
        from connectors.calendar import delete_event
        return delete_event(event_id)
    except Exception:
        print(traceback.format_exc())
        raise HTTPException(500, "Calendar delete failed")


@router.get("/api/calendar/free-slot")
def calendar_free_slot(duration: int = 60, hours_ahead: int = 48):
    """Find the next free slot of `duration` minutes in the next `hours_ahead` hours."""
    try:
        from connectors.calendar import find_free_slot
        result = find_free_slot(duration_minutes=duration, hours_ahead=hours_ahead)
        if result.get("ok"):
            result["start"] = result["start"].isoformat()
            result["end"]   = result["end"].isoformat()
        return result
    except Exception:
        print(traceback.format_exc())
        raise HTTPException(500, "Free slot search failed")