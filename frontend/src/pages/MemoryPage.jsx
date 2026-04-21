import { useState, useEffect } from "react"

const API = "http://localhost:8000"

export default function MemoryPage() {
  const [profile, setProfile] = useState({})
  const [events, setEvents] = useState([])
  const [prefs, setPrefs] = useState([])

  useEffect(() => {
    Promise.all([
      fetch(`${API}/api/memory/profile`).then(r => r.json()),
      fetch(`${API}/api/memory/events`).then(r => r.json()),
      fetch(`${API}/api/memory/preferences`).then(r => r.json()),
    ]).then(([p, e, pr]) => {
      setProfile(p); setEvents(e); setPrefs(pr)
    }).catch(() => {})
  }, [])

  const impColor = n => n >= 8 ? "var(--red)" : n >= 5 ? "var(--amber)" : "var(--text3)"

  return (
    <div className="page">
      <div className="page-header">
        <div className="page-title">// Memory Core</div>
        <div className="page-sub">Everything ORA knows and remembers about Elisha</div>
      </div>

      <div className="grid-2" style={{ marginBottom: "1rem" }}>
        <div className="card">
          <div className="card-title">Identity Profile</div>
          {Object.entries(profile).map(([k, v]) => (
            <div key={k} className="mem-row">
              <span className="mem-key">{k}</span>
              <span className="mem-val">{v}</span>
            </div>
          ))}
        </div>

        <div className="card">
          <div className="card-title">Learned Preferences</div>
          {prefs.length === 0
            ? <div className="empty"><div className="empty-icon">▣</div>No preferences yet<br /><span style={{ fontSize: "0.75rem" }}>ORA learns from your conversations</span></div>
            : prefs.map((p, i) => (
              <div key={i} className="mem-row">
                <span className="mem-key">{p.category}/{p.key}</span>
                <span className="mem-val">{p.value}</span>
              </div>
            ))
          }
        </div>
      </div>

      <div className="card">
        <div className="card-title">Event Log ({events.length})</div>
        <div style={{ maxHeight: 400, overflowY: "auto" }}>
          {events.length === 0
            ? <div className="empty"><div className="empty-icon">▣</div>No events logged yet</div>
            : events.map((e, i) => (
              <div key={i} className="event-row">
                <span className="event-tag" style={{ color: impColor(e.importance) }}>{e.type}</span>
                <span className="event-summary">{e.summary}</span>
                <span className="event-time">{e.timestamp?.slice(11, 19)}</span>
              </div>
            ))
          }
        </div>
      </div>
    </div>
  )
}