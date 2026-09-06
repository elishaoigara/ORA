import Native from "@/modules/ora-notification-listener/src/OraNotificationListenerModule";
import React, { useCallback, useState } from "react";
import {
  ScrollView,
  Text,
  TextInput,
  View,
  Pressable,
  StyleSheet,
  Linking,
  Switch,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { router, useFocusEffect } from "expo-router";
import * as Location from "expo-location";
import * as N from "expo-notifications";
import { useMini } from "@/lib/mini/provider";
import { readLocal, writeLocal } from "@/lib/mini/api";
import { enableReminders, reconcileReminders } from "@/lib/mini/reminders";
import {
  channels,
  notificationHealth,
  registerPush,
  localTest,
  LocalAlert,
} from "@/lib/mini/notification-center";
import { request } from "@/lib/mini/api";
import { colors as c } from "@/lib/mini/theme";
export default function NotificationsScreen() {
  const m = useMini();
  const [health, setHealth] = useState<any>({});
  const [history, setHistory] = useState<LocalAlert[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [city, setCity] = useState("");
  const [places, setPlaces] = useState<any[]>([]);
  const [privateMode, setPrivate] = useState(true);
  const [rain, setRain] = useState("60");
  const [heat, setHeat] = useState("32");
  const [wind, setWind] = useState("40");
  const device = m.data?.devices.find((d) => d.id === m.session?.device_id);
  const refresh = useCallback(async () => {
    setHealth(await notificationHealth());
    setHistory(await readLocal<LocalAlert[]>("alertHistory", []));
    setPrivate(await readLocal("privateNotifications", true));
  }, []);
  useFocusEffect(
    useCallback(() => {
      void refresh();
    }, [refresh]),
  );
  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError("");
    try {
      await fn();
      await refresh();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };
  const button = (label: string, fn: () => Promise<unknown>) => (
    <Pressable disabled={busy} style={s.button} onPress={() => run(fn)}>
      <Text style={{ color: c.background }}>{label}</Text>
    </Pressable>
  );
  const saveWeather = async (
    latitude: number,
    longitude: number,
    label: string,
    source: string,
  ) => {
    await m.mutate("companion.weather", {
      enabled: true,
      latitude,
      longitude,
      label,
      source,
      rain: Number(rain),
      heat: Number(heat),
      wind: Number(wind),
      briefings: true,
    });
    await request("/weather/refresh", {});
    await m.sync();
  };
  return (
    <SafeAreaView style={s.safe}>
      <ScrollView contentContainerStyle={{ padding: 22, gap: 14 }}>
        <Pressable onPress={() => router.back()}>
          <Text style={s.text}>‹ Back</Text>
        </Pressable>
        <Text style={s.title}>Your notification center</Text>
        <Text style={s.text}>
          Local reminders work after scheduling, even while Render sleeps.
          Remote weather updates need the scheduler and push credentials.
        </Text>
        {!!error && <Text style={{ color: "#ffaaa5" }}>{error}</Text>}
        <View style={s.card}>
          <Text style={s.title}>Delivery health</Text>
          <Text style={s.text}>
            Exact alarms:{" "}
            {Native?.canScheduleExactAlarms?.()
              ? "Allowed"
              : "Check Alarms & reminders in Android settings"}
            {"\n"}Permission: {health.permission}
            {"\n"}Scheduled: {health.scheduled}
            {"\n"}Last sync: {health.lastSync}
            {"\n"}Push registered: {device?.push_registered ? "Yes" : "No"}
            {"\n"}Scheduler last ran: {m.data?.scheduler_at || "Not yet"}
            {"\n"}
            {health.channels}
            {"\n"}
            {health.error}
          </Text>
          {button("Enable notifications", async () => {
            await enableReminders();
            await channels();
            if (m.data) await reconcileReminders(m.data);
          })}
          {button("Allow precise reminder timing", async () => {
            if (!Native?.openExactAlarmSettings)
              throw Error("Install the new APK first.");
            Native.openExactAlarmSettings();
          })}
          {button("Test local notification · 5 seconds", localTest)}
          {button("Register / repair remote push", async () => {
            await registerPush();
            await m.sync();
          })}
          {button("Disable remote push", async () => {
            await writeLocal("pushEnabled", false);
            await m.mutate("companion.push", { token: "" });
            await writeLocal("pushRegistered", "Disabled");
          })}
          {button("Queue remote push test", async () => {
            await m.mutate("companion.push.test", {});
            setError(
              "Test queued. The next scheduler run sends it outside quiet hours.",
            );
          })}
          {button("Android notification settings", () =>
            Linking.openSettings(),
          )}
          <Text style={s.text}>Hide reminder and push contents</Text>
          <Switch
            value={privateMode}
            onValueChange={(v) =>
              run(async () => {
                await writeLocal("privateNotifications", v);
                setPrivate(v);
                const scheduled = await N.getAllScheduledNotificationsAsync();
                for (const n of scheduled)
                  if (n.identifier.startsWith("ora2-")) {
                    await N.cancelScheduledNotificationAsync(n.identifier);
                    const d = n.content.data || {};
                    if (
                      n.identifier.startsWith("ora2-snooze-") &&
                      Number(d.snooze_until) > Date.now()
                    ) {
                      await N.scheduleNotificationAsync({
                        identifier: n.identifier,
                        content: {
                          title: "ORA · Reminder",
                          body: v
                            ? "Open ORA to see your reminder."
                            : m.data?.tasks.find((t) => t.id === d.task_id)
                                ?.title || "Open your plan",
                          data: d,
                          categoryIdentifier: "ora-task",
                          sound: "default",
                        },
                        trigger: {
                          type: N.SchedulableTriggerInputTypes.DATE,
                          date: new Date(Number(d.snooze_until)),
                          channelId: "ora-reminders",
                        },
                      });
                    }
                  }
                if (m.data) await reconcileReminders(m.data);
                if (device?.push_registered) await registerPush();
              })
            }
          />
          <Text style={s.text}>
            Android can delay delivery in battery saver or after force-stop. A
            provider receipt confirms handoff, not that you saw the
            notification.
          </Text>
        </View>
        <View style={s.card}>
          <Text style={s.title}>Weather awareness</Text>
          <Text style={s.text}>
            {device?.weather?.enabled
              ? "Enabled · " + device.weather.label
              : "Off until you choose a place"}
          </Text>
          <Text style={s.text}>
            Forecast guidance from Open-Meteo, not official emergency warnings.
            Up to two updates daily; quiet hours apply. Phone location expires
            after 24 hours. A saved city remains active until disabled.
          </Text>
          {[
            [rain, setRain, "Rain chance %"],
            [heat, setHeat, "Heat °C"],
            [wind, setWind, "Wind km/h"],
          ].map(([v, set, label]: any) => (
            <View key={label}>
              <Text style={s.text}>{label}</Text>
              <TextInput
                style={s.input}
                value={v}
                onChangeText={set}
                keyboardType="numeric"
                accessibilityLabel={label}
                placeholder={label}
              />
            </View>
          ))}
          <TextInput
            style={s.input}
            value={city}
            onChangeText={setCity}
            placeholder="Search a city"
            placeholderTextColor={c.muted}
          />
          {button("Find city", async () => {
            const r = await fetch(
              "https://geocoding-api.open-meteo.com/v1/search?count=5&name=" +
                encodeURIComponent(city),
            );
            if (!r.ok) throw Error("City search unavailable");
            setPlaces((await r.json()).results || []);
          })}
          {places.map((p) => (
            <View key={p.id}>
              {button(`${p.name}, ${p.country}`, () =>
                saveWeather(p.latitude, p.longitude, p.name, "city"),
              )}
            </View>
          ))}
          {button("Use current approximate location", async () => {
            if (
              (await Location.requestForegroundPermissionsAsync()).status !==
              "granted"
            )
              throw Error("Location permission denied");
            await m.mutate("device.permissions", {
              permission: "location",
              enabled: true,
            });
            const p = await Location.getCurrentPositionAsync({
              accuracy: Location.Accuracy.Balanced,
            });
            await saveWeather(
              Number(p.coords.latitude.toFixed(2)),
              Number(p.coords.longitude.toFixed(2)),
              "Current area",
              "location",
            );
          })}
          {button("Refresh forecast", async () => {
            await request("/weather/refresh", {});
            await m.sync();
          })}
          {button("Disable weather and delete saved location", () =>
            m.mutate("companion.weather", { enabled: false }),
          )}
          {!!device?.forecast && (
            <Text style={s.text}>
              {device.forecast.temperature_2m_min}–
              {device.forecast.temperature_2m_max}°C · rain{" "}
              {device.forecast.precipitation_probability_max}%{"\n"}Updated{" "}
              {new Date(device.forecast.fetched_at * 1000).toLocaleString()}
            </Text>
          )}
        </View>
        <Text style={s.title}>
          Alert inbox · {(m.data?.alerts || []).filter((a) => !a.read).length}{" "}
          unread
        </Text>
        {button("Mark all read", () =>
          m.mutate("companion.alert.read", { all: true }),
        )}
        {[...(m.data?.alerts || [])].reverse().map((a) => (
          <Pressable
            key={a.id}
            style={s.card}
            onPress={() =>
              run(() => m.mutate("companion.alert.read", { id: a.id }))
            }
          >
            <Text style={s.title}>
              {a.read ? "" : "● "}
              {a.title}
            </Text>
            <Text style={s.text}>
              {a.body}
              {"\n"}
              {new Date(a.created * 1000).toLocaleString()} ·{" "}
              {a.expires * 1000 < Date.now() ? "expired" : a.delivery}
              {a.error ? " · " + a.error : ""}
            </Text>
          </Pressable>
        ))}
        <Text style={s.title}>Seen on this phone</Text>
        {history.map((a) => (
          <View key={a.id} style={s.card}>
            <Text style={s.text}>
              {a.title}
              {"\n"}
              {a.body}
            </Text>
          </View>
        ))}
        {button("Clear alert history", async () => {
          await m.mutate("companion.alert.clear", {});
          await writeLocal("alertHistory", []);
        })}
        <Text style={s.text}>
          Server alert history is retained for up to 30 days / 500 entries.
          Local history is capped at 100 entries.
        </Text>
      </ScrollView>
    </SafeAreaView>
  );
}
const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: c.background },
  text: { color: c.text, lineHeight: 22 },
  title: { color: c.cyan, fontSize: 19, fontWeight: "600" },
  card: { padding: 16, gap: 12, backgroundColor: c.surface, borderRadius: 16 },
  button: {
    backgroundColor: c.cyan,
    padding: 13,
    borderRadius: 10,
    marginVertical: 4,
  },
  input: {
    color: c.text,
    borderColor: c.border,
    borderWidth: 1,
    padding: 12,
    borderRadius: 8,
  },
});
