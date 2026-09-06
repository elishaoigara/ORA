import React, { useState } from "react";
import { Text, TextInput, Pressable, Switch, ScrollView } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { router, useLocalSearchParams } from "expo-router";
import { useMini } from "@/lib/mini/provider";
import { colors as c } from "@/lib/mini/theme";
export default function EditMemory() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const m = useMini();
  const item = m.data?.memories.find((x) => x.id === id);
  const [text, setText] = useState(item?.text || "");
  const [category, setCategory] = useState(item?.category || "General");
  const [pinned, setPinned] = useState(!!item?.pinned);
  const [error, setError] = useState("");
  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: c.background }}>
      <ScrollView contentContainerStyle={{ padding: 24, gap: 20 }}>
        <Pressable onPress={() => router.back()}>
          <Text style={{ color: c.cyan }}>‹ Back</Text>
        </Pressable>
        <Text style={{ color: c.text, fontSize: 28 }}>Edit memory</Text>
        <TextInput
          multiline
          value={text}
          onChangeText={setText}
          maxLength={1000}
          style={{
            color: c.text,
            minHeight: 150,
            borderWidth: 1,
            borderColor: c.border,
            padding: 14,
          }}
        />
        <TextInput
          value={category}
          onChangeText={setCategory}
          maxLength={40}
          accessibilityLabel="Memory category"
          style={{
            color: c.text,
            padding: 14,
            borderWidth: 1,
            borderColor: c.border,
          }}
        />
        <Text style={{ color: c.text }}>Pin to top</Text>
        <Switch value={pinned} onValueChange={setPinned} />
        <Pressable
          onPress={async () => {
            try {
              await m.mutate("memory.update", { id, text, category, pinned });
              router.back();
            } catch (e) {
              setError(String(e));
            }
          }}
        >
          <Text style={{ color: c.cyan, fontSize: 20 }}>Save memory</Text>
        </Pressable>
        <Text style={{ color: "#ffaaa5" }}>{error}</Text>
      </ScrollView>
    </SafeAreaView>
  );
}
