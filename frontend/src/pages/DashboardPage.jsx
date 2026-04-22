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
        <span className="meter-value" style={{ color }}>
          {safeValue}{unit}
        </span>
      </div>

      <div className="meter-track">
        <div
          className="meter-bar"
          style={{
            width: `${Math.min(safeValue, 100)}%`,
            background: color
          }}
        />
      </div>
    </div>
  )
}

export default function DashboardPage() {
  const [status, setStatus] = useState(null)
  const [alerts, setAlerts] = useState([])
  const [tasks, setTasks] = useState([])

  const fetchJSON = async (url) => {
    const res = await fetch(url)
    if (!res.ok) throw new Error(`HTTP ${res.status} → ${url}`)
    return res.json()
  }

  const fetchAll = async () => {
    try {
      const [s, a, t] = await Promise.all([
        fetchJSON(`${API}/api/status`),
        fetchJSON(`${API}/api/alerts`),
        fetchJSON(`${API}/api/tasks`)
      ])

      setStatus(s || {})
      setAlerts(Array.isArray(a) ? a : [])
      setTasks(Array.isArray(t) ? t : [])

    } catch (e) {
      console.error("🔥 API ERROR:", e)
      // Don't wipe status to "error" on network blip — keep last known state
      setStatus(prev => prev ?? { status: "error" })
      setAlerts([])
      setTasks([])
    }
  }

  const ack = async (id) => {
    try {
      await fetch(`${API}/api/alerts/${id}/ack`, { method: "POST" })
      fetchAll()
    } catch (e) {
      console.error("ACK ERROR:", e)
    }
  }

  useEffect(() => {
    fetchAll()
    const i = setInterval(fetchAll, 10000)
    return () => clearInterval(i)
  }, [])

  const active = alerts.filter(a => !a.acknowledged)

  const sevColor = {
    high: "var(--red)",
    medium: "var(--amber)",
    low: "var(--green)"
  }

  // FIX: status is "online" when we got a valid response with cpu as a number.
  // "warming_up" means backend is running but monitoring hasn't logged data yet.
  // "error" means the fetch itself failed (CORS / network / server down).
  const isOnline =
    status !== null &&
    status.status !== "warming_up" &&
    status.status !== "error" &&
    typeof status.cpu === "number"

  const statusLabel = () => {
    if (status === null) return "..."
    if (status.status === "error") return "ERR"
    if (status.status === "warming_up") return "INIT"
    if (isOnline) return "ON"
    return "OFF"
  }

  const statusColor = () => {
    if (status === null) return "var(--text3)"
    if (status.status === "error") return "var(--red)"
    if (status.status === "warming_up") return "var(--amber)"
    if (isOnline) return "var(--green)"
    return "var(--red)"
  }

  return (
    <div className="page">
      <div className="page-header">
        <div className="page-title">// System Monitor</div>
        <div className="page-sub">
          Real-time intelligence feed · Nairobi, KE
        </div>
      </div>

      {/* STATS */}
      <div className="grid-3" style={{ marginBottom: "1rem" }}>
        <div className="stat-box">
          <div className="stat-num">{tasks.length}</div>
          <div className="stat-label">Pending Tasks</div>
        </div>

        <div className="stat-box">
          <div
            className="stat-num"
            style={{
              color: active.length > 0
                ? "var(--red)"
                : "var(--green)"
            }}
          >
            {active.length}
          </div>
          <div className="stat-label">Active Alerts</div>
        </div>

        <div className="stat-box">
          <div
            className="stat-num"
            style={{ color: statusColor() }}
          >
            {statusLabel()}
          </div>
          <div className="stat-label">ORA Status</div>
        </div>
      </div>

      {/* MAIN GRID */}
      <div className="grid-2">

        {/* HARDWARE */}
        <div className="card">
          <div className="card-title">// Hardware Status</div>

          {isOnline ? (
            <>
              <Meter label="CPU_LOAD" value={status.cpu} />
              <Meter label="RAM_USED" value={status.ram} />
              <Meter
                label="DISK_FREE"
                value={Math.round(status.disk_free_gb || 0)}
                unit="GB"
              />

              <div style={{
                fontFamily: "Share Tech Mono, monospace",
                fontSize: "0.65rem",
                color: "var(--text3)",
                marginTop: 8
              }}>
                LAST_SYNC: {
                  status.last_updated
                    ? new Date(status.last_updated).toLocaleTimeString()
                    : "—"
                }
              </div>
            </>
          ) : (
            <div className="empty">
              <div className="empty-icon">⌛</div>
              {status?.status === "error"
                ? "Backend unreachable — check CORS / env vars"
                : status?.status === "warming_up"
                ? "ORA warming up... (may take 30s on free tier)"
                : "Initializing ORA system..."}
            </div>
          )}
        </div>

        {/* ALERTS */}
        <div className="card">
          <div className="card-title">// Alert Feed</div>

          {active.length === 0 ? (
            <div className="empty">
              <div className="empty-icon" style={{ color: "var(--green)" }}>
                ◉
              </div>
              All systems nominal
            </div>
          ) : (
            active.slice(0, 4).map(a => (
              <div key={a.id} className={`alert-row ${a.severity}`}>
                <div style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center"
                }}>
                  <div
                    className="alert-severity"
                    style={{ color: sevColor[a.severity] }}
                  >
                    {a.severity?.toUpperCase()}
                  </div>

                  <button
                    className="btn btn-ghost"
                    onClick={() => ack(a.id)}
                    style={{ fontSize: "0.6rem", padding: "2px 6px" }}
                  >
                    ACK
                  </button>
                </div>

                <div className="alert-msg">{a.message}</div>
              </div>
            ))
          )}
        </div>

        {/* TASKS */}
        <div className="card" style={{ gridColumn: "1 / -1" }}>
          <div className="card-title">// Task Queue</div>

          {tasks.length === 0 ? (
            <div className="empty">
              <div className="empty-icon">◆</div>
              Queue empty · Add via Telegram: /task add
            </div>
          ) : (
            <div style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
              gap: "0.5rem"
            }}>
              {tasks.slice(0, 6).map(t => (
                <div key={t.id} className="task-row">
                  <div>
                    <div className="task-title">{t.title}</div>
                    {t.due_at && (
                      <div className="task-meta">
                        DUE: {t.due_at.slice(11, 16)}
                      </div>
                    )}
                  </div>
                  <div className="task-due">[{t.id}]</div>
                </div>
              ))}
            </div>
          )}
        </div>

      </div>
    </div>
  )
}
