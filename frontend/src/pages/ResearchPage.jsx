import { useState, useEffect, useRef, useCallback } from "react"
import BASE_URL from "../api"

const R_BASE = BASE_URL + "/api/research"

async function rApi(method, path, body = null, timeout = 90000) {
  const ctrl = new AbortController()
  const t    = setTimeout(() => ctrl.abort(), timeout)
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
    .replace(/^## (.+)$/gm,  "<h2>$1</h2>")
    .replace(/^# (.+)$/gm,   "<h1>$1</h1>")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g,     "<em>$1</em>")
    .replace(/`(.+?)`/g,       "<code>$1</code>")
    .replace(/^> (.+)$/gm,     "<blockquote>$1</blockquote>")
    .replace(/^[-*] (.+)$/gm,  "<li>$1</li>")
    .replace(/(<li>.*<\/li>)/gs,"<ul>$1</ul>")
    .replace(/\n\n/g, "</p><p>")
    .replace(/^(?!<[hpulbi])(.+)$/gm, "<p>$1</p>")
    .replace(/<p><\/p>/g, "")
}

const MODES = [
  { id: "research",     icon: "⊕", label: "Research",     desc: "Web search + synthesis" },
  { id: "essay",        icon: "✎", label: "Essay",         desc: "Long-form writing" },
  { id: "presentation", icon: "◈", label: "Presentation",  desc: "Slide outline" },
]

const SUGGESTIONS = [
  "Latest AI breakthroughs in 2025",
  "How does Retrieval-Augmented Generation work?",
  "Kenya's startup ecosystem overview",
  "Best practices for REST API design",
  "Climate change impact on East Africa",
  "How to build a personal brand as a developer",
]

const LOAD_MESSAGES = {
  research:     ["Searching the web...", "Synthesizing sources...", "Generating insights..."],
  essay:        ["Outlining structure...", "Writing draft...", "Polishing prose..."],
  presentation: ["Planning slides...", "Writing content...", "Structuring deck..."],
}

export default function ResearchPage() {
  const [mode,         setMode]         = useState("research")
  const [query,        setQuery]        = useState("")
  const [loading,      setLoading]      = useState(false)
  const [loadStep,     setLoadStep]     = useState(0)
  const [result,       setResult]       = useState(null)
  const [history,      setHistory]      = useState([])    // past results this session
  const [toast,        setToast]        = useState(null)
  const [essayStyle,   setEssayStyle]   = useState("analytical")
  const [essayLen,     setEssayLen]     = useState("medium")
  const [presStyle,    setPresStyle]    = useState("professional")
  const [presSlides,   setPresSlides]   = useState("10")
  const [stats,        setStats]        = useState({})
  const [showHistory,  setShowHistory]  = useState(false)
  const loadInterval = useRef(null)
  const resultRef    = useRef(null)

  useEffect(() => {
    rApi("GET", "/stats").then(s => setStats(s || {})).catch(() => {})
  }, [])

  const showToast = (msg, type = "success") => {
    setToast({ msg, type })
    setTimeout(() => setToast(null), 3500)
  }

  const startLoadAnimation = (m) => {
    setLoadStep(0)
    const steps = LOAD_MESSAGES[m] || LOAD_MESSAGES.research
    let i = 0
    loadInterval.current = setInterval(() => {
      i = (i + 1) % steps.length
      setLoadStep(i)
    }, 2200)
  }

  const stopLoadAnimation = () => {
    if (loadInterval.current) { clearInterval(loadInterval.current); loadInterval.current = null }
  }

  const run = async () => {
    if (!query.trim() || loading) return
    setLoading(true)
    setResult(null)
    startLoadAnimation(mode)

    try {
      let res, content

      if (mode === "research") {
        res     = await rApi("POST", "/research", { query })
        content = res.result || res.content || res.text || JSON.stringify(res)
      } else if (mode === "essay") {
        res     = await rApi("POST", "/essay", { topic: query, style: essayStyle, length: essayLen })
        content = res.essay || res.result || res.content || res.text || JSON.stringify(res)
      } else {
        res     = await rApi("POST", "/presentation", { topic: query, style: presStyle, slides: parseInt(presSlides) })
        content = res.presentation || res.outline || res.result || res.content || JSON.stringify(res)
      }

      if (!content || content === "{}") throw new Error("Empty response from API")

      const entry = { id: Date.now(), mode, query, content, ts: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) }
      setResult(entry)
      setHistory(prev => [entry, ...prev.slice(0, 9)])
      showToast(mode === "research" ? "Research complete" : mode === "essay" ? "Essay ready" : "Presentation ready")

      // Scroll to result
      setTimeout(() => resultRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 100)

    } catch (e) {
      showToast(e.name === "AbortError" ? "Request timed out (90s)" : e.message || "Request failed", "error")
    } finally {
      setLoading(false)
      stopLoadAnimation()
    }
  }

  const loadHistoryItem = (item) => {
    setResult(item)
    setShowHistory(false)
    setTimeout(() => resultRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 100)
  }

  const currentMode = MODES.find(m => m.id === mode)
  const loadSteps   = LOAD_MESSAGES[mode] || LOAD_MESSAGES.research

  return (
    <div className="page" style={{ maxWidth: 800, margin: "0 auto" }}>

      {/* ── Header ── */}
      <div className="page-header">
        <div>
          <div className="page-title">RESEARCH LAB</div>
          <div className="page-subtitle">RESEARCH · ESSAYS · PRESENTATIONS</div>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          {history.length > 0 && (
            <button className="btn btn-sm" onClick={() => setShowHistory(v => !v)}>
              🕐 HISTORY ({history.length})
            </button>
          )}
          {loading && <div className="spinner" />}
        </div>
      </div>

      {/* ── Stats row ── */}
      <div className="metrics-row" style={{ marginBottom: 16 }}>
        {[
          { label: "SESSIONS",  value: stats.total_sessions  || 0, color: "var(--green)" },
          { label: "DOCUMENTS", value: stats.total_documents || 0, color: "#4488ff" },
          { label: "STORAGE",   value: stats.storage_used_mb ? stats.storage_used_mb + "MB" : "0MB", color: "#ff9900", small: true },
        ].map(s => (
          <div className="metric-card" key={s.label}>
            <div className="metric-label">{s.label}</div>
            <div className="metric-value" style={{ color: s.color, fontSize: s.small ? 16 : undefined }}>{s.value}</div>
          </div>
        ))}
      </div>

      {/* ── History panel ── */}
      {showHistory && history.length > 0 && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="card-header">
            <span className="card-title">SESSION HISTORY</span>
            <button className="btn btn-sm" onClick={() => setShowHistory(false)}>✕</button>
          </div>
          <div style={{ maxHeight: 240, overflowY: "auto" }}>
            {history.map(item => (
              <div
                key={item.id}
                onClick={() => loadHistoryItem(item)}
                style={{
                  padding: "10px 16px", borderBottom: "1px solid var(--border)",
                  cursor: "pointer", transition: "background 0.15s",
                  display: "flex", alignItems: "center", gap: 10,
                }}
                onMouseEnter={e => e.currentTarget.style.background = "var(--bg-2)"}
                onMouseLeave={e => e.currentTarget.style.background = "transparent"}
              >
                <span style={{ fontSize: 16 }}>{MODES.find(m => m.id === item.mode)?.icon || "⊕"}</span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 12, color: "var(--text-1)", fontWeight: 600,
                    whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                    {item.query}
                  </div>
                  <div className="mono text-xs" style={{ color: "var(--text-4)", marginTop: 2 }}>
                    {item.mode.toUpperCase()} · {item.ts}
                  </div>
                </div>
                <span style={{ color: "var(--text-4)", fontSize: 12 }}>→</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Mode selector ── */}
      <div style={{ display: "flex", gap: 8, marginBottom: 14, flexWrap: "wrap" }}>
        {MODES.map(m => (
          <button
            key={m.id}
            onClick={() => { setMode(m.id); setResult(null) }}
            disabled={loading}
            style={{
              flex: "1 1 0", minWidth: 100,
              display: "flex", flexDirection: "column", alignItems: "center",
              gap: 4, padding: "12px 8px",
              background: mode === m.id ? "rgba(0,255,157,0.08)" : "var(--bg-card)",
              border: `1px solid ${mode === m.id ? "var(--green)" : "var(--border)"}`,
              borderRadius: "var(--radius-lg)", cursor: "pointer", transition: "all 0.15s",
            }}
          >
            <span style={{ fontSize: 20, color: mode === m.id ? "var(--green)" : "var(--text-3)" }}>{m.icon}</span>
            <span className="mono" style={{ fontSize: 10, fontWeight: 700, letterSpacing: 1,
              color: mode === m.id ? "var(--green)" : "var(--text-3)" }}>{m.label.toUpperCase()}</span>
            <span style={{ fontSize: 10, color: "var(--text-5)", letterSpacing: 0.5 }}>{m.desc}</span>
          </button>
        ))}
      </div>

      {/* ── Main input card ── */}
      <div className="card" style={{ border: loading ? "1px solid rgba(0,255,157,0.3)" : undefined }}>
        <div className="card-header">
          <span className="card-title">{currentMode?.icon} {mode.toUpperCase()} QUERY</span>
          {result && (
            <button className="btn btn-sm" onClick={() => setResult(null)} style={{ color: "var(--text-4)" }}>
              ✕ CLEAR
            </button>
          )}
        </div>
        <div className="card-body" style={{ display: "flex", flexDirection: "column", gap: 12 }}>

          {/* Query textarea */}
          <textarea
            className="textarea"
            placeholder={
              mode === "research"     ? "What do you want to research? Be specific for better results." :
              mode === "essay"        ? "What topic should the essay cover?" :
                                        "What should the presentation be about?"
            }
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={e => {
              if (e.key === "Enter" && !e.shiftKey && window.innerWidth >= 768) {
                e.preventDefault(); run();
              }
            }}
            disabled={loading}
            style={{ minHeight: 80, resize: "none", fontSize: 14, lineHeight: 1.6 }}
          />

          {/* Suggestions (only when empty) */}
          {!query && !loading && (
            <div>
              <div className="mono text-xs" style={{ color: "var(--text-5)", letterSpacing: 1, marginBottom: 6 }}>
                SUGGESTIONS
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                {SUGGESTIONS.map(s => (
                  <button
                    key={s}
                    onClick={() => setQuery(s)}
                    style={{
                      background: "var(--bg-2)", border: "1px solid var(--border-2)",
                      borderRadius: 16, color: "var(--text-3)", fontFamily: "var(--sans)",
                      fontSize: 11, padding: "4px 10px", cursor: "pointer",
                      transition: "all 0.15s", whiteSpace: "nowrap",
                    }}
                    onMouseEnter={e => { e.currentTarget.style.borderColor = "var(--text-4)"; e.currentTarget.style.color = "var(--text-2)"; }}
                    onMouseLeave={e => { e.currentTarget.style.borderColor = "var(--border-2)"; e.currentTarget.style.color = "var(--text-3)"; }}
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Mode-specific options */}
          {mode === "essay" && (
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <div style={{ flex: 1, minWidth: 140 }}>
                <div className="mono text-xs" style={{ color: "var(--text-4)", marginBottom: 4 }}>STYLE</div>
                <select className="select" value={essayStyle} onChange={e => setEssayStyle(e.target.value)}
                  disabled={loading} style={{ width: "100%" }}>
                  <option value="analytical">Analytical</option>
                  <option value="narrative">Narrative</option>
                  <option value="persuasive">Persuasive</option>
                  <option value="expository">Expository</option>
                </select>
              </div>
              <div style={{ flex: 1, minWidth: 140 }}>
                <div className="mono text-xs" style={{ color: "var(--text-4)", marginBottom: 4 }}>LENGTH</div>
                <select className="select" value={essayLen} onChange={e => setEssayLen(e.target.value)}
                  disabled={loading} style={{ width: "100%" }}>
                  <option value="short">Short (~500 words)</option>
                  <option value="medium">Medium (~1000 words)</option>
                  <option value="long">Long (~2000 words)</option>
                </select>
              </div>
            </div>
          )}

          {mode === "presentation" && (
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <div style={{ flex: 1, minWidth: 140 }}>
                <div className="mono text-xs" style={{ color: "var(--text-4)", marginBottom: 4 }}>STYLE</div>
                <select className="select" value={presStyle} onChange={e => setPresStyle(e.target.value)}
                  disabled={loading} style={{ width: "100%" }}>
                  <option value="professional">Professional</option>
                  <option value="academic">Academic</option>
                  <option value="pitch">Pitch Deck</option>
                  <option value="tutorial">Tutorial</option>
                </select>
              </div>
              <div style={{ flex: 1, minWidth: 140 }}>
                <div className="mono text-xs" style={{ color: "var(--text-4)", marginBottom: 4 }}>SLIDES</div>
                <select className="select" value={presSlides} onChange={e => setPresSlides(e.target.value)}
                  disabled={loading} style={{ width: "100%" }}>
                  <option value="5">5 slides</option>
                  <option value="10">10 slides</option>
                  <option value="15">15 slides</option>
                  <option value="20">20 slides</option>
                </select>
              </div>
            </div>
          )}

          {/* Run button */}
          <button
            className="btn btn-green"
            onClick={run}
            disabled={loading || !query.trim()}
            style={{ width: "100%", justifyContent: "center", padding: "12px", fontSize: 12, letterSpacing: 2 }}
          >
            {loading
              ? <><div className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }} />
                  {loadSteps[loadStep]}...</>
              : mode === "research"     ? "⊕ RUN RESEARCH"
              : mode === "essay"        ? "✎ GENERATE ESSAY"
                                        : "◈ BUILD PRESENTATION"}
          </button>
        </div>
      </div>

      {/* ── Loading progress ── */}
      {loading && (
        <div style={{
          background: "rgba(0,255,157,0.04)", border: "1px solid rgba(0,255,157,0.15)",
          borderRadius: "var(--radius-lg)", padding: "16px 20px", marginBottom: 14,
          display: "flex", alignItems: "center", gap: 16,
        }}>
          <div style={{ position: "relative", width: 36, height: 36, flexShrink: 0 }}>
            <div className="spinner" style={{ width: 36, height: 36, borderWidth: 3, position: "absolute" }} />
            <span style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center",
              justifyContent: "center", fontSize: 14 }}>{currentMode?.icon}</span>
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="mono" style={{ fontSize: 11, color: "var(--green)", letterSpacing: 2, marginBottom: 6 }}>
              {loadSteps[loadStep].toUpperCase()}
            </div>
            {/* Progress dots */}
            <div style={{ display: "flex", gap: 4 }}>
              {loadSteps.map((_, i) => (
                <div key={i} style={{
                  width: 6, height: 6, borderRadius: "50%",
                  background: i <= loadStep ? "var(--green)" : "var(--border-2)",
                  transition: "background 0.3s",
                }} />
              ))}
            </div>
          </div>
          <div style={{ fontSize: 11, color: "var(--text-4)", textAlign: "right", flexShrink: 0 }}>
            <div className="mono" style={{ color: "var(--text-5)", fontSize: 10 }}>MAX WAIT</div>
            <div className="mono" style={{ color: "var(--orange)" }}>90s</div>
          </div>
        </div>
      )}

      {/* ── Result ── */}
      {result && !loading && (
        <div className="card" ref={resultRef} style={{ border: "1px solid rgba(0,255,157,0.2)" }}>
          <div className="card-header">
            <span className="card-title">
              {MODES.find(m => m.id === result.mode)?.icon} {result.mode.toUpperCase()} RESULT
            </span>
            <div style={{ display: "flex", gap: 6 }}>
              <button
                className="btn btn-sm"
                onClick={() => { navigator.clipboard.writeText(result.content); showToast("Copied to clipboard") }}
              >
                ⎘ COPY
              </button>
              <button className="btn btn-sm" onClick={() => {
                const blob = new Blob([result.content], { type: "text/plain" })
                const a    = Object.assign(document.createElement("a"), {
                  href: URL.createObjectURL(blob),
                  download: `ORA-${result.mode}-${Date.now()}.txt`,
                })
                a.click()
              }}>
                ↓ SAVE
              </button>
              <button className="btn btn-sm btn-red" onClick={() => setResult(null)}>✕</button>
            </div>
          </div>
          <div className="card-body">
            <div className="mono text-xs" style={{ color: "var(--text-4)", marginBottom: 12, letterSpacing: 1,
              borderLeft: "2px solid var(--green)", paddingLeft: 8 }}>
              {result.query}
            </div>
            <div
              className="result-content"
              style={{ maxHeight: "none" }} // full height on result page
              dangerouslySetInnerHTML={{ __html: renderMd(result.content) }}
            />
            <div style={{ marginTop: 14, paddingTop: 12, borderTop: "1px solid var(--border)",
              display: "flex", gap: 8, flexWrap: "wrap" }}>
              <button className="btn btn-sm" onClick={() => { setQuery(result.query); setResult(null) }}>
                ↺ REFINE QUERY
              </button>
              {result.mode === "research" && (
                <button className="btn btn-sm" onClick={() => {
                  setQuery(result.query); setMode("essay"); setResult(null);
                }}>
                  ✎ TURN INTO ESSAY
                </button>
              )}
              {result.mode === "research" && (
                <button className="btn btn-sm" onClick={() => {
                  setQuery(result.query); setMode("presentation"); setResult(null);
                }}>
                  ◈ MAKE PRESENTATION
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {toast && (
        <div className={`toast ${toast.type === "error" ? "error" : "success"}`}>
          {toast.type === "error" ? "⚠" : "✓"} {toast.msg}
        </div>
      )}
    </div>
  )
}
