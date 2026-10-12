# Telegram, voice notes and optional phone calls

Telegram can be ORA's main daily contact channel. Text chat and voice notes share
its existing workspace. Daily check-ins work without Android being open or even
paired. Weather and device routines still need the phone's existing opt-in setup.
Task/tool changes retain the existing review flow in ORA web → Tools & activity.

## Render configuration

| Variable | Purpose |
| --- | --- |
| `TELEGRAM_BOT_TOKEN` | Bot token; server only |
| `ORA_PUBLIC_URL` | `https://ora-oovf.onrender.com`; Render's `RENDER_EXTERNAL_URL` is also supported |
| `GROQ_API_KEY` | Incoming transcription and spoken reply previews |
| `GROQ_STT_MODEL` | Optional; defaults to `whisper-large-v3-turbo` |
| `GROQ_TTS_MODEL` | Optional; defaults to `canopylabs/orpheus-v1-english` |
| `GROQ_TTS_VOICE` | Optional; defaults to `troy` |
| `ORA_CRON_TOKEN` | Random secret of at least 32 characters, matching ORA GitHub Actions |

Keep the existing database, owner login, DeepSeek and CORS settings. On Vercel,
`VITE_API_URL` points to the backend; provider secrets belong on Render.
No Firebase or Expo remote push credential is needed for this path. Local Android
notifications still use expo-notifications; that dependency may contain Firebase
libraries without ORA configuring or calling the Firebase remote service.

In **ORA repository → Settings → Secrets and variables → Actions**, configure
`ORA_BACKEND_URL=https://ora-oovf.onrender.com` and the same `ORA_CRON_TOKEN`.
Run **Companion weather and Telegram alerts** once and inspect its result.
Missing secrets now fail visibly. Scheduled runs are every 30 minutes, subject to
GitHub scheduling delays and Render wake-up time. This is not exact-time calling
or an emergency alert service.

## Pair and verify

1. Open web Connections → Telegram. Activate/refresh the webhook.
2. Generate a one-time pairing link and open it in your private chat. Tap Start.
   Groups and unpaired senders cannot access the workspace.
3. Send `/status`, `/tasks`, and a simple text question. A configured key alone
   does not prove an actual successful model reply.
4. Send a voice note under three minutes and 8 MB. ORA transcribes it and sends
   it through the same chat and approval flow. Audio is not retained by ORA.
5. Send `/voice on`, then ask a short question. The complete text is followed by
   an AI voice preview of up to 200 characters, matching the Groq TTS request
   limit. WAV is converted to OGG/Opus locally. A TTS failure keeps the text reply.
   Check Groq model access if speech fails. `/voice off` disables spoken previews.
6. Send `/alerts on` for one daily check-in, after your configured briefing hour
   and outside quiet hours. `/briefing` retrieves it immediately. `/alerts off`
   cancels queued daily check-ins. Details are hidden by default; `/privacy off`
   includes task titles in future check-ins, and `/privacy on` hides them again.
7. For phone weather/routines, install the new APK, pair it, and enable Telegram
   alerts in its notification center. Queue a test and run the scheduler outside
   quiet hours. This is a separate preference from the daily Telegram check-in.

Retries are bounded to five attempts. Messages accepted by Telegram are recorded
as `sent_to_telegram`, which is not a read receipt. A network timeout after
acceptance can cause a duplicate. Jobs from the old Expo transport are retired,
not replayed to Telegram. Unlinking or switching the Telegram account disables
its daily preferences and prevents queued private alerts reaching another chat.

## Optional calls to your own phone

Telegram bots cannot initiate Telegram voice calls. ORA's optional Twilio path
makes an ordinary phone call and reads a short briefing. It identifies itself as
an AI assistant, records nothing, hangs up after speaking, and has a 90-second
maximum. It is not a two-way conversational call.

Configure these **on Render**, using a Twilio account with voice calling enabled:

| Variable | Value |
| --- | --- |
| `TWILIO_ACCOUNT_SID` | Your Twilio account SID |
| `TWILIO_AUTH_TOKEN` | Your Twilio auth token |
| `TWILIO_FROM_NUMBER` | Your Twilio voice-capable caller number, e.g. E.164 format |
| `ORA_CALL_PHONE_NUMBER` | Your own destination number in E.164 format |

Twilio charges separately; account verification, trial restrictions and destination
permissions still apply. ORA cannot provision or verify these account details.
The destination is fixed on the server; Telegram commands cannot supply arbitrary
numbers.

- `/call` requests one spoken check-in now, outside quiet hours.
- `/calls on` enables a daily phone check-in after the briefing hour.
- `/calls off` stops future scheduled calls.
- `/status` reports configuration, opt-in and the latest call request outcome.

Calls are off initially. Manual and scheduled calls share a maximum of one attempt
per 24 hours. There is no automatic redial. If the provider times out, the outcome
is marked unknown because the phone may still ring. A provider acceptance does
not prove that the call was answered. A successful live call still needs to be
verified on your phone after configuring Twilio.

## Validation

The regression suite covers private pairing, webhook authentication, duplicate
updates, shared chat actions, outbound retry without repeating AI, voice input,
voice output fallback, daily alerts without Android, quiet hours, account changes,
expired/retired jobs, fixed call destination, XML escaping and no duplicate calls.
WAV-to-Opus conversion is exercised locally with real FFmpeg and mocked Groq audio.
External provider requests in automated tests are mocked. Live credentials,
notification presentation and real phone calls are separate activation checks.

Primary API references:
- https://core.telegram.org/bots/api#sendvoice
- https://core.telegram.org/method/phone.requestCall
- https://console.groq.com/docs/text-to-speech/orpheus
- https://console.groq.com/docs/speech-to-text
- https://www.twilio.com/docs/voice/api/call-resource
