# ORA Android Companion — Interface Design

## Product purpose

The ORA Android Companion is a consent-first bridge between the user’s Android phone and the existing ORA backend. Its first release pairs one device securely, keeps a visible connection state, stores only a revocable device credential, and gives the user clear control over future alert, notification, and location capabilities.

The app is designed for **portrait 9:16 use**, one-handed interaction, and mainstream Android conventions. It must remain useful even when no sensitive data source is enabled.

## Screen list

| Screen | Primary content and functionality |
|---|---|
| **Home** | Connection status, paired device name, last sync, a primary **Connect ORA** action when unpaired, and a global awareness pause control when paired. |
| **Pair ORA** | HTTPS backend address, pairing code entry, validation status, device-name confirmation, and a clear explanation that the companion receives a device-scoped token rather than ORA’s master token. |
| **Awareness** | Separate, opt-in cards for push alerts, named-zone routines, and continuous location. Every card gives plain-language data scope, native permission rationale, a visible enabled state, and a direct stop action. No permission is requested automatically. |
| **Privacy & Device** | Device identifier, last check-in, consent summary, retention explanation, immediate precise-location deletion, reconnect action, and a destructive **Revoke device** control with explicit confirmation. |
| **Pairing result** | A success state with the paired name, current backend, and the next recommended safe action: enable push notifications or test a device check-in. |

## Key user flows

1. **First pairing:** User opens Home → taps **Connect ORA** → enters the HTTPS ORA backend address and short pairing code → confirms the device label → companion exchanges the code for a device-scoped token → token is stored securely → Home displays **Connected**.
2. **Device health:** User opens Home → sees last successful sync and backend readiness → taps refresh → companion fetches its device record and updates the status.
3. **Privacy control:** User opens Privacy & Device → reviews what is currently enabled → taps **Revoke device** → confirms → companion clears the locally stored credential and returns to an unpaired state.
4. **Future awareness opt-in:** User opens Awareness → reads the purpose and data scope for a capability → enables a feature only after the corresponding backend consent and native permission flow has been implemented.
5. **Named-zone routine:** User enables Named-zone routines → grants Android foreground then background location → saves current place as Home, Work, or Commute → phone sends only entered/left events.
6. **Continuous location:** User enables Continuous location → reviews persistent Android notification and 24-hour retention → grants permissions → sees the foreground service notification → stops it from Awareness or deletes retained samples from Privacy.

## Interaction and accessibility

Primary controls are at least 44 px high, use high-contrast labels, show loading and error states inline, and use destructive red styling only for revocation. The pairing form supports normal keyboard submission. Status is always expressed in text and color: **Connected**, **Needs pairing**, **Backend unavailable**, **Paused**, or **Revoked**.

## Color choices

The companion inherits ORA’s dark operational identity while using clear Android status colors:

| Token | Color | Role |
|---|---|---|
| `background` | `#08110F` | Near-black green screen background |
| `surface` | `#10201C` | Elevated cards and form surfaces |
| `primary` | `#00E6A7` | ORA action and active connection accent |
| `foreground` | `#F2FFF9` | Main text |
| `muted` | `#95AAA3` | Supporting labels and timestamps |
| `border` | `#1D3931` | Card and divider boundaries |
| `success` | `#38D996` | Confirmed connection and safe state |
| `warning` | `#F5B94C` | Unavailable or attention-required state |
| `error` | `#F87171` | Failed connection and revoke action |
