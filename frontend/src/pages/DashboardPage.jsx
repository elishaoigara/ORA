import { useState, useEffect } from "react"

const API = "http://localhost:8000"

function StatBar({ label, value, color }) {
  return (
    <div style={{ marginBottom: "1.25rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.5rem" }}>
        <span style={{ fontSize: "0.7rem", color: "var(--muted)", letterSpacing: "0.1em" }}>{label}</span>
        <span style={{ fontSize: "0.8rem", fontWeight: 700, color: value > 80 ? "var(--accent2)" : "var(--text)" }}>{value}%</span>
      </div>
      <div style={{ height: "3px", background: "var(--border)", borderRadius: "2px" }}>
        <div style={{
          width: `${value}%`, height: "100%", borderRadius: "2px",
          background: value > 80 ? "var(--accent2)" : color,
          boxShadow: `0 0 8px ${value > 80 ? "var(--accent2)" : color}`,
          transition: "width 1s ease"
        }} />
      </div>
    </div>
  )
}

export default function DashboardPage() {
  const [status, setStatus] = useState(null)
  const [alerts, setAlerts] = useState([])
  const [tasks, setTasks] = useState([])
  const [time, setTime] = useState(new Date())

  useEffect(() => {
    const fetch_data = async () => {
      try {
        const [s, a, t] = await Promise.all([
          fetch(`${API}/api/status`).then(r => r.json()),
          fetch(`${API}/api/alerts`).then(r => r.json()),
          fetch(`${API}/api/tasks`).then(r => r.json()),
        ])
        setStatus(s)
        setAlerts(a)
        setTasks(t)
      } catch (e) {}
    }
    fetch_data()
    const iv = setInterval(fetch_data, 10000)
    const clock = setInterval(() => setTime(new Date()), 1000)
    return () => { clearInterval(iv); clearInterval(clock) }
  }, [])

  const pending = tasks.filter(t => t.status === "pending")
  const activeAlerts = alerts.filter(a => !a.acknowledged)

  return (
    <div>
      <div style={{ marginBottom: "2.5rem" }}>
        <h1 style={{ fontFamily: "Syne, sans-serif", fontSize: "2rem", fontWeight: 800, letterSpacing: "-0.02em" }}>
          Dashboard
        </h1>
        <div style={{ color: "var(--muted)", fontSize: "0.75rem", marginTop: "0.25rem", letterSpacing: "0.05em" }}>
          {time.toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long" })} — {time.toLocaleTimeString()}
        </div>
      </div>

      <div className="grid-2" style={{ marginBottom: "1.5rem" }}>
        <div className="card">
          <div className="tag">System Status</div>
          {status ? (
            <>
              <StatBar label="CPU" value={status.cpu} color="var(--accent)" />
              <StatBar label="RAM" value={status.ram} color="#43e97b" />
              <div style={{ fontSize: "0.7rem", color: "var(--muted)", marginTop: "1rem" }}>
                Disk free: {status.disk_free_gb}GB &nbsp;|&nbsp; Updated: {status.last_updated?.slice(11,19)}
              </div>
            </>
          ) : (
            <div style={{ color: "var(--muted)", fontSize: "0.8rem" }}>Connecting to ORA...</div>
          )}
        </div>

        <div className="card">
          <div className="tag">Pending Tasks</div>
          {pending.length === 0 ? (
            <div style={{ color: "var(--muted)", fontSize: "0.8rem" }}>All clear.</div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
              {pending.slice(0, 5).map(t => (
                <div key={t.id} style={{
                  fontSize: "0.8rem", padding: "0.5rem 0.75rem",
                  background: "rgba(108,99,255,0.06)",
                  border: "1px solid rgba(108,99,255,0.12)",
                  borderRadius: "8px",
                  display: "flex", justifyContent: "space-between", alignItems: "center"
                }}>
                  <span>{t.title}</span>
                  {t.due_at && <span style={{ fontSize: "0.65rem", color: "var(--accent)" }}>{t.due_at.slice(11,16)}</span>}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="grid-2">
        <div className="card">
          <div className="tag">Alerts</div>
          {activeAlerts.length === 0 ? (
            <div style={{ color: "var(--accent3)", fontSize: "0.8rem" }}>All clear.</div>
          ) : (
            activeAlerts.slice(0, 4).map(a => (
              <div key={a.id} style={{
                padding: "0.5rem 0", borderBottom: "1px solid var(--border)",
                fontSize: "0.8rem", color: a.severity === "high" ? "var(--accent2)" : "var(--text)"
              }}>
                [{a.severity}] {a.message}
              </div>
            ))
          )}
        </div>

        <div className="card">
          <div className="tag">Quick Stats</div>
          <div className="grid-2">
            {[
              { label: "Pending Tasks", value: pending.length, color: "var(--accent)" },
              { label: "Active Alerts", value: activeAlerts.length, color: "var(--accent2)" },
              { label: "Total Tasks", value: tasks.length, color: "var(--accent3)" },
              { label: "Resolved", value: alerts.filter(a => a.acknowledged).length, color: "var(--muted)" },
            ].map(({ label, value, color }) => (
              <div key={label} style={{ textAlign: "center", padding: "1rem" }}>
                <div style={{ fontSize: "2rem", fontWeight: 800, fontFamily: "Syne, sans-serif", color }}>{value}</div>
                <div style={{ fontSize: "0.65rem", color: "var(--muted)", letterSpacing: "0.1em", marginTop: "0.25rem" }}>{label}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}