"""Request authentication for ORA's single-user deployment.

The web app is intentionally simple: one configured API token protects all
application endpoints. Health checks and the Google OAuth handshake remain
public so the service can start and complete login. Production fails closed
when ORA_API_TOKEN is missing; local development may opt out explicitly.
"""

from __future__ import annotations

import hmac
import os
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

_API_TOKEN = os.getenv("ORA_API_TOKEN", "").strip()
_APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
_PUBLIC_EXACT_PATHS = {
    "/",
    "/api/health",
    "/api/ping",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/api/whatsapp/incoming",
}
_PUBLIC_PREFIXES = (
    "/api/auth/google",
)


def is_public_path(path: str) -> bool:
    return path in _PUBLIC_EXACT_PATHS or path.startswith(_PUBLIC_PREFIXES)


def is_authorized(token: str | None) -> bool:
    """Return whether the supplied header token is valid for this process."""
    if _API_TOKEN:
        return bool(token) and hmac.compare_digest(token.strip(), _API_TOKEN)
    # A missing token is acceptable only for an explicitly local/test process.
    return _APP_ENV in {"development", "test", "local"}


async def auth_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Any]],
):
    if request.method == "OPTIONS" or is_public_path(request.url.path):
        return await call_next(request)

    if not is_authorized(request.headers.get("X-ORA-Token")):
        status = 503 if not _API_TOKEN else 401
        detail = (
            "ORA_API_TOKEN is not configured"
            if status == 503
            else "Missing or invalid X-ORA-Token"
        )
        return JSONResponse(
            status_code=status,
            content={"ok": False, "error": detail},
        )

    return await call_next(request)
