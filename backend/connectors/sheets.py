"""
ORA Google Sheets Connector

Capabilities:
  - Create new spreadsheets
  - Read any sheet (by URL or ID)
  - Write/append rows to any sheet
  - Auto-log M-Pesa transactions to a dedicated sheet
  - Auto-log weekly reviews to a dedicated sheet
  - Natural-language "put this in a spreadsheet" via create_sheet_from_prompt()

All functions return {"ok": True, ...} or {"ok": False, "error": "..."}.
Requires scope: https://www.googleapis.com/auth/spreadsheets

Sheet IDs are stored in ORA's database so the same sheets are reused
on subsequent auto-logs (no duplicate sheets created).
"""

from __future__ import annotations

import json
import re
import traceback
from datetime import datetime, timezone
from typing import Any

import requests

from connectors.google_auth import get_access_token, is_authorized

SHEETS_BASE = "https://sheets.googleapis.com/v4/spreadsheets"
DRIVE_BASE  = "https://www.googleapis.com/drive/v3"

# Sheet names used for auto-logging
MPESA_SHEET_NAME   = "M-Pesa Transactions"
REVIEW_SHEET_NAME  = "Weekly Reviews"


# ─────────────────────────────────────────────
# INTERNAL HELPERS
# ─────────────────────────────────────────────

def _headers() -> dict:
    return {
        "Authorization": f"Bearer {get_access_token()}",
        "Content-Type":  "application/json",
    }


def _get(url: str, params: dict | None = None) -> dict:
    r = requests.get(url, headers=_headers(), params=params or {}, timeout=15)
    r.raise_for_status()
    return r.json()


def _post(url: str, body: dict) -> dict:
    r = requests.post(url, headers=_headers(), json=body, timeout=15)
    r.raise_for_status()
    return r.json()


def _put(url: str, body: dict) -> dict:
    r = requests.put(url, headers=_headers(), json=body, timeout=15)
    r.raise_for_status()
    return r.json()


def _extract_sheet_id(url_or_id: str) -> str:
    """Accept a full Google Sheets URL or a bare spreadsheet ID."""
    m = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", url_or_id)
    return m.group(1) if m else url_or_id.strip()


def _now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


# ─────────────────────────────────────────────
# DB HELPERS  (store sheet IDs so we reuse them)
# ─────────────────────────────────────────────

def _db_get_sheet_id(key: str) -> str | None:
    try:
        from database import get_conn, close_conn
        conn = get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ora_sheets (
                key        TEXT PRIMARY KEY,
                sheet_id   TEXT NOT NULL,
                sheet_url  TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.commit()
        row = conn.execute(
            "SELECT sheet_id FROM ora_sheets WHERE key = ?", (key,)
        ).fetchone()
        close_conn()
        return row[0] if row else None
    except Exception as e:
        print(f"[SHEETS DB] get error: {e}")
        return None


def _db_save_sheet_id(key: str, sheet_id: str, url: str) -> None:
    try:
        from database import get_conn, close_conn
        conn = get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ora_sheets (
                key        TEXT PRIMARY KEY,
                sheet_id   TEXT NOT NULL,
                sheet_url  TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute(
            "INSERT OR REPLACE INTO ora_sheets (key, sheet_id, sheet_url) VALUES (?, ?, ?)",
            (key, sheet_id, url),
        )
        conn.commit()
        close_conn()
    except Exception as e:
        print(f"[SHEETS DB] save error: {e}")


# ─────────────────────────────────────────────
# CORE FUNCTIONS
# ─────────────────────────────────────────────

def create_spreadsheet(
    title:  str,
    sheets: list[str] | None = None,
) -> dict:
    """
    Create a new Google Spreadsheet.

    Args:
        title:  The spreadsheet title
        sheets: List of tab names. Defaults to ["Sheet1"]

    Returns:
        {"ok": True, "id": "...", "url": "...", "title": "..."}
    """
    if not is_authorized():
        return {"ok": False, "error": "Google not authorized — visit /api/auth/google"}
    try:
        sheet_tabs = sheets or ["Sheet1"]
        body: dict = {
            "properties": {"title": title},
            "sheets": [
                {"properties": {"title": tab, "index": i}}
                for i, tab in enumerate(sheet_tabs)
            ],
        }
        result = _post(SHEETS_BASE, body)
        sid    = result["spreadsheetId"]
        url    = result.get("spreadsheetUrl", f"https://docs.google.com/spreadsheets/d/{sid}")
        print(f"[SHEETS] Created: {title} ({sid})")
        return {"ok": True, "id": sid, "url": url, "title": title}
    except Exception as e:
        print(f"[SHEETS] create error: {e}")
        return {"ok": False, "error": str(e)}


def read_sheet(
    url_or_id: str,
    tab:       str = "Sheet1",
    range_a1:  str = "",
) -> dict:
    """
    Read data from a spreadsheet.

    Args:
        url_or_id: Full Google Sheets URL or spreadsheet ID
        tab:       Sheet tab name (default "Sheet1")
        range_a1:  Optional A1 range like "A1:D20". If empty, reads the whole tab.

    Returns:
        {"ok": True, "values": [[row], [row], ...], "rows": int, "cols": int}
    """
    if not is_authorized():
        return {"ok": False, "error": "Google not authorized"}
    try:
        sid   = _extract_sheet_id(url_or_id)
        rng   = f"{tab}!{range_a1}" if range_a1 else tab
        data  = _get(f"{SHEETS_BASE}/{sid}/values/{rng}")
        values = data.get("values", [])
        return {
            "ok":     True,
            "values": values,
            "rows":   len(values),
            "cols":   max((len(r) for r in values), default=0),
        }
    except Exception as e:
        print(f"[SHEETS] read error: {e}")
        return {"ok": False, "error": str(e)}


def write_rows(
    url_or_id: str,
    rows:      list[list[Any]],
    tab:       str  = "Sheet1",
    start_cell: str = "A1",
    clear_first: bool = False,
) -> dict:
    """
    Write rows to a spreadsheet (overwrites from start_cell).

    Args:
        url_or_id:   Spreadsheet URL or ID
        rows:        List of rows, each row is a list of values
        tab:         Sheet tab name
        start_cell:  Top-left cell to start writing (default A1)
        clear_first: If True, clear the tab before writing

    Returns:
        {"ok": True, "updated_cells": N}
    """
    if not is_authorized():
        return {"ok": False, "error": "Google not authorized"}
    try:
        sid = _extract_sheet_id(url_or_id)
        rng = f"{tab}!{start_cell}"

        if clear_first:
            requests.post(
                f"{SHEETS_BASE}/{sid}/values/{tab}:clear",
                headers=_headers(), timeout=10,
            )

        body = {
            "values":          [[str(v) for v in row] for row in rows],
            "majorDimension":  "ROWS",
        }
        result = _put(
            f"{SHEETS_BASE}/{sid}/values/{rng}?valueInputOption=USER_ENTERED",
            body,
        )
        cells = result.get("updatedCells", 0)
        print(f"[SHEETS] Wrote {cells} cells to {sid} tab={tab}")
        return {"ok": True, "updated_cells": cells}
    except Exception as e:
        print(f"[SHEETS] write error: {e}")
        return {"ok": False, "error": str(e)}


def append_rows(
    url_or_id: str,
    rows:      list[list[Any]],
    tab:       str = "Sheet1",
) -> dict:
    """
    Append rows to the next empty row in a spreadsheet.

    Args:
        url_or_id: Spreadsheet URL or ID
        rows:      List of rows to append
        tab:       Sheet tab name

    Returns:
        {"ok": True, "appended_rows": N}
    """
    if not is_authorized():
        return {"ok": False, "error": "Google not authorized"}
    try:
        sid  = _extract_sheet_id(url_or_id)
        body = {
            "values":         [[str(v) for v in row] for row in rows],
            "majorDimension": "ROWS",
        }
        result = _post(
            f"{SHEETS_BASE}/{sid}/values/{tab}:append?valueInputOption=USER_ENTERED&insertDataOption=INSERT_ROWS",
            body,
        )
        appended = result.get("updates", {}).get("updatedRows", len(rows))
        print(f"[SHEETS] Appended {appended} rows to {sid} tab={tab}")
        return {"ok": True, "appended_rows": appended}
    except Exception as e:
        print(f"[SHEETS] append error: {e}")
        return {"ok": False, "error": str(e)}


def add_sheet_tab(url_or_id: str, tab_name: str) -> dict:
    """Add a new tab to an existing spreadsheet."""
    if not is_authorized():
        return {"ok": False, "error": "Google not authorized"}
    try:
        sid  = _extract_sheet_id(url_or_id)
        body = {
            "requests": [{
                "addSheet": {
                    "properties": {"title": tab_name}
                }
            }]
        }
        _post(f"{SHEETS_BASE}/{sid}:batchUpdate", body)
        return {"ok": True, "tab": tab_name}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ─────────────────────────────────────────────
# NATURAL LANGUAGE SHEET CREATION
# ─────────────────────────────────────────────

def create_sheet_from_prompt(natural_text: str) -> dict:
    """
    Parse a natural-language request and create a spreadsheet with data.

    Examples:
      "Make a spreadsheet of my top 5 Kenyan banks with columns: Bank, HQ, Founded, Market Cap"
      "Create a sheet tracking my monthly expenses with columns: Date, Category, Amount, Notes"
      "Put this in a sheet: Name | Age | City — Elisha | 25 | Nairobi, John | 30 | Mombasa"

    Returns:
        {"ok": True, "id": ..., "url": ..., "title": ..., "rows_written": N}
    """
    if not is_authorized():
        return {"ok": False, "error": "Google not authorized"}
    try:
        from ai_brain import ask_groq

        prompt = f"""The user wants to create a Google Spreadsheet. Their request:
"{natural_text}"

Respond ONLY with a valid JSON object — no markdown, no explanation:
{{
  "title": "spreadsheet title",
  "tab":   "sheet tab name",
  "headers": ["Column1", "Column2", "Column3"],
  "rows": [
    ["value1", "value2", "value3"],
    ["value1", "value2", "value3"]
  ]
}}

Rules:
- Infer a sensible title and tab name from the request
- If the user provided data, extract it into rows
- If the user only described structure (no data), rows = []
- Headers must always be present
- All values must be strings
- Max 50 rows"""

        raw = ask_groq(prompt)
        if isinstance(raw, dict):
            text = raw.get("reply") or raw.get("raw") or raw.get("text") or str(raw)
        else:
            text = str(raw)

        text   = re.sub(r"```(?:json)?|```", "", text).strip()
        parsed = json.loads(text)

        title   = parsed.get("title", "ORA Sheet")
        tab     = parsed.get("tab",   "Sheet1")
        headers = parsed.get("headers", [])
        rows    = parsed.get("rows",    [])

        # Create the spreadsheet
        result = create_spreadsheet(title=title, sheets=[tab])
        if not result.get("ok"):
            return result

        sid = result["id"]
        url = result["url"]

        # Write headers + data
        all_rows = ([headers] if headers else []) + rows
        if all_rows:
            write_rows(sid, all_rows, tab=tab, start_cell="A1")

        rows_written = len(all_rows)
        return {
            "ok":          True,
            "id":          sid,
            "url":         url,
            "title":       title,
            "rows_written": rows_written,
            "message":     f"✅ Created **{title}** with {rows_written} row(s). [Open sheet]({url})",
        }

    except json.JSONDecodeError:
        return {"ok": False, "error": "Could not parse sheet structure from request"}
    except Exception as e:
        print(f"[SHEETS] create_from_prompt error: {e}\n{traceback.format_exc()}")
        return {"ok": False, "error": str(e)}


# ─────────────────────────────────────────────
# AUTO-LOG: M-PESA TRANSACTIONS
# ─────────────────────────────────────────────

MPESA_HEADERS = [
    "Date", "Time", "Transaction ID", "Type",
    "Amount (Ksh)", "Party", "Balance (Ksh)", "Raw SMS",
]


def _get_or_create_mpesa_sheet() -> str | None:
    """Return the M-Pesa sheet ID, creating it if needed."""
    key = "mpesa_transactions_sheet"
    sid = _db_get_sheet_id(key)
    if sid:
        return sid

    result = create_spreadsheet(
        title  = "ORA — M-Pesa Transactions",
        sheets = [MPESA_SHEET_NAME],
    )
    if not result.get("ok"):
        print(f"[SHEETS] Could not create M-Pesa sheet: {result.get('error')}")
        return None

    sid = result["id"]
    url = result["url"]
    _db_save_sheet_id(key, sid, url)

    # Write header row
    write_rows(sid, [MPESA_HEADERS], tab=MPESA_SHEET_NAME)
    print(f"[SHEETS] M-Pesa sheet created: {url}")
    return sid


def log_mpesa_transaction(txn: dict) -> dict:
    """
    Append a single M-Pesa transaction to the ORA M-Pesa sheet.
    Called automatically from mpesa_engine.ingest_sms() after a successful parse.

    txn dict keys: transaction_id, type, amount, party, balance, raw_sms, timestamp
    """
    if not is_authorized():
        return {"ok": False, "error": "Google not authorized"}
    try:
        sid = _get_or_create_mpesa_sheet()
        if not sid:
            return {"ok": False, "error": "Could not get M-Pesa sheet"}

        ts  = txn.get("timestamp", _now_str())
        try:
            dt   = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            date = dt.strftime("%Y-%m-%d")
            time = dt.strftime("%H:%M:%S")
        except Exception:
            date = ts[:10] if len(ts) >= 10 else ts
            time = ts[11:19] if len(ts) >= 19 else ""

        row = [
            date,
            time,
            txn.get("transaction_id", ""),
            txn.get("type", ""),
            txn.get("amount", ""),
            txn.get("party", ""),
            txn.get("balance", ""),
            (txn.get("raw_sms", "") or "")[:200],
        ]
        return append_rows(sid, [row], tab=MPESA_SHEET_NAME)

    except Exception as e:
        print(f"[SHEETS] log_mpesa error: {e}")
        return {"ok": False, "error": str(e)}


def sync_mpesa_history(days: int = 30) -> dict:
    """
    Bulk-sync recent M-Pesa transactions from ORA's SQLite DB to the sheet.
    Useful for the first-time setup or after a gap.
    """
    if not is_authorized():
        return {"ok": False, "error": "Google not authorized"}
    try:
        from mpesa_engine import get_recent_transactions
        from database import get_conn, close_conn

        conn = get_conn()
        rows_raw = conn.execute(f"""
            SELECT transaction_id, type, amount, party, balance, raw_sms, timestamp
            FROM mpesa_transactions
            WHERE timestamp >= datetime('now', '-{days} days')
            ORDER BY timestamp ASC
        """).fetchall()
        close_conn()

        if not rows_raw:
            return {"ok": True, "synced": 0, "message": "No transactions in the last 30 days"}

        sid = _get_or_create_mpesa_sheet()
        if not sid:
            return {"ok": False, "error": "Could not get M-Pesa sheet"}

        # Clear and rewrite with headers + all data
        all_rows = [MPESA_HEADERS]
        for r in rows_raw:
            txn_id, typ, amount, party, balance, raw_sms, ts = r
            try:
                dt   = datetime.fromisoformat((ts or "").replace("Z", "+00:00"))
                date = dt.strftime("%Y-%m-%d")
                time = dt.strftime("%H:%M:%S")
            except Exception:
                date = (ts or "")[:10]
                time = (ts or "")[11:19]
            all_rows.append([
                date, time, txn_id or "", typ or "", amount or "",
                party or "", balance or "", (raw_sms or "")[:200],
            ])

        result = write_rows(sid, all_rows, tab=MPESA_SHEET_NAME, clear_first=True)
        url    = f"https://docs.google.com/spreadsheets/d/{sid}"
        synced = len(all_rows) - 1  # exclude header
        return {
            **result,
            "synced":  synced,
            "url":     url,
            "message": f"✅ Synced {synced} M-Pesa transactions to Google Sheets. [Open sheet]({url})",
        }

    except Exception as e:
        print(f"[SHEETS] sync_mpesa error: {e}\n{traceback.format_exc()}")
        return {"ok": False, "error": str(e)}


# ─────────────────────────────────────────────
# AUTO-LOG: WEEKLY REVIEWS
# ─────────────────────────────────────────────

REVIEW_HEADERS = [
    "Week Ending", "Goals Progress", "M-Pesa Spend (Ksh)",
    "M-Pesa Received (Ksh)", "Top Transactions", "Key Events",
    "Notes", "Created At",
]


def _get_or_create_review_sheet() -> str | None:
    key = "weekly_review_sheet"
    sid = _db_get_sheet_id(key)
    if sid:
        return sid

    result = create_spreadsheet(
        title  = "ORA — Weekly Reviews",
        sheets = [REVIEW_SHEET_NAME],
    )
    if not result.get("ok"):
        return None

    sid = result["id"]
    url = result["url"]
    _db_save_sheet_id(key, sid, url)
    write_rows(sid, [REVIEW_HEADERS], tab=REVIEW_SHEET_NAME)
    print(f"[SHEETS] Weekly review sheet created: {url}")
    return sid


def log_weekly_review(review_data: dict) -> dict:
    """
    Append a weekly review entry to the ORA Weekly Reviews sheet.

    review_data keys:
        week_ending       str  e.g. "2026-05-17"
        goals_progress    str  summary of goal progress
        spend_total       float
        received_total    float
        top_transactions  str  e.g. "Rent 15000, Groceries 3200"
        key_events        str  calendar highlights
        notes             str  free-form notes
    """
    if not is_authorized():
        return {"ok": False, "error": "Google not authorized"}
    try:
        sid = _get_or_create_review_sheet()
        if not sid:
            return {"ok": False, "error": "Could not get review sheet"}

        row = [
            review_data.get("week_ending", _now_str()[:10]),
            review_data.get("goals_progress", ""),
            review_data.get("spend_total", ""),
            review_data.get("received_total", ""),
            review_data.get("top_transactions", ""),
            review_data.get("key_events", ""),
            review_data.get("notes", ""),
            _now_str(),
        ]
        result = append_rows(sid, [row], tab=REVIEW_SHEET_NAME)
        url    = f"https://docs.google.com/spreadsheets/d/{sid}"
        return {**result, "url": url,
                "message": f"✅ Weekly review logged to Google Sheets. [Open]({url})"}

    except Exception as e:
        print(f"[SHEETS] log_review error: {e}")
        return {"ok": False, "error": str(e)}


print("[SHEETS] Google Sheets connector loaded")