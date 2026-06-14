"""
ORA Browse Connector
- Fetches any URL and extracts clean readable text
- Summarises with Groq if content is long
- Falls back gracefully if beautifulsoup4 not installed (regex strip)
- YouTube URLs → transcript via youtube_transcript_api
- PDF URLs → text via PyMuPDF
"""

from __future__ import annotations

import re
import traceback
from typing import Optional
from urllib.parse import urlparse

import requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

MAX_RAW_CHARS    = 12_000   # chars sent to Groq for summary
MAX_DIRECT_CHARS =  4_000   # if content fits, return directly without LLM


# ─────────────────────────────────────────────
# URL DETECTION HELPERS
# ─────────────────────────────────────────────

def _is_youtube(url: str) -> bool:
    return bool(re.search(r"(youtube\.com/watch|youtu\.be/)", url))

def _is_pdf(url: str) -> bool:
    return url.lower().split("?")[0].endswith(".pdf")

def _extract_video_id(url: str) -> Optional[str]:
    m = re.search(r"(?:v=|youtu\.be/)([a-zA-Z0-9_-]{11})", url)
    return m.group(1) if m else None


# ─────────────────────────────────────────────
# TEXT EXTRACTORS
# ─────────────────────────────────────────────

def _extract_html(html: str) -> str:
    """Strip HTML tags → clean text. Uses BeautifulSoup if available, regex fallback."""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        # Remove noise elements
        for tag in soup(["script", "style", "nav", "footer", "header",
                          "aside", "noscript", "iframe", "form"]):
            tag.decompose()
        # Prefer article/main content
        main = soup.find("article") or soup.find("main") or soup.body or soup
        text = main.get_text(separator="\n", strip=True)
    except ImportError:
        # Regex fallback — good enough for most pages
        text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.S | re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"&[a-z]+;", " ", text)

    # Collapse whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)
    return text.strip()


def _fetch_youtube(url: str) -> dict:
    vid = _extract_video_id(url)
    if not vid:
        return {"ok": False, "error": "Could not extract YouTube video ID"}
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        entries = YouTubeTranscriptApi.get_transcript(vid)
        transcript = " ".join(e["text"] for e in entries)
        return {"ok": True, "type": "youtube", "url": url,
                "content": transcript, "title": f"YouTube: {vid}"}
    except Exception as e:
        return {"ok": False, "error": f"Transcript unavailable: {e}"}


def _fetch_pdf(url: str) -> dict:
    try:
        import fitz  # PyMuPDF
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        doc  = fitz.open(stream=r.content, filetype="pdf")
        text = "\n".join(page.get_text() for page in doc)
        doc.close()
        return {"ok": True, "type": "pdf", "url": url,
                "content": text.strip(), "title": f"PDF: {urlparse(url).path.split('/')[-1]}"}
    except Exception as e:
        return {"ok": False, "error": f"PDF read failed: {e}"}


def _fetch_html(url: str) -> dict:
    try:
        r = requests.get(url, headers=HEADERS, timeout=(5, 12), allow_redirects=True)
        r.raise_for_status()
        content_type = r.headers.get("content-type", "")
        if "pdf" in content_type:
            # Redirect to PDF handler
            return _fetch_pdf(url)

        # Try to get page title
        title_match = re.search(r"<title[^>]*>(.*?)</title>", r.text, re.I | re.S)
        title = title_match.group(1).strip() if title_match else urlparse(url).netloc

        text = _extract_html(r.text)
        return {"ok": True, "type": "html", "url": url,
                "content": text, "title": title}
    except requests.exceptions.Timeout:
        return {"ok": False, "error": "Page took too long to load (>15s)"}
    except requests.exceptions.HTTPError as e:
        return {"ok": False, "error": f"HTTP {e.response.status_code}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ─────────────────────────────────────────────
# SUMMARISE WITH GROQ
# ─────────────────────────────────────────────

def _summarise(content: str, url: str, question: Optional[str] = None) -> str:
    """Use Groq to summarise or answer a question about the page content."""
    try:
        from groq import Groq
        from config import GROQ_API_KEY, GROQ_MODEL_PRIMARY
        import httpx

        client = Groq(api_key=GROQ_API_KEY, timeout=httpx.Timeout(20.0))

        if question:
            prompt = (
                f"Based on the content below from {url}, answer this question:\n"
                f"{question}\n\n"
                f"Content:\n{content[:MAX_RAW_CHARS]}\n\n"
                "Answer concisely and cite specific details from the content."
            )
        else:
            prompt = (
                f"Summarise the key information from this page ({url}):\n\n"
                f"{content[:MAX_RAW_CHARS]}\n\n"
                "Give a clear structured summary in 3-5 bullet points covering "
                "the most important facts, numbers, or conclusions."
            )

        resp = client.chat.completions.create(
            model=GROQ_MODEL_PRIMARY or "llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=600,
            temperature=0.3,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        print(f"[BROWSE] Summarise error: {e}")
        # Fallback: return clean lines, strip HTML entities
        import html
        lines = [html.unescape(l) for l in content.splitlines() if len(l.strip()) > 30]
        return "\n".join(lines[:40])[:MAX_DIRECT_CHARS]


# ─────────────────────────────────────────────
# MAIN PUBLIC FUNCTION
# ─────────────────────────────────────────────

def browse(url: str, question: Optional[str] = None) -> dict:
    """
    Fetch a URL and return clean content.
    If question is provided, answers it from the page.
    If content is short enough, returns directly. Otherwise summarises with Groq.

    Returns:
        {
            "ok": True,
            "url": str,
            "title": str,
            "summary": str,        # what gets shown to user
            "raw_length": int,
            "type": "html"|"pdf"|"youtube"
        }
    """
    url = url.strip()
    if not url.startswith("http"):
        url = "https://" + url

    print(f"[BROWSE] Fetching: {url}")

    # Route by type
    if _is_youtube(url):
        result = _fetch_youtube(url)
    elif _is_pdf(url):
        result = _fetch_pdf(url)
    else:
        result = _fetch_html(url)

    if not result.get("ok"):
        return result

    content   = result.get("content", "")
    raw_len   = len(content)
    title     = result.get("title", url)

    # Very short content — return directly
    if raw_len < 800 and not question:
        summary = content
    else:
        # Always summarise — raw HTML text is not useful as-is
        summary = _summarise(content, url, question=question)

    return {
        "ok":         True,
        "url":        url,
        "title":      title,
        "summary":    summary,
        "raw_length": raw_len,
        "type":       result.get("type", "html"),
    }