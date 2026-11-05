import type { ExpoConfig } from "expo/config";
const config: ExpoConfig = {
  name: "ORA Mini AI",
  slug: "ora-android-companion",
  // Override with EXPO_OWNER to build under a different Expo account.
  owner: process.env.EXPO_OWNER || "leo333",
  version: "2.2.0",
  scheme: "ora",
  orientation: "portrait",
  userInterfaceStyle: "dark",
  icon: "./assets/images/ora-launcher.png",
  android: {
    package: "com.app.oraandroidcompanion",
    permissions: [
      "POST_NOTIFICATIONS",
      "com.android.alarm.permission.SET_ALARM",
      "SCHEDULE_EXACT_ALARM",
    ],
    adaptiveIcon: {
      foregroundImage: "./assets/images/ora-adaptive-modern.png",
      monochromeImage: "./assets/images/ora-monochrome.png",
      backgroundColor: "#10131d",
    },
  },
  ios: { bundleIdentifier: "com.app.oraandroidcompanion" },
  plugins: [
    "expo-router",
    "expo-font",
    "expo-secure-store",
    [
      "expo-notifications",
      { color: "#a5b4fc", defaultChannel: "ora-reminders" },
    ],
    [
      "expo-audio",
      {
        microphonePermission:
          "Allow ORA to record a voice note when you tap the microphone.",
      },
    ],
    [
      "expo-contacts",
      { contactsPermission: "Choose individual contacts to share with ORA." },
    ],
    [
      "expo-location",
      {
        locationWhenInUsePermission:
          "Share your current location with ORA when you request it.",
        isAndroidBackgroundLocationEnabled: true,
        isAndroidForegroundServiceEnabled: true,
      },
    ],
    [
      "expo-splash-screen",
      {
        image: "./assets/images/ora-mark.png",
        imageWidth: 200,
        resizeMode: "contain",
        backgroundColor: "#10131d",
      },
    ],
    ["expo-build-properties", { android: { minSdkVersion: 26 } }],
    [
      "expo-share-intent",
      {
        androidIntentFilters: [
          "text/*",
          "image/png",
          "image/jpeg",
          "application/pdf",
        ],
        androidMultiIntentFilters: [],
      },
    ],
    [
      "expo-calendar",
      { calendarPermission: "Share today’s events with ORA when you ask." },
    ],
    "expo-document-picker",
  ],
  experiments: { typedRoutes: true },
  extra: {
    // Set EXPO_PUBLIC_EAS_PROJECT_ID in .env (local builds) or as an EAS
    // environment variable to link a different Expo project. It feeds both EAS
    // and the push-token project id read by lib/awareness-controls.ts.
    eas: {
      projectId:
        process.env.EXPO_PUBLIC_EAS_PROJECT_ID ||
        "eeb08070-cabe-47bb-b2bb-3e9ef6533240",
    },
  },
};
export default config;
