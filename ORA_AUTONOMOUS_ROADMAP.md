# ORA Autonomous Personal AI Roadmap

## Current position

ORA is no longer a blank prototype. It has a working FastAPI backend, React/Vercel frontend, Google OAuth, Gmail/Calendar/Drive connectors, chat, tasks, goals, memory, knowledge documents, alerts, weather, M-Pesa ingestion, Telegram notifications, and an autonomous scheduler. The latest Render logs show that the service is alive, the frontend is reaching the API successfully, and Google OAuth completed successfully at 07:17 UTC on August 20, 2026.

The immediate problem is not a lack of features. It is that the product currently exposes more surfaces than its execution and memory model can reliably support. A Jarvis-level assistant should feel coherent, selective, trustworthy, and capable of completing work—not like a collection of disconnected dashboards and periodic polling jobs.

## Keep, consolidate, and remove

| Decision | Current area | Recommendation | Reason |
|---|---|---|---|
| Keep and strengthen | Chat | Make this the primary command center for every task, query, approval, and follow-up. | The assistant should have one natural control surface. |
| Keep and strengthen | Gmail, Calendar, Drive | Keep these as ORA’s first-party personal context layer now that Google OAuth works. | They provide high-value context for planning and action. |
| Keep and strengthen | Tasks and Goals | Merge them into one execution model: goals contain projects; projects contain tasks; ORA tracks next actions and deadlines. | Autonomous behavior needs a clear objective hierarchy. |
| Keep and strengthen | Memory | Retain profile, preferences, events, and learned facts, but add confidence, source, expiration, and user controls. | Memory must be useful without becoming invasive or incorrect. |
| Keep and strengthen | Alerts and proactive checks | Retain only high-signal reminders, deadline warnings, meeting preparation, and meaningful changes. | Proactivity is valuable only when notification noise is low. |
| Keep, but defer | Knowledge/RAG | Keep document ingestion and search, but make it a deliberate source used for questions and work—not an always-running background process. | It is useful, but it should not compete with personal context. |
| Optional | Weather | Keep as a small context provider if weather affects your decisions; otherwise disable its notifications. | It is useful only when tied to an action or routine. |
| Optional | M-Pesa | Keep only if you actively use the financial summaries and alerts. | It adds security and maintenance cost. |
| Defer or remove | WhatsApp sidecar | Disable until the sidecar is stable, authenticated, and backed by tests. | A broken message bridge creates reliability and privacy risk. |
| Remove from active product | Research, News, Content, Code, Agent Bus | Remove from the deployed frontend and stop polling their absent endpoints. | The latest source tree already removed these surfaces; the current Vercel deployment is stale because it still requests `/api/news/unread/count` and `/api/bus/*`. |
| Remove | GitHub context collection | Keep GitHub as a developer integration only if explicitly needed; do not run it in the autonomous personal loop. | It produces noise and does not directly improve daily personal assistance. |
| Remove | Keep-alive behavior | Remove `wa_ping` as a Render anti-sleep mechanism and stop external uptime polling. | It consumes free-tier hours without improving assistant quality. |

## The target experience

ORA should operate as a **personal operating system** with five connected responsibilities:

1. It understands your current situation from calendar, inbox, tasks, goals, documents, location, and explicit preferences.
2. It maintains a small, trustworthy memory of who you are, what matters, and what you have committed to.
3. It turns intentions into concrete next actions and follows up until they are completed, deferred, or explicitly cancelled.
4. It can perform safe actions across Google and messaging services, but asks for approval whenever an action is consequential.
5. It communicates selectively through the channel you prefer, with a concise explanation of what it noticed, why it matters, and what it did.

The assistant should not attempt to autonomously do everything. It should autonomously handle **low-risk, reversible, and clearly authorized work**, while requiring confirmation for sending messages, deleting data, spending money, changing appointments, or making commitments on your behalf.

## Prioritized build sequence

### Phase 1: Make the deployed product truthful and quiet

Deploy commit `8905ae5` to Render and allow Vercel to redeploy from the same GitHub branch. The scheduler fix now skips Drive and Gmail jobs when Google is unavailable, and the agent and proactive checks skip Calendar/Gmail context without repeatedly logging authorization warnings. Since Google is now connected, these jobs should resume normally after Render runs the new commit.

Verify that the Vercel deployment no longer displays Research, News, Content, Code, or Agent Bus navigation. The latest local frontend contains only Dashboard, Chat, Inbox, Tasks, Alerts, Knowledge, and Memory. The 404s in the supplied log prove that the deployed Vercel build is behind the current repository.

Success criteria are simple: no `/api/news/*` or `/api/bus/*` requests, no `github failed` messages, Google summary returns 200, Calendar events appear, Drive sync succeeds, and a fresh Render deployment is using commit `8905ae5`.

### Phase 2: Build a unified personal context engine

Create one `PersonalContext` object assembled from the highest-value sources: today’s calendar, unread/high-priority email, active tasks, overdue tasks, goals, recent conversation, relevant memory, and relevant knowledge documents. Each item should include a source, timestamp, confidence, importance, and freshness.

The agent should not call every connector on every cycle. Use short-lived caching, change detection, and source-specific refresh intervals. Calendar may refresh frequently, Drive less frequently, and document embeddings only when a document changes. This will reduce latency, API calls, rate-limit risk, and scheduler noise.

### Phase 3: Replace the current agent loop with an execution cycle

The current autonomous loop gathers context, makes simple rule decisions, and sends notifications. The next version should create an explicit work cycle:

```text
Observe → Prioritize → Propose → Approve if needed → Execute → Verify → Remember
```

Every proposed action should have an ID, reason, target, parameters, risk level, required approval, status, retry count, result, and timestamp. This makes ORA capable of following through instead of merely announcing that something might matter.

Examples of autonomous low-risk actions include creating a task from an email, preparing a draft reply without sending it, adding a private note, summarizing a document, and reminding you about an approaching commitment. Examples requiring confirmation include sending an email, creating an external calendar invitation, deleting an email or event, sending a WhatsApp message, or initiating M-Pesa activity.

### Phase 4: Unify goals, projects, and tasks

Keep the existing Goals and Tasks features, but introduce a clear hierarchy. A goal should have projects or milestones; each project should have ordered next actions; each task should have an owner, due date, priority, status, and source. ORA should be able to answer: “What is the next action?”, “What is blocked?”, “What am I neglecting?”, and “What can I finish in the next 30 minutes?”

Add daily planning and end-of-day review as first-class workflows. The morning brief should propose a realistic plan from calendar constraints and task priority. The evening review should summarize completed work, unfinished commitments, and the next best action—not merely send a generic notification.

### Phase 5: Make memory deliberate and safe

The current memory layer has profile, preferences, events, and learned facts. Keep it, but change the write policy. ORA should store a fact only when it is explicitly stated, repeatedly observed, or confirmed by you. Each memory item should record its source, confidence, last-confirmed time, sensitivity, and expiration policy.

Add user-facing controls to inspect, edit, forget, and correct memory. Sensitive facts should never be inferred casually. Conversation history should remain separate from durable memory; not every conversation message should become a permanent fact.

### Phase 6: Build a typed tool and approval system

The existing tool registry is a starting point, but the assistant needs a smaller, typed tool surface. Each tool should declare its name, input schema, risk class, idempotency key, timeout, retry policy, and approval requirement.

Use four risk classes:

| Risk class | Example | Approval |
|---|---|---|
| Read-only | Read calendar, search Gmail, retrieve a document | No approval |
| Reversible personal change | Create a private task, save a draft, add a memory candidate | Usually no approval, with undo |
| External communication | Send email, send Telegram/WhatsApp, invite someone to a meeting | Always confirm unless explicitly pre-authorized |
| Irreversible or financial | Delete data, send money, make a purchase, submit a formal request | Always confirm, show exact parameters |

This system is the difference between a useful Jarvis and an unsafe automation script.

### Phase 7: Add voice only after the core is reliable

Voice is valuable for a Jarvis experience, but it should come after the execution and approval model works through text. Add push-to-talk first, then speech-to-text, then spoken responses. Avoid always-listening microphones until privacy, wake-word behavior, interruption handling, and local data retention are designed properly.

The first voice version should support commands such as “What is my next meeting?”, “Add a task,” “Summarize my unread important emails,” and “Prepare a reply.” It should read back the planned action and ask for confirmation when required.

### Phase 8: Reliability, observability, and cost control

Add a job-status screen showing the last run, next run, duration, result, and error for each scheduled job. Add an action ledger showing what ORA proposed, what it executed, and what it verified. Add rate-limit handling and circuit breakers for external services.

The health endpoint should report component status without exposing secrets: database, Google authorization, scheduler, notification channel, LLM availability, and storage. Add an internal diagnostic endpoint protected by the ORA token.

## Recommended next three implementation tasks

The next concrete work should be:

1. Deploy commit `8905ae5` to Render and redeploy the Vercel frontend so the live UI matches the repository.
2. Add a unified `PersonalContext` and action ledger, then make the agent produce proposed actions instead of directly sending every notification.
3. Add approval-aware Gmail and Calendar actions, beginning with draft replies and private task creation before enabling external sends.

Do not add more integrations yet. The highest-value improvement is not another connector; it is making ORA reliably understand context, choose one useful next action, execute it safely, and remember the result.

## References to the current implementation

[1]: https://github.com/elishaoigara/ORA/tree/main/backend/agent.py "ORA autonomous agent"
[2]: https://github.com/elishaoigara/ORA/tree/main/backend/ora_scheduler.py "ORA scheduler"
[3]: https://github.com/elishaoigara/ORA/tree/main/backend/conversation_history.py "ORA conversation history"
[4]: https://github.com/elishaoigara/ORA/tree/main/backend/intelligence/learning_engine.py "ORA learning and memory"
[5]: https://github.com/elishaoigara/ORA/tree/main/backend/tool_registry.py "ORA tool registry"
[6]: https://github.com/elishaoigara/ORA/tree/main/frontend/src/App.jsx "ORA frontend application shell"
