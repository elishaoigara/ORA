import type { ExpoConfig } from "expo/config";
const config: ExpoConfig = {
  name: "ORA Mini AI",
  slug: "ora-android-companion",
  owner: "leo333",
  version: "2.1.0",
  scheme: "ora",
  orientation: "portrait",
  userInterfaceStyle: "dark",
  icon: "./assets/images/ora-horus.png",
  android: {
    package: "com.app.oraandroidcompanion",
    ...(process.env.GOOGLE_SERVICES_JSON
      ? { googleServicesFile: process.env.GOOGLE_SERVICES_JSON }
      : {}),
    permissions: ["POST_NOTIFICATIONS", "SCHEDULE_EXACT_ALARM"],
    adaptiveIcon: {
      foregroundImage: "./assets/images/ora-adaptive.png",
      backgroundColor: "#000000",
    },
  },
  ios: { bundleIdentifier: "com.app.oraandroidcompanion" },
  plugins: [
    "expo-router",
    "expo-font",
    "expo-secure-store",
    [
      "expo-notifications",
      { color: "#e4bc73", defaultChannel: "ora-reminders" },
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
        image: "./assets/images/ora-horus.png",
        imageWidth: 200,
        resizeMode: "contain",
        backgroundColor: "#000000",
      },
    ],
    ["expo-build-properties", { android: { minSdkVersion: 26 } }],
    [
      "expo-share-intent",
      { androidIntentFilters: ["text/*"], androidMultiIntentFilters: [] },
    ],
    [
      "expo-calendar",
      { calendarPermission: "Share today’s events with ORA when you ask." },
    ],
    "expo-document-picker",
  ],
  experiments: { typedRoutes: true },
  extra: {
    eas: { projectId: "eeb08070-cabe-47bb-b2bb-3e9ef6533240" },
  },
};
export default config;
