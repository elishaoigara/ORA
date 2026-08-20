"""ORA push-to-talk speech-to-text service."""

from __future__ import annotations

import io
import os
from typing import Any

import requests
from groq import Groq

VOICE_MAX_BYTES = 10 * 1024 * 1024
VOICE_MODEL = os.getenv("GROQ_STT_MODEL", "whisper-large-v3-turbo")
VOICE_TTS_MODEL = os.getenv("GROQ_TTS_MODEL", "canopylabs/orpheus-v1-english")
VOICE_TTS_DEFAULT = os.getenv("GROQ_TTS_VOICE", "hannah")
VOICE_ALLOWED_EXTENSIONS = {".webm", ".ogg", ".m4a", ".mp4", ".wav", ".mp3", ".flac", ".mpeg", ".mpga"}


class VoiceInputError(ValueError):
    """Raised when an uploaded voice recording is invalid or empty."""


def _extension(filename: str) -> str:
    return os.path.splitext((filename or "").lower())[1]


def _segment_quality(transcription: Any) -> dict[str, Any]:
    segments = getattr(transcription, "segments", None) or []
    no_speech = [float(getattr(s, "no_speech_prob", 0.0) or 0.0) for s in segments]
    logprobs = [float(getattr(s, "avg_logprob", 0.0) or 0.0) for s in segments]
    quality: dict[str, Any] = {"segments": len(segments)}
    if no_speech:
        quality["max_no_speech_prob"] = round(max(no_speech), 4)
    if logprobs:
        quality["min_avg_logprob"] = round(min(logprobs), 4)
    return quality


def transcribe_audio(audio_bytes: bytes, filename: str = "ora-voice.webm", language: str | None = None) -> dict[str, Any]:
    """Transcribe one browser recording using Groq Whisper with safe limits."""
    if not audio_bytes:
        raise VoiceInputError("No audio was received")
    if len(audio_bytes) > VOICE_MAX_BYTES:
        raise VoiceInputError(f"Audio is too large; maximum is {VOICE_MAX_BYTES // (1024 * 1024)} MB")
    extension = _extension(filename) or ".webm"
    if extension not in VOICE_ALLOWED_EXTENSIONS:
        raise VoiceInputError(f"Unsupported audio format: {extension}")

    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Voice transcription is not configured")

    audio_file = io.BytesIO(audio_bytes)
    audio_file.name = f"ora-voice{extension}"
    client = Groq(api_key=api_key)
    kwargs: dict[str, Any] = {
        "file": audio_file,
        "model": VOICE_MODEL,
        "response_format": "verbose_json",
        "temperature": 0.0,
    }
    if language and language != "auto":
        kwargs["language"] = language[:8]

    transcription = client.audio.transcriptions.create(**kwargs)
    text = (getattr(transcription, "text", "") or "").strip()
    if not text:
        raise VoiceInputError("No speech was detected; try speaking closer to the microphone")

    return {
        "text": text,
        "model": VOICE_MODEL,
        "language": getattr(transcription, "language", None),
        "duration_seconds": getattr(transcription, "duration", None),
        "quality": _segment_quality(transcription),
    }


def synthesize_speech(text: str, voice: str | None = None) -> bytes:
    """Generate a short WAV response for browsers without local speech synthesis."""
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    clean_text = " ".join((text or "").split())[:2000]
    if not api_key:
        raise RuntimeError("Voice synthesis is not configured")
    if not clean_text:
        raise VoiceInputError("No text was provided for speech")
    response = requests.post(
        "https://api.groq.com/openai/v1/audio/speech",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": VOICE_TTS_MODEL,
            "voice": voice or VOICE_TTS_DEFAULT,
            "input": clean_text,
            "response_format": "wav",
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.content
