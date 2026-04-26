"""
ORA Drive Connector — Phase 4
Polls Google Drive every 30 min for new/modified docs.
Feeds knowledge/pipeline.py automatically.
Render free tier safe — no threads, uses existing scheduler.
"""

from __future__ import annotations

import traceback
from datetime import datetime, timezone, timedelta
from typing import Optional, Callable

# ─────────────────────────────────────────────────────────────
# Supported file types
# ─────────────────────────────────────────────────────────────
SUPPORTED_MIME = {
    "application/vnd.google-apps.document",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
    "text/markdown",
    "application/pdf",
}

EXPORT_MIME = {
    "application/vnd.google-apps.document": "text/plain",
}


# ─────────────────────────────────────────────────────────────
# Google Drive service
# ─────────────────────────────────────────────────────────────
def _service():
    from connectors.google_auth import get_credentials
    from googleapiclient.discovery import build

    creds = get_credentials()
    return build("drive", "v3", credentials=creds, cache_discovery=False)


# ─────────────────────────────────────────────────────────────
# SAFE IMPORT (fixes Pylance issue cleanly)
# ─────────────────────────────────────────────────────────────
def _get_ingest_text() -> Optional[Callable[..., None]]:
    try:
        from knowledge.pipeline import ingest_text  # type: ignore[attr-defined]
        return ingest_text
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────
# Drive sync state
# ─────────────────────────────────────────────────────────────
def _get_last_check() -> str:
    try:
        from config import DB_PATH
        import sqlite3

        con = sqlite3.connect(DB_PATH)
        con.execute("""
            CREATE TABLE IF NOT EXISTS drive_state (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        row = con.execute(
            "SELECT value FROM drive_state WHERE key='last_check'"
        ).fetchone()

        con.close()

        if row:
            return row[0]

    except Exception:
        pass

    # default: last 24 hours
    return (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()


def _set_last_check(ts: str) -> None:
    try:
        from config import DB_PATH
        import sqlite3

        con = sqlite3.connect(DB_PATH)
        con.execute("""
            CREATE TABLE IF NOT EXISTS drive_state (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        con.execute(
            "INSERT OR REPLACE INTO drive_state (key, value) VALUES ('last_check', ?)",
            (ts,)
        )

        con.commit()
        con.close()

    except Exception:
        pass


# ─────────────────────────────────────────────────────────────
# Extract text from Drive files
# ─────────────────────────────────────────────────────────────
def _extract_text(service, file_id: str, mime: str, filename: str) -> str:
    try:
        if mime == "application/vnd.google-apps.document":
            data = service.files().export(
                fileId=file_id,
                mimeType="text/plain"
            ).execute()
            return data.decode("utf-8", errors="ignore")

        elif mime in ("text/plain", "text/markdown"):
            data = service.files().get_media(fileId=file_id).execute()
            return data.decode("utf-8", errors="ignore")

        elif mime == "application/pdf":
            import io
            import pdfplumber

            data = service.files().get_media(fileId=file_id).execute()
            with pdfplumber.open(io.BytesIO(data)) as pdf:
                return "\n".join(
                    page.extract_text() or ""
                    for page in pdf.pages[:20]
                )

        elif "wordprocessingml" in mime:
            import io
            from docx import Document

            data = service.files().get_media(fileId=file_id).execute()
            doc = Document(io.BytesIO(data))
            return "\n".join(p.text for p in doc.paragraphs)

    except Exception as e:
        print(f"[DRIVE] extract failed {filename}: {e}")

    return ""


# ─────────────────────────────────────────────────────────────
# MAIN SYNC FUNCTION
# ─────────────────────────────────────────────────────────────
def sync_drive() -> None:
    try:
        from connectors.google_auth import is_authorized

        if not is_authorized():
            print("[DRIVE] Not authorized")
            return

        service = _service()
        last_check = _get_last_check()
        now_ts = datetime.now(timezone.utc).isoformat()

        print(f"[DRIVE] Sync since {last_check[:19]}")

        results = service.files().list(
            q=f"modifiedTime > '{last_check}' and trashed=false",
            fields="files(id,name,mimeType,modifiedTime,size)",
            pageSize=20,
            orderBy="modifiedTime desc",
        ).execute()

        files = results.get("files", [])
        print(f"[DRIVE] Found {len(files)} files")

        ingest_text = _get_ingest_text()
        ingested = 0

        for f in files:
            mime = f.get("mimeType", "")
            filename = f.get("name", "")
            file_id = f["id"]

            if mime not in SUPPORTED_MIME:
                continue

            text = _extract_text(service, file_id, mime, filename)

            if not text or len(text.strip()) < 50:
                continue

            # ── SAFE INGEST ───────────────────────────────
            if ingest_text:
                try:
                    ingest_text(
                        text=text[:50000],
                        source=f"Google Drive: {filename}",
                        tags=f"drive:{file_id}",
                    )
                    ingested += 1
                    print(f"[DRIVE] Ingested {filename}")
                except Exception as e:
                    print(f"[DRIVE] ingest failed {filename}: {e}")

        _set_last_check(now_ts)

        print(f"[DRIVE] Sync complete — {ingested} files ingested")

    except Exception:
        print("[DRIVE ERROR]")
        print(traceback.format_exc())