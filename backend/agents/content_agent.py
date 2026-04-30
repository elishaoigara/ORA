"""
ORA Content Creation Agent — Fixed & Extended
Fixes vs v1:
  - Removed broken safe_ai_call(ask_groq,...) pattern
  - Direct Groq call with platform-specific prompts
  - Added: delete_draft, regenerate_draft, search_drafts, get_draft_by_id
  - Added: analytics, word_count, char_count, platform field
"""
from __future__ import annotations
import json, os
from datetime import datetime
from typing import Optional

from groq import Groq
from config import GROQ_API_KEY, GROQ_MODEL_PRIMARY, GROQ_MODEL_FALLBACK
from database import get_conn, close_conn

_client: Optional[Groq] = None
def _groq() -> Groq:
    global _client
    if _client is None:
        _client = Groq(api_key=GROQ_API_KEY)
    return _client

def init_content_drafts_table():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS content_drafts (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            title        TEXT NOT NULL,
            content_type TEXT DEFAULT 'post',
            topic        TEXT,
            draft_text   TEXT NOT NULL,
            tone         TEXT DEFAULT 'professional',
            length       TEXT DEFAULT 'medium',
            platform     TEXT DEFAULT NULL,
            status       TEXT DEFAULT 'draft',
            word_count   INTEGER DEFAULT 0,
            char_count   INTEGER DEFAULT 0,
            version      INTEGER DEFAULT 1,
            parent_id    INTEGER DEFAULT NULL,
            created_at   TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at   TEXT DEFAULT CURRENT_TIMESTAMP,
            metadata     TEXT DEFAULT '{}'
        )
    """)
    conn.commit()
    close_conn()
    print("[CONTENT_AGENT] content_drafts table ready")

_PLATFORM_GUIDES = {
    "linkedin": "LinkedIn post (150-300 words). Hook on line 1. Short paragraphs. 3-5 hashtags at end. End with a question or CTA.",
    "twitter":  "Twitter/X thread. Format: Tweet 1 (hook ≤280 chars) then numbered tweets 2-8 (each ≤280 chars), final tweet = CTA.",
    "instagram":"Instagram caption. Hook first 2 lines. Short paragraphs. Question at end. 10-15 hashtags after a line break.",
    "email":    "Professional email. Format exactly:\nSubject: [subject line]\n\n[body with greeting, message, clear ask, sign-off]",
    "blog":     "Blog post with markdown. Include: H1 title, hook paragraph, 3-5 H2 sections, key takeaways, CTA conclusion.",
    "script":   "Video script with cues. Sections: HOOK(0-5s), INTRO(5-15s), MAIN POINTS, OUTRO+CTA. Add [B-ROLL] and [ON-SCREEN TEXT] cues.",
    "post":     "General social post. Hook first. 1-3 tight paragraphs. CTA at end.",
    "caption":  "Short caption. Max 3 sentences. Lead with the most interesting thing. 2-3 natural emojis. 3-5 hashtags.",
    "newsletter":"Newsletter section. Subject line, preview text (50 chars), personal opener, main story, 1-3 quick bullets, sign-off.",
}
_TONE_MODS = {
    "professional":  "professional, authoritative, clear",
    "casual":        "casual, warm, conversational — like a smart friend",
    "inspirational": "inspiring, motivational, forward-looking",
    "technical":     "technical precision + founder authenticity",
    "humorous":      "witty, playful, light — makes people smile",
    "storytelling":  "narrative-driven, personal, shows vulnerability + lessons",
}
_LENGTH_GUIDES = {
    "short": "Keep it SHORT: under 150 words.",
    "medium": "Use the natural full length for this format.",
    "long":   "Go LONG and comprehensive: maximum depth.",
}

def _get_persona() -> str:
    try:
        from memory.profile import get_all_profile
        p = get_all_profile()
        return f"{p.get('name','Elisha')} — {p.get('role','Software Engineer')} in {p.get('location','Nairobi, Kenya')}. Building: {p.get('goals','autonomous AI systems')}"
    except Exception:
        return "Elisha Oigara — Nairobi-based founder building ORA (autonomous AI system)"

def create_draft(topic, content_type="post", tone="professional", length="medium",
                 platform=None, extra_context="", parent_id=None):
    eff = platform or content_type
    guide = _PLATFORM_GUIDES.get(eff, _PLATFORM_GUIDES["post"])
    tone_desc = _TONE_MODS.get(tone, tone)
    len_guide = _LENGTH_GUIDES.get(length, _LENGTH_GUIDES["medium"])
    persona = _get_persona()

    system = (f"You are ORA's Content Agent for {persona}.\n"
              f"Tone: {tone_desc}\n{len_guide}\n\nPLATFORM RULES:\n{guide}\n\n"
              "Return ONLY the final content. No preamble, no meta-commentary.")
    user = f"Write a {content_type} about: {topic}"
    if extra_context.strip():
        user += f"\n\nContext:\n{extra_context[:1000]}"

    draft_text = ""
    for model in [GROQ_MODEL_PRIMARY, GROQ_MODEL_FALLBACK]:
        try:
            r = _groq().chat.completions.create(
                model=model,
                messages=[{"role":"system","content":system},{"role":"user","content":user}],
                max_tokens=2048, temperature=0.75,
            )
            draft_text = (r.choices[0].message.content or "").strip()
            break
        except Exception as e:
            print(f"[CONTENT_AGENT] {model} failed: {e}")
    if not draft_text:
        return {"status": "error", "error": "AI generation failed"}

    wc = len(draft_text.split())
    cc = len(draft_text)
    title = f"{content_type.title()}: {topic[:80]}"
    now = datetime.now().isoformat()
    conn = get_conn(); cur = conn.cursor()
    cur.execute("""
        INSERT INTO content_drafts
          (title,content_type,topic,draft_text,tone,length,platform,
           status,word_count,char_count,version,parent_id,created_at,updated_at,metadata)
        VALUES (?,?,?,?,?,?,?,'draft',?,?,1,?,?,?,'{}')
    """, (title, content_type, topic, draft_text, tone, length,
          platform or content_type, wc, cc, parent_id, now, now))
    draft_id = cur.lastrowid
    conn.commit(); close_conn()
    return {"id":draft_id,"status":"success","draft":draft_text,"title":title,
            "type":content_type,"platform":platform or content_type,"topic":topic,
            "tone":tone,"length":length,"word_count":wc,"char_count":cc,"created_at":now}

def regenerate_draft(draft_id, feedback=""):
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT topic,content_type,tone,length,platform FROM content_drafts WHERE id=?", (draft_id,))
    row = cur.fetchone(); close_conn()
    if not row:
        return {"status":"error","error":"Draft not found"}
    topic, ctype, tone, length, platform = row
    extra = f"User feedback on previous version: {feedback}" if feedback else ""
    return create_draft(topic=topic, content_type=ctype, tone=tone,
                        length=length or "medium", platform=platform,
                        extra_context=extra, parent_id=draft_id)

def get_drafts(status="all", limit=20, search=""):
    conn = get_conn(); cur = conn.cursor()
    cols = "id,title,content_type,topic,draft_text,tone,platform,status,word_count,char_count,version,created_at"
    if search.strip():
        p = f"%{search.strip()}%"
        base = f"(title LIKE ? OR topic LIKE ? OR draft_text LIKE ?)"
        args = [p, p, p]
        where = (f"WHERE status=? AND {base}", [status] + args) if status != "all" else (f"WHERE {base}", args)
    else:
        where = ("WHERE status=?", [status]) if status != "all" else ("", [])
    cur.execute(f"SELECT {cols} FROM content_drafts {where[0]} ORDER BY created_at DESC LIMIT ?",
                where[1] + [limit])
    rows = cur.fetchall(); close_conn()
    return [{"id":r[0],"title":r[1],"type":r[2],"topic":r[3],"draft":r[4],"tone":r[5],
             "platform":r[6],"status":r[7],"word_count":r[8],"char_count":r[9],
             "version":r[10],"ts":r[11]} for r in rows]

def get_draft_by_id(draft_id):
    conn = get_conn(); cur = conn.cursor()
    cur.execute("""SELECT id,title,content_type,topic,draft_text,tone,platform,
                          status,word_count,char_count,version,created_at
                   FROM content_drafts WHERE id=?""", (draft_id,))
    r = cur.fetchone(); close_conn()
    if not r:
        return None
    return {"id":r[0],"title":r[1],"type":r[2],"topic":r[3],"draft":r[4],"tone":r[5],
            "platform":r[6],"status":r[7],"word_count":r[8],"char_count":r[9],
            "version":r[10],"ts":r[11]}

def get_content_stats():
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT COUNT(*),status FROM content_drafts GROUP BY status")
    rows = cur.fetchall()
    cur.execute("SELECT COUNT(*) FROM content_drafts")
    total = cur.fetchone()[0]
    cur.execute("SELECT content_type,COUNT(*) FROM content_drafts GROUP BY content_type ORDER BY 2 DESC LIMIT 5")
    top = cur.fetchall(); close_conn()
    return {"total":total,"by_status":{r[1]:r[0] for r in rows},
            "top_types":[{"type":r[0],"count":r[1]} for r in top]}

def update_draft_status(draft_id, new_status):
    if new_status not in {"draft","approved","sent","rejected","archived"}:
        return False
    conn = get_conn(); cur = conn.cursor()
    cur.execute("UPDATE content_drafts SET status=?,updated_at=? WHERE id=?",
                (new_status, datetime.now().isoformat(), draft_id))
    conn.commit(); affected = cur.rowcount; close_conn()
    return affected > 0

def update_draft_text(draft_id, new_text):
    conn = get_conn(); cur = conn.cursor()
    cur.execute("UPDATE content_drafts SET draft_text=?,word_count=?,char_count=?,updated_at=? WHERE id=?",
                (new_text, len(new_text.split()), len(new_text), datetime.now().isoformat(), draft_id))
    conn.commit(); affected = cur.rowcount; close_conn()
    return affected > 0

def delete_draft(draft_id):
    conn = get_conn(); cur = conn.cursor()
    cur.execute("DELETE FROM content_drafts WHERE id=?", (draft_id,))
    conn.commit(); affected = cur.rowcount; close_conn()
    return affected > 0