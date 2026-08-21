import { describe, expect, it } from "vitest";

import {
  canSubmitAwarenessEvent,
  capabilityEnabled,
  continuousRetentionHours,
  DEFAULT_CONTINUOUS_RETENTION_HOURS,
} from "../lib/awareness-policy";
import type { AwarenessConsent, AwarenessState } from "../lib/ora-device";

const disabled: AwarenessConsent[] = [
  { capability: "push_alerts", enabled: false, retention_hours: 0, policy_version: "ora-awareness-v1" },
  { capability: "zone_routines", enabled: false, retention_hours: 0, policy_version: "ora-awareness-v1" },
  { capability: "continuous_location", enabled: false, retention_hours: 24, policy_version: "ora-awareness-v1" },
];

describe("Companion awareness policy", () => {
  it("keeps every sensitive awareness source disabled by default", () => {
    const state: AwarenessState = { consents: disabled, zones: [], push: { registered: false } };

    expect(capabilityEnabled(state, "push_alerts")).toBe(false);
    expect(capabilityEnabled(state, "zone_routines")).toBe(false);
    expect(capabilityEnabled(state, "continuous_location")).toBe(false);
    expect(canSubmitAwarenessEvent(disabled, "zone_enter")).toBe(false);
    expect(canSubmitAwarenessEvent(disabled, "location_sample")).toBe(false);
  });

  it("requires distinct consent for zone events and precise location samples", () => {
    const zoneOnly = disabled.map((item) => item.capability === "zone_routines" ? { ...item, enabled: true } : item);
    const continuousOnly = disabled.map((item) => item.capability === "continuous_location" ? { ...item, enabled: true } : item);

    expect(canSubmitAwarenessEvent(zoneOnly, "zone_exit")).toBe(true);
    expect(canSubmitAwarenessEvent(zoneOnly, "location_sample")).toBe(false);
    expect(canSubmitAwarenessEvent(continuousOnly, "location_sample")).toBe(true);
    expect(canSubmitAwarenessEvent(continuousOnly, "zone_enter")).toBe(false);
  });

  it("falls back to the finite 24-hour retention default when server state is missing or invalid", () => {
    expect(continuousRetentionHours(undefined)).toBe(DEFAULT_CONTINUOUS_RETENTION_HOURS);
    expect(continuousRetentionHours({ consents: [{ ...disabled[2], retention_hours: 9999 }], zones: [], push: { registered: false } })).toBe(DEFAULT_CONTINUOUS_RETENTION_HOURS);
  });
});
