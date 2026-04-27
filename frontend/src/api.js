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

export const getTasks = (status = "pending") => request(`/tasks?status=${status}`);
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
   ALERTS (REAL BACKEND)
   ========================= */

export const getAlerts = (limit = 50) => request(`/alerts?limit=${limit}`);

export const ackAlert = (id) =>
  request(`/alerts/${id}/ack`, { method: "POST" });

export const ackAllAlerts = async () => {
  const alerts = await getAlerts(100);
  const unread = Array.isArray(alerts) ? alerts.filter((a) => !a.acknowledged) : [];
  await Promise.all(unread.map((a) => ackAlert(a.id)));
  return { ok: true };
};

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
   THE NUMBER (top priority task)
   ========================= */

export const getTheNumber = async () => {
  try {
    const tasks = await getTasks("pending");
    if (!Array.isArray(tasks) || tasks.length === 0) return { status: "empty" };

    const now = new Date();
    const scored = tasks.map((t) => {
      const isOverdue = t.due_at && new Date(t.due_at) < now;
      const priScore = t.priority === "high" ? 30 : t.priority === "medium" ? 10 : 0;
      const overdueScore = isOverdue ? 40 : 0;
      const ageScore = Math.min(
        Math.floor((now - new Date(t.created_at)) / (1000 * 60 * 60 * 24)) * 2,
        20
      );
      return { ...t, score: priScore + overdueScore + ageScore, overdue: isOverdue };
    });

    scored.sort((a, b) => b.score - a.score);
    const top = scored[0];
    return {
      ...top,
      reason:
        top.overdue
          ? "Overdue — needs immediate attention"
          : top.priority === "high"
          ? "High priority task"
          : "Top pending task",
    };
  } catch {
    return { status: "empty" };
  }
};

/* =========================
   MEMORY (REAL BACKEND)
   ========================= */

export const getProfile = () => request("/memory/profile");

export const getPreferences = () => request("/memory/preferences");

export const getMemoryEvents = (limit = 30) =>
  request(`/memory/events?limit=${limit}`);

/* =========================
   GOOGLE AUTH (matches backend)
   ========================= */

export const getGoogleAuthStatus = () =>
  request("/auth/google/status");

/* =========================
   BASE URL EXPORT
   ========================= */

export default BASE_URL;