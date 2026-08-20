import { useState, useEffect, useCallback } from "react"
import { apiFetch } from "../api"

async function api(path) {
  const res = await apiFetch(path)
  if (!res.ok) throw new Error("HTTP " + res.status)
  return res.json()
}

async function apiPost(path, body) {
  const res = await apiFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  })
  if (!res.ok) throw new Error("HTTP " + res.status)
  return res.json()
}

async function apiPut(path, body) {
  const res = await apiFetch(path, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  })
  if (!res.ok) throw new Error("HTTP " + res.status)
  return res.json()
}

function fmtTime(str) {
  if (!str) return "—"
  try {
    const d = new Date(str)
    const now = new Date()
    const diff = now - d
    if (diff < 60000)   return "just now"
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
  if (m < 0)   return "in progress"
  if (m === 0) return "now"
  if (m < 60)  return "in " + m + "m"
  const h = Math.floor(m / 60), mins = m % 60
  return "in " + h + "h" + (mins ? " " + mins + "m" : "")
}

function senderName(from) {
  if (!from) return "Unknown"
  const match = from.match(/^(.+?)\s*</)
  return match ? match[1].replace(/"/g, "").trim() : from.split("@")[0]
}

function senderInitial(from) {
  return senderName(from).charAt(0).toUpperCase()
}

const AVATAR_COLORS = ["#00ff9d", "#4488ff", "#ff9900", "#ff4444", "#cc44ff", "#00ccff"]
function avatarColor(str) {
  let h = 0
  for (let i = 0; i < str.length; i++) h = str.charCodeAt(i) + ((h << 5) - h)
  return AVATAR_COLORS[Math.abs(h) % AVATAR_COLORS.length]
}

// ── Compose Reply Modal ────────────────────────────────────────────────────────
function ComposeModal({ email, onClose, onSent }) {
  const [text, setText] = useState("")
  const [tone, setTone] = useState("professional")
  const [generating, setGenerating] = useState(false)
  const [sending, setSending] = useState(false)
  const [toast, setToast] = useState(null)

  const showToast = (msg, type = "success") => {
    setToast({ msg, type })
    setTimeout(() => setToast(null), 3000)
  }

  const generate = async () => {
    setGenerating(true)
    try {
      // Save to suggested_replies and get back the text
      const r = await apiPost("/api/gmail/replies/generate-single", {
        email_id:   email.id,
        thread_id:  email.thread_id,
        subject:    email.subject,
        sender:     email.sender,
        email_body: email.body || email.snippet || "",
        tone,
        account:    email.account || "primary",
      })
      if (r.suggested_text) setText(r.suggested_text)
      else showToast("Could not generate — try again", "error")
    } catch {
      showToast("Generation failed", "error")
    } finally {
      setGenerating(false)
    }
  }

  const send = async () => {
    if (!text.trim()) return showToast("Write a reply first", "error")
    setSending(true)
    try {
      // Save the reply, then create an approval-ledger action; execution is separate.
      const saved = await apiPost("/api/gmail/replies/generate-single", {
        email_id:       email.id,
        thread_id:      email.thread_id,
        subject:        email.subject,
        sender:         email.sender,
        email_body:     email.body || email.snippet || "",
        suggested_text: text,
        tone,
        account:        email.account || "primary",
      })
      if (saved.reply_id) {
        const result = await apiPost(`/api/gmail/replies/${saved.reply_id}/approve`)
        if (result.action) {
          showToast(`Approval queued — action #${result.action.id}`)
          setTimeout(() => { onSent && onSent(); onClose() }, 1200)
        } else {
          showToast("Could not create approval action", "error")
        }
      } else {
        showToast("Failed to queue reply", "error")
      }
    } catch {
      showToast("Send failed", "error")
    } finally {
      setSending(false)
    }
  }

  return (
    <div style={{
      position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)",
      display: "flex", alignItems: "center", justifyContent: "center",
      zIndex: 1000, padding: 20,
    }}>
      <div style={{
        background: "var(--bg-1)", border: "1px solid var(--border)",
        borderRadius: "var(--radius-lg)", width: "100%", maxWidth: 560,
        maxHeight: "90vh", overflowY: "auto",
      }}>
        {/* Header */}
        <div style={{
          padding: "14px 18px", borderBottom: "1px solid var(--border)",
          display: "flex", justifyContent: "space-between", alignItems: "center",
        }}>
          <div>
            <div className="mono text-xs" style={{ color: "var(--text-4)", letterSpacing: 2, marginBottom: 4 }}>
              REPLY TO
            </div>
            <div style={{ fontSize: 13, color: "var(--text-1)", fontWeight: 600 }}>
              {senderName(email.sender)}
            </div>
            <div style={{ fontSize: 11, color: "var(--text-4)", marginTop: 2 }}>
              {email.subject || "(no subject)"}
            </div>
          </div>
          <button className="btn btn-sm" onClick={onClose}>✕</button>
        </div>

        <div style={{ padding: "16px 18px" }}>
          {/* Original email preview */}
          <div style={{
            fontSize: 11, color: "var(--text-4)", lineHeight: 1.5,
            background: "var(--bg-2)", border: "1px solid var(--border)",
            borderRadius: "var(--radius)", padding: "8px 10px",
            marginBottom: 14, maxHeight: 80, overflowY: "auto",
            fontStyle: "italic",
          }}>
            {(email.body || email.snippet || "").slice(0, 300)}
            {(email.body || "").length > 300 ? "…" : ""}
          </div>

          {/* Tone selector */}
          <div style={{ marginBottom: 12 }}>
            <div className="mono text-xs" style={{ color: "var(--text-4)", marginBottom: 6, letterSpacing: 1 }}>
              TONE
            </div>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              {["professional", "friendly", "brief", "formal"].map(t => (
                <button
                  key={t}
                  onClick={() => setTone(t)}
                  style={{
                    padding: "4px 10px", borderRadius: "var(--radius)",
                    border: `1px solid ${tone === t ? "rgba(0,255,157,0.5)" : "var(--border)"}`,
                    background: tone === t ? "rgba(0,255,157,0.08)" : "transparent",
                    color: tone === t ? "#00ff9d" : "var(--text-3)",
                    fontSize: 11, fontFamily: "var(--mono)", cursor: "pointer",
                    letterSpacing: 1, textTransform: "uppercase",
                  }}
                >
                  {t}
                </button>
              ))}
            </div>
          </div>

          {/* AI Generate button */}
          <button
            className="btn"
            style={{ width: "100%", marginBottom: 12, justifyContent: "center" }}
            onClick={generate}
            disabled={generating}
          >
            {generating
              ? <><span className="spinner" style={{ width: 12, height: 12 }} /> GENERATING...</>
              : "⚡ AI GENERATE REPLY"}
          </button>

          {/* Reply textarea */}
          <div className="mono text-xs" style={{ color: "var(--text-4)", marginBottom: 6, letterSpacing: 1 }}>
            YOUR REPLY
          </div>
          <textarea
            value={text}
            onChange={e => setText(e.target.value)}
            placeholder="Write your reply here, or click AI Generate above..."
            rows={7}
            style={{
              width: "100%", background: "var(--bg-2)",
              border: "1px solid var(--border-2)",
              borderRadius: "var(--radius)", padding: "10px 12px",
              color: "var(--text-1)", fontSize: 13, lineHeight: 1.7,
              resize: "vertical", fontFamily: "inherit", boxSizing: "border-box",
            }}
          />

          {toast && (
            <div style={{
              padding: "8px 12px", borderRadius: "var(--radius)", marginTop: 10,
              background: toast.type === "error" ? "rgba(255,68,68,0.1)" : "rgba(0,255,157,0.08)",
              border: `1px solid ${toast.type === "error" ? "rgba(255,68,68,0.3)" : "rgba(0,255,157,0.3)"}`,
              color: toast.type === "error" ? "#ff4444" : "#00ff9d",
              fontSize: 12, fontFamily: "var(--mono)",
            }}>
              {toast.msg}
            </div>
          )}

          {/* Actions */}
          <div style={{ display: "flex", gap: 8, marginTop: 14 }}>
            <button
              className="btn"
              style={{
                flex: 1, justifyContent: "center",
                background: "rgba(0,255,157,0.1)",
                borderColor: "rgba(0,255,157,0.3)", color: "#00ff9d",
              }}
              onClick={send}
              disabled={sending || !text.trim()}
            >
              {sending
                ? <><span className="spinner" style={{ width: 12, height: 12 }} /> QUEUING...</>
                : "✓ REQUEST APPROVAL"}
            </button>
            <button className="btn" onClick={onClose} disabled={sending}>
              CANCEL
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────────
export default function InboxPage() {
  const [tab,            setTab]            = useState("inbox")
  const [emails,         setEmails]         = useState([])
  const [today,          setToday]          = useState([])
  const [week,           setWeek]           = useState([])
  const [summary,        setSummary]        = useState(null)
  const [loading,        setLoading]        = useState(true)
  const [selected,       setSelected]       = useState(null)
  const [calView,        setCalView]        = useState("today")
  const [lastRefresh,    setLastRefresh]    = useState(null)
  const [_error,         setError]          = useState(null)
  const [composing,      setComposing]      = useState(null)  // email being replied to
  const [filterUnread,   setFilterUnread]   = useState(false)

  // Smart replies
  const [pendingReplies, setPendingReplies] = useState([])
  const [replyStats,     setReplyStats]     = useState(null)
  const [editingId,      setEditingId]      = useState(null)
  const [editText,       setEditText]       = useState("")
  const [replyLoading,   setReplyLoading]   = useState(false)
  const [replyToast,     setReplyToast]     = useState(null)
  const [generating,     setGenerating]     = useState(false)

  const showReplyToast = (msg, type = "success") => {
    setReplyToast({ msg, type })
    setTimeout(() => setReplyToast(null), 3000)
  }

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
    } catch {
      setError("Could not reach backend")
    }
    setLastRefresh(new Date())
    setLoading(false)
  }, [])

  const loadEmails = useCallback(async () => {
    try {
      const data = await api("/api/gmail/emails?limit=25")
      setEmails(Array.isArray(data) ? data : [])
    } catch { setEmails([]) }
  }, [])

  const loadReplies = useCallback(async () => {
    try {
      const [pending, stats] = await Promise.allSettled([
        api("/api/gmail/replies/pending"),
        api("/api/gmail/replies/stats"),
      ])
      if (pending.status === "fulfilled") setPendingReplies(Array.isArray(pending.value) ? pending.value : [])
      if (stats.status === "fulfilled")   setReplyStats(stats.value)
    } catch { setPendingReplies([]) }
  }, [])

  useEffect(() => {
    load(); loadEmails(); loadReplies()
    const id = setInterval(() => { load(); loadEmails(); loadReplies() }, 5 * 60 * 1000)
    return () => clearInterval(id)
  }, [load, loadEmails, loadReplies])

  const unread    = summary?.unread_count || 0
  const total     = summary?.total_count  || emails.length
  const imminent  = today.filter(e => e.minutes_until != null && e.minutes_until >= 0 && e.minutes_until <= 60)
  const calEvents = calView === "today" ? today : week

  const displayedEmails = filterUnread
    ? emails.filter(e => e.is_unread)
    : emails

  return (
    <div className="page">
      {/* Compose modal */}
      {composing && (
        <ComposeModal
          email={composing}
          onClose={() => setComposing(null)}
          onSent={() => { loadEmails(); loadReplies() }}
        />
      )}

      {/* Header */}
      <div className="page-header">
        <div>
          <div className="page-title">INBOX</div>
          <div className="page-subtitle">GMAIL · CALENDAR · GOOGLE</div>
        </div>
        <button className="btn" onClick={() => { load(); loadEmails(); loadReplies() }} disabled={loading}>
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
          <div className="metric-label">TOTAL</div>
          <div className="metric-value" style={{ color: "#4488ff" }}>{total}</div>
          <div className="metric-sub">in inbox</div>
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
          padding: "12px 16px", marginBottom: 14,
          display: "flex", flexDirection: "column", gap: 6,
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
          { id: "replies",  label: "SMART REPLIES" + (pendingReplies.length > 0 ? " (" + pendingReplies.length + ")" : "") },
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
            <span className="card-title">PRIMARY INBOX</span>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              {/* Unread filter toggle */}
              <button
                onClick={() => setFilterUnread(f => !f)}
                style={{
                  padding: "3px 10px", borderRadius: "var(--radius)",
                  border: `1px solid ${filterUnread ? "rgba(255,153,0,0.5)" : "var(--border)"}`,
                  background: filterUnread ? "rgba(255,153,0,0.08)" : "transparent",
                  color: filterUnread ? "#ff9900" : "var(--text-4)",
                  fontSize: 10, fontFamily: "var(--mono)", cursor: "pointer",
                  letterSpacing: 1,
                }}
              >
                {filterUnread ? "● UNREAD" : "○ ALL"}
              </button>
              <span className="card-badge">{displayedEmails.length}</span>
            </div>
          </div>

          {displayedEmails.length === 0 && !loading ? (
            <div className="card-body">
              <div className="empty-state">
                <div className="empty-icon">◉</div>
                <div className="empty-title">{filterUnread ? "No unread emails" : "Inbox clear"}</div>
                <div className="empty-body">
                  {filterUnread ? "Switch to ALL to see all emails" : "No emails in your primary inbox"}
                </div>
              </div>
            </div>
          ) : (
            <div>
              {displayedEmails.map((email, i) => {
                const isSelected = selected?.id === email.id
                const color = avatarColor(email.sender || "?")
                return (
                  <div key={email.id || i}>
                    <div
                      onClick={() => setSelected(isSelected ? null : email)}
                      style={{
                        display: "flex", alignItems: "flex-start", gap: 12,
                        padding: "12px 14px",
                        borderBottom: "1px solid var(--border)",
                        cursor: "pointer",
                        background: isSelected ? "rgba(0,255,157,0.04)" : "transparent",
                        transition: "background 0.15s",
                        opacity: email.is_unread ? 1 : 0.7,
                      }}
                    >
                      {/* Unread dot */}
                      <div style={{ paddingTop: 14, flexShrink: 0 }}>
                        <div style={{
                          width: 6, height: 6, borderRadius: "50%",
                          background: email.is_unread ? "#00ff9d" : "transparent",
                          border: email.is_unread ? "none" : "1px solid var(--border-2)",
                        }} />
                      </div>

                      {/* Avatar */}
                      <div style={{
                        width: 34, height: 34, borderRadius: "50%",
                        background: color + "22", border: "1px solid " + color + "44",
                        display: "flex", alignItems: "center", justifyContent: "center",
                        fontFamily: "var(--mono)", fontSize: 12, fontWeight: 700,
                        color: color, flexShrink: 0,
                      }}>
                        {senderInitial(email.sender)}
                      </div>

                      {/* Content */}
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 3 }}>
                          <span style={{
                            fontSize: 13,
                            fontWeight: email.is_unread ? 700 : 500,
                            color: "var(--text-1)",
                          }}>
                            {senderName(email.sender)}
                          </span>
                          <span className="mono text-xs" style={{ color: "var(--text-4)", flexShrink: 0, marginLeft: 8 }}>
                            {fmtTime(email.date)}
                          </span>
                        </div>
                        <div style={{
                          fontSize: 12, color: "var(--text-2)", marginBottom: 3,
                          fontWeight: email.is_unread ? 600 : 400,
                        }}>
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
                                color: "var(--text-4)",
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
                        background: "rgba(0,255,157,0.02)",
                      }}>
                        <div className="mono text-xs" style={{ color: "var(--text-4)", marginBottom: 8, letterSpacing: 1 }}>
                          FROM: {email.sender}
                        </div>
                        <div style={{
                          fontSize: 13, color: "var(--text-2)", lineHeight: 1.7,
                          whiteSpace: "pre-wrap", wordBreak: "break-word",
                          maxHeight: 320, overflowY: "auto",
                          background: "var(--bg-2)", border: "1px solid var(--border)",
                          borderRadius: "var(--radius)", padding: "12px 14px",
                        }}>
                          {email.body || "(no body)"}
                        </div>
                        <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
                          {/* Reply button — opens compose modal */}
                          <button
                            className="btn btn-sm"
                            style={{
                              background: "rgba(0,255,157,0.1)",
                              borderColor: "rgba(0,255,157,0.3)", color: "#00ff9d",
                            }}
                            onClick={e => { e.stopPropagation(); setComposing(email) }}
                          >
                            ↩ REPLY
                          </button>
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

      {/* ── SMART REPLIES TAB ── */}
      {tab === "replies" && (
        <div>
          {/* Stats row */}
          {replyStats && (
            <div className="metrics-row" style={{ marginBottom: 14 }}>
              {[
                { label: "PENDING",  value: replyStats.pending,  color: replyStats.pending > 0 ? "#ff9900" : "#00ff9d" },
                { label: "SENT",     value: replyStats.sent,     color: "#00ff9d" },
                { label: "APPROVED", value: replyStats.approved, color: "#4488ff" },
                { label: "REJECTED", value: replyStats.rejected, color: "var(--text-4)" },
              ].map(s => (
                <div className="metric-card" key={s.label}>
                  <div className="metric-label">{s.label}</div>
                  <div className="metric-value" style={{ color: s.color }}>{s.value}</div>
                </div>
              ))}
            </div>
          )}

          {/* How it works */}
          <div style={{
            background: "rgba(68,136,255,0.04)",
            border: "1px solid rgba(68,136,255,0.15)",
            borderRadius: "var(--radius)", padding: "10px 14px", marginBottom: 14,
            fontSize: 12, color: "var(--text-3)", lineHeight: 1.6,
          }}>
            <span className="mono" style={{ color: "#4488ff", fontSize: 10, letterSpacing: 1 }}>HOW IT WORKS</span>
            <br />
            ORA scans your inbox, drafts replies for emails that need a response, and waits for your approval.
            Click <strong style={{ color: "var(--text-2)" }}>Generate</strong> to scan now, or open any email in the Gmail tab and click <strong style={{ color: "var(--text-2)" }}>↩ Reply</strong> to compose directly.
          </div>

          {/* Generate button */}
          <div style={{ display: "flex", gap: 8, marginBottom: 14 }}>
            <button
              className="btn"
              disabled={generating}
              onClick={async () => {
                setGenerating(true)
                try {
                  const r = await apiPost("/api/gmail/replies/generate")
                  showReplyToast(`Generated ${r.generated} new suggestion(s)`)
                  loadReplies()
                } catch { showReplyToast("Generation failed", "error") }
                finally { setGenerating(false) }
              }}
            >
              {generating
                ? <><span className="spinner" style={{ width: 12, height: 12 }} /> SCANNING INBOX...</>
                : "⚡ GENERATE REPLY SUGGESTIONS"}
            </button>
          </div>

          {replyToast && (
            <div style={{
              padding: "10px 14px", borderRadius: "var(--radius)", marginBottom: 12,
              background: replyToast.type === "error" ? "rgba(255,68,68,0.1)" : "rgba(0,255,157,0.08)",
              border: `1px solid ${replyToast.type === "error" ? "rgba(255,68,68,0.3)" : "rgba(0,255,157,0.3)"}`,
              color: replyToast.type === "error" ? "#ff4444" : "#00ff9d",
              fontSize: 12, fontFamily: "var(--mono)",
            }}>
              {replyToast.msg}
            </div>
          )}

          <div className="card">
            <div className="card-header">
              <span className="card-title">PENDING SMART REPLIES</span>
              <span className="card-badge">{pendingReplies.length}</span>
            </div>

            {pendingReplies.length === 0 ? (
              <div className="card-body">
                <div className="empty-state">
                  <div className="empty-icon">✉</div>
                  <div className="empty-title">No pending replies</div>
                  <div className="empty-body">Click Generate to scan your inbox for emails that need replies</div>
                </div>
              </div>
            ) : (
              <div>
                {pendingReplies.map(reply => {
                  const isEditing = editingId === reply.id
                  return (
                    <div key={reply.id} style={{ borderBottom: "1px solid var(--border)", padding: "14px 16px" }}>
                      {/* Header */}
                      <div style={{ marginBottom: 8 }}>
                        <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text-1)", marginBottom: 2 }}>
                          {reply.subject || "(no subject)"}
                        </div>
                        <div className="mono text-xs" style={{ color: "var(--text-4)" }}>
                          FROM: {reply.sender || "unknown"}
                          {reply.account && reply.account !== "primary" && (
                            <span style={{ marginLeft: 8, color: "#4488ff" }}>via {reply.account}</span>
                          )}
                        </div>
                      </div>

                      {/* Original email */}
                      {reply.email_body && (
                        <div style={{
                          fontSize: 11, color: "var(--text-4)", lineHeight: 1.5,
                          background: "var(--bg-2)", border: "1px solid var(--border)",
                          borderRadius: "var(--radius)", padding: "8px 10px",
                          marginBottom: 10, maxHeight: 80, overflowY: "auto",
                          fontStyle: "italic",
                        }}>
                          {reply.email_body.slice(0, 280)}{reply.email_body.length > 280 ? "…" : ""}
                        </div>
                      )}

                      {/* Suggested reply */}
                      <div className="mono text-xs" style={{ color: "var(--text-4)", marginBottom: 4, letterSpacing: 1 }}>
                        ORA SUGGESTS ({(reply.tone || "professional").toUpperCase()}):
                      </div>
                      {isEditing ? (
                        <textarea
                          value={editText}
                          onChange={e => setEditText(e.target.value)}
                          rows={5}
                          style={{
                            width: "100%", background: "var(--bg-2)",
                            border: "1px solid rgba(0,255,157,0.3)",
                            borderRadius: "var(--radius)", padding: "10px 12px",
                            color: "var(--text-1)", fontSize: 12, lineHeight: 1.6,
                            resize: "vertical", fontFamily: "inherit", boxSizing: "border-box",
                          }}
                        />
                      ) : (
                        <div style={{
                          fontSize: 13, color: "var(--text-2)", lineHeight: 1.7,
                          whiteSpace: "pre-wrap", background: "var(--bg-2)",
                          border: "1px solid var(--border)", borderRadius: "var(--radius)",
                          padding: "10px 12px", marginBottom: 10,
                        }}>
                          {reply.suggested_text}
                        </div>
                      )}

                      {/* Actions */}
                      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 10 }}>
                        {!isEditing ? (
                          <>
                            <button
                              className="btn btn-sm"
                              style={{ background: "rgba(0,255,157,0.1)", borderColor: "rgba(0,255,157,0.3)", color: "#00ff9d" }}
                              disabled={replyLoading}
                              onClick={async () => {
                                setReplyLoading(true)
                                try {
                                  const r = await apiPost(`/api/gmail/replies/${reply.id}/approve`)
                                  showReplyToast(r.action ? `Approval queued — action #${r.action.id}` : "Approval action created")
                                  loadReplies()
                                } catch { showReplyToast("Failed", "error") }
                                finally { setReplyLoading(false) }
                              }}
                            >
                              {replyLoading ? "⋯" : "✓ REQUEST SEND APPROVAL"}
                            </button>
                            <button
                              className="btn btn-sm"
                              onClick={() => { setEditingId(reply.id); setEditText(reply.suggested_text) }}
                            >
                              ✎ EDIT
                            </button>
                            {["professional", "brief", "friendly", "formal"].map(tone => (
                              <button
                                key={tone}
                                className="btn btn-sm"
                                style={{ opacity: 0.7, fontSize: 10 }}
                                disabled={replyLoading}
                                onClick={async () => {
                                  setReplyLoading(true)
                                  try {
                                    await apiPost(`/api/gmail/replies/${reply.id}/regenerate`, { tone })
                                    showReplyToast(`Regenerated (${tone})`)
                                    loadReplies()
                                  } catch { showReplyToast("Regen failed", "error") }
                                  finally { setReplyLoading(false) }
                                }}
                              >
                                ↺ {tone.toUpperCase()}
                              </button>
                            ))}
                            <button
                              className="btn btn-sm"
                              style={{ borderColor: "rgba(255,68,68,0.3)", color: "#ff4444" }}
                              onClick={async () => {
                                try {
                                  await apiPost(`/api/gmail/replies/${reply.id}/reject`)
                                  showReplyToast("Dismissed")
                                  loadReplies()
                                } catch {}
                              }}
                            >
                              ✕ DISMISS
                            </button>
                          </>
                        ) : (
                          <>
                            <button
                              className="btn btn-sm"
                              style={{ background: "rgba(0,255,157,0.1)", borderColor: "rgba(0,255,157,0.3)", color: "#00ff9d" }}
                              onClick={async () => {
                                try {
                                  await apiPut(`/api/gmail/replies/${reply.id}/text`, { text: editText })
                                  setEditingId(null)
                                  showReplyToast("Saved")
                                  loadReplies()
                                } catch { showReplyToast("Save failed", "error") }
                              }}
                            >
                              ✓ SAVE
                            </button>
                            <button className="btn btn-sm" onClick={() => setEditingId(null)}>
                              ✕ CANCEL
                            </button>
                          </>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── CALENDAR TAB ── */}
      {tab === "calendar" && (
        <>
          <div className="filter-tabs" style={{ marginBottom: 14 }}>
            {[
              { id: "today", label: "TODAY (" + today.length + ")" },
              { id: "week",  label: "THIS WEEK (" + week.length + ")" },
            ].map(v => (
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
                  const isNow  = ev.minutes_until != null && ev.minutes_until < 0
                  const isSoon = ev.minutes_until != null && ev.minutes_until >= 0 && ev.minutes_until <= 60
                  const dotColor = isNow ? "#00ff9d" : isSoon ? "#ff4444" : "#4488ff"
                  return (
                    <div key={ev.id || i} style={{
                      display: "flex", alignItems: "flex-start", gap: 14,
                      padding: "12px 14px", borderBottom: "1px solid var(--border)",
                      background: isNow ? "rgba(0,255,157,0.03)" : isSoon ? "rgba(255,68,68,0.03)" : "transparent",
                    }}>
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
                      <div style={{ paddingTop: 4, flexShrink: 0 }}>
                        <div style={{ width: 7, height: 7, borderRadius: "50%", background: dotColor }} />
                      </div>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontSize: 13, color: isNow ? "var(--text-1)" : "var(--text-2)", fontWeight: isNow ? 600 : 400, marginBottom: 3 }}>
                          {ev.title}
                        </div>
                        {ev.location && (
                          <div className="mono text-xs" style={{ color: "var(--text-4)", marginBottom: 2 }}>⌖ {ev.location}</div>
                        )}
                        {ev.description && (
                          <div style={{ fontSize: 11, color: "var(--text-4)", lineHeight: 1.4 }}>
                            {ev.description.slice(0, 100)}{ev.description.length > 100 ? "…" : ""}
                          </div>
                        )}
                      </div>
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