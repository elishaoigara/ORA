import { useCallback, useEffect, useState } from "react";
import { Alert, FlatList, StyleSheet, Text, View } from "react-native";
import MaterialIcons from "@expo/vector-icons/MaterialIcons";

import { ScreenContainer } from "@/components/screen-container";
import { useDevice } from "@/lib/device-provider";
import { getCommandActivity, type CommandActivity } from "@/lib/ora-device";

function formatDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

function activityIcon(category: string) {
  if (category === "capture") return "bookmark-added" as const;
  if (category === "privacy") return "shield" as const;
  if (category === "location") return "near-me" as const;
  if (category === "approval") return "task-alt" as const;
  return "bolt" as const;
}

export default function ActivityScreen() {
  const { session } = useDevice();
  const [activity, setActivity] = useState<CommandActivity[]>([]);
  const [refreshing, setRefreshing] = useState(false);

  const refresh = useCallback(async () => {
    if (!session) {
      setActivity([]);
      return;
    }
    setRefreshing(true);
    try {
      setActivity(await getCommandActivity(session));
    } catch (err) {
      Alert.alert("Activity unavailable", err instanceof Error ? err.message : "ORA could not load this device history.");
    } finally {
      setRefreshing(false);
    }
  }, [session]);

  useEffect(() => {
    const timer = setTimeout(() => { void refresh(); }, 0);
    return () => clearTimeout(timer);
  }, [refresh]);

  return (
    <ScreenContainer className="bg-background" edges={["top", "left", "right"]}>
      <FlatList
        data={activity}
        keyExtractor={(item, index) => `${item.occurred_at}-${item.category}-${index}`}
        contentContainerStyle={styles.content}
        refreshing={refreshing}
        onRefresh={() => void refresh()}
        ListHeaderComponent={<View style={styles.header}><Text style={styles.eyebrow}>ORA // ACTIVITY</Text><Text style={styles.title}>A clear record of what happened.</Text><Text style={styles.subtitle}>Every Companion event is visible here with its retention window.</Text></View>}
        renderItem={({ item }) => (
          <View style={styles.eventCard}>
            <View style={styles.iconWrap}><MaterialIcons name={activityIcon(item.category)} color="#4CA7FF" size={19} /></View>
            <View style={styles.copy}><Text style={styles.eventTitle}>{item.title}</Text>{item.detail ? <Text style={styles.detail}>{item.detail}</Text> : null}<Text style={styles.meta}>{formatDate(item.occurred_at)} · kept {item.retention_hours}h</Text></View>
          </View>
        )}
        ListEmptyComponent={!refreshing ? <View style={styles.empty}><MaterialIcons name="timeline" color="#38D996" size={30} /><Text style={styles.emptyTitle}>Your timeline is quiet.</Text><Text style={styles.emptyBody}>Captures, privacy changes, routines, and completed actions will appear here.</Text></View> : null}
      />
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  content: { padding: 20, paddingBottom: 32, gap: 10, flexGrow: 1 },
  header: { marginBottom: 10 },
  eyebrow: { color: "#00E6A7", fontSize: 11, fontWeight: "800", letterSpacing: 3.1 },
  title: { color: "#F2FFF9", fontSize: 28, fontWeight: "700", lineHeight: 34, letterSpacing: -0.5, marginTop: 8 },
  subtitle: { color: "#95AAA3", fontSize: 14, lineHeight: 21, marginTop: 8 },
  eventCard: { flexDirection: "row", gap: 12, borderRadius: 18, padding: 14, borderColor: "#1D3931", borderWidth: 1, backgroundColor: "#10201C" },
  iconWrap: { width: 34, height: 34, borderRadius: 12, alignItems: "center", justifyContent: "center", backgroundColor: "#102D2B" },
  copy: { flex: 1, gap: 4 },
  eventTitle: { color: "#F2FFF9", fontSize: 14, fontWeight: "700" },
  detail: { color: "#B8D7CD", fontSize: 12, lineHeight: 17 },
  meta: { color: "#6F8980", fontSize: 10, marginTop: 2 },
  empty: { flex: 1, minHeight: 280, alignItems: "center", justifyContent: "center", paddingHorizontal: 40, gap: 9 },
  emptyTitle: { color: "#F2FFF9", fontSize: 16, fontWeight: "700", marginTop: 4 },
  emptyBody: { color: "#95AAA3", fontSize: 13, textAlign: "center", lineHeight: 20 },
});
