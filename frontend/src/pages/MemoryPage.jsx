import { useState, useEffect } from "react"
import API from "../api"

const IMP_COLOR = n => n >= 8 ? "var(--red)" : n >= 5 ? "var(--amber)" : "var(--text3)"
const IMP_LABEL = n => n >= 8 ? "HIGH" : n >= 5 ? "MED" : "LOW"

export default function MemoryPage() {
  const [profile, setProfile] = useState({})
  const [events, setEvents] = useState([])
  const [prefs, setPrefs] = useState([])
  const [filter, setFilter] = useState("all")

  useEffect(() => {
    Promise.all([
      fetch(`${API}/api/memory/profile`).then(r => r.json()),
      fetch(`${API}/api/memory/events`).then(r => r.json()),
      fetch(`${API}/api/memory/preferences`).then(r => r.json()),
    ]).then(([p, e, pr]) => {
      setProfile(p)
      setEvents(e)
      setPrefs(pr)
    }).catch(() => {})
  }, [])

  const eventTypes = ["all", ...new Set(events.map(e => e.type))]
  const filtered = filter === "all" ? events : events.filter(e => e.type === filter)

  return (
    <div className="page">
      <div className="page-header">
        <div className="page-title">// Memory Core</div>
        <div className="page-sub">Everything ORA knows and remembers about you</div>
      </div>

      {/* How memory works */}
      <div className="card" style={{ marginBottom: "1rem", borderColor: "rgba(245,158,11,0.2)" }}>
        <div className="card-title">How ORA Builds Memory</div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: "0.75rem" }}>
          {[
            { icon: "💬", title: "Conversations", desc: "Every chat on Telegram or web is remembered and used as context." },
            { icon: "📁", title: "Your Files", desc: "Documents in the Knowledge Base are indexed and searchable." },
            { icon: "✅", title: "Tasks", desc: "Pending and completed tasks inform ORA's context." },
            { icon: "🔔", title: "Alerts", desc: "System events and alerts are logged with importance scores." },
          ].map(m => (
            <div key={m.title} style={{ padding: "0.6rem", background: "var(--bg2)", borderRadius: 4, border: "1px solid var(--border)" }}>
              <div style={{ fontSize: "1.1rem", marginBottom: 4 }}>{m.icon}</div>
              <div style={{ fontFamily: "Share Tech Mono, monospace", fontSize: "0.75rem", color: "var(--amber)", marginBottom: 3 }}>{m.title}</div>
              <div style={{ fontSize: "0.76rem", color: "var(--text3)", lineHeight: 1.5 }}>{m.desc}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="grid-2" style={{ marginBottom: "1rem" }}>
        {/* Identity Profile */}
        <div className="card">
          <div className="card-title">Identity Profile</div>
          <div style={{ marginBottom: 8, fontSize: "0.72rem", color: "var(--text3)", fontFamily: "Share Tech Mono, monospace" }}>
            Core facts ORA always knows about you
          </div>
          {Object.entries(profile).length === 0 ? (
            <div className="empty"><div className="empty-icon">👤</div>No profile data</div>
          ) : (
            Object.entries(profile).map(([k, v]) => (
              <div key={k} className="mem-row">
                <span className="mem-key">{k.replace(/_/g, " ")}</span>
                <span className="mem-val">{v}</span>
              </div>
            ))
          )}
          <div style={{ marginTop: 12, padding: "0.5rem 0.6rem", background: "rgba(245,158,11,0.04)", border: "1px solid var(--border)", borderRadius: 4, fontSize: "0.72rem", color: "var(--text3)", fontFamily: "Share Tech Mono, monospace" }}>
            To update your profile, tell ORA directly in chat: "Update my role to Senior Engineer"
          </div>
        </div>

        {/* Learned Preferences */}
        <div className="card">
          <div className="card-title">Learned Preferences</div>
          <div style={{ marginBottom: 8, fontSize: "0.72rem", color: "var(--text3)", fontFamily: "Share Tech Mono, monospace" }}>
            Patterns ORA has learned from your behaviour
          </div>
          {prefs.length === 0 ? (
            <div className="empty">
              <div className="empty-icon">▣</div>
              <div style={{ marginBottom: 6 }}>No preferences learned yet</div>
              <div style={{ fontSize: "0.75rem", color: "var(--text3)", lineHeight: 1.6, maxWidth: 220, margin: "0 auto" }}>
                ORA learns your preferences from conversations. The more you chat, the smarter it gets.
              </div>
            </div>
          ) : (
            prefs.map((p, i) => (
              <div key={i} className="mem-row">
                <span className="mem-key">{p.category}/{p.key}</span>
                <div style={{ textAlign: "right" }}>
                  <div className="mem-val">{p.value}</div>
                  <div style={{ fontSize: "0.65rem", color: "var(--text3)", fontFamily: "Share Tech Mono, monospace" }}>
                    confidence: {Math.round(p.confidence * 100)}%
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Event Log */}
      <div className="card">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
          <div className="card-title" style={{ marginBottom: 0 }}>
            Event Log
            <span style={{ color: "var(--text3)", fontWeight: 400, marginLeft: 8 }}>({events.length})</span>
          </div>
          <div style={{ display: "flex", gap: 6 }}>
            {eventTypes.slice(0, 5).map(t => (
              <button
                key={t}
                className="btn btn-ghost"
                onClick={() => setFilter(t)}
                style={{
                  fontSize: "0.6rem",
                  padding: "2px 8px",
                  borderColor: filter === t ? "var(--amber)" : "var(--border)",
                  color: filter === t ? "var(--amber)" : "var(--text3)",
                }}
              >
                {t.toUpperCase()}
              </button>
            ))}
          </div>
        </div>

        <div style={{ maxHeight: 400, overflowY: "auto" }}>
          {filtered.length === 0 ? (
            <div className="empty"><div className="empty-icon">▣</div>No events logged yet</div>
          ) : (
            filtered.map((e, i) => (
              <div key={i} className="event-row">
                <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 2 }}>
                  <span className="event-tag" style={{ color: IMP_COLOR(e.importance) }}>{e.type}</span>
                  <span style={{ fontFamily: "Share Tech Mono, monospace", fontSize: "0.58rem", color: IMP_COLOR(e.importance) }}>
                    {IMP_LABEL(e.importance)}
                  </span>
                </div>
                <span className="event-summary">{e.summary}</span>
                <span className="event-time">{e.timestamp?.slice(11, 19)}</span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}
