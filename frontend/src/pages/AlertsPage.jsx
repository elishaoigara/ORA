import { useState, useEffect, useCallback } from "react"
import { getAlerts, ackAlert, ackAllAlerts } from "../api"

const SEV_COLOR = {
  critical: "var(--red)",
  high:     "var(--red)",
  medium:   "var(--amber)",
  low:      "var(--green)",
  info:     "var(--blue)",
}

const SEV_ORDER = { critical: 0, high: 1, medium: 2, low: 3, info: 4 }

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
    <div className="page">
      <div className="page-header">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
          <div>
            <div className="page-title">// Alert Feed</div>
            <div className="page-sub">{unread} unread · {alerts.length} total</div>
          </div>
          <div style={{ display: "flex", gap: 6 }}>
            {["unread", "all"].map(f => (
              <button key={f} className={`btn ${filter === f ? "btn-primary" : "btn-ghost"}`} onClick={() => setFilter(f)}>
                {f.toUpperCase()}
              </button>
            ))}
            {unread > 0 && (
              <button className="btn btn-ghost" onClick={handleAckAll} style={{ color: "var(--green)" }}>
                ACK ALL
              </button>
            )}
          </div>
        </div>
      </div>

      {loading ? (
        <div className="card"><div className="empty">Loading alerts...</div></div>
      ) : displayed.length === 0 ? (
        <div className="card">
          <div className="empty">
            <div className="empty-icon" style={{ color: "var(--green)", fontSize: "2rem" }}>◉</div>
            <div className="glow-green">ALL CLEAR</div>
            <div>No {filter === "unread" ? "unread " : ""}alerts</div>
          </div>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: ".5rem" }}>
          {displayed.map(a => (
            <div key={a.id} className={`card alert-row ${a.severity}`} style={{ padding: "1rem 1.1rem" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 8 }}>
                <div style={{ flex: 1 }}>
                  <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 4 }}>
                    <span className="alert-severity" style={{ color: SEV_COLOR[a.severity] || "var(--amber)" }}>
                      {a.severity?.toUpperCase()}
                    </span>
                    <span style={{ fontFamily: "Share Tech Mono, monospace", fontSize: ".6rem", color: "var(--text3)" }}>
                      {a.rule_name}
                    </span>
                    {a.acknowledged && (
                      <span style={{ fontFamily: "Share Tech Mono, monospace", fontSize: ".58rem", color: "var(--green)", marginLeft: "auto" }}>
                        ✓ ACK
                      </span>
                    )}
                  </div>
                  <div className="alert-msg" style={{ fontSize: ".9rem" }}>{a.message}</div>
                  <div style={{ fontFamily: "Share Tech Mono, monospace", fontSize: ".6rem", color: "var(--text3)", marginTop: 5 }}>
                    {a.timestamp ? new Date(a.timestamp).toLocaleString("en-KE") : "—"}
                  </div>
                </div>
                {!a.acknowledged && (
                  <button
                    className="btn btn-ghost"
                    onClick={() => handleAck(a.id)}
                    disabled={acking === a.id}
                    style={{ flexShrink: 0, fontSize: ".65rem" }}
                  >
                    {acking === a.id ? "···" : "ACK"}
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
