// src/api.js

const BASE_URL =
  import.meta.env.VITE_API_URL || "https://ora-oovf.onrender.com";

/* unified request helper */
async function request(path, options = {}) {
  const res = await fetch(`${BASE_URL}/api${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });

  if (!res.ok) {
    throw new Error(await res.text());
  }

  return res.json();
}

/* =========================
   MATCHES YOUR BACKEND EXACTLY
   ========================= */

export const health = () => request("/health");

export const getStatus = () => request("/status");

export const getAgentStatus = () => request("/agent/status");

export const getAlerts = () => request("/alerts");

/* optional extras (already exist backend-side or safe fallback) */

export const getTasks = () => request("/tasks");

export const getGoals = () => request("/goals");

export const getCalendarToday = () => request("/calendar/today");

/* fallback */
export default BASE_URL;