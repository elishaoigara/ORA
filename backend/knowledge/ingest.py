"""
ORA Knowledge — Phase 1 + 2
Multi-format document ingestion with semantic chunking.

Supports: PDF, DOCX, TXT, MD, PNG/JPG (OCR)
Chunks by paragraph/section, not blind character slices.
"""

import os
import re


# ============================================================
# PHASE 1 — UNIFIED LOADER
# ============================================================

def load_document(filepath: str) -> tuple[list[dict], str]:
    """
    Load any supported file format.
    Returns: (pages: list[{text, page_num}], doc_type: str)
    """
    name = filepath.lower()

    if name.endswith(".pdf"):
        return _load_pdf(filepath), "pdf"

    elif name.endswith(".docx"):
        return _load_docx(filepath), "docx"

    elif name.endswith((".png", ".jpg", ".jpeg")):
        return _load_image(filepath), "image"

    elif name.endswith((".txt", ".md")):
        return _load_text(filepath), "text"

    else:
        # fallback: try reading as text
        return _load_text(filepath), "text"


def _load_pdf(filepath: str) -> list[dict]:
    """Use pdfplumber for layout-aware extraction (better than PyPDF2)."""
    pages = []
    try:
        import pdfplumber
        with pdfplumber.open(filepath) as pdf:
            for i, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                if text.strip():
                    pages.append({"text": text, "page_num": i + 1})
    except Exception as e:
        print(f"[INGEST] pdfplumber failed ({e}), trying pypdf fallback")
        try:
            from pypdf import PdfReader
            reader = PdfReader(filepath)
            for i, page in enumerate(reader.pages):
                text = page.extract_text() or ""
                if text.strip():
                    pages.append({"text": text, "page_num": i + 1})
        except Exception as e2:
            print(f"[INGEST] PDF failed entirely: {e2}")
    return pages


def _load_docx(filepath: str) -> list[dict]:
    """Extract DOCX preserving paragraph structure."""
    pages = []
    try:
        from docx import Document
        doc = Document(filepath)
        # Group paragraphs into logical pages (~40 paragraphs each)
        buffer = []
        page_num = 1
        for para in doc.paragraphs:
            if para.text.strip():
                buffer.append(para.text)
            if len(buffer) >= 40:
                pages.append({"text": "\n".join(buffer), "page_num": page_num})
                buffer = []
                page_num += 1
        if buffer:
            pages.append({"text": "\n".join(buffer), "page_num": page_num})
    except Exception as e:
        print(f"[INGEST] DOCX failed: {e}")
    return pages


def _load_image(filepath: str) -> list[dict]:
    """OCR image using pytesseract."""
    try:
        import pytesseract
        from PIL import Image
        img = Image.open(filepath)
        text = pytesseract.image_to_string(img)
        if text.strip():
            return [{"text": text, "page_num": 1}]
    except Exception as e:
        print(f"[INGEST] OCR failed: {e}")
        # Fallback: record image dimensions as metadata
        try:
            from PIL import Image
            img = Image.open(filepath)
            return [{"text": f"[Image: {img.size[0]}x{img.size[1]}px — no OCR text extracted]", "page_num": 1}]
        except:
            pass
    return []


def _load_text(filepath: str) -> list[dict]:
    """Load plain text / markdown."""
    try:
        with open(filepath, encoding="utf-8", errors="ignore") as f:
            content = f.read()
        if content.strip():
            return [{"text": content, "page_num": 1}]
    except Exception as e:
        print(f"[INGEST] Text load failed: {e}")
    return []


# ============================================================
# PHASE 2 — SMART SEMANTIC CHUNKING
# ============================================================

def chunk_document(pages: list[dict], filename: str, doc_type: str) -> list[dict]:
    """
    Smart chunking: splits by semantic sections (headings, paragraphs, blank lines).
    Each chunk carries source metadata for grounded retrieval.

    Returns list of chunk dicts:
    {
        text, section, source, page_num, chunk_index, importance, doc_type
    }
    """
    all_chunks = []
    chunk_index = 0

    for page in pages:
        raw = page["text"]
        page_num = page["page_num"]

        sections = _split_into_sections(raw)

        for section_title, section_body in sections:
            # Further split long sections into overlapping windows
            sub_chunks = _window_split(section_body, size=600, overlap=120)

            for sub in sub_chunks:
                if len(sub.strip()) < 40:
                    continue

                importance = _score_importance(sub, section_title)

                all_chunks.append({
                    "text": sub.strip(),
                    "section": section_title or f"Page {page_num}",
                    "source": filename,
                    "page_num": page_num,
                    "chunk_index": chunk_index,
                    "importance": importance,
                    "doc_type": doc_type,
                })

                chunk_index += 1

    return all_chunks


def _split_into_sections(text: str) -> list[tuple[str, str]]:
    """
    Split text into (heading, body) pairs.
    Detects: markdown headings, ALL CAPS lines, numbered sections, blank-line paragraphs.
    """
    # Heading patterns: markdown #, numbered (1. / 1.1), ALL CAPS short lines
    heading_pattern = re.compile(
        r'^(#{1,4}\s.+|[A-Z][A-Z\s]{3,40}$|\d+[\.\d]*\s+[A-Z].{0,60})$',
        re.MULTILINE
    )

    sections = []
    parts = heading_pattern.split(text)

    # parts alternates: [pre-heading text, heading, body, heading, body, ...]
    current_heading = ""
    current_body = parts[0] if parts else ""

    i = 1
    while i < len(parts):
        heading = parts[i].strip()
        body = parts[i + 1] if i + 1 < len(parts) else ""

        if current_body.strip():
            sections.append((current_heading, current_body))

        current_heading = heading
        current_body = body
        i += 2

    if current_body.strip():
        sections.append((current_heading, current_body))

    # Fallback: if no headings detected, split by double newlines (paragraphs)
    if not sections:
        paragraphs = [p.strip() for p in re.split(r'\n{2,}', text) if p.strip()]
        sections = [("", p) for p in paragraphs]

    return sections if sections else [("", text)]


def _window_split(text: str, size: int = 600, overlap: int = 120) -> list[str]:
    """Sliding window split for long sections."""
    if len(text) <= size:
        return [text]

    chunks = []
    i = 0
    while i < len(text):
        chunks.append(text[i:i + size])
        i += size - overlap

    return chunks


def _score_importance(text: str, section: str) -> float:
    """
    Heuristic importance score 0.0–1.0.
    Higher = more likely to be useful in retrieval.
    """
    score = 0.5

    # Boost for key signal words
    signals = [
        "conclusion", "summary", "result", "finding", "important",
        "key", "critical", "objective", "goal", "recommend",
        "decision", "action", "deadline", "urgent", "must", "should"
    ]
    lower = text.lower()
    hits = sum(1 for s in signals if s in lower)
    score += min(hits * 0.05, 0.3)

    # Boost for headings that are content-rich
    if section and len(section) > 3:
        score += 0.1

    # Penalize very short chunks
    if len(text) < 100:
        score -= 0.2

    # Penalize chunks that are mostly whitespace/punctuation
    alpha_ratio = sum(c.isalpha() for c in text) / max(len(text), 1)
    if alpha_ratio < 0.5:
        score -= 0.1

    return round(max(0.0, min(1.0, score)), 3)