import { useState, useEffect, useCallback } from "react"
import { getAlerts, ackAlert, ackAllAlerts } from "../api"

const SEV_ORDER = { critical: 0, high: 1, medium: 2, low: 3, info: 4 }

const getSeverityColor = (severity) => {
  const sev = severity?.toLowerCase() || "info"
  if (sev === "critical" || sev === "high") return { bg: "rgba(255, 0, 110, 0.2)", color: "#ff006e" }
  if (sev === "medium") return { bg: "rgba(255, 165, 0, 0.2)", color: "#ffa500" }
  if (sev === "low") return { bg: "rgba(57, 255, 20, 0.2)", color: "#39ff14" }
  return { bg: "rgba(0, 240, 255, 0.2)", color: "#00f0ff" }
}

export default function AlertsPage() {
  const [alerts,   setAlerts]   = useState([])
  const [loading,  setLoading]  = useState(true)
  const [filter,   setFilter]   = useState("unread")
  const [acking,   setAcking]   = useState(null)

  const load = useCallback(async () => {
    try {
      const data = await getAlerts(50)
      setAlerts(Array.isArray(data) ? data : [])
    } catch {}
    setLoading(false)
  }, [])

  useEffect(() => { load(); const t = setInterval(load, 15000); return () => clearInterval(t) }, [load])

  const handleAck = async (id) => {
    setAcking(id)
    await ackAlert(id).catch(() => {})
    setAlerts(prev => prev.map(a => a.id === id ? { ...a, acknowledged: true } : a))
    setAcking(null)
  }

  const handleAckAll = async () => {
    await ackAllAlerts().catch(() => {})
    setAlerts(prev => prev.map(a => ({ ...a, acknowledged: true })))
  }

  const displayed = alerts
    .filter(a => filter === "all" || !a.acknowledged)
    .sort((a, b) => (SEV_ORDER[a.severity] ?? 5) - (SEV_ORDER[b.severity] ?? 5))

  const unread = alerts.filter(a => !a.acknowledged).length

  return (
    <div className="dashboard-container">
      {/* Header */}
      <div className="dashboard-header">
        <div>
          <h1 className="dashboard-title">Alert Feed</h1>
          <p className="dashboard-subtitle">{unread} unread · {alerts.length} total</p>
        </div>
        <div style={{ display: "flex", gap: "12px" }}>
          {["unread", "all"].map(f => (
            <button 
              key={f} 
              className="cyber-button"
              onClick={() => setFilter(f)}
              style={{
                background: filter === f ? "rgba(255, 0, 110, 0.2)" : "transparent",
                borderColor: filter === f ? "#ff006e" : "rgba(255, 0, 110, 0.3)",
                color: filter === f ? "#ff006e" : "var(--text-secondary)",
                padding: "8px 16px"
              }}
            >
              {f.toUpperCase()}
            </button>
          ))}
          {unread > 0 && (
            <button 
              className="cyber-button"
              onClick={handleAckAll}
              style={{
                color: "#39ff14",
                borderColor: "rgba(57, 255, 20, 0.4)",
                padding: "8px 16px"
              }}
            >
              ACK ALL
            </button>
          )}
        </div>
      </div>

      {/* Stats */}
      <div className="stats-grid">
        <div className="stat-card magenta">
          <div className="stat-label">Unread</div>
          <div className={`stat-value ${unread > 0 ? 'magenta' : 'lime'}`}>{unread}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Total</div>
          <div className="stat-value">{alerts.length}</div>
        </div>
        <div className="stat-card lime">
          <div className="stat-label">Acknowledged</div>
          <div className="stat-value lime">{alerts.filter(a => a.acknowledged).length}</div>
        </div>
      </div>

      {/* Alerts List */}
      {loading ? (
        <div className="dashboard-card">
          <div style={{ textAlign: "center", padding: "32px", color: "var(--text-tertiary)" }}>
            Loading alerts...
          </div>
        </div>
      ) : displayed.length === 0 ? (
        <div className="dashboard-card">
          <div className="empty-state">
            <div className="empty-icon" style={{ color: "#39ff14", fontSize: "3rem" }}>◉</div>
            <div style={{ color: "#39ff14", fontWeight: "600", fontSize: "16px", marginBottom: "8px" }}>ALL CLEAR</div>
            <div style={{ color: "var(--text-tertiary)" }}>No {filter === "unread" ? "unread " : ""}alerts</div>
          </div>
        </div>
      ) : (
        <div className="alert-feed">
          <div className="card-header">
            <span className="card-icon">⚠️</span>
            <span className="card-title">Active Alerts</span>
            <span className="card-badge">{displayed.length}</span>
          </div>
          <div className="alerts-list">
            {displayed.map(a => {
              const sevColor = getSeverityColor(a.severity)
              return (
                <div key={a.id} className="alert-row" style={{ 
                  borderLeftColor: sevColor.color,
                  background: `${sevColor.bg}`,
                  borderColor: `${sevColor.color}40`
                }}>
                  <div className="alert-severity" style={{ background: sevColor.bg, color: sevColor.color }}>
                    {(a.severity || "INFO").toUpperCase()}
                  </div>
                  <div className="alert-content">
                    <div className="alert-title">{a.message}</div>
                    <div className="alert-meta">
                      <span className="alert-rule">{a.rule_name}</span>
                      <span className="alert-time">
                        {a.timestamp ? new Date(a.timestamp).toLocaleString("en-KE") : "—"}
                      </span>
                      {a.acknowledged && (
                        <span style={{ color: "#39ff14", fontWeight: "600", marginLeft: "auto" }}>
                          ✓ ACK
                        </span>
                      )}
                    </div>
                  </div>
                  {!a.acknowledged && (
                    <button
                      className="cyber-button"
                      onClick={() => handleAck(a.id)}
                      disabled={acking === a.id}
                      style={{ 
                        padding: "4px 12px", 
                        fontSize: "11px",
                        whiteSpace: "nowrap"
                      }}
                    >
                      {acking === a.id ? "..." : "Ack"}
                    </button>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
