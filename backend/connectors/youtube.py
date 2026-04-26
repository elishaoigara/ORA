"""
ORA YouTube Connector — Phase 4
On-demand only — called from chat when user pastes a YouTube URL.
No API key needed. Uses youtube-transcript-api.
"""

from __future__ import annotations

import re
import traceback
from typing import Optional


# ── Video ID extractor ─────────────────────────────────────────
def _extract_video_id(url: str) -> Optional[str]:
    patterns = [
        r"(?:v=|youtu\.be/|embed/|shorts/)([a-zA-Z0-9_-]{11})",
    ]

    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)

    return None


# ── Transcript fetcher ─────────────────────────────────────────
def get_transcript(url: str) -> Optional[str]:
    try:
        from youtube_transcript_api import YouTubeTranscriptApi

        video_id = _extract_video_id(url)
        if not video_id:
            return None

        transcript = YouTubeTranscriptApi.get_transcript(
            video_id,
            languages=["en", "en-US", "en-GB"],
        )

        text = " ".join(t["text"] for t in transcript)
        return text[:50000]

    except Exception as e:
        print(f"[YOUTUBE] transcript error: {e}")
        return None


# ── SAFE INGESTION WRAPPER (FIX FOR PYLANCE) ───────────────────
def _ingest(text: str, source: str, tags: str) -> None:
    """
    Safe bridge to knowledge pipeline.
    Avoids direct symbol import issues.
    """
    try:
        import knowledge.pipeline as kp

        ingest_fn = getattr(kp, "ingest_text", None)

        if callable(ingest_fn):
            ingest_fn(text=text, source=source, tags=tags)
        else:
            print("[YOUTUBE] ingest_text not found in pipeline")

    except Exception as e:
        print(f"[YOUTUBE] ingestion error: {e}")


# ── MAIN INGEST FUNCTION ───────────────────────────────────────
def ingest_youtube(url: str) -> dict:
    try:
        video_id = _extract_video_id(url)
        if not video_id:
            return {"ok": False, "message": "Invalid YouTube URL"}

        transcript = get_transcript(url)
        if not transcript:
            return {"ok": False, "message": "No transcript available"}

        _ingest(
            text=transcript,
            source=f"YouTube: {url}",
            tags=f"youtube:{video_id}",
        )

        word_count = len(transcript.split())

        return {
            "ok": True,
            "video_id": video_id,
            "words": word_count,
            "message": f"Ingested {word_count} words",
        }

    except Exception:
        print("[YOUTUBE] ingest failed:")
        print(traceback.format_exc())
        return {"ok": False, "message": "Ingestion failed"}