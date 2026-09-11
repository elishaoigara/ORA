# ORA Projects and Desktop — companion 2.2

This release adds project workspaces, dated and correctable project facts, project chat with selected attachments, signed GitHub event ingestion, connection checks, and a paired desktop job runner. Web and Android use the same authenticated backend and Neon workspace.

## Deploy and rebuild

Keep the existing Render service, Neon DATABASE_URL, owner token, CORS settings and notification credentials. No new database service is required; new collections are initialized as used.

Render uses `backend` as root, installs `requirements-mini.txt`, and starts:

```sh
uvicorn next_api:app --host 0.0.0.0 --port $PORT --workers 1
```

After deploying, `/api/health` keeps `release: ora-mini-2` and adds `work_release: 1.0`, `companion_release: 2.2`. Vercel builds the updated frontend as before.

Android includes new share intent filters and version 2.2.0, so build a new APK:

```powershell
git pull origin main
pnpm install --frozen-lockfile
npx eas-cli build --platform android --profile preview
```

## Projects and memory

Open **Projects & desktop** on web or Android. Create a project with its goal, repository (`owner/name`), branch, next step and blockers. Save before adding facts or attachments. Archive suppresses GitHub alerts without removing the project.

Facts have an explicit source and optional expiry. Correct and Forget are available on both clients. Expired facts remain visibly marked for review but are excluded from project AI context. Forget removes the fact record; an earlier chat quoting that fact remains in chat history. Concurrent project/fact edits return a conflict instead of overwriting newer changes; refresh and reselect the project before editing again.

**Show saved context** displays saved priorities and the last 20 project messages, including messages sent from the other client. It does not claim the recorded branch or goals are live Git state. Ask ORA for a GitHub lookup when live verification is needed. Project chat includes active project facts, recent recorded GitHub events and selected documents. General chat is still available separately.

## Attachments and image analysis

Both clients accept PNG/JPEG, readable PDF (40 pages maximum), UTF-8 text, Markdown, CSV and logs, under 2 MB. Up to three selected documents can accompany a project question. Each selected excerpt is capped at 6,000 characters, with truncation indicated in AI context. The existing 20-document workspace limit applies; remove old documents when needed.

Configure on Render:

- `GROQ_API_KEY`: existing provider key.
- `GROQ_VISION_MODEL`: an image-capable model ID available to your Groq account. Check https://console.groq.com/docs/vision and your provider model list. There is no hardcoded model that may later disappear.

Images are sent to Groq only after the user chooses upload/import. ORA stores a generated description/transcription, not the original image. Image descriptions can be wrong; retain original evidence for important technical decisions. Empty/scanned PDFs return a clear error; share a page as an image instead. Image analysis is capped at 20 attempts/day and four uploads/minute per session.

On Android, use **Share → ORA** from the source app. If the shared item opens in Talk, choose **Attach shared file to a project**. Select a saved project and tap **Import shared file**. Only the first shared file is imported at a time. The file picker also works. Sharing does not grant continuous screen access.

## GitHub notifications

1. Configure `GITHUB_TOKEN` and `ORA_GITHUB_REPOS` (comma-separated allowed repositories) on Render. Use repository permissions appropriate for the existing Tools & GitHub features.
2. Generate a random secret of at least 32 characters locally. Save it as `ORA_GITHUB_WEBHOOK_SECRET` on Render. Do not put it in Git or frontend environment variables.
3. In each allowed repository: Settings → Webhooks → Add webhook.
4. Payload URL: `https://ora-oovf.onrender.com/api/v2/work/github/webhook`.
5. Content type: `application/json`. Secret: the same value as Render. Keep SSL verification enabled.
6. Select **Workflow runs** and **Pull requests** events, then save.
7. In ORA, save that repository on a project and enable **GitHub alerts**.

ORA records failed/timed-out/action-required completed workflow runs, and opened/reopened/closed/ready-for-review/review-requested PR events. Verify the GitHub delivery returns HTTP 200, then perform a real test event. ORA verifies the SHA-256 signature, checks the repository allowlist, stores the event, and queues one alert per active phone. Repeated delivery IDs are deduplicated (last 2,000 retained); recent event history is capped at 200.

Push uses the existing Expo/Firebase registration and external companion scheduler. It respects quiet hours and paused/revoked phones. This is queued delivery, not an instant-alert SLA. Webhook handling does no AI inference or push network calls before acknowledging.

**Render Free limitation:** GitHub expects a response within 10 seconds. A sleeping Render service can miss that deadline; GitHub does not automatically redeliver all failed webhook deliveries. Wake ORA, open the webhook's Recent Deliveries, and redeliver a failed event. For reliable unattended event intake, a durable always-available ingress/queue is a separate future deployment. No keep-alive workaround or new paid service is enabled by this release.

## Connection checks

Use **Test connections** on either client. It verifies the workspace can be read, reads the first three allowed GitHub repositories, and checks whether the configured Groq vision model is listed for the supplied key. It does not prove model image inference, webhook delivery, Gmail/Calendar permissions or Expo delivery. Use a real attachment, webhook event, existing Google tool and notification test respectively to validate those paths. Results include HTTP status or a useful timeout/configuration explanation without provider response bodies or secrets.

## Desktop worker installation (Windows)

The runner needs Python 3.10+, Git, and the development tools used by your selected checks (for example Node and pnpm). It is a foreground command-line worker, not a Windows service or unrestricted remote shell.

From your local ORA repository:

```powershell
cd desktop
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item worker.example.json worker.local.json
notepad worker.local.json
```

Edit the allowed repository paths and command arrays. The example uses `C:\Users\USER\ora-android-companion`, installs its frozen dependencies into a new worktree, then runs TypeScript. Commands are configured locally; the server selects only advertised repository/check names. Set up only trusted repositories: setup and check commands execute repository code with your local user permissions. A Git worktree isolates changes from your original checkout; it is **not an operating-system security sandbox**.

On ORA web, **Projects & desktop → Create worker pairing code**, then:

```powershell
.\.venv\Scripts\python.exe worker.py --pair
.\.venv\Scripts\python.exe worker.py
```

Enter the one-time code at the hidden prompt. It expires after ten minutes. The worker token is saved using the OS credential vault via keyring, not in config or Git. Worker pairing lasts 90 days; revoke on web or pair again when needed. If you change the advertised repositories/checks, revoke and pair again. Stop with Ctrl+C. Jobs wait while the PC is off.

To use it:

1. Select a project, computer, local repository and configured check on web or Android.
2. Optionally supply a standard Git unified diff and the exact 40-character base SHA. Patches are restricted to at most five existing regular text files; hidden, credential, binary, symlink, create/delete and rename operations are rejected.
3. Queue the job. Review the exact commit, commands, setup and patch printed on your computer; type `RUN` to approve.
4. ORA creates a separate `ora/desktop-<job ID>` worktree, applies the patch, and runs the chosen check with a timeout.
5. Review the displayed redacted output and diff; type `SHARE` to send that evidence to your private ORA workspace. Otherwise only the check exit status is uploaded. Inspect output yourself: pattern-based redaction cannot guarantee removal of every secret.
6. Refresh Desktop activity on either client. Passed means the configured command exited zero; it does not mean all project tests or an Android APK build were run.

The runner journals each claim locally before execution. Reports retry after disconnection, but a claimed job is never automatically executed again. An interrupted or hour-old unreported job becomes `needs_review`; inspect its worktree before queuing a fresh job. Cancelling a queued job prevents execution; stop a running process on the computer. Revoking pairing blocks further backend access but cannot remotely stop a process already executing.

## Publish reviewed code as a draft PR

Install GitHub CLI and run `gh auth login` locally. After a successful patch job, copy its job ID from Desktop activity:

```powershell
.\.venv\Scripts\python.exe worker.py --publish JOB_ID
```

The runner verifies the worktree HEAD and complete diff still match the successful check, requires no staged or untracked files, shows the GitHub repository/base/branch/diff, and asks you to type `PUBLISH`. It commits tracked changes, pushes the new branch and opens a draft PR. It does not merge. A publish attempt is recorded before network writes, so an ambiguous failure cannot silently cause another publish; inspect GitHub and local Git before a manual recovery. PR URL is printed and saved in the local receipt. The shared job status describes the check; it does not claim the PR was merged or deployed.

This version accepts explicit patches; it does not autonomously refactor a project. Ask the existing GitHub assistant to investigate and propose a fix, review it, then test an exact patch here. AI-selected local commands, background Windows service installation and automatic merges are not enabled.

## Verification performed

Backend regression and new route tests cover auth boundaries, project conflicts and sync, memory expiry/corrections, attachment selection, provider-failure handling, signed/deduplicated GitHub events, worker claims/reports/revocation and abandoned jobs. Desktop tests exercise a real temporary Git repository, isolated worktree, patch and passing check, plus refusal/validation paths. Android is checked with TypeScript; web is bundled for syntax/import verification. Native APK builds, Windows credential-vault behavior, Windows command dispatch, live Groq inference, live push and GitHub publication still require deployment/device acceptance checks.
