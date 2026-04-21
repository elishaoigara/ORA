export default function MemoryPanel({ profile, events }) {
  return (
    <div style={s.card}>
      <h2 style={s.title}>ORA Memory</h2>

      {profile && Object.keys(profile).length > 0 && (
        <div style={s.section}>
          <h3 style={s.sub}>Profile</h3>
          {Object.entries(profile).map(([k, v]) => (
            <div key={k} style={s.row}>
              <span style={s.key}>{k}</span>
              <span style={s.val}>{v}</span>
            </div>
          ))}
        </div>
      )}

      {events && events.length > 0 && (
        <div style={s.section}>
          <h3 style={s.sub}>Recent Events</h3>
          {events.slice(0, 8).map((e, i) => (
            <div key={i} style={s.event}>
              <span style={s.tag}>{e.type}</span>
              <span style={s.summary}>{e.summary}</span>
            </div>
          ))}
        </div>
      )}
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
  section: { marginBottom: "1.25rem" },
  sub: { color: "#444", fontSize: "0.75rem", textTransform: "uppercase", letterSpacing: 1, marginBottom: "0.75rem" },
  row: { display: "flex", justifyContent: "space-between", padding: "4px 0", borderBottom: "1px solid #0f0f1a" },
  key: { color: "#555", fontSize: "0.82rem" },
  val: { color: "#aaa", fontSize: "0.82rem", textAlign: "right", maxWidth: "60%" },
  event: { display: "flex", gap: "0.5rem", alignItems: "flex-start", padding: "4px 0" },
  tag: { color: "#7c6af7", fontSize: "0.7rem", background: "#1a1a2e", padding: "2px 6px", borderRadius: 4, whiteSpace: "nowrap" },
  summary: { color: "#666", fontSize: "0.82rem" }
}