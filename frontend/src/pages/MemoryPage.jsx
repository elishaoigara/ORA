import { useState, useEffect } from "react"
import { getProfile, getPreferences, getMemoryEvents, getGoals, getGoogleAuthStatus } from "../api"
import BASE_URL from "../api"

async function safe(fn, fb) {
  try { return (await fn()) ?? fb } catch { return fb }
}

const IMP_COLOR = (n) => n >= 8 ? "#ff4444" : n >= 5 ? "#ff9900" : "#4488ff"
const IMP_LABEL = (n) => n >= 8 ? "HIGH" : n >= 5 ? "MED" : "LOW"

function fmtTs(ts) {
  if (!ts) return "—"
  try { return new Date(ts).toLocaleString("en-KE", { dateStyle: "short", timeStyle: "short" }) }
  catch { return "—" }
}

export default function MemoryPage() {
  const [profile,    setProfile]    = useState({})
  const [events,     setEvents]     = useState([])
  const [prefs,      setPrefs]      = useState([])
  const [goals,      setGoals]      = useState([])
  const [googleAuth, setGoogleAuth] = useState(null)
  const [filter,     setFilter]     = useState("all")
  const [loading,    setLoading]    = useState(true)
  const [tab,        setTab]        = useState("overview")

  useEffect(() => {
    const load = async () => {
      setLoading(true)
      const [p, e, pr, g, ga] = await Promise.all([
        safe(getProfile,                {}),
        safe(() => getMemoryEvents(50), []),
        safe(getPreferences,            []),
        safe(() => getGoals("active"),  []),
        safe(getGoogleAuthStatus,       null),
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

  const eventTypes  = ["all", ...new Set(events.map(e => e.event_type || "unknown"))]
  const filtered    = filter === "all" ? events : events.filter(e => e.event_type === filter)
  const profileKeys = Object.entries(profile)

  const tabs = [
    { id: "overview",  label: "OVERVIEW" },
    { id: "events",    label: "EVENTS (" + events.length + ")" },
    { id: "goals",     label: "GOALS (" + goals.length + ")" },
    { id: "settings",  label: "SETTINGS" },
  ]

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <div className="page-title">MEMORY CORE</div>
          <div className="page-subtitle">PROFILE · PREFERENCES · EVENTS</div>
        </div>
        {loading && <div className="spinner" />}
      </div>

      <div className="metrics-row">
        <div className="metric-card">
          <div className="metric-label">EVENTS</div>
          <div className="metric-value">{events.length}</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">PREFS</div>
          <div className="metric-value" style={{ color: "#00ff9d" }}>{prefs.length}</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">GOALS</div>
          <div className="metric-value" style={{ color: "#4488ff" }}>{goals.length}</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">GOOGLE</div>
          <div className="metric-value" style={{ fontSize: 14, color: googleAuth?.authorized ? "#00ff9d" : "#ff4444" }}>
            {googleAuth?.authorized ? "LINKED" : "UNLINKED"}
          </div>
        </div>
      </div>

      <div className="filter-tabs" style={{ marginBottom: 14 }}>
        {tabs.map(t => (
          <button key={t.id} className={"filter-tab" + (tab === t.id ? " active" : "")} onClick={() => setTab(t.id)}>
            {t.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="card"><div className="card-body"><div className="empty-state"><div className="spinner" /></div></div></div>
      ) : (
        <>
          {tab === "overview" && (
            <>
              <div className="card">
                <div className="card-header">
                  <span className="card-title">PROFILE</span>
                  <span className="card-badge">{profileKeys.length} fields</span>
                </div>
                <div className="card-body">
                  {profileKeys.length === 0 ? (
                    <div className="empty-state">
                      <div className="empty-icon">◌</div>
                      <div className="empty-title">No profile data</div>
                      <div className="empty-body">Chat with ORA to build your profile</div>
                    </div>
                  ) : (
                    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: 8 }}>
                      {profileKeys.map(([k, v]) => (
                        <div key={k} style={{ background: "var(--bg-2)", border: "1px solid var(--border)", borderRadius: "var(--radius)", padding: "10px 12px" }}>
                          <div className="mono text-xs" style={{ color: "var(--text-4)", letterSpacing: 2, marginBottom: 4 }}>{k.toUpperCase()}</div>
                          <div style={{ fontSize: 13, color: "var(--text-1)", fontWeight: 500 }}>{String(v)}</div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              <div className="card">
                <div className="card-header">
                  <span className="card-title">PREFERENCES</span>
                  <span className="card-badge">{prefs.length}</span>
                </div>
                <div className="card-body">
                  {prefs.length === 0 ? (
                    <div className="empty-state">
                      <div className="empty-icon">⚙</div>
                      <div className="empty-title">No preferences yet</div>
                      <div className="empty-body">ORA learns from your interactions</div>
                    </div>
                  ) : (
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                      {prefs.map((p, i) => (
                        <div key={i} className="pref-tag">
                          <span className="pref-tag-key">{p.category}/{p.key}</span>
                          <span className="pref-tag-text">{p.value}</span>
                          {p.confidence && (
                            <span className="mono text-xs" style={{ color: "var(--text-4)" }}>{Math.round(p.confidence * 100)}%</span>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              {events.length > 0 && (
                <div className="card">
                  <div className="card-header">
                    <span className="card-title">RECENT EVENTS</span>
                    <button className="btn btn-sm" onClick={() => setTab("events")}>VIEW ALL →</button>
                  </div>
                  <div className="card-body" style={{ padding: 0 }}>
                    {events.slice(0, 5).map((ev, i) => (
                      <div key={i} className="mem-event-row" style={{ padding: "10px 14px" }}>
                        <div className="mem-event-type">{(ev.event_type || "UNKNOWN").toUpperCase()}</div>
                        <div className="mem-event-content">{ev.summary || ev.event_type}</div>
                        <div className="mem-event-ts">{fmtTs(ev.timestamp)}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}

          {tab === "events" && (
            <div className="card">
              <div className="card-header">
                <span className="card-title">MEMORY EVENTS</span>
                <span className="card-badge">{filtered.length}</span>
              </div>
              <div className="card-body">
                {eventTypes.length > 1 && (
                  <div className="filter-tabs" style={{ marginBottom: 14 }}>
                    {eventTypes.map(et => (
                      <button key={et} className={"filter-tab" + (filter === et ? " active" : "")} onClick={() => setFilter(et)}>
                        {et.toUpperCase()}
                      </button>
                    ))}
                  </div>
                )}
                {filtered.length === 0 ? (
                  <div className="empty-state"><div className="empty-icon">◌</div><div className="empty-title">No events</div></div>
                ) : (
                  <div>
                    {filtered.slice(0, 20).map((ev, i) => (
                      <div key={i} style={{ display: "flex", alignItems: "flex-start", gap: 12, padding: "10px 0", borderBottom: "1px solid var(--border)" }}>
                        <div style={{ width: 38, height: 38, borderRadius: "var(--radius)", background: "var(--bg-2)", border: "1px solid var(--border-2)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, fontFamily: "var(--mono)", fontSize: 8, color: "var(--text-4)", letterSpacing: 0.5, textAlign: "center", lineHeight: 1.2 }}>
                          {(ev.event_type || "EVT").slice(0, 4).toUpperCase()}
                        </div>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ fontSize: 13, color: "var(--text-2)", lineHeight: 1.4, marginBottom: 3 }}>{ev.summary || ev.event_type}</div>
                          <div className="mono text-xs" style={{ color: "var(--text-5)" }}>{fmtTs(ev.timestamp)}</div>
                        </div>
                        {ev.importance != null && (
                          <span style={{ background: "var(--bg-2)", border: "1px solid " + IMP_COLOR(ev.importance), color: IMP_COLOR(ev.importance), borderRadius: 4, fontFamily: "var(--mono)", fontSize: 9, fontWeight: 700, letterSpacing: 1, padding: "2px 7px", flexShrink: 0 }}>
                            {IMP_LABEL(ev.importance)}
                          </span>
                        )}
                      </div>
                    ))}
                    {filtered.length > 20 && (
                      <div className="mono text-xs text-dimmer" style={{ marginTop: 10, textAlign: "center" }}>+{filtered.length - 20} more</div>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}

          {tab === "goals" && (
            <div className="card">
              <div className="card-header">
                <span className="card-title">ACTIVE GOALS</span>
                <span className="card-badge">{goals.length}</span>
              </div>
              <div className="card-body">
                {goals.length === 0 ? (
                  <div className="empty-state">
                    <div className="empty-icon">◎</div>
                    <div className="empty-title">No active goals</div>
                    <div className="empty-body">Tell ORA what you want to achieve</div>
                  </div>
                ) : goals.map((g, i) => {
                  const pct = g.progress || 0
                  const bar = "█".repeat(Math.floor(pct / 10)) + "░".repeat(10 - Math.floor(pct / 10))
                  const overdue = g.due_at && new Date(g.due_at) < new Date()
                  return (
                    <div key={i} className="goal-row">
                      <div className="goal-text">{g.goal}</div>
                      <div className="goal-bar-row">
                        <span className="goal-bar-mono">{bar}</span>
                        <span className="goal-pct" style={overdue ? { color: "#ff4444" } : {}}>{pct}%{overdue ? " ⚠" : ""}</span>
                      </div>
                      {g.due_at && <div className="mono text-xs" style={{ color: "var(--text-5)", marginTop: 3 }}>DUE {g.due_at.slice(0, 10)}</div>}
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {tab === "settings" && (
            <div className="card">
              <div className="card-header"><span className="card-title">INTEGRATIONS</span></div>
              <div className="card-body">
                <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "12px 0" }}>
                  <div style={{ width: 8, height: 8, borderRadius: "50%", flexShrink: 0, background: googleAuth?.authorized ? "var(--green)" : "var(--red)" }} />
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 13, color: "var(--text-2)", fontWeight: 500 }}>Google Calendar</div>
                    <div className="mono text-xs" style={{ color: "var(--text-4)", marginTop: 2 }}>
                      {googleAuth?.authorized ? "CONNECTED — syncing automatically" : "NOT CONNECTED"}
                    </div>
                  </div>
                  {!googleAuth?.authorized ? (
                    <a href={BASE_URL + "/api/auth/google"} target="_blank" rel="noreferrer" className="btn btn-sm" style={{ textDecoration: "none" }}>CONNECT →</a>
                  ) : (
                    <span className="mono text-xs text-green">✓ ACTIVE1</span>
                  )}
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}