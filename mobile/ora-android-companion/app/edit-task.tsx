import React, { useState } from "react";
import { ScrollView, Text, TextInput, Pressable, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useLocalSearchParams, router } from "expo-router";
import { useMini } from "@/lib/mini/provider";
import { colors as c } from "@/lib/mini/theme";
import Native from "@/modules/ora-notification-listener/src/OraNotificationListenerModule";
export default function EditTask() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const m = useMini();
  const t = m.data?.tasks.find((t) => t.id === id);
  const [title, setTitle] = useState(t?.title || "");
  const [date, setDate] = useState(t?.due_at || "");
  const [priority, setPriority] = useState(t?.priority || 2);
  const [repeat, setRepeat] = useState(t?.repeat || "none");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const button = (text: string, fn: () => void) => (
    <Pressable
      disabled={busy}
      style={{ padding: 14, backgroundColor: c.surface, borderRadius: 10 }}
      onPress={fn}
    >
      <Text style={{ color: c.cyan }}>{text}</Text>
    </Pressable>
  );
  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: c.background }}>
      <ScrollView contentContainerStyle={{ padding: 24, gap: 18 }}>
        {button("‹ Back", () => router.back())}
        <Text style={{ color: c.text, fontSize: 28 }}>
          {t ? "Edit task" : "New task"}
        </Text>
        <TextInput
          style={{
            color: c.text,
            borderColor: c.border,
            borderWidth: 1,
            padding: 14,
          }}
          value={title}
          onChangeText={setTitle}
          placeholder="Task title"
          placeholderTextColor={c.muted}
        />
        {button(
          date ? new Date(date).toLocaleString() : "Choose date and time",
          async () => {
            try {
              if (!Native?.pickDateTime)
                throw Error(
                  "Install the new APK to use the native date picker.",
                );
              const value = await Native.pickDateTime(
                date ? Date.parse(date) : Date.now() + 3600000,
              );
              if (value) setDate(new Date(value).toISOString());
            } catch (e) {
              setError(String(e));
            }
          },
        )}
        {button("Remove reminder", () => setDate(""))}
        <Text style={{ color: c.text }}>Priority</Text>
        {[1, 2, 3].map((p) => (
          <View key={p}>
            {button(
              `${priority === p ? "● " : ""}${["High", "Normal", "Low"][p - 1]}`,
              () => setPriority(p),
            )}
          </View>
        ))}
        <Text style={{ color: c.text }}>
          Repeat · fixed 24-hour / 7-day intervals
        </Text>
        {["none", "daily", "weekly"].map((r) => (
          <View key={r}>
            {button(`${repeat === r ? "● " : ""}${r}`, () => setRepeat(r))}
          </View>
        ))}
        <Text style={{ color: c.muted }}>
          Recurring tasks move to the next occurrence when completed.
        </Text>
        {button("Save task", async () => {
          setBusy(true);
          try {
            if (id && !t) throw Error("Task no longer exists.");
            if (repeat !== "none" && !date)
              throw Error("Choose a date for repeating reminders.");
            await m.mutate(t ? "task.update" : "task.create", {
              ...(t ? { id: t.id, version: t.version } : {}),
              title,
              due_at: date || null,
              priority,
              repeat,
            });
            router.back();
          } catch (e) {
            setError(String(e));
          } finally {
            setBusy(false);
          }
        })}
        <Text style={{ color: "#ffaaa5" }}>{error}</Text>
      </ScrollView>
    </SafeAreaView>
  );
}
