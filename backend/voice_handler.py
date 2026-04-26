"""
ORA Voice Handler — Telegram Voice Messages
Receives .ogg voice from Telegram → transcribes via Groq Whisper → routes to ORA chat.
Optional TTS reply via gTTS.

Render free tier safe:
- Whisper only runs on voice messages
- Audio deleted immediately after transcription
- No ffmpeg/pydub required
- TTS optional (disabled by default)
"""

import os
import time
import tempfile
import requests
import traceback

from config import TELEGRAM_BOT_TOKEN, GROQ_API_KEY

BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}" if TELEGRAM_BOT_TOKEN else None


# ─────────────────────────────────────────────
# Voice reply toggle
# ─────────────────────────────────────────────
_voice_reply_enabled = False

def toggle_voice_reply(enabled: bool):
    global _voice_reply_enabled
    _voice_reply_enabled = enabled

def voice_reply_enabled() -> bool:
    return _voice_reply_enabled


# ─────────────────────────────────────────────
# Download voice from Telegram
# ─────────────────────────────────────────────
def download_voice(file_id: str) -> str | None:
    try:
        r = requests.get(
            f"{BASE}/getFile",
            params={"file_id": file_id},
            timeout=10,
        )

        file_path = r.json().get("result", {}).get("file_path")
        if not file_path:
            print("[VOICE] Missing file_path")
            return None

        audio_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
        audio_r = requests.get(audio_url, timeout=30)

        if not audio_r.ok:
            print(f"[VOICE] Download failed: {audio_r.status_code}")
            return None

        tmp = tempfile.NamedTemporaryFile(
            suffix=".ogg",
            delete=False,
            dir=os.path.join(os.path.dirname(__file__), "data")
        )

        tmp.write(audio_r.content)
        tmp.close()

        return tmp.name

    except Exception as e:
        print(f"[VOICE] download error: {e}")
        return None


# ─────────────────────────────────────────────
# Transcribe via Groq Whisper
# ─────────────────────────────────────────────
def transcribe(audio_path: str) -> str | None:
    try:
        from groq import Groq
        client = Groq(api_key=GROQ_API_KEY)

        with open(audio_path, "rb") as f:
            result = client.audio.transcriptions.create(
                model="whisper-large-v3-turbo",
                file=f,
                response_format="text",
            )

        text = result.strip() if isinstance(result, str) else getattr(result, "text", "").strip()
        return text if text else None

    except Exception as e:
        print(f"[VOICE] transcribe error: {e}")
        print(traceback.format_exc())
        return None

    finally:
        # SAFE cleanup
        try:
            if audio_path and os.path.exists(audio_path):
                os.unlink(audio_path)
        except Exception:
            pass


# ─────────────────────────────────────────────
# TTS reply (optional)
# ─────────────────────────────────────────────
def speak_reply(chat_id: int, text: str) -> bool:
    """
    Send ORA response as voice using gTTS.
    """

    tmp_path = None

    try:
        from gtts import gTTS  # type: ignore[import]

        short_text = text[:400] if len(text) > 400 else text

        tmp_path = os.path.join(
            os.path.dirname(__file__),
            "data",
            f"reply_{int(time.time())}.mp3"
        )

        tts = gTTS(text=short_text, lang="en", slow=False)
        tts.save(tmp_path)

        with open(tmp_path, "rb") as f:
            requests.post(
                f"{BASE}/sendAudio",
                data={"chat_id": chat_id},
                files={"audio": ("reply.mp3", f, "audio/mpeg")},
                timeout=30,
            )

        return True

    except ImportError:
        print("[VOICE] gTTS not installed")
        return False

    except Exception as e:
        print(f"[VOICE] speak error: {e}")
        return False

    finally:
        # SAFE cleanup (fixes Pylance warning)
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


# ─────────────────────────────────────────────
# Main handler
# ─────────────────────────────────────────────
def handle_voice_message(chat_id: int, voice: dict) -> str | None:
    """
    Full pipeline:
    Telegram voice → download → Whisper → return text
    """

    file_id = voice.get("file_id")
    duration = voice.get("duration", 0)

    if not file_id:
        return None

    # Safety limit (cost control)
    if duration > 60:
        return "__TOO_LONG__"

    audio_path = download_voice(file_id)
    if not audio_path:
        return None

    return transcribe(audio_path)