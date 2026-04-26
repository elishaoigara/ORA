// src/api.js

const BASE_URL =
  import.meta.env.VITE_API_URL?.replace(/\/$/, "") ||
  "https://ora-oovf.onrender.com";

/* unified request helper */
async function request(path, options = {}) {
  const cleanPath = path.startsWith("/") ? path : `/${path}`;

  const res = await fetch(`${BASE_URL}/api${cleanPath}`, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });

  if (!res.ok) {
    const err = await res.text();
    throw new Error(err);
  }

  return res.json();
}

/* =========================
   BACKEND ALIGNED ENDPOINTS
   ========================= */

export const health = () => request("/health");

export const getStatus = () => request("/status");

export const getAgentStatus = () => request("/agent/status");

/* ⚠️ IMPORTANT: THIS DOES NOT EXIST IN YOUR BACKEND */
export const getAlerts = () => request("/alerts"); // will 404 unless you add it

export const getTasks = () => request("/tasks");

export const getGoals = () => request("/goals");

export const getCalendarToday = () => request("/calendar/today");

/* default export */
export default BASE_URL;