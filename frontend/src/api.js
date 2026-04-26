const BASE_URL =
  import.meta.env.VITE_API_URL?.replace(/\/$/, "") ||
  "https://ora-oovf.onrender.com";

/* =========================
   CORE REQUEST HELPER
   ========================= */
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
    throw new Error(await res.text());
  }

  return res.json();
}

/* =========================
   BACKEND MATCHED ENDPOINTS
   ========================= */

export const health = () => request("/health");
export const getStatus = () => request("/status");
export const getAgentStatus = () => request("/agent/status");

export const getTasks = () => request("/tasks");
export const getGoals = () => request("/goals");
export const getCalendarToday = () => request("/calendar/today");

export const getMpesaSummary = () => request("/mpesa/summary");
export const getConversations = () => request("/conversations");

/* =========================
   CHAT
   ========================= */
export const sendMessage = (message) =>
  request("/chat", {
    method: "POST",
    body: JSON.stringify({ message }),
  });

/* =========================
   PLACEHOLDER FEATURES (NO BACKEND YET)
   ========================= */

export const getAlerts = () => request("/agent/status"); // fallback mapping
export const ackAlert = async () => ({ ok: true });
export const ackAllAlerts = async () => ({ ok: true });

export const getTheNumber = async () => ({ value: 0 });

/* ========================= */
export default BASE_URL;
/* =========================
   TASKS (REAL BACKEND)
   ========================= */

export const createTask = (data) =>
  request("/tasks", {
    method: "POST",
    body: JSON.stringify(data),
  });

export const completeTask = (taskId) =>
  request(`/tasks/${taskId}/complete`, {
    method: "POST",
  });

export const deleteTask = (taskId) =>
  request(`/tasks/${taskId}`, {
    method: "DELETE",
  });

/* =========================
   MEMORY (PLACEHOLDERS for now)
   ========================= */

export const getProfile = async () => ({
  name: "User",
  email: "",
});

export const getPreferences = async () => ({
  theme: "light",
});

export const getMemoryEvents = async () => ([]);

/* =========================
   GOOGLE AUTH (matches backend)
   ========================= */

export const getGoogleAuthStatus = () =>
  request("/auth/google/status");