# Awareness Permission Research

## Official sources consulted

| Topic | Key finding | Source |
|---|---|---|
| Android notification permission | Android 13+ requires the user to grant `POST_NOTIFICATIONS`; request it only when the user activates the feature and handle denial gracefully. | [Android notification runtime permission](https://developer.android.com/develop/ui/compose/notifications/notification-permission) |
| Android runtime permissions | Permission requests should be tied to a user action, include a clear rationale, remain optional, and gracefully degrade when denied. | [Android runtime permission workflow](https://developer.android.com/training/permissions/requesting) |
| Expo notifications | A native/development build is required for Android remote push notifications; create an Android notification channel before requesting permission or obtaining a push token. | [Expo Notifications documentation](https://docs.expo.dev/versions/latest/sdk/notifications/) |
| Expo location | Background location requires separate foreground and background permission, a build-time configuration change, and a global background task. Android background tracking may stop when an app is terminated. | [Expo Location documentation](https://docs.expo.dev/versions/latest/sdk/location/) |
| Expo task manager | Background task handlers must be defined in global scope and should expose an explicit stop/unregister action. | [Expo TaskManager documentation](https://docs.expo.dev/versions/latest/sdk/task-manager/) |

## Implementation defaults derived from the research

1. No permission request occurs automatically. Each awareness tier uses a separate in-app explanation and user-initiated enable action.
2. Push uses an Android notification channel with non-marketing, user-selected alert classes only.
3. Named-zone routines use event-only ingestion by default. Raw coordinates are not retained for this mode.
4. Continuous location is a separate, clearly labeled opt-in mode with a persistent Android foreground-service notification, visible state, one-tap stop, and a finite retention period.
5. Permission denial leaves pairing, check-ins, and privacy controls functional.
