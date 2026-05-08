"""
ORA M-Pesa Engine — v2
Parses ALL M-Pesa SMS types: sent, received, paid, withdrawn,
airtime, deposit, reversal, loan, fuliza, and buy goods.
Much more flexible regex — handles Safaricom's inconsistent formatting.
"""

import re
from datetime import datetime, timedelta
from typing import Optional
from database import get_conn, log_alert


# ─────────────────────────────────────────────
# DB INIT
# ─────────────────────────────────────────────

def init_mpesa_table():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS mpesa_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_id TEXT UNIQUE,
            type TEXT,
            amount REAL,
            party TEXT,
            balance REAL,
            raw_sms TEXT,
            timestamp TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()


# ─────────────────────────────────────────────
# AMOUNT + BALANCE HELPERS
# ─────────────────────────────────────────────

def _amt(s: str) -> float:
    """Parse 'Ksh1,234.50' or '1234.50' → float."""
    return float(re.sub(r"[^\d.]", "", s))

def _extract_balance(sms: str) -> Optional[float]:
    m = re.search(
        r"(?:balance|M-PESA balance|new M-PESA balance)[^\d]*(?:is\s*)?Ksh\s*([\d,]+(?:\.\d+)?)",
        sms, re.IGNORECASE
    )
    return _amt(m.group(1)) if m else None

def _extract_txn_id(sms: str) -> Optional[str]:
    """Extract the transaction code like QGH1234ABC from the SMS."""
    m = re.search(r"\b([A-Z0-9]{10})\b", sms)
    return m.group(1) if m else None


# ─────────────────────────────────────────────
# PATTERN DEFINITIONS
# ─────────────────────────────────────────────
# Each pattern: (type, regex)
# Groups must be: (txn_id, amount, party) OR (txn_id, amount) for airtime

PATTERNS = [

    # ── SENT ──────────────────────────────────────────────────────────
    # "QGH1234 Confirmed. Ksh500 sent to JOHN DOE 0712345678"
    ("sent",
     r"([A-Z0-9]{8,12})\s+Confirmed[.\s]+Ksh\s*([\d,]+(?:\.\d+)?)\s+sent to\s+(.+?)\s+(?:\d{9,}|on\s)"),

    # ── RECEIVED ──────────────────────────────────────────────────────
    # "QGH1234 Confirmed. You have received Ksh200 from JANE DOE"
    ("received",
     r"([A-Z0-9]{8,12})\s+Confirmed[.\s]+You have received\s+Ksh\s*([\d,]+(?:\.\d+)?)\s+from\s+(.+?)(?:\s+on\s|\s+New|\.)"),

    # ── PAID (paybill/till) ────────────────────────────────────────────
    # "QGH1234 Confirmed. Ksh300 paid to SAFARICOM"
    # "QGH1234 Confirmed. Ksh1,200.00 paid to KPLC PREPAID"
    ("paid",
     r"([A-Z0-9]{8,12})\s+Confirmed[.\s]+Ksh\s*([\d,]+(?:\.\d+)?)\s+paid to\s+(.+?)(?:\s+on\s|\s+New|\s+Acc|\.)"),

    # ── BUY GOODS ─────────────────────────────────────────────────────
    # "QGH1234 Confirmed. Ksh150 paid to NAIVAS SUPERMARKET for account"
    ("paid",
     r"([A-Z0-9]{8,12})\s+Confirmed[.\s]+Ksh\s*([\d,]+(?:\.\d+)?)\s+paid to\s+(.+?)\s+for account"),

    # ── WITHDRAWN ─────────────────────────────────────────────────────
    # "QGH1234 Confirmed.Withdraw Ksh1,000 from 254712345678 - Agent"
    ("withdrawn",
     r"([A-Z0-9]{8,12})\s+Confirmed[.\s]+Withdraw\s+Ksh\s*([\d,]+(?:\.\d+)?)\s+from\s+(.+?)(?:\s+New|\s+M-PESA|\.)"),

    # ── AIRTIME (self) ────────────────────────────────────────────────
    # "QGH1234 Confirmed. Ksh10.00 airtime for 0712345678"
    ("airtime",
     r"([A-Z0-9]{8,12})\s+Confirmed[.\s]+Ksh\s*([\d,]+(?:\.\d+)?)\s+airtime\s+(?:for|to)\s+([\d+]+)"),

    # ── AIRTIME (simple, no recipient group) ─────────────────────────
    # "QGH1234 Confirmed. Ksh10.00 airtime"
    ("airtime",
     r"([A-Z0-9]{8,12})\s+Confirmed[.\s]+Ksh\s*([\d,]+(?:\.\d+)?)\s+airtime"),

    # ── DEPOSIT / AGENT DEPOSIT ───────────────────────────────────────
    # "QGH1234 Confirmed. Ksh500 deposited to 254712345678 by Agent"
    ("received",
     r"([A-Z0-9]{8,12})\s+Confirmed[.\s]+Ksh\s*([\d,]+(?:\.\d+)?)\s+deposited\s+(?:to\s+\S+\s+)?by\s+(.+?)(?:\s+New|\.)"),

    # ── REVERSAL ─────────────────────────────────────────────────────
    # "QGH1234 Confirmed. Ksh200 reversed to your M-PESA"
    ("received",
     r"([A-Z0-9]{8,12})\s+Confirmed[.\s]+Ksh\s*([\d,]+(?:\.\d+)?)\s+reversed"),

    # ── FULIZA / LOAN DISBURSEMENT ────────────────────────────────────
    # "QGH1234 Confirmed. You have borrowed Ksh500 from Fuliza"
    ("received",
     r"([A-Z0-9]{8,12})\s+Confirmed[.\s]+You have borrowed\s+Ksh\s*([\d,]+(?:\.\d+)?)\s+from\s+(.+?)(?:\s+New|\.)"),

    # ── FULIZA REPAYMENT ──────────────────────────────────────────────
    ("paid",
     r"([A-Z0-9]{8,12})\s+Confirmed[.\s]+Ksh\s*([\d,]+(?:\.\d+)?)\s+repaid\s+(?:to\s+)?(.+?)(?:\s+New|\.)"),

    # ── GENERIC FALLBACK — any Confirmed + Ksh + known verb ──────────
    # Catches anything not matched above
    ("transaction",
     r"([A-Z0-9]{8,12})\s+Confirmed[.\s]+(?:Ksh\s*([\d,]+(?:\.\d+)?))\s+(.{1,60})"),
]


# ─────────────────────────────────────────────
# PARSER
# ─────────────────────────────────────────────

def parse_mpesa_sms(sms: str) -> Optional[dict]:
    sms = sms.strip()

    # Must contain "Confirmed" and "Ksh" to be an M-Pesa transaction SMS
    if "Confirmed" not in sms and "confirmed" not in sms:
        return None
    if "Ksh" not in sms and "ksh" not in sms:
        return None

    balance = _extract_balance(sms)

    for txn_type, pattern in PATTERNS:
        m = re.search(pattern, sms, re.IGNORECASE | re.DOTALL)
        if not m:
            continue

        groups = m.groups()
        txn_id = groups[0] if groups else _extract_txn_id(sms) or f"TXN_{int(datetime.now().timestamp())}"

        # Amount is always group 1 (index 1)
        try:
            amount = _amt(groups[1]) if len(groups) > 1 and groups[1] else 0.0
        except (ValueError, TypeError):
            continue

        if amount <= 0:
            continue

        # Party is group 2 (index 2) if it exists
        party = "M-Pesa"
        if len(groups) > 2 and groups[2]:
            party = groups[2].strip()
            # Clean up trailing noise
            party = re.sub(r"\s+(on|New|Acc|M-PESA|\.)\s*.*$", "", party, flags=re.IGNORECASE).strip()
            party = party[:80]  # cap length

        # For airtime with no party, use own number
        if txn_type == "airtime" and party == "M-Pesa":
            m2 = re.search(r"(?:for|to)\s+([\d+]+)", sms, re.IGNORECASE)
            party = m2.group(1) if m2 else "Self"

        return {
            "transaction_id": txn_id,
            "type":           txn_type,
            "amount":         amount,
            "party":          party,
            "balance":        balance,
            "raw_sms":        sms,
            "timestamp":      datetime.now().isoformat(),
        }

    # Last resort — if it has a transaction code + Ksh but nothing matched
    txn_id = _extract_txn_id(sms)
    ksh_m  = re.search(r"Ksh\s*([\d,]+(?:\.\d+)?)", sms, re.IGNORECASE)
    if txn_id and ksh_m:
        try:
            amount = _amt(ksh_m.group(1))
            if amount > 0:
                return {
                    "transaction_id": txn_id,
                    "type":           "transaction",
                    "amount":         amount,
                    "party":          "M-Pesa",
                    "balance":        balance,
                    "raw_sms":        sms,
                    "timestamp":      datetime.now().isoformat(),
                }
        except ValueError:
            pass

    return None


# ─────────────────────────────────────────────
# STORAGE
# ─────────────────────────────────────────────

def save_transaction(txn: dict) -> bool:
    try:
        conn = get_conn()
        conn.execute("""
            INSERT OR IGNORE INTO mpesa_transactions
            (transaction_id, type, amount, party, balance, raw_sms, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (txn["transaction_id"], txn["type"], txn["amount"],
              txn["party"], txn.get("balance"), txn["raw_sms"], txn["timestamp"]))
        conn.commit()
        return conn.execute(
            "SELECT changes()"
        ).fetchone()[0] > 0
    except Exception as e:
        print(f"[MPESA] save error: {e}")
        return False


def ingest_sms(raw_sms: str) -> dict:
    print(f"[MPESA] Parsing SMS: {raw_sms[:120]}")
    txn = parse_mpesa_sms(raw_sms)
    if not txn:
        print(f"[MPESA] No pattern matched")
        return {"status": "not_mpesa", "message": "SMS does not match M-Pesa format"}
    print(f"[MPESA] Parsed: type={txn['type']} amount={txn['amount']} party={txn['party']}")
    saved = save_transaction(txn)
    if not saved:
        return {"status": "duplicate", "transaction_id": txn["transaction_id"]}
    alert = check_spend_alert()
    return {"status": "saved", "transaction": txn, "alert": alert}


# ─────────────────────────────────────────────
# ANALYTICS
# ─────────────────────────────────────────────

def get_today_spend() -> dict:
    """Money going OUT today."""
    try:
        conn  = get_conn()
        today = datetime.now().strftime("%Y-%m-%d")
        row   = conn.execute("""
            SELECT SUM(amount), COUNT(*) FROM mpesa_transactions
            WHERE DATE(timestamp) = ?
            AND type IN ('sent','paid','withdrawn','airtime','transaction')
        """, (today,)).fetchone()
        return {"total": float(row[0] or 0), "transactions": int(row[1] or 0), "date": today}
    except Exception:
        return {"total": 0.0, "transactions": 0, "date": ""}


def get_today_received() -> dict:
    """Money coming IN today."""
    try:
        conn  = get_conn()
        today = datetime.now().strftime("%Y-%m-%d")
        row   = conn.execute("""
            SELECT SUM(amount), COUNT(*) FROM mpesa_transactions
            WHERE DATE(timestamp) = ? AND type = 'received'
        """, (today,)).fetchone()
        return {"total": float(row[0] or 0), "transactions": int(row[1] or 0), "date": today}
    except Exception:
        return {"total": 0.0, "transactions": 0, "date": ""}


def get_average_daily_spend(days: int = 14) -> float:
    try:
        conn  = get_conn()
        since = (datetime.now() - timedelta(days=days)).isoformat()
        row   = conn.execute("""
            SELECT AVG(daily_total) FROM (
                SELECT DATE(timestamp) as day, SUM(amount) as daily_total
                FROM mpesa_transactions
                WHERE timestamp >= ? AND type IN ('sent','paid','withdrawn','airtime','transaction')
                GROUP BY day
            )
        """, (since,)).fetchone()
        return float(row[0]) if row[0] is not None else 0.0
    except Exception:
        return 0.0


def get_daily_summary(days: int = 7) -> list:
    try:
        conn  = get_conn()
        since = (datetime.now() - timedelta(days=days)).isoformat()
        rows  = conn.execute("""
            SELECT DATE(timestamp) as day, type, SUM(amount) as total, COUNT(*) as count
            FROM mpesa_transactions
            WHERE timestamp >= ?
            GROUP BY day, type ORDER BY day DESC
        """, (since,)).fetchall()
        return [{"day": r[0], "type": r[1], "total": r[2], "count": r[3]} for r in rows]
    except Exception:
        return []


def get_recent_transactions(limit: int = 20) -> list:
    try:
        conn = get_conn()
        rows = conn.execute("""
            SELECT id, transaction_id, type, amount, party, balance, timestamp
            FROM mpesa_transactions ORDER BY created_at DESC LIMIT ?
        """, (limit,)).fetchall()
        return [
            {
                "id":        r[0],
                "txn_id":    r[1],
                "type":      r[2],
                "amount":    r[3],
                "party":     r[4],
                "balance":   r[5],
                "timestamp": r[6],
            }
            for r in rows
        ]
    except Exception:
        return []


def get_recurring_patterns() -> list:
    try:
        conn = get_conn()
        rows = conn.execute("""
            SELECT party, COUNT(*) as freq, AVG(amount) as avg_amount, type
            FROM mpesa_transactions
            WHERE type IN ('sent','paid')
            GROUP BY party HAVING freq >= 2 ORDER BY freq DESC LIMIT 10
        """).fetchall()
        return [
            {"party": r[0], "frequency": r[1], "avg_amount": round(r[2], 2), "type": r[3]}
            for r in rows
        ]
    except Exception:
        return []


def check_spend_alert() -> Optional[dict]:
    today = get_today_spend()
    avg   = get_average_daily_spend()
    total = float(today["total"])
    if avg > 0 and total > (avg * 3):
        return {
            "type":     "spend_spike",
            "message":  f"💸 Spend alert: Ksh{total:,.0f} today vs Ksh{avg:,.0f} daily avg ({today['transactions']} txns)",
            "severity": "high",
        }
    return None