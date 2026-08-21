import MaterialIcons from "@expo/vector-icons/MaterialIcons";
import { Tabs } from "expo-router";
import { Platform } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { useColors } from "@/hooks/use-colors";

const iconMap = {
  index: "hub" as const,
  awareness: "visibility" as const,
  privacy: "shield" as const,
};

export default function TabLayout() {
  const colors = useColors();
  const insets = useSafeAreaInsets();
  const bottomPadding = Platform.OS === "web" ? 12 : Math.max(insets.bottom, 8);

  return (
    <Tabs
      screenOptions={({ route }) => ({
        headerShown: false,
        tabBarActiveTintColor: colors.primary,
        tabBarInactiveTintColor: colors.muted,
        tabBarStyle: {
          height: 64 + bottomPadding,
          paddingTop: 8,
          paddingBottom: bottomPadding,
          backgroundColor: colors.background,
          borderTopColor: colors.border,
          borderTopWidth: 1,
        },
        tabBarLabelStyle: { fontSize: 11, fontWeight: "700" },
        tabBarIcon: ({ color, size }) => (
          <MaterialIcons name={iconMap[route.name as keyof typeof iconMap]} color={color} size={size} />
        ),
      })}
    >
      <Tabs.Screen name="index" options={{ title: "Companion" }} />
      <Tabs.Screen name="awareness" options={{ title: "Awareness" }} />
      <Tabs.Screen name="privacy" options={{ title: "Privacy" }} />
    </Tabs>
  );
}
