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
  const res = await fetch(`${BASE_URL}/api/knowledge/upload`, {
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
   CONTENT STUDIO
   ========================= */

export const createContentDraft = (payload) =>
  request("/content/draft", { method: "POST", body: JSON.stringify(payload) });

export const getContentDrafts = (status = "all", limit = 20, search = "") =>
  request(`/content/drafts?status=${status}&limit=${limit}&search=${encodeURIComponent(search)}`);

export const getContentDraft = (id) =>
  request(`/content/drafts/${id}`);

export const updateDraftStatus = (id, status) =>
  request(`/content/drafts/${id}/status?status=${status}`, { method: "POST" });

export const editDraftText = (id, draft_text) =>
  request(`/content/drafts/${id}/text`, { method: "PUT", body: JSON.stringify({ draft_text }) });

export const regenerateDraft = (id, feedback = "") =>
  request(`/content/drafts/${id}/regenerate`, { method: "POST", body: JSON.stringify({ feedback }) });

export const deleteDraft = (id) =>
  request(`/content/drafts/${id}`, { method: "DELETE" });

export const getContentStats = () =>
  request("/content/stats");

/* =========================
   CODE AGENT
   ========================= */

export const getCodeStats        = ()           => request("/code/stats");
export const getCodeRepos        = ()           => request("/code/repos");
export const getCodeRuns         = ()           => request("/code/runs");
export const getRepoRun          = (repo)       => request(`/code/runs/${repo}`);
export const getCodeScans        = (repo = "", status = "open", limit = 40) =>
  request(`/code/scans?repo=${repo}&status=${status}&limit=${limit}`);
export const resolveCodeScan     = (id)         => request(`/code/scans/${id}/resolve`, { method: "POST" });
export const openCodeIssue       = (id)         => request(`/code/scans/${id}/issue`,   { method: "POST" });
export const scanRepo            = (repo)       => request(`/code/scan/${repo}/sync`,   { method: "POST" });
export const scanAllRepos        = ()           => request("/code/scan",                { method: "POST" });
export const askCodeAgent        = (question, repo = "") =>
  request("/code/ask", { method: "POST", body: JSON.stringify({ question, repo }) });

/* =========================
   BASE URL EXPORT
   ========================= */

export default BASE_URL;