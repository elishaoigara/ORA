import { useState, useEffect } from "react"
import API from "../api"

function Meter({ label, value = 0, unit = "%" }) {
  const safeValue = Number(value) || 0
  const color =
    safeValue > 80 ? "var(--red)" :
    safeValue > 60 ? "var(--amber)" :
    "var(--green)"
  return (
    <div className="meter">
      <div className="meter-header">
        <span className="meter-label">{label}</span>
        <span className="meter-value" style={{ color }}>{safeValue}{unit}</span>
      </div>
      <div className="meter-track">
        <div className="meter-bar" style={{ width: `${Math.min(safeValue, 100)}%`, background: color }} />
      </div>
    </div>
  )
}

function TheNumber({ task }) {
  if (!task || task.status === "empty") return null
  return (
    <div style={{
      gridColumn: "1 / -1",
      padding: "1rem 1.25rem",
      background: "linear-gradient(135deg, rgba(245,158,11,0.08) 0%, rgba(245,158,11,0.03) 100%)",
      border: "1px solid rgba(245,158,11,0.3)",
      borderLeft: "4px solid var(--amber)",
      borderRadius: 6,
      marginBottom: "0.5rem",
      position: "relative",
      overflow: "hidden"
    }}>
      <div style={{
        position: "absolute", top: 0, left: 0, right: 0, bottom: 0,
        background: "radial-gradient(ellipse at left, rgba(245,158,11,0.05) 0%, transparent 70%)",
        pointerEvents: "none"
      }} />
      <div style={{
        fontFamily: "Share Tech Mono, monospace", fontSize: "0.6rem",
        color: "var(--text3)", letterSpacing: 3, marginBottom: 6
      }}>
        ◈ TODAY'S NUMBER
      </div>
      <div style={{
        fontFamily: "Share Tech Mono, monospace", fontSize: "1.1rem",
        color: "var(--amber)", textShadow: "0 0 15px rgba(245,158,11,0.5)",
        marginBottom: 4, lineHeight: 1.3
      }}>
        {task.title}
      </div>
      <div style={{ display: "flex", gap: "1rem", fontSize: "0.72rem", color: "var(--text3)" }}>
        <span style={{ color: task.priority === "high" ? "var(--red)" : task.priority === "medium" ? "var(--amber)" : "var(--green)" }}>
          {task.priority?.toUpperCase()}
        </span>
        {task.overdue && <span style={{ color: "var(--red)" }}>⚠ OVERDUE</span>}
        <span>Reason: {task.reason}</span>
        <span style={{ marginLeft: "auto", fontFamily: "Share Tech Mono, monospace" }}>
          SCORE: {task.score}
        </span>
      </div>
    </div>
  )
}

function MpesaWidget({ summary }) {
  if (!summary || summary.status === "error") return null
  const today = summary.today || {}
  const avg = summary.average_daily || 0
  const ratio = avg > 0 ? (today.total / avg) : 0
  const spendColor = ratio >= 3 ? "var(--red)" : ratio >= 1.5 ? "var(--amber)" : "var(--green)"

  return (
    <div className="card">
      <div className="card-title">// M-Pesa · Financial</div>
      <div style={{ marginBottom: "0.75rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end" }}>
          <div>
            <div style={{
              fontFamily: "Share Tech Mono, monospace", fontSize: "1.4rem",
              color: spendColor, lineHeight: 1
            }}>
              Ksh {(today.total || 0).toLocaleString()}
            </div>
            <div style={{ fontSize: "0.7rem", color: "var(--text3)", marginTop: 3 }}>
              spent today · {today.transactions || 0} transactions
            </div>
          </div>
          <div style={{ textAlign: "right" }}>
            <div style={{ fontSize: "0.75rem", color: "var(--text3)" }}>Daily avg</div>
            <div style={{ fontFamily: "Share Tech Mono, monospace", fontSize: "0.9rem", color: "var(--text2)" }}>
              Ksh {avg.toLocaleString()}
            </div>
          </div>
        </div>
        <div style={{ marginTop: 8, background: "var(--border)", borderRadius: 4, height: 5 }}>
          <div style={{
            width: `${Math.min(ratio * 33, 100)}%`, height: "100%",
            background: spendColor, borderRadius: 4, transition: "width 0.6s ease"
          }} />
        </div>
        {ratio >= 3 && (
          <div style={{ fontSize: "0.7rem", color: "var(--red)", marginTop: 4 }}>
            ⚠ 3× daily average — spike detected
          </div>
        )}
      </div>
      {summary.last_7_days?.length > 0 && (
        <div>
          <div style={{ fontSize: "0.65rem", color: "var(--text3)", marginBottom: 4, fontFamily: "Share Tech Mono, monospace" }}>
            LAST 7 DAYS
          </div>
          <div style={{ display: "flex", gap: 4, alignItems: "flex-end", height: 32 }}>
            {(() => {
              const byDay = {}
              summary.last_7_days.forEach(r => { byDay[r.day] = (byDay[r.day] || 0) + r.total })
              const entries = Object.entries(byDay).slice(-7)
              const max = Math.max(...entries.map(e => e[1]), 1)
              return entries.map(([day, total]) => (
                <div key={day} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 2 }}>
                  <div style={{
                    width: "100%", background: "var(--amber)", opacity: 0.6,
                    height: `${Math.round((total / max) * 28)}px`,
                    borderRadius: "2px 2px 0 0", minHeight: 2
                  }} />
                  <div style={{ fontSize: "0.5rem", color: "var(--text3)" }}>{day.slice(8)}</div>
                </div>
              ))
            })()}
          </div>
        </div>
      )}
      {summary.last_7_days?.length === 0 && (
        <div style={{ fontSize: "0.75rem", color: "var(--text3)" }}>
          No transactions yet · Send M-Pesa SMS via Telegram: /mpesa [sms]
        </div>
      )}
    </div>
  )
}

export default function DashboardPage() {
  const [status, setStatus] = useState(null)
  const [alerts, setAlerts] = useState([])
  const [tasks, setTasks] = useState([])
  const [theNumber, setTheNumber] = useState(null)
  const [mpesa, setMpesa] = useState(null)

  const fetchJSON = async (url, fallback = null) => {
    try {
      const res = await fetch(url)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      return await res.json()
    } catch (e) {
      console.error(`[API ERROR] ${url}:`, e)
      return fallback
    }
  }

  const fetchAll = async () => {
    const [s, a, t, n, m] = await Promise.all([
      fetchJSON(`${API}/api/status`, {}),
      fetchJSON(`${API}/api/alerts`, []),
      fetchJSON(`${API}/api/tasks`, []),
      fetchJSON(`${API}/api/the-number`, null),
      fetchJSON(`${API}/api/mpesa/summary`, null),
    ])
    setStatus(s || {})
    setAlerts(Array.isArray(a) ? a : [])
    setTasks(Array.isArray(t) ? t : [])
    setTheNumber(n)
    setMpesa(m)
  }

  const ack = async (id) => {
    try {
      await fetch(`${API}/api/alerts/${id}/ack`, { method: "POST" })
      fetchAll()
    } catch (e) { console.error("ACK ERROR:", e) }
  }

  useEffect(() => {
    fetchAll()
    const i = setInterval(fetchAll, 10000)
    return () => clearInterval(i)
  }, [])

  const active = alerts.filter(a => !a.acknowledged)
  const sevColor = { high: "var(--red)", medium: "var(--amber)", low: "var(--green)" }
  const isOnline = status !== null && status.status !== "error" && typeof status.cpu === "number"

  const statusLabel = () => {
    if (status === null) return "..."
    if (status.status === "error") return "ERR"
    if (isOnline) return "ON"
    return "OFF"
  }

  const statusColor = () => {
    if (status === null) return "var(--text3)"
    if (status.status === "error") return "var(--red)"
    if (isOnline) return "var(--green)"
    return "var(--red)"
  }

  return (
    <div className="page">
      <div className="page-header">
        <div className="page-title">// System Monitor</div>
        <div className="page-sub">Real-time intelligence feed · Nairobi, KE · EAT</div>
      </div>

      <div className="grid-3" style={{ marginBottom: "1rem" }}>
        <div className="stat-box">
          <div className="stat-num">{tasks.length}</div>
          <div className="stat-label">Pending Tasks</div>
        </div>
        <div className="stat-box">
          <div className="stat-num" style={{ color: active.length > 0 ? "var(--red)" : "var(--green)" }}>
            {active.length}
          </div>
          <div className="stat-label">Active Alerts</div>
        </div>
        <div className="stat-box">
          <div className="stat-num" style={{ color: statusColor() }}>{statusLabel()}</div>
          <div className="stat-label">ORA Status</div>
        </div>
      </div>

      <TheNumber task={theNumber} />

      <div className="grid-2">

        <div className="card">
          <div className="card-title">// Hardware Status</div>
          {isOnline ? (
            <>
              <Meter label="CPU_LOAD" value={status.cpu} />
              <Meter label="RAM_USED" value={status.ram} />
              <Meter label="DISK_FREE" value={Math.round(status.disk_free_gb || 0)} unit="GB" />
              <div style={{ fontFamily: "Share Tech Mono, monospace", fontSize: "0.65rem", color: "var(--text3)", marginTop: 8 }}>
                LAST_SYNC: {status.last_updated ? new Date(status.last_updated).toLocaleTimeString() : "—"}
              </div>
            </>
          ) : (
            <div className="empty">
              <div className="empty-icon">⌛</div>
              {status?.status === "error" ? "Backend unreachable — check VITE_API_URL in Vercel" : "Connecting to ORA..."}
            </div>
          )}
        </div>

        <div className="card">
          <div className="card-title">// Alert Feed</div>
          {active.length === 0 ? (
            <div className="empty">
              <div className="empty-icon" style={{ color: "var(--green)" }}>◉</div>
              All systems nominal
            </div>
          ) : (
            active.slice(0, 4).map(a => (
              <div key={a.id} className={`alert-row ${a.severity}`}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <div className="alert-severity" style={{ color: sevColor[a.severity] }}>
                    {a.severity?.toUpperCase()}
                  </div>
                  <button className="btn btn-ghost" onClick={() => ack(a.id)}
                    style={{ fontSize: "0.6rem", padding: "2px 6px" }}>
                    ACK
                  </button>
                </div>
                <div className="alert-msg">{a.message}</div>
              </div>
            ))
          )}
        </div>

        <MpesaWidget summary={mpesa} />

        <div className="card">
          <div className="card-title">// Task Queue</div>
          {tasks.length === 0 ? (
            <div className="empty">
              <div className="empty-icon">◆</div>
              Queue empty · Add via Telegram: /task add
            </div>
          ) : (
            <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: "0.4rem" }}>
              {tasks.slice(0, 5).map(t => (
                <div key={t.id} className="task-row">
                  <div>
                    <div className="task-title">{t.title}</div>
                    {t.due_at && <div className="task-meta">DUE: {t.due_at.slice(11, 16)}</div>}
                  </div>
                  <div style={{
                    fontFamily: "Share Tech Mono, monospace", fontSize: "0.68rem",
                    color: t.priority === "high" ? "var(--red)" : t.priority === "medium" ? "var(--amber)" : "var(--green)"
                  }}>
                    {t.priority?.toUpperCase()}
                  </div>
                </div>
              ))}
              {tasks.length > 5 && (
                <div style={{ fontSize: "0.7rem", color: "var(--text3)", textAlign: "center", paddingTop: 4 }}>
                  +{tasks.length - 5} more · see Tasks tab
                </div>
              )}
            </div>
          )}
        </div>

      </div>
    </div>
  )
}