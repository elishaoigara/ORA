// src/api.js

const BASE_URL =
  import.meta.env.VITE_API_URL || "https://ora-oovf.onrender.com";

/* helper */
async function request(path, options = {}) {
  const res = await fetch(`${BASE_URL}${path}`, {
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

/* ✅ MATCHES YOUR IMPORTS */
export const health = () => request("/health");

export const getAgentStatus = () => request("/agent/status");

export const getAlerts = () => request("/alerts");

export const getStatus = () => request("/status");

/* optional fallback */
export default BASE_URL;