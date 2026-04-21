export default function StatusCard({ status }) {
  if (!status || status.status === "warming_up") {
    return (
      <div style={s.card}>
        <h2 style={s.title}>System Status</h2>
        <p style={s.muted}>⏳ ORA is warming up...</p>
      </div>
    )
  }

  return (
    <div style={s.card}>
      <h2 style={s.title}>System Status</h2>
      <div style={s.grid}>
        <Meter label="CPU" value={status.cpu} />
        <Meter label="RAM" value={status.ram} />
        <div style={s.stat}>
          <span style={s.label}>Disk Free</span>
          <span style={s.value}>{status.disk_free_gb} GB</span>
        </div>
      </div>
      <p style={s.updated}>
        Last updated: {new Date(status.last_updated).toLocaleTimeString()}
      </p>
    </div>
  )
}

function Meter({ label, value }) {
  const color = value > 80 ? "#f87171" : value > 60 ? "#fbbf24" : "#7c6af7"
  return (
    <div style={s.stat}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
        <span style={s.label}>{label}</span>
        <span style={{ color, fontWeight: 600 }}>{value}%</span>
      </div>
      <div style={s.track}>
        <div style={{ ...s.bar, width: `${value}%`, background: color }} />
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
  grid: { display: "flex", flexDirection: "column", gap: "1rem" },
  stat: {},
  label: { color: "#666", fontSize: "0.85rem" },
  value: { color: "#e0e0e0", fontWeight: 600 },
  track: { height: 6, background: "#1a1a2e", borderRadius: 3, overflow: "hidden" },
  bar: { height: "100%", borderRadius: 3, transition: "width 0.6s ease" },
  updated: { color: "#333", fontSize: "0.72rem", marginTop: "1rem" },
  muted: { color: "#444" }
}