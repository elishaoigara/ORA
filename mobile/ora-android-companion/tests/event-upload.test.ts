import { describe, expect, it, vi } from "vitest";
import { flushEvents } from "../lib/mini/event-upload";
import type { NativeNotificationEvent } from "../modules/ora-notification-listener/src/OraNotificationListenerModule";

const clock = Date.parse("2026-10-12T10:00:00Z");
const event = (id: string, occurredAt = new Date(clock).toISOString()): NativeNotificationEvent => ({
  id, occurredAt, appLabel: "Test", packageName: "test.app", title: "Update", body: "", contentMode: "metadata",
});

describe("notification queue upload", () => {
  it("acknowledges successful uploads before a later failure", async () => {
    const upload = vi.fn().mockResolvedValueOnce({}).mockRejectedValueOnce(new Error("offline"));
    const ack = vi.fn();
    await expect(flushEvents([event("one"), event("two"), event("three")], upload, ack, clock)).rejects.toThrow("offline");
    expect(ack.mock.calls).toEqual([[["one"]]]);
    expect(upload).toHaveBeenCalledTimes(2);
  });
  it("discards expired or invalid clocks without uploading", async () => {
    const upload = vi.fn();
    const ack = vi.fn();
    await flushEvents([event("old", "2026-10-10T10:00:00Z"), event("bad", ""), event("future", "2026-10-13T10:00:00Z")], upload, ack, clock);
    expect(upload).not.toHaveBeenCalled();
    expect(ack.mock.calls).toEqual([[["old"]], [["bad"]], [["future"]]]);
  });
  it("only acknowledges events in this snapshot", async () => {
    const ack = vi.fn();
    const upload = vi.fn().mockResolvedValue({});
    await flushEvents([event("one"), event("two")], upload, ack, clock);
    expect(ack.mock.calls).toEqual([[["one"]], [["two"]]]);
  });
});
