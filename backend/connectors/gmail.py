"""
ORA Gmail Connector — Phase 4
Polls Gmail every 15 min for unread emails (last 24h).
Feeds summaries into agent context + important ones into knowledge base.
Render free tier safe — max 10 emails per cycle.
"""

from __future__ import annotations

import base64
import traceback
from datetime import datetime, timezone, timedelta

MAX_EMAILS_PER_CYCLE = 10
MAX_BODY_CHARS = 2000


# ── Gmail service ──────────────────────────────────────────────
def _service():
    from connectors.google_auth import get_credentials
    from googleapiclient.discovery import build

    creds = get_credentials()
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


# ── Body decoder ───────────────────────────────────────────────
def _decode_body(payload: dict) -> str:
    body = ""
    mime = payload.get("mimeType", "")

    if mime == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            body = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="ignore")

    elif mime.startswith("multipart"):
        for part in payload.get("parts", []):
            if part.get("mimeType") == "text/plain":
                data = part.get("body", {}).get("data", "")
                if data:
                    body = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="ignore")
                    break

    return body.strip()[:MAX_BODY_CHARS]


# ── Header helper ──────────────────────────────────────────────
def _get_header(headers: list, name: str) -> str:
    for h in headers:
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


# ── SAFE INGESTION WRAPPER (FIX FOR ALL CONNECTORS) ───────────
def _ingest(text: str, source: str, tags: str) -> None:
    try:
        import knowledge.pipeline as kp

        ingest_fn = getattr(kp, "ingest_text", None)

        if callable(ingest_fn):
            ingest_fn(text=text, source=source, tags=tags)
        else:
            print("[GMAIL] ingest_text not available in pipeline")

    except Exception as e:
        print(f"[GMAIL] ingestion error: {e}")


# ── Fetch emails ───────────────────────────────────────────────
def get_recent_emails(max_results: int = MAX_EMAILS_PER_CYCLE) -> list[dict]:
    try:
        from connectors.google_auth import is_authorized
        if not is_authorized():
            return []

        service = _service()

        since_ts = int(
            (datetime.now(timezone.utc) - timedelta(hours=24)).timestamp()
        )

        results = service.users().messages().list(
            userId="me",
            q=f"is:unread after:{since_ts}",
            maxResults=max_results,
        ).execute()

        emails = []

        for ref in results.get("messages", [])[:max_results]:
            try:
                msg = service.users().messages().get(
                    userId="me",
                    id=ref["id"],
                    format="full",
                ).execute()

                headers = msg.get("payload", {}).get("headers", [])

                emails.append({
                    "id": ref["id"],
                    "sender": _get_header(headers, "From")[:100],
                    "subject": _get_header(headers, "Subject")[:200],
                    "body": _decode_body(msg.get("payload", {}))
                            or msg.get("snippet", "")[:500],
                    "date": _get_header(headers, "Date"),
                    "labels": msg.get("labelIds", []),
                })

            except Exception as e:
                print(f"[GMAIL] message error {ref['id']}: {e}")

        return emails

    except Exception:
        print("[GMAIL] get_recent_emails failed:")
        print(traceback.format_exc())
        return []


# ── Lightweight summary (agent context) ────────────────────────
def get_gmail_summary() -> dict:
    try:
        emails = get_recent_emails(max_results=5)

        if not emails:
            return {"unread_count": 0, "senders": [], "subjects": []}

        return {
            "unread_count": len(emails),
            "senders": [e["sender"].split("<")[0].strip() for e in emails],
            "subjects": [e["subject"] for e in emails],
        }

    except Exception:
        return {"unread_count": 0, "senders": [], "subjects": []}


# ── Full sync (ingestion) ──────────────────────────────────────
def sync_gmail() -> None:
    try:
        from connectors.google_auth import is_authorized

        if not is_authorized():
            print("[GMAIL] Not authorized — skipping")
            return

        emails = get_recent_emails()

        if not emails:
            print("[GMAIL] No new emails")
            return

        print(f"[GMAIL] Processing {len(emails)} email(s)")

        ingested = 0

        for email in emails:
            labels = set(email.get("labels", []))
            body = email.get("body", "")
            subject = email.get("subject", "")

            # Skip noise
            skip = {
                "CATEGORY_PROMOTIONS",
                "CATEGORY_SOCIAL",
                "SPAM",
                "CATEGORY_FORUMS",
            }

            if labels.intersection(skip):
                continue

            if len(body) < 100:
                continue

            text = (
                f"Email from: {email['sender']}\n"
                f"Subject: {subject}\n"
                f"Date: {email['date']}\n\n"
                f"{body}"
            )

            _ingest(
                text=text,
                source=f"Gmail: {subject[:60]}",
                tags=f"gmail:{email['id']}",
            )

            ingested += 1

        print(f"[GMAIL] Sync complete — {ingested} email(s) ingested")

    except Exception:
        print("[GMAIL] sync_gmail failed:")
        print(traceback.format_exc())