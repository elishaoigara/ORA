# ORA tools and GitHub workspace

One shared tool runtime on Render serves web and Android. Open **Tools & GitHub** on web or **Work tools & GitHub** on Android. Chat can call read tools and prepare write approvals; review approvals in Tools & activity. Results and history synchronize through the existing workspace. No schema migration is needed.

## Start here

1. Deploy the latest ORA backend commit using the existing start command. Deploy the web commit through Vercel.
2. Configure only the connections you want below. A tool displays **Needs connection** when its server credentials are missing; ORA cannot access your connected ChatGPT GitHub account automatically.
3. Select a repository in Tools & GitHub and try Overview, Files and Builds. Ask: “Inspect ORA's recent failed build and explain the failing steps. Cite the evidence.”
4. Rebuild and install the Android companion for the new screen and native clock handoff. Existing pairing continues to work.
5. Read a pending change's exact diff and target before approval. GitHub changes create a fresh `ora/<action-id>` branch and a draft PR, never merge or overwrite main.

## GitHub connection — configure in Render

Set `GITHUB_TOKEN` to a fine-grained personal access token limited to your selected repositories. Set `ORA_GITHUB_REPOS` to a comma-separated allowlist, for example:

```
elishaoigara/ORA,elishaoigara/ora-android-companion,elishaoigara/Nia
```

Select only repositories you own or are authorized to connect. Required read permissions: Metadata, Contents, Issues, Pull requests, Actions and Checks. For approved issue/comment/PR changes, enable Issues write, Pull requests write and Contents write. Organization approval or SSO authorization may also be required. Use an expiring token and replace it in Render when it expires. Never put it in Vercel public variables, Expo public variables, chat, or the app bundle.

Capabilities: allowed-repository list, overview, recent commits, file tree, text file reads, repository-scoped code search, issues/PRs, PR file patches, workflow runs, job steps and check annotations. The tool does not download or execute build logs. A failure without annotations may require opening the returned GitHub source link and sharing the relevant log excerpt.

Proposed code changes require a current base SHA, one to five regular text files, at most 30,000 characters per file and 60,000 in total. ORA shows a unified diff before approval and checks the base again before publishing. Credential files, symlinks, deletions and workflow edits are not supported by this patch tool. The PR is marked draft and explicitly says it has not been tested by ORA's runtime. Use your repository's CI before merging. Code execution, dependency installation, merging, deployments and broad refactors are separate capabilities, not implied by this assistant.

## Google Calendar and Gmail

Set `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `GOOGLE_REFRESH_TOKEN` in Render. These must represent the Google account you intend ORA to use. Enable Gmail API and Google Calendar API in that OAuth client's Google Cloud project. Obtain an offline-access refresh token through Google's OAuth flow (the OAuth Playground with **Use your own OAuth credentials** is one setup option). The application does not currently provide an interactive Google sign-in button.

Request only needed scopes: Calendar events and free/busy access for scheduling; Gmail read-only for search/read, compose for drafts, and send for sending. Your refresh token must cover the enabled features. Scope verification/testing-mode rules depend on your Google OAuth configuration; a token obtained in testing mode may expire and need replacing. See the official scope documentation. Credentials are used server-side only.

Calendar tools list events and free intervals in an explicit, timezone-aware interval of at most 31 days. Event creation requires review and does not add invitees. Gmail search returns up to five messages; message reads return plain text/snippet without attachments. Draft creation and sending require separate explicit approvals with the recipient, subject and body shown. Sending is never retried automatically after an ambiguous failure.

## Research

Set `TAVILY_API_KEY` in Render for live search, source collection and public-page extraction. This is an external service with its own quota/billing. Queries and chosen page URLs are sent to Tavily. Do not include secrets or private material in research requests. `research.sources` returns up to six distinct HTTPS sources with titles, short excerpts and available publication dates. Open primary sources and check important claims before publishing; excerpts can be misleading or stale. ORA does not log into websites or run a remote browser.

## Files that ORA can make and revise

- `documents.create`: supply a title, text and optional `format` (`md`, `txt`, `docx`, `pdf`; default `md`). Markdown style headings and `-` bullets become structured DOCX/PDF paragraphs. `documents.list` and `documents.read` show saved source and version; `documents.edit` replaces text after checking that version.
- `presentations.create` and `presentations.edit`: `slides` is a JSON array of `{"title":"...","bullets":["...", "..."]}`. Each deck has 1–15 slides with at most six bullets per slide. The downloadable result is a real `.pptx` file.
- `spreadsheets.create` and `spreadsheets.edit`: `headers` is a JSON array of unique column names, and `rows` is a JSON array of arrays with the same length. Up to 20 columns and 200 rows are accepted. XLSX text beginning with `=`, `+`, `-` or `@` stays text rather than executing as a formula. Calculations belong in the separate calculator/data tools.

Every create/edit is an approval card containing the exact source. A version change during review blocks an edit. ORA keeps at most 20 files and renders binary exports only when an authenticated web or phone client downloads them (3 MB output limit). The app stores source content, not an original uploaded PDF or DOCX layout. Uploaded PDFs can be revised from extracted text, producing a newly rendered layout. Web and Android show Saved files for later downloads. Android asks for a storage folder; an updated APK is needed for the export action. No database migration or public file host is required. DOCX/PPTX/XLSX/PDF rendering adds `python-docx`, `python-pptx`, `openpyxl` and `reportlab` to the Mini backend requirements.

## Tools available without new external credentials

- Tasks: list, create, edit, complete and delete with version checks and approval for writes.
- Personal knowledge: search relevant memory/document excerpts with source names; propose saved memories.
- Documents, presentations and spreadsheets: create, read, versioned edits and authenticated exports as described above.
- Calculator: a bounded arithmetic parser, never arbitrary code execution.
- CSV analysis: numeric counts, totals, means, minimums and maximums, up to 1,000 rows / 50 columns of supplied CSV. It is not a general spreadsheet editor.
- Phone handoffs: prepare SMS, dialer, map and browser links. Android can also open the clock app to confirm timers and alarms; install the new APK. Handoff does not mean a message was sent, a call was made, or an alarm was confirmed.
- Weather: read stored forecasts with timestamps or request an explicit coordinate forecast through Open-Meteo. Existing weather alert settings still apply separately.
- Notification digest: fresh consented notification context; each phone sees its own captured context. No unrestricted reading of other apps.
- Briefing: current task priorities, overdue counts and stored weather.
- Routines: save up to three bounded read steps, run on demand, inspect results, and disable. Scheduled daily routines are created from a paired phone with an account-timezone hour. The existing external companion tick runs them and queues an alert; at most two routines are processed per tick. Quiet hours defer them. The scheduler is approximate, and a failed routine is not silently rerun or expanded into writes.

## Examples to ask ORA

- “Read ORA's main branch, find how reminders are scheduled, and explain the request flow with file references.”
- “Inspect Nia's recent builds. Show the failed steps and annotations; don't assume a cause without evidence.”
- “Read this file and prepare a small fix as a draft pull request. Show the full diff first.”
- “Find time for a 90-minute coding session tomorrow, then prepare a calendar event.”
- “Search my saved notes for our hosting decision and turn the answer into a Markdown document.”
- “Search my Gmail for this client's latest email and draft a reply for review.”
- “Create a morning routine with my task briefing, saved weather and ORA's latest build status.”
- “Research solar container farming in Kenya using current public sources, cite the URLs and prepare a three-page PDF brief for review.”
- “Turn this plan into an eight-slide PowerPoint, then prepare the deck for my approval.”
- “Build an XLSX startup budget with columns for cost, frequency and notes. Keep user-entered text literal.”

## Controls, limits and recovery

The web owner can disable individual tools. Disabling also blocks pending approvals. GitHub access has a server allowlist in addition to token permissions. Approval records expire after 30 minutes and cannot be changed in place. Duplicate approvals do not resend external writes. If a write returns **needs review**, check the external service before preparing a replacement: an interrupted multi-step GitHub action may have left a branch or commit even if the PR was not created.

Tool history is capped at 200 records / 30 days, and 150 new executions per day. Input, output and provider response sizes are bounded. Chat uses at most three model responses and two rounds of bounded tool calls; extra model calls increase provider usage compared with the previous single-call chat. Tool output is not a guarantee of correctness; truncated files/diffs must be inspected further before broad conclusions. Workspaces and results contain private data; existing owner/device authentication protects the API. Tokens are never returned by connection status.

Validation in this implementation uses mocked provider responses and checks actual approval/state behavior. Live Google, GitHub and Tavily requests require your credentials and a deployment smoke test. The backend never executes repository code. Native clock behavior must be checked in the rebuilt APK on a physical device.

Official references:
- https://docs.github.com/en/rest/git/trees
- https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens
- https://developers.google.com/workspace/gmail/api/auth/scopes
- https://developers.google.com/workspace/calendar/api/auth
- https://docs.tavily.com/documentation/api-reference/endpoint/search
