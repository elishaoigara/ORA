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

export type AwarenessCapability = "push_alerts" | "zone_routines" | "continuous_location" | "notification_access" | "selected_contacts" | "device_health";

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

export type CommandTask = {
  id: number;
  title: string;
  priority: "low" | "medium" | "high" | string;
  created_at: string;
  due_at?: string | null;
  goal_id?: number | null;
};

export type CommandAlert = {
  id: number;
  rule_name: string;
  message: string;
  severity: "low" | "medium" | "high" | "critical" | string;
  timestamp: string;
  acknowledged: boolean;
};

export type CommandActivity = {
  category: string;
  title: string;
  detail: string;
  occurred_at: string;
  retention_hours: number;
};

export type CommandPreferences = {
  global_pause: boolean;
  quiet_hours_enabled: boolean;
  quiet_start?: string | null;
  quiet_end?: string | null;
  updated_at?: string | null;
};

export type Capture = {
  id: number;
  kind: "text" | "link" | "voice_transcript" | "shared_file" | string;
  title: string;
  body: string;
  metadata: Record<string, unknown>;
  status: "inbox" | "saved" | "archived" | "task";
  created_at: string;
  updated_at: string;
};

export type CommandCenter = {
  briefing: string;
  tasks: CommandTask[];
  alerts: CommandAlert[];
  attention_count: number;
  pending_capture_count: number;
  preferences: CommandPreferences;
  activity: CommandActivity[];
};

export type NotificationContentMode = "metadata" | "redacted" | "full";

export type NotificationSource = {
  package_name: string;
  app_label: string;
  content_mode: NotificationContentMode;
  enabled: boolean;
  updated_at?: string | null;
};

export type NotificationAuditEvent = {
  id: number;
  package_name: string;
  app_label: string;
  title: string;
  body: string;
  content_mode: NotificationContentMode;
  occurred_at: string;
  expires_at: string;
};

export type SelectedContact = {
  id?: number;
  display_name: string;
  normalized_phone?: string | null;
  relationship_label?: string | null;
  created_at?: string;
};

export type DeviceHealthSnapshot = {
  id?: number;
  battery_percent: number;
  is_charging: boolean;
  network_type: string;
  occurred_at?: string;
  retention_hours?: number;
};

export type DeviceApproval = {
  id: number;
  action_type: string;
  title: string;
  description: string;
  risk: string;
  status: "proposed" | "approved" | "completed" | "failed" | "rejected" | "cancelled" | string;
  requires_approval: boolean;
  source?: string | null;
  created_at: string;
  updated_at: string;
  expires_at?: string | null;
  error?: string | null;
  verification_status?: string | null;
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

export async function getCommandCenter(session: DeviceSession): Promise<CommandCenter> {
  const result = await requestJson<{ ok: boolean; command_center: CommandCenter }>(`${session.backendUrl}/api/devices/self/command-center`, {
    headers: deviceHeaders(session),
  });
  return result.command_center;
}

export async function getCommandPreferences(session: DeviceSession): Promise<CommandPreferences> {
  const result = await requestJson<{ ok: boolean; preferences: CommandPreferences }>(`${session.backendUrl}/api/devices/self/preferences`, {
    headers: deviceHeaders(session),
  });
  return result.preferences;
}

export async function updateCommandPreferences(
  session: DeviceSession,
  updates: Partial<Pick<CommandPreferences, "global_pause" | "quiet_hours_enabled" | "quiet_start" | "quiet_end">>,
): Promise<CommandPreferences> {
  const result = await requestJson<{ ok: boolean; preferences: CommandPreferences }>(`${session.backendUrl}/api/devices/self/preferences`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...deviceHeaders(session) },
    body: JSON.stringify(updates),
  });
  return result.preferences;
}

export async function getCaptures(session: DeviceSession, status?: Capture["status"]): Promise<Capture[]> {
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  const result = await requestJson<{ ok: boolean; captures: Capture[] }>(`${session.backendUrl}/api/devices/self/captures${query}`, {
    headers: deviceHeaders(session),
  });
  return result.captures;
}

export async function createCapture(
  session: DeviceSession,
  payload: Pick<Capture, "kind" | "title" | "body"> & { metadata?: Record<string, unknown> },
): Promise<Capture> {
  const result = await requestJson<{ ok: boolean; capture: Capture }>(`${session.backendUrl}/api/devices/self/captures`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...deviceHeaders(session) },
    body: JSON.stringify(payload),
  });
  return result.capture;
}

export async function updateCaptureStatus(
  session: DeviceSession,
  captureId: number,
  status: Capture["status"],
): Promise<Capture> {
  const result = await requestJson<{ ok: boolean; capture: Capture }>(`${session.backendUrl}/api/devices/self/captures/${captureId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...deviceHeaders(session) },
    body: JSON.stringify({ status }),
  });
  return result.capture;
}

export type VoiceCaptureResult = {
  capture: Capture;
  transcription: {
    text: string;
    language?: string | null;
    duration_seconds?: number | null;
    model?: string;
  };
};

export async function uploadVoiceCapture(
  session: DeviceSession,
  input: { uri: string; filename: string; mimeType: string; language?: string },
): Promise<VoiceCaptureResult> {
  const form = new FormData();
  form.append("audio", { uri: input.uri, name: input.filename, type: input.mimeType } as never);
  form.append("language", input.language || "auto");
  const result = await requestJson<{ ok: boolean } & VoiceCaptureResult>(`${session.backendUrl}/api/devices/self/captures/voice`, {
    method: "POST",
    headers: deviceHeaders(session),
    body: form,
  });
  return { capture: result.capture, transcription: result.transcription };
}

export async function getCommandActivity(session: DeviceSession): Promise<CommandActivity[]> {
  const result = await requestJson<{ ok: boolean; activity: CommandActivity[] }>(`${session.backendUrl}/api/devices/self/activity`, {
    headers: deviceHeaders(session),
  });
  return result.activity;
}

export async function getNotificationSources(session: DeviceSession): Promise<NotificationSource[]> {
  const result = await requestJson<{ ok: boolean; sources: NotificationSource[] }>(`${session.backendUrl}/api/devices/self/notification-sources`, {
    headers: deviceHeaders(session),
  });
  return result.sources;
}

export async function replaceNotificationSources(
  session: DeviceSession,
  sources: Array<Pick<NotificationSource, "package_name" | "app_label" | "content_mode" | "enabled">>,
): Promise<NotificationSource[]> {
  const result = await requestJson<{ ok: boolean; sources: NotificationSource[] }>(`${session.backendUrl}/api/devices/self/notification-sources`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...deviceHeaders(session) },
    body: JSON.stringify({ sources }),
  });
  return result.sources;
}

export async function submitNotificationAuditEvent(
  session: DeviceSession,
  payload: Pick<NotificationAuditEvent, "package_name" | "title" | "body">,
): Promise<void> {
  await requestJson<{ ok: boolean }>(`${session.backendUrl}/api/devices/self/notification-events`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...deviceHeaders(session) },
    body: JSON.stringify(payload),
  });
}

export async function getNotificationAuditEvents(session: DeviceSession): Promise<NotificationAuditEvent[]> {
  const result = await requestJson<{ ok: boolean; events: NotificationAuditEvent[] }>(`${session.backendUrl}/api/devices/self/notification-events`, {
    headers: deviceHeaders(session),
  });
  return result.events;
}

export async function deleteNotificationAuditEvents(session: DeviceSession): Promise<number> {
  const result = await requestJson<{ ok: boolean; deleted: number }>(`${session.backendUrl}/api/devices/self/notification-events`, {
    method: "DELETE",
    headers: deviceHeaders(session),
  });
  return result.deleted;
}

export async function getSelectedContacts(session: DeviceSession): Promise<SelectedContact[]> {
  const result = await requestJson<{ ok: boolean; contacts: SelectedContact[] }>(`${session.backendUrl}/api/devices/self/contacts`, {
    headers: deviceHeaders(session),
  });
  return result.contacts;
}

export async function replaceSelectedContacts(
  session: DeviceSession,
  contacts: Array<Pick<SelectedContact, "display_name" | "normalized_phone" | "relationship_label">>,
): Promise<SelectedContact[]> {
  const result = await requestJson<{ ok: boolean; contacts: SelectedContact[] }>(`${session.backendUrl}/api/devices/self/contacts`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...deviceHeaders(session) },
    body: JSON.stringify({ contacts }),
  });
  return result.contacts;
}

export async function getLatestDeviceHealth(session: DeviceSession): Promise<DeviceHealthSnapshot | null> {
  const result = await requestJson<{ ok: boolean; health: DeviceHealthSnapshot | null }>(`${session.backendUrl}/api/devices/self/health`, {
    headers: deviceHeaders(session),
  });
  return result.health;
}

export async function submitDeviceHealth(session: DeviceSession, snapshot: DeviceHealthSnapshot): Promise<DeviceHealthSnapshot> {
  const result = await requestJson<{ ok: boolean; health: DeviceHealthSnapshot }>(`${session.backendUrl}/api/devices/self/health`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...deviceHeaders(session) },
    body: JSON.stringify(snapshot),
  });
  return result.health;
}

export async function deleteDeviceHealthHistory(session: DeviceSession): Promise<number> {
  const result = await requestJson<{ ok: boolean; deleted: number }>(`${session.backendUrl}/api/devices/self/health`, {
    method: "DELETE",
    headers: deviceHeaders(session),
  });
  return result.deleted;
}

export async function getDeviceApprovals(session: DeviceSession): Promise<DeviceApproval[]> {
  const result = await requestJson<{ ok: boolean; approvals: DeviceApproval[] }>(`${session.backendUrl}/api/devices/self/approvals`, {
    headers: deviceHeaders(session),
  });
  return result.approvals;
}

export async function approveDeviceApproval(session: DeviceSession, actionId: number): Promise<DeviceApproval> {
  const result = await requestJson<{ ok: boolean; approval: DeviceApproval }>(`${session.backendUrl}/api/devices/self/approvals/${actionId}/approve`, {
    method: "POST",
    headers: deviceHeaders(session),
  });
  return result.approval;
}

export async function rejectDeviceApproval(session: DeviceSession, actionId: number): Promise<DeviceApproval> {
  const result = await requestJson<{ ok: boolean; approval: DeviceApproval }>(`${session.backendUrl}/api/devices/self/approvals/${actionId}/reject`, {
    method: "POST",
    headers: deviceHeaders(session),
  });
  return result.approval;
}

export async function executeDeviceApproval(session: DeviceSession, actionId: number): Promise<DeviceApproval> {
  const result = await requestJson<{ ok: boolean; approval: DeviceApproval }>(`${session.backendUrl}/api/devices/self/approvals/${actionId}/execute`, {
    method: "POST",
    headers: deviceHeaders(session),
  });
  return result.approval;
}

export async function completeCommandTask(session: DeviceSession, taskId: number): Promise<void> {
  await requestJson<{ ok: boolean }>(`${session.backendUrl}/api/devices/self/tasks/${taskId}/complete`, {
    method: "POST",
    headers: deviceHeaders(session),
  });
}

export async function acknowledgeCommandAlert(session: DeviceSession, alertId: number): Promise<void> {
  await requestJson<{ ok: boolean }>(`${session.backendUrl}/api/devices/self/alerts/${alertId}/ack`, {
    method: "POST",
    headers: deviceHeaders(session),
  });
}

export async function clearDeviceSession() {
  await clearSensitiveSession();
}
