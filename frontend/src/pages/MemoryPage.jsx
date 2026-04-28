import { useState, useEffect } from "react"
import { getProfile, getPreferences, getMemoryEvents, getGoals, getGoogleAuthStatus } from "../api"
import BASE from "../api"

const getImportanceColor = (n) => {
  if (n >= 8) return { bg: "rgba(255, 0, 110, 0.2)", color: "#ff006e" }
  if (n >= 5) return { bg: "rgba(255, 165, 0, 0.2)", color: "#ffa500" }
  return { bg: "rgba(0, 240, 255, 0.2)", color: "#00f0ff" }
}

const getImportanceLabel = (n) => n >= 8 ? "HIGH" : n >= 5 ? "MED" : "LOW"

async function safeFetch(fn, fallback) {
  try { return await fn() ?? fallback }
  catch { return fallback }
}

export default function MemoryPage() {
  const [profile,    setProfile]    = useState({})
  const [events,     setEvents]     = useState([])
  const [prefs,      setPrefs]      = useState([])
  const [goals,      setGoals]      = useState([])
  const [googleAuth, setGoogleAuth] = useState(null)
  const [filter,     setFilter]     = useState("all")
  const [loading,    setLoading]    = useState(true)

  useEffect(() => {
    const load = async () => {
      setLoading(true)
      const [p, e, pr, g, ga] = await Promise.all([
        safeFetch(getProfile,                     {}),
        safeFetch(() => getMemoryEvents(30),      []),
        safeFetch(getPreferences,                 []),
        safeFetch(() => getGoals("active"),       []),
        safeFetch(getGoogleAuthStatus,            null),
      ])
      setProfile(typeof p === "object" && !Array.isArray(p) ? p : {})
      setEvents(Array.isArray(e) ? e : [])
      setPrefs(Array.isArray(pr) ? pr : [])
      setGoals(Array.isArray(g) ? g : [])
      setGoogleAuth(ga)
      setLoading(false)
    }
    load()
  }, [])

  const eventTypes = ["all", ...new Set(events.map(e => e.event_type || "unknown"))]
  const filtered   = filter === "all" ? events : events.filter(e => e.event_type === filter)

  return (
    <div className="dashboard-container">
      {/* Header */}
      <div className="dashboard-header">
        <div>
          <h1 className="dashboard-title">Memory Core</h1>
          <p className="dashboard-subtitle">Profile · preferences · events · integrations</p>
        </div>
      </div>

      {/* Stats */}
      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-label">Events</div>
          <div className="stat-value">{events.length}</div>
        </div>
        <div className="stat-card lime">
          <div className="stat-label">Preferences</div>
          <div className="stat-value lime">{prefs.length}</div>
        </div>
        <div className="stat-card magenta">
          <div className="stat-label">Goals</div>
          <div className="stat-value magenta">{goals.length}</div>
        </div>
      </div>

      {loading ? (
        <div className="dashboard-card">
          <div style={{ textAlign: "center", padding: "32px", color: "var(--text-tertiary)", fontFamily: "'JetBrains Mono', monospace" }}>
            Loading memory...
          </div>
        </div>
      ) : (
        <>
          {/* Integration Status */}
          <div className="dashboard-card" style={{ marginBottom: "20px" }}>
            <div className="card-header">
              <span className="card-icon">🔗</span>
              <span className="card-title">Integration Status</span>
            </div>
            <div style={{ display: "flex", gap: "16px", flexWrap: "wrap" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <div style={{
                  width: 8, height: 8, borderRadius: "50%",
                  background: googleAuth?.authorized ? "#39ff14" : "#ff006e",
                  boxShadow: `0 0 8px ${googleAuth?.authorized ? "#39ff14" : "#ff006e"}`,
                }} />
                <span style={{ fontSize: "13px", color: "var(--text-secondary)" }}>Google Calendar</span>
                <span style={{ fontSize: "11px", color: "var(--text-tertiary)" }}>
                  {googleAuth?.authorized ? "✓ Connected" : "Not connected"}
                </span>
                {!googleAuth?.authorized && (
                  <a
                    href={`${BASE}/api/auth/google`}
                    target="_blank"
                    rel="noreferrer"
                    style={{ fontSize: "11px", color: "var(--neon-cyan)", textDecoration: "none", marginLeft: "8px" }}
                  >
                    Connect →
                  </a>
                )}
              </div>
            </div>
          </div>

          {/* Profile & Preferences */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(350px, 1fr))", gap: "20px", marginBottom: "20px" }}>
            {/* Profile */}
            <div className="dashboard-card">
              <div className="card-header">
                <span className="card-icon">👤</span>
                <span className="card-title">Profile</span>
              </div>
              {Object.keys(profile).length === 0 ? (
                <div style={{ color: "var(--text-tertiary)", fontSize: "13px" }}>No profile data</div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                  {Object.entries(profile).map(([key, val]) => (
                    <div key={key} style={{ display: "flex", justifyContent: "space-between", fontSize: "12px" }}>
                      <span style={{ color: "var(--text-tertiary)" }}>{key}</span>
                      <span style={{ color: "var(--neon-cyan)", fontWeight: "500" }}>{String(val)}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Preferences */}
            <div className="dashboard-card">
              <div className="card-header">
                <span className="card-icon">⚙️</span>
                <span className="card-title">Preferences</span>
              </div>
              {prefs.length === 0 ? (
                <div style={{ color: "var(--text-tertiary)", fontSize: "13px" }}>No preferences set</div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                  {prefs.slice(0, 5).map((pref, i) => (
                    <div key={i} style={{ fontSize: "12px" }}>
                      <div style={{ color: "var(--text-secondary)", marginBottom: "2px" }}>
                        {pref.category} / {pref.key}
                      </div>
                      <div style={{ color: "var(--neon-lime)", fontSize: "11px" }}>
                        {pref.value} {pref.confidence && `(${Math.round(pref.confidence * 100)}%)`}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Goals */}
          {goals.length > 0 && (
            <div className="dashboard-card" style={{ marginBottom: "20px" }}>
              <div className="card-header">
                <span className="card-icon">🎯</span>
                <span className="card-title">Active Goals</span>
                <span className="card-badge">{goals.length}</span>
              </div>
              <div className="goals-list">
                {goals.map((goal, i) => {
                  const progress = goal.progress || 0
                  return (
                    <div key={i} className="goal-item">
                      <div className="goal-header">
                        <div className="goal-title">{goal.goal}</div>
                        <span className="goal-progress-text">{progress}%</span>
                      </div>
                      <div className="goal-progress-bar">
                        <div className="goal-progress-fill" style={{ width: `${progress}%`, background: "#39ff14" }} />
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* Events */}
          <div className="dashboard-card">
            <div className="card-header">
              <span className="card-icon">📝</span>
              <span className="card-title">Memory Events</span>
              <span className="card-badge">{filtered.length}</span>
            </div>

            {/* Event Type Filter */}
            {eventTypes.length > 1 && (
              <div style={{ display: "flex", gap: "8px", marginBottom: "16px", flexWrap: "wrap" }}>
                {eventTypes.map(et => (
                  <button
                    key={et}
                    className="cyber-button"
                    onClick={() => setFilter(et)}
                    style={{
                      background: filter === et ? "rgba(0, 240, 255, 0.2)" : "transparent",
                      borderColor: filter === et ? "var(--neon-cyan)" : "rgba(0, 240, 255, 0.3)",
                      color: filter === et ? "var(--neon-cyan)" : "var(--text-secondary)",
                      padding: "6px 12px",
                      fontSize: "11px"
                    }}
                  >
                    {et}
                  </button>
                ))}
              </div>
            )}

            {filtered.length === 0 ? (
              <div style={{ color: "var(--text-tertiary)", fontSize: "13px", textAlign: "center", padding: "20px" }}>
                No events
              </div>
            ) : (
              <div className="task-list">
                {filtered.slice(0, 10).map((event, i) => {
                  const impColor = getImportanceColor(event.importance || 0)
                  return (
                    <div key={i} className="task-item">
                      <div style={{ flex: 1 }}>
                        <div className="task-title">{event.summary || event.event_type}</div>
                        <div style={{ fontSize: "11px", color: "var(--text-tertiary)", marginTop: "4px", fontFamily: "'JetBrains Mono', monospace" }}>
                          {event.timestamp ? new Date(event.timestamp).toLocaleString("en-KE") : "—"}
                        </div>
                      </div>
                      {event.importance && (
                        <span 
                          style={{ 
                            padding: "4px 8px",
                            borderRadius: "4px",
                            fontSize: "10px",
                            fontWeight: "600",
                            background: impColor.bg,
                            color: impColor.color,
                            border: `1px solid ${impColor.color}`
                          }}
                        >
                          {getImportanceLabel(event.importance)}
                        </span>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}
