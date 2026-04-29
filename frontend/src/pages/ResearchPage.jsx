import { useState, useEffect } from "react"
import BASE_URL from "../api"

const R_BASE = BASE_URL + "/api/research"

async function rApi(method, path, body = null, timeout = 90000) {
  const ctrl = new AbortController()
  const t = setTimeout(() => ctrl.abort(), timeout)
  try {
    const opts = { method, headers: { "Content-Type": "application/json" }, signal: ctrl.signal }
    if (body) opts.body = JSON.stringify(body)
    const res = await fetch(R_BASE + path, opts)
    clearTimeout(t)
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || "HTTP " + res.status)
    }
    return res.json()
  } catch (e) {
    clearTimeout(t)
    throw e
  }
}

function renderMd(text = "") {
  if (!text) return ""
  return text
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/^### (.+)$/gm, "<h3>$1</h3>")
    .replace(/^## (.+)$/gm, "<h2>$1</h2>")
    .replace(/^# (.+)$/gm, "<h1>$1</h1>")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    .replace(/`(.+?)`/g, "<code>$1</code>")
    .replace(/^> (.+)$/gm, "<blockquote>$1</blockquote>")
    .replace(/^[-*] (.+)$/gm, "<li>$1</li>")
    .replace(/(<li>.*<\/li>)/gs, "<ul>$1</ul>")
    .replace(/\n\n/g, "</p><p>")
    .replace(/^(?!<[hpulbi])(.+)$/gm, "<p>$1</p>")
    .replace(/<p><\/p>/g, "")
}

export default function ResearchPage() {
  const [mode,       setMode]       = useState("research")
  const [loading,    setLoading]    = useState(false)
  const [loadMsg,    setLoadMsg]    = useState("PROCESSING")
  const [result,     setResult]     = useState(null)
  const [stats,      setStats]      = useState({})
  const [toast,      setToast]      = useState(null)
  const [query,      setQuery]      = useState("")
  const [essayStyle, setEssayStyle] = useState("analytical")
  const [essayLen,   setEssayLen]   = useState("medium")
  const [presStyle,  setPresStyle]  = useState("professional")
  const [presSlides, setPresSlides] = useState("10")

  useEffect(() => {
    rApi("GET", "/stats").then(s => setStats(s || {})).catch(() => {})
  }, [])

  const showToast = (msg, type = "success") => {
    setToast({ msg, type })
    setTimeout(() => setToast(null), 3500)
  }

  const run = async () => {
    if (!query.trim()) return
    setLoading(true)
    setResult(null)

    const msgs = {
      research:     "RESEARCHING",
      essay:        "WRITING ESSAY",
      presentation: "BUILDING SLIDES",
    }
    setLoadMsg(msgs[mode] || "PROCESSING")

    try {
      let res, content, title = query

      if (mode === "research") {
        res = await rApi("POST", "/research", { query })
        content = res.result || res.content || res.text || JSON.stringify(res)
      } else if (mode === "essay") {
        res = await rApi("POST", "/essay", { topic: query, style: essayStyle, length: essayLen })
        content = res.essay || res.result || res.content || res.text || JSON.stringify(res)
      } else if (mode === "presentation") {
        res = await rApi("POST", "/presentation", { topic: query, style: presStyle, slides: parseInt(presSlides) })
        content = res.presentation || res.outline || res.result || res.content || JSON.stringify(res)
      }

      if (!content || content === "{}") {
        throw new Error("Empty response from API")
      }

      setResult({ type: mode, content, title })
      showToast(mode === "research" ? "Research complete" : mode === "essay" ? "Essay generated" : "Presentation ready")
    } catch (e) {
      showToast(e.message || "Request failed", "error")
    }
    setLoading(false)
  }

  const modeLabels = { research: "⊕ RESEARCH", essay: "✎ ESSAY", presentation: "◈ PRESENTATION" }
  const resultLabels = { research: "RESEARCH RESULT", essay: "GENERATED ESSAY", presentation: "PRESENTATION OUTLINE" }

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <div className="page-title">RESEARCH LAB</div>
          <div className="page-subtitle">RESEARCH · ESSAYS · PRESENTATIONS</div>
        </div>
        {loading && <div className="spinner" />}
      </div>

      <div className="metrics-row">
        <div className="metric-card">
          <div className="metric-label">SESSIONS</div>
          <div className="metric-value">{stats.total_sessions || 0}</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">DOCUMENTS</div>
          <div className="metric-value" style={{ color: "#00ff9d" }}>{stats.total_documents || 0}</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">STORAGE</div>
          <div className="metric-value" style={{ color: "#4488ff", fontSize: 14 }}>
            {stats.storage_used_mb ? stats.storage_used_mb + "MB" : "0MB"}
          </div>
        </div>
      </div>

      {/* Mode tabs */}
      <div className="card">
        <div className="card-header"><span className="card-title">MODE</span></div>
        <div className="card-body" style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {["research", "essay", "presentation"].map(m => (
            <button
              key={m}
              className={"mode-btn" + (mode === m ? " active" : "")}
              onClick={() => { setMode(m); setResult(null) }}
              disabled={loading}
            >
              {modeLabels[m]}
            </button>
          ))}
        </div>
      </div>

      {/* Input */}
      <div className="card">
        <div className="card-header">
          <span className="card-title">
            {mode === "research" ? "QUERY" : mode === "essay" ? "ESSAY TOPIC" : "PRESENTATION TOPIC"}
          </span>
        </div>
        <div className="card-body" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <textarea
            className="textarea"
            placeholder={
              mode === "research" ? "What do you want to research?" :
              mode === "essay"    ? "What topic should the essay cover?" :
                                    "What should the presentation be about?"
            }
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            disabled={loading}
            style={{ minHeight: 90, resize: "none" }}
          />

          {mode === "essay" && (
            <div style={{ display: "flex", gap: 10 }}>
              <select className="select" value={essayStyle} onChange={(e) => setEssayStyle(e.target.value)} disabled={loading} style={{ flex: 1 }}>
                <option value="analytical">ANALYTICAL</option>
                <option value="narrative">NARRATIVE</option>
                <option value="persuasive">PERSUASIVE</option>
                <option value="expository">EXPOSITORY</option>
              </select>
              <select className="select" value={essayLen} onChange={(e) => setEssayLen(e.target.value)} disabled={loading} style={{ flex: 1 }}>
                <option value="short">SHORT — 500 WORDS</option>
                <option value="medium">MEDIUM — 1000 WORDS</option>
                <option value="long">LONG — 2000 WORDS</option>
              </select>
            </div>
          )}

          {mode === "presentation" && (
            <div style={{ display: "flex", gap: 10 }}>
              <select className="select" value={presStyle} onChange={(e) => setPresStyle(e.target.value)} disabled={loading} style={{ flex: 1 }}>
                <option value="professional">PROFESSIONAL</option>
                <option value="academic">ACADEMIC</option>
                <option value="pitch">PITCH DECK</option>
                <option value="tutorial">TUTORIAL</option>
              </select>
              <select className="select" value={presSlides} onChange={(e) => setPresSlides(e.target.value)} disabled={loading} style={{ flex: 1 }}>
                <option value="5">5 SLIDES</option>
                <option value="10">10 SLIDES</option>
                <option value="15">15 SLIDES</option>
                <option value="20">20 SLIDES</option>
              </select>
            </div>
          )}

          <button
            className="btn btn-green"
            onClick={run}
            disabled={loading || !query.trim()}
          >
            {loading
              ? loadMsg + "..."
              : mode === "research"     ? "⊕ RUN RESEARCH"
              : mode === "essay"        ? "✎ GENERATE ESSAY"
                                        : "◈ BUILD PRESENTATION"}
          </button>
        </div>
      </div>

      {/* Loading state */}
      {loading && (
        <div className="card" style={{ borderColor: "rgba(0,255,157,0.2)" }}>
          <div className="card-body">
            <div style={{ display: "flex", alignItems: "center", gap: 14, padding: "8px 0" }}>
              <div className="spinner" />
              <div>
                <div className="mono text-xs" style={{ color: "var(--green)", letterSpacing: 2, marginBottom: 4 }}>{loadMsg}</div>
                <div style={{ fontSize: 12, color: "var(--text-3)" }}>
                  {mode === "research" ? "Searching the web and synthesizing results..." :
                   mode === "essay"    ? "Writing your " + essayLen + " " + essayStyle + " essay..." :
                                        "Building a " + presSlides + "-slide " + presStyle + " presentation..."}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Result */}
      {result && !loading && (
        <div className="card">
          <div className="card-header">
            <span className="card-title">{resultLabels[result.type] || "RESULT"}</span>
            <div style={{ display: "flex", gap: 8 }}>
              <button
                className="btn btn-sm"
                onClick={() => { navigator.clipboard.writeText(result.content); showToast("Copied to clipboard") }}
              >
                ⎘ COPY
              </button>
              <button className="btn btn-sm btn-red" onClick={() => setResult(null)}>
                ✕
              </button>
            </div>
          </div>
          <div className="card-body">
            <div className="mono text-xs" style={{ color: "var(--text-4)", marginBottom: 12, letterSpacing: 1 }}>
              {result.title}
            </div>
            <div
              className="result-content"
              dangerouslySetInnerHTML={{ __html: renderMd(result.content) }}
            />
          </div>
        </div>
      )}

      {toast && (
        <div className={"toast" + (toast.type === "error" ? " error" : " success")}>
          {toast.type === "error" ? "⚠" : "✓"} {toast.msg}
        </div>
      )}
    </div>
  )
}