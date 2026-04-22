import { useState, useEffect } from "react"
import API from "../api"

const nav = [
  { id: "dashboard", icon: "◈", label: "Dashboard" },
  { id: "chat",      icon: "◎", label: "Neural Link" },
  { id: "tasks",     icon: "◆", label: "Tasks" },
  { id: "knowledge", icon: "◉", label: "Knowledge" },
  { id: "memory",    icon: "▣", label: "Memory" },
]

export default function Sidebar({ current, onNavigate }) {
  const [time, setTime] = useState("")
  const [online, setOnline] = useState(false)

  // Clock
  useEffect(() => {
    const tick = () => {
      const now = new Date()
      setTime(now.toLocaleTimeString("en-KE", { hour12: false }))
    }
    tick()
    const t = setInterval(tick, 1000)
    return () => clearInterval(t)
  }, [])

  // Health check — reads body to confirm backend is truly responding
  useEffect(() => {
    const check = async () => {
      try {
        const res = await fetch(`${API}/api/health`, { method: "GET" })
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const data = await res.json()
        // Backend returns { status: "ok" }
        setOnline(data?.status === "ok" || data?.status === "ORA online")
      } catch {
        setOnline(false)
      }
    }
    check()
    const t = setInterval(check, 10000)
    return () => clearInterval(t)
  }, [])

  return (
    <aside className="sidebar">
      <div className="sidebar-logo">
        <span className="eye">👁</span>
        <div>
          <div className="ora-name">ORA</div>
          <div className="ora-sub">Oigara's Assistant</div>
        </div>
      </div>

      <div className="sidebar-clock">{time}</div>

      <div className="sidebar-status">
        <div className={`status-dot ${online ? "online" : "offline"}`} />
        <span>{online ? "SYSTEMS NOMINAL" : "OFFLINE"}</span>
      </div>

      <nav className="sidebar-nav">
        {nav.map(item => (
          <button
            key={item.id}
            className={`nav-btn ${current === item.id ? "active" : ""}`}
            onClick={() => onNavigate(item.id)}
          >
            <span className="nav-icon">{item.icon}</span>
            <span>{item.label}</span>
          </button>
        ))}
      </nav>

      <div className="sidebar-footer">
        SYS v0.3 · ELI-NBO-KE
      </div>
    </aside>
  )
}
