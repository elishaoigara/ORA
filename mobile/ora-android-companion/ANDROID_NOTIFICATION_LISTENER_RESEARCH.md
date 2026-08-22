# Android Notification Listener Constraints

Source: [Android `NotificationListenerService` reference](https://developer.android.com/reference/android/service/notification/NotificationListenerService), retrieved 2026-08-22.

- A notification listener receives system callbacks when notifications are posted, removed, or ranking changes.
- The Android manifest must declare a non-exported service protected by `android.permission.BIND_NOTIFICATION_LISTENER_SERVICE` with the `android.service.notification.NotificationListenerService` intent action.
- The implementation must wait for `onListenerConnected()` before using listener operations; the platform may disconnect it later.
- Android supports default filter metadata for conversations and alerting notifications and disabled filter metadata for ongoing and silent notifications. ORA should default to conversations and alerting only, then enforce its own app allowlist and redaction server-side.
- Access is user-controlled in Android system settings. The Companion must direct the user to Settings, show a disabled state until connected, and offer a local/server stop path.
- The listener must never cancel, snooze, or reply to third-party notifications automatically. ORA will ingest reviewable copies only after explicit capability consent.

## Expo build integration

Expo’s official Modules API guidance confirms that an existing Expo application can host a local Expo module created with `npx create-expo-module@latest --local`. A local module contains Android and TypeScript source and is autolinked into a standalone build. Expo’s configuration-plugin tutorial further confirms that a local module can use a synchronous config plugin to inject native Android manifest configuration during Continuous Native Generation/prebuild. ORA will use this route for the protected notification-listener service, so Expo Go cannot exercise the listener; a newly published standalone APK is required.

Sources: [Expo Modules API: Get started](https://docs.expo.dev/modules/get-started/) and [Expo config plugin and native module tutorial](https://docs.expo.dev/modules/config-plugin-and-native-module-tutorial/), reviewed 2026-08-22.
