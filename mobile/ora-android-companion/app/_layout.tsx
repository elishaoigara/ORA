import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { ShareIntentProvider } from "expo-share-intent";
import { AppLock } from "@/lib/mini/app-lock";
import { MiniProvider } from "@/lib/mini/provider";
import { colors } from "@/lib/mini/theme";
export { ErrorBoundary } from "expo-router";
export default function RootLayout() {
  return (
    <SafeAreaProvider>
      <ShareIntentProvider>
        <MiniProvider>
          <AppLock>
            <StatusBar style="light" />
            <Stack
              screenOptions={{
                headerShown: false,
                contentStyle: { backgroundColor: colors.background },
              }}
            />
          </AppLock>
        </MiniProvider>
      </ShareIntentProvider>
    </SafeAreaProvider>
  );
}
