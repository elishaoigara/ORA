import { useState, useEffect, useCallback } from "react"
import BASE_URL from "../api"

async function api(path) {
  const res = await fetch(BASE_URL + path)
  if (!res.ok) throw new Error("HTTP " + res.status)
  return res.json()
}

function fmtTime(str) {
  if (!str) return "—"
  try {
    const d = new Date(str)
    const now = new Date()
    const diff = now - d
    if (diff < 60000)  return "just now"
    if (diff < 3600000) return Math.floor(diff / 60000) + "m ago"
    if (diff < 86400000) return Math.floor(diff / 3600000) + "h ago"
    return d.toLocaleDateString("en-KE", { day: "numeric", month: "short" })
  } catch { return "—" }
}

function fmtEvent(e) {
  if (e.all_day) return "All day"
  if (!e.start) return "—"
  try {
    return new Date(e.start).toLocaleTimeString("en-KE", { hour: "2-digit", minute: "2-digit", hour12: true })
  } catch { return e.start.slice(11, 16) }
}

function fmtMinutes(m) {
  if (m == null) return ""
  if (m < 0)  return "in progress"
  if (m === 0) return "now"
  if (m < 60) return "in " + m + "m"
  const h = Math.floor(m / 60), mins = m % 60
  return "in " + h + "h" + (mins ? " " + mins + "m" : "")
}

function senderName(from) {
  if (!from) return "Unknown"
  const match = from.match(/^(.+?)\s*</)
  return match ? match[1].replace(/"/g, "").trim() : from.split("@")[0]
}

function senderInitial(from) {
  const name = senderName(from)
  return name.charAt(0).toUpperCase()
}

const AVATAR_COLORS = [
  "#00ff9d", "#4488ff", "#ff9900", "#ff4444", "#cc44ff", "#00ccff"
]
function avatarColor(str) {
  let h = 0
  for (let i = 0; i < str.length; i++) h = str.charCodeAt(i) + ((h << 5) - h)
  return AVATAR_COLORS[Math.abs(h) % AVATAR_COLORS.length]
}

export default function InboxPage() {
  const [tab,          setTab]          = useState("inbox")
  const [emails,       setEmails]       = useState([])
  const [today,        setToday]        = useState([])
  const [week,         setWeek]         = useState([])
  const [summary,      setSummary]      = useState(null)
  const [loading,      setLoading]      = useState(true)
  const [selected,     setSelected]     = useState(null)
  const [calView,      setCalView]      = useState("today")
  const [lastRefresh,  setLastRefresh]  = useState(null)
  const [error,        setError]        = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [sum, evToday, evWeek] = await Promise.allSettled([
        api("/api/gmail/summary"),
        api("/api/calendar/today"),
        api("/api/calendar/week"),
      ])
      if (sum.status === "fulfilled")     setSummary(sum.value)
      if (evToday.status === "fulfilled") setToday(Array.isArray(evToday.value) ? evToday.value : [])
      if (evWeek.status === "fulfilled")  setWeek(Array.isArray(evWeek.value) ? evWeek.value : [])
    } catch (e) {
      setError("Could not reach backend")
    }
    setLastRefresh(new Date())
    setLoading(false)
  }, [])

  const loadEmails = useCallback(async () => {
    try {
      const data = await api("/api/gmail/emails?limit=10")
      setEmails(Array.isArray(data) ? data : [])
    } catch { setEmails([]) }
  }, [])

  useEffect(() => {
    load()
    loadEmails()
    const id = setInterval(() => { load(); loadEmails() }, 5 * 60 * 1000)
    return () => clearInterval(id)
  }, [load, loadEmails])

  const unread   = summary?.unread_count || 0
  const imminent = today.filter(e => e.minutes_until != null && e.minutes_until >= 0 && e.minutes_until <= 60)
  const calEvents = calView === "today" ? today : week

  return (
    <div className="page">
      {/* Header */}
      <div className="page-header">
        <div>
          <div className="page-title">INBOX</div>
          <div className="page-subtitle">GMAIL · CALENDAR · GOOGLE</div>
        </div>
        <button className="btn" onClick={() => { load(); loadEmails() }} disabled={loading}>
          {loading ? <span className="spinner" style={{ width: 14, height: 14 }} /> : "↺ REFRESH"}
        </button>
      </div>

      {/* Metrics */}
      <div className="metrics-row">
        <div className="metric-card">
          <div className="metric-label">UNREAD</div>
          <div className="metric-value" style={{ color: unread > 0 ? "#ff9900" : "#00ff9d" }}>{unread}</div>
          <div className="metric-sub">emails</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">TODAY</div>
          <div className="metric-value" style={{ color: "#4488ff" }}>{today.length}</div>
          <div className="metric-sub">events</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">THIS WEEK</div>
          <div className="metric-value">{week.length}</div>
          <div className="metric-sub">events</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">IMMINENT</div>
          <div className="metric-value" style={{ color: imminent.length > 0 ? "#ff4444" : "#00ff9d" }}>{imminent.length}</div>
          <div className="metric-sub">within 1h</div>
        </div>
      </div>

      {/* Imminent events alert */}
      {imminent.length > 0 && (
        <div style={{
          background: "rgba(255,68,68,0.06)",
          border: "1px solid rgba(255,68,68,0.25)",
          borderRadius: "var(--radius-lg)",
          padding: "12px 16px",
          marginBottom: 14,
          display: "flex",
          flexDirection: "column",
          gap: 6
        }}>
          <div className="mono text-xs" style={{ color: "#ff4444", letterSpacing: 3, marginBottom: 2 }}>⚠ STARTING SOON</div>
          {imminent.map((e, i) => (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <div style={{ width: 6, height: 6, borderRadius: "50%", background: "#ff4444", flexShrink: 0 }} />
              <span style={{ fontSize: 13, color: "var(--text-1)", flex: 1 }}>{e.title}</span>
              <span className="mono text-xs" style={{ color: "#ff4444" }}>{fmtMinutes(e.minutes_until)}</span>
            </div>
          ))}
        </div>
      )}

      {/* Tabs */}
      <div className="filter-tabs" style={{ marginBottom: 14 }}>
        {[
          { id: "inbox",    label: "GMAIL" + (unread > 0 ? " (" + unread + ")" : "") },
          { id: "calendar", label: "CALENDAR" },
        ].map(t => (
          <button key={t.id} className={"filter-tab" + (tab === t.id ? " active" : "")} onClick={() => setTab(t.id)}>
            {t.label}
          </button>
        ))}
      </div>

      {/* ── GMAIL TAB ── */}
      {tab === "inbox" && (
        <div className="card">
          <div className="card-header">
            <span className="card-title">UNREAD EMAILS (LAST 24H)</span>
            <span className="card-badge">{emails.length}</span>
          </div>

          {emails.length === 0 && !loading ? (
            <div className="card-body">
              <div className="empty-state">
                <div className="empty-icon">◉</div>
                <div className="empty-title">Inbox clear</div>
                <div className="empty-body">No unread emails in the last 24 hours</div>
              </div>
            </div>
          ) : (
            <div>
              {emails.map((email, i) => {
                const isSelected = selected?.id === email.id
                const color = avatarColor(email.sender || "?")
                return (
                  <div key={email.id || i}>
                    <div
                      onClick={() => setSelected(isSelected ? null : email)}
                      style={{
                        display: "flex",
                        alignItems: "flex-start",
                        gap: 12,
                        padding: "12px 14px",
                        borderBottom: "1px solid var(--border)",
                        cursor: "pointer",
                        background: isSelected ? "rgba(0,255,157,0.04)" : "transparent",
                        transition: "background 0.15s"
                      }}
                    >
                      {/* Avatar */}
                      <div style={{
                        width: 34, height: 34, borderRadius: "50%",
                        background: color + "22",
                        border: "1px solid " + color + "44",
                        display: "flex", alignItems: "center", justifyContent: "center",
                        fontFamily: "var(--mono)", fontSize: 12, fontWeight: 700,
                        color: color, flexShrink: 0
                      }}>
                        {senderInitial(email.sender)}
                      </div>

                      {/* Content */}
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 3 }}>
                          <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text-1)" }}>
                            {senderName(email.sender)}
                          </span>
                          <span className="mono text-xs" style={{ color: "var(--text-4)", flexShrink: 0, marginLeft: 8 }}>
                            {fmtTime(email.date)}
                          </span>
                        </div>
                        <div style={{ fontSize: 12, color: "var(--text-2)", marginBottom: 3, fontWeight: 500 }}>
                          {email.subject || "(no subject)"}
                        </div>
                        <div style={{ fontSize: 11, color: "var(--text-4)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                          {email.body?.slice(0, 120) || ""}
                        </div>

                        {/* Label chips */}
                        {email.labels && email.labels.length > 0 && (
                          <div style={{ display: "flex", gap: 4, marginTop: 6, flexWrap: "wrap" }}>
                            {email.labels.filter(l => !["UNREAD", "INBOX"].includes(l)).slice(0, 3).map(l => (
                              <span key={l} style={{
                                fontFamily: "var(--mono)", fontSize: 8, letterSpacing: 1,
                                padding: "2px 6px", borderRadius: 3,
                                background: "var(--bg-2)", border: "1px solid var(--border-2)",
                                color: "var(--text-4)"
                              }}>
                                {l.replace("CATEGORY_", "").replace("_", " ")}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Expanded body */}
                    {isSelected && (
                      <div style={{
                        padding: "14px 16px 16px",
                        borderBottom: "1px solid var(--border)",
                        background: "rgba(0,255,157,0.02)"
                      }}>
                        <div className="mono text-xs" style={{ color: "var(--text-4)", marginBottom: 8, letterSpacing: 1 }}>
                          FROM: {email.sender}
                        </div>
                        <div style={{
                          fontSize: 13, color: "var(--text-2)", lineHeight: 1.7,
                          whiteSpace: "pre-wrap", wordBreak: "break-word",
                          maxHeight: 320, overflowY: "auto",
                          background: "var(--bg-2)", border: "1px solid var(--border)",
                          borderRadius: "var(--radius)", padding: "12px 14px"
                        }}>
                          {email.body || "(no body)"}
                        </div>
                        <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
                          <button
                            className="btn btn-sm"
                            onClick={() => navigator.clipboard.writeText(email.body || "")}
                          >
                            ⎘ COPY
                          </button>
                          <button className="btn btn-sm" onClick={() => setSelected(null)}>
                            ✕ CLOSE
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}

      {/* ── CALENDAR TAB ── */}
      {tab === "calendar" && (
        <>
          <div className="filter-tabs" style={{ marginBottom: 14 }}>
            {[{ id: "today", label: "TODAY (" + today.length + ")" }, { id: "week", label: "THIS WEEK (" + week.length + ")" }].map(v => (
              <button key={v.id} className={"filter-tab" + (calView === v.id ? " active" : "")} onClick={() => setCalView(v.id)}>
                {v.label}
              </button>
            ))}
          </div>

          <div className="card">
            <div className="card-header">
              <span className="card-title">{calView === "today" ? "TODAY'S EVENTS" : "WEEK AHEAD"}</span>
              <span className="card-badge">{calEvents.length}</span>
            </div>

            {calEvents.length === 0 ? (
              <div className="card-body">
                <div className="empty-state">
                  <div className="empty-icon">◈</div>
                  <div className="empty-title">{calView === "today" ? "Nothing scheduled today" : "Clear week"}</div>
                  <div className="empty-body">Your calendar is free</div>
                </div>
              </div>
            ) : (
              <div>
                {calEvents.map((ev, i) => {
                  const isNow = ev.minutes_until != null && ev.minutes_until < 0
                  const isSoon = ev.minutes_until != null && ev.minutes_until >= 0 && ev.minutes_until <= 60
                  const dotColor = isNow ? "#00ff9d" : isSoon ? "#ff4444" : "#4488ff"

                  return (
                    <div key={ev.id || i} style={{
                      display: "flex",
                      alignItems: "flex-start",
                      gap: 14,
                      padding: "12px 14px",
                      borderBottom: "1px solid var(--border)",
                      background: isNow ? "rgba(0,255,157,0.03)" : isSoon ? "rgba(255,68,68,0.03)" : "transparent"
                    }}>
                      {/* Time column */}
                      <div style={{ width: 52, flexShrink: 0, textAlign: "right" }}>
                        <div className="mono" style={{ fontSize: 11, color: "var(--text-3)", fontWeight: 600 }}>
                          {fmtEvent(ev)}
                        </div>
                        {calView === "week" && (
                          <div className="mono" style={{ fontSize: 9, color: "var(--text-5)", marginTop: 2 }}>
                            {ev.start ? new Date(ev.start).toLocaleDateString("en-KE", { weekday: "short", day: "numeric" }).toUpperCase() : ""}
                          </div>
                        )}
                      </div>

                      {/* Dot */}
                      <div style={{ paddingTop: 4, flexShrink: 0 }}>
                        <div style={{ width: 7, height: 7, borderRadius: "50%", background: dotColor }} />
                      </div>

                      {/* Event */}
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontSize: 13, color: isNow ? "var(--text-1)" : "var(--text-2)", fontWeight: isNow ? 600 : 400, marginBottom: 3 }}>
                          {ev.title}
                        </div>
                        {ev.location && (
                          <div className="mono text-xs" style={{ color: "var(--text-4)", marginBottom: 2 }}>
                            ⌖ {ev.location}
                          </div>
                        )}
                        {ev.description && (
                          <div style={{ fontSize: 11, color: "var(--text-4)", lineHeight: 1.4 }}>
                            {ev.description.slice(0, 100)}{ev.description.length > 100 ? "…" : ""}
                          </div>
                        )}
                      </div>

                      {/* Status */}
                      <div style={{ flexShrink: 0, textAlign: "right" }}>
                        {ev.minutes_until != null && (
                          <span className="mono" style={{ fontSize: 10, color: dotColor, fontWeight: 700 }}>
                            {fmtMinutes(ev.minutes_until)}
                          </span>
                        )}
                        {ev.all_day && (
                          <span className="mono text-xs" style={{ color: "var(--text-4)" }}>ALL DAY</span>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>

          {lastRefresh && (
            <div className="mono text-xs text-dimmer" style={{ textAlign: "center", marginTop: 8 }}>
              UPDATED {lastRefresh.toLocaleTimeString("en-KE", { hour: "2-digit", minute: "2-digit" })} · AUTO-REFRESHES EVERY 5 MIN
            </div>
          )}
        </>
      )}
    </div>
  )
}