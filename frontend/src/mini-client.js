const base = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(
  /\/$/,
  "",
);
export const uid = () => crypto.randomUUID();
export const saved = (key, fallback = null) => {
  try {
    return JSON.parse(sessionStorage.getItem(`ora2:${key}`)) ?? fallback;
  } catch {
    return fallback;
  }
};
export const save = (key, value) =>
  sessionStorage.setItem(`ora2:${key}`, JSON.stringify(value));
export async function api(path, body, method = body ? "POST" : "GET") {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 115000);
  try {
    const token = saved("token");
    const response = await fetch(`${base}/api/v2${path}`, {
      method,
      signal: controller.signal,
      headers: {
        ...(body && !(body instanceof FormData)
          ? { "Content-Type": "application/json" }
          : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: body
        ? body instanceof FormData
          ? body
          : JSON.stringify(body)
        : undefined,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(
        typeof data.detail === "string"
          ? data.detail
          : "Request could not be completed.",
      );
      error.status = response.status;
      throw error;
    }
    return data;
  } catch (error) {
    if (!error.status)
      error.message =
        "ORA could not connect. The server may be waking up. Your draft is kept here.";
    throw error;
  } finally {
    clearTimeout(timer);
  }
}
export async function connect(token) {
  const result = await api("/session", { token });
  save("token", result.token);
}
export async function operation(kind, payload, requestId = uid()) {
  return api("/operations", { request_id: requestId, kind, payload });
}
export async function downloadDocument(id, name) {
  const token = saved("token");
  if (!token) throw new Error("Connect to ORA first.");
  const response = await fetch(`${base}/api/v2/documents/${encodeURIComponent(id)}/download`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(typeof error.detail === "string" ? error.detail : "File download failed.");
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  try {
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = (name || "ora-file.txt").replace(/[^a-zA-Z0-9._-]/g, "_");
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
  } finally {
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
}
export function clearLocal() {
  for (const key of Object.keys(sessionStorage))
    if (key.startsWith("ora2:")) sessionStorage.removeItem(key);
}
