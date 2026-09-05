import { describe, it, expect } from "vitest";
import { upcomingReminders, briefingHour } from "../lib/mini/reminder-plan";
import type { Task } from "../lib/mini/api";
const task = (id: string, more: Partial<Task> = {}): Task => ({
  id,
  title: id,
  done: false,
  version: 1,
  priority: 2,
  due_at: "2030-01-01T10:00:00Z",
  ...more,
});
describe("phone reminder planning", () => {
  it("removes completed and past tasks, keeps stable ids across syncs", () => {
    const list = [
      task("future"),
      task("done", { done: true }),
      task("past", { due_at: "2000-01-01T10:00:00Z" }),
    ];
    expect(upcomingReminders(list, Date.parse("2029-01-01"))).toEqual([
      { id: "ora2-future-1", title: "future", date: "2030-01-01T10:00:00Z" },
    ]);
  });
  it("changes identity on edits and bounds scheduled work", () => {
    expect(upcomingReminders([task("edited", { version: 2 })], 0)[0].id).toBe(
      "ora2-edited-2",
    );
    expect(
      upcomingReminders(
        Array.from({ length: 70 }, (_, i) => task(String(i))),
        0,
      ),
    ).toHaveLength(50);
  });
  it("moves a daily nudge outside quiet hours including overnight", () => {
    expect(briefingHour(7, 22, 8)).toBe(8);
    expect(briefingHour(7, 22, 6)).toBe(7);
    expect(briefingHour(14, 13, 16)).toBe(16);
    expect(briefingHour(7, 7, 7)).toBe(7);
  });
});
