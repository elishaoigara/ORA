export default function StatusCard({ status }) {
  if (!status || status.status === "warming_up") {
    return (
      <div className="card fade-in">
        <div className="card-title">SYSTEM STATUS</div>

        <div className="empty">
          <div className="empty-icon">⏳</div>
          <div>INITIALIZING SYSTEM...</div>
        </div>
      </div>
    )
  }

  return (
    <div className="card fade-in">
      <div className="card-title">SYSTEM STATUS</div>

      <div className="grid-2">
        <Meter label="CPU" value={status.cpu} />
        <Meter label="RAM" value={status.ram} />
      </div>

      {/* DISK */}
      <div style={{ marginTop: "0.75rem" }} className="stat-box">
        <div className="stat-num">
          {status.disk_free_gb ?? "--"}
        </div>
        <div className="stat-label">DISK FREE (GB)</div>
      </div>

      {/* UPDATED */}
      <div className="event-time" style={{ marginTop: "0.75rem" }}>
        UPDATED {formatTime(status.last_updated)}
      </div>
    </div>
  )
}

/* ───────── METER ───────── */

function Meter({ label, value = 0 }) {
  const level = getLevel(value)

  return (
    <div className="meter">
      <div className="meter-header">
        <div className="meter-label">{label}</div>
        <div className={`meter-value ${level}`}>
          {value}%
        </div>
      </div>

      <div className="meter-track">
        <div
          className="meter-bar"
          style={{
            width: `${value}%`,
            color: getColor(level),
            background: getColor(level),
          }}
        />
      </div>
    </div>
  )
}

/* ───────── HELPERS ───────── */

function getLevel(v) {
  if (v >= 85) return "glow-red"
  if (v >= 65) return "glow"
  return "glow-green"
}

function getColor(level) {
  if (level === "glow-red") return "var(--red)"
  if (level === "glow") return "var(--amber)"
  return "var(--green)"
}

function formatTime(ts) {
  try {
    return new Date(ts).toLocaleTimeString("en-KE", {
      hour: "2-digit",
      minute: "2-digit",
    })
  } catch {
    return "--:--"
  }
}