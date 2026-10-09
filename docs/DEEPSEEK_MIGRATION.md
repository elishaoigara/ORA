# DeepSeek for ORA and Android

The deployed Mini backend (`uvicorn next_api:app`) handles web, Android and Telegram chat through `mini/intelligence.py`. It now sends chat and tool reasoning to DeepSeek. The archived legacy backend modules are not part of this migration.

## Activate on Render

1. Add `DEEPSEEK_API_KEY` as a secret on the existing ORA backend service. Use a DeepSeek account with available API credit. Do not commit the key or put it in Vercel/Expo public variables.
2. Set `DEEPSEEK_MODEL=deepseek-flash` (the default). The model can be overridden with a compatible DeepSeek chat model.
3. Deploy the migration branch after review. Existing Render services may require adding variables manually; changing the example files does not set live secrets.
4. Check `/api/health`: `ai_provider` should be `deepseek`, `ai_model` should match your setting and `ai_configured` should be true. This only checks configuration presence, not authentication or billing.
5. Send a message on web and the paired Android app. Ask for `2+2` using the calculator, then ask for a task and verify it remains pending until approved. Check Telegram too if configured.

No Android rebuild, new pairing or database migration is required. The companion keeps using `/api/v2/chat`; all provider credentials stay on the backend.

## Voice and images

Keep `GROQ_API_KEY` for the existing optional Whisper transcription and image-analysis features. Images also need `GROQ_VISION_MODEL`. These routes remain on Groq; this change does not claim DeepSeek is a Whisper-compatible transcription service. Text chat no longer uses `GROQ_API_KEY` or `GROQ_MODEL_PRIMARY` and never falls back to Groq.

## Bounds and rollback

Non-thinking mode is explicit to preserve the current bounded tool loop and avoid retaining reasoning content. The existing three-call limit, output cap, request timeouts and approval rules remain in place. No automatic provider retries are added, since earlier tool calls may already have prepared actions.

To roll back, deploy the preceding backend commit with its original Groq chat configuration. Workspace data and pairing credentials are unchanged.

References: https://api-docs.deepseek.com/en/ and https://api-docs.deepseek.com/guides/tool_calls/
