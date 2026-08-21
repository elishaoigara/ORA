import type { AwarenessCapability, AwarenessConsent, AwarenessState } from "@/lib/ora-device";

export const AWARENESS_CAPABILITIES: AwarenessCapability[] = ["push_alerts", "zone_routines", "continuous_location"];
export const DEFAULT_CONTINUOUS_RETENTION_HOURS = 24;
export const MAX_CONTINUOUS_RETENTION_HOURS = 24 * 7;

export function capabilityEnabled(state: AwarenessState | null | undefined, capability: AwarenessCapability): boolean {
  return Boolean(state?.consents.find((item) => item.capability === capability)?.enabled);
}

export function continuousRetentionHours(state: AwarenessState | null | undefined): number {
  const value = state?.consents.find((item) => item.capability === "continuous_location")?.retention_hours;
  if (!value || value < 1 || value > MAX_CONTINUOUS_RETENTION_HOURS) return DEFAULT_CONTINUOUS_RETENTION_HOURS;
  return value;
}

export function canSubmitAwarenessEvent(
  consents: AwarenessConsent[],
  eventType: "zone_enter" | "zone_exit" | "location_sample",
): boolean {
  const required: AwarenessCapability = eventType === "location_sample" ? "continuous_location" : "zone_routines";
  return Boolean(consents.find((item) => item.capability === required)?.enabled);
}
