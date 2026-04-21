export default function AlertsFeed({ alerts, onAck }) {
  const colors = { high: "#f87171", medium: "#fbbf24", low: "#34d399" }

  if (!alerts.length) {
    return (
      <div style={s.card}>
        <h2 style={s.title}>Alerts</h2>
        <p style={s.empty}>✅ No alerts. All clear.</p>
      </div>
    )
  }

  return (
    <div style={s.card}>
      <h2 style={s.title}>Alerts</h2>
      <div style={s.list}>
        {alerts.map(alert => (
          <div key={alert.id} style={{
            ...s.alert,
            borderLeftColor: colors[alert.severity] || "#444",
            opacity: alert.acknowledged ? 0.4 : 1
          }}>
            <div style={s.row}>
              <span style={{ color: colors[alert.severity], fontSize: "0.72rem", fontWeight: 700, textTransform: "uppercase" }}>
                {alert.severity}
              </span>
              <span style={s.time}>
                {new Date(alert.timestamp).toLocaleTimeString()}
              </span>
            </div>
            <p style={s.message}>{alert.message}</p>
            {!alert.acknowledged && (
              <button style={s.ackBtn} onClick={() => onAck(alert.id)}>
                acknowledge
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

const s = {
  card: {
    background: "#0d0d1a",
    border: "1px solid #1a1a2e",
    borderRadius: 16,
    padding: "1.5rem",
  },
  title: { color: "#7c6af7", fontSize: "1rem", fontWeight: 600, marginBottom: "1.25rem", textTransform: "uppercase", letterSpacing: 1 },
  list: { display: "flex", flexDirection: "column", gap: "0.75rem" },
  alert: { borderLeft: "3px solid", paddingLeft: "1rem", paddingTop: "0.5rem", paddingBottom: "0.5rem" },
  row: { display: "flex", justifyContent: "space-between", marginBottom: 4 },
  time: { color: "#333", fontSize: "0.72rem" },
  message: { color: "#ccc", fontSize: "0.9rem" },
  ackBtn: {
    marginTop: 6, background: "none", border: "1px solid #2a2a3e",
    color: "#555", borderRadius: 4, padding: "2px 8px",
    fontSize: "0.72rem", cursor: "pointer"
  },
  empty: { color: "#444" }
}