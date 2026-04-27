import { useState, useEffect, useRef } from "react"
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
  const [time, setTime] = useState("")
  const [date, setDate] = useState("")
  const [online, setOnline] = useState(false)
  const [latency, setLatency] = useState(null)

  const [unreadAlerts, setUnreadAlerts] = useState(0)
  const [agentCtx, setAgentCtx] = useState(null)
  const [cycleFlash, setCycleFlash] = useState(false)

  const pollingRef = useRef(false)

  /* ───────── CLOCK ───────── */
  useEffect(() => {
    const tick = () => {
      const now = new Date()
      setTime(now.toLocaleTimeString("en-KE", { hour12: false }))
      setDate(
        now
          .toLocaleDateString("en-KE", {
            weekday: "short",
            day: "2-digit",
            month: "short",
          })
          .toUpperCase()
      )
    }
    tick()
    const t = setInterval(tick, 1000)
    return () => clearInterval(t)
  }, [])

  /* ───────── HEALTH + LATENCY ───────── */
  useEffect(() => {
    const check = async () => {
      const start = performance.now()
      try {
        const data = await health()
        const end = performance.now()

        setOnline(data?.status === "ok")
        setLatency(Math.round(end - start))
      } catch {
        setOnline(false)
        setLatency(null)
      }
    }

    check()
    const t = setInterval(check, 15000)
    return () => clearInterval(t)
  }, [])

  /* ───────── ALERT BADGE ───────── */
  useEffect(() => {
    const check = async () => {
      if (pollingRef.current) return
      pollingRef.current = true

      try {
        const data = await getAlerts(20)
        if (Array.isArray(data)) {
          setUnreadAlerts(data.filter(a => !a.acknowledged).length)
        }
      } catch {}

      pollingRef.current = false
    }

    check()
    const t = setInterval(check, 30000)
    return () => clearInterval(t)
  }, [])

  /* ───────── AGENT CONTEXT ───────── */
  useEffect(() => {
    const fetch_ = async () => {
      try {
        const data = await getAgentStatus()
        setAgentCtx(data)

        // flash on update
        setCycleFlash(true)
        setTimeout(() => setCycleFlash(false), 600)
      } catch {}
    }

    fetch_()
    const t = setInterval(fetch_, 20000)
    return () => clearInterval(t)
  }, [])

  /* ───────── STATUS TEXT ───────── */
  const getStatusText = () => {
    if (!online) return "OFFLINE"
    if (latency > 1000) return "DEGRADED"
    if (latency > 300) return "SLOW LINK"
    return "SYSTEMS NOMINAL"
  }

  /* ───────── AGENT STATE LABEL ───────── */
  const getAgentState = () => {
    if (!agentCtx) return "IDLE"

    if (agentCtx.overdue > 0) return "INTERVENING"
    if (agentCtx.tasks > 0) return "PROCESSING"
    return "MONITORING"
  }

  return (
    <aside className="sidebar">
      {/* LOGO */}
      <div className="sidebar-logo">
        <div className="ora-eye">
          <div className="ora-eye-inner" />
        </div>
        <div>
          <div className="ora-name">ORA</div>
          <div className="ora-sub">Oigara's Assistant</div>
        </div>
      </div>

      {/* CLOCK */}
      <div className="sidebar-clock">
        <div>{time}</div>
        <div style={{
          fontSize: ".55rem",
          color: "var(--text3)",
          marginTop: 1,
          letterSpacing: 2
        }}>
          {date} · EAT
        </div>
      </div>

      {/* STATUS */}
      <div className="sidebar-status">
        <div className={`status-dot ${online ? "online" : "offline"}`} />
        <span>{getStatusText()}</span>

        {latency && (
          <span style={{
            marginLeft: "auto",
            fontSize: ".55rem",
            color: "var(--text3)"
          }}>
            {latency}ms
          </span>
        )}
      </div>

      {/* AGENT STRIP */}
      {agentCtx && (
        <div
          className="agent-pulse"
          style={{
            opacity: cycleFlash ? 1 : 0.7,
            transform: cycleFlash ? "scale(1.02)" : "scale(1)",
            transition: "all .25s ease"
          }}
        >
          <div className="agent-dot" />

          <span style={{ color: "var(--green)" }}>
            {getAgentState()}
          </span>

          <span style={{
            marginLeft: "auto",
            color: "var(--amber)"
          }}>
            {agentCtx.tasks ?? 0}T ·
            {agentCtx.overdue ?? 0}OD ·
            {agentCtx.goals ?? 0}G
          </span>
        </div>
      )}

      {/* NAV */}
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
              <span className="nav-badge">
                {unreadAlerts}
              </span>
            )}
          </button>
        ))}
      </nav>

      {/* FOOTER */}
      <div className="sidebar-footer">
        <div>SYS v0.5 · ELI-NBO-KE</div>

        <div style={{
          marginTop: 3,
          color: online ? "var(--green)" : "var(--red)",
          opacity: 0.6
        }}>
          {online ? "● LINK STABLE" : "○ RECONNECTING"}
        </div>
      </div>
    </aside>
  )
}