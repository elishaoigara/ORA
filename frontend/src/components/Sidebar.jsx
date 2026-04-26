import { useState, useEffect } from "react"
import { health, getAgentStatus, getAlerts } from "../api"

const nav = [
  { id: "dashboard", icon: "◈", label: "Command" },
  { id: "chat",      icon: "◎", label: "Neural Link" },
  { id: "tasks",     icon: "◆", label: "Task Queue" },
  { id: "alerts",    icon: "◉", label: "Alert Feed" },
  { id: "knowledge", icon: "▣", label: "Knowledge" },
  { id: "memory",    icon: "≡", label: "Memory Core" },
]

export default function Sidebar({ current, onNavigate }) {
  const [time,         setTime]         = useState("")
  const [date,         setDate]         = useState("")
  const [online,       setOnline]       = useState(false)
  const [unreadAlerts, setUnreadAlerts] = useState(0)
  const [agentCtx,     setAgentCtx]     = useState(null)
  const [cycleFlash,   setCycleFlash]   = useState(false)

  // Clock
  useEffect(() => {
    const tick = () => {
      const now = new Date()
      setTime(now.toLocaleTimeString("en-KE", { hour12: false }))
      setDate(now.toLocaleDateString("en-KE", { weekday: "short", day: "2-digit", month: "short" }).toUpperCase())
    }
    tick()
    const t = setInterval(tick, 1000)
    return () => clearInterval(t)
  }, [])

  // Health check
  useEffect(() => {
    const check = async () => {
      try {
        const data = await health()
        setOnline(data?.status === "ok")
      } catch {
        setOnline(false)
      }
    }
    check()
    const t = setInterval(check, 15000)
    return () => clearInterval(t)
  }, [])

  // Alert badge
  useEffect(() => {
    const check = async () => {
      try {
        const data = await getAlerts(20)
        if (Array.isArray(data)) {
          setUnreadAlerts(data.filter(a => !a.acknowledged).length)
        }
      } catch {}
    }
    check()
    const t = setInterval(check, 30000)
    return () => clearInterval(t)
  }, [])

  // Agent context — shows what ORA is currently tracking
  useEffect(() => {
    const fetch_ = async () => {
      try {
        const data = await getAgentStatus()
        setAgentCtx(data)
        // Flash on new cycle
        setCycleFlash(true)
        setTimeout(() => setCycleFlash(false), 800)
      } catch {}
    }
    fetch_()
    const t = setInterval(fetch_, 30000)
    return () => clearInterval(t)
  }, [])

  return (
    <aside className="sidebar">
      {/* Logo */}
      <div className="sidebar-logo">
        <div className="ora-eye">
          <div className="ora-eye-inner" />
        </div>
        <div>
          <div className="ora-name">ORA</div>
          <div className="ora-sub">Oigara's Assistant</div>
        </div>
      </div>

      {/* Clock */}
      <div className="sidebar-clock">
        <div>{time}</div>
        <div style={{ fontSize: ".55rem", color: "var(--text3)", marginTop: 1, letterSpacing: 2 }}>{date} · EAT</div>
      </div>

      {/* Status */}
      <div className="sidebar-status">
        <div className={`status-dot ${online ? "online" : "offline"}`} />
        <span>{online ? "SYSTEMS NOMINAL" : "OFFLINE"}</span>
      </div>

      {/* Agent pulse strip */}
      {agentCtx && (
        <div className="agent-pulse" style={{ opacity: cycleFlash ? 1 : .7, transition: "opacity .3s" }}>
          <div className="agent-dot" />
          <span style={{ color: "var(--green)" }}>AGENT</span>
          <span style={{ marginLeft: "auto", color: "var(--amber)" }}>
            {agentCtx.tasks ?? 0}T · {agentCtx.overdue ?? 0}OD · {agentCtx.goals ?? 0}G
          </span>
        </div>
      )}

      {/* Nav */}
      <nav className="sidebar-nav">
        {nav.map(item => (
          <button
            key={item.id}
            className={`nav-btn ${current === item.id ? "active" : ""}`}
            onClick={() => onNavigate(item.id)}
          >
            <span className="nav-icon">{item.icon}</span>
            <span>{item.label}</span>
            {item.id === "alerts" && unreadAlerts > 0 && (
              <span className="nav-badge">{unreadAlerts}</span>
            )}
          </button>
        ))}
      </nav>

      {/* Footer */}
      <div className="sidebar-footer">
        <div>SYS v0.4 · ELI-NBO-KE</div>
        <div style={{ marginTop: 3, color: "var(--green)", opacity: .5 }}>
          {online ? "● CONNECTED" : "○ RECONNECTING"}
        </div>
      </div>
    </aside>
  )
}