"""
ORA Learning Engine — Makes ORA smarter over time.
"""

import os
import re
import json
import time
from datetime import datetime
from database import get_conn, close_conn
from groq import Groq

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
_last_extract: float = 0
_EXTRACT_DEBOUNCE = 60


# ─────────────────────────────────────────────
# SCHEMA INIT
# ─────────────────────────────────────────────
def init_learning_tables() -> None:
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS learned_facts (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            category  TEXT NOT NULL,
            subject   TEXT NOT NULL,
            predicate TEXT NOT NULL,
            object    TEXT NOT NULL,
            confidence REAL DEFAULT 0.7,
            source    TEXT DEFAULT 'conversation',
            verified  INTEGER DEFAULT 0,
            created_at TEXT,
            updated_at TEXT
        )
    """)

    c.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_learned_facts
        ON learned_facts(category, subject, predicate)
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS corrections (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            original_query TEXT,
            ora_response   TEXT,
            correction     TEXT,
            timestamp      TEXT
        )
    """)

    columns = {row[1] for row in c.execute("PRAGMA table_info(learned_facts)").fetchall()}
    migrations = {
        "status": "TEXT DEFAULT 'candidate'",
        "confirmed_at": "TEXT DEFAULT NULL",
        "expires_at": "TEXT DEFAULT NULL",
    }
    for name, definition in migrations.items():
        if name not in columns:
            c.execute(f"ALTER TABLE learned_facts ADD COLUMN {name} {definition}")

    conn.commit()
    close_conn()
    print("[Learning] Tables initialized")


# ─────────────────────────────────────────────
# FACT STORAGE
# ─────────────────────────────────────────────
def store_fact(category: str, subject: str, predicate: str, obj: str,
               confidence: float = 0.7, source: str = "conversation",
               status: str = "candidate") -> int:
    """Store a candidate without overwriting a user-confirmed fact."""
    if status not in {"candidate", "confirmed", "verified", "rejected"}:
        raise ValueError(f"invalid memory status: {status}")
    conn = get_conn()
    c = conn.cursor()
    now = datetime.now().isoformat()
    existing = c.execute(
        "SELECT id, status FROM learned_facts WHERE category=? AND subject=? AND predicate=?",
        (category, subject, predicate),
    ).fetchone()
    if existing and existing[1] in {"confirmed", "verified"} and status == "candidate":
        close_conn()
        return existing[0]
    if existing:
        c.execute("""UPDATE learned_facts SET object=?, confidence=?, source=?,
                   status=?, verified=?, updated_at=? WHERE id=?""",
                  (obj, confidence, source, status, int(status in {"confirmed", "verified"}), now, existing[0]))
        fact_id = existing[0]
    else:
        c.execute("""INSERT INTO learned_facts
            (category, subject, predicate, object, confidence, source, status,
             verified, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (category, subject, predicate, obj, confidence, source, status,
             int(status in {"confirmed", "verified"}), now, now))
        fact_id = c.lastrowid
    conn.commit()
    close_conn()
    return int(fact_id or 0)


def get_learned_facts(category: str | None = None, status: str | None = None,
                      limit: int = 30) -> list[dict]:
    conn = get_conn()
    c = conn.cursor()
    filters = []
    params: list = []
    if category:
        filters.append("category=?")
        params.append(category)
    if status:
        filters.append("status=?")
        params.append(status)
    where = " WHERE " + " AND ".join(filters) if filters else ""
    params.append(min(limit, 200))
    c.execute(f"""
        SELECT id, category, subject, predicate, object, confidence,
               status, source, verified, created_at, updated_at, confirmed_at, expires_at
        FROM learned_facts{where}
        ORDER BY confidence DESC, updated_at DESC LIMIT ?
    """, params)
    rows = c.fetchall()
    close_conn()
    return [
        {"id": r[0], "category": r[1], "subject": r[2], "predicate": r[3],
         "object": r[4], "confidence": r[5], "status": r[6], "source": r[7],
         "verified": bool(r[8]), "created_at": r[9], "updated_at": r[10],
         "confirmed_at": r[11], "expires_at": r[12]}
        for r in rows
    ]


def confirm_fact(fact_id: int) -> bool:
    conn = get_conn()
    cur = conn.execute("""UPDATE learned_facts SET status='confirmed', verified=1,
                         confirmed_at=?, updated_at=? WHERE id=?""",
                       (datetime.now().isoformat(), datetime.now().isoformat(), fact_id))
    conn.commit()
    close_conn()
    return cur.rowcount > 0


def reject_fact(fact_id: int) -> bool:
    conn = get_conn()
    cur = conn.execute("UPDATE learned_facts SET status='rejected', updated_at=? WHERE id=?",
                       (datetime.now().isoformat(), fact_id))
    conn.commit()
    close_conn()
    return cur.rowcount > 0


def update_fact(fact_id: int, obj: str | None = None, confidence: float | None = None) -> bool:
    updates = []
    params = []
    if obj is not None:
        updates.append("object=?")
        params.append(obj.strip())
    if confidence is not None:
        updates.append("confidence=?")
        params.append(max(0.0, min(1.0, confidence)))
    if not updates:
        return False
    updates.append("status='candidate'")
    updates.append("verified=0")
    updates.append("updated_at=?")
    params.extend([datetime.now().isoformat(), fact_id])
    conn = get_conn()
    cur = conn.execute(f"UPDATE learned_facts SET {', '.join(updates)} WHERE id=?", params)
    conn.commit()
    close_conn()
    return cur.rowcount > 0


def forget_fact(fact_id: int) -> bool:
    conn = get_conn()
    cur = conn.execute("DELETE FROM learned_facts WHERE id=?", (fact_id,))
    conn.commit()
    close_conn()
    return cur.rowcount > 0


def get_facts_as_context(limit: int = 20) -> str:
    facts = get_learned_facts(status="confirmed", limit=limit)
    if not facts:
        return ""
    return "\n".join(f"- {f['subject']} {f['predicate']}: {f['object']}" for f in facts)


# ─────────────────────────────────────────────
# CORRECTION DETECTION
# ─────────────────────────────────────────────
_CORRECTION_PATTERNS = re.compile(
    r"\b(no(,| that'?s)?|wrong|incorrect|not right|actually|that'?s not|"
    r"you'?re wrong|that'?s wrong|fix that|stop saying|don'?t say)\b",
    re.IGNORECASE
)


def detect_correction(user_text: str) -> bool:
    return bool(_CORRECTION_PATTERNS.search(user_text))


def log_correction(query: str, ora_response: str, correction_text: str) -> None:
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO corrections (original_query, ora_response, correction, timestamp)
        VALUES (?, ?, ?, ?)
    """, (query, ora_response, correction_text, datetime.now().isoformat()))
    conn.commit()
    close_conn()
    print("[Learning] Correction logged")


# ─────────────────────────────────────────────
# AI EXTRACTION (debounced)
# ─────────────────────────────────────────────
def extract_facts_from_exchange(user_text: str, ora_response: str) -> None:
    global _last_extract

    if not GROQ_API_KEY:
        return
    if len(user_text.split()) < 10:
        return
    if time.time() - _last_extract < _EXTRACT_DEBOUNCE:
        return

    _last_extract = time.time()

    client = Groq(api_key=GROQ_API_KEY)

    prompt = (
        f"Extract factual information about the user (Elisha) from this conversation.\n"
        f"Output ONLY a JSON array. Each item: category, subject, predicate, object, confidence.\n"
        f"Categories: preference, work, personal, goal, habit, relationship, technical.\n"
        f"Max 5 facts. If nothing useful, return [].\n\n"
        f"User: {user_text[:500]}\n"
        f"ORA: {ora_response[:300]}\n\n"
        f"JSON array only:"
    )

    try:
        resp = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.2,
        )
        raw_content = resp.choices[0].message.content
        raw = raw_content.strip() if raw_content else ""
        if not raw:
            return

        match = re.search(r'\[.*?\]', raw, re.DOTALL)
        if not match:
            return
        facts = json.loads(match.group())
        for fact in facts[:5]:
            if all(k in fact for k in ("category", "subject", "predicate", "object")):
                store_fact(
                    category=fact["category"],
                    subject=fact["subject"],
                    predicate=fact["predicate"],
                    obj=fact["object"],
                    confidence=float(fact.get("confidence", 0.7)),
                    source="conversation"
                )
        if facts:
            print(f"[Learning] Extracted {len(facts)} facts")
    except Exception as e:
        print(f"[Learning] Extraction failed: {e}")


# ─────────────────────────────────────────────
# RULE-BASED EXTRACTION (zero AI cost)
# ─────────────────────────────────────────────
_EXPLICIT_PATTERNS = [
    (re.compile(r"i prefer (.+)", re.I),
     lambda m: ("preference", "Elisha", "prefers", m.group(1)[:80])),
    (re.compile(r"i use (.+?) for (.+)", re.I),
     lambda m: ("technical", "Elisha", f"uses {m.group(1)} for", m.group(2)[:80])),
    (re.compile(r"i work (?:at|on|with) (.+)", re.I),
     lambda m: ("work", "Elisha", "works on", m.group(1)[:80])),
    (re.compile(r"my (\w+) is (.+)", re.I),
     lambda m: ("personal", "Elisha", f"{m.group(1)} is", m.group(2)[:80])),
    (re.compile(r"i(?:'m| am) (?:working on|building|making) (.+)", re.I),
     lambda m: ("work", "Elisha", "is building", m.group(1)[:80])),
]


def extract_explicit_facts(user_text: str) -> None:
    for pattern, extractor in _EXPLICIT_PATTERNS:
        m = pattern.search(user_text)
        if m:
            try:
                cat, subj, pred, obj = extractor(m)
                store_fact(cat, subj, pred, obj, confidence=0.9, source="explicit")
            except Exception:
                pass