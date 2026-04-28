"""
ORA Research Agent — Highly Analytical Intelligence Layer
=========================================================
Capabilities:
  - Deep document analysis (PDF, DOCX, TXT, MD)
  - Multi-source research synthesis
  - Essay & long-form writing
  - Structured report generation
  - Web-aware research via RSS knowledge base
  - Citation tracking
  - Iterative deep-dive with follow-up reasoning
  - PPTX outline generation (structured JSON for slide renderer)

Design:
  - Uses Groq llama-3.3-70b-versatile for all heavy reasoning
  - Falls back to llama-3.1-8b-instant for fast tasks
  - All outputs stored in research_sessions table
  - Fully integrated with ORA knowledge base (FTS5)
  - Posts key findings to Telegram
"""

from __future__ import annotations

import json
import traceback
import hashlib
from datetime import datetime
from typing import Optional


# ─────────────────────────────────────────────────────────────────
# GROQ CLIENT (reuse ORA's existing client pattern)
# ─────────────────────────────────────────────────────────────────

def _get_client():
    import os
    from groq import Groq
    key = os.getenv("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY not set")
    return Groq(api_key=key)


def _call_groq(messages: list, model: str = "llama-3.3-70b-versatile", max_tokens: int = 4096) -> str:
    client = _get_client()
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=0.3,
    )
    return response.choices[0].message.content or ""


# ─────────────────────────────────────────────────────────────────
# DATABASE — Research Sessions
# ─────────────────────────────────────────────────────────────────

def init_research_tables():
    """Initialize research-specific tables in ORA's main DB."""
    import sqlite3
    from config import DB_PATH

    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS research_sessions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  TEXT UNIQUE NOT NULL,
            title       TEXT NOT NULL,
            query       TEXT NOT NULL,
            mode        TEXT DEFAULT 'analyze',
            status      TEXT DEFAULT 'pending',
            result      TEXT,
            sources     TEXT DEFAULT '[]',
            citations   TEXT DEFAULT '[]',
            word_count  INTEGER DEFAULT 0,
            created_at  TEXT DEFAULT (datetime('now')),
            updated_at  TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS research_documents (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  TEXT NOT NULL,
            filename    TEXT NOT NULL,
            doc_type    TEXT,
            page_count  INTEGER DEFAULT 0,
            summary     TEXT,
            key_points  TEXT DEFAULT '[]',
            indexed_at  TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()
    print("[Research] Tables initialized")


def _new_session_id(query: str) -> str:
    ts = datetime.now().isoformat()
    return hashlib.md5(f"{query}{ts}".encode()).hexdigest()[:12]


def _save_session(session_id: str, title: str, query: str, mode: str,
                  status: str, result: str, sources: list, citations: list, word_count: int):
    import sqlite3
    from config import DB_PATH
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO research_sessions
            (session_id, title, query, mode, status, result, sources, citations, word_count)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(session_id) DO UPDATE SET
            status=excluded.status,
            result=excluded.result,
            sources=excluded.sources,
            citations=excluded.citations,
            word_count=excluded.word_count,
            updated_at=datetime('now')
    """, (session_id, title, query, mode, status, result,
          json.dumps(sources), json.dumps(citations), word_count))
    conn.commit()
    conn.close()


def get_sessions(limit: int = 20) -> list:
    import sqlite3
    from config import DB_PATH
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT session_id, title, query, mode, status, word_count, created_at FROM research_sessions ORDER BY created_at DESC LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()
    return [{"session_id": r[0], "title": r[1], "query": r[2], "mode": r[3],
             "status": r[4], "word_count": r[5], "created_at": r[6]} for r in rows]


def get_session(session_id: str) -> Optional[dict]:
    import sqlite3
    from config import DB_PATH
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT session_id, title, query, mode, status, result, sources, citations, word_count, created_at FROM research_sessions WHERE session_id=?",
        (session_id,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    return {
        "session_id": row[0], "title": row[1], "query": row[2], "mode": row[3],
        "status": row[4], "result": row[5],
        "sources": json.loads(row[6] or "[]"),
        "citations": json.loads(row[7] or "[]"),
        "word_count": row[8], "created_at": row[9]
    }


def delete_session(session_id: str):
    import sqlite3
    from config import DB_PATH
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM research_sessions WHERE session_id=?", (session_id,))
    conn.commit()
    conn.close()


# ─────────────────────────────────────────────────────────────────
# KNOWLEDGE BASE RETRIEVAL (ORA's existing pipeline)
# ─────────────────────────────────────────────────────────────────

def _retrieve_from_kb(query: str, n: int = 8) -> tuple[str, list]:
    """Pull relevant chunks from ORA's knowledge base."""
    try:
        from knowledge.retrieval import retrieve, format_context
        chunks = retrieve(query, n_results=n)
        if not chunks:
            return "", []
        sources = list({c.get("source", "unknown") for c in chunks})
        return format_context(chunks), sources
    except Exception as e:
        print(f"[Research] KB retrieval failed: {e}")
        return "", []


def _retrieve_rss(query: str) -> str:
    """Pull relevant RSS-ingested news from knowledge base."""
    try:
        from knowledge.retrieval import retrieve, format_context
        chunks = retrieve(query, n_results=4)
        rss_chunks = [c for c in chunks if c.get("doc_type") == "rss" or "rss" in c.get("tags", "")]
        if rss_chunks:
            return format_context(rss_chunks)
        return ""
    except Exception:
        return ""


# ─────────────────────────────────────────────────────────────────
# CORE ANALYSIS MODES
# ─────────────────────────────────────────────────────────────────

def analyze_document(query: str, filename: str, full_text: str) -> dict:
    """
    Deep analytical reading of a single document.
    Returns structured analysis with key points, themes, critique.
    """
    session_id = _new_session_id(f"analyze:{filename}:{query}")

    system = """You are ORA's Research Agent — an expert analytical intelligence.
You read documents with the precision of a scholar and the clarity of a great teacher.

When analyzing a document:
1. Extract and synthesize the CORE ARGUMENT or main thesis
2. Identify KEY FINDINGS with specific evidence
3. Map CONCEPTUAL STRUCTURE (how ideas connect)
4. Note GAPS, assumptions, or weaknesses
5. Draw IMPLICATIONS for the user's query

Use clear section headers. Be specific — cite page numbers or sections when possible.
Write in flowing analytical prose, not just bullet lists.
Length: comprehensive but efficient (600-1200 words)."""

    context_snippet = full_text[:6000] if len(full_text) > 6000 else full_text

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"""Document: {filename}

Content:
{context_snippet}

Research Question / Focus: {query}

Provide a deep analytical breakdown of this document."""}
    ]

    try:
        result = _call_groq(messages, max_tokens=2000)
        word_count = len(result.split())

        title = f"Analysis: {filename}"
        _save_session(session_id, title, query, "analyze", "complete",
                      result, [filename], [], word_count)

        # Notify Telegram
        _notify(f"📄 Research Complete: {title}\n{word_count} words generated")

        return {"session_id": session_id, "title": title, "result": result,
                "word_count": word_count, "status": "complete"}

    except Exception as e:
        print(f"[Research] analyze_document failed: {e}")
        return {"session_id": session_id, "status": "error", "error": str(e)}


def deep_research(query: str, n_sources: int = 8) -> dict:
    """
    Multi-source research synthesis.
    Pulls from ORA's entire knowledge base and synthesizes a research brief.
    """
    session_id = _new_session_id(f"research:{query}")

    # Step 1: Retrieve relevant chunks
    kb_context, sources = _retrieve_from_kb(query, n=n_sources)
    rss_context = _retrieve_rss(query)

    combined_context = ""
    if kb_context:
        combined_context += f"## Knowledge Base\n{kb_context}\n\n"
    if rss_context:
        combined_context += f"## Recent News & Articles\n{rss_context}\n\n"

    has_context = bool(combined_context.strip())

    system = """You are ORA's Research Agent — a world-class research synthesizer.
Your job is to produce research briefs that are:
- ANALYTICAL: draw non-obvious connections
- EVIDENCE-BASED: ground every claim in sources
- STRUCTURED: clear hierarchy of ideas
- ACTIONABLE: end with concrete insights or implications

Format with clear headers (##), use numbered lists for key findings,
and cite sources inline as [Source: filename].

If no knowledge base context is provided, use your training knowledge
but clearly label sections as "[General Knowledge]"."""

    user_content = f"Research Query: {query}\n\n"
    if has_context:
        user_content += f"Available Sources:\n{combined_context}"
    else:
        user_content += "No documents in knowledge base yet. Provide research from general knowledge."

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_content}
    ]

    try:
        result = _call_groq(messages, max_tokens=3000)
        word_count = len(result.split())
        title = _generate_title(query)

        _save_session(session_id, title, query, "research", "complete",
                      result, sources, [], word_count)
        _notify(f"🔬 Research Brief: {title}\n{word_count} words | {len(sources)} sources")

        return {"session_id": session_id, "title": title, "result": result,
                "sources": sources, "word_count": word_count, "status": "complete"}

    except Exception as e:
        print(f"[Research] deep_research failed: {e}")
        return {"session_id": session_id, "status": "error", "error": str(e)}


def write_essay(topic: str, style: str = "analytical", length: str = "medium") -> dict:
    """
    Generate a structured essay or long-form piece.
    Styles: analytical, argumentative, expository, critical, comparative
    Lengths: short (400w), medium (800w), long (1500w)
    """
    session_id = _new_session_id(f"essay:{topic}")

    word_targets = {"short": 400, "medium": 800, "long": 1500}
    target = word_targets.get(length, 800)

    # Pull KB context for grounding
    kb_context, sources = _retrieve_from_kb(topic, n=6)

    style_instructions = {
        "analytical": "Analyze causes, effects, and relationships. Use evidence to build arguments layer by layer.",
        "argumentative": "Take a clear position and defend it rigorously with evidence and counterargument.",
        "expository": "Explain the topic clearly and comprehensively for an intelligent reader.",
        "critical": "Evaluate strengths and weaknesses. Challenge assumptions. Offer reasoned judgment.",
        "comparative": "Compare and contrast key ideas, approaches, or positions with nuanced balance."
    }

    style_guide = style_instructions.get(style, style_instructions["analytical"])

    system = f"""You are ORA's Research Agent writing a {style} essay.

Style guidance: {style_guide}

Target length: approximately {target} words.

Structure:
1. Hook/Opening — compelling framing of the question
2. Thesis — clear statement of your central argument
3. Body (3-4 sections) — each with a clear topic sentence, evidence, analysis
4. Counterpoint (if argumentative/critical) — steelman the opposing view
5. Conclusion — synthesis and broader implications

Write with intellectual rigor and stylistic clarity.
Use subheadings for sections. Cite sources as [Source: name] when available."""

    user_content = f"Essay Topic: {topic}\n\n"
    if kb_context:
        user_content += f"Relevant Sources from Knowledge Base:\n{kb_context}\n\n"
    user_content += "Write the full essay."

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_content}
    ]

    try:
        result = _call_groq(messages, max_tokens=min(target * 2, 4000))
        word_count = len(result.split())
        title = f"Essay: {topic}"

        _save_session(session_id, title, topic, f"essay_{style}", "complete",
                      result, sources, [], word_count)
        _notify(f"✍️ Essay Complete: {topic}\n{word_count} words ({style})")

        return {"session_id": session_id, "title": title, "result": result,
                "sources": sources, "word_count": word_count, "status": "complete",
                "style": style, "length": length}

    except Exception as e:
        print(f"[Research] write_essay failed: {e}")
        return {"session_id": session_id, "status": "error", "error": str(e)}


def generate_presentation(topic: str, slides: int = 10) -> dict:
    """
    Generate a structured presentation outline as JSON.
    Returns slide data that the frontend renders as a beautiful deck.
    """
    session_id = _new_session_id(f"pptx:{topic}")

    kb_context, sources = _retrieve_from_kb(topic, n=6)

    system = """You are ORA's Research Agent creating a presentation outline.
Return ONLY valid JSON — no markdown, no explanation, just the JSON object.

The JSON must have this exact structure:
{
  "title": "Presentation Title",
  "subtitle": "Subtitle or tagline",
  "theme": "one of: blue|green|dark|warm|minimal",
  "slides": [
    {
      "index": 1,
      "type": "title",
      "title": "Main title",
      "subtitle": "Optional subtitle",
      "notes": "Speaker notes"
    },
    {
      "index": 2,
      "type": "bullets",
      "title": "Section title",
      "points": ["Point 1", "Point 2", "Point 3"],
      "notes": "Speaker notes"
    },
    {
      "index": 3,
      "type": "two_column",
      "title": "Section title",
      "left": {"heading": "Left heading", "points": ["..."]},
      "right": {"heading": "Right heading", "points": ["..."]},
      "notes": "Speaker notes"
    },
    {
      "index": 4,
      "type": "quote",
      "quote": "A powerful quote or key finding",
      "attribution": "Source or context",
      "notes": "Speaker notes"
    },
    {
      "index": 5,
      "type": "conclusion",
      "title": "Key Takeaways",
      "points": ["Takeaway 1", "Takeaway 2"],
      "notes": "Speaker notes"
    }
  ]
}

Use a mix of slide types. Make content insightful and specific, not generic."""

    user_content = f"Presentation Topic: {topic}\nNumber of slides: {slides}\n\n"
    if kb_context:
        user_content += f"Source material:\n{kb_context}\n\n"
    user_content += "Generate the full presentation JSON."

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_content}
    ]

    try:
        raw = _call_groq(messages, max_tokens=4000)

        # Parse JSON safely
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip().rstrip("```")

        pptx_data = json.loads(raw)
        result_str = json.dumps(pptx_data)
        title = f"Presentation: {topic}"

        _save_session(session_id, title, topic, "presentation", "complete",
                      result_str, sources, [], slides)
        _notify(f"📊 Presentation Ready: {topic}\n{slides} slides generated")

        return {"session_id": session_id, "title": title, "result": result_str,
                "pptx_data": pptx_data, "sources": sources,
                "slide_count": len(pptx_data.get("slides", [])), "status": "complete"}

    except json.JSONDecodeError as e:
        print(f"[Research] JSON parse failed: {e}\nRaw: {raw[:200]}")
        return {"session_id": session_id, "status": "error", "error": "Presentation generation failed — retry"}
    except Exception as e:
        print(f"[Research] generate_presentation failed: {e}")
        return {"session_id": session_id, "status": "error", "error": str(e)}


def summarize_document(filename: str, full_text: str, style: str = "executive") -> dict:
    """
    Summarize a document in different styles:
    executive, detailed, bullet, tldr
    """
    session_id = _new_session_id(f"summary:{filename}")

    style_prompts = {
        "executive": "Write a crisp executive summary (200-300 words) for a busy decision-maker. Lead with the most important finding. End with 3 key implications.",
        "detailed": "Write a comprehensive summary (500-700 words) covering all major sections, key arguments, and important details.",
        "bullet": "Extract the 10 most important points as clear, specific bullet points. Each point should be a complete insight, not a vague label.",
        "tldr": "Write a 3-sentence TL;DR that captures the absolute essence of this document.",
    }

    prompt = style_prompts.get(style, style_prompts["executive"])
    text_sample = full_text[:8000] if len(full_text) > 8000 else full_text

    messages = [
        {"role": "system", "content": f"You are ORA's Research Agent. {prompt}"},
        {"role": "user", "content": f"Document: {filename}\n\nContent:\n{text_sample}"}
    ]

    try:
        result = _call_groq(messages, model="llama-3.3-70b-versatile", max_tokens=1500)
        word_count = len(result.split())
        title = f"Summary ({style}): {filename}"

        _save_session(session_id, title, filename, f"summary_{style}", "complete",
                      result, [filename], [], word_count)

        return {"session_id": session_id, "title": title, "result": result,
                "word_count": word_count, "status": "complete", "style": style}

    except Exception as e:
        return {"session_id": session_id, "status": "error", "error": str(e)}


def compare_documents(query: str, filenames: list) -> dict:
    """
    Comparative analysis across multiple documents.
    """
    session_id = _new_session_id(f"compare:{':'.join(filenames)}")

    # Retrieve content for each doc
    combined = ""
    sources = []
    for fname in filenames[:4]:  # max 4 docs
        chunks, _ = _retrieve_from_kb(fname, n=4)
        if chunks:
            combined += f"\n\n### Document: {fname}\n{chunks}"
            sources.append(fname)

    if not combined:
        return {"session_id": session_id, "status": "error",
                "error": "Could not retrieve content from specified documents"}

    system = """You are ORA's Research Agent performing comparative document analysis.

Structure your comparison as:
1. OVERVIEW — What each document is about (2-3 sentences each)
2. COMMON GROUND — Where they agree or complement each other
3. KEY DIFFERENCES — Where they diverge (methodology, conclusions, perspective)
4. SYNTHESIS — What the combination reveals that neither alone shows
5. VERDICT — Which is stronger/more relevant for the query and why

Be specific and cite documents by name. Avoid vague generalities."""

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"Comparison Focus: {query}\n\nDocuments:\n{combined}"}
    ]

    try:
        result = _call_groq(messages, max_tokens=2500)
        word_count = len(result.split())
        title = f"Comparison: {' vs '.join(filenames[:3])}"

        _save_session(session_id, title, query, "compare", "complete",
                      result, sources, [], word_count)
        _notify(f"⚖️ Comparison Complete: {title}")

        return {"session_id": session_id, "title": title, "result": result,
                "sources": sources, "word_count": word_count, "status": "complete"}

    except Exception as e:
        return {"session_id": session_id, "status": "error", "error": str(e)}


def extract_key_points(filename: str, full_text: str) -> dict:
    """Extract structured key points, entities, and insights from a document."""
    session_id = _new_session_id(f"extract:{filename}")

    text_sample = full_text[:6000]

    system = """You are ORA's Research Agent performing structured extraction.
Return JSON only — no markdown fences, just valid JSON.

{
  "key_arguments": ["...", "..."],
  "key_facts": ["...", "..."],
  "named_entities": {"people": [], "organizations": [], "places": [], "concepts": []},
  "definitions": [{"term": "...", "definition": "..."}],
  "questions_raised": ["...", "..."],
  "action_items": ["...", "..."],
  "overall_stance": "...",
  "confidence_level": "high|medium|low",
  "recommended_followup": "..."
}"""

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"Document: {filename}\n\nContent:\n{text_sample}\n\nExtract all key structured information."}
    ]

    try:
        raw = _call_groq(messages, model="llama-3.1-8b-instant", max_tokens=1500)
        raw = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        extracted = json.loads(raw)
        title = f"Extraction: {filename}"

        _save_session(session_id, title, filename, "extract", "complete",
                      json.dumps(extracted), [filename], [], 0)

        return {"session_id": session_id, "title": title, "result": json.dumps(extracted),
                "extracted": extracted, "status": "complete"}

    except Exception as e:
        print(f"[Research] extract failed: {e}")
        return {"session_id": session_id, "status": "error", "error": str(e)}


def ask_document(question: str, filename: str, full_text: str) -> dict:
    """Q&A mode — ask a specific question about a document."""
    session_id = _new_session_id(f"qa:{filename}:{question}")

    # Also search KB for this doc's chunks
    kb_context, _ = _retrieve_from_kb(f"{filename} {question}", n=6)
    context = kb_context or full_text[:5000]

    messages = [
        {"role": "system", "content": """You are ORA's Research Agent answering questions about documents.
Be precise and evidence-based. Quote or paraphrase the document directly.
If the answer is not in the document, say so clearly.
Format: Answer directly, then cite where in the document this comes from."""},
        {"role": "user", "content": f"Document: {filename}\n\nContent:\n{context}\n\nQuestion: {question}"}
    ]

    try:
        result = _call_groq(messages, model="llama-3.3-70b-versatile", max_tokens=800)
        return {"session_id": session_id, "result": result, "status": "complete",
                "question": question, "document": filename}
    except Exception as e:
        return {"session_id": session_id, "status": "error", "error": str(e)}


# ─────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────

def _generate_title(query: str) -> str:
    try:
        messages = [
            {"role": "system", "content": "Generate a concise research title (max 8 words) for this query. Return ONLY the title, nothing else."},
            {"role": "user", "content": query}
        ]
        title = _call_groq(messages, model="llama-3.1-8b-instant", max_tokens=30)
        return title.strip().strip('"').strip("'")[:80]
    except Exception:
        return query[:60]


def _notify(message: str):
    try:
        from telegram_bot import notify
        notify(f"[Research Agent] {message}", is_alert=False)
    except Exception:
        pass