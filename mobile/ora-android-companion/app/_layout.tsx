import "../global.css";
import "@/lib/awareness-runtime";

import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { ShareIntentProvider } from "expo-share-intent";

import { DeviceProvider } from "@/lib/device-provider";
import { ThemeProvider } from "@/lib/theme-provider";

export default function RootLayout() {
  return (
    <ThemeProvider>
      <ShareIntentProvider options={{ resetOnBackground: false }}>
        <DeviceProvider>
          <StatusBar style="light" />
          <Stack screenOptions={{ headerShown: false, animation: "fade" }}>
            <Stack.Screen name="(tabs)" />
            <Stack.Screen name="pair" options={{ presentation: "modal" }} />
            <Stack.Screen name="approvals" options={{ presentation: "card" }} />
          </Stack>
        </DeviceProvider>
      </ShareIntentProvider>
    </ThemeProvider>
  );
}
