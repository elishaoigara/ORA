import { describe, it, expect } from "vitest";
import { applyLocal } from "../lib/mini/offline";
import type { Snapshot } from "../lib/mini/api";
const state = { tasks: [], memories: [] } as unknown as Snapshot;
describe("offline task operations", () => {
  it("creates immediately and deduplicates server acknowledgement", () => {
    const op = {
      request_id: "local-1",
      kind: "task.create",
      payload: {
        title: "Remember",
        due_at: "2027-01-01T10:00:00Z",
        priority: 1,
      },
    };
    const next = applyLocal(state, op);
    expect(next.tasks[0].id).toBe("local-1");
    expect(state.tasks).toHaveLength(0);
    expect(applyLocal(next, op).tasks).toHaveLength(1);
  });
  it("does not replay completion against a changed version", () => {
    const s = {
      ...state,
      tasks: [
        {
          id: "one",
          title: "One",
          done: false,
          version: 2,
          priority: 2,
          due_at: null,
        },
      ],
    };
    expect(
      applyLocal(s, {
        request_id: "done",
        kind: "task.complete",
        payload: { id: "one", version: 1 },
      }).tasks[0].done,
    ).toBe(false);
  });
  it("advances recurring tasks without marking them done", () => {
    const s = {
      ...state,
      tasks: [
        {
          id: "one",
          title: "One",
          done: false,
          repeat: "daily",
          version: 1,
          priority: 2,
          due_at: "2020-01-01T00:00:00Z",
        },
      ],
    };
    const t = applyLocal(s, {
      request_id: "done",
      kind: "task.complete",
      payload: { id: "one", version: 1 },
    }).tasks[0];
    expect(t.done).toBe(false);
    expect(Date.parse(t.due_at!)).toBeGreaterThan(Date.now());
  });
});
