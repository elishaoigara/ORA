import { useState, useEffect, useRef, useCallback } from "react"
import {
  sendMessage, getConversations, getTasks, getGoals,
  getMpesaSummary, getCalendarToday, getAgentStatus, getAlerts,
  createTask, completeTask, getStatus,
} from "../api"
import BASE from "../api"

/* ─────────────────────────────────────────────
   QUICK ACTIONS — expanded set
   ───────────────────────────────────────────── */
const QUICK = [
  { label: "📋 Tasks",    msg: "what are my pending tasks" },
  { label: "🎯 Goals",    msg: "show my active goals and progress" },
  { label: "💳 Spend",    msg: "how much have I spent today on mpesa" },
  { label: "📊 Briefing", msg: "give me a full morning briefing" },
  { label: "⚡ Alerts",   msg: "any active alerts or issues" },
  { label: "📅 Calendar", msg: "what events do I have today" },
  { label: "🔮 Focus",    msg: "what should I focus on right now" },
  { label: "🧠 Memory",   msg: "what do you know about me" },
]

/* ─────────────────────────────────────────────
   ACTION CHIPS — direct backend actions
   ───────────────────────────────────────────── */
const ACTIONS = [
  { label: "+ Task",    type: "add_task" },
  { label: "✓ Done",   type: "complete_task" },
  { label: "⚙ Status", type: "sys_status" },
]

/* ─────────────────────────────────────────────
   SIMPLE MARKDOWN renderer (no deps)
   ───────────────────────────────────────────── */
function renderMarkdown(text) {
  if (!text) return []
  const lines = text.split("\n")
  const out = []
  let i = 0
  while (i < lines.length) {
    const line = lines[i]
    if (/^#{1,3}\s/.test(line)) {
      out.push({ type: "heading", text: line.replace(/^#{1,3}\s/, "") })
    } else if (/^[-•*]\s/.test(line)) {
      const items = []
      while (i < lines.length && /^[-•*]\s/.test(lines[i])) {
        items.push(lines[i].replace(/^[-•*]\s/, ""))
        i++
      }
      out.push({ type: "list", items })
      continue
    } else if (/^\d+\.\s/.test(line)) {
      const items = []
      while (i < lines.length && /^\d+\.\s/.test(lines[i])) {
        items.push(lines[i].replace(/^\d+\.\s/, ""))
        i++
      }
      out.push({ type: "olist", items })
      continue
    } else if (line.startsWith("```")) {
      const code = []
      i++
      while (i < lines.length && !lines[i].startsWith("```")) {
        code.push(lines[i])
        i++
      }
      out.push({ type: "code", text: code.join("\n") })
    } else if (line.trim() === "") {
      out.push({ type: "spacer" })
    } else {
      out.push({ type: "para", text: line })
    }
    i++
  }
  return out
}

function inlineFmt(text) {
  // bold, italic, code inline
  return text
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    .replace(/`(.+?)`/g, "<code style=\"background:rgba(0,255,157,.1);padding:1px 5px;border-radius:3px;font-size:.88em\">$1</code>")
}

function MsgBody({ content }) {
  const blocks = renderMarkdown(content)
  if (blocks.length === 0) return <p>{content}</p>
  return (
    <div className="msg-body">
      {blocks.map((b, i) => {
        if (b.type === "heading")
          return <div key={i} style={{ fontFamily: "Orbitron, monospace", fontSize: ".78rem", color: "var(--cyan)", letterSpacing: 1, marginBottom: 4, marginTop: 8 }}>{b.text}</div>
        if (b.type === "list")
          return <ul key={i} style={{ paddingLeft: "1.2rem", margin: "4px 0" }}>{b.items.map((it, j) => <li key={j} style={{ fontSize: ".85rem", lineHeight: 1.6 }} dangerouslySetInnerHTML={{ __html: inlineFmt(it) }} />)}</ul>
        if (b.type === "olist")
          return <ol key={i} style={{ paddingLeft: "1.4rem", margin: "4px 0" }}>{b.items.map((it, j) => <li key={j} style={{ fontSize: ".85rem", lineHeight: 1.6 }} dangerouslySetInnerHTML={{ __html: inlineFmt(it) }} />)}</ol>
        if (b.type === "code")
          return <pre key={i} style={{ background: "rgba(0,0,0,.35)", border: "1px solid var(--border)", borderRadius: 6, padding: "8px 10px", fontSize: ".78rem", overflowX: "auto", margin: "6px 0", fontFamily: "Share Tech Mono, monospace" }}>{b.text}</pre>
        if (b.type === "spacer")
          return <div key={i} style={{ height: 4 }} />
        return <p key={i} style={{ fontSize: ".9rem", lineHeight: 1.7, margin: "2px 0" }} dangerouslySetInnerHTML={{ __html: inlineFmt(b.text) }} />
      })}
    </div>
  )
}

/* ─────────────────────────────────────────────
   LIVE CONTEXT PANEL
   ───────────────────────────────────────────── */
function ContextPanel({ visible }) {
  const [tasks, setTasks]       = useState([])
  const [goals, setGoals]       = useState([])
  const [alerts, setAlerts]     = useState([])
  const [cal, setCal]           = useState([])
  const [sys, setSys]           = useState(null)
  const [loading, setLoading]   = useState(true)

  useEffect(() => {
    if (!visible) return
    const load = async () => {
      setLoading(true)
      const [t, g, a, c, s] = await Promise.allSettled([
        getTasks("pending"), getGoals(), getAlerts(10),
        getCalendarToday(), getStatus(),
      ])
      if (t.status === "fulfilled") setTasks(Array.isArray(t.value) ? t.value.slice(0, 5) : [])
      if (g.status === "fulfilled") setGoals(Array.isArray(g.value) ? g.value.slice(0, 4) : [])
      if (a.status === "fulfilled") setAlerts(Array.isArray(a.value) ? a.value.filter(x => !x.acknowledged).slice(0, 3) : [])
      if (c.status === "fulfilled") setCal(Array.isArray(c.value) ? c.value.slice(0, 3) : [])
      if (s.status === "fulfilled") setSys(s.value)
      setLoading(false)
    }
    load()
    const t = setInterval(load, 30000)
    return () => clearInterval(t)
  }, [visible])

  if (!visible) return null

  return (
    <div className="ctx-panel">
      <div className="ctx-title">// LIVE CONTEXT</div>
      {loading ? (
        <div style={{ fontSize: ".7rem", color: "var(--text3)", padding: "8px 0" }}>Loading...</div>
      ) : (
        <>
          {sys && (
            <div className="ctx-section">
              <div className="ctx-label">SYS</div>
              <div className="ctx-row">
                <span style={{ color: sys.cpu > 80 ? "var(--red)" : "var(--green)" }}>CPU {sys.cpu?.toFixed(0)}%</span>
                <span style={{ color: sys.ram > 85 ? "var(--red)" : "var(--text2)" }}>RAM {sys.ram?.toFixed(0)}%</span>
              </div>
            </div>
          )}
          {cal.length > 0 && (
            <div className="ctx-section">
              <div className="ctx-label">CALENDAR</div>
              {cal.map((e, i) => (
                <div key={i} className="ctx-row">
                  <span style={{ color: "var(--cyan)", fontSize: ".65rem", minWidth: 36 }}>
                    {e.minutes_until != null && e.minutes_until >= 0 ? `${e.minutes_until}m` : "NOW"}
                  </span>
                  <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontSize: ".72rem" }}>{e.title}</span>
                </div>
              ))}
            </div>
          )}
          {alerts.length > 0 && (
            <div className="ctx-section">
              <div className="ctx-label" style={{ color: "var(--red)" }}>⚠ ALERTS</div>
              {alerts.map((a, i) => (
                <div key={i} style={{ fontSize: ".68rem", color: "var(--red)", marginBottom: 2, opacity: .85 }}>{a.message?.slice(0, 50)}</div>
              ))}
            </div>
          )}
          {tasks.length > 0 && (
            <div className="ctx-section">
              <div className="ctx-label">TASKS ({tasks.length})</div>
              {tasks.map((t, i) => (
                <div key={i} className="ctx-row">
                  <span style={{ color: t.priority === "high" ? "var(--red)" : t.priority === "medium" ? "var(--amber)" : "var(--text3)", fontSize: ".6rem", minWidth: 6 }}>●</span>
                  <span style={{ fontSize: ".7rem", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{t.title}</span>
                </div>
              ))}
            </div>
          )}
          {goals.length > 0 && (
            <div className="ctx-section">
              <div className="ctx-label">GOALS</div>
              {goals.map((g, i) => (
                <div key={i} style={{ marginBottom: 5 }}>
                  <div style={{ fontSize: ".68rem", color: "var(--text2)", marginBottom: 2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{g.goal?.slice(0, 40)}</div>
                  <div style={{ background: "var(--border)", height: 2, borderRadius: 2 }}>
                    <div style={{ width: `${g.progress || 0}%`, height: "100%", background: "var(--green)", borderRadius: 2 }} />
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}

/* ─────────────────────────────────────────────
   ACTION MODAL — for direct task actions
   ───────────────────────────────────────────── */
function ActionModal({ type, onClose, onDone }) {
  const [val, setVal] = useState("")
  const [taskId, setTaskId] = useState("")
  const [loading, setLoading] = useState(false)
  const [msg, setMsg] = useState(null)

  const handleAddTask = async () => {
    if (!val.trim()) return
    setLoading(true)
    try {
      await createTask({ title: val.trim(), priority: "medium" })
      setMsg({ ok: true, text: `Task created: "${val.trim()}"` })
      setTimeout(() => { onDone(`Task added: "${val.trim()}"`); onClose() }, 800)
    } catch {
      setMsg({ ok: false, text: "Failed to create task." })
    }
    setLoading(false)
  }

  const handleComplete = async () => {
    const id = parseInt(taskId.trim())
    if (!id) return
    setLoading(true)
    try {
      await completeTask(id)
      setMsg({ ok: true, text: `Task #${id} marked done.` })
      setTimeout(() => { onDone(`Task #${id} marked as complete.`); onClose() }, 800)
    } catch {
      setMsg({ ok: false, text: "Failed. Check the task ID." })
    }
    setLoading(false)
  }

  return (
    <div className="action-modal-overlay" onClick={onClose}>
      <div className="action-modal" onClick={e => e.stopPropagation()}>
        <div className="action-modal-title">
          {type === "add_task" ? "Add Task" : type === "complete_task" ? "Complete Task" : "System Status"}
        </div>

        {type === "add_task" && (
          <>
            <input
              className="input"
              autoFocus
              placeholder="Task title..."
              value={val}
              onChange={e => setVal(e.target.value)}
              onKeyDown={e => e.key === "Enter" && handleAddTask()}
              style={{ marginBottom: 8 }}
            />
            <button className="btn btn-primary" onClick={handleAddTask} disabled={loading || !val.trim()}>
              {loading ? "···" : "CREATE"}
            </button>
          </>
        )}

        {type === "complete_task" && (
          <>
            <input
              className="input"
              autoFocus
              placeholder="Task ID (e.g. 3)"
              value={taskId}
              onChange={e => setTaskId(e.target.value)}
              onKeyDown={e => e.key === "Enter" && handleComplete()}
              style={{ marginBottom: 8 }}
            />
            <button className="btn btn-primary" onClick={handleComplete} disabled={loading || !taskId.trim()}>
              {loading ? "···" : "MARK DONE"}
            </button>
          </>
        )}

        {type === "sys_status" && (
          <SysStatusBlock />
        )}

        {msg && (
          <div style={{ marginTop: 8, fontSize: ".78rem", color: msg.ok ? "var(--green)" : "var(--red)" }}>
            {msg.text}
          </div>
        )}

        <button className="btn btn-ghost" style={{ marginTop: 10, fontSize: ".65rem" }} onClick={onClose}>
          CLOSE
        </button>
      </div>
    </div>
  )
}

function SysStatusBlock() {
  const [data, setData] = useState(null)
  useEffect(() => {
    getStatus().then(setData).catch(() => setData(null))
    getAgentStatus().then(ag => setData(prev => ({ ...prev, agent: ag }))).catch(() => {})
  }, [])

  if (!data) return <div style={{ fontSize: ".8rem", color: "var(--text3)" }}>Loading...</div>

  return (
    <div style={{ fontSize: ".8rem", lineHeight: 2 }}>
      <div>CPU: <span style={{ color: data.cpu > 80 ? "var(--red)" : "var(--green)" }}>{data.cpu?.toFixed(1)}%</span></div>
      <div>RAM: <span style={{ color: data.ram > 85 ? "var(--red)" : "var(--green)" }}>{data.ram?.toFixed(1)}%</span></div>
      {data.agent && (
        <>
          <div>Tasks: <span style={{ color: "var(--amber)" }}>{data.agent.tasks}</span></div>
          <div>Overdue: <span style={{ color: data.agent.overdue > 0 ? "var(--red)" : "var(--green)" }}>{data.agent.overdue}</span></div>
          <div>Goals: <span style={{ color: "var(--cyan)" }}>{data.agent.goals}</span></div>
        </>
      )}
    </div>
  )
}

/* ─────────────────────────────────────────────
   PERSONA LABEL MAP
   ───────────────────────────────────────────── */
function msgLabel(m) {
  if (m.isError) return { text: "ORA // ERROR", color: "var(--red)" }
  if (m.cached)  return { text: "ORA // CACHE HIT", color: "var(--text3)" }
  if (m.intent === "add_task")     return { text: "ORA // TASK CREATED", color: "var(--green)" }
  if (m.intent === "check_tasks")  return { text: "ORA // TASKS", color: "var(--cyan)" }
  if (m.intent === "spend_summary")return { text: "ORA // FINANCE", color: "var(--amber)" }
  if (m.intent === "search_docs")  return { text: "ORA // KNOWLEDGE", color: "var(--purple, #a78bfa)" }
  if (m.intent === "set_goal")     return { text: "ORA // GOAL LOGGED", color: "var(--green)" }
  if (m.intent === "remind")       return { text: "ORA // REMINDER SET", color: "var(--cyan)" }
  if (m.intent)  return { text: `ORA // ${m.intent.toUpperCase()}`, color: "var(--amber)" }
  if (m.model?.includes("70b")) return { text: "ORA // DEEP ANALYSIS", color: "var(--amber)" }
  return { text: "ORA", color: "var(--green)" }
}

/* ─────────────────────────────────────────────
   MESSAGE COMPONENT
   ───────────────────────────────────────────── */
function Message({ msg }) {
  const lbl = msg.role === "assistant" ? msgLabel(msg) : null
  return (
    <div className={`msg ${msg.role} fade-in`}>
      <div className="msg-avatar">
        {msg.role === "user" ? "EL" : "◎"}
      </div>
      <div className="msg-bubble">
        {lbl && (
          <div className="msg-label" style={{ color: lbl.color }}>
            {lbl.text}
          </div>
        )}
        <MsgBody content={msg.content} />
        <div className="event-time">{formatTime(msg.timestamp)}</div>
      </div>
    </div>
  )
}

/* ─────────────────────────────────────────────
   MAIN PAGE
   ───────────────────────────────────────────── */
export default function ChatPage() {
  const [messages,      setMessages]      = useState([])
  const [input,         setInput]         = useState("")
  const [loading,       setLoading]       = useState(false)
  const [backendState,  setBackendState]  = useState("connecting")
  const [showCtx,       setShowCtx]       = useState(false)
  const [activeAction,  setActiveAction]  = useState(null)
  const [charCount,     setCharCount]     = useState(0)

  const bottomRef  = useRef(null)
  const inputRef   = useRef(null)

  /* ── HEALTH ── */
  useEffect(() => {
    fetch(`${BASE}/api/health`)
      .then(r => r.ok ? r.json() : null)
      .then(d => setBackendState(d?.status === "ok" ? "online" : "cold"))
      .catch(() => setBackendState("cold"))
  }, [])

  /* ── HISTORY ── */
  useEffect(() => {
    getConversations(50)
      .then(data => setMessages(Array.isArray(data) ? data : []))
      .catch(() => {})
  }, [])

  /* ── SCROLL ── */
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages, loading])

  /* ── SEND ── */
  const send = useCallback(async (textOverride) => {
    const text = (textOverride ?? input).trim()
    if (!text || loading) return

    setInput("")
    setCharCount(0)
    setLoading(true)

    setMessages(prev => [...prev, { role: "user", content: text, timestamp: now() }])

    try {
      const res = await sendMessage(text)
      setMessages(prev => [...prev, {
        role: "assistant",
        content: res?.reply || "[EMPTY RESPONSE]",
        model: res?.model,
        cached: res?.cached,
        intent: res?.intent,
        timestamp: now(),
      }])
      setBackendState("online")
    } catch {
      setMessages(prev => [...prev, {
        role: "assistant",
        content: "Signal lost. Try again.",
        isError: true,
        timestamp: now(),
      }])
      setBackendState("cold")
    }
    setLoading(false)
    inputRef.current?.focus()
  }, [input, loading])

  /* ── ACTION DONE callback ── */
  const handleActionDone = (confirmText) => {
    setMessages(prev => [...prev, {
      role: "assistant",
      content: `◎ ${confirmText}`,
      timestamp: now(),
      intent: "action",
    }])
  }

  return (
    <div className="chat-page-v2">

      {/* ── HEADER ── */}
      <div className="chat-header-v2">
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div>
            <div className="page-title" style={{ fontSize: "1rem", letterSpacing: 3 }}>NEURAL LINK</div>
            <div className="page-sub" style={{ fontSize: ".62rem" }}>
              Direct channel to ORA
              <span style={{ marginLeft: 8, color: backendState === "online" ? "var(--green)" : backendState === "cold" ? "var(--amber)" : "var(--text3)" }}>
                ● {backendState.toUpperCase()}
              </span>
            </div>
          </div>
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          <button
            className={`btn btn-ghost ${showCtx ? "btn-active" : ""}`}
            style={{ fontSize: ".62rem" }}
            onClick={() => setShowCtx(v => !v)}
          >
            {showCtx ? "◂ HIDE CTX" : "▸ LIVE CTX"}
          </button>
        </div>
      </div>

      <div className="chat-body-layout">

        {/* ── MAIN COLUMN ── */}
        <div className="chat-main-col">

          {/* QUICK PILLS */}
          <div className="pill-row" style={{ paddingBottom: 0 }}>
            {QUICK.map(q => (
              <button key={q.label} className="pill" onClick={() => send(q.msg)} disabled={loading}>
                {q.label}
              </button>
            ))}
          </div>

          {/* ACTION CHIPS */}
          <div className="action-chip-row">
            <span style={{ fontSize: ".58rem", color: "var(--text3)", fontFamily: "Share Tech Mono, monospace", letterSpacing: 1, marginRight: 4 }}>ACTIONS:</span>
            {ACTIONS.map(a => (
              <button
                key={a.type}
                className="action-chip"
                onClick={() => setActiveAction(a.type)}
              >
                {a.label}
              </button>
            ))}
          </div>

          {/* MESSAGES */}
          <div className="chat-messages">
            {messages.length === 0 && <IdleState />}
            {messages.map((m, i) => <Message key={i} msg={m} />)}
            {loading && <TypingIndicator />}
            <div ref={bottomRef} />
          </div>

          {/* INPUT */}
          <div className="chat-input-area">
            <div className="chat-input-row">
              <textarea
                ref={inputRef}
                className="chat-textarea"
                value={input}
                disabled={loading}
                onChange={e => { setInput(e.target.value); setCharCount(e.target.value.length) }}
                onKeyDown={e => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault()
                    send()
                  }
                }}
                placeholder="TRANSMIT MESSAGE  ·  shift+enter for newline"
                rows={2}
              />
              <div className="send-col">
                <button className="btn-send" onClick={() => send()} disabled={loading || !input.trim()}>
                  {loading ? "···" : "SEND ▶"}
                </button>
                {charCount > 0 && (
                  <div style={{ fontSize: ".55rem", color: "var(--text3)", textAlign: "center", marginTop: 3, fontFamily: "Share Tech Mono, monospace" }}>
                    {charCount}
                  </div>
                )}
              </div>
            </div>
          </div>

        </div>

        {/* ── CONTEXT PANEL ── */}
        <ContextPanel visible={showCtx} />

      </div>

      {/* ── ACTION MODAL ── */}
      {activeAction && (
        <ActionModal
          type={activeAction}
          onClose={() => setActiveAction(null)}
          onDone={handleActionDone}
        />
      )}

    </div>
  )
}

/* ─────────────────────────────────────────────
   HELPERS
   ───────────────────────────────────────────── */

function now() { return new Date().toISOString() }

function formatTime(ts) {
  try {
    return new Date(ts).toLocaleTimeString("en-KE", { hour12: false })
  } catch { return "" }
}

function IdleState() {
  return (
    <div className="empty" style={{ marginTop: "5rem" }}>
      <div className="glow-green" style={{ fontSize: "2rem" }}>◎</div>
      <div style={{ fontFamily: "Share Tech Mono, monospace", fontSize: ".75rem", letterSpacing: 2, marginTop: 8 }}>ORA STANDING BY</div>
      <div style={{ fontSize: ".65rem", color: "var(--text3)", marginTop: 6, maxWidth: 320, textAlign: "center", lineHeight: 1.6 }}>
        Ask anything, run actions, or pick a quick command above.
        I have access to your tasks, goals, calendar, spend, alerts, and knowledge base.
      </div>
    </div>
  )
}

function TypingIndicator() {
  return (
    <div className="msg ora fade-in">
      <div className="msg-avatar">◎</div>
      <div className="msg-bubble">
        <div className="msg-label" style={{ color: "var(--green)" }}>ORA // PROCESSING</div>
        <div className="thinking-dots"><span /><span /><span /></div>
      </div>
    </div>
  )
}