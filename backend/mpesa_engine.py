"""
ORA M-Pesa Engine
Parses and analyzes M-Pesa SMS transaction data.
Provides spend awareness, daily aggregation, and spike alerts.
"""

import re
from datetime import datetime, timedelta
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
# SMS PARSER
# ─────────────────────────────────────────────

MPESA_PATTERNS = [
    {
        "type": "sent",
        "pattern": r"(\w+)\s+Confirmed\.\s+Ksh([\d,]+(?:\.\d+)?)\s+sent to\s+(.+?)\s+\d{10,}",
    },
    {
        "type": "received",
        "pattern": r"(\w+)\s+Confirmed\.\s+You have received\s+Ksh([\d,]+(?:\.\d+)?)\s+from\s+(.+?)\s+\d",
    },
    {
        "type": "paid",
        "pattern": r"(\w+)\s+Confirmed\.\s+Ksh([\d,]+(?:\.\d+)?)\s+paid to\s+(.+?)[\.\s]",
    },
    {
        "type": "withdrawn",
        "pattern": r"(\w+)\s+Confirmed.*?Withdraw\s+Ksh([\d,]+(?:\.\d+)?)\s+from\s+(.+?)[\.\s]",
    },
    {
        "type": "airtime",
        "pattern": r"(\w+)\s+Confirmed\.\s+Ksh([\d,]+(?:\.\d+)?)\s+airtime",
    },
]

BALANCE_PATTERN = r"balance is Ksh([\d,]+(?:\.\d+)?)"


def _clean_amount(s: str) -> float:
    return float(s.replace(",", ""))


def parse_mpesa_sms(sms: str) -> dict | None:
    sms = sms.strip()
    for p in MPESA_PATTERNS:
        m = re.search(p["pattern"], sms, re.IGNORECASE)
        if m:
            groups = m.groups()
            balance = None
            bm = re.search(BALANCE_PATTERN, sms, re.IGNORECASE)
            if bm:
                balance = _clean_amount(bm.group(1))
            return {
                "transaction_id": groups[0],
                "type": p["type"],
                "amount": _clean_amount(groups[1]),
                "party": groups[2].strip() if len(groups) > 2 else "M-Pesa",
                "balance": balance,
                "raw_sms": sms,
                "timestamp": datetime.now().isoformat()
            }
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
        return True
    except Exception as e:
        print(f"[MPESA] save error: {e}")
        return False


def ingest_sms(raw_sms: str) -> dict:
    txn = parse_mpesa_sms(raw_sms)
    if not txn:
        return {"status": "not_mpesa", "message": "SMS does not match M-Pesa format"}
    saved = save_transaction(txn)
    if not saved:
        return {"status": "duplicate", "transaction_id": txn["transaction_id"]}
    alert = check_spend_alert()
    return {"status": "saved", "transaction": txn, "alert": alert}


# ─────────────────────────────────────────────
# ANALYTICS
# ─────────────────────────────────────────────

def get_today_spend() -> dict:
    try:
        conn = get_conn()
        today = datetime.now().strftime("%Y-%m-%d")
        row = conn.execute("""
            SELECT SUM(amount), COUNT(*) FROM mpesa_transactions
            WHERE DATE(timestamp) = ? AND type IN ('sent','paid','withdrawn','airtime')
        """, (today,)).fetchone()
        return {"total": row[0] or 0, "transactions": row[1] or 0, "date": today}
    except Exception:
        return {"total": 0, "transactions": 0, "date": ""}


def get_average_daily_spend(days: int = 14) -> float:
    try:
        conn = get_conn()
        since = (datetime.now() - timedelta(days=days)).isoformat()
        row = conn.execute("""
            SELECT AVG(daily_total) FROM (
                SELECT DATE(timestamp) as day, SUM(amount) as daily_total
                FROM mpesa_transactions
                WHERE timestamp >= ? AND type IN ('sent','paid','withdrawn','airtime')
                GROUP BY day
            )
        """, (since,)).fetchone()
        return row[0] or 0
    except Exception:
        return 0


def get_daily_summary(days: int = 7) -> list:
    try:
        conn = get_conn()
        since = (datetime.now() - timedelta(days=days)).isoformat()
        rows = conn.execute("""
            SELECT DATE(timestamp) as day, type, SUM(amount) as total, COUNT(*) as count
            FROM mpesa_transactions
            WHERE timestamp >= ? AND type IN ('sent','paid','withdrawn','airtime')
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
        return [{"id": r[0], "txn_id": r[1], "type": r[2], "amount": r[3],
                 "party": r[4], "balance": r[5], "timestamp": r[6]} for r in rows]
    except Exception:
        return []


def get_recurring_patterns() -> list:
    try:
        conn = get_conn()
        rows = conn.execute("""
            SELECT party, COUNT(*) as freq, AVG(amount) as avg_amount
            FROM mpesa_transactions WHERE type IN ('sent','paid')
            GROUP BY party HAVING freq >= 2 ORDER BY freq DESC LIMIT 10
        """).fetchall()
        return [{"party": r[0], "frequency": r[1], "avg_amount": round(r[2], 2)} for r in rows]
    except Exception:
        return []


def check_spend_alert() -> dict | None:
    today = get_today_spend()
    avg = get_average_daily_spend()
    if avg > 0 and today["total"] > (avg * 3):
        return {
            "type": "spend_spike",
            "message": f"💸 Spend alert: Ksh{today['total']:,.0f} today vs Ksh{avg:,.0f} daily avg ({today['transactions']} txns)",
            "severity": "high"
        }
    return None