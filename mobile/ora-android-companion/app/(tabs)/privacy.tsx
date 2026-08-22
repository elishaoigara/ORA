import { Alert, Platform, Pressable, ScrollView, StyleSheet, Switch, Text, View } from "react-native";
import { useEffect, useState } from "react";
import * as Battery from "expo-battery";
import * as Contacts from "expo-contacts";
import * as Network from "expo-network";

import { ScreenContainer } from "@/components/screen-container";
import {
  deleteDeviceHealthHistory,
  deleteNotificationAuditEvents,
  deletePreciseLocationHistory,
  getLatestDeviceHealth,
  getSelectedContacts,
  replaceSelectedContacts,
  setAwarenessConsent,
  submitDeviceHealth,
  type DeviceHealthSnapshot,
  type SelectedContact,
} from "@/lib/ora-device";
import { useDevice } from "@/lib/device-provider";

export default function PrivacyScreen() {
  const { session, device, awareness, commandCenter, busy, revoke, forgetLocalSession, refreshAwareness, updateCommandPreferences } = useDevice();
  const [clearing, setClearing] = useState(false);
  const [contacts, setContacts] = useState<SelectedContact[]>([]);
  const [health, setHealth] = useState<DeviceHealthSnapshot | null>(null);
  const [working, setWorking] = useState<"contacts" | "health" | "pause" | "quiet" | null>(null);
  const continuous = awareness?.consents.find((item) => item.capability === "continuous_location");
  const contactsConsent = awareness?.consents.find((item) => item.capability === "selected_contacts");
  const healthConsent = awareness?.consents.find((item) => item.capability === "device_health");
  const enabled = awareness?.consents.filter((item) => item.enabled).map((item) => item.capability.replaceAll("_", " ")) ?? [];
  const preferences = commandCenter?.preferences;

  useEffect(() => {
    let active = true;
    async function loadPrivateContext() {
      if (!session) return;
      try {
        if (contactsConsent?.enabled) {
          const nextContacts = await getSelectedContacts(session);
          if (active) setContacts(nextContacts);
        }
        if (healthConsent?.enabled) {
          const snapshot = await getLatestDeviceHealth(session);
          if (active) setHealth(snapshot);
        }
      } catch {
        // A feature may wait for the matching backend deployment without breaking Privacy.
      }
    }
    void loadPrivateContext();
    return () => { active = false; };
  }, [contactsConsent?.enabled, healthConsent?.enabled, session]);

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
      { text: "Delete history", style: "destructive", onPress: () => void runDeletion(() => deletePreciseLocationHistory(session), "Location history deleted", "precise sample") },
    ]);
  }

  function confirmNotificationDelete() {
    if (!session) return;
    Alert.alert("Delete notification audit?", "This permanently removes all retained selected-notification records from ORA. It does not change Android notification access or your source choices.", [
      { text: "Cancel", style: "cancel" },
      { text: "Delete audit", style: "destructive", onPress: () => void runDeletion(() => deleteNotificationAuditEvents(session), "Notification audit deleted", "audit record") },
    ]);
  }

  function confirmHealthDelete() {
    if (!session) return;
    Alert.alert("Delete device health history?", "This permanently removes the retained battery, charging, and network summaries from ORA.", [
      { text: "Cancel", style: "cancel" },
      { text: "Delete history", style: "destructive", onPress: () => void runDeletion(() => deleteDeviceHealthHistory(session), "Health history deleted", "health snapshot") },
    ]);
  }

  async function runDeletion(action: () => Promise<number>, title: string, noun: string) {
    setClearing(true);
    try {
      const count = await action();
      Alert.alert(title, `${count} ${noun}${count === 1 ? "" : "s"} removed.`);
      if (noun === "health snapshot") setHealth(null);
    } catch (error) {
      Alert.alert("Delete failed", error instanceof Error ? error.message : "Please try again.");
    } finally {
      setClearing(false);
      void refreshAwareness();
    }
  }

  async function togglePause(value: boolean) {
    if (!session) return;
    setWorking("pause");
    try {
      await updateCommandPreferences({ global_pause: value });
      Alert.alert(value ? "Awareness paused" : "Awareness resumed", value ? "ORA will reject new phone awareness data until you resume it. Existing records remain under their retention controls." : "Your enabled awareness sources can send new consented data again.");
    } catch (error) {
      Alert.alert("Pause setting was not changed", error instanceof Error ? error.message : "Please try again.");
    } finally {
      setWorking(null);
    }
  }

  async function toggleQuietHours(value: boolean) {
    if (!session) return;
    setWorking("quiet");
    try {
      await updateCommandPreferences(value ? { quiet_hours_enabled: true, quiet_start: "22:00", quiet_end: "07:00" } : { quiet_hours_enabled: false });
    } catch (error) {
      Alert.alert("Quiet hours were not changed", error instanceof Error ? error.message : "Please try again.");
    } finally {
      setWorking(null);
    }
  }

  async function toggleContacts(value: boolean) {
    if (!session) return;
    setWorking("contacts");
    try {
      if (!value) {
        await setAwarenessConsent(session, "selected_contacts", false);
        setContacts([]);
      } else {
        await setAwarenessConsent(session, "selected_contacts", true);
        Alert.alert("Selected contacts only", "ORA never imports your full address book. Tap Add selected contact to choose individual people from Android’s contact picker.");
      }
      await refreshAwareness();
    } catch (error) {
      Alert.alert("Contacts setting was not changed", error instanceof Error ? error.message : "Please try again.");
    } finally {
      setWorking(null);
    }
  }

  async function addSelectedContact() {
    if (!session) return;
    if (Platform.OS === "web") {
      Alert.alert("Android device required", "Contact selection is available only in the installed Companion.");
      return;
    }
    setWorking("contacts");
    try {
      const permission = await Contacts.requestPermissionsAsync();
      if (!permission.granted) throw new Error("Android Contacts permission was not granted.");
      const contact = await Contacts.presentContactPickerAsync();
      if (!contact) return;
      const phone = contact.phoneNumbers?.[0]?.number?.replace(/[\s()-]/g, "") || undefined;
      const candidate: SelectedContact = { display_name: contact.name || contact.firstName || "Selected contact", normalized_phone: phone };
      const next = contacts.some((item) => item.display_name === candidate.display_name && item.normalized_phone === candidate.normalized_phone) ? contacts : [...contacts, candidate];
      setContacts(await replaceSelectedContacts(session, next));
    } catch (error) {
      Alert.alert("Contact was not added", error instanceof Error ? error.message : "Please try again.");
    } finally {
      setWorking(null);
    }
  }

  async function removeSelectedContact(index: number) {
    if (!session) return;
    setWorking("contacts");
    try {
      setContacts(await replaceSelectedContacts(session, contacts.filter((_, currentIndex) => currentIndex !== index)));
    } catch (error) {
      Alert.alert("Contact was not removed", error instanceof Error ? error.message : "Please try again.");
    } finally {
      setWorking(null);
    }
  }

  async function toggleHealth(value: boolean) {
    if (!session) return;
    setWorking("health");
    try {
      await setAwarenessConsent(session, "device_health", value, 24);
      if (!value) setHealth(null);
      await refreshAwareness();
    } catch (error) {
      Alert.alert("Device health setting was not changed", error instanceof Error ? error.message : "Please try again.");
    } finally {
      setWorking(null);
    }
  }

  async function refreshHealthNow() {
    if (!session || Platform.OS === "web") {
      Alert.alert("Android device required", "Device health is available only in the installed Companion.");
      return;
    }
    setWorking("health");
    try {
      if (!await Battery.isAvailableAsync()) throw new Error("Battery information is unavailable on this device.");
      const [level, state, network] = await Promise.all([Battery.getBatteryLevelAsync(), Battery.getBatteryStateAsync(), Network.getNetworkStateAsync()]);
      if (level < 0) throw new Error("Battery information is unavailable on this device.");
      const snapshot = await submitDeviceHealth(session, {
        battery_percent: Math.round(level * 100),
        is_charging: state === Battery.BatteryState.CHARGING || state === Battery.BatteryState.FULL,
        network_type: String(network.type || "unknown").toLowerCase(),
      });
      setHealth(snapshot);
    } catch (error) {
      Alert.alert("Health snapshot was not saved", error instanceof Error ? error.message : "Please try again.");
    } finally {
      setWorking(null);
    }
  }

  return (
    <ScreenContainer className="bg-background" edges={["top", "left", "right"]}>
      <ScrollView contentContainerStyle={styles.content}>
        <Text className="text-xs font-bold tracking-[4px] text-primary">ORA // PRIVACY</Text>
        <Text className="mt-2 text-3xl font-bold text-foreground">Your phone, your control.</Text>
        <Text className="mt-3 text-sm leading-5 text-muted">The Companion stores only a revocable device credential. It never stores ORA’s owner API token, and every phone source can be paused or removed here.</Text>

        <ControlCard title="Pause all awareness" detail="Stop new location, notification, contact, and health data from being accepted by ORA. It does not erase existing records." value={Boolean(preferences?.global_pause)} busy={working === "pause"} onValueChange={(value) => void togglePause(value)} state={preferences?.global_pause ? "Paused" : "Receiving enabled sources"} warning />
        <ControlCard title="Quiet hours" detail="Delivery policy for non-urgent ORA notifications. Uses 10 PM–7 AM in Africa/Nairobi; remote push remains configuration-required until FCM is connected." value={Boolean(preferences?.quiet_hours_enabled)} busy={working === "quiet"} onValueChange={(value) => void toggleQuietHours(value)} state={preferences?.quiet_hours_enabled ? "22:00–07:00 Nairobi" : "Off"} />

        <View className="rounded-3xl border border-border bg-surface p-5">
          <Text className="text-base font-bold text-foreground">Paired device</Text>
          <Text className="mt-3 text-lg font-semibold text-foreground">{device?.label ?? "No paired phone"}</Text>
          <Text className="mt-1 text-sm text-muted">{session ? `Device ID: ${session.deviceId}` : "Pairing is required before ORA can receive device events."}</Text>
          {device ? <Text className="mt-4 text-sm text-muted">Token ending: •••{device.token_hint}</Text> : null}
          {session ? <Text className="mt-1 text-sm text-muted">Backend: {session.backendUrl}</Text> : null}
        </View>

        <View style={styles.card}>
          <View style={styles.row}><View style={styles.grow}><Text style={styles.cardTitle}>Selected contacts</Text><Text style={styles.cardDetail}>Choose people one-by-one from Android. ORA receives only names, an optional selected phone number, and an optional relationship label—never your entire address book.</Text><Text style={styles.state}>{contactsConsent?.enabled ? `${contacts.length} selected` : "Off"}</Text></View><Switch value={Boolean(contactsConsent?.enabled)} disabled={working === "contacts"} onValueChange={(value) => void toggleContacts(value)} trackColor={{ false: "#1D3931", true: "#00A878" }} thumbColor={contactsConsent?.enabled ? "#00E6A7" : "#95AAA3"} /></View>
          {contactsConsent?.enabled ? <><Pressable disabled={working === "contacts"} onPress={() => void addSelectedContact()} style={({ pressed }) => [styles.primaryButton, (pressed || working === "contacts") && styles.pressed]}><Text style={styles.primaryText}>{working === "contacts" ? "WORKING…" : "ADD SELECTED CONTACT"}</Text></Pressable><View style={styles.miniList}>{contacts.map((contact, index) => <Pressable key={`${contact.display_name}-${contact.normalized_phone || index}`} onPress={() => void removeSelectedContact(index)} style={({ pressed }) => [styles.miniRow, pressed && styles.pressed]}><View><Text style={styles.miniTitle}>{contact.display_name}</Text><Text style={styles.miniDetail}>{contact.normalized_phone || "Name only"}</Text></View><Text style={styles.remove}>REMOVE</Text></Pressable>)}</View></> : null}
        </View>

        <View style={styles.card}>
          <View style={styles.row}><View style={styles.grow}><Text style={styles.cardTitle}>Device health</Text><Text style={styles.cardDetail}>A manual snapshot can include battery percentage, charging state, and network type. It never collects an IP address, Wi-Fi name, app usage, or a background feed.</Text><Text style={styles.state}>{healthConsent?.enabled ? `Retention: ${healthConsent.retention_hours} hours` : "Off"}</Text></View><Switch value={Boolean(healthConsent?.enabled)} disabled={working === "health"} onValueChange={(value) => void toggleHealth(value)} trackColor={{ false: "#1D3931", true: "#00A878" }} thumbColor={healthConsent?.enabled ? "#00E6A7" : "#95AAA3"} /></View>
          {healthConsent?.enabled ? <><Pressable disabled={working === "health"} onPress={() => void refreshHealthNow()} style={({ pressed }) => [styles.primaryButton, (pressed || working === "health") && styles.pressed]}><Text style={styles.primaryText}>{working === "health" ? "SAVING…" : "SAVE HEALTH SNAPSHOT"}</Text></Pressable><Text style={styles.miniDetail}>{health ? `Last saved: ${health.battery_percent}% · ${health.is_charging ? "Charging" : "On battery"} · ${health.network_type}` : "No health snapshot saved."}</Text><Pressable disabled={clearing} onPress={confirmHealthDelete} style={({ pressed }) => [styles.neutralButton, (pressed || clearing) && styles.pressed]}><Text style={styles.neutralText}>DELETE HEALTH HISTORY</Text></Pressable></> : null}
        </View>

        <View className="rounded-3xl border border-border p-5">
          <Text className="text-base font-bold text-foreground">Current awareness</Text>
          <Text className="mt-2 text-sm leading-5 text-muted">{enabled.length ? `Enabled: ${enabled.join(", ")}.` : "No awareness source is enabled."}</Text>
          <Text className="mt-2 text-sm leading-5 text-muted">Named-zone routines retain only arrival/departure events. Continuous location retains precise samples for {continuous?.enabled ? `${continuous.retention_hours} hours` : "no time because it is off"}.</Text>
        </View>

        {session ? <><Pressable disabled={clearing} onPress={confirmLocationDelete} style={({ pressed }) => [styles.neutralButton, (pressed || clearing) && styles.pressed]}><Text style={styles.neutralText}>{clearing ? "DELETING…" : "DELETE PRECISE LOCATION HISTORY"}</Text></Pressable><Pressable disabled={clearing} onPress={confirmNotificationDelete} style={({ pressed }) => [styles.neutralButton, (pressed || clearing) && styles.pressed]}><Text style={styles.neutralText}>DELETE NOTIFICATION AUDIT</Text></Pressable></> : null}

        {session ? <Pressable disabled={busy} onPress={confirmRevocation} style={({ pressed }) => [styles.revokeButton, (pressed || busy) && styles.pressed]}><Text style={styles.revokeText}>{busy ? "WORKING…" : "REVOKE THIS DEVICE"}</Text></Pressable> : <Pressable disabled={busy} onPress={() => void forgetLocalSession()} style={({ pressed }) => [styles.neutralButton, (pressed || busy) && styles.pressed]}><Text style={styles.neutralText}>CLEAR LOCAL STATE</Text></Pressable>}
      </ScrollView>
    </ScreenContainer>
  );
}

function ControlCard({ title, detail, state, value, busy, onValueChange, warning = false }: { title: string; detail: string; state: string; value: boolean; busy: boolean; onValueChange: (value: boolean) => void; warning?: boolean }) {
  return <View style={styles.card}><View style={styles.row}><View style={styles.grow}><Text style={styles.cardTitle}>{title}</Text><Text style={styles.cardDetail}>{detail}</Text><Text style={[styles.state, warning && value ? styles.warning : undefined]}>{busy ? "WORKING…" : state.toUpperCase()}</Text></View><Switch value={value} disabled={busy} onValueChange={onValueChange} trackColor={{ false: "#1D3931", true: "#00A878" }} thumbColor={value ? "#00E6A7" : "#95AAA3"} /></View></View>;
}

const styles = StyleSheet.create({
  content: { padding: 20, paddingBottom: 30, gap: 16 },
  card: { borderWidth: 1, borderColor: "#1D3931", backgroundColor: "#0D201A", borderRadius: 24, padding: 20 },
  row: { flexDirection: "row", alignItems: "flex-start", gap: 14 },
  grow: { flex: 1 },
  cardTitle: { color: "#E7F3EE", fontSize: 16, fontWeight: "800" },
  cardDetail: { color: "#95AAA3", fontSize: 13, lineHeight: 19, marginTop: 8 },
  state: { color: "#00E6A7", fontSize: 10, fontWeight: "900", letterSpacing: 1, marginTop: 13 },
  warning: { color: "#F6C86A" },
  primaryButton: { minHeight: 46, marginTop: 15, borderRadius: 13, alignItems: "center", justifyContent: "center", backgroundColor: "#00A878" },
  primaryText: { color: "#071B16", fontWeight: "900", fontSize: 11, letterSpacing: 1 },
  miniList: { marginTop: 12, gap: 8 },
  miniRow: { minHeight: 48, paddingHorizontal: 12, borderRadius: 12, borderWidth: 1, borderColor: "#1D3931", flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  miniTitle: { color: "#E7F3EE", fontSize: 13, fontWeight: "700" },
  miniDetail: { color: "#95AAA3", fontSize: 12, lineHeight: 17, marginTop: 12 },
  remove: { color: "#F87171", fontWeight: "900", fontSize: 10, letterSpacing: 0.8 },
  revokeButton: { minHeight: 50, marginTop: 14, borderRadius: 14, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: "#F87171" },
  neutralButton: { minHeight: 50, marginTop: 12, borderRadius: 14, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: "#95AAA3" },
  revokeText: { color: "#F87171", fontWeight: "800", fontSize: 12, letterSpacing: 1.2 },
  neutralText: { color: "#95AAA3", fontWeight: "800", fontSize: 11, letterSpacing: 0.8 },
  pressed: { opacity: 0.8, transform: [{ scale: 0.98 }] },
});
