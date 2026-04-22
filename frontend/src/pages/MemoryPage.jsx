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

// Safe fetch — never throws, always returns a value or fallback
async function safeFetch(url, fallback) {
  try {
    const res = await fetch(url)
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const data = await res.json()
    return data ?? fallback
  } catch (e) {
    console.error(`[MEMORY] fetch failed: ${url}`, e)
    return fallback
  }
}

export default function MemoryPage() {
  const [profile, setProfile] = useState({})
  const [events, setEvents] = useState([])
  const [prefs, setPrefs] = useState([])
  const [filter, setFilter] = useState("all")
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    const load = async () => {
      setLoading(true)
      setError(null)

      // FIX: fetch each endpoint independently — one failure won't wipe all three.
      const [p, e, pr] = await Promise.all([
        safeFetch(`${API}/api/memory/profile`, {}),
        safeFetch(`${API}/api/memory/events`, []),
        safeFetch(`${API}/api/memory/preferences`, []),
      ])

      // If ALL three came back empty/failed, surface an error
      const allEmpty =
        Object.keys(p).length === 0 &&
        e.length === 0 &&
        pr.length === 0

      setProfile(p)
      setEvents(Array.isArray(e) ? e : [])
      setPrefs(Array.isArray(pr) ? pr : [])

      if (allEmpty) {
        setError("Memory is empty — ORA hasn't stored anything yet, or the backend just restarted.")
      }

      setLoading(false)
    }

    load()
  }, [])

  const eventTypes = ["all", ...new Set(events.map(e => e.type || "unknown"))]

  const filtered =
    filter === "all"
      ? events
      : events.filter(e => e.type === filter)

  return (
    <div className="page">

      <div className="page-header">
        <div className="page-title">// Memory Core</div>
        <div className="page-sub">
          Stored profile, preferences, and system events
        </div>
      </div>

      {loading && (
        <div className="card">
          <div style={{ color: "var(--text3)", fontFamily: "Share Tech Mono, monospace", fontSize: "0.8rem" }}>
            Loading memory...
          </div>
        </div>
      )}

      {/* FIX: show error as info, not blocker — still render whatever data loaded */}
      {!loading && error && (
        <div className="card" style={{ borderColor: "rgba(245,158,11,0.3)", marginBottom: "1rem" }}>
          <div style={{ color: "var(--amber)", fontSize: "0.8rem" }}>
            ⚠ {error}
          </div>
        </div>
      )}

      {!loading && (
        <>
          {/* HOW MEMORY WORKS */}
          <div className="card" style={{ marginBottom: "1rem" }}>
            <div className="card-title">How Memory Works</div>
            <div style={{ fontSize: "0.8rem", color: "var(--text3)", lineHeight: 1.6 }}>
              ORA stores structured memory in three layers:
              <br />• Profile → core identity data (name, role, timezone)
              <br />• Preferences → learned patterns and habits
              <br />• Events → timeline of interactions and system actions
            </div>
          </div>

          {/* PROFILE + PREFS */}
          <div className="grid-2" style={{ marginBottom: "1rem" }}>

            <div className="card">
              <div className="card-title">Identity Profile</div>

              {Object.keys(profile).length === 0 ? (
                <div className="empty">No profile data yet</div>
              ) : (
                Object.entries(profile).map(([k, v]) => (
                  <div key={k} className="mem-row">
                    <span className="mem-key">{k.replace(/_/g, " ")}</span>
                    <span className="mem-val">{String(v)}</span>
                  </div>
                ))
              )}
            </div>

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
                      <div className="mem-val">{p.value || "-"}</div>
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
              alignItems: "center",
              marginBottom: "1rem"
            }}>
              <div className="card-title">
                Event Log ({events.length})
              </div>

              <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                {eventTypes.slice(0, 5).map(t => (
                  <button
                    key={t}
                    onClick={() => setFilter(t)}
                    style={{
                      fontSize: "0.65rem",
                      padding: "2px 6px",
                      background: "none",
                      border: `1px solid ${filter === t ? "var(--amber)" : "var(--border)"}`,
                      color: filter === t ? "var(--amber)" : "var(--text3)",
                      cursor: "pointer",
                      borderRadius: 2,
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
                    <div style={{ color: IMP_COLOR(e.importance), minWidth: 80 }}>
                      <div style={{ fontSize: "0.7rem" }}>{e.type || "event"}</div>
                      <div style={{ fontSize: "0.6rem" }}>{IMP_LABEL(e.importance)}</div>
                    </div>

                    <div className="event-summary">
                      {e.summary || "No summary"}
                    </div>

                    <div className="event-time">
                      {e.timestamp ? e.timestamp.slice(11, 19) : "--:--"}
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