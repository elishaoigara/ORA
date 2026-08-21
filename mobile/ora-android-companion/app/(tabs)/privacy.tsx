import { Alert, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useState } from "react";

import { ScreenContainer } from "@/components/screen-container";
import { deletePreciseLocationHistory } from "@/lib/ora-device";
import { useDevice } from "@/lib/device-provider";

export default function PrivacyScreen() {
  const { session, device, awareness, busy, revoke, forgetLocalSession, refreshAwareness } = useDevice();
  const [clearing, setClearing] = useState(false);
  const continuous = awareness?.consents.find((item) => item.capability === "continuous_location");
  const enabled = awareness?.consents.filter((item) => item.enabled).map((item) => item.capability.replaceAll("_", " ")) ?? [];

  function confirmRevocation() {
    Alert.alert("Revoke this phone?", "ORA will reject this phone’s device token immediately. Pair it again to reconnect.", [
      { text: "Cancel", style: "cancel" },
      { text: "Revoke device", style: "destructive", onPress: () => void revoke().catch((error: Error) => Alert.alert("Revocation failed", error.message)) },
    ]);
  }

  function confirmLocationDelete() {
    if (!session) return;
    Alert.alert("Delete precise location history?", "This removes retained continuous-location samples from ORA now. Named-zone enter and exit events are not precise coordinates.", [
      { text: "Cancel", style: "cancel" },
      {
        text: "Delete history",
        style: "destructive",
        onPress: () => {
          setClearing(true);
          void deletePreciseLocationHistory(session)
            .then((count) => Alert.alert("Location history deleted", `${count} precise sample${count === 1 ? "" : "s"} removed.`))
            .catch((error: Error) => Alert.alert("Delete failed", error.message))
            .finally(() => {
              setClearing(false);
              void refreshAwareness();
            });
        },
      },
    ]);
  }

  return (
    <ScreenContainer className="bg-background" edges={["top", "left", "right"]}>
      <ScrollView contentContainerStyle={styles.content}>
        <Text className="text-xs font-bold tracking-[4px] text-primary">ORA // PRIVACY</Text>
        <Text className="mt-2 text-3xl font-bold text-foreground">Your phone, your control.</Text>
        <Text className="mt-3 text-sm leading-5 text-muted">The Companion stores only a revocable device credential. It never stores ORA’s owner API token.</Text>

        <View className="mt-7 rounded-3xl border border-border bg-surface p-5">
          <Text className="text-base font-bold text-foreground">Paired device</Text>
          <Text className="mt-3 text-lg font-semibold text-foreground">{device?.label ?? "No paired phone"}</Text>
          <Text className="mt-1 text-sm text-muted">{session ? `Device ID: ${session.deviceId}` : "Pairing is required before ORA can receive device events."}</Text>
          {device ? <Text className="mt-4 text-sm text-muted">Token ending: •••{device.token_hint}</Text> : null}
          {session ? <Text className="mt-1 text-sm text-muted">Backend: {session.backendUrl}</Text> : null}
        </View>

        <View className="rounded-3xl border border-border p-5">
          <Text className="text-base font-bold text-foreground">Current awareness</Text>
          <Text className="mt-2 text-sm leading-5 text-muted">{enabled.length ? `Enabled: ${enabled.join(", ")}.` : "No awareness source is enabled."}</Text>
          <Text className="mt-2 text-sm leading-5 text-muted">Named-zone routines retain only arrival/departure events. Continuous location retains precise samples for {continuous?.enabled ? `${continuous.retention_hours} hours` : "no time because it is off"}.</Text>
        </View>

        {session ? <Pressable disabled={clearing} onPress={confirmLocationDelete} style={({ pressed }) => [styles.neutralButton, (pressed || clearing) && styles.pressed]}><Text style={styles.neutralText}>{clearing ? "DELETING…" : "DELETE PRECISE LOCATION HISTORY"}</Text></Pressable> : null}

        {session ? (
          <Pressable disabled={busy} onPress={confirmRevocation} style={({ pressed }) => [styles.revokeButton, (pressed || busy) && styles.pressed]}><Text style={styles.revokeText}>{busy ? "WORKING…" : "REVOKE THIS DEVICE"}</Text></Pressable>
        ) : (
          <Pressable disabled={busy} onPress={() => void forgetLocalSession()} style={({ pressed }) => [styles.neutralButton, (pressed || busy) && styles.pressed]}><Text style={styles.neutralText}>CLEAR LOCAL STATE</Text></Pressable>
        )}
      </ScrollView>
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  content: { padding: 20, paddingBottom: 30 },
  revokeButton: { minHeight: 50, marginTop: 14, borderRadius: 14, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: "#F87171" },
  neutralButton: { minHeight: 50, marginTop: 18, borderRadius: 14, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: "#95AAA3" },
  revokeText: { color: "#F87171", fontWeight: "800", fontSize: 12, letterSpacing: 1.2 },
  neutralText: { color: "#95AAA3", fontWeight: "800", fontSize: 11, letterSpacing: 0.8 },
  pressed: { opacity: 0.8, transform: [{ scale: 0.98 }] },
});
