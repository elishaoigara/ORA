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
      setProfile(p)
      setEvents(e)
      setPrefs(pr)
    }).catch(() => {})
  }, [])

  const impColor = (n) => n >= 8 ? "#f87171" : n >= 5 ? "#fbbf24" : "#444"

  return (
    <div style={s.page}>
      <h1 style={s.title}>🧠 ORA Memory</h1>
      <p style={s.sub}>Everything ORA knows and remembers about you</p>

      <div style={s.grid}>
        <div style={s.card}>
          <h2 style={s.cardTitle}>Profile</h2>
          {Object.entries(profile).map(([k, v]) => (
            <div key={k} style={s.row}>
              <span style={s.key}>{k}</span>
              <span style={s.val}>{v}</span>
            </div>
          ))}
        </div>

        <div style={s.card}>
          <h2 style={s.cardTitle}>Preferences</h2>
          {prefs.length === 0
            ? <p style={{ color: "#444" }}>No preferences learned yet.</p>
            : prefs.map((p, i) => (
              <div key={i} style={s.row}>
                <span style={s.key}>{p.category}/{p.key}</span>
                <span style={s.val}>{p.value}</span>
              </div>
            ))
          }
        </div>
      </div>

      <div style={{ ...s.card, marginTop: "1.5rem" }}>
        <h2 style={s.cardTitle}>Recent Events ({events.length})</h2>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {events.map((e, i) => (
            <div key={i} style={s.event}>
              <span style={{ ...s.tag, color: impColor(e.importance) }}>{e.type}</span>
              <span style={s.summary}>{e.summary}</span>
              <span style={s.time}>{e.timestamp?.slice(11, 19)}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

const s = {
  page: { padding: "2rem", maxWidth: 1000, margin: "0 auto" },
  title: { color: "#7c6af7", fontSize: "1.3rem", fontWeight: 700, marginBottom: 4 },
  sub: { color: "#333", fontSize: "0.8rem", marginBottom: "2rem" },
  grid: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1.5rem" },
  card: { background: "#0d0d1a", border: "1px solid #1a1a2e", borderRadius: 16, padding: "1.5rem" },
  cardTitle: { color: "#7c6af7", fontSize: "0.85rem", fontWeight: 600, textTransform: "uppercase", letterSpacing: 1, marginBottom: "1rem" },
  row: { display: "flex", justifyContent: "space-between", padding: "5px 0", borderBottom: "1px solid #0f0f1a" },
  key: { color: "#555", fontSize: "0.82rem" },
  val: { color: "#aaa", fontSize: "0.82rem", textAlign: "right", maxWidth: "60%" },
  event: { display: "flex", gap: 10, alignItems: "center", padding: "4px 0", borderBottom: "1px solid #0a0a14" },
  tag: { fontSize: "0.72rem", background: "#1a1a2e", padding: "2px 6px", borderRadius: 4, whiteSpace: "nowrap", minWidth: 80, textAlign: "center" },
  summary: { flex: 1, color: "#666", fontSize: "0.82rem" },
  time: { color: "#333", fontSize: "0.72rem", whiteSpace: "nowrap" }
}