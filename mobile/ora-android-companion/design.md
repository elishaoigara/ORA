# ORA Android Companion — Command Center Design

## Product purpose

ORA Companion is a **private mobile command center** for the paired ORA assistant. It gives the user a calm, glanceable view of the day, captures information deliberately, presents only reviewable proposed actions, and makes every awareness source visible, scoped, and reversible.

The design assumes **portrait 9:16**, one-handed Android use, and mainstream Android interaction conventions. The app stays useful with all awareness features off; pairing is never consent for notifications, location, contacts, or imported content.

## Navigation and screen list

| Destination | Primary content and functionality |
|---|---|
| **Today** | Personal greeting, live ORA briefing, top priorities, active goal progress, next commitment, attention items, and one-thumb quick actions for voice note, share inbox, approval queue, and refresh. |
| **Inbox** | Unified, reviewable feed for explicit shares, voice captures, redacted notification events, alerts, and suggested follow-ups. Filters separate Captures, Notifications, and ORA alerts. |
| **Approvals** | A focused queue of proposed Gmail, Calendar, and other externally visible actions. Every card shows what will happen, risk, source, expiry, and explicit Approve / Reject controls. |
| **Activity** | Time-ordered device events, routine transitions, completed tasks, assistant follow-ups, and delivery status. Detail screens explain why an event was retained and when it will expire. |
| **Awareness** | Separate, opt-in controls for push alerts, notification access, named zones, continuous location, contacts, and device health. Each shows data scope, retention, Android permission state, and a stop control. |
| **Privacy** | Global Pause All Awareness, audit/export/delete controls, source-by-source retention, precise-location deletion, notification allowlists, device session details, and revoke-device action. |
| **Pair ORA** | HTTPS backend address, one-time pairing code, device-name confirmation, and clear explanation of the device-scoped credential boundary. |

## Key user flows

1. **Morning command center:** User opens Today → reads briefing and attention items → marks a task done or opens an approval → returns to the next priority without navigating a long dashboard.
2. **Capture deliberately:** User uses Android Share → selects ORA Companion → chooses save as reference, task, or question → sees it in Inbox → confirms, edits, or archives it.
3. **Voice capture:** User holds the microphone control → releases to stop → sees a transcription draft and proposed task/reminder → confirms before ORA stores it.
4. **Approval safety:** User opens Approvals → reads the exact external action → taps Approve & Execute or Reject → result is added to Activity with outcome and timestamp.
5. **Notification awareness:** User enables notification access → is sent to Android Settings → returns to choose allowed apps and content level → ORA receives only the chosen redaction level → every event appears in Activity with a delete path.
6. **Context routine:** User enables a named zone → saves current place as Home, Work, or Commute → ORA receives only arrival/departure event names. Continuous location requires its own consent, foreground notification, retention time, and Stop control.
7. **Global pause:** User opens Privacy → taps Pause All Awareness → all ingestion is rejected server-side and native routines are stopped locally; a clear Resume control remains visible.

## Consent and retention model

| Capability | Default | Data boundary | Retention and stop path |
|---|---|---|---|
| Explicit shares | Off until user shares | Only user-selected text, links, images, or files | Inbox archive/delete at any time |
| Voice notes | Off until press-and-hold | Audio only during an active recording; user confirms transcript | Delete original capture or derived draft |
| Notification access | Off | Per-app allowlist; metadata, redacted preview, or full content chosen individually | Stop in Awareness and Android Settings; delete audit events |
| Named zones | Off | Home/Work/Commute enter and exit events only | Stop in Awareness; remove each saved zone |
| Continuous location | Off | Coordinates and accuracy only during foreground service | 24-hour default; immediate Privacy deletion and Stop |
| Contacts | Off | Selected contacts or on-device matching; no bulk cloud copy by default | Disconnect in Awareness and delete mappings |
| Device health | Off | Battery, charging, network class, and app status; no content | 7-day default with global pause |

## Interaction and accessibility

Primary actions are at least 48 px high and positioned within the lower thumb zone. Each sensitive control uses a short summary first, then an explanatory sheet before Android requests permission. Use inline loading states, plain-language errors, and haptic confirmation only for meaningful transitions. Destructive controls are visually distinct and always require confirmation.

## Visual system

The Companion uses an **operational dark mode** with calm, high-contrast information layers rather than dense “cyber” ornament. Large briefing text, compact status chips, restrained dividers, and consistent cards make the interface feel deliberate and readable at a glance.

| Token | Color | Role |
|---|---|---|
| `background` | `#08110F` | Deep green-black canvas |
| `surface` | `#10201C` | Main cards and bottom navigation |
| `surfaceRaised` | `#162A24` | Attention cards and modal sheets |
| `primary` | `#00E6A7` | Primary actions and active state |
| `accent` | `#4CA7FF` | Information, plan progress, and links |
| `foreground` | `#F2FFF9` | Main text |
| `muted` | `#95AAA3` | Supporting text and time labels |
| `border` | `#1D3931` | Card and list separators |
| `success` | `#38D996` | Safe, connected, complete |
| `warning` | `#F5B94C` | Attention and pending approval |
| `error` | `#F87171` | Failed, revoked, and destructive actions |
