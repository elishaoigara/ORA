"""
ORA Knowledge — Phase 1 + 2 (UPGRADED RAG VERSION)
Production-grade ingestion + semantic chunking.
"""

import os
import re
import hashlib
from typing import List, Dict, Tuple


# ============================================================
# PHASE 1 — LOADER (UNCHANGED BUT CLEANED)
# ============================================================

def load_document(filepath: str) -> Tuple[List[dict], str]:
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
        return _load_text(filepath), "text"


# ============================================================
# PDF / DOCX / IMAGE / TEXT LOADERS (same but slightly improved)
# ============================================================

def _load_pdf(filepath: str):
    pages = []
    try:
        import pdfplumber
        with pdfplumber.open(filepath) as pdf:
            for i, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                text = _clean_text(text)
                if text.strip():
                    pages.append({"text": text, "page_num": i + 1})
    except Exception:
        pass
    return pages


def _load_docx(filepath: str):
    pages = []
    try:
        from docx import Document
        doc = Document(filepath)

        buffer = []
        page = 1

        for para in doc.paragraphs:
            t = para.text.strip()
            if t:
                buffer.append(t)

            if len(buffer) >= 30:
                pages.append({"text": _clean_text("\n".join(buffer)), "page_num": page})
                buffer = []
                page += 1

        if buffer:
            pages.append({"text": _clean_text("\n".join(buffer)), "page_num": page})

    except Exception:
        pass

    return pages


def _load_image(filepath: str):
    try:
        import pytesseract
        from PIL import Image

        img = Image.open(filepath)
        text = pytesseract.image_to_string(img)
        text = _clean_text(text)

        if text:
            return [{"text": text, "page_num": 1}]
    except Exception:
        pass

    return []


def _load_text(filepath: str):
    try:
        with open(filepath, encoding="utf-8", errors="ignore") as f:
            return [{"text": _clean_text(f.read()), "page_num": 1}]
    except Exception:
        return []


# ============================================================
# TEXT CLEANING (IMPORTANT FOR EMBEDDINGS)
# ============================================================

def _clean_text(text: str) -> str:
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'[^\w\s.,;:()\-/%]', '', text)
    return text.strip()


# ============================================================
# PHASE 2 — RAG-GRADE CHUNKING (IMPROVED)
# ============================================================

def chunk_document(pages: List[dict], filename: str, doc_type: str) -> List[dict]:
    chunks = []
    index = 0

    for page in pages:
        text = page["text"]
        page_num = page["page_num"]

        # 1. Split into sentences first (CRITICAL FIX)
        sentences = _split_sentences(text)

        # 2. Build semantic chunks
        current = []

        for s in sentences:
            if len(" ".join(current + [s])) > 600:
                chunk_text = " ".join(current)
                chunks.append(_build_chunk(chunk_text, filename, doc_type, page_num, index))
                index += 1

                # overlap
                current = current[-2:] if len(current) > 2 else current
            current.append(s)

        if current:
            chunks.append(_build_chunk(" ".join(current), filename, doc_type, page_num, index))
            index += 1

    return chunks


# ============================================================
# SENTENCE SPLITTING (FIXED)
# ============================================================

def _split_sentences(text: str) -> List[str]:
    return [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]


# ============================================================
# CHUNK BUILDER
# ============================================================

def _build_chunk(text, source, doc_type, page_num, index):
    return {
        "text": text.strip(),
        "source": source,
        "doc_type": doc_type,
        "page_num": page_num,
        "chunk_index": index,
        "importance": _score(text),
        "hash": hashlib.md5(text.encode()).hexdigest()
    }


# ============================================================
# IMPORTANCE SCORING (IMPROVED)
# ============================================================

def _score(text: str) -> float:
    text = text.lower()
    score = 0.5

    keywords = [
        "important", "critical", "must", "should", "required",
        "deadline", "summary", "conclusion", "result", "key"
    ]

    score += sum(0.05 for k in keywords if k in text)

    if len(text) < 120:
        score -= 0.2

    alpha_ratio = sum(c.isalpha() for c in text) / max(len(text), 1)
    if alpha_ratio < 0.5:
        score -= 0.1

    return round(max(0.0, min(1.0, score)), 3)