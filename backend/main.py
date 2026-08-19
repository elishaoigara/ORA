"""Compatibility entry point for ORA.

The deployed service runs ``uvicorn api:app``. This module remains only so
older local commands do not start a second scheduler or agent loop.
"""

from __future__ import annotations

import os

from api import app

__all__ = ["app"]


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        reload=False,
    )
