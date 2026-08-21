import { Platform } from "react-native";
import * as SecureStore from "expo-secure-store";

export type DeviceRecord = {
  id: string;
  label: string;
  platform: string;
  app_version?: string | null;
  status: "active" | "revoked";
  paired_at: string;
  last_seen_at?: string | null;
  token_hint: string;
  revoked_at?: string | null;
  capabilities: string[];
};

export type DeviceSession = {
  backendUrl: string;
  deviceId: string;
  deviceToken: string;
  device: DeviceRecord;
};

export type PairingResult = {
  device: DeviceRecord;
  device_token: string;
};

export type AwarenessCapability = "push_alerts" | "zone_routines" | "continuous_location";

export type AwarenessConsent = {
  capability: AwarenessCapability;
  enabled: boolean;
  retention_hours: number;
  policy_version: string;
  updated_at?: string | null;
};

export type AwarenessZone = {
  id: string;
  label: string;
  latitude: number;
  longitude: number;
  radius_m: number;
  enabled: boolean;
  updated_at?: string | null;
};

export type AwarenessState = {
  consents: AwarenessConsent[];
  zones: AwarenessZone[];
  push: { registered: boolean; provider?: string | null; created_at?: string | null; last_seen_at?: string | null };
};

const SESSION_KEY = "ora_companion_device_session_v1";
export const DEFAULT_BACKEND_URL = "https://ora-oovf.onrender.com";

function normalizeBackendUrl(value: string): string {
  const cleaned = value.trim().replace(/\/$/, "");
  if (!/^https:\/\//i.test(cleaned)) throw new Error("Use a secure HTTPS ORA backend address.");
  return cleaned;
}

async function saveSensitiveSession(value: string) {
  if (Platform.OS === "web") {
    if (typeof sessionStorage !== "undefined") sessionStorage.setItem(SESSION_KEY, value);
    return;
  }
  await SecureStore.setItemAsync(SESSION_KEY, value);
}

async function readSensitiveSession(): Promise<string | null> {
  if (Platform.OS === "web") return typeof sessionStorage === "undefined" ? null : sessionStorage.getItem(SESSION_KEY);
  return SecureStore.getItemAsync(SESSION_KEY);
}

async function clearSensitiveSession() {
  if (Platform.OS === "web") {
    if (typeof sessionStorage !== "undefined") sessionStorage.removeItem(SESSION_KEY);
    return;
  }
  await SecureStore.deleteItemAsync(SESSION_KEY);
}

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, init);
  } catch {
    throw new Error("ORA could not be reached. Check the backend address and connection.");
  }
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof body.detail === "string" ? body.detail : body.detail?.message;
    throw new Error(detail || body.error || `ORA returned ${response.status}.`);
  }
  return body as T;
}

function deviceHeaders(session: DeviceSession) {
  return { "X-ORA-Device-ID": session.deviceId, "X-ORA-Device-Token": session.deviceToken };
}

export async function pairWithOra(input: { backendUrl: string; pairingCode: string; deviceName: string; appVersion?: string }): Promise<DeviceSession> {
  const backendUrl = normalizeBackendUrl(input.backendUrl);
  const result = await requestJson<{ ok: boolean } & PairingResult>(`${backendUrl}/api/devices/pair`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      pairing_code: input.pairingCode,
      device_name: input.deviceName,
      platform: "android",
      app_version: input.appVersion || "0.1.0",
    }),
  });
  if (!result.ok || !result.device_token) throw new Error("ORA did not return a device credential.");
  const session: DeviceSession = { backendUrl, deviceId: result.device.id, deviceToken: result.device_token, device: result.device };
  await saveSensitiveSession(JSON.stringify(session));
  return session;
}

export async function loadDeviceSession(): Promise<DeviceSession | null> {
  const raw = await readSensitiveSession();
  if (!raw) return null;
  try {
    const session = JSON.parse(raw) as DeviceSession;
    if (!session.backendUrl || !session.deviceId || !session.deviceToken || !session.device) return null;
    return session;
  } catch {
    await clearSensitiveSession();
    return null;
  }
}

export async function getCurrentDevice(session: DeviceSession): Promise<DeviceRecord> {
  const result = await requestJson<{ ok: boolean; device: DeviceRecord }>(`${session.backendUrl}/api/devices/self`, {
    headers: deviceHeaders(session),
  });
  return result.device;
}

export async function checkIn(session: DeviceSession): Promise<DeviceRecord> {
  const result = await requestJson<{ ok: boolean; device: DeviceRecord }>(`${session.backendUrl}/api/devices/self/check-in`, {
    method: "POST",
    headers: deviceHeaders(session),
  });
  return result.device;
}

export async function revokeCurrentDevice(session: DeviceSession): Promise<void> {
  await requestJson<{ ok: boolean }>(`${session.backendUrl}/api/devices/self/revoke`, {
    method: "POST",
    headers: deviceHeaders(session),
  });
  await clearSensitiveSession();
}

export async function getAwarenessState(session: DeviceSession): Promise<AwarenessState> {
  const result = await requestJson<{ ok: boolean; awareness: AwarenessState }>(`${session.backendUrl}/api/devices/self/awareness`, {
    headers: deviceHeaders(session),
  });
  return result.awareness;
}

export async function setAwarenessConsent(
  session: DeviceSession,
  capability: AwarenessCapability,
  enabled: boolean,
  retentionHours?: number,
): Promise<AwarenessState> {
  const result = await requestJson<{ ok: boolean; awareness: AwarenessState }>(`${session.backendUrl}/api/devices/self/awareness`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...deviceHeaders(session) },
    body: JSON.stringify({ capability, enabled, retention_hours: retentionHours }),
  });
  return result.awareness;
}

export async function replaceAwarenessZones(
  session: DeviceSession,
  zones: Array<Pick<AwarenessZone, "id" | "label" | "latitude" | "longitude" | "radius_m">>,
): Promise<AwarenessZone[]> {
  const result = await requestJson<{ ok: boolean; zones: AwarenessZone[] }>(`${session.backendUrl}/api/devices/self/zones`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...deviceHeaders(session) },
    body: JSON.stringify({ zones }),
  });
  return result.zones;
}

export async function registerAwarenessPushToken(session: DeviceSession, token: string): Promise<AwarenessState["push"]> {
  const result = await requestJson<{ ok: boolean; push: AwarenessState["push"] }>(`${session.backendUrl}/api/devices/self/push/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...deviceHeaders(session) },
    body: JSON.stringify({ token, provider: "expo" }),
  });
  return result.push;
}

export async function testAwarenessPush(session: DeviceSession): Promise<string> {
  const result = await requestJson<{ ok: boolean; message: string }>(`${session.backendUrl}/api/devices/self/push/test`, {
    method: "POST",
    headers: deviceHeaders(session),
  });
  if (!result.ok) throw new Error(result.message || "ORA could not dispatch a push test.");
  return result.message;
}

export async function submitAwarenessEvent(
  session: DeviceSession,
  payload:
    | { event_type: "zone_enter" | "zone_exit"; zone_id: string }
    | { event_type: "location_sample"; latitude: number; longitude: number; accuracy_m: number }
    | { event_type: "awareness_heartbeat"; mode: string },
): Promise<void> {
  await requestJson<{ ok: boolean }>(`${session.backendUrl}/api/devices/self/events`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...deviceHeaders(session) },
    body: JSON.stringify(payload),
  });
}

export async function deletePreciseLocationHistory(session: DeviceSession): Promise<number> {
  const result = await requestJson<{ ok: boolean; deleted: number }>(`${session.backendUrl}/api/devices/self/location/delete`, {
    method: "POST",
    headers: deviceHeaders(session),
  });
  return result.deleted;
}

export async function clearDeviceSession() {
  await clearSensitiveSession();
}
