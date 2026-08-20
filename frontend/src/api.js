const BASE_URL =
  import.meta.env.VITE_API_URL?.replace(/\/$/, "") ||
  "https://ora-oovf.onrender.com";
const API_TOKEN = import.meta.env.VITE_ORA_API_TOKEN || "";

export function apiFetch(path, options = {}) {
  const cleanPath = path.startsWith("/") ? path : `/${path}`;
  const headers = {
    ...(API_TOKEN ? { "X-ORA-Token": API_TOKEN } : {}),
    ...(options.headers || {}),
  };

  return fetch(`${BASE_URL}${cleanPath}`, { ...options, headers });
}

/* =========================
   CORE REQUEST HELPER
   ========================= */
async function request(path, options = {}) {
  const cleanPath = path.startsWith("/") ? path : `/${path}`;

  const res = await apiFetch(`/api${cleanPath}`, {
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
export const getConversations = (limit = 40, sessionId = null) =>
  request(`/conversations?limit=${limit}${sessionId ? `&session_id=${encodeURIComponent(sessionId)}` : ""}`);
export const getRecentSessions = (limit = 10) => request(`/sessions?limit=${limit}`);

/* =========================
   CHAT
   ========================= */
export const sendMessage = (message, sessionId = null) =>
  request("/chat", {
    method: "POST",
    body: JSON.stringify({ message, session_id: sessionId }),
  });

/* =========================
   ALERTS (REAL BACKEND)
   ========================= */

export const getAlerts = (limit = 50) => request(`/alerts?limit=${limit}`);

export const ackAlert = (id) =>
  request(`/alerts/${id}/ack`, { method: "POST" });

export const ackAllAlerts = () =>
  request("/alerts/ack-all", { method: "POST" });

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

export const connectGoogle = () => {
  // Navigate the whole window so the OAuth redirect comes back to this app
  window.location.href = `${BASE_URL}/api/auth/google`;
};

export const disconnectGoogle = () =>
  request("/auth/google", { method: "DELETE" });

/* =========================
   KNOWLEDGE
   ========================= */

export const getDocuments = () => request("/knowledge/documents");

export const searchKnowledge = (query, n_results = 4) =>
  request("/knowledge/search", {
    method: "POST",
    body: JSON.stringify({ query, n_results }),
  });

export const deleteDocument = (filename) =>
  request(`/knowledge/documents/${encodeURIComponent(filename)}`, {
    method: "DELETE",
  });

export const getDocumentSummary = (filename) =>
  request(`/knowledge/summary/${encodeURIComponent(filename)}`);

export const uploadDocument = async (file, tags = "") => {
  const formData = new FormData();
  formData.append("file", file);
  if (tags) formData.append("tags", tags);
  const res = await apiFetch("/api/knowledge/upload", {
    method: "POST",
    body: formData,
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
};

/* =========================
   BRIEFING & PREDICTIONS
   ========================= */

export const getBriefing = () => request("/briefing");
export const getPredictions = () => request("/predictions");
export const triggerAgentRun = () => request("/agent/run", { method: "POST" });

/* =========================
   PUSH NOTIFICATIONS
   ========================= */

export const registerPushToken = (token, platform = "expo") =>
  request("/push/register", {
    method: "POST",
    body: JSON.stringify({ token, platform }),
  });

export const unregisterPushToken = (token) =>
  request("/push/register", {
    method: "DELETE",
    body: JSON.stringify({ token }),
  });

export const getPushTokenCount = () => request("/push/tokens");

export const testPush = (token = null, title = "ORA Test", body = "Push works ✓") =>
  request("/push/test", {
    method: "POST",
    body: JSON.stringify({ token, title, body }),
  });

/* =========================
   GOALS (extended)
   ========================= */

export const createGoal = (goal, due_at = null) =>
  request("/goals", {
    method: "POST",
    body: JSON.stringify({ goal, due_at }),
  });

export const triggerGoalCheckin = () =>
  request("/goals/checkin", { method: "POST" });

/* =========================
   PERSONAL CONTEXT & ACTIONS
   ========================= */

export const getPersonalContext = (force = false) =>
  request(`/context${force ? "?force=true" : ""}`);

export const getCapabilities = () => request("/capabilities");
export const getActions = (status = "", limit = 50) =>
  request(`/actions?limit=${limit}${status ? `&status=${encodeURIComponent(status)}` : ""}`);
export const createAction = (payload) =>
  request("/actions", { method: "POST", body: JSON.stringify(payload) });
export const approveAction = (id) => request(`/actions/${id}/approve`, { method: "POST" });
export const rejectAction = (id) => request(`/actions/${id}/reject`, { method: "POST" });
export const cancelAction = (id) => request(`/actions/${id}/cancel`, { method: "POST" });
export const executeAction = (id) => request(`/actions/${id}/execute`, { method: "POST" });
export const getLearnedFacts = (status = "candidate", limit = 50) =>
  request(`/memory/learned?status=${encodeURIComponent(status)}&limit=${limit}`);
export const confirmLearnedFact = (id) => request(`/memory/learned/${id}/confirm`, { method: "POST" });
export const rejectLearnedFact = (id) => request(`/memory/learned/${id}/reject`, { method: "POST" });
export const updateLearnedFact = (id, payload) =>
  request(`/memory/learned/${id}`, { method: "PATCH", body: JSON.stringify(payload) });
export const forgetLearnedFact = (id) => request(`/memory/learned/${id}`, { method: "DELETE" });
export const getGoalTasks = (goalId, status = "") =>
  request(`/goals/${goalId}/tasks${status ? `?status=${encodeURIComponent(status)}` : ""}`);
export const syncGoal = (goalId) => request(`/goals/${goalId}/sync`, { method: "POST" });

/* =========================
   BASE URL EXPORT
   ========================= */

export default BASE_URL;
/* =========================
   PHASE 2 — COMMUNICATION AGENT
   ========================= */

export const getGmailSummary      = ()      => request("/gmail/summary");
export const getGmailEmails       = (n=15)  => request(`/gmail/emails?limit=${n}`);
export const getPendingReplies    = (n=15)  => request(`/gmail/replies/pending?limit=${n}`);
export const getReplyHistory      = (n=20)  => request(`/gmail/replies/history?limit=${n}`);
export const getReplyStats        = ()      => request("/gmail/replies/stats");

export const generateReplies      = ()      =>
  request("/gmail/replies/generate", { method: "POST" });

export const approveReply         = (id)    =>
  request(`/gmail/replies/${id}/approve`, { method: "POST" });

export const rejectReply          = (id)    =>
  request(`/gmail/replies/${id}/reject`, { method: "POST" });

export const updateReplyText      = (id, text) =>
  request(`/gmail/replies/${id}/text`, { method: "PUT",  body: JSON.stringify({ text }) });

export const regenerateReply      = (id, tone = "professional") =>
  request(`/gmail/replies/${id}/regenerate`, { method: "POST", body: JSON.stringify({ tone }) });

/* =========================
   PHASE 2 — PROACTIVE INTELLIGENCE
   ========================= */

export const getProactiveStatus   = ()      => request("/proactive/status");
export const runProactiveChecks   = ()      => request("/proactive/run", { method: "POST" });

/* =========================
   PHASE 2 — VOICE
   ========================= */

// Voice transcription is called with raw FormData (not JSON) — done inline in ChatPage.
