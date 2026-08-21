import { useMemo } from "react";
import { ActivityIndicator, Alert, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { router } from "expo-router";

import { OraStatusCard } from "@/components/ora-status-card";
import { ScreenContainer } from "@/components/screen-container";
import { useDevice } from "@/lib/device-provider";

function formatTime(value?: string | null) {
  if (!value) return "Not yet";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

export default function HomeScreen() {
  const { session, device, loading, busy, error, refresh, sendCheckIn } = useDevice();
  const tone = useMemo(() => {
    if (error) return "error" as const;
    if (session && device?.status === "active") return "success" as const;
    return "neutral" as const;
  }, [device?.status, error, session]);

  async function handleCheckIn() {
    try {
      await sendCheckIn();
      Alert.alert("ORA updated", "This phone check-in reached ORA successfully.");
    } catch (err) {
      Alert.alert("Check-in failed", err instanceof Error ? err.message : "Try again after checking the backend.");
    }
  }

  return (
    <ScreenContainer className="bg-background" edges={["top", "left", "right"]}>
      <ScrollView className="flex-1" contentContainerStyle={styles.content}>
        <View className="mb-7 gap-2">
          <Text className="text-xs font-bold tracking-[4px] text-primary">ORA // ANDROID COMPANION</Text>
          <Text className="text-3xl font-bold text-foreground">Your private bridge to ORA.</Text>
          <Text className="text-sm leading-5 text-muted">Pair this phone once. Choose every awareness capability deliberately.</Text>
        </View>

        {loading ? (
          <View className="items-center py-14"><ActivityIndicator color="#00E6A7" /></View>
        ) : (
          <View className="gap-4">
            <OraStatusCard
              tone={tone}
              title={session && device?.status === "active" ? device.label : "Phone not paired"}
              detail={
                session && device
                  ? `Last check-in: ${formatTime(device.last_seen_at)}\nBackend: ${session.backendUrl}`
                  : "Create a short-lived pairing code in ORA, then connect this Android phone without exposing the master ORA token."
              }
            >
              <Pressable
                accessibilityRole="button"
                accessibilityLabel={session ? "Refresh ORA connection" : "Connect this phone to ORA"}
                disabled={busy}
                onPress={session ? () => void refresh() : () => router.push("/pair" as never)}
                style={({ pressed }) => [styles.primaryButton, (pressed || busy) && styles.buttonPressed]}
              >
                <Text style={styles.primaryButtonText}>{busy ? "WORKING…" : session ? "REFRESH CONNECTION" : "CONNECT ORA"}</Text>
              </Pressable>
            </OraStatusCard>

            {session ? (
              <OraStatusCard tone="success" title="Safe device check-in" detail="Send a harmless connection event before enabling any phone awareness capability.">
                <Pressable
                  accessibilityRole="button"
                  accessibilityLabel="Send a device check-in to ORA"
                  disabled={busy}
                  onPress={() => void handleCheckIn()}
                  style={({ pressed }) => [styles.secondaryButton, (pressed || busy) && styles.buttonPressed]}
                >
                  <Text style={styles.secondaryButtonText}>SEND TEST CHECK-IN</Text>
                </Pressable>
              </OraStatusCard>
            ) : null}

            <View className="rounded-3xl border border-border bg-surface px-5 py-5">
              <Text className="text-base font-bold text-foreground">Awareness starts with consent</Text>
              <Text className="mt-2 text-sm leading-5 text-muted">Push, selected notification access, and location routines remain off until you enable and understand each one.</Text>
            </View>
          </View>
        )}
      </ScrollView>
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  content: { padding: 20, paddingBottom: 30 },
  primaryButton: { minHeight: 48, alignItems: "center", justifyContent: "center", borderRadius: 14, backgroundColor: "#00E6A7", paddingHorizontal: 18 },
  secondaryButton: { minHeight: 48, alignItems: "center", justifyContent: "center", borderRadius: 14, borderWidth: 1, borderColor: "#00E6A7", paddingHorizontal: 18 },
  primaryButtonText: { color: "#08110F", fontWeight: "800", fontSize: 12, letterSpacing: 1.4 },
  secondaryButtonText: { color: "#00E6A7", fontWeight: "800", fontSize: 12, letterSpacing: 1.2 },
  buttonPressed: { opacity: 0.8, transform: [{ scale: 0.98 }] },
});
