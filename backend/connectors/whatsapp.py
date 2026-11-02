"""
ORA WhatsApp Connector v2
Features:
  - Contact name resolution
  - Group mute/unmute
  - Message search
  - Auto-summarise unread (called by scheduler)
  - Smart reply drafting + sending via Telegram inline keyboard
"""

from __future__ import annotations

import os
import time
from typing import Optional

import requests

if os.getenv("WA_SIDECAR_URL", "").strip():
    SIDECAR_URL = os.environ["WA_SIDECAR_URL"].strip().rstrip("/")
elif os.getenv("WA_EMBEDDED", "") == "1":
    # The bridge runs inside this container, so talk to it on loopback: the public
    # port belongs to the API and the bridge is never exposed directly.
    SIDECAR_URL = "http://127.0.0.1:" + (os.getenv("WA_SIDECAR_PORT", "8080").strip() or "8080")
else:
    SIDECAR_URL = ""
API_SECRET  = os.getenv("WA_API_SECRET", "ora-wa-secret-change-me")
# A loopback bridge answers in milliseconds or not at all; long timeouts on a
# 0.1-CPU instance only buy wasted wall-clock while the service is awake.
TIMEOUT     = 5 if SIDECAR_URL.startswith("http://127.0.0.1") else 12

_status_cache: dict = {}
_STATUS_TTL   = 30


def _headers() -> dict:
    return {"x-api-secret": API_SECRET, "Content-Type": "application/json"}

def _get(path: str, params: dict = None) -> dict:
    if not SIDECAR_URL:
        return {"ok": False, "error": "WA_SIDECAR_URL not set"}
    try:
        r = requests.get(f"{SIDECAR_URL}{path}", headers=_headers(),
                         params=params, timeout=TIMEOUT)
        return r.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}

def _post(path: str, body: dict) -> dict:
    if not SIDECAR_URL:
        return {"ok": False, "error": "WA_SIDECAR_URL not set"}
    try:
        r = requests.post(f"{SIDECAR_URL}{path}", headers=_headers(),
                          json=body, timeout=TIMEOUT)
        return r.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ─────────────────────────────────────────────
# CONNECTION
# ─────────────────────────────────────────────

def get_status() -> dict:
    global _status_cache
    now = time.time()
    if _status_cache and now - _status_cache.get("_ts", 0) < _STATUS_TTL:
        return _status_cache
    result = _get("/status")
    if result.get("ok"):
        result["_ts"] = now
        _status_cache = result
    return result

def is_connected() -> bool:
    return get_status().get("state") == "open"


# ─────────────────────────────────────────────
# MESSAGING
# ─────────────────────────────────────────────

def send_message(to: str, message: str) -> dict:
    if not to or not message:
        return {"ok": False, "error": "to and message are required"}
    if not any(c.isdigit() for c in to):
        resolved = resolve_contact(to)
        if not resolved:
            return {"ok": False, "error": f"Contact '{to}' not found in WhatsApp"}
        to = resolved
    return _post("/send", {"to": to, "message": message})

def get_messages(limit: int = 20, contact: str = "",
                 unread_only: bool = False, search: str = "",
                 dms_only: bool = False) -> dict:
    return _get("/messages", {
        "limit":     limit,
        "contact":   contact,
        "unread":    "true" if unread_only else "false",
        "search":    search,
        "no_groups": "true" if dms_only else "false",
    })

def mark_read(message_ids: list[str]) -> dict:
    return _post("/mark-read", {"ids": message_ids})


# ─────────────────────────────────────────────
# CONTACTS
# ─────────────────────────────────────────────

def get_contacts() -> list[dict]:
    result = _get("/contacts")
    return result.get("contacts", [])

def resolve_contact(name: str) -> Optional[str]:
    contacts = get_contacts()
    name_l   = name.lower()
    for c in contacts:
        if c.get("name", "").lower() == name_l:
            return c["phone"]
    for c in contacts:
        if name_l in c.get("name", "").lower():
            return c["phone"]
    return None


# ─────────────────────────────────────────────
# GROUPS
# ─────────────────────────────────────────────

def get_groups() -> list[dict]:
    result = _get("/groups")
    return result.get("groups", [])

def mute_group(jid: str, mute: bool = True) -> dict:
    return _post("/mute", {"jid": jid, "mute": mute})

def get_group_jid(name: str) -> Optional[str]:
    """Find group JID by name (fuzzy)."""
    groups  = get_groups()
    name_l  = name.lower()
    for g in groups:
        if name_l in g.get("name", "").lower():
            return g["jid"]
    return None


# ─────────────────────────────────────────────
# UNREAD SUMMARY
# ─────────────────────────────────────────────

def get_unread_summary() -> dict:
    return _get("/unread-summary")


def format_unread_summary() -> str:
    """
    Morning summary: who messaged you and how many times.
    Returns empty string if nothing unread.
    """
    result = get_unread_summary()
    items  = result.get("summary", [])
    total  = result.get("total", 0)
    if not items:
        return ""

    lines = [f"📱 *WhatsApp — {total} unread message(s):*\n"]
    for item in items[:8]:
        icon  = "👥" if item["type"] == "group" else "👤"
        name  = item["name"]
        count = item["count"]
        preview = item.get("latest", "")[:50]
        lines.append(f"{icon} *{name}* ({count}) — _{preview}_")

    if len(items) > 8:
        lines.append(f"_...and {len(items)-8} more conversations_")
    return "\n".join(lines)


# ─────────────────────────────────────────────
# SMART REPLY (Groq drafts, you approve)
# ─────────────────────────────────────────────

def draft_reply(message: dict, tone: str = "friendly") -> str:
    """
    Use Groq to draft a WhatsApp reply to a message.
    Returns the draft text.
    """
    try:
        from groq import Groq
        from config import GROQ_API_KEY, GROQ_MODEL_PRIMARY

        sender  = message.get("fromName") or message.get("from", "them")
        body    = message.get("body", "")
        group   = f" in group '{message['groupName']}'" if message.get("isGroup") else ""
        client  = Groq(api_key=GROQ_API_KEY)

        prompt = (
            f"Draft a short, {tone} WhatsApp reply to this message from {sender}{group}:\n\n"
            f"\"{body}\"\n\n"
            "Requirements:\n"
            "- Max 2-3 sentences\n"
            "- Conversational WhatsApp tone\n"
            "- No emojis unless appropriate\n"
            "- Reply directly, don't explain what you're doing\n"
            "Just write the reply text, nothing else."
        )

        resp  = client.chat.completions.create(
            model=GROQ_MODEL_PRIMARY or "llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150,
            temperature=0.7,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        print(f"[WA] draft_reply error: {e}")
        return ""


def summarise_messages(messages: list[dict]) -> str:
    """Use Groq to summarise a batch of WhatsApp messages."""
    if not messages:
        return "No messages to summarise."
    try:
        from groq import Groq
        from config import GROQ_API_KEY, GROQ_MODEL_PRIMARY

        client = Groq(api_key=GROQ_API_KEY)
        texts  = []
        for m in messages[:30]:
            name  = m.get("fromName") or m.get("from", "?")
            group = f"[{m['groupName']}] " if m.get("isGroup") else ""
            texts.append(f"{group}{name}: {m.get('body','')[:100]}")

        prompt = (
            "Summarise these WhatsApp messages concisely. "
            "Group by conversation. Highlight anything urgent or requiring action.\n\n"
            + "\n".join(texts)
        )
        resp = client.chat.completions.create(
            model=GROQ_MODEL_PRIMARY or "llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
            temperature=0.3,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        return f"Summary unavailable: {e}"


# ─────────────────────────────────────────────
# FORMAT HELPERS
# ─────────────────────────────────────────────

def format_messages_summary(messages: list[dict], limit: int = 10) -> str:
    if not messages:
        return "No messages found."
    lines = []
    for m in messages[:limit]:
        name   = m.get("fromName") or m.get("from", "?")
        body   = m.get("body", "")[:80]
        ts     = m.get("timestamp", "")[:16].replace("T", " ")
        group  = f"[{m['groupName']}] " if m.get("isGroup") else ""
        unread = "🔵 " if not m.get("read") else ""
        lines.append(f"{unread}{group}*{name}* _{ts}_\n{body}")
    return "\n\n".join(lines)