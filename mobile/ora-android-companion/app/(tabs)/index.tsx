import { useMemo } from "react";
import { ActivityIndicator, Alert, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import MaterialIcons from "@expo/vector-icons/MaterialIcons";
import { router } from "expo-router";

import { ScreenContainer } from "@/components/screen-container";
import { useDevice } from "@/lib/device-provider";

function formatWhen(value?: string | null) {
  if (!value) return "Not yet";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString(undefined, { weekday: "short", hour: "numeric", minute: "2-digit" });
}

function timeGreeting() {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

function priorityTone(priority: string) {
  if (priority === "high") return styles.priorityHigh;
  if (priority === "low") return styles.priorityLow;
  return styles.priorityMedium;
}

export default function TodayScreen() {
  const {
    session,
    device,
    commandCenter,
    loading,
    busy,
    error,
    refresh,
    refreshCommandCenter,
    completeTask,
    acknowledgeAlert,
    updateCommandPreferences,
  } = useDevice();
  const connected = Boolean(session && device?.status === "active");
  const tasks = commandCenter?.tasks ?? [];
  const alerts = (commandCenter?.alerts ?? []).filter((alert) => !alert.acknowledged);
  const topTasks = tasks.slice(0, 3);
  const greeting = useMemo(() => timeGreeting(), []);

  async function handleRefresh() {
    await Promise.all([refresh(), refreshCommandCenter()]);
  }

  async function handleTask(taskId: number) {
    try {
      await completeTask(taskId);
    } catch (err) {
      Alert.alert("Task not updated", err instanceof Error ? err.message : "Try again after checking ORA.");
    }
  }

  async function handleAcknowledge(alertId: number) {
    try {
      await acknowledgeAlert(alertId);
    } catch (err) {
      Alert.alert("Alert not updated", err instanceof Error ? err.message : "Try again after checking ORA.");
    }
  }

  async function handleResume() {
    try {
      await updateCommandPreferences({ global_pause: false });
    } catch (err) {
      Alert.alert("Unable to resume", err instanceof Error ? err.message : "Try again after checking ORA.");
    }
  }

  if (loading) {
    return (
      <ScreenContainer className="items-center justify-center bg-background">
        <ActivityIndicator color="#00E6A7" />
        <Text className="mt-4 text-sm text-muted">Opening your private command center…</Text>
      </ScreenContainer>
    );
  }

  if (!connected) {
    return (
      <ScreenContainer className="bg-background" edges={["top", "left", "right"]}>
        <View style={styles.unpairedWrap}>
          <View style={styles.orb} />
          <Text style={styles.eyebrow}>ORA // COMMAND CENTER</Text>
          <Text style={styles.unpairedTitle}>Your day, held privately.</Text>
          <Text style={styles.unpairedBody}>Pair this phone to view briefings, review approved captures, and choose every awareness capability deliberately.</Text>
          <Pressable onPress={() => router.push("/pair" as never)} style={({ pressed }) => [styles.primaryCta, pressed && styles.pressed]}>
            <Text style={styles.primaryCtaText}>CONNECT ORA</Text>
            <MaterialIcons name="arrow-forward" color="#08110F" size={19} />
          </Pressable>
          {error ? <Text style={styles.errorText}>{error}</Text> : null}
        </View>
      </ScreenContainer>
    );
  }

  return (
    <ScreenContainer className="bg-background" edges={["top", "left", "right"]}>
      <ScrollView contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
        <View style={styles.topBar}>
          <View>
            <Text style={styles.eyebrow}>ORA // TODAY</Text>
            <Text style={styles.greeting}>{greeting}, Elisha.</Text>
          </View>
          <View style={styles.topActions}>
            <Pressable accessibilityLabel="Open approvals" onPress={() => router.push("/approvals" as never)} style={({ pressed }) => [styles.refreshButton, pressed && styles.pressed]}>
              <MaterialIcons name="verified-user" color="#F5B94C" size={20} />
            </Pressable>
            <Pressable
              accessibilityLabel="Refresh command center"
              disabled={busy}
              onPress={() => void handleRefresh()}
              style={({ pressed }) => [styles.refreshButton, (pressed || busy) && styles.pressed]}
            >
              {busy ? <ActivityIndicator color="#00E6A7" size="small" /> : <MaterialIcons name="refresh" color="#00E6A7" size={21} />}
            </Pressable>
          </View>
        </View>

        {commandCenter?.preferences.global_pause ? (
          <View style={styles.pauseCard}>
            <View style={styles.pauseIcon}><MaterialIcons name="pause-circle-filled" color="#F5B94C" size={22} /></View>
            <View style={styles.pauseCopy}><Text style={styles.pauseTitle}>Awareness is paused</Text><Text style={styles.pauseBody}>ORA is not accepting new phone awareness data.</Text></View>
            <Pressable onPress={() => void handleResume()} style={({ pressed }) => [styles.resumeButton, pressed && styles.pressed]}><Text style={styles.resumeText}>RESUME</Text></Pressable>
          </View>
        ) : null}

        <View style={styles.briefingCard}>
          <View style={styles.briefingEyebrowRow}>
            <Text style={styles.briefingLabel}>YOUR ORA BRIEFING</Text>
            <View style={styles.liveDot} />
          </View>
          <Text style={styles.briefingText}>{commandCenter?.briefing ?? "Refreshing today’s picture from ORA…"}</Text>
          <View style={styles.briefingFoot}><Text style={styles.briefingFootText}>Paired as {device?.label}</Text><Text style={styles.briefingFootText}>Synced {formatWhen(device?.last_seen_at)}</Text></View>
        </View>

        <View style={styles.metricRow}>
          <Pressable onPress={() => router.push("/inbox" as never)} style={({ pressed }) => [styles.metricCard, pressed && styles.pressed]}>
            <Text style={styles.metricValue}>{commandCenter?.pending_capture_count ?? 0}</Text>
            <Text style={styles.metricLabel}>INBOX</Text>
          </Pressable>
          <Pressable onPress={() => router.push("/activity" as never)} style={({ pressed }) => [styles.metricCard, pressed && styles.pressed]}>
            <Text style={styles.metricValue}>{commandCenter?.attention_count ?? 0}</Text>
            <Text style={styles.metricLabel}>ATTENTION</Text>
          </Pressable>
          <View style={styles.metricCard}>
            <Text style={styles.metricValue}>{tasks.length}</Text>
            <Text style={styles.metricLabel}>TASKS</Text>
          </View>
        </View>

        <View style={styles.sectionHeader}>
          <View><Text style={styles.sectionKicker}>FOCUS</Text><Text style={styles.sectionTitle}>What matters next</Text></View>
          <Pressable onPress={() => router.push("/inbox" as never)}><Text style={styles.linkText}>VIEW INBOX</Text></Pressable>
        </View>
        <View style={styles.stack}>
          {topTasks.length ? topTasks.map((task) => (
            <View style={styles.taskCard} key={task.id}>
              <Pressable accessibilityLabel={`Complete ${task.title}`} onPress={() => void handleTask(task.id)} style={({ pressed }) => [styles.completeControl, pressed && styles.pressed]}>
                <MaterialIcons name="check" size={17} color="#08110F" />
              </Pressable>
              <View style={styles.taskCopy}><Text numberOfLines={2} style={styles.taskTitle}>{task.title}</Text><Text style={styles.taskMeta}>{task.due_at ? `Due ${formatWhen(task.due_at)}` : "No due time set"}</Text></View>
              <View style={[styles.priorityChip, priorityTone(task.priority)]}><Text style={styles.priorityText}>{task.priority.toUpperCase()}</Text></View>
            </View>
          )) : (
            <View style={styles.emptyCard}><MaterialIcons name="check-circle-outline" color="#38D996" size={24} /><Text style={styles.emptyText}>No pending tasks. Your focus is clear.</Text></View>
          )}
        </View>

        {alerts.length ? (
          <>
            <View style={styles.sectionHeader}><View><Text style={styles.sectionKicker}>ATTENTION</Text><Text style={styles.sectionTitle}>Needs your review</Text></View><Pressable onPress={() => router.push("/activity" as never)}><Text style={styles.linkText}>SEE ALL</Text></Pressable></View>
            <View style={styles.stack}>
              {alerts.slice(0, 2).map((alert) => (
                <View style={styles.alertCard} key={alert.id}>
                  <MaterialIcons name={alert.severity === "high" || alert.severity === "critical" ? "priority-high" : "info-outline"} color="#F5B94C" size={22} />
                  <View style={styles.alertCopy}><Text numberOfLines={1} style={styles.alertTitle}>{alert.rule_name}</Text><Text numberOfLines={2} style={styles.alertBody}>{alert.message}</Text></View>
                  <Pressable onPress={() => void handleAcknowledge(alert.id)} style={({ pressed }) => [styles.ackButton, pressed && styles.pressed]}><Text style={styles.ackText}>DONE</Text></Pressable>
                </View>
              ))}
            </View>
          </>
        ) : null}

        <View style={styles.quickCard}>
          <View><Text style={styles.sectionKicker}>QUICK CAPTURE</Text><Text style={styles.quickTitle}>Save something for ORA</Text><Text style={styles.quickBody}>Send a thought, link, or voice note to your reviewable inbox.</Text></View>
          <Pressable onPress={() => router.push("/inbox" as never)} style={({ pressed }) => [styles.quickButton, pressed && styles.pressed]}><MaterialIcons name="add" color="#08110F" size={22} /></Pressable>
        </View>
        {error ? <Text style={styles.errorText}>{error}</Text> : null}
      </ScrollView>
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  scrollContent: { padding: 20, paddingBottom: 34, gap: 18 },
  topBar: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: 2 },
  topActions: { flexDirection: "row", gap: 8 },
  eyebrow: { color: "#00E6A7", fontSize: 11, fontWeight: "800", letterSpacing: 3.4 },
  greeting: { color: "#F2FFF9", fontSize: 29, fontWeight: "700", letterSpacing: -0.6, marginTop: 7 },
  refreshButton: { height: 44, width: 44, borderRadius: 14, borderWidth: 1, borderColor: "#1D3931", backgroundColor: "#10201C", alignItems: "center", justifyContent: "center" },
  briefingCard: { backgroundColor: "#10201C", borderColor: "#1D3931", borderWidth: 1, borderRadius: 26, padding: 20, gap: 13 },
  briefingEyebrowRow: { flexDirection: "row", alignItems: "center", gap: 7 },
  briefingLabel: { color: "#95AAA3", fontSize: 10, fontWeight: "800", letterSpacing: 2.1 },
  liveDot: { width: 7, height: 7, borderRadius: 4, backgroundColor: "#38D996" },
  briefingText: { color: "#F2FFF9", fontSize: 20, fontWeight: "600", lineHeight: 28, letterSpacing: -0.2 },
  briefingFoot: { borderTopColor: "#1D3931", borderTopWidth: 1, paddingTop: 12, flexDirection: "row", justifyContent: "space-between", gap: 10 },
  briefingFootText: { color: "#95AAA3", fontSize: 11, flex: 1 },
  metricRow: { flexDirection: "row", gap: 9 },
  metricCard: { flex: 1, minHeight: 80, backgroundColor: "#0D1916", borderColor: "#1D3931", borderWidth: 1, borderRadius: 18, padding: 13, justifyContent: "space-between" },
  metricValue: { color: "#F2FFF9", fontSize: 26, fontWeight: "700" },
  metricLabel: { color: "#95AAA3", fontSize: 9, fontWeight: "800", letterSpacing: 1.4 },
  sectionHeader: { flexDirection: "row", alignItems: "flex-end", justifyContent: "space-between", marginTop: 4 },
  sectionKicker: { color: "#95AAA3", fontSize: 10, fontWeight: "800", letterSpacing: 1.8 },
  sectionTitle: { color: "#F2FFF9", fontSize: 18, fontWeight: "700", marginTop: 3 },
  linkText: { color: "#4CA7FF", fontSize: 10, fontWeight: "800", letterSpacing: 1.2, paddingVertical: 6 },
  stack: { gap: 9 },
  taskCard: { minHeight: 74, flexDirection: "row", alignItems: "center", gap: 12, backgroundColor: "#10201C", borderColor: "#1D3931", borderWidth: 1, borderRadius: 18, padding: 13 },
  completeControl: { width: 30, height: 30, borderRadius: 15, alignItems: "center", justifyContent: "center", backgroundColor: "#00E6A7" },
  taskCopy: { flex: 1, gap: 4 },
  taskTitle: { color: "#F2FFF9", fontSize: 14, fontWeight: "600" },
  taskMeta: { color: "#95AAA3", fontSize: 11 },
  priorityChip: { borderRadius: 8, paddingHorizontal: 7, paddingVertical: 5 },
  priorityHigh: { backgroundColor: "#4A2A29" },
  priorityMedium: { backgroundColor: "#40361D" },
  priorityLow: { backgroundColor: "#18342B" },
  priorityText: { color: "#F2FFF9", fontSize: 8, fontWeight: "800", letterSpacing: 0.8 },
  alertCard: { minHeight: 80, flexDirection: "row", alignItems: "center", gap: 11, backgroundColor: "#1C1B14", borderColor: "#51431D", borderWidth: 1, borderRadius: 18, padding: 13 },
  alertCopy: { flex: 1, gap: 4 },
  alertTitle: { color: "#FFF6D9", fontSize: 13, fontWeight: "700" },
  alertBody: { color: "#C4B995", fontSize: 11, lineHeight: 16 },
  ackButton: { paddingVertical: 8, paddingHorizontal: 6 },
  ackText: { color: "#F5B94C", fontSize: 9, fontWeight: "800", letterSpacing: 0.9 },
  quickCard: { minHeight: 126, borderRadius: 24, padding: 18, backgroundColor: "#12382E", borderColor: "#1F5948", borderWidth: 1, flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: 16 },
  quickTitle: { color: "#F2FFF9", fontSize: 19, fontWeight: "700", marginTop: 4 },
  quickBody: { color: "#B8D7CD", fontSize: 12, lineHeight: 18, maxWidth: 230, marginTop: 5 },
  quickButton: { width: 46, height: 46, borderRadius: 23, backgroundColor: "#00E6A7", alignItems: "center", justifyContent: "center" },
  pauseCard: { flexDirection: "row", alignItems: "center", gap: 10, borderRadius: 18, padding: 13, backgroundColor: "#1C1B14", borderColor: "#51431D", borderWidth: 1 },
  pauseIcon: { width: 30, alignItems: "center" },
  pauseCopy: { flex: 1 },
  pauseTitle: { color: "#FFF6D9", fontSize: 13, fontWeight: "700" },
  pauseBody: { color: "#C4B995", fontSize: 11, marginTop: 2 },
  resumeButton: { paddingHorizontal: 8, paddingVertical: 8 },
  resumeText: { color: "#F5B94C", fontSize: 10, fontWeight: "800" },
  emptyCard: { minHeight: 72, flexDirection: "row", alignItems: "center", gap: 10, borderRadius: 18, backgroundColor: "#10201C", borderWidth: 1, borderColor: "#1D3931", padding: 14 },
  emptyText: { color: "#B8D7CD", fontSize: 13, flex: 1 },
  unpairedWrap: { flex: 1, justifyContent: "center", padding: 28 },
  orb: { width: 68, height: 68, borderRadius: 34, backgroundColor: "#12382E", borderWidth: 1, borderColor: "#1F5948", marginBottom: 28 },
  unpairedTitle: { color: "#F2FFF9", fontSize: 36, fontWeight: "700", letterSpacing: -1, lineHeight: 42, marginTop: 8 },
  unpairedBody: { color: "#95AAA3", fontSize: 15, lineHeight: 23, marginTop: 15, maxWidth: 320 },
  primaryCta: { minHeight: 54, borderRadius: 16, backgroundColor: "#00E6A7", flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 10, marginTop: 30 },
  primaryCtaText: { color: "#08110F", fontSize: 12, fontWeight: "800", letterSpacing: 1.3 },
  errorText: { color: "#F87171", fontSize: 12, lineHeight: 18, marginTop: 8 },
  pressed: { opacity: 0.82, transform: [{ scale: 0.98 }] },
});
