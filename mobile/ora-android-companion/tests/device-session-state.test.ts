import { describe, expect, it } from "vitest";

import { clearedDeviceState, pairedDeviceState } from "../lib/device-session-state";
import type { DeviceSession } from "../lib/ora-device";

const session: DeviceSession = {
  backendUrl: "https://ora.example.com",
  deviceId: "dev_test_phone",
  deviceToken: "device-token-only-for-test",
  device: {
    id: "dev_test_phone",
    label: "Test Pixel",
    platform: "android",
    app_version: "0.1.0",
    status: "active",
    paired_at: "2026-08-20T10:00:00+03:00",
    last_seen_at: "2026-08-20T10:00:00+03:00",
    token_hint: "e12345",
    capabilities: [],
  },
};

describe("Android companion device session state", () => {
  it("keeps the paired device and clears previous errors after a successful pairing", () => {
    const state = pairedDeviceState(session);

    expect(state.session?.deviceToken).toBe("device-token-only-for-test");
    expect(state.device?.id).toBe("dev_test_phone");
    expect(state.error).toBeNull();
  });

  it("clears every in-memory device reference after revoke or local credential removal", () => {
    expect(clearedDeviceState()).toEqual({ session: null, device: null, error: null });
  });
});
