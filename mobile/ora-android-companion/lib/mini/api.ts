import AsyncStorage from "@react-native-async-storage/async-storage";
import * as SecureStore from "expo-secure-store";
import { Platform } from "react-native";
export type Session = { url: string; token: string; device_id: string };
export type Task = {
  id: string;
  title: string;
  due_at: string | null;
  done: boolean;
  priority: number;
  version: number;
};
export type Action = {
  id: string;
  kind: string;
  payload: {
    title?: string;
    due_at?: string;
    text?: string;
    recipient?: string;
    body?: string;
  };
  status: string;
  expires_at: string;
};
export type Snapshot = {
  revision: number;
  tasks: Task[];
  messages: { id: string; role: string; text: string; created_at: string }[];
  memories: { id: string; text: string }[];
  actions: Action[];
  documents: { id: string; name: string }[];
  suggestions: { title: string; detail: string; prompt: string }[];
  settings: {
    name: string;
    timezone: string;
    quiet_start: number;
    quiet_end: number;
    briefing_hour: number;
  };
  devices: {
    id: string;
    label: string;
    paused: boolean;
    permissions: Record<string, boolean>;
  }[];
  events: { id: string; kind: string; text: string; observed_at: string }[];
  synced_at: string;
  device_id: string;
};
export type Op = {
  request_id: string;
  kind: string;
  payload: Record<string, unknown>;
};
export class ApiError extends Error {
  constructor(
    message: string,
    public status = 0,
  ) {
    super(message);
  }
}
export const makeId = () =>
  `${Date.now()}-${Math.random().toString(36).slice(2)}-${Math.random().toString(36).slice(2)}`;
export async function readLocal<T>(key: string, fallback: T): Promise<T> {
  try {
    return (
      JSON.parse((await AsyncStorage.getItem("ora2:" + key)) || "null") ??
      fallback
    );
  } catch {
    return fallback;
  }
}
export const writeLocal = (key: string, value: unknown) =>
  AsyncStorage.setItem("ora2:" + key, JSON.stringify(value));
export async function session(): Promise<Session | null> {
  if (Platform.OS === "web") return null;
  const raw = await SecureStore.getItemAsync("ora_mini_session");
  return raw ? JSON.parse(raw) : null;
}
export async function saveSession(value: Session) {
  await SecureStore.setItemAsync("ora_mini_session", JSON.stringify(value));
}
export async function clearSession() {
  await SecureStore.deleteItemAsync("ora_mini_session");
  const keys = await AsyncStorage.getAllKeys();
  await AsyncStorage.multiRemove(keys.filter((k) => k.startsWith("ora2:")));
}
export async function request<T = Record<string, unknown>>(
  path: string,
  body?: unknown,
  credentials?: Session,
): Promise<T> {
  const active = credentials || (await session());
  if (!active) throw new ApiError("Pair ORA first.", 401);
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 115000);
  try {
    const form = body instanceof FormData;
    const response = await fetch(active.url + "/api/v2" + path, {
      method: body ? "POST" : "GET",
      signal: controller.signal,
      headers: {
        Authorization: "Bearer " + active.token,
        ...(body && !form ? { "Content-Type": "application/json" } : {}),
      },
      body: body ? (form ? body : JSON.stringify(body)) : undefined,
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok)
      throw new ApiError(
        typeof result.detail === "string"
          ? result.detail
          : "ORA could not complete that request.",
        response.status,
      );
    return result;
  } catch (e) {
    if (e instanceof ApiError) throw e;
    throw new ApiError(
      "ORA is offline or waking up. Your saved workspace is still here.",
    );
  } finally {
    clearTimeout(timer);
  }
}
export async function pair(url: string, code: string) {
  const clean = url.trim().replace(/\/$/, "");
  if (!/^https:\/\/[a-z0-9.-]+(?::\d+)?$/i.test(clean))
    throw new Error("Use the HTTPS backend address from Render.");
  const result = await request<{ token: string; device_id: string }>(
    "/pair",
    { code: code.trim(), label: "My Android" },
    { url: clean, token: "", device_id: "" },
  );
  const active = { url: clean, ...result };
  await saveSession(active);
  return active;
}
