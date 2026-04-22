import { useState, useEffect } from "react"
import API from "../api"

const IMP_COLOR = (n = 0) =>
  n >= 8 ? "var(--red)" :
  n >= 5 ? "var(--amber)" :
  "var(--text3)"

const IMP_LABEL = (n = 0) =>
  n >= 8 ? "HIGH" :
  n >= 5 ? "MED" :
  "LOW"

export default function MemoryPage() {
  const [profile, setProfile] = useState({})
  const [events, setEvents] = useState([])
  const [prefs, setPrefs] = useState([])
  const [filter, setFilter] = useState("all")
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  // -----------------------------
  // LOAD DATA
  // -----------------------------
  useEffect(() => {
    const load = async () => {
      try {
        setLoading(true)

        const [pRes, eRes, prRes] = await Promise.all([
          fetch(`${API}/api/memory/profile`),
          fetch(`${API}/api/memory/events`),
          fetch(`${API}/api/memory/preferences`)
        ])

        if (!pRes.ok || !eRes.ok || !prRes.ok) {
          throw new Error()
        }

        const [p, e, pr] = await Promise.all([
          pRes.json(),
          eRes.json(),
          prRes.json()
        ])

        setProfile(p || {})
        setEvents(Array.isArray(e) ? e : [])
        setPrefs(Array.isArray(pr) ? pr : [])

      } catch {
        setError(true)
      } finally {
        setLoading(false)
      }
    }

    load()
  }, [])

  // -----------------------------
  // FILTER EVENTS
  // -----------------------------
  const eventTypes = ["all", ...new Set(events.map(e => e.type || "unknown"))]

  const filtered =
    filter === "all"
      ? events
      : events.filter(e => e.type === filter)

  // -----------------------------
  // UI
  // -----------------------------
  return (
    <div className="page">

      {/* HEADER */}
      <div className="page-header">
        <div className="page-title">// Memory Core</div>
        <div className="page-sub">
          Stored profile, preferences, and system events
        </div>
      </div>

      {/* LOADING / ERROR */}
      {loading && (
        <div className="card">
          <div>Loading memory...</div>
        </div>
      )}

      {error && (
        <div className="card" style={{ color: "var(--red)" }}>
          Failed to load memory (server may be sleeping)
        </div>
      )}

      {!loading && !error && (
        <>
          {/* HOW IT WORKS */}
          <div className="card" style={{ marginBottom: "1rem" }}>
            <div className="card-title">How Memory Works</div>
            <div style={{ fontSize: "0.8rem", color: "var(--text3)", lineHeight: 1.6 }}>
              ORA stores structured memory in three layers:
              <br />• Profile → core identity data
              <br />• Preferences → learned patterns
              <br />• Events → timeline of interactions and actions
            </div>
          </div>

          {/* PROFILE + PREFS */}
          <div className="grid-2" style={{ marginBottom: "1rem" }}>

            {/* PROFILE */}
            <div className="card">
              <div className="card-title">Identity Profile</div>

              {Object.keys(profile).length === 0 ? (
                <div className="empty">No profile data</div>
              ) : (
                Object.entries(profile).map(([k, v]) => (
                  <div key={k} className="mem-row">
                    <span className="mem-key">
                      {k.replace(/_/g, " ")}
                    </span>
                    <span className="mem-val">
                      {String(v)}
                    </span>
                  </div>
                ))
              )}
            </div>

            {/* PREFS */}
            <div className="card">
              <div className="card-title">Preferences</div>

              {prefs.length === 0 ? (
                <div className="empty">No preferences yet</div>
              ) : (
                prefs.map((p, i) => (
                  <div key={i} className="mem-row">
                    <span className="mem-key">
                      {(p.category || "general")}/{p.key || "unknown"}
                    </span>

                    <div style={{ textAlign: "right" }}>
                      <div className="mem-val">
                        {p.value || "-"}
                      </div>
                      <div style={{ fontSize: "0.65rem", color: "var(--text3)" }}>
                        {Math.round((p.confidence || 0) * 100)}%
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* EVENTS */}
          <div className="card">
            <div style={{
              display: "flex",
              justifyContent: "space-between",
              marginBottom: "1rem"
            }}>
              <div className="card-title">
                Event Log ({events.length})
              </div>

              <div>
                {eventTypes.slice(0, 5).map(t => (
                  <button
                    key={t}
                    onClick={() => setFilter(t)}
                    style={{
                      marginRight: 4,
                      fontSize: "0.65rem",
                      color: filter === t ? "var(--amber)" : "var(--text3)"
                    }}
                  >
                    {t}
                  </button>
                ))}
              </div>
            </div>

            <div style={{ maxHeight: 400, overflowY: "auto" }}>
              {filtered.length === 0 ? (
                <div className="empty">No events</div>
              ) : (
                filtered.map((e, i) => (
                  <div key={i} className="event-row">

                    <div style={{ color: IMP_COLOR(e.importance) }}>
                      {e.type || "event"}
                      <div style={{ fontSize: "0.6rem" }}>
                        {IMP_LABEL(e.importance)}
                      </div>
                    </div>

                    <div className="event-summary">
                      {e.summary || "No summary"}
                    </div>

                    <div className="event-time">
                      {e.timestamp
                        ? e.timestamp.slice(11, 19)
                        : "--:--"}
                    </div>

                  </div>
                ))
              )}
            </div>
          </div>
        </>
      )}

    </div>
  )
}