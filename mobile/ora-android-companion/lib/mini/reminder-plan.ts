import type { Task } from "./api";
export function upcomingReminders(tasks: Task[], now: number) {
  return tasks
    .filter((t) => !t.done && t.due_at && Date.parse(t.due_at) > now)
    .sort((a, b) => Date.parse(a.due_at!) - Date.parse(b.due_at!))
    .slice(0, 50)
    .map((t) => ({
      id: "ora2-" + t.id + "-" + t.version,
      title: t.title,
      date: t.due_at!,
    }));
}
export function briefingHour(hour: number, start: number, end: number) {
  const quiet =
    start === end
      ? false
      : start < end
        ? hour >= start && hour < end
        : hour >= start || hour < end;
  return quiet ? end : hour;
}
