import { type ReactNode } from "react";
import { StyleSheet, Text, View } from "react-native";

type StatusTone = "success" | "warning" | "neutral" | "error";

const tones: Record<StatusTone, { dot: string; label: string }> = {
  success: { dot: "#38D996", label: "CONNECTED" },
  warning: { dot: "#F5B94C", label: "ACTION NEEDED" },
  neutral: { dot: "#95AAA3", label: "NOT CONFIGURED" },
  error: { dot: "#F87171", label: "CONNECTION ISSUE" },
};

export function OraStatusCard({
  title,
  detail,
  tone = "neutral",
  children,
}: {
  title: string;
  detail: string;
  tone?: StatusTone;
  children?: ReactNode;
}) {
  const status = tones[tone];
  return (
    <View className="rounded-3xl border border-border bg-surface p-5" style={styles.card}>
      <View className="mb-4 flex-row items-center justify-between">
        <View className="flex-row items-center gap-2">
          <View style={[styles.dot, { backgroundColor: status.dot }]} />
          <Text className="text-[10px] font-bold tracking-[2px] text-muted">{status.label}</Text>
        </View>
      </View>
      <Text className="text-xl font-bold text-foreground">{title}</Text>
      <Text className="mt-2 text-sm leading-5 text-muted">{detail}</Text>
      {children ? <View className="mt-5">{children}</View> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: { shadowColor: "#000", shadowOpacity: 0.18, shadowRadius: 16, shadowOffset: { width: 0, height: 7 } },
  dot: { width: 8, height: 8, borderRadius: 4 },
});
