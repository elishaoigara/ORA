import { useState, useEffect } from "react"
import { getProfile, getPreferences, getMemoryEvents, getGoals, getGoogleAuthStatus } from "../api"

const IMP_COLOR = n => n >= 8 ? "var(--red)" : n >= 5 ? "var(--amber)" : "var(--text3)"
const IMP_LABEL = n => n >= 8 ? "HIGH" : n >= 5 ? "MED" : "LOW"

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
        safeFetch(getProfile,         {}),
        safeFetch(() => getMemoryEvents(30), []),
        safeFetch(getPreferences,     []),
        safeFetch(() => getGoals("active"), []),
        safeFetch(getGoogleAuthStatus, null),
      ])
      setProfile(p)
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
    <div className="page">
      <div className="page-header">
        <div className="page-title">// Memory Core</div>
        <div className="page-sub">Profile · preferences · events · integrations</div>
      </div>

      {loading ? (
        <div className="card"><div className="empty" style={{ fontFamily: "Share Tech Mono, monospace", fontSize: ".75rem" }}>Loading memory...</div></div>
      ) : (
        <>
          {/* Integrations status */}
          <div className="card" style={{ marginBottom: "1rem" }}>
            <div className="card-title">// Integration Status</div>
            <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <div style={{ width: 6, height: 6, borderRadius: "50%", background: googleAuth?.authorized ? "var(--green)" : "var(--red)", boxShadow: `0 0 6px ${googleAuth?.authorized ? "var(--green)" : "var(--red)"}` }} />
                <span style={{ fontSize: ".75rem", color: "var(--text2)" }}>Google Calendar</span>
                <span style={{ fontSize: ".65rem", color: "var(--text3)" }}>
                  {googleAuth?.authorized ? "Connected" : "Not connected"}
                </span>
                {!googleAuth?.authorized && (
                  <a href="https://ora-oovf.onrender.com/api/auth/google" target="_blank" rel="noreferrer"
                    style={{ fontSize: ".65rem", color: "var(--amber)" }}>
                    Connect →
                  </a>
                )}
              </div>
            </div>
          </div>

          {/* Goals */}
          {goals.length > 0 && (
            <div className="card" style={{ marginBottom: "1rem" }}>
              <div className="card-title">// Active Goals ({goals.length})</div>
              {goals.map((g, i) => {
                const pct     = g.progress || 0
                const overdue = g.due_at && new Date(g.due_at) < new Date()
                const color   = overdue ? "var(--red)" : pct >= 70 ? "var(--green)" : "var(--amber)"
                return (
                  <div key={i} className="goal-row">
                    <div className="goal-title">{g.goal}</div>
                    <div className="goal-bar-track">
                      <div className="goal-bar-fill" style={{ width: `${pct}%`, background: color }} />
                    </div>
                    <div className="goal-meta">
                      <span>{pct}%</span>
                      <span style={{ color: overdue ? "var(--red)" : "var(--text3)" }}>
                        {overdue ? "⚠ OVERDUE" : g.due_at ? g.due_at.slice(0, 10) : "no deadline"}
                      </span>
                    </div>
                  </div>
                )
              })}
            </div>
          )}

          {/* Profile + Prefs */}
          <div className="grid-2" style={{ marginBottom: "1rem" }}>
            <div className="card">
              <div className="card-title">Identity Profile</div>
              {Object.keys(profile).length === 0 ? (
                <div className="empty">No profile data yet</div>
              ) : (
                Object.entries(profile).map(([k, v]) => (
                  <div key={k} className="mem-row">
                    <span className="mem-key">{k.replace(/_/g, " ")}</span>
                    <span className="mem-val">{String(v)}</span>
                  </div>
                ))
              )}
            </div>

            <div className="card">
              <div className="card-title">Learned Preferences</div>
              {prefs.length === 0 ? (
                <div className="empty">No preferences learned yet</div>
              ) : (
                prefs.map((p, i) => (
                  <div key={i} className="mem-row">
                    <span className="mem-key">{p.category}/{p.key}</span>
                    <div style={{ textAlign: "right" }}>
                      <div className="mem-val">{p.value}</div>
                      <div style={{ fontSize: ".6rem", color: "var(--text3)" }}>{Math.round((p.confidence || 0) * 100)}% conf</div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Events */}
          <div className="card">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: ".75rem" }}>
              <div className="card-title" style={{ marginBottom: 0 }}>Event Log ({events.length})</div>
              <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                {eventTypes.slice(0, 6).map(t => (
                  <button key={t}
                    onClick={() => setFilter(t)}
                    style={{
                      fontSize: ".6rem", padding: "2px 7px", background: "none", cursor: "pointer", borderRadius: 3,
                      border: `1px solid ${filter === t ? "var(--amber)" : "var(--border)"}`,
                      color: filter === t ? "var(--amber)" : "var(--text3)",
                    }}>
                    {t}
                  </button>
                ))}
              </div>
            </div>
            <div style={{ maxHeight: 380, overflowY: "auto" }}>
              {filtered.length === 0 ? (
                <div className="empty">No events</div>
              ) : (
                filtered.map((e, i) => (
                  <div key={i} className="event-row fade-in">
                    <div style={{ color: IMP_COLOR(e.importance), minWidth: 72 }}>
                      <div style={{ fontSize: ".68rem", fontFamily: "Share Tech Mono, monospace" }}>{e.event_type || "event"}</div>
                      <div style={{ fontSize: ".55rem" }}>{IMP_LABEL(e.importance)}</div>
                    </div>
                    <div className="event-summary">{e.summary || "—"}</div>
                    <div className="event-time">{e.timestamp?.slice(11, 19) || "—"}</div>
                  </div>
                ))
              )}
            </div>
          </div>
        </>
      )}
    </div>
  )
}