# Build the ORA companion app and put it on your phone

This is the hands-on recipe for turning `mobile/ora-android-companion` into an APK you
install on your own Android phone and pair with the ORA backend you already run.

It assumes the backend is already deployed (see [ORA_MINI_SETUP.md](ORA_MINI_SETUP.md)).
If the backend is not live yet, do that first: the phone pairs against a real HTTPS
backend, and pairing is the step that fails most often when the backend is missing.

**What you get:** an Android app (`com.app.oraandroidcompanion`, display name
"ORA Mini AI") that shares one workspace with the web app — conversations, tasks,
memory, documents, approvals — plus phone-only features: local reminders with no
server needed, Android notification awareness for apps you pick, and explicit
one-shot shares of location, calendar, battery, or a single contact.

**What it is not:** there is no committed APK in this repository. `.apk`/`.aab`
files are never stored in Git, so you compile the app yourself with EAS Build
(cloud, no Android Studio) or Gradle (local). Expo Go cannot run it — the custom
notification listener is native Kotlin.

---

## 0. Prerequisites

| Need | Version / detail | Why |
| --- | --- | --- |
| Android phone | Android 8.0 (API 26) or newer | `minSdkVersion: 26` is set in `app.config.ts` |
| Expo account | Free tier | EAS Build cloud compilation + credentials |
| Node.js | 22 LTS (20.19.x also works; 22.13+ recommended) | React Native 0.85.3 `engines` field |
| pnpm | 9.12.0 (pinned by `packageManager`) | Lockfile is `pnpm-lock.yaml` |
| Working ORA backend | HTTPS URL, `APP_ENV=production` + a database | Pairing needs it live |
| Your ORA owner key | The `ORA_API_TOKEN` value on Render | Only to generate the pairing code in the browser, never typed into the phone |
| *Local build only* | JDK 17, Android SDK compileSdk 36, build-tools 36.0.0 | Gradle 9.3.1 + AGP 8.12 |

You do **not** need Firebase or FCM credentials. Remote push was retired in this
codebase; remote alerts go through Telegram now (see step 8). Local reminders,
the notification listener and all sharing features work without Firebase.

---

## 1. Point the app at your backend (optional but recommended)

The pairing screen defaults to `https://ora-oovf.onrender.com`, taken from
`process.env.EXPO_PUBLIC_API_URL` in `lib/mini/ui.tsx`. Two options:

- **Skip it.** Leave the field empty, type your backend URL on the pairing screen when
  you install the app. Works every time.
- **Bake it in.** Create `mobile/ora-android-companion/.env`:

  ```bash
  EXPO_PUBLIC_API_URL=https://YOUR-BACKEND.onrender.com
  ```

  `app.config.ts` also reads two optional overrides you may want:

  ```bash
  EXPO_OWNER=your-expo-username              # default: leo333 (see account note below)
  EXPO_PUBLIC_EAS_PROJECT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
  ```

  `.env` is gitignored (`.gitignore` line 2). Nothing in it is a secret — every
  `EXPO_PUBLIC_*` value is compiled into the APK in plain text. Never put
  `ORA_API_TOKEN` or an AI key here.

Only an `https://` URL is accepted; `pair()` in `lib/mini/api.ts` rejects plain
`http://` and any path or port suffix that is not numeric. A phone cannot reach
your laptop's `localhost` anyway, so for local testing use your machine's LAN IP
with a tunnel that terminates TLS, or test against the deployed backend.

---

## 2. Install the project's toolchain

```bash
cd mobile/ora-android-companion
npm install -g pnpm@9.12.0        # skip if pnpm --version is already 9.12.0
pnpm install --frozen-lockfile
npx expo-doctor                   # optional health check
```

If `pnpm` is not on your PATH at all, `corepack enable pnpm` also works on Node 22.

Verified on this checkout: `pnpm install --frozen-lockfile` installs 1090 packages
with no peer-dependency errors, `npx tsc --noEmit` passes, and `npx vitest run`
passes 14 tests across 5 files.

`npx expo-doctor` currently reports 18/22 checks passing. The four failures are
known and do not block building: it wants SDK 57/58 (this project is deliberately
on SDK 56 / React Native 0.85.3), and `components/haptic-tab.tsx` imports
`@react-navigation/*` directly. That file is unused by any route.

---

## 3. Build the APK

Two supported paths. Pick one — after the first successful build, the Expo account
owns the Android signing key, so do not switch paths between releases or the
phone will refuse to update the installed app.

### 3a. EAS Build (recommended — no Android Studio)

```bash
cd mobile/ora-android-companion
npx eas-cli login
npx eas-cli whoami                                  # confirm the account matches `owner`
npx eas-cli build:configure                         # one time; keep the committed eas.json
npx eas-cli credentials --platform android          # one time; let EAS generate the keystore
npx eas-cli build --platform android --profile preview
```

`eas.json` already defines the right profile:

```json
{"cli":{"version":">= 16.0.0"},
 "build":{"preview":{"distribution":"internal","android":{"buildType":"apk"}},
          "production":{"autoIncrement":true}}}
```

- `--profile preview` → internal-distribution **APK** you can sideload. This is the
  profile you want.
- `--profile production` → a **AAB** for the Play Store, not directly installable.

The build prints an `https://expo.dev/artifacts/...` link when it finishes, and the
same link appears under **expo.dev → your project → Builds**. Open it on the phone
and install. Builds deleted after 30 days; re-run the command to get a fresh link.

**Account check.** `app.config.ts` pins `owner: "leo333"` (an existing Expo
project, `projectId eeb08070-cabe-47bb-b2bb-3e9ef6533240`) unless you set
`EXPO_OWNER`. If you log in as a different Expo user, set `EXPO_OWNER` **and**
`EXPO_PUBLIC_EAS_PROJECT_ID` in `.env` before `build:configure`, otherwise
`build:configure` writes a new `projectId` into `app.config.ts`/`extra` and EAS
rejects the mismatch. Simplest path: log in as the account that owns the project.

Free-tier reality: 15 Android builds per calendar month, low-priority queue,
45-minute cap, ~10-25 minutes per build when the queue is quiet. A failed build
still counts.

### 3b. Local Gradle build (no cloud queue, unlimited)

Needs JDK 17 and Android SDK platform 36 + build-tools 36.0.0.

```bash
cd mobile/ora-android-companion
export ANDROID_HOME="$HOME/Android/Sdk"            # or your SDK path
export JAVA_HOME="$(/usr/libexec/java_home -v 17)" # macOS; use your JDK 17 path elsewhere
pnpm install --frozen-lockfile
npx expo prebuild --platform android --clean       # generates ./android (gitignored)
cd android
./gradlew :app:assembleRelease                     # or assembleDebug for a debug build
```

Output: `android/app/build/outputs/apk/release/app-release.apk`.

`release` here is signed with the **debug keystore** that `expo prebuild` writes to
`android/app/debug.keystore` (see `signingConfigs` in `android/app/build.gradle`).
That is fine for personal use, but the key is regenerated on a fresh clone, so
re-installs from a different machine will conflict. If you want a stable personal
key, generate one keystore and point `signingConfigs.release` at it before the
first install. Never commit a keystore.

`./gradlew` will download Gradle 9.3.1 on first run and needs several hundred MB
of Android dependencies — expect 15-30 minutes cold, a few minutes warm.

Copy the APK to the phone (USB, Drive, `adb install app-release.apk`, etc.).

---

## 4. Install on the phone

1. Transfer the APK to the phone.
2. Open it; allow **Install unknown apps** for whichever app opened it (Files,
   Chrome, Drive) when Android prompts.
3. If Play Protect warns about an unknown developer, choose **Install anyway** —
   this is your own build, not a modified app from the store.
4. Launch **ORA Mini AI**. You should land on the pairing screen with the orb and
   "A mind by your side."

You cannot skip this step with Expo Go: the app imports a local native module
(`modules/ora-notification-listener`) that only exists in a compiled build.

---

## 5. Pair the phone

Pairing gives the phone its **own** revocable 90-day session. Your owner key never
touches the device.

1. **On the web app** (`https://YOUR-VERCEL-APP`), sign in with the owner key.
2. Go to **Connections → Phone → Generate pairing code**. A 10-character code
   appears, valid once for 10 minutes. Copy it.
3. **On the phone**, on the pairing screen:
   - *Backend address*: `https://YOUR-BACKEND.onrender.com` (prefilled if you did
     step 1).
   - *One-time pairing code*: the code from step 2 (case-insensitive).
   - Tap **Pair my phone**.
4. First sync may take up to ~2 minutes if the Render free instance is asleep; the
   app waits 115 seconds and keeps your draft if it times out.

Backend contract, if you want to verify by hand or script it:

```bash
# owner session (7-day token)
curl -s -X POST https://YOUR-BACKEND.onrender.com/api/v2/session \
  -H 'Content-Type: application/json' -d '{"token":"YOUR_ORA_API_TOKEN"}'

# one-use pairing code (owner session only)
curl -s -X POST https://YOUR-BACKEND.onrender.com/api/v2/pairing-code \
  -H "Authorization: Bearer OWNER_SESSION"

# what the phone does (device session, 90 days)
curl -s -X POST https://YOUR-BACKEND.onrender.com/api/v2/pair \
  -H 'Content-Type: application/json' \
  -d '{"code":"ABC12DEF34","label":"My Android"}'
```

These were exercised against a local backend on this checkout: pairing returns
`{token, device_id}`, a device token can call `/api/v2/sync` (HTTP 200), and
replaying the same code returns `400 Pairing code is invalid or expired.`

Rules the backend enforces, so you are not surprised:

- Codes are single use and expire in 10 minutes.
- Maximum 10 non-revoked devices; revoke one first.
- `/api/v2/pair` and `/api/v2/session` are rate limited to 5 attempts per minute per IP.
- If you enter the code 5+ times in a minute, wait 60 seconds (HTTP 429).
- Only one live pairing code exists at a time — generating a new one invalidates
  the old one.

If pairing fails: `401` means the code is wrong/expired (regenerate it); a network
error usually means the backend URL is wrong or the Render instance is still
waking; `400` after a first success means you are reusing a code.

---

## 6. First-run configuration (5 minutes)

Pairing alone gives you a read/write workspace. These toggles make the phone useful:

**Settings tab → "Reminders that stay with you" → Schedule on this phone**
Schedules up to 50 upcoming tasks as local Android notifications. They fire while
the backend is asleep and while ORA is closed. Then in **Settings → Notifications,
weather and alert inbox → Allow precise reminder timing** and grant **Alarms &
reminders** in Android so times are exact. Test with **Test local notification ·
5 seconds** and with a real task 2-3 minutes out.

**Settings → Notifications, weather and alert inbox** — also where you opt into
Telegram alerts, set quiet hours, and choose a weather city or share approximate
location for forecasts.

**Settings → Biometric app lock**
Locks ORA when you leave it, using your enrolled fingerprint. Requires a
fingerprint/PIN already enrolled in Android.

**Settings → Phone awareness** — the privacy surface:
- *Pause all awareness* stops collecting; re-enabling it does **not** silently
  restart notification collection — you must tap **Enable selected apps** again.
- *Selected notifications*: pick apps, tap **Enable selected apps**, then in
  Android's **Notification access** screen enable ORA and come back. Only the
  chosen apps are read; codes, links and email addresses are redacted, and the
  on-phone queue uploads when the app opens (not real-time cloud monitoring).
- One-shot shares: **Share my location now**, **Share today's calendar**,
  **Share battery status**, **Choose a contact to share**. Each asks for the OS
  permission and confirms before sending. Shared context expires after 24 hours.
- **Delete shared phone context** wipes what the backend holds for this device.

**Talk tab** — record a voice note, review the transcript, send it. Choose a
system TTS voice and toggle automatic read-aloud in Settings.

---

## 7. Verify the install

Do these in order; each one isolates a different failure mode.

| Check | Expected |
| --- | --- |
| Create a task in the web **Plan** page, open the phone's **My plan** tab | The task appears |
| Complete it on the phone, refresh the web | Task is done on both |
| Turn on *Schedule on this phone*, make a task 3 minutes out | Notification fires with the screen locked |
| **Test local notification · 5 seconds** with ORA backgrounded | Notification appears |
| Enable one app under *Selected notifications*, trigger a notification from it | It appears later in the phone's alert history after a sync |
| **Share my location now** | A `location` event appears in web **Tools & activity** |
| Web **Connections → Phone** | Your device listed with a recent "last heard" time |
| Revoke the device on web, then sync the phone | Phone clears its session and returns to pairing |

The last row matters: revocation is enforced at the next sync. An offline phone
cannot be reached instantly — if you lose the device, revoke it on the web and it
loses access the next time it connects.

---

## 8. Optional: remote alerts via Telegram (replaces push)

This build has no FCM path. `backend/next_api.py` returns HTTP 410
"Remote alerts now use Telegram" for the old push operation, and the shipped
`backend/fcm.py` is not wired to any route. So for alerts that arrive when the app
is closed and the backend is awake:

1. Set `TELEGRAM_BOT_TOKEN` on the backend (Render env var) — see
   [TELEGRAM_SETUP.md](TELEGRAM_SETUP.md).
2. On the web, **Connections → Telegram → Generate Telegram link**, open it in your
   private Telegram chat within 10 minutes.
3. On the phone, **Notifications, weather and alert inbox → Enable Telegram alerts**.
4. Optionally **Queue Telegram test** to confirm end-to-end delivery.

`lib/awareness-controls.ts` also contains an Expo-push registration helper, but no
screen calls it and the backend would reject it, so ignore it.

Local reminders (step 6) remain the reliable path and need no server.

---

## 9. Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| Build fails: `owner`/project mismatch | Logged into a different Expo account. Use `leo333`, or set `EXPO_OWNER` + `EXPO_PUBLIC_EAS_PROJECT_ID` |
| Build fails: Java/Gradle version | Local builds need **JDK 17** and `ANDROID_HOME` pointing at an SDK with platform 36 |
| `INSTALL_FAILED_UPDATE_INCOMPATIBLE` | A different signing key built the installed copy. Uninstall the old app (this deletes its local data) then install |
| App opens but the pairing screen rejects the URL | Must be `https://host` only — no `http://`, no `/path`, no trailing slash requirements beyond a single `/` |
| "ORA is offline or waking up" | Render free instance is asleep. Wait ~60 s and retry; unsent drafts are preserved |
| Pairing code rejected | Expired (10 min) or already used. Generate a new one; wait 60 s if you hit the rate limit |
| No reminders fire | Notifications off, or exact alarms not allowed. Use **Enable notifications** and **Allow precise reminder timing**; check battery optimization isn't force-stopping ORA |
| Notification access toggles back off | Enable ORA in Android **Settings → Notification access**, then tap **Enable selected apps** again |
| Voice recording silent | Microphone permission denied, or another app holds the mic |
| App lock won't unlock after re-enrolling fingerprints | Disconnect and re-pair the phone |
| Phone lost | Revoke it on web **Connections → Phone**; it loses access at its next sync |

---

## 10. Updating the app later

The phone version is `2.2.0` while the backend reports `companion_release: 2.3`
in `/api/health`; that field is informational and does not block a build.

- **JavaScript-only change** (screens, copy, API calls): rebuild and reinstall, or
  push an over-the-air update if you have configured `expo-updates`.
- **Native change** (`modules/ora-notification-listener`, permissions in
  `app.config.ts`, SDK upgrades): a new APK is mandatory. Restarting Metro does
  not update Kotlin that is already installed.
- Keep the same signing key. Re-installing with a different key requires
  uninstalling first, which wipes the phone's cached workspace and queued changes.
- Bump `version` in `app.config.ts` (and use the `production` profile's
  `autoIncrement`) when you want the build number to move.

---

## What actually runs, by file

| Concern | File |
| --- | --- |
| Pairing UI, tabs, all screens | `lib/mini/ui.tsx` |
| Session storage in `expo-secure-store`, HTTP client, timeouts | `lib/mini/api.ts` |
| Sync loop, offline outbox, per-op send | `lib/mini/provider.tsx` |
| Local reminders (max 50) | `lib/mini/reminder-plan.ts`, `lib/mini/reminders.ts` |
| Notification listener bridge | `modules/ora-notification-listener/`, `lib/notification-listener.ts` |
| Notification/weather/Telegram screen | `app/notifications.tsx` |
| App config, Android permissions, `minSdkVersion: 26` | `app.config.ts` |
| APK profile | `eas.json` |

Gates this repository can run without a phone:

```bash
cd mobile/ora-android-companion
pnpm check      # tsc --noEmit
pnpm test       # vitest: 14 tests, 5 files
pnpm build      # expo export --platform android (JS packaging only, not an APK)
```

`pnpm lint` currently reports 2 errors (`react-hooks/purity`: `Date.now()` during
render in `app/edit-task.tsx` and `app/tools.tsx`) and 2 duplicate-import warnings.
They are pre-existing and do not affect the bundle, which `pnpm build` produces
successfully, but they will fail a CI job that gates on lint.

None of the above substitutes for installing on a real device: the Kotlin listener,
exact-alarm scheduling, biometrics, voice engine behaviour and battery policy can
only be validated on hardware.
