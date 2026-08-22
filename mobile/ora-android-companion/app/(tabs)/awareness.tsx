import { Alert, Pressable, ScrollView, StyleSheet, Switch, Text, View } from "react-native";
import { useEffect, useState } from "react";

import { ScreenContainer } from "@/components/screen-container";
import {
  disableContinuousLocation,
  disablePushAlerts,
  disableZoneRoutines,
  enableContinuousLocation,
  enablePushAlerts,
  enableZoneRoutines,
  saveCurrentPlaceAsZone,
} from "@/lib/awareness-controls";
import { capabilityEnabled, continuousRetentionHours } from "@/lib/awareness-policy";
import { useDevice } from "@/lib/device-provider";
import {
  getNotificationSources,
  replaceNotificationSources,
  setAwarenessConsent,
  type AwarenessCapability,
  type AwarenessZone,
  type NotificationSource,
} from "@/lib/ora-device";
import {
  clearQueuedNotificationEvents,
  configureNotificationListener,
  getNotificationListenerStatus,
  openNotificationListenerSettings,
  synchronizeQueuedNotificationEvents,
} from "@/lib/notification-listener";

const labels: Record<AwarenessCapability, string> = {
  push_alerts: "Push alerts",
  zone_routines: "Named-zone routines",
  continuous_location: "Continuous location",
  notification_access: "Selected notifications",
  selected_contacts: "Selected contacts",
  device_health: "Device health",
};

const notificationChoices = [
  { package_name: "com.google.android.apps.messaging", app_label: "Google Messages" },
  { package_name: "com.whatsapp", app_label: "WhatsApp" },
  { package_name: "com.google.android.gm", app_label: "Gmail" },
  { package_name: "org.telegram.messenger", app_label: "Telegram" },
] as const;

export default function AwarenessScreen() {
  const { session, awareness, refreshAwareness } = useDevice();
  const [working, setWorking] = useState<AwarenessCapability | "zone" | null>(null);
  const [notificationSources, setNotificationSources] = useState<NotificationSource[]>([]);
  const [listenerStatus, setListenerStatus] = useState(getNotificationListenerStatus());
  const [syncingNotifications, setSyncingNotifications] = useState(false);

  const pushEnabled = capabilityEnabled(awareness, "push_alerts");
  const zonesEnabled = capabilityEnabled(awareness, "zone_routines");
  const continuousEnabled = capabilityEnabled(awareness, "continuous_location");
  const notificationEnabled = capabilityEnabled(awareness, "notification_access");
  const retention = continuousRetentionHours(awareness);

  useEffect(() => {
    let active = true;
    async function loadNotificationSetup() {
      if (!session || !notificationEnabled) return;
      try {
        const sources = await getNotificationSources(session);
        if (!active) return;
        setNotificationSources(sources);
        configureNotificationListener(true, sources);
      } catch {
        // The screen remains usable while a new backend deployment is pending.
      } finally {
        if (active) setListenerStatus(getNotificationListenerStatus());
      }
    }
    void loadNotificationSetup();
    return () => { active = false; };
  }, [notificationEnabled, session]);

  async function run(key: AwarenessCapability | "zone", action: () => Promise<unknown>) {
    if (!session) {
      Alert.alert("Pair ORA first", "Pair this phone before enabling a phone awareness capability.");
      return;
    }
    setWorking(key);
    try {
      await action();
      await refreshAwareness();
    } catch (error) {
      Alert.alert(`${key === "zone" ? "Named place" : labels[key]} was not enabled`, error instanceof Error ? error.message : "Please try again.");
    } finally {
      setWorking(null);
    }
  }

  function togglePush(value: boolean) {
    if (!session) return;
    if (!value) {
      Alert.alert("Turn off push alerts?", "ORA will remove this phone’s push token. You can enable it again later.", [
        { text: "Cancel", style: "cancel" },
        { text: "Turn off", style: "destructive", onPress: () => void run("push_alerts", () => disablePushAlerts(session)) },
      ]);
      return;
    }
    void run("push_alerts", () => enablePushAlerts(session));
  }

  function toggleZones(value: boolean) {
    if (!session) return;
    if (!value) {
      Alert.alert("Turn off zone routines?", "ORA will remove your saved named zones from the phone and backend.", [
        { text: "Cancel", style: "cancel" },
        { text: "Turn off", style: "destructive", onPress: () => void run("zone_routines", () => disableZoneRoutines(session)) },
      ]);
      return;
    }
    void run("zone_routines", () => enableZoneRoutines(session));
  }

  function toggleContinuous(value: boolean) {
    if (!session) return;
    if (!value) {
      Alert.alert("Stop continuous location?", "ORA will stop the visible Android location service immediately. Retained samples stay until you delete them in Privacy.", [
        { text: "Cancel", style: "cancel" },
        { text: "Stop", style: "destructive", onPress: () => void run("continuous_location", () => disableContinuousLocation(session)) },
      ]);
      return;
    }
    Alert.alert(
      "Enable continuous location?",
      `ORA will show a persistent Android notification while active and retain precise samples for ${retention} hours. You can stop it here and delete samples in Privacy.`,
      [
        { text: "Cancel", style: "cancel" },
        { text: "Enable", onPress: () => void run("continuous_location", () => enableContinuousLocation(session, retention)) },
      ],
    );
  }

  function toggleNotifications(value: boolean) {
    if (!session) return;
    if (!value) {
      Alert.alert("Turn off selected notifications?", "ORA will stop reading notification events, clear the phone’s unsent listener queue, and keep no new notification data. Existing review records can be deleted in Privacy.", [
        { text: "Cancel", style: "cancel" },
        { text: "Turn off", style: "destructive", onPress: () => void run("notification_access", async () => {
          configureNotificationListener(false, []);
          clearQueuedNotificationEvents();
          setNotificationSources([]);
          setListenerStatus(getNotificationListenerStatus());
          return setAwarenessConsent(session, "notification_access", false);
        }) },
      ]);
      return;
    }
    Alert.alert("Enable selected notifications?", "Choose only the apps ORA may see next. Android will show its own Notification access settings; ORA never replies, clears, snoozes, or acts on those notifications.", [
      { text: "Cancel", style: "cancel" },
      { text: "Continue", onPress: () => void run("notification_access", async () => {
        const result = await setAwarenessConsent(session, "notification_access", true, 72);
        setListenerStatus(getNotificationListenerStatus());
        openNotificationListenerSettings();
        return result;
      }) },
    ]);
  }

  function cycleNotificationSource(choice: (typeof notificationChoices)[number]) {
    setNotificationSources((current) => {
      const existing = current.find((source) => source.package_name === choice.package_name);
      if (!existing) return [...current, { ...choice, content_mode: "metadata", enabled: true }];
      if (existing.content_mode === "metadata") return current.map((source) => source.package_name === choice.package_name ? { ...source, content_mode: "redacted" } : source);
      if (existing.content_mode === "redacted") return current.map((source) => source.package_name === choice.package_name ? { ...source, content_mode: "full" } : source);
      return current.filter((source) => source.package_name !== choice.package_name);
    });
  }

  async function saveNotificationSources() {
    if (!session) return;
    setWorking("notification_access");
    try {
      const saved = await replaceNotificationSources(session, notificationSources);
      setNotificationSources(saved);
      configureNotificationListener(true, saved);
      setListenerStatus(getNotificationListenerStatus());
      Alert.alert("Selected apps updated", `${saved.length} app${saved.length === 1 ? "" : "s"} may now send the mode you chose.`);
    } catch (error) {
      Alert.alert("Selected apps were not saved", error instanceof Error ? error.message : "Please try again.");
    } finally {
      setWorking(null);
    }
  }

  async function syncNotifications() {
    if (!session) return;
    setSyncingNotifications(true);
    try {
      const count = await synchronizeQueuedNotificationEvents(session);
      setListenerStatus(getNotificationListenerStatus());
      Alert.alert("Notification review synced", count ? `${count} queued event${count === 1 ? "" : "s"} added to the private audit.` : "There were no queued events to sync.");
    } catch (error) {
      Alert.alert("Sync paused", error instanceof Error ? error.message : "The phone kept the queue; you can retry or clear it by turning the feature off.");
    } finally {
      setSyncingNotifications(false);
    }
  }

  function saveZone(id: "home" | "work" | "commute", label: string) {
    if (!session) return;
    if (!zonesEnabled) {
      Alert.alert("Enable zone routines first", "Turn on named-zone routines, read the Android permission prompt, then save this place.");
      return;
    }
    void run("zone", () => saveCurrentPlaceAsZone(session, awareness?.zones ?? [], id, label));
  }

  const zoneButtons: { id: "home" | "work" | "commute"; label: string }[] = [
    { id: "home", label: "Save current place as Home" },
    { id: "work", label: "Save current place as Work" },
    { id: "commute", label: "Save current place as Commute" },
  ];

  return (
    <ScreenContainer className="bg-background" edges={["top", "left", "right"]}>
      <ScrollView contentContainerStyle={styles.content}>
        <Text className="text-xs font-bold tracking-[4px] text-primary">ORA // AWARENESS</Text>
        <Text className="mt-2 text-3xl font-bold text-foreground">You decide what ORA can know.</Text>
        <Text className="mt-3 text-sm leading-5 text-muted">Every source is separate, optional, and reversible. Permission prompts occur only after you select an awareness capability.</Text>

        <CapabilityCard
          title="Push alerts"
          detail="Receive ORA approval requests, urgent reminders, and selected service alerts. Android controls notification visibility after you grant permission."
          state={pushEnabled ? (awareness?.push.registered ? "Enabled and registered" : "Enabled — registration required") : "Off"}
          value={pushEnabled}
          busy={working === "push_alerts"}
          onValueChange={togglePush}
        />

        <CapabilityCard
          title="Named-zone routines"
          detail="Store up to five private places. ORA receives only entered/left events; it does not retain coordinates for this mode."
          state={zonesEnabled ? `${awareness?.zones.length ?? 0} named zones active` : "Off"}
          value={zonesEnabled}
          busy={working === "zone_routines"}
          onValueChange={toggleZones}
        />

        {zonesEnabled ? (
          <View className="rounded-3xl border border-border bg-surface p-5">
            <Text className="text-base font-bold text-foreground">Save named places</Text>
            <Text className="mt-2 text-sm leading-5 text-muted">Save your current phone location as a named routine. A 200 m boundary avoids over-sensitive GPS changes.</Text>
            <View className="mt-4 gap-3">
              {zoneButtons.map((zone) => (
                <Pressable key={zone.id} disabled={working !== null} onPress={() => saveZone(zone.id, zone.id === "home" ? "Home" : zone.id === "work" ? "Work" : "Commute")} style={({ pressed }) => [styles.secondaryButton, (pressed || working !== null) && styles.pressed]}>
                  <Text style={styles.secondaryText}>{working === "zone" ? "SAVING…" : zone.label.toUpperCase()}</Text>
                </Pressable>
              ))}
            </View>
            {awareness?.zones.length ? <ZoneSummary zones={awareness.zones} /> : null}
          </View>
        ) : null}

        <CapabilityCard
          title="Continuous location"
          detail="Use only when you want ongoing location updates. Android shows a persistent ORA notification while the routine is active."
          state={continuousEnabled ? `Active — precise samples retained for ${retention} hours` : "Off"}
          value={continuousEnabled}
          busy={working === "continuous_location"}
          onValueChange={toggleContinuous}
          warning
        />

        <CapabilityCard
          title="Selected notifications"
          detail="Choose specific apps and a content level. Events stay in a reviewable audit with a 72-hour limit; ORA cannot reply, dismiss, snooze, or open another app’s notification actions."
          state={!notificationEnabled ? "Off" : !listenerStatus.available ? "New standalone APK required" : listenerStatus.accessGranted ? `${notificationSources.length} selected app${notificationSources.length === 1 ? "" : "s"} · ${listenerStatus.queuedEventCount} queued` : "Android access required"}
          value={notificationEnabled}
          busy={working === "notification_access"}
          onValueChange={toggleNotifications}
          warning
        />

        {notificationEnabled ? (
          <View className="rounded-3xl border border-border bg-surface p-5">
            <Text className="text-base font-bold text-foreground">Notification access setup</Text>
            <Text className="mt-2 text-sm leading-5 text-muted">Android permission is separate from ORA consent. Choose a source repeatedly to cycle through OFF, METADATA, REDACTED, and FULL. Metadata records only the app and time; redacted removes links, codes, and email-like values before upload.</Text>
            <Pressable onPress={() => { openNotificationListenerSettings(); setListenerStatus(getNotificationListenerStatus()); }} style={({ pressed }) => [styles.secondaryButton, styles.setupButton, pressed && styles.pressed]}>
              <Text style={styles.secondaryText}>{listenerStatus.accessGranted ? "OPEN ANDROID NOTIFICATION ACCESS" : "GRANT ANDROID NOTIFICATION ACCESS"}</Text>
            </Pressable>
            {!listenerStatus.available ? <Text className="mt-3 text-xs leading-4 text-warning">This capability appears only in a newly published ORA Companion APK; it cannot run in Expo Go or the browser preview.</Text> : null}
            <View className="mt-4 gap-2">
              {notificationChoices.map((choice) => {
                const source = notificationSources.find((item) => item.package_name === choice.package_name);
                const mode = source?.content_mode || "off";
                return <Pressable key={choice.package_name} disabled={working !== null} onPress={() => cycleNotificationSource(choice)} style={({ pressed }) => [styles.sourceRow, (pressed || working !== null) && styles.pressed]}>
                  <Text style={styles.sourceTitle}>{choice.app_label}</Text>
                  <Text style={[styles.sourceMode, mode === "full" ? styles.fullMode : mode === "redacted" ? styles.redactedMode : mode === "metadata" ? styles.metadataMode : styles.offMode]}>{mode.toUpperCase()}</Text>
                </Pressable>;
              })}
            </View>
            <Pressable disabled={working !== null} onPress={() => void saveNotificationSources()} style={({ pressed }) => [styles.primaryButton, (pressed || working !== null) && styles.pressed]}>
              <Text style={styles.primaryText}>{working === "notification_access" ? "SAVING…" : "SAVE SELECTED APPS"}</Text>
            </Pressable>
            <Pressable disabled={syncingNotifications || working !== null} onPress={() => void syncNotifications()} style={({ pressed }) => [styles.secondaryButton, styles.setupButton, (pressed || syncingNotifications || working !== null) && styles.pressed]}>
              <Text style={styles.secondaryText}>{syncingNotifications ? "SYNCING REVIEW QUEUE…" : "SYNC QUEUED EVENTS TO AUDIT"}</Text>
            </Pressable>
          </View>
        ) : null}

        <View className="rounded-3xl border border-border p-5">
          <Text className="text-sm font-bold text-foreground">Safety boundary</Text>
          <Text className="mt-2 text-sm leading-5 text-muted">Declining Android permission leaves pairing, check-ins, and Privacy controls available. Background location may stop if Android or the device manufacturer terminates the app; use the visible service notification to verify when continuous tracking is active.</Text>
        </View>
      </ScrollView>
    </ScreenContainer>
  );
}

function CapabilityCard({ title, detail, state, value, busy, onValueChange, warning = false }: { title: string; detail: string; state: string; value: boolean; busy: boolean; onValueChange: (value: boolean) => void; warning?: boolean }) {
  return (
    <View className="rounded-3xl border border-border bg-surface p-5">
      <View className="flex-row items-start justify-between gap-4">
        <View className="flex-1">
          <Text className="text-lg font-bold text-foreground">{title}</Text>
          <Text className="mt-2 text-sm leading-5 text-muted">{detail}</Text>
          <Text className={`mt-4 text-[11px] font-bold tracking-[1.2px] ${warning && value ? "text-warning" : value ? "text-success" : "text-muted"}`}>{busy ? "WORKING…" : state.toUpperCase()}</Text>
        </View>
        <Switch value={value} disabled={busy} onValueChange={onValueChange} trackColor={{ false: "#1D3931", true: "#00A878" }} thumbColor={value ? "#00E6A7" : "#95AAA3"} />
      </View>
    </View>
  );
}

function ZoneSummary({ zones }: { zones: AwarenessZone[] }) {
  return (
    <View className="mt-4 gap-2">
      {zones.map((zone) => <Text key={zone.id} className="text-xs text-muted">• {zone.label} — {zone.radius_m} m event boundary</Text>)}
    </View>
  );
}

const styles = StyleSheet.create({
  content: { padding: 20, paddingBottom: 30, gap: 16 },
  secondaryButton: { minHeight: 44, borderWidth: 1, borderColor: "#1D3931", borderRadius: 13, alignItems: "center", justifyContent: "center" },
  secondaryText: { color: "#00E6A7", fontWeight: "800", fontSize: 11, letterSpacing: 1.1 },
  setupButton: { marginTop: 14 },
  primaryButton: { minHeight: 46, borderRadius: 13, backgroundColor: "#00A878", alignItems: "center", justifyContent: "center", marginTop: 14 },
  primaryText: { color: "#071B16", fontWeight: "900", fontSize: 11, letterSpacing: 1.1 },
  sourceRow: { minHeight: 48, paddingHorizontal: 14, borderRadius: 13, borderWidth: 1, borderColor: "#1D3931", flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  sourceTitle: { color: "#E7F3EE", fontWeight: "700", fontSize: 14 },
  sourceMode: { fontSize: 10, fontWeight: "900", letterSpacing: 1.05 },
  offMode: { color: "#95AAA3" },
  metadataMode: { color: "#8EC5FF" },
  redactedMode: { color: "#00E6A7" },
  fullMode: { color: "#F6C86A" },
  pressed: { opacity: 0.72, transform: [{ scale: 0.98 }] },
});
