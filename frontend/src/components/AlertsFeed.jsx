export default function AlertsFeed({ alerts = [], onAck }) {
  if (!alerts.length) {
    return (
      <div className="card fade-in">
        <div className="card-title">ALERT FEED</div>

        <div className="empty">
          <div className="empty-icon">✓</div>
          <div>NO ACTIVE SIGNALS</div>
        </div>
      </div>
    )
  }

  return (
    <div className="card fade-in">
      <div className="card-title">ALERT FEED</div>

      {alerts.map(alert => {
        const level = mapSeverity(alert.severity)

        return (
          <div
            key={alert.id}
            className={`alert-row ${level}`}
            style={{
              opacity: alert.acknowledged ? 0.35 : 1
            }}
          >
            {/* HEADER */}
            <div style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center"
            }}>
              <div className="alert-severity">
                {level.toUpperCase()}
              </div>

              <div className="event-time">
                {formatTime(alert.timestamp)}
              </div>
            </div>

            {/* MESSAGE */}
            <div className="alert-msg">
              {alert.message}
            </div>

            {/* ACTION */}
            {!alert.acknowledged && (
              <div style={{ marginTop: "6px" }}>
                <button
                  className="btn btn-ghost"
                  onClick={() => onAck(alert.id)}
                >
                  ACKNOWLEDGE
                </button>
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

/* ───────── HELPERS ───────── */

function mapSeverity(sev) {
  if (!sev) return "low"

  const s = sev.toLowerCase()

  if (s.includes("crit")) return "critical"
  if (s.includes("high")) return "high"
  if (s.includes("med")) return "medium"
  return "low"
}

function formatTime(ts) {
  try {
    return new Date(ts).toLocaleTimeString("en-KE", {
      hour: "2-digit",
      minute: "2-digit"
    })
  } catch {
    return ""
  }
}