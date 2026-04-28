import { useState, useEffect } from "react"
import BASE_URL from "../api"

const R_BASE = `${BASE_URL}/api/research`

async function rApi(method, path, body = null, timeout = 90000) {
  const ctrl = new AbortController()
  const t = setTimeout(() => ctrl.abort(), timeout)
  try {
    const opts = {
      method,
      headers: { "Content-Type": "application/json" },
      signal: ctrl.signal,
    }
    if (body) opts.body = JSON.stringify(body)
    const res = await fetch(`${R_BASE}${path}`, opts)
    clearTimeout(t)
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || `HTTP ${res.status}`)
    }
    return res.json()
  } catch (e) {
    clearTimeout(t)
    throw e
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
    .replace(/\n/g, "<br>")
}

export default function Research() {
  const [mode, setMode] = useState("research")
  const [loading, setLoading] = useState(false)
  const [loadMsg, setLoadMsg] = useState("PROCESSING...")
  const [result, setResult] = useState(null)
  const [sessions, setSessions] = useState([])
  const [stats, setStats] = useState({})
  const [toast, setToast] = useState(null)

  const [query, setQuery] = useState("")
  const [essayStyle, setEssayStyle] = useState("analytical")
  const [essayLength, setEssayLength] = useState("medium")

  useEffect(() => {
    const loadStats = async () => {
      try {
        const s = await rApi("GET", "/stats")
        setStats(s || {})
      } catch {}
    }
    loadStats()
  }, [])

  const showToast = (msg, type = "info") => {
    setToast({ msg, type })
    setTimeout(() => setToast(null), 3000)
  }

  const handleResearch = async () => {
    if (!query.trim()) return
    setLoading(true)
    setLoadMsg("Researching...")
    try {
      const res = await rApi("POST", "/research", { query })
      setResult({ type: "research", content: res.result || "", title: query })
      showToast("Research complete", "success")
    } catch (e) {
      showToast(e.message || "Research failed", "error")
    }
    setLoading(false)
  }

  const handleEssay = async () => {
    if (!query.trim()) return
    setLoading(true)
    setLoadMsg("Writing essay...")
    try {
      const res = await rApi("POST", "/essay", { 
        topic: query, 
        style: essayStyle, 
        length: essayLength 
      })
      setResult({ type: "essay", content: res.essay || "", title: query })
      showToast("Essay generated", "success")
    } catch (e) {
      showToast(e.message || "Essay generation failed", "error")
    }
    setLoading(false)
  }

  return (
    <div className="dashboard-container">
      {/* Header */}
      <div className="dashboard-header">
        <div>
          <h1 className="dashboard-title">Research Lab</h1>
          <p className="dashboard-subtitle">Advanced research & analysis workspace</p>
        </div>
      </div>

      {/* Stats */}
      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-label">Sessions</div>
          <div className="stat-value">{stats.total_sessions || 0}</div>
        </div>
        <div className="stat-card lime">
          <div className="stat-label">Documents</div>
          <div className="stat-value lime">{stats.total_documents || 0}</div>
        </div>
        <div className="stat-card magenta">
          <div className="stat-label">Storage</div>
          <div className="stat-value magenta">{stats.storage_used_mb ? `${stats.storage_used_mb}MB` : "0MB"}</div>
        </div>
      </div>

      {/* Toast */}
      {toast && (
        <div className="dashboard-card" style={{
          borderColor: toast.type === "success" ? "rgba(57, 255, 20, 0.3)" : "rgba(255, 0, 110, 0.3)",
          background: toast.type === "success" ? "rgba(57, 255, 20, 0.05)" : "rgba(255, 0, 110, 0.05)",
          marginBottom: "20px"
        }}>
          <div style={{ color: toast.type === "success" ? "#39ff14" : "#ff006e" }}>
            {toast.type === "success" ? "✓" : "⚠"} {toast.msg}
          </div>
        </div>
      )}

      {/* Mode Selector */}
      <div style={{ display: "flex", gap: "12px", marginBottom: "20px", flexWrap: "wrap" }}>
        {["research", "essay"].map(m => (
          <button
            key={m}
            className="cyber-button"
            onClick={() => setMode(m)}
            disabled={loading}
            style={{
              background: mode === m ? "rgba(0, 240, 255, 0.2)" : "transparent",
              borderColor: mode === m ? "var(--neon-cyan)" : "rgba(0, 240, 255, 0.3)",
              color: mode === m ? "var(--neon-cyan)" : "var(--text-secondary)",
              padding: "8px 16px"
            }}
          >
            {m === "research" ? "🔍 Research" : "✍️ Essay"}
          </button>
        ))}
      </div>

      {/* Input Area */}
      <div className="dashboard-card" style={{ marginBottom: "20px" }}>
        <div className="card-header">
          <span className="card-icon">{mode === "research" ? "🔍" : "✍️"}</span>
          <span className="card-title">{mode === "research" ? "Research Query" : "Essay Topic"}</span>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
          <textarea
            className="chat-textarea"
            placeholder={mode === "research" ? "Enter your research query..." : "Enter essay topic..."}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            disabled={loading}
            style={{ resize: "none", height: "100px" }}
          />

          {mode === "essay" && (
            <div style={{ display: "flex", gap: "12px" }}>
              <select
                className="chat-textarea"
                value={essayStyle}
                onChange={(e) => setEssayStyle(e.target.value)}
                disabled={loading}
                style={{ flex: 1, height: "auto" }}
              >
                <option value="analytical">Analytical</option>
                <option value="narrative">Narrative</option>
                <option value="persuasive">Persuasive</option>
              </select>
              <select
                className="chat-textarea"
                value={essayLength}
                onChange={(e) => setEssayLength(e.target.value)}
                disabled={loading}
                style={{ flex: 1, height: "auto" }}
              >
                <option value="short">Short (500 words)</option>
                <option value="medium">Medium (1000 words)</option>
                <option value="long">Long (2000 words)</option>
              </select>
            </div>
          )}

          <button
            className="cyber-button"
            onClick={mode === "research" ? handleResearch : handleEssay}
            disabled={loading || !query.trim()}
            style={{ padding: "10px 16px" }}
          >
            {loading ? `${loadMsg}...` : mode === "research" ? "🔍 Research" : "✍️ Generate Essay"}
          </button>
        </div>
      </div>

      {/* Result */}
      {result && (
        <div className="dashboard-card">
          <div className="card-header">
            <span className="card-icon">{result.type === "research" ? "📊" : "📄"}</span>
            <span className="card-title">{result.type === "research" ? "Research Result" : "Generated Essay"}</span>
          </div>
          <div style={{
            maxHeight: "600px",
            overflowY: "auto",
            padding: "16px",
            background: "rgba(0, 240, 255, 0.05)",
            borderRadius: "8px",
            border: "1px solid rgba(0, 240, 255, 0.1)",
            fontSize: "13px",
            lineHeight: 1.6,
            color: "var(--text-primary)"
          }}>
            <div dangerouslySetInnerHTML={{ __html: renderMd(result.content) }} />
          </div>
          <button
            className="cyber-button"
            onClick={() => {
              navigator.clipboard.writeText(result.content)
              showToast("Copied to clipboard", "success")
            }}
            style={{ padding: "8px 16px", marginTop: "12px" }}
          >
            📋 Copy
          </button>
        </div>
      )}

      {/* Sessions */}
      {sessions.length > 0 && (
        <div className="dashboard-card" style={{ marginTop: "20px" }}>
          <div className="card-header">
            <span className="card-icon">📋</span>
            <span className="card-title">Recent Sessions</span>
            <span className="card-badge">{sessions.length}</span>
          </div>
          <div className="task-list">
            {sessions.slice(0, 5).map((s, i) => (
              <div key={i} className="task-item">
                <div style={{ flex: 1 }}>
                  <div className="task-title">{s.title || "Untitled"}</div>
                  <div style={{ fontSize: "11px", color: "var(--text-tertiary)", marginTop: "4px", fontFamily: "'JetBrains Mono', monospace" }}>
                    {s.created_at ? new Date(s.created_at).toLocaleString("en-KE") : "—"}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
