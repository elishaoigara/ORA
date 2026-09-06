import * as SecureStore from "expo-secure-store";
import * as N from "expo-notifications";
import Constants from "expo-constants";
import { router } from "expo-router";
import { makeId, readLocal, request, writeLocal } from "./api";
const processing = new Set<string>();
export type LocalAlert = {
  id: string;
  title: string;
  body: string;
  created: number;
  read: boolean;
};
export async function channels() {
  for (const [id, name] of [
    ["ora-weather", "ORA weather"],
    ["ora-alerts", "ORA updates"],
  ])
    await N.setNotificationChannelAsync(id, {
      name,
      importance: N.AndroidImportance.DEFAULT,
      sound: "default",
    });
}
export async function registerPush() {
  await writeLocal("pushEnabled", true);
  await channels();
  if ((await N.getPermissionsAsync()).status !== "granted")
    throw new Error("Enable notifications first.");
  const projectId = Constants.expoConfig?.extra?.eas?.projectId;
  if (!projectId) throw new Error("EAS project is not linked.");
  const token = (await N.getExpoPushTokenAsync({ projectId })).data;
  await request("/operations", {
    request_id: makeId(),
    kind: "companion.push",
    payload: { token, private: await readLocal("privateNotifications", true) },
  });
  await writeLocal("pushRegistered", new Date().toISOString());
}
export async function localTest() {
  await channels();
  await N.scheduleNotificationAsync({
    content: {
      title: "ORA · Notification test",
      body: "Your local notifications work.",
      data: { test: true },
    },
    trigger: {
      type: N.SchedulableTriggerInputTypes.TIME_INTERVAL,
      seconds: 5,
      channelId: "ora-alerts",
    },
  });
}
export async function notificationHealth() {
  return {
    permission: (await N.getPermissionsAsync()).status,
    scheduled: (await N.getAllScheduledNotificationsAsync()).length,
    channels: (await N.getNotificationChannelsAsync())
      .map((c) => c.name + ": " + (c.importance === 0 ? "blocked" : "enabled"))
      .join("\n"),
    lastSync: await readLocal("lastSync", "Never"),
    push: await readLocal("pushRegistered", "Not registered"),
    error: await readLocal("notificationError", ""),
  };
}
let historyChain: Promise<unknown> = Promise.resolve();
function record(n: N.Notification) {
  const next = historyChain.then(() => recordOne(n));
  historyChain = next.catch(() => {});
  return next;
}
async function recordOne(n: N.Notification) {
  const list = await readLocal<LocalAlert[]>("alertHistory", []);
  if (list.some((a) => a.id === n.request.identifier)) return;
  await writeLocal(
    "alertHistory",
    [
      {
        id: n.request.identifier,
        title: n.request.content.title || "ORA",
        body: n.request.content.body || "",
        created: n.date,
        read: false,
      },
      ...list,
    ]
      .filter((a) => a.created > Date.now() - 30 * 86400000)
      .slice(0, 100),
  );
}
export function notificationListeners(
  mutate: (kind: string, p: Record<string, unknown>) => Promise<void>,
  sync: () => Promise<void>,
) {
  let alive = true;
  const handle = async (r: N.NotificationResponse) => {
    if (!alive) return;
    const key = r.notification.request.identifier + ":" + r.actionIdentifier;
    if (processing.has(key)) return;
    processing.add(key);
    try {
      if ((await readLocal<string[]>("handledNotifications", [])).includes(key))
        return;
      if (await readLocal("appLock", false)) {
        if (
          (await SecureStore.getItemAsync("ora_biometric_lock", {
            requireAuthentication: true,
            authenticationPrompt: "Unlock ORA notification",
          })) !== "unlocked"
        )
          return;
      }
      await record(r.notification);
      const d = r.notification.request.content.data || {};
      if (r.actionIdentifier === "done" && typeof d.task_id === "string")
        await mutate("task.complete", { id: d.task_id, version: d.version });
      if (r.actionIdentifier === "snooze")
        await N.scheduleNotificationAsync({
          identifier: "ora2-snooze-" + makeId(),
          content: {
            title: r.notification.request.content.title,
            body: r.notification.request.content.body,
            data: { ...d, snooze_until: Date.now() + 600000 },
            categoryIdentifier: "ora-task",
            sound: "default",
          },
          trigger: {
            type: N.SchedulableTriggerInputTypes.TIME_INTERVAL,
            seconds: 600,
            channelId: "ora-reminders",
          },
        });
      if (d.alert_id) {
        await mutate("companion.alert.read", { id: d.alert_id });
        router.push("/notifications");
      } else if (d.task_id) router.push("/(tabs)/activity");
      else router.push("/notifications");
      await writeLocal(
        "handledNotifications",
        [...(await readLocal<string[]>("handledNotifications", [])), key].slice(
          -100,
        ),
      );
      await N.clearLastNotificationResponseAsync();
    } catch (e) {
      await writeLocal("notificationError", String(e));
    } finally {
      processing.delete(key);
    }
  };
  const received = N.addNotificationReceivedListener((n) => {
    void record(n).catch(() => {});
  });
  const response = N.addNotificationResponseReceivedListener((r) => {
    void handle(r);
  });
  const token = N.addPushTokenListener(() => {
    void registerPush().catch((e) =>
      writeLocal("notificationError", String(e)),
    );
  });
  void N.getLastNotificationResponseAsync().then((r) => r && handle(r));
  void N.getPresentedNotificationsAsync()
    .then((ns) => Promise.all(ns.map(record)))
    .catch(() => {});
  return () => {
    alive = false;
    received.remove();
    response.remove();
    token.remove();
  };
}
