"""Regression coverage for ORA Phase 7 voice and Phase 8 reliability."""

from __future__ import annotations

import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.dirname(__file__))


class VoiceServiceTests(unittest.TestCase):
    def test_transcribe_audio_uses_whisper_and_returns_quality_metadata(self):
        from voice_service import transcribe_audio

        segment = SimpleNamespace(no_speech_prob=0.02, avg_logprob=-0.08)
        transcription = SimpleNamespace(
            text="What is on my calendar today?",
            language="en",
            duration=2.4,
            segments=[segment],
        )
        fake_client = SimpleNamespace(
            audio=SimpleNamespace(
                transcriptions=SimpleNamespace(create=lambda **kwargs: transcription)
            )
        )
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}), patch("voice_service.Groq", return_value=fake_client):
            result = transcribe_audio(b"fake-webm-bytes", "recording.webm", "auto")

        self.assertEqual(result["text"], "What is on my calendar today?")
        self.assertEqual(result["model"], "whisper-large-v3-turbo")
        self.assertEqual(result["quality"]["segments"], 1)
        self.assertEqual(result["quality"]["max_no_speech_prob"], 0.02)

    def test_synthesize_speech_posts_bounded_text_and_returns_audio(self):
        from voice_service import synthesize_speech

        fake_response = SimpleNamespace(content=b"RIFF-wav", raise_for_status=lambda: None)
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}), patch("voice_service.requests.post", return_value=fake_response) as post:
            audio = synthesize_speech("Hello ORA", "hannah")
        self.assertEqual(audio, b"RIFF-wav")
        self.assertEqual(post.call_args.kwargs["json"]["voice"], "hannah")
        self.assertEqual(post.call_args.kwargs["json"]["response_format"], "wav")

    def test_transcribe_audio_rejects_empty_oversized_and_unknown_audio(self):
        from voice_service import VoiceInputError, VOICE_MAX_BYTES, transcribe_audio

        with self.assertRaises(VoiceInputError):
            transcribe_audio(b"", "recording.webm")
        with self.assertRaises(VoiceInputError):
            transcribe_audio(b"x" * (VOICE_MAX_BYTES + 1), "recording.webm")
        with self.assertRaises(VoiceInputError):
            transcribe_audio(b"audio", "recording.exe")


class ReliabilityTests(unittest.TestCase):
    def test_sliding_window_limiter_has_bounded_voice_budget(self):
        from reliability import SlidingWindowLimiter

        limiter = SlidingWindowLimiter()
        results = [limiter.allow("test-client", limit=2, window_seconds=60) for _ in range(3)]
        self.assertEqual(results[0][0], True)
        self.assertEqual(results[1][0], True)
        self.assertEqual(results[2][0], False)
        self.assertGreaterEqual(results[2][1], 1)

    def test_runtime_metrics_report_errors_and_latency(self):
        from reliability import RuntimeMetrics

        metrics = RuntimeMetrics()
        metrics.record("/api/voice/command", 200, 12.5)
        metrics.record("/api/voice/command", 502, 20.0)
        snapshot = metrics.snapshot()
        self.assertEqual(snapshot["requests"], 2)
        self.assertEqual(snapshot["errors"], 1)
        self.assertEqual(snapshot["paths"]["/api/voice/command"]["errors"], 1)
        self.assertGreater(snapshot["latency_p95_ms"], 0)


class VoiceApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["APP_ENV"] = "development"
        os.environ["ORA_API_TOKEN"] = ""
        from fastapi.testclient import TestClient
        from api import app
        cls.client = TestClient(app)

    def test_ready_and_voice_config_contracts(self):
        ready = self.client.get("/api/ready")
        self.assertEqual(ready.status_code, 200)
        self.assertIn(ready.json()["status"], {"ready", "degraded"})
        self.assertIn("database", ready.json()["checks"])

        config = self.client.get("/api/voice/config")
        self.assertEqual(config.status_code, 200)
        body = config.json()
        self.assertEqual(body["interaction"]["mode"], "push_to_talk")
        self.assertEqual(body["tts"]["provider"], "browser_speech_synthesis")
        self.assertIn(".webm", body["stt"]["formats"])

    def test_voice_speak_returns_wav_audio(self):
        with patch("voice_service.synthesize_speech", return_value=b"RIFF-wav"):
            response = self.client.post("/api/voice/speak", json={"text": "Hello ORA", "voice": "hannah"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "audio/wav")
        self.assertEqual(response.content, b"RIFF-wav")

    def test_voice_command_preserves_transcript_reply_session_and_intent(self):
        from api import chat

        transcription = {
            "text": "send an email to test@example.com",
            "model": "whisper-large-v3-turbo",
            "language": "en",
            "duration_seconds": 1.5,
            "quality": {"segments": 1},
        }
        chat_result = {
            "reply": "Approval required. Review the action queue.",
            "intent": "send_email",
            "query_type": "action",
            "pipeline": "intent",
            "session_id": "session-voice-1",
        }
        with patch("voice_service.transcribe_audio", return_value=transcription), \
             patch("api.chat", new=AsyncMock(return_value=chat_result)) as chat_mock:
            response = self.client.post(
                "/api/voice/command",
                files={"audio": ("voice.webm", b"audio-bytes", "audio/webm")},
                data={"session_id": "session-voice-0", "language": "auto"},
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["transcript"], transcription["text"])
        self.assertEqual(body["reply"], chat_result["reply"])
        self.assertEqual(body["intent"], "send_email")
        self.assertEqual(body["session_id"], "session-voice-1")
        chat_mock.assert_awaited_once()
        self.assertEqual(chat_mock.call_args.args[0].message, transcription["text"])


if __name__ == "__main__":
    unittest.main()
