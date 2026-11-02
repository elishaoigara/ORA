# ORA companion 2.1 setup

Deploy the ORA backend commit before installing the new Android build. Existing Neon workspace data is extended automatically; no SQL migration or new always-on worker is required. Keep the existing Render start command.

## Remote weather and push notifications

1. In Firebase, register Android package `com.app.oraandroidcompanion`. Download its `google-services.json`.
2. In the Expo project `leo333/ora-android-companion`, add an EAS **file** environment variable `GOOGLE_SERVICES_JSON` containing that downloaded file for the build's environment (preview profile normally uses preview). The app config reads its path. Do not paste a service-account private key into this file or commit one.
3. Run `npx eas-cli credentials --platform android` and configure FCM V1 credentials using the Firebase service-account JSON. That private credential belongs in EAS, never in the APK or repository.
4. Set a new random secret of at least 32 characters as `ORA_CRON_TOKEN` in Render. Use a separate secret from the owner access key. Add the same value as the ORA repository Actions secret `ORA_CRON_TOKEN`. Add Actions secret `ORA_BACKEND_URL` = `https://ora-oovf.onrender.com`.
5. The `Companion weather and Telegram alerts` workflow runs twice hourly; use Actions → Run workflow for the first test. Missing or invalid scheduler secrets fail visibly with setup guidance. GitHub scheduled workflows can be delayed and consume Actions minutes; an external HTTPS scheduler can instead POST the same endpoint with `Authorization: Bearer <ORA_CRON_TOKEN>`. Do not run two independent schedulers unnecessarily. No exact delivery-time guarantee.
6. If Expo enhanced push security is enabled, set `EXPO_ACCESS_TOKEN` in Render as well.
7. In the new app: Today → Alert inbox → Enable notifications → Test local notification → Register / repair remote push → Queue remote push test. Remote tests obey quiet hours. Run the workflow and sync the app to inspect delivery state.
8. Choose a city or explicitly share approximate location in Weather awareness. Coordinates go to the ORA backend and Open-Meteo for forecasting. Shared phone locations expire after 24 hours; saved cities remain until disabled. Disabling location permission clears location-based weather. Choose a saved city for updates when the app stays closed.

Weather is forecast guidance, not an official severe-weather warning service. Forecasts cache for one hour; morning/evening summaries and threshold guidance are deduplicated to two daily updates per phone. Quiet hours apply to remote alerts; explicitly timed local task reminders still sound. Expo receipts report provider acceptance, not whether a human saw the notification. Check failed receipt states in the inbox. Invalid tokens are removed; use Register / repair after fixing credentials. An ambiguous transport failure may cause a duplicate push, but the inbox has one record.

## Rebuild

```powershell
git pull origin main
pnpm install --frozen-lockfile
npx eas-cli build --platform android --profile preview
```

The native date/time picker is part of ORA's existing native module. An old APK or Expo Go cannot load that method. The SDK dependencies have not changed.

## Included improvements

- Notification health, local test, remote registration with hourly opt-in retry, delivery receipts, retries, separate weather/update channels, privacy previews, persistent alert inbox.
- Task changes persist in the offline outbox before network requests and schedule from the local snapshot. Phone-context upload errors no longer block reminder scheduling.
- Done, Snooze 10 minutes and Open actions; correct task IDs/version checks. Actions open the app and respect biometric authentication when enabled.
- Task editor with native date/time picker, priorities, overdue labels, recurring daily/weekly tasks. Recurring tasks advance on completion, using fixed 24-hour / seven-day intervals, not daylight-saving-aware calendar rules.
- Home task briefing, searchable conversations and memories, editable/pinned/categorized memories, voice-speed choices.
- Biometric app lock, notification content privacy, server alert history capped at 500 entries/30 days, local history capped at 100; clear controls.

Local history records notifications observed by the app or still present in Android's notification tray. It cannot recover notifications dismissed while the app was terminated. Remote alerts remain on the server. App lock is an interface gate; it does not encrypt all cached AsyncStorage data. Fingerprint enrollment changes can invalidate the lock key; disconnect and re-pair to recover. Revocation stops future server sends, but already handed-off notifications cannot be recalled.

On Android 12+, use **Allow precise reminder timing** in the notification center and grant **Alarms & reminders** access for exact task timing. If scheduling fails, grant this access and sync again; the task remains saved.

## Physical-device acceptance checks

Test local notification after five seconds with ORA foregrounded, backgrounded and the screen locked. Create a reminder in airplane mode, restart the app, then reconnect and verify there is only one task. Complete and snooze from the notification. Check native date/time selection, recurring completion, biometric unlock/cancel/recovery, push while closed, weather opt-out and quiet hours. Check battery saver and Android channel settings if notifications are delayed. Force-stopping Android apps can suppress delivery until reopened.

Not added in this release: streamed chat replies, full Markdown rendering, continuous background location/geofences, hands-free listening, or automatic calendar conflict analysis. Existing explicit voice, calendar and context-sharing controls remain available.
