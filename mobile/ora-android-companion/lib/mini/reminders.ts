import * as Notifications from "expo-notifications";
import { Platform } from "react-native";
import type { Snapshot } from "./api";
import { upcomingReminders, briefingHour } from "./reminder-plan";
import { readLocal, writeLocal } from "./api";
Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowBanner: true,
    shouldShowList: true,
    shouldPlaySound: true,
    shouldSetBadge: false,
  }),
});
export async function enableReminders() {
  if (Platform.OS !== "android")
    throw new Error("Local reminders are available in the Android app.");
  await Notifications.setNotificationChannelAsync("ora-reminders", {
    name: "ORA reminders",
    importance: Notifications.AndroidImportance.HIGH,
    sound: "default",
  });
  const result = await Notifications.requestPermissionsAsync();
  if (result.status !== "granted")
    throw new Error(
      "Allow notifications in Android Settings to receive reminders.",
    );
  await Notifications.setNotificationCategoryAsync("ora-task", [
    {
      identifier: "done",
      buttonTitle: "Done",
      options: { opensAppToForeground: true },
    },
    {
      identifier: "snooze",
      buttonTitle: "Snooze 10 min",
      options: { opensAppToForeground: true },
    },
    {
      identifier: "open",
      buttonTitle: "Open",
      options: { opensAppToForeground: true },
    },
  ]);
  await writeLocal("reminders", true);
}
export async function cancelReminders() {
  const all = await Notifications.getAllScheduledNotificationsAsync();
  await Promise.all(
    all
      .filter((n) => n.identifier.startsWith("ora2-"))
      .map((n) => Notifications.cancelScheduledNotificationAsync(n.identifier)),
  );
  await writeLocal("reminders", false);
}
export async function reconcileReminders(snapshot: Snapshot) {
  if (Platform.OS !== "android" || !(await readLocal("reminders", false)))
    return 0;
  if ((await Notifications.getPermissionsAsync()).status !== "granted")
    return 0;
  const plan = upcomingReminders(snapshot.tasks, Date.now());
  const daily = await readLocal("dailyNudge", false);
  const hour = briefingHour(
    snapshot.settings.briefing_hour,
    snapshot.settings.quiet_start,
    snapshot.settings.quiet_end,
  );
  const dailyId = "ora2-daily-" + hour;
  const ids = new Set(plan.map((t) => t.id));
  if (daily) ids.add(dailyId);
  const scheduled = await Notifications.getAllScheduledNotificationsAsync();
  const existing = new Set(scheduled.map((n) => n.identifier));
  for (const n of scheduled) {
    const d = n.content.data || {};
    const validSnooze =
      n.identifier.startsWith("ora2-snooze-") &&
      snapshot.tasks.some(
        (t) => t.id === d.task_id && t.version === d.version && !t.done,
      );
    if (
      n.identifier.startsWith("ora2-") &&
      !validSnooze &&
      !ids.has(n.identifier)
    )
      await Notifications.cancelScheduledNotificationAsync(n.identifier);
  }
  for (const item of plan)
    if (!existing.has(item.id))
      await Notifications.scheduleNotificationAsync({
        identifier: item.id,
        content: {
          title: "ORA · A little nudge",
          body: (await readLocal("privateNotifications", true))
            ? "Open ORA to see your reminder."
            : item.title,
          sound: "default",
          data: { task_id: item.taskId, version: item.version },
          categoryIdentifier: "ora-task",
        },
        trigger: {
          type: Notifications.SchedulableTriggerInputTypes.DATE,
          date: new Date(item.date),
          channelId: "ora-reminders",
        },
      });
  if (daily && !existing.has(dailyId))
    await Notifications.scheduleNotificationAsync({
      identifier: dailyId,
      content: {
        title: "ORA · Make a little room for today",
        body: "Choose one thing that matters. Open ORA and let’s make a plan.",
        sound: "default",
      },
      trigger: {
        type: Notifications.SchedulableTriggerInputTypes.DAILY,
        hour,
        minute: 0,
        channelId: "ora-reminders",
      },
    });
  return plan.length;
}
