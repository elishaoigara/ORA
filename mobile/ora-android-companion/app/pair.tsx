import { type ComponentProps, useState } from "react";
import { ActivityIndicator, Alert, KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { router } from "expo-router";

import { ScreenContainer } from "@/components/screen-container";
import { useDevice } from "@/lib/device-provider";
import { DEFAULT_BACKEND_URL } from "@/lib/ora-device";

export default function PairScreen() {
  const { pair, busy } = useDevice();
  const [backendUrl, setBackendUrl] = useState(DEFAULT_BACKEND_URL);
  const [pairingCode, setPairingCode] = useState("");
  const [deviceName, setDeviceName] = useState("My Android phone");
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setError(null);
    try {
      await pair({ backendUrl, pairingCode, deviceName });
      Alert.alert("Phone paired", "ORA created a device-scoped credential for this phone.", [
        { text: "Continue", onPress: () => router.replace("/") },
      ]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Pairing could not be completed.");
    }
  }

  return (
    <ScreenContainer className="bg-background" edges={["top", "bottom", "left", "right"]}>
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} className="flex-1">
        <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
          <Pressable onPress={() => router.back()} style={({ pressed }) => [styles.backButton, pressed && styles.pressed]}>
            <Text style={styles.backText}>CLOSE</Text>
          </Pressable>
          <Text className="mt-8 text-xs font-bold tracking-[4px] text-primary">ORA // SECURE PAIRING</Text>
          <Text className="mt-2 text-3xl font-bold text-foreground">Connect this phone.</Text>
          <Text className="mt-3 text-sm leading-5 text-muted">Create a short-lived pairing code in the ORA dashboard. The code creates a device-scoped credential; it never exposes ORA’s master token.</Text>

          <View className="mt-8 gap-5">
            <Field label="ORA backend" value={backendUrl} onChangeText={setBackendUrl} autoCapitalize="none" keyboardType="url" />
            <Field label="Pairing code" value={pairingCode} onChangeText={setPairingCode} autoCapitalize="characters" placeholder="ORA-ABCDE-12345" />
            <Field label="Device name" value={deviceName} onChangeText={setDeviceName} autoCapitalize="words" />
          </View>

          {error ? <Text className="mt-5 text-sm leading-5 text-error">{error}</Text> : null}

          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Pair this Android phone with ORA"
            disabled={busy || !pairingCode.trim() || !deviceName.trim()}
            onPress={() => void submit()}
            style={({ pressed }) => [styles.primaryButton, (pressed || busy || !pairingCode.trim()) && styles.pressed]}
          >
            {busy ? <ActivityIndicator color="#08110F" /> : <Text style={styles.primaryText}>PAIR THIS PHONE</Text>}
          </Pressable>

          <View className="mt-5 rounded-2xl border border-border p-4">
            <Text className="text-sm font-bold text-foreground">Before you continue</Text>
            <Text className="mt-2 text-sm leading-5 text-muted">Use the official ORA backend address. Pair only on a private network or trusted mobile connection. You can revoke this phone from ORA or from the Privacy tab at any time.</Text>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </ScreenContainer>
  );
}

function Field({ label, ...props }: { label: string } & ComponentProps<typeof TextInput>) {
  return (
    <View>
      <Text className="mb-2 text-xs font-bold tracking-[1.4px] text-muted">{label.toUpperCase()}</Text>
      <TextInput
        {...props}
        className="min-h-14 rounded-2xl border border-border bg-surface px-4 text-base text-foreground"
        placeholderTextColor="#60746D"
        returnKeyType="done"
      />
    </View>
  );
}

const styles = StyleSheet.create({
  content: { padding: 20, paddingBottom: 28 },
  backButton: { alignSelf: "flex-start", minHeight: 36, justifyContent: "center" },
  backText: { color: "#95AAA3", fontSize: 12, fontWeight: "800", letterSpacing: 1.2 },
  primaryButton: { minHeight: 52, marginTop: 28, alignItems: "center", justifyContent: "center", borderRadius: 15, backgroundColor: "#00E6A7" },
  primaryText: { color: "#08110F", fontWeight: "800", fontSize: 12, letterSpacing: 1.3 },
  pressed: { opacity: 0.78, transform: [{ scale: 0.98 }] },
});
