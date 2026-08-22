import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Alert, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import MaterialIcons from "@expo/vector-icons/MaterialIcons";
import { router } from "expo-router";

import { ScreenContainer } from "@/components/screen-container";
import {
  approveDeviceApproval,
  executeDeviceApproval,
  getDeviceApprovals,
  rejectDeviceApproval,
  type DeviceApproval,
} from "@/lib/ora-device";
import { useDevice } from "@/lib/device-provider";

function formatWhen(value?: string | null) {
  if (!value) return "No expiry set";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString(undefined, { weekday: "short", hour: "numeric", minute: "2-digit" });
}

export default function ApprovalsScreen() {
  const { session } = useDevice();
  const [approvals, setApprovals] = useState<DeviceApproval[]>([]);
  const [loading, setLoading] = useState(true);
  const [workingId, setWorkingId] = useState<number | null>(null);

  const load = useCallback(async () => {
    if (!session) {
      setApprovals([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      setApprovals(await getDeviceApprovals(session));
    } catch (error) {
      Alert.alert("Approvals unavailable", error instanceof Error ? error.message : "Please try again.");
    } finally {
      setLoading(false);
    }
  }, [session]);

  useEffect(() => {
    const timer = setTimeout(() => { void load(); }, 0);
    return () => clearTimeout(timer);
  }, [load]);

  async function approve(item: DeviceApproval) {
    if (!session) return;
    setWorkingId(item.id);
    try {
      await approveDeviceApproval(session, item.id);
      await load();
      Alert.alert("Approved, not sent", "The action is approved but has not run. Review it once more, then tap Execute if you want ORA to perform the external action.");
    } catch (error) {
      Alert.alert("Approval failed", error instanceof Error ? error.message : "Please try again.");
    } finally {
      setWorkingId(null);
    }
  }

  async function reject(item: DeviceApproval) {
    if (!session) return;
    setWorkingId(item.id);
    try {
      await rejectDeviceApproval(session, item.id);
      await load();
    } catch (error) {
      Alert.alert("Rejection failed", error instanceof Error ? error.message : "Please try again.");
    } finally {
      setWorkingId(null);
    }
  }

  async function execute(item: DeviceApproval) {
    if (!session) return;
    setWorkingId(item.id);
    try {
      const result = await executeDeviceApproval(session, item.id);
      await load();
      Alert.alert(result.status === "completed" ? "Action completed" : "Action did not complete", result.status === "completed" ? "ORA recorded the external action result in its activity history." : result.error || "Check the result status and try again only if appropriate.");
    } catch (error) {
      Alert.alert("Execution failed", error instanceof Error ? error.message : "Please try again.");
    } finally {
      setWorkingId(null);
    }
  }

  function confirmApprove(item: DeviceApproval) {
    Alert.alert("Approve this action?", `${item.title}\n\nApproval does not send, edit, or delete anything. Execution always needs one more tap.`, [
      { text: "Cancel", style: "cancel" },
      { text: "Approve", onPress: () => void approve(item) },
    ]);
  }

  function confirmReject(item: DeviceApproval) {
    Alert.alert("Reject this action?", "ORA will not execute this proposal. You can create a new proposal later if needed.", [
      { text: "Cancel", style: "cancel" },
      { text: "Reject", style: "destructive", onPress: () => void reject(item) },
    ]);
  }

  function confirmExecute(item: DeviceApproval) {
    Alert.alert("Execute approved action?", `${item.title}\n\nThis is the final user-tapped step. ORA will now attempt the external action and record the outcome.`, [
      { text: "Cancel", style: "cancel" },
      { text: "Execute now", style: "destructive", onPress: () => void execute(item) },
    ]);
  }

  const pending = approvals.filter((item) => item.status === "proposed" || item.status === "approved");
  const history = approvals.filter((item) => item.status !== "proposed" && item.status !== "approved");

  return (
    <ScreenContainer className="bg-background" edges={["top", "left", "right"]}>
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.topBar}>
          <Pressable accessibilityLabel="Go back" onPress={() => router.back()} style={({ pressed }) => [styles.iconButton, pressed && styles.pressed]}><MaterialIcons name="arrow-back" size={22} color="#00E6A7" /></Pressable>
          <Pressable accessibilityLabel="Refresh approvals" onPress={() => void load()} style={({ pressed }) => [styles.iconButton, pressed && styles.pressed]}>{loading ? <ActivityIndicator size="small" color="#00E6A7" /> : <MaterialIcons name="refresh" size={21} color="#00E6A7" />}</Pressable>
        </View>
        <Text style={styles.eyebrow}>ORA // APPROVALS</Text>
        <Text style={styles.title}>You stay in charge.</Text>
        <Text style={styles.subtitle}>ORA may prepare an action, but it cannot execute an external change until you approve it and then tap Execute separately. Sensitive payload details never appear in this device queue.</Text>

        <View style={styles.policyCard}><MaterialIcons name="verified-user" color="#00E6A7" size={22} /><Text style={styles.policyCopy}>Two deliberate steps: approve first, execute second. Rejecting ends the proposal without acting.</Text></View>

        <Text style={styles.sectionLabel}>NEEDS REVIEW · {pending.length}</Text>
        {loading ? <View style={styles.empty}><ActivityIndicator color="#00E6A7" /></View> : pending.length ? pending.map((item) => <ApprovalCard key={item.id} item={item} working={workingId === item.id} onApprove={() => confirmApprove(item)} onReject={() => confirmReject(item)} onExecute={() => confirmExecute(item)} />) : <View style={styles.empty}><MaterialIcons name="task-alt" color="#38D996" size={26} /><Text style={styles.emptyText}>No external actions are waiting for your decision.</Text></View>}

        {history.length ? <><Text style={[styles.sectionLabel, styles.historyLabel]}>RECENT OUTCOMES</Text>{history.slice(0, 8).map((item) => <ApprovalCard key={item.id} item={item} working={false} onApprove={() => undefined} onReject={() => undefined} onExecute={() => undefined} />)}</> : null}
      </ScrollView>
    </ScreenContainer>
  );
}

function ApprovalCard({ item, working, onApprove, onReject, onExecute }: { item: DeviceApproval; working: boolean; onApprove: () => void; onReject: () => void; onExecute: () => void }) {
  const ready = item.status === "proposed";
  const approved = item.status === "approved";
  const tone = item.risk === "financial" || item.risk === "irreversible" ? "#F87171" : item.risk === "external_communication" || item.risk === "external_write" ? "#F6C86A" : "#8EC5FF";
  return <View style={styles.approvalCard}>
    <View style={styles.cardHead}><View style={[styles.riskDot, { backgroundColor: tone }]} /><View style={styles.cardCopy}><Text style={styles.cardTitle}>{item.title}</Text><Text style={styles.cardMeta}>{item.action_type.replaceAll(".", " ")} · {item.risk.replaceAll("_", " ")}</Text></View><Text style={[styles.status, { color: tone }]}>{item.status.toUpperCase()}</Text></View>
    {item.description ? <Text style={styles.description}>{item.description}</Text> : null}
    <Text style={styles.expiry}>{item.status === "proposed" || item.status === "approved" ? `Expires ${formatWhen(item.expires_at)}` : `Updated ${formatWhen(item.updated_at)}`}</Text>
    {item.error ? <Text style={styles.error}>{item.error}</Text> : null}
    {ready ? <View style={styles.buttonRow}><Pressable disabled={working} onPress={onReject} style={({ pressed }) => [styles.rejectButton, (pressed || working) && styles.pressed]}><Text style={styles.rejectText}>REJECT</Text></Pressable><Pressable disabled={working} onPress={onApprove} style={({ pressed }) => [styles.approveButton, (pressed || working) && styles.pressed]}><Text style={styles.approveText}>{working ? "WORKING…" : "APPROVE"}</Text></Pressable></View> : null}
    {approved ? <><Text style={styles.secondStep}>Approved only. No external action has run yet.</Text><Pressable disabled={working} onPress={onExecute} style={({ pressed }) => [styles.executeButton, (pressed || working) && styles.pressed]}><Text style={styles.executeText}>{working ? "EXECUTING…" : "EXECUTE NOW"}</Text></Pressable></> : null}
  </View>;
}

const styles = StyleSheet.create({
  content: { padding: 20, paddingBottom: 34, gap: 14 },
  topBar: { flexDirection: "row", justifyContent: "space-between", marginBottom: 4 },
  iconButton: { width: 42, height: 42, borderRadius: 14, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: "#1D3931", backgroundColor: "#10201C" },
  eyebrow: { color: "#00E6A7", fontSize: 11, fontWeight: "900", letterSpacing: 3.3, marginTop: 8 },
  title: { color: "#F2FFF9", fontSize: 31, lineHeight: 38, fontWeight: "700", letterSpacing: -0.6, marginTop: 8 },
  subtitle: { color: "#95AAA3", fontSize: 14, lineHeight: 21, marginTop: 10 },
  policyCard: { flexDirection: "row", alignItems: "flex-start", gap: 10, borderRadius: 18, borderWidth: 1, borderColor: "#1F5948", backgroundColor: "#12382E", padding: 14, marginTop: 4 },
  policyCopy: { color: "#B8D7CD", fontSize: 12, lineHeight: 18, flex: 1 },
  sectionLabel: { color: "#95AAA3", fontSize: 10, fontWeight: "900", letterSpacing: 1.8, marginTop: 8 },
  historyLabel: { marginTop: 14 },
  approvalCard: { borderRadius: 20, borderWidth: 1, borderColor: "#1D3931", backgroundColor: "#10201C", padding: 15, gap: 10 },
  cardHead: { flexDirection: "row", alignItems: "flex-start", gap: 9 },
  riskDot: { width: 9, height: 9, borderRadius: 5, marginTop: 5 },
  cardCopy: { flex: 1 },
  cardTitle: { color: "#F2FFF9", fontSize: 15, fontWeight: "700" },
  cardMeta: { color: "#95AAA3", fontSize: 10, textTransform: "uppercase", letterSpacing: 0.7, marginTop: 4 },
  status: { fontSize: 9, fontWeight: "900", letterSpacing: 0.8 },
  description: { color: "#B8D7CD", fontSize: 12, lineHeight: 18 },
  expiry: { color: "#95AAA3", fontSize: 11 },
  error: { color: "#F87171", fontSize: 11, lineHeight: 16 },
  secondStep: { color: "#F6C86A", fontSize: 11, fontWeight: "700" },
  buttonRow: { flexDirection: "row", gap: 9, marginTop: 2 },
  rejectButton: { flex: 1, minHeight: 42, borderRadius: 12, borderWidth: 1, borderColor: "#71413F", alignItems: "center", justifyContent: "center" },
  rejectText: { color: "#F87171", fontSize: 10, fontWeight: "900", letterSpacing: 0.9 },
  approveButton: { flex: 1, minHeight: 42, borderRadius: 12, backgroundColor: "#00A878", alignItems: "center", justifyContent: "center" },
  approveText: { color: "#071B16", fontSize: 10, fontWeight: "900", letterSpacing: 0.9 },
  executeButton: { minHeight: 44, borderRadius: 12, backgroundColor: "#F87171", alignItems: "center", justifyContent: "center", marginTop: 1 },
  executeText: { color: "#250909", fontSize: 10, fontWeight: "900", letterSpacing: 1 },
  empty: { minHeight: 100, borderRadius: 18, borderWidth: 1, borderColor: "#1D3931", alignItems: "center", justifyContent: "center", gap: 8 },
  emptyText: { color: "#B8D7CD", fontSize: 13 },
  pressed: { opacity: 0.78, transform: [{ scale: 0.98 }] },
});
