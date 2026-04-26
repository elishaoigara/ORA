import { useState, useEffect, useCallback } from "react"
import {
  getStatus, getAlerts, getTasks, getTheNumber,
  getMpesaSummary, getGoals, getCalendarToday,
  getAgentStatus, ackAlert, ackAllAlerts,
} from "../api"

// ── Helpers ───────────────────────────────────────────────────
function Meter({ label, value = 0, unit = "%" }) {
  const v = Number(value) || 0
  const color = v > 80 ? "var(--red)" : v > 60 ? "var(--amber)" : "var(--green)"
  return (
    <div className="meter">
      <div className="meter-header">
        <span className="meter-label">{label}</span>
        <span className="meter-value" style={{ color }}>{v}{unit}</span>
      </div>
      <div className="meter-track">
        <div className="meter-bar" style={{ width: `${Math.min(v, 100)}%`, background: color }} />
      </div>
    </div>
  )
}

function TheNumber({ task }) {
  if (!task || task.status === "empty") return null
  return (
    <div style={{
      gridColumn: "1 / -1",
      padding: "1rem 1.25rem",
      background: "linear-gradient(135deg, rgba(245,158,11,.08), rgba(245,158,11,.02))",
      border: "1px solid rgba(245,158,11,.3)",
      borderLeft: "4px solid var(--amber)",
      borderRadius: 8,
      marginBottom: ".75rem",
      position: "relative",
      overflow: "hidden",
    }}>
      <div style={{
        position: "absolute", top: 0, left: 0, right: 0, bottom: 0,
        background: "radial-gradient(ellipse at left, rgba(245,158,11,.04), transparent 60%)",
        pointerEvents: "none",
      }} />
      <div style={{ fontFamily: "Share Tech Mono, monospace", fontSize: ".58rem", color: "var(--text3)", letterSpacing: 3, marginBottom: 6 }}>
        ◈ THE NUMBER — TODAY'S TOP PRIORITY
      </div>
      <div style={{ fontFamily: "Orbitron, monospace", fontSize: "1rem", color: "var(--amber)", textShadow: "0 0 15px rgba(245,158,11,.5)", marginBottom: 6, lineHeight: 1.4 }}>
        {task.title}
      </div>
      <div style={{ display: "flex", gap: "1rem", fontSize: ".72rem", color: "var(--text3)", flexWrap: "wrap" }}>
        <span style={{ color: task.priority === "high" ? "var(--red)" : task.priority === "medium" ? "var(--amber)" : "var(--green)", fontWeight: 700 }}>
          {task.priority?.toUpperCase()}
        </span>
        {task.overdue && <span style={{ color: "var(--red)", fontWeight: 700 }}>⚠ OVERDUE</span>}
        <span>{task.reason}</span>
        <span style={{ marginLeft: "auto", fontFamily: "Share Tech Mono, monospace" }}>
          SCORE: {task.score}
        </span>
      </div>
    </div>
  )
}

function MpesaWidget({ summary }) {
  if (!summary || summary.status === "error") return null
  const today = summary.today || {}
  const avg   = summary.average_daily || 0
  const ratio = avg > 0 ? (today.total / avg) : 0
  const color = ratio >= 3 ? "var(--red)" : ratio >= 1.5 ? "var(--amber)" : "var(--green)"
  return (
    <div className="card">
      <div className="card-title">// M-Pesa · Financial</div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: 8 }}>
        <div>
          <div style={{ fontFamily: "Orbitron, monospace", fontSize: "1.3rem", color, lineHeight: 1 }}>
            Ksh {(today.total || 0).toLocaleString()}
          </div>
          <div style={{ fontSize: ".68rem", color: "var(--text3)", marginTop: 3 }}>
            spent today · {today.transactions || 0} txns
          </div>
        </div>
        <div style={{ textAlign: "right" }}>
          <div style={{ fontSize: ".68rem", color: "var(--text3)" }}>Daily avg</div>
          <div style={{ fontFamily: "Share Tech Mono, monospace", fontSize: ".9rem", color: "var(--text2)" }}>
            Ksh {avg.toLocaleString()}
          </div>
        </div>
      </div>
      <div style={{ background: "var(--border)", borderRadius: 4, height: 4 }}>
        <div style={{ width: `${Math.min(ratio * 33, 100)}%`, height: "100%", background: color, borderRadius: 4, transition: "width .6s ease" }} />
      </div>
      {ratio >= 3 && <div style={{ fontSize: ".68rem", color: "var(--red)", marginTop: 4 }}>⚠ 3× daily average — spike detected</div>}
      {summary.last_7_days?.length > 0 && (
        <div style={{ marginTop: 10 }}>
          <div style={{ fontSize: ".6rem", color: "var(--text3)", marginBottom: 4, fontFamily: "Share Tech Mono, monospace", letterSpacing: 1 }}>LAST 7 DAYS</div>
          <div style={{ display: "flex", gap: 3, alignItems: "flex-end", height: 28 }}>
            {(() => {
              const byDay = {}
              summary.last_7_days.forEach(r => { byDay[r.day] = (byDay[r.day] || 0) + r.total })
              const entries = Object.entries(byDay).slice(-7)
              const max = Math.max(...entries.map(e => e[1]), 1)
              return entries.map(([day, total]) => (
                <div key={day} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 2 }}>
                  <div style={{ width: "100%", background: "var(--amber)", opacity: .5, height: `${Math.round((total / max) * 24)}px`, borderRadius: "2px 2px 0 0", minHeight: 2 }} />
                  <div style={{ fontSize: ".48rem", color: "var(--text3)" }}>{day.slice(8)}</div>
                </div>
              ))
            })()}
          </div>
        </div>
      )}
    </div>
  )
}

function CalendarWidget({ events }) {
  if (!events?.length) return (
    <div className="card">
      <div className="card-title">// Today's Calendar</div>
      <div className="empty">
        <div className="empty-icon" style={{ color: "var(--cyan)" }}>📅</div>
        <span>No events · <a href="/api/auth/google" style={{ color: "var(--amber)" }} target="_blank" rel="noreferrer">Connect Google</a></span>
      </div>
    </div>
  )
  return (
    <div className="card">
      <div className="card-title">// Today's Calendar · {events.length} event{events.length !== 1 ? "s" : ""}</div>
      {events.slice(0, 5).map((e, i) => {
        const imminent = e.minutes_until != null && e.minutes_until >= 0 && e.minutes_until <= 30
        return (
          <div key={i} className="calendar-event">
            <div className="cal-time">
              {e.all_day ? "ALL DAY" : e.minutes_until != null
                ? (e.minutes_until <= 0 ? "NOW" : `${e.minutes_until}m`)
                : e.start?.slice(11, 16) || "—"}
            </div>
            <div>
              <div className="cal-title">{e.title}</div>
              {e.location && <div style={{ fontSize: ".62rem", color: "var(--text3)" }}>📍 {e.location}</div>}
              {imminent && <div className="cal-imminent">● STARTING SOON</div>}
            </div>
          </div>
        )
      })}
    </div>
  )
}

function GoalsWidget({ goals }) {
  if (!goals?.length) return null
  return (
    <div className="card">
      <div className="card-title">// Active Goals</div>
      {goals.slice(0, 4).map((g, i) => {
        const pct      = g.progress || 0
        const overdue  = g.due_at && new Date(g.due_at) < new Date()
        const color    = overdue ? "var(--red)" : pct >= 70 ? "var(--green)" : "var(--amber)"
        return (
          <div key={i} className="goal-row">
            <div className="goal-title">{g.goal}</div>
            <div className="goal-bar-track">
              <div className="goal-bar-fill" style={{ width: `${pct}%`, background: color }} />
            </div>
            <div className="goal-meta">
              <span>{pct}% complete</span>
              <span style={{ color: overdue ? "var(--red)" : "var(--text3)" }}>
                {overdue ? "⚠ OVERDUE" : g.due_at ? `due ${g.due_at.slice(0, 10)}` : "no deadline"}
              </span>
            </div>
          </div>
        )
      })}
    </div>
  )
}

function AgentRibbon({ ctx }) {
  if (!ctx) return null
  return (
    <div className="agent-ribbon">
      <div className="agent-ribbon-item">
        <div className="agent-dot" />
        <span>AGENT CYCLE</span>
      </div>
      <div className="agent-ribbon-item">TASKS <span className="agent-ribbon-val">{ctx.tasks ?? 0}</span></div>
      <div className="agent-ribbon-item">OVERDUE <span className="agent-ribbon-val" style={{ color: ctx.overdue > 0 ? "var(--red)" : "var(--green)" }}>{ctx.overdue ?? 0}</span></div>
      <div className="agent-ribbon-item">GOALS <span className="agent-ribbon-val">{ctx.goals ?? 0}</span></div>
      <div className="agent-ribbon-item">CALENDAR <span className="agent-ribbon-val" style={{ color: "var(--cyan)" }}>{ctx.calendar_today ?? 0}</span></div>
      {ctx.pending_actions?.length > 0 && (
        <div className="agent-ribbon-item" style={{ marginLeft: "auto", color: "var(--amber)" }}>
          {ctx.pending_actions.length} pending action{ctx.pending_actions.length > 1 ? "s" : ""}
        </div>
      )}
    </div>
  )
}

// ── Main ──────────────────────────────────────────────────────
export default function DashboardPage() {
  const [status,    setStatus]    = useState(null)
  const [alerts,    setAlerts]    = useState([])
  const [tasks,     setTasks]     = useState([])
  const [theNumber, setTheNumber] = useState(null)
  const [mpesa,     setMpesa]     = useState(null)
  const [goals,     setGoals]     = useState([])
  const [calendar,  setCalendar]  = useState([])
  const [agentCtx,  setAgentCtx]  = useState(null)

  const fetchAll = useCallback(async () => {
    const results = await Promise.allSettled([
      getStatus(), getAlerts(10), getTasks(), getTheNumber(),
      getMpesaSummary(), getGoals(), getCalendarToday(), getAgentStatus(),
    ])
    const [s, a, t, n, m, g, c, ag] = results.map(r => r.status === "fulfilled" ? r.value : null)
    if (s)  setStatus(s)
    if (a)  setAlerts(Array.isArray(a) ? a : [])
    if (t)  setTasks(Array.isArray(t) ? t : [])
    if (n)  setTheNumber(n)
    if (m)  setMpesa(m)
    if (g)  setGoals(Array.isArray(g) ? g : [])
    if (c)  setCalendar(Array.isArray(c) ? c : [])
    if (ag) setAgentCtx(ag)
  }, [])

  const ack = async (id) => {
    await ackAlert(id).catch(() => {})
    fetchAll()
  }

  const ackAll = async () => {
    await ackAllAlerts().catch(() => {})
    fetchAll()
  }

  useEffect(() => {
    fetchAll()
    const t = setInterval(fetchAll, 15000)
    return () => clearInterval(t)
  }, [fetchAll])

  const active    = alerts.filter(a => !a.acknowledged)
  const sevColor  = { high: "var(--red)", medium: "var(--amber)", low: "var(--green)", critical: "var(--red)" }
  const isOnline  = status && typeof status.cpu === "number"
  const statusColor = isOnline ? "var(--green)" : "var(--red)"

  return (
    <div className="page">
      <div className="page-header">
        <div className="page-title">// Command Center</div>
        <div className="page-sub">Real-time intelligence feed · Nairobi, KE · EAT</div>
      </div>

      {/* Agent ribbon */}
      <AgentRibbon ctx={agentCtx} />

      {/* Stat row */}
      <div className="grid-3" style={{ marginBottom: "1rem" }}>
        <div className="stat-box">
          <div className="stat-num">{tasks.length}</div>
          <div className="stat-label">Pending Tasks</div>
        </div>
        <div className="stat-box">
          <div className="stat-num" style={{ color: active.length > 0 ? "var(--red)" : "var(--green)" }}>{active.length}</div>
          <div className="stat-label">Active Alerts</div>
        </div>
        <div className="stat-box">
          <div className="stat-num" style={{ color: statusColor }}>{isOnline ? "ON" : status === null ? "···" : "OFF"}</div>
          <div className="stat-label">ORA Status</div>
        </div>
      </div>

      {/* The Number */}
      <TheNumber task={theNumber} />

      <div className="grid-2">

        {/* System */}
        <div className="card">
          <div className="card-title">// System Monitor</div>
          {isOnline ? (
            <>
              <Meter label="CPU_LOAD"  value={status.cpu} />
              <Meter label="RAM_USED"  value={status.ram} />
              <div style={{ fontFamily: "Share Tech Mono, monospace", fontSize: ".6rem", color: "var(--text3)", marginTop: 8, letterSpacing: 1 }}>
                SYNC: {status.time ? new Date(status.time).toLocaleTimeString() : "—"}
              </div>
            </>
          ) : (
            <div className="empty">
              <div className="empty-icon">⌛</div>
              {status === null ? "Connecting to ORA..." : "Backend unreachable"}
            </div>
          )}
        </div>

        {/* Alerts */}
        <div className="card">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: ".75rem" }}>
            <div className="card-title" style={{ marginBottom: 0 }}>// Alert Feed</div>
            {active.length > 0 && (
              <button className="btn btn-ghost" style={{ fontSize: ".6rem" }} onClick={ackAll}>
                ACK ALL
              </button>
            )}
          </div>
          {active.length === 0 ? (
            <div className="empty">
              <div className="empty-icon" style={{ color: "var(--green)" }}>◉</div>
              All systems nominal
            </div>
          ) : (
            active.slice(0, 4).map(a => (
              <div key={a.id} className={`alert-row ${a.severity}`}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <div className="alert-severity" style={{ color: sevColor[a.severity] || "var(--amber)" }}>
                    {a.severity?.toUpperCase()}
                  </div>
                  <button className="btn btn-ghost" onClick={() => ack(a.id)} style={{ fontSize: ".58rem", padding: "2px 6px" }}>
                    ACK
                  </button>
                </div>
                <div className="alert-msg">{a.message}</div>
                <div style={{ fontFamily: "Share Tech Mono, monospace", fontSize: ".58rem", color: "var(--text3)", marginTop: 3 }}>
                  {a.timestamp?.slice(11, 19)} · {a.rule_name}
                </div>
              </div>
            ))
          )}
        </div>

        {/* M-Pesa */}
        <MpesaWidget summary={mpesa} />

        {/* Task Queue */}
        <div className="card">
          <div className="card-title">// Task Queue · {tasks.length} pending</div>
          {tasks.length === 0 ? (
            <div className="empty">
              <div className="empty-icon">◆</div>
              Queue empty · Add via chat or Telegram
            </div>
          ) : (
            tasks.slice(0, 5).map(t => (
              <div key={t.id} className="task-row">
                <div>
                  <div className="task-title">{t.title}</div>
                  <div className="task-meta">
                    #{t.id} · {t.created_at?.slice(0, 10)}
                    {t.due_at && ` · DUE ${t.due_at.slice(11, 16)}`}
                  </div>
                </div>
                <div style={{
                  fontFamily: "Share Tech Mono, monospace", fontSize: ".68rem", fontWeight: 700,
                  color: t.priority === "high" ? "var(--red)" : t.priority === "medium" ? "var(--amber)" : "var(--green)"
                }}>
                  {t.priority?.toUpperCase()}
                </div>
              </div>
            ))
          )}
          {tasks.length > 5 && (
            <div style={{ fontSize: ".7rem", color: "var(--text3)", textAlign: "center", paddingTop: 6 }}>
              +{tasks.length - 5} more · see Task Queue
            </div>
          )}
        </div>

        {/* Calendar */}
        <CalendarWidget events={calendar} />

        {/* Goals */}
        <GoalsWidget goals={goals} />

      </div>
    </div>
  )
}