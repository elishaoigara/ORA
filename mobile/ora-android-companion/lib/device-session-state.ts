import type { DeviceRecord, DeviceSession } from "@/lib/ora-device";

export type CompanionSessionState = {
  session: DeviceSession | null;
  device: DeviceRecord | null;
  error: string | null;
};

export function pairedDeviceState(session: DeviceSession): CompanionSessionState {
  return { session, device: session.device, error: null };
}

export function clearedDeviceState(): CompanionSessionState {
  return { session: null, device: null, error: null };
}
