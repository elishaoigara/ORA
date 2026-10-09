# What ORA Mini can actually do

The product goal is a useful personal AI, not a claim of unrestricted phone control.

| Area | This rebuild | Boundary |
| --- | --- | --- |
| Web + phone | One durable workspace, shared conversations/tasks/memory/documents | Sync on open, return to foreground and every 60 seconds while visible |
| Offline | Cached phone workspace, drafts, queued personal task/memory changes | AI inference and approvals require a connection; conflicts stay queued for review/discard |
| Reminders | Android-local scheduling for 50 upcoming synchronized tasks | New web reminders require phone sync; OS restrictions may delay delivery |
| Daily nudge | Optional recurring local planning prompt | Generic prompt, not an AI-written live morning briefing |
| Voice | Push-to-talk transcription and installed voice selection | No always-listening wake word; not guaranteed offline TTS on every speech engine |
| Intelligence | Grounded context, bounded history, task/memory/message tools and suggestions | Live research requires Tavily; there is no local offline model or unrestricted autonomous execution |
| Notifications | Allowlisted native listener, redacted previews, bounded queue and synchronization | Cannot read an app's private database or unrelated message history; not real-time cloud monitoring |
| Contacts | Pick and confirm one contact | No silent address-book upload |
| Calendar | Review/share remaining events today from phone calendars | No automatic Google OAuth sync in the Mini runtime |
| Location | User-triggered approximate location snapshot | No continuous/background tracking in this version |
| Battery | User-triggered device battery snapshot | No continuous health monitoring |
| Files | User-picked PDF/text/Markdown, extracted text shared between clients | No full-filesystem scan, OCR, image understanding or video analysis |
| Work files | Reviewed creation and versioned edits; authenticated DOCX/PDF, PPTX and XLSX downloads on web/phone | Generated layouts use bounded text and JSON specifications; uploaded files retain extracted text rather than original layout |
| Public research | Tavily-backed search with source links when a server key is configured | Search excerpts are evidence to verify, not a guarantee of factual accuracy; no authenticated browsing |
| Outgoing messages | AI draft, approval, OS share sheet | User selects/verifies the recipient and sends; ORA never claims sending happened |
| Privacy | Per-source consent, pause, deletion, device revocation, browser export | An offline phone cannot receive remote revocation until reconnecting |

## Storage and retention

The active workspace holds at most 500 tasks, 300 recent conversation turns, 200 memories, 100 action cards, 60 phone context events and 20 documents (50,000 extracted characters each). Phone context is excluded from sync/model context after 24 hours and purged on the next mutation. Read-only requests do not run a persistent cleanup daemon. User-directed deletion immediately removes active phone context. Provider backups and database logs follow the provider's retention settings.

Android's saved workspace and outbox live in app-private AsyncStorage. The access credential lives in SecureStore. The native notification queue is app-private and bounded to 30 events; redaction is heuristic, not a guarantee that all sensitive text is removed. Use metadata-only access in future refinements if broader sources are added; this UI configures redacted previews only. Logout clears the Mini cache/outbox and cancels local reminders. Browser caches are tab-scoped.

Chat and tool reasoning inputs are sent to your configured DeepSeek account. Voice recordings and image-analysis uploads still use Groq when configured. Only confirmed memory, selected recent phone context, a small task snapshot and relevant document excerpts enter context. Uploaded/phone content is explicitly marked untrusted; prompts inside it must not grant tool authority. Model-generated tasks, memories and outgoing drafts remain approval-gated.

## Legacy functionality

Old Gmail/Calendar/Drive OAuth, M-Pesa ingestion, Telegram polling, WhatsApp sidecar, knowledge agents and roadmap modules remain in source for reference and rollback. They are not loaded by `next_api.py`. Do not advertise them as connected to the new durable workspace. The new phone's Gmail/WhatsApp notification awareness is distinct from direct service integrations.

## What comes after the physical-device gate

The next meaningful expansion is durable provider OAuth and event-based synchronization, then an Android background worker with a battery-aware, consented outbox. Full-time cloud intelligence requires an always-running service or another event platform; Render Free cannot supply that property. Additional phone powers must be implemented and tested individually through Android-supported APIs. Do not add accessibility-service automation or bypass app isolation to simulate “access to everything.”

Mutation receipts are retained in a separate private table to prevent duplicate operations after reconnects; they can contain the original operation response. Deleting an active memory or document removes it from the active assistant context, not from provider backups or historical conversation/receipt records. A full retention and history-erasure policy is separate work before any multi-user release.

