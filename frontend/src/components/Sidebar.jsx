import { useState, useEffect } from "react"

const nav = [
  { id: "dashboard", icon: "◈", label: "Dashboard" },
  { id: "chat", icon: "◎", label: "Neural Link" },
  { id: "tasks", icon: "◆", label: "Tasks" },
  { id: "knowledge", icon: "◉", label: "Knowledge" },
  { id: "memory", icon: "▣", label: "Memory" },
]

export default function Sidebar({ current, onNavigate }) {
  const [time, setTime] = useState("")
  const [online, setOnline] = useState(false)

  useEffect(() => {
    const tick = () => {
      const now = new Date()
      setTime(now.toLocaleTimeString("en-KE", { hour12: false }))
    }
    tick()
    const t = setInterval(tick, 1000)
    return () => clearInterval(t)
  }, [])

  useEffect(() => {
    const check = async () => {
      try {
        await fetch("http://localhost:8000/api/health")
        setOnline(true)
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