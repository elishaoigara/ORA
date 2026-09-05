import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { ShareIntentProvider } from "expo-share-intent";
import { MiniProvider } from "@/lib/mini/provider";
export default function RootLayout() {
  return (
    <SafeAreaProvider>
      <ShareIntentProvider>
        <MiniProvider>
          <StatusBar style="light" />
          <Stack
            screenOptions={{
              headerShown: false,
              contentStyle: { backgroundColor: "#090e14" },
            }}
          />
        </MiniProvider>
      </ShareIntentProvider>
    </SafeAreaProvider>
  );
}
