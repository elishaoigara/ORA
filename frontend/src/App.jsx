import { useState, useEffect } from "react"
import StatusCard from "./components/StatusCard"
import AlertsFeed from "./components/AlertsFeed"
import MemoryPanel from "./components/MemoryPanel"

const API = "http://localhost:8000"

export default function App() {
  const [status, setStatus] = useState(null)
  const [alerts, setAlerts] = useState([])
  const [profile, setProfile] = useState({})
  const [events, setEvents] = useState([])
  const [online, setOnline] = useState(false)

  const fetchAll = async () => {
    try {
      const [s, a, p, e] = await Promise.all([
        fetch(`${API}/api/status`).then(r => r.json()),
        fetch(`${API}/api/alerts`).then(r => r.json()),
        fetch(`${API}/api/memory/profile`).then(r => r.json()),
        fetch(`${API}/api/memory/events`).then(r => r.json()),
      ])
      setStatus(s)
      setAlerts(a)
      setProfile(p)
      setEvents(e)
      setOnline(true)
    } catch {
      setOnline(false)
    }
  }

  const ackAlert = async (id) => {
    await fetch(`${API}/api/alerts/${id}/ack`, { method: "POST" })
    fetchAll()
  }

  useEffect(() => {
    fetchAll()
    const interval = setInterval(fetchAll, 10000)
    return () => clearInterval(interval)
  }, [])

  return (
    <div style={s.container}>
      <header style={s.header}>
        <div style={s.headerLeft}>
          <span style={s.logo}>👁</span>
          <div>
            <h1 style={s.name}>ORA</h1>
            <p style={s.tagline}>Oigara's Responsive Assistant</p>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div style={{ ...s.dot, background: online ? "#34d399" : "#f87171" }} />
          <span style={s.status}>{online ? "online" : "offline"}</span>
        </div>
      </header>

      <main style={s.main}>
        <div style={s.col}>
          <StatusCard status={status} />
          <AlertsFeed alerts={alerts} onAck={ackAlert} />
        </div>
        <div style={s.col}>
          <MemoryPanel profile={profile} events={events} />
        </div>
      </main>

      <footer style={s.footer}>
        ORA v0.1 · {new Date().toLocaleDateString("en-KE", { weekday: "long", day: "numeric", month: "long", year: "numeric" })}
      </footer>
    </div>
  )
}

const s = {
  container: { minHeight: "100vh", display: "flex", flexDirection: "column" },
  header: {
    display: "flex", justifyContent: "space-between", alignItems: "center",
    padding: "1.25rem 2rem",
    borderBottom: "1px solid #1a1a2e",
    background: "#0a0a14"
  },
  headerLeft: { display: "flex", alignItems: "center", gap: "1rem" },
  logo: { fontSize: "2rem" },
  name: { fontSize: "1.5rem", fontWeight: 700, color: "#7c6af7", lineHeight: 1 },
  tagline: { color: "#333", fontSize: "0.78rem", marginTop: 2 },
  dot: { width: 8, height: 8, borderRadius: "50%" },
  status: { color: "#444", fontSize: "0.8rem" },
  main: {
    display: "grid",
    gridTemplateColumns: "1fr 1fr",
    gap: "1.5rem",
    padding: "2rem",
    flex: 1,
    maxWidth: 1100,
    margin: "0 auto",
    width: "100%"
  },
  col: { display: "flex", flexDirection: "column", gap: "1.5rem" },
  footer: {
    textAlign: "center", padding: "1rem",
    color: "#222", fontSize: "0.75rem",
    borderTop: "1px solid #0f0f1a"
  }
}