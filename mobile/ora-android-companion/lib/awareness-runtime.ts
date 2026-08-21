import { Platform } from "react-native";
import * as Location from "expo-location";
import * as SecureStore from "expo-secure-store";
import * as TaskManager from "expo-task-manager";

import { loadDeviceSession, submitAwarenessEvent, type AwarenessZone } from "@/lib/ora-device";

export const ZONE_TASK = "ora-companion-zone-events-v1";
export const CONTINUOUS_LOCATION_TASK = "ora-companion-continuous-location-v1";
const RUNTIME_KEY = "ora_companion_awareness_runtime_v1";

export type AwarenessRuntimeSettings = {
  zones: AwarenessZone[];
  continuousEnabled: boolean;
};

const emptyRuntime: AwarenessRuntimeSettings = { zones: [], continuousEnabled: false };

export async function getRuntimeSettings(): Promise<AwarenessRuntimeSettings> {
  if (Platform.OS === "web") return emptyRuntime;
  const raw = await SecureStore.getItemAsync(RUNTIME_KEY);
  if (!raw) return emptyRuntime;
  try {
    const parsed = JSON.parse(raw) as AwarenessRuntimeSettings;
    return {
      zones: Array.isArray(parsed.zones) ? parsed.zones : [],
      continuousEnabled: Boolean(parsed.continuousEnabled),
    };
  } catch {
    return emptyRuntime;
  }
}

export async function saveRuntimeSettings(next: AwarenessRuntimeSettings): Promise<void> {
  if (Platform.OS === "web") return;
  await SecureStore.setItemAsync(RUNTIME_KEY, JSON.stringify(next));
}

async function submitFromBackground(
  payload:
    | { event_type: "zone_enter" | "zone_exit"; zone_id: string }
    | { event_type: "location_sample"; latitude: number; longitude: number; accuracy_m: number },
) {
  const session = await loadDeviceSession();
  if (!session) return;
  await submitAwarenessEvent(session, payload);
}

if (!TaskManager.isTaskDefined(ZONE_TASK)) {
  TaskManager.defineTask(ZONE_TASK, async ({ data, error }) => {
    if (error || !data) return;
    const event = data as { eventType?: number; region?: { identifier?: string } };
    const zoneId = event.region?.identifier;
    if (!zoneId) return;
    const eventType = event.eventType === Location.GeofencingEventType.Enter ? "zone_enter" : "zone_exit";
    try {
      await submitFromBackground({ event_type: eventType, zone_id: zoneId });
    } catch {
      // The server remains the consent authority; it can reject stale tasks safely.
    }
  });
}

if (!TaskManager.isTaskDefined(CONTINUOUS_LOCATION_TASK)) {
  TaskManager.defineTask(CONTINUOUS_LOCATION_TASK, async ({ data, error }) => {
    if (error || !data) return;
    const runtime = await getRuntimeSettings();
    if (!runtime.continuousEnabled) return;
    const locations = (data as { locations?: Location.LocationObject[] }).locations ?? [];
    const latest = locations.at(-1);
    if (!latest) return;
    try {
      await submitFromBackground({
        event_type: "location_sample",
        latitude: latest.coords.latitude,
        longitude: latest.coords.longitude,
        accuracy_m: latest.coords.accuracy ?? 0,
      });
    } catch {
      // A later OS delivery will retry; do not retain location payloads locally.
    }
  });
}
