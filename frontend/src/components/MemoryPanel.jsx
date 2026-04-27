export default function MemoryPanel({ profile, events }) {
  return (
    <div className="card fade-in">
      <div className="card-title">MEMORY CORE</div>

      {/* PROFILE */}
      {profile && Object.keys(profile).length > 0 && (
        <div style={{ marginBottom: "1rem" }}>
          <div className="card-title" style={{ opacity: 0.6 }}>
            PROFILE DATA
          </div>

          {Object.entries(profile).map(([k, v]) => (
            <div key={k} className="mem-row">
              <div className="mem-key">{k}</div>
              <div className="mem-val">{v}</div>
            </div>
          ))}
        </div>
      )}

      {/* EVENTS */}
      {events && events.length > 0 && (
        <div>
          <div className="card-title" style={{ opacity: 0.6 }}>
            RECENT EVENTS
          </div>

          {events.slice(0, 8).map((e, i) => (
            <div key={i} className="event-row">
              <div className="mem-key">{e.type}</div>

              <div className="event-summary">
                {e.summary}
              </div>

              {e.time && (
                <div className="event-time">
                  {formatTime(e.time)}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* EMPTY STATE */}
      {!profile?.length && !events?.length && (
        <div className="empty">
          <div className="empty-icon">◎</div>
          <div>No memory records</div>
        </div>
      )}
    </div>
  )
}

/* Small helper */
function formatTime(t) {
  try {
    return new Date(t).toLocaleTimeString("en-KE", {
      hour: "2-digit",
      minute: "2-digit",
    })
  } catch {
    return ""
  }
}