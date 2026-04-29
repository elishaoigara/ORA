import { useState, useEffect } from "react";
import BASE_URL from "../api";

const R_BASE = `${BASE_URL}/api/research`;

async function rApi(method, path, body = null, timeout = 90000) {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), timeout);
  try {
    const opts = {
      method,
      headers: { "Content-Type": "application/json" },
      signal: ctrl.signal,
    };
    if (body) opts.body = JSON.stringify(body);
    const res = await fetch(`${R_BASE}${path}`, opts);
    clearTimeout(t);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res.json();
  } catch (e) {
    clearTimeout(t);
    throw e;
  }
}

function renderMd(text = "") {
  return text
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/^### (.+)$/gm, "<h3>$1</h3>")
    .replace(/^## (.+)$/gm, "<h2>$1</h2>")
    .replace(/^# (.+)$/gm, "<h1>$1</h1>")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    .replace(/`(.+?)`/g, "<code>$1</code>")
    .replace(/^> (.+)$/gm, "<blockquote>$1</blockquote>")
    .replace(/\n\n/g, "</p><p>")
    .replace(/\n/g, "<br>");
}

export default function ResearchPage() {
  const [mode, setMode] = useState("research");
  const [loading, setLoading] = useState(false);
  const [loadMsg, setLoadMsg] = useState("PROCESSING...");
  const [result, setResult] = useState(null);
  const [sessions, setSessions] = useState([]);
  const [stats, setStats] = useState({});
  const [toast, setToast] = useState(null);

  const [query, setQuery] = useState("");
  const [essayStyle, setEssayStyle] = useState("analytical");
  const [essayLength, setEssayLength] = useState("medium");

  useEffect(() => {
    const loadStats = async () => {
      try {
        const s = await rApi("GET", "/stats");
        setStats(s || {});
      } catch {}
    };
    loadStats();
  }, []);

  const showToast = (msg, type = "info") => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3000);
  };

  const handleResearch = async () => {
    if (!query.trim()) return;
    setLoading(true);
    setLoadMsg("RESEARCHING");
    try {
      const res = await rApi("POST", "/research", { query });
      setResult({ type: "research", content: res.result || "", title: query });
      showToast("Research complete", "success");
    } catch (e) {
      showToast(e.message || "Research failed", "error");
    }
    setLoading(false);
  };

  const handleEssay = async () => {
    if (!query.trim()) return;
    setLoading(true);
    setLoadMsg("WRITING ESSAY");
    try {
      const res = await rApi("POST", "/essay", {
        topic: query,
        style: essayStyle,
        length: essayLength,
      });
      setResult({ type: "essay", content: res.essay || "", title: query });
      showToast("Essay generated", "success");
    } catch (e) {
      showToast(e.message || "Essay generation failed", "error");
    }
    setLoading(false);
  };

  return (
    <div className="page">
      {/* Header */}
      <div className="page-header">
        <div>
          <div className="page-title">RESEARCH LAB</div>
          <div className="page-subtitle">ADVANCED RESEARCH &amp; ANALYSIS</div>
        </div>
        {loading && <div className="spinner" />}
      </div>

      {/* Stats */}
      <div className="metrics-row">
        <div className="metric-card">
          <div className="metric-label">SESSIONS</div>
          <div className="metric-value">{stats.total_sessions || 0}</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">DOCUMENTS</div>
          <div className="metric-value" style={{ color: "#00ff9d" }}>
            {stats.total_documents || 0}
          </div>
        </div>
        <div className="metric-card">
          <div className="metric-label">STORAGE</div>
          <div className="metric-value" style={{ color: "#4488ff" }}>
            {stats.storage_used_mb ? `${stats.storage_used_mb}MB` : "0MB"}
          </div>
        </div>
      </div>

      {/* Mode Selector */}
      <div className="card">
        <div className="card-header">
          <span className="card-title">MODE</span>
        </div>
        <div className="card-body" style={{ display: "flex", gap: "8px" }}>
          {["research", "essay"].map((m) => (
            <button
              key={m}
              className={`mode-btn ${mode === m ? "active" : ""}`}
              onClick={() => setMode(m)}
              disabled={loading}
            >
              {m === "research" ? "⊕ RESEARCH" : "✎ ESSAY"}
            </button>
          ))}
        </div>
      </div>

      {/* Input */}
      <div className="card">
        <div className="card-header">
          <span className="card-title">
            {mode === "research" ? "QUERY" : "TOPIC"}
          </span>
        </div>
        <div className="card-body" style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
          <textarea
            className="textarea"
            placeholder={
              mode === "research"
                ? "Enter your research query..."
                : "Enter essay topic..."
            }
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            disabled={loading}
            style={{ minHeight: "90px", resize: "none" }}
          />

          {mode === "essay" && (
            <div style={{ display: "flex", gap: "10px" }}>
              <select
                className="select"
                value={essayStyle}
                onChange={(e) => setEssayStyle(e.target.value)}
                disabled={loading}
                style={{ flex: 1 }}
              >
                <option value="analytical">ANALYTICAL</option>
                <option value="narrative">NARRATIVE</option>
                <option value="persuasive">PERSUASIVE</option>
              </select>
              <select
                className="select"
                value={essayLength}
                onChange={(e) => setEssayLength(e.target.value)}
                disabled={loading}
                style={{ flex: 1 }}
              >
                <option value="short">SHORT — 500 WORDS</option>
                <option value="medium">MEDIUM — 1000 WORDS</option>
                <option value="long">LONG — 2000 WORDS</option>
              </select>
            </div>
          )}

          <button
            className="btn btn-green"
            onClick={mode === "research" ? handleResearch : handleEssay}
            disabled={loading || !query.trim()}
          >
            {loading
              ? `${loadMsg}...`
              : mode === "research"
              ? "⊕ RUN RESEARCH"
              : "✎ GENERATE ESSAY"}
          </button>
        </div>
      </div>

      {/* Result */}
      {result && (
        <div className="card">
          <div className="card-header">
            <span className="card-title">
              {result.type === "research" ? "RESEARCH RESULT" : "GENERATED ESSAY"}
            </span>
            <button
              className="btn btn-sm"
              onClick={() => {
                navigator.clipboard.writeText(result.content);
                showToast("Copied to clipboard", "success");
              }}
            >
              ⎘ COPY
            </button>
          </div>
          <div className="card-body">
            <div
              className="result-content"
              dangerouslySetInnerHTML={{ __html: renderMd(result.content) }}
            />
          </div>
        </div>
      )}

      {/* Sessions */}
      {sessions.length > 0 && (
        <div className="card">
          <div className="card-header">
            <span className="card-title">RECENT SESSIONS</span>
            <span className="card-badge">{sessions.length}</span>
          </div>
          <div className="card-body" style={{ padding: 0 }}>
            {sessions.slice(0, 5).map((s, i) => (
              <div key={i} className="task-row" style={{ padding: "9px 14px" }}>
                <div className="task-dot" style={{ background: "#4488ff" }} />
                <span className="task-title">{s.title || "Untitled"}</span>
                <span className="task-due">
                  {s.created_at
                    ? new Date(s.created_at).toLocaleString("en-KE")
                    : "—"}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Toast */}
      {toast && (
        <div className={`toast ${toast.type === "success" ? "success" : toast.type === "error" ? "error" : ""}`}>
          {toast.type === "success" ? "✓" : "⚠"} {toast.msg}
        </div>
      )}
    </div>
  );
}