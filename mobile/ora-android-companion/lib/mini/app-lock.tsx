import React, { useEffect, useState } from "react";
import { AppState, View, Text, Pressable } from "react-native";
import * as SecureStore from "expo-secure-store";
import { readLocal, writeLocal } from "./api";
import { useMini } from "./provider";
import { colors as c } from "./theme";
const key = "ora_biometric_lock";
export async function enableAppLock() {
  if (!SecureStore.canUseBiometricAuthentication())
    throw Error(
      "Enroll a fingerprint or supported biometric in Android Settings first.",
    );
  await SecureStore.setItemAsync(key, "unlocked", {
    requireAuthentication: true,
    authenticationPrompt: "Protect ORA",
  });
  await writeLocal("appLock", true);
}
export async function disableAppLock() {
  if (
    (await SecureStore.getItemAsync(key, {
      requireAuthentication: true,
      authenticationPrompt: "Unlock ORA settings",
    })) !== "unlocked"
  )
    throw Error("Authentication required.");
  await writeLocal("appLock", false);
  await SecureStore.deleteItemAsync(key);
}
export function AppLock({ children }: { children: React.ReactNode }) {
  const m = useMini();
  const [locked, setLocked] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => {
    let alive = true;
    void readLocal("appLock", false).then((v) => {
      if (alive) setLocked(v);
    });
    const sub = AppState.addEventListener("change", (s) => {
      if (s !== "active")
        void readLocal("appLock", false).then((v) => {
          if (alive && v) setLocked(true);
        });
    });
    return () => {
      alive = false;
      sub.remove();
    };
  }, [m.session]);
  if (!m.session || !locked) return <>{children}</>;
  return (
    <View
      style={{
        flex: 1,
        backgroundColor: c.background,
        justifyContent: "center",
        padding: 32,
        gap: 24,
      }}
    >
      <Text style={{ color: c.cyan, fontSize: 30 }}>ORA · Private space</Text>
      <Pressable
        onPress={async () => {
          try {
            const result = await SecureStore.getItemAsync(key, {
              requireAuthentication: true,
              authenticationPrompt: "Unlock ORA",
            });
            if (result === "unlocked") setLocked(false);
            else
              setError(
                "Biometrics changed. Disconnect and pair this phone again.",
              );
          } catch {
            setError("Unlock cancelled. Try again.");
          }
        }}
      >
        <Text style={{ color: c.text, fontSize: 20 }}>
          Unlock with biometrics
        </Text>
      </Pressable>
      <Text style={{ color: c.text }}>{error}</Text>
      <Pressable onPress={() => m.disconnect()}>
        <Text style={{ color: c.muted }}>Disconnect and clear this phone</Text>
      </Pressable>
    </View>
  );
}
